"""Migrate the three share-out tables from StockDevVM SQL Server to Parquet on
Cloudflare R2 — the replacement for _migrate_to_azure.py.

Source  : StockDevVM / ORATS_Options  (pyodbc, Windows auth)  — UNCHANGED engine.
Target  : s3://<bucket>/<prefix><Table>.parquet on R2 (boto3 upload, path-style).

Penny-exact by construction: a pyarrow schema is derived per-column from
INFORMATION_SCHEMA, so decimal(p,s) -> decimal128(p,s) and values stream straight
from pyodbc (decimal.Decimal) into Parquet DECIMAL — never through float64. The
tradelog is sorted by (run_id, day_num) so DuckDB row-group pruning makes per-run
reads on the dashboard fetch only a few MB.

R2 creds are read from .streamlit/secrets.toml [r2].

Usage (PowerShell):
    python _migrate_to_r2.py                      # full load, all tables
    python _migrate_to_r2.py --runs 3981,3982,3983 --prefix poc/ --skip-spx
    python _migrate_to_r2.py --tables Scenario_Runs SPX_Daily_MAs
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import pathlib
import sys
import tempfile
import time
import tomllib

import boto3
from botocore.config import Config
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pyodbc

try:                                   # Windows console defaults to cp1252
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = pathlib.Path(__file__).parent
SRC = ("DRIVER={ODBC Driver 18 for SQL Server};SERVER=StockDevVM;"
       "DATABASE=ORATS_Options;Trusted_Connection=yes;Encrypt=no")

TABLES = ["Scenario_Runs", "Scenario_TradeLog", "SPX_Daily_MAs"]
ORDER_BY = {                       # clustering key -> Parquet row-group pruning
    "Scenario_Runs": "run_id",
    "Scenario_TradeLog": "run_id, day_num",
    "SPX_Daily_MAs": "trade_date",
}
STANDING_WHERE = {"SPX_Daily_MAs": "trade_date >= '2007-01-01'"}
RUN_KEYED = {"Scenario_Runs", "Scenario_TradeLog"}   # filtered by --runs
BATCH = 50_000


# ── R2 plumbing ────────────────────────────────────────────────────────────
def r2_config() -> dict:
    cfg = tomllib.loads((HERE / ".streamlit" / "secrets.toml").read_text())
    r2 = cfg["r2"]
    r2["host"] = r2["endpoint"].split("://", 1)[-1].rstrip("/")
    r2["account_id"] = r2.get("account_id") or r2["host"].split(".")[0]
    return r2


def s3_client(r2: dict):
    return boto3.client("s3", endpoint_url=r2["endpoint"],
                        aws_access_key_id=r2["access_key_id"],
                        aws_secret_access_key=r2["secret_access_key"],
                        region_name="auto",
                        config=Config(signature_version="s3v4",
                                      s3={"addressing_style": "path"}))


def duck_with_r2(r2: dict) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("CREATE SECRET r2 (TYPE S3, KEY_ID ?, SECRET ?, ENDPOINT ?, "
                "URL_STYLE 'path', REGION 'auto', USE_SSL true)",
                [r2["access_key_id"], r2["secret_access_key"], r2["host"]])
    return con


# ── schema derivation: SQL Server -> pyarrow (exact) ───────────────────────
def arrow_type(data_type: str, prec, scale, clen):
    dt_ = data_type.lower()
    if dt_ in ("decimal", "numeric"):
        return pa.decimal128(prec, scale)
    if dt_ == "int":
        return pa.int32()
    if dt_ == "bigint":
        return pa.int64()
    if dt_ == "smallint":
        return pa.int16()
    if dt_ == "tinyint":
        return pa.int16()           # SQL tinyint is 0-255; int16 holds it safely
    if dt_ == "bit":
        return pa.bool_()
    if dt_ == "date":
        return pa.date32()
    if dt_ in ("datetime2", "datetime", "smalldatetime", "datetimeoffset"):
        return pa.timestamp("us")
    if dt_ == "float":
        return pa.float64()
    if dt_ == "real":
        return pa.float32()
    return pa.string()              # char/varchar/nchar/nvarchar/text/...


def table_schema(cur, table: str) -> pa.Schema:
    cur.execute("""
        SELECT COLUMN_NAME, DATA_TYPE, NUMERIC_PRECISION, NUMERIC_SCALE,
               CHARACTER_MAXIMUM_LENGTH
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME=?
        ORDER BY ORDINAL_POSITION""", table)
    fields = []
    for name, dtp, prec, scale, clen in cur.fetchall():
        fields.append(pa.field(name, arrow_type(dtp, prec, scale, clen)))
    return pa.schema(fields)


# ── core: stream one table to a local Parquet, then upload to R2 ───────────
def build_and_upload(src, r2, s3, table: str, runs: list[int] | None,
                     prefix: str) -> tuple[int, str]:
    cur = src.cursor()
    schema = table_schema(cur, table)
    bool_idx = [i for i, f in enumerate(schema) if f.type == pa.bool_()]

    conds = []
    if table in STANDING_WHERE:
        conds.append(STANDING_WHERE[table])
    if runs and table in RUN_KEYED:
        conds.append("run_id IN (" + ",".join(str(int(r)) for r in runs) + ")")
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    cols = ", ".join(f"[{f.name}]" for f in schema)
    sql = f"SELECT {cols} FROM dbo.{table}{where} ORDER BY {ORDER_BY[table]}"

    key = f"{prefix}{table}.parquet"
    tmp = pathlib.Path(tempfile.gettempdir()) / f"_r2mig_{table}.parquet"
    print(f"\n[{table}] querying{(' runs=' + str(runs)) if runs else ''}...", flush=True)
    cur.execute(sql)

    writer = pq.ParquetWriter(tmp, schema, compression="zstd")
    total = 0
    t0 = time.monotonic()
    try:
        while True:
            rows = cur.fetchmany(BATCH)
            if not rows:
                break
            ncols = len(schema)
            columns = [[row[i] for row in rows] for i in range(ncols)]
            for bi in bool_idx:                      # bit -> real bools for pyarrow
                columns[bi] = [None if v is None else bool(v) for v in columns[bi]]
            arrays = [pa.array(columns[i], type=schema.field(i).type)
                      for i in range(ncols)]
            writer.write_batch(pa.record_batch(arrays, schema=schema))
            total += len(rows)
            print(f"\r[{table}] {total:,} rows...", end="", flush=True)
    finally:
        writer.close()
    size_mb = tmp.stat().st_size / 1e6
    print(f"\r[{table}] {total:,} rows -> {tmp.name} ({size_mb:.1f} MB), "
          f"{time.monotonic()-t0:.1f}s. Uploading to s3://{r2['bucket']}/{key} ...",
          flush=True)

    s3.upload_file(str(tmp), r2["bucket"], key)
    tmp.unlink(missing_ok=True)
    print(f"[{table}] uploaded.", flush=True)
    return total, key


# ── validation: counts + penny-exact cell compare vs the source ────────────
def validate(src, con_r2, r2, table, key, runs, sample_runs):
    keycols = ORDER_BY[table]
    # count check
    conds = []
    if table in STANDING_WHERE:
        conds.append(STANDING_WHERE[table])
    if runs and table in RUN_KEYED:
        conds.append("run_id IN (" + ",".join(str(int(r)) for r in runs) + ")")
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    scur = src.cursor()
    scur.execute(f"SELECT COUNT(*) FROM dbo.{table}{where}")
    src_n = scur.fetchone()[0]
    r2_n = con_r2.execute(
        f"SELECT COUNT(*) FROM read_parquet('s3://{r2['bucket']}/{key}')").fetchone()[0]
    ok_count = (src_n == r2_n)
    print(f"[{table}] count  source={src_n:,}  r2={r2_n:,}  "
          f"{'OK' if ok_count else 'MISMATCH'}")

    # exact cell compare on a sample (or all rows if this is the small subset)
    if table in RUN_KEYED:
        cmp_runs = sample_runs if sample_runs else (runs or [])
        if not cmp_runs:
            return ok_count
        rfilter = " WHERE run_id IN (" + ",".join(str(int(r)) for r in cmp_runs) + ")"
    else:
        rfilter = where  # small table — compare everything
    cols = [d[0] for d in
            src.cursor().execute(f"SELECT * FROM dbo.{table} WHERE 1=0").description]
    collist = ", ".join(f"[{c}]" for c in cols)
    scur.execute(f"SELECT {collist} FROM dbo.{table}{rfilter} ORDER BY {keycols}")
    src_rows = scur.fetchall()
    r2_rows = con_r2.execute(
        f"SELECT {', '.join(cols)} FROM read_parquet('s3://{r2['bucket']}/{key}')"
        f"{rfilter} ORDER BY {keycols}").fetchall()

    mism = 0
    if len(src_rows) != len(r2_rows):
        print(f"[{table}] EXACT row-count differs in sample: "
              f"src={len(src_rows)} r2={len(r2_rows)}")
        return False
    for ri, (a, b) in enumerate(zip(src_rows, r2_rows)):
        for ci, (x, y) in enumerate(zip(a, b)):
            if x != y:
                mism += 1
                if mism <= 5:
                    print(f"   mismatch {table}.{cols[ci]} row{ri}: src={x!r} r2={y!r}")
    cells = len(src_rows) * len(cols)
    print(f"[{table}] exact compare: {len(src_rows):,} rows x {len(cols)} cols "
          f"= {cells:,} cells, {mism} mismatch(es) "
          f"{'-- PENNY-EXACT OK' if mism == 0 else '-- FAILED'}")
    return ok_count and mism == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", nargs="+", choices=TABLES, default=None)
    ap.add_argument("--runs", default=None, help="comma list of run_ids (subset test)")
    ap.add_argument("--prefix", default="", help="R2 key prefix, e.g. poc/")
    ap.add_argument("--skip-spx", action="store_true")
    ap.add_argument("--sample-runs", default=None,
                    help="comma list of run_ids to exact-compare on a full load")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    runs = [int(x) for x in args.runs.split(",")] if args.runs else None
    sample_runs = ([int(x) for x in args.sample_runs.split(",")]
                   if args.sample_runs else None)
    tables = args.tables or TABLES
    if args.skip_spx:
        tables = [t for t in tables if t != "SPX_Daily_MAs"]

    r2 = r2_config()
    s3 = s3_client(r2)
    src = pyodbc.connect(SRC, autocommit=True)
    con_r2 = duck_with_r2(r2)

    print(f"Source: StockDevVM/ORATS_Options -> R2 s3://{r2['bucket']}/{args.prefix}")
    results = {}
    for t in tables:
        n, key = build_and_upload(src, r2, s3, t, runs, args.prefix)
        results[t] = key
    if not args.no_validate:
        print("\n-- validation --")
        all_ok = True
        for t in tables:
            all_ok &= validate(src, con_r2, r2, t, results[t], runs, sample_runs)
        print("\n" + ("ALL VALIDATED — penny-exact." if all_ok
                      else "VALIDATION FAILED — see above."))
        sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
