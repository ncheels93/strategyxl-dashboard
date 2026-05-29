"""One-time / repeatable migration of the two share-out tables from the local
VM SQL Server to Azure SQL.

    Scenario_Runs      (parent, IDENTITY run_id)  -> copied with IDENTITY_INSERT
    Scenario_TradeLog  (child,  FK run_id)        -> copied after the parent

Source is read with pyodbc + Windows auth (StockDevVM). Target is written with
pyodbc + fast_executemany (this VM has the MS ODBC driver) for bulk speed. (The
deployed Streamlit app uses pymssql instead, since Streamlit Cloud has no ODBC driver.)

Transfer is raw cursor-to-cursor (no pandas) so DECIMAL values move as
decimal.Decimal and never round-trip through float64 — the engine's penny-exact
values arrive byte-for-byte on Azure.

Usage (PowerShell):
    python _migrate_to_azure.py \
        --server  strategyxl-sql.database.windows.net \
        --database StrategyXL_Share \
        --user    sqladmin
    # password: pass --password, set AZURE_SQL_PASSWORD, or be prompted

Run the schema script (_azure_schema_deploy.sql) against the target FIRST so the
empty tables exist. By default the script refuses to run if the target tables
already hold rows; pass --truncate to wipe and reload.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

import pyodbc

# Parent before child — FK on Scenario_TradeLog.run_id references Scenario_Runs.
TABLES = ["Scenario_Runs", "Scenario_TradeLog"]
IDENTITY_TABLES = {"Scenario_Runs"}  # preserve run_id so drill-in URLs stay stable
BATCH = 2000


def connect_source(server: str, database: str) -> pyodbc.Connection:
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};"
        f"DATABASE={database};Trusted_Connection=yes;Encrypt=no",
        autocommit=True,
    )


def connect_target(server: str, database: str, user: str, password: str) -> pyodbc.Connection:
    # Migration runs from the VM (which has the MS ODBC driver), so use pyodbc +
    # fast_executemany for bulk speed on the ~2.8M tradelog rows. (The deployed app
    # uses pymssql instead, because Streamlit Cloud has no ODBC driver.)
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server},1433;DATABASE={database};"
        f"UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60",
        autocommit=False, timeout=60,
    )


def columns_of(cursor, table: str) -> list[str]:
    cursor.execute(f"SELECT * FROM dbo.{table} WHERE 1 = 0")
    cols = [d[0] for d in cursor.description]
    cursor.fetchall()  # drain the empty result set
    return cols


def migrate_table(src: pyodbc.Connection, tgt: pyodbc.Connection, table: str,
                  truncate: bool) -> int:
    scur = src.cursor()
    tcur = tgt.cursor()
    tcur.fast_executemany = True   # pyodbc bulk param binding — fast for the ~2.8M tradelog rows

    src_cols = columns_of(scur, table)
    tgt_cols = columns_of(tcur, table)
    if src_cols != tgt_cols:
        only_src = set(src_cols) - set(tgt_cols)
        only_tgt = set(tgt_cols) - set(src_cols)
        raise SystemExit(
            f"[{table}] column mismatch source vs target.\n"
            f"  only in source: {sorted(only_src)}\n"
            f"  only in target: {sorted(only_tgt)}\n"
            "Re-deploy _azure_schema_deploy.sql so the schemas match."
        )

    tcur.execute(f"SELECT COUNT(*) FROM dbo.{table}")
    existing = tcur.fetchone()[0]
    if existing:
        if not truncate:
            raise SystemExit(
                f"[{table}] target already has {existing:,} rows. "
                "Pass --truncate to wipe and reload, or clear it manually."
            )
        # DELETE (not TRUNCATE) — TRUNCATE is blocked by the FK on the child table.
        print(f"[{table}] clearing {existing:,} existing rows...")
        tcur.execute(f"DELETE FROM dbo.{table}")
        tgt.commit()

    col_list = ", ".join(f"[{c}]" for c in src_cols)
    placeholders = ", ".join(["?"] * len(src_cols))
    insert_sql = f"INSERT INTO dbo.{table} ({col_list}) VALUES ({placeholders})"

    is_identity = table in IDENTITY_TABLES
    if is_identity:
        tcur.execute(f"SET IDENTITY_INSERT dbo.{table} ON")

    scur.execute(f"SELECT {col_list} FROM dbo.{table}")
    total = 0
    while True:
        rows = scur.fetchmany(BATCH)
        if not rows:
            break
        tcur.executemany(insert_sql, [tuple(r) for r in rows])
        tgt.commit()
        total += len(rows)
        print(f"\r[{table}] {total:,} rows...", end="", flush=True)

    if is_identity:
        tcur.execute(f"SET IDENTITY_INSERT dbo.{table} OFF")
        tgt.commit()

    # Verify
    scur.execute(f"SELECT COUNT(*) FROM dbo.{table}")
    src_count = scur.fetchone()[0]
    tcur.execute(f"SELECT COUNT(*) FROM dbo.{table}")
    tgt_count = tcur.fetchone()[0]
    print(f"\r[{table}] done: {tgt_count:,} rows on target (source {src_count:,}).")
    if src_count != tgt_count:
        raise SystemExit(f"[{table}] COUNT MISMATCH — source {src_count}, target {tgt_count}.")
    return tgt_count


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate share-out tables to Azure SQL.")
    ap.add_argument("--server", required=True, help="Azure SQL server, e.g. xxx.database.windows.net")
    ap.add_argument("--database", default="StrategyXL_Share", help="Target database (default StrategyXL_Share)")
    ap.add_argument("--user", required=True, help="Azure SQL login")
    ap.add_argument("--password", default=None, help="Azure SQL password (or AZURE_SQL_PASSWORD env, or prompt)")
    ap.add_argument("--src-server", default="StockDevVM", help="Source server (default StockDevVM)")
    ap.add_argument("--src-database", default="ORATS_Options", help="Source database (default ORATS_Options)")
    ap.add_argument("--truncate", action="store_true", help="Wipe target tables before loading")
    args = ap.parse_args()

    password = args.password or os.environ.get("AZURE_SQL_PASSWORD") or getpass.getpass("Azure SQL password: ")

    print(f"Source: {args.src_server}/{args.src_database} (Windows auth)")
    print(f"Target: {args.server}/{args.database} (pyodbc + fast_executemany, user={args.user})")
    src = connect_source(args.src_server, args.src_database)
    tgt = connect_target(args.server, args.database, args.user, password)

    try:
        grand = 0
        for table in TABLES:
            grand += migrate_table(src, tgt, table, args.truncate)
        print(f"\nMigration complete — {grand:,} rows across {len(TABLES)} tables.")
    finally:
        src.close()
        tgt.close()


if __name__ == "__main__":
    sys.exit(main())
