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
# SPX_Daily_MAs is standalone reference data (no FK); order doesn't matter.
TABLES = ["Scenario_Runs", "Scenario_TradeLog", "SPX_Daily_MAs"]
IDENTITY_TABLES = {"Scenario_Runs"}  # preserve run_id so drill-in URLs stay stable
# Tables migrated as a SUBSET of the local source. The full-history SPX_Daily_MAs
# lives on StockDevVM; only the 2007+ slice the dashboard needs goes to Azure.
# The filter is applied to both the source SELECT and the source COUNT check.
WHERE_FILTERS = {"SPX_Daily_MAs": "trade_date >= '2007-01-01'"}
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
                  truncate: bool, append_where: str | None = None) -> int:
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
    if existing and not append_where:
        if not truncate:
            raise SystemExit(
                f"[{table}] target already has {existing:,} rows. "
                "Pass --truncate to wipe and reload, --append-where to add new rows, "
                "or clear it manually."
            )
        # DELETE (not TRUNCATE) — TRUNCATE is blocked by the FK on the child table.
        print(f"[{table}] clearing {existing:,} existing rows...")
        tcur.execute(f"DELETE FROM dbo.{table}")
        tgt.commit()
        existing = 0

    col_list = ", ".join(f"[{c}]" for c in src_cols)
    placeholders = ", ".join(["?"] * len(src_cols))
    insert_sql = f"INSERT INTO dbo.{table} ({col_list}) VALUES ({placeholders})"

    # Combine the table's standing subset filter (if any) with the append filter.
    _conds = [c for c in (WHERE_FILTERS.get(table), append_where) if c]
    where_sql = (" WHERE " + " AND ".join(f"({c})" for c in _conds)) if _conds else ""
    if where_sql:
        print(f"[{table}] source filter:{where_sql[7:]}")
    if append_where:
        print(f"[{table}] APPEND mode — target keeps its {existing:,} existing rows.")

    is_identity = table in IDENTITY_TABLES
    if is_identity:
        tcur.execute(f"SET IDENTITY_INSERT dbo.{table} ON")

    scur.execute(f"SELECT {col_list} FROM dbo.{table}{where_sql}")
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

    # Verify — appended rows must equal the SAME-filtered source count
    # (in append mode the target also keeps its pre-existing rows).
    scur.execute(f"SELECT COUNT(*) FROM dbo.{table}{where_sql}")
    src_count = scur.fetchone()[0]
    tcur.execute(f"SELECT COUNT(*) FROM dbo.{table}")
    tgt_count = tcur.fetchone()[0]
    loaded = tgt_count - existing
    print(f"\r[{table}] done: {tgt_count:,} rows on target "
          f"({existing:,} kept + {loaded:,} loaded; source selection {src_count:,}).")
    if src_count != loaded:
        raise SystemExit(f"[{table}] COUNT MISMATCH — source selection {src_count}, loaded {loaded}.")
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
    ap.add_argument("--append-where", default=None,
                    help="Incremental mode: append only source rows matching this SQL predicate "
                         "(e.g. \"run_id > 990\") and keep the target's existing rows. "
                         "Applied to every table migrated — use with --tables.")
    ap.add_argument("--tables", nargs="+", choices=TABLES, default=None,
                    help="Subset of tables to migrate (default: all). "
                         "e.g. --tables SPX_Daily_MAs to add just the daily series.")
    args = ap.parse_args()

    if args.append_where and args.truncate:
        raise SystemExit("--append-where and --truncate are mutually exclusive.")

    tables = args.tables or TABLES

    password = args.password or os.environ.get("AZURE_SQL_PASSWORD") or getpass.getpass("Azure SQL password: ")

    print(f"Source: {args.src_server}/{args.src_database} (Windows auth)")
    print(f"Target: {args.server}/{args.database} (pyodbc + fast_executemany, user={args.user})")
    src = connect_source(args.src_server, args.src_database)
    tgt = connect_target(args.server, args.database, args.user, password)

    try:
        grand = 0
        for table in tables:
            grand += migrate_table(src, tgt, table, args.truncate, args.append_where)
        print(f"\nMigration complete — {grand:,} rows across {len(tables)} table(s).")
    finally:
        src.close()
        tgt.close()


if __name__ == "__main__":
    sys.exit(main())
