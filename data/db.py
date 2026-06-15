"""Data layer with two interchangeable backends, selected from secrets:

  backend = "sql"  → SQLAlchemy + pyodbc to StockDevVM (local dev; LIVE engine data).
  backend = "r2"   → DuckDB reading Parquet from Cloudflare R2 (cloud / pre-deploy preview).

Selection order:
  1. [data].backend in secrets if it's "sql" or "r2"
  2. else "r2" if an [r2] secrets section exists
  3. else "sql"

Local dev pins backend="sql" so you keep reading the live SQL Server exactly as before
(run a backtest on StockDevVM, see it locally with no migration step). Flip it to "r2"
to preview precisely what the deployed app will render before pushing.

Scenario_Requests:
  - sql backend → dbo.Scenario_Requests table (Windows auth has write).
  - r2  backend → one JSON object per request under the requests/ prefix in the bucket.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import time

import pandas as pd
import streamlit as st

_AUTH_COOKIE = "sxl_auth"


def _secrets_section(name: str) -> dict | None:
    """Return a secrets section as a dict, or None if absent. Bare `st.secrets` access
    raises when no secrets file exists, so this needs try/except, not a plain `in` check."""
    try:
        if name in st.secrets:
            return dict(st.secrets[name])
    except Exception:
        pass
    return None


def _backend() -> str:
    data = _secrets_section("data") or {}
    b = str(data.get("backend", "")).lower()
    if b in ("sql", "r2"):
        return b
    return "r2" if _secrets_section("r2") else "sql"


# ─────────────────────────────────────────────────────────────────────────
# SQL backend — StockDevVM via the installed ODBC driver (Windows auth).
# ODBC Driver 18 defaults Encrypt=Mandatory; trust the local cert so the
# connection isn't rejected (same reason sqlcmd needs -C against StockDevVM).
# ─────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _sql_engine():
    from sqlalchemy import create_engine
    conn_str = (
        "mssql+pyodbc://@StockDevVM/ORATS_Options"
        "?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes"
        "&Encrypt=yes&TrustServerCertificate=yes"
    )
    return create_engine(conn_str, pool_pre_ping=True)


def _sql_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    from sqlalchemy import text
    with _sql_engine().connect() as cn:
        return pd.read_sql(text(sql), cn, params=params or {})


# ─────────────────────────────────────────────────────────────────────────
# R2 backend — DuckDB (httpfs, path-style S3) reading Parquet; boto3 for requests.
# ─────────────────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _duck():
    import duckdb
    r2 = _secrets_section("r2")
    host = r2["endpoint"].split("://", 1)[-1].rstrip("/")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    # Explicit S3 secret with path-style addressing — R2 with the account endpoint
    # requires it; the duckdb TYPE R2 shortcut defaults to vhost and 404s.
    con.execute(
        "CREATE SECRET r2 (TYPE S3, KEY_ID ?, SECRET ?, ENDPOINT ?, "
        "URL_STYLE 'path', REGION 'auto', USE_SSL true)",
        [r2["access_key_id"], r2["secret_access_key"], host],
    )
    return con


@st.cache_resource(show_spinner=False)
def _s3():
    import boto3
    from botocore.config import Config
    r2 = _secrets_section("r2")
    return boto3.client(
        "s3", endpoint_url=r2["endpoint"],
        aws_access_key_id=r2["access_key_id"],
        aws_secret_access_key=r2["secret_access_key"],
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _bucket() -> str:
    return _secrets_section("r2")["bucket"]


def _uri(table: str) -> str:
    # table name is a fixed internal constant, never user input → safe to inline.
    return f"s3://{_bucket()}/{table}.parquet"


def _duck_df(sql: str, params: list | None = None) -> pd.DataFrame:
    # .cursor() gives a thread-safe execution context off the cached connection.
    df = _duck().cursor().execute(sql, params or []).df()
    # DuckDB returns SQL `date` columns as datetime64; the SQL path returns python
    # date objects. Coerce back (every datetime col except the one real timestamp)
    # so str()/formatting match exactly — no spurious "00:00:00" on dates.
    for c in df.columns:
        if c != "run_timestamp" and pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.date
    return df


# ═════════════════════════════════════════════════════════════════════════
# Public queries — identical signatures across both backends.
# ═════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner="Loading scenarios…")
def load_scenario_runs() -> pd.DataFrame:
    """All scenarios for the leaderboard. Cached 5 minutes."""
    if _backend() == "r2":
        return _duck_df(f"SELECT * FROM read_parquet('{_uri('Scenario_Runs')}') "
                        "ORDER BY run_id DESC")
    return _sql_df("SELECT * FROM dbo.Scenario_Runs ORDER BY run_id DESC")


@st.cache_data(ttl=1800, show_spinner="Loading trade log…")
def load_trade_log(run_id: int) -> pd.DataFrame:
    """Per-day trade log for one run. Cached 30 minutes."""
    if _backend() == "r2":
        return _duck_df(
            f"SELECT * FROM read_parquet('{_uri('Scenario_TradeLog')}') "
            "WHERE run_id = ? ORDER BY day_num", [int(run_id)])
    return _sql_df(
        "SELECT * FROM dbo.Scenario_TradeLog WHERE run_id = :run_id ORDER BY day_num",
        {"run_id": int(run_id)})


@st.cache_data(ttl=3600, show_spinner="Loading SPX daily MAs…")
def load_spx_daily() -> pd.DataFrame:
    """SPX daily close + all moving averages (2007+ on the share DB). Cached 1 hour."""
    cols = ("trade_date, spx_close, sma_5, sma_10, sma_20, sma_50, sma_100, "
            "sma_150, sma_200, ema_9, ema_20, ema_50, ema_200")
    if _backend() == "r2":
        return _duck_df(f"SELECT {cols} FROM read_parquet('{_uri('SPX_Daily_MAs')}') "
                        "ORDER BY trade_date")
    return _sql_df(f"SELECT {cols} FROM dbo.SPX_Daily_MAs ORDER BY trade_date")


# ─────────────────────────────────────────────────────────────────────────
# Scenario Requests — submit / list / complete / reopen / delete.
# ─────────────────────────────────────────────────────────────────────────
REQUEST_INPUT_COLS = [
    "in_spread_width", "in_trend_filter_on", "in_trend_filter_ma",
    "in_weekly_risk_pct", "in_max_weekly_risk", "in_withdrawals_on",
    "in_target_monthly_withdrawal", "in_withdrawal_floor", "in_starting_capital",
    "in_short_delta_threshold", "in_commission_per_contract", "in_slippage_per_leg",
    "in_otm_close_threshold", "in_breach_close", "in_profit_target", "in_stop_loss",
    "in_backtest_start", "in_backtest_end", "in_inflation_adjust_pct",
]
_REQUEST_COLS = (["request_id", "scenario_name", "requested_by", "requested_at",
                  "status", "result_queue_name", "notes"] + REQUEST_INPUT_COLS)


def _json_safe(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


def _req_key(request_id: int) -> str:
    return f"requests/{int(request_id)}.json"


def _r2_get_request(request_id: int) -> dict:
    body = _s3().get_object(Bucket=_bucket(), Key=_req_key(request_id))["Body"].read()
    return json.loads(body)


def _r2_put_request(rec: dict) -> None:
    _s3().put_object(Bucket=_bucket(), Key=_req_key(rec["request_id"]),
                     Body=json.dumps(rec).encode("utf-8"),
                     ContentType="application/json")


def insert_request(scenario_name: str, requested_by: str, inputs: dict) -> None:
    if _backend() == "sql":
        from sqlalchemy import text
        cols = ["scenario_name", "requested_by"] + REQUEST_INPUT_COLS
        params = {"scenario_name": scenario_name, "requested_by": (requested_by or None)}
        params.update({c: inputs.get(c) for c in REQUEST_INPUT_COLS})
        sql = (f"INSERT INTO dbo.Scenario_Requests ({', '.join(cols)}) "
               f"VALUES ({', '.join(':' + c for c in cols)})")
        with _sql_engine().begin() as cn:
            cn.execute(text(sql), params)
        return
    rec = {
        "request_id": int(time.time() * 1_000_000),   # epoch-µs → unique, int-sortable
        "scenario_name": scenario_name,
        "requested_by": (requested_by or None),
        "requested_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "Pending",
        "result_queue_name": None,
        "notes": None,
    }
    rec.update({c: _json_safe(inputs.get(c)) for c in REQUEST_INPUT_COLS})
    _r2_put_request(rec)


def load_requests() -> pd.DataFrame:
    """All requests, newest first. Not cached — changes on submit/complete/delete."""
    if _backend() == "sql":
        return _sql_df("SELECT * FROM dbo.Scenario_Requests ORDER BY requested_at DESC")
    s3, bkt = _s3(), _bucket()
    recs = []
    token = None
    while True:
        kw = {"Bucket": bkt, "Prefix": "requests/"}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            if o["Key"].endswith(".json"):
                recs.append(json.loads(
                    s3.get_object(Bucket=bkt, Key=o["Key"])["Body"].read()))
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    df = pd.DataFrame(recs, columns=_REQUEST_COLS)
    if not df.empty:
        df = df.sort_values("requested_at", ascending=False).reset_index(drop=True)
    return df


def complete_request(request_id: int, queue_name: str, notes: str | None = None) -> None:
    if _backend() == "sql":
        from sqlalchemy import text
        with _sql_engine().begin() as cn:
            cn.execute(text("UPDATE dbo.Scenario_Requests SET status='Complete', "
                            "result_queue_name=:q, notes=:n WHERE request_id=:id"),
                       {"q": queue_name, "n": (notes or None), "id": int(request_id)})
        return
    rec = _r2_get_request(request_id)
    rec.update(status="Complete", result_queue_name=queue_name, notes=(notes or None))
    _r2_put_request(rec)


def reopen_request(request_id: int) -> None:
    if _backend() == "sql":
        from sqlalchemy import text
        with _sql_engine().begin() as cn:
            cn.execute(text("UPDATE dbo.Scenario_Requests SET status='Pending', "
                            "result_queue_name=NULL WHERE request_id=:id"),
                       {"id": int(request_id)})
        return
    rec = _r2_get_request(request_id)
    rec.update(status="Pending", result_queue_name=None)
    _r2_put_request(rec)


def delete_request(request_id: int) -> None:
    if _backend() == "sql":
        from sqlalchemy import text
        with _sql_engine().begin() as cn:
            cn.execute(text("DELETE FROM dbo.Scenario_Requests WHERE request_id=:id"),
                       {"id": int(request_id)})
        return
    _s3().delete_object(Bucket=_bucket(), Key=_req_key(request_id))


def resolve_run_id(queue_name: str):
    """Latest run_id whose run_label equals this queue_name — for deep-linking a completed
    request to its results. Returns int or None (run not present yet)."""
    if not queue_name:
        return None
    if _backend() == "r2":
        df = _duck_df(f"SELECT run_id FROM read_parquet('{_uri('Scenario_Runs')}') "
                      "WHERE run_label = ? ORDER BY run_id DESC LIMIT 1", [queue_name])
    else:
        df = _sql_df("SELECT TOP 1 run_id FROM dbo.Scenario_Runs WHERE run_label = :q "
                     "ORDER BY run_id DESC", {"q": queue_name})
    return int(df["run_id"].iloc[0]) if not df.empty else None


def request_for_run_label(run_label: str):
    """The completed request (if any) that produced a run with this label — lets Run Detail
    show who requested it. Returns {scenario_name, requested_by} or None."""
    if not run_label:
        return None
    if _backend() == "sql":
        df = _sql_df("SELECT TOP 1 scenario_name, requested_by FROM dbo.Scenario_Requests "
                     "WHERE result_queue_name = :q AND status = 'Complete' "
                     "ORDER BY requested_at DESC", {"q": run_label})
        return None if df.empty else df.iloc[0].to_dict()
    reqs = load_requests()
    if reqs.empty:
        return None
    hit = reqs[(reqs["result_queue_name"] == run_label) & (reqs["status"] == "Complete")]
    if hit.empty:
        return None
    r = hit.iloc[0]
    return {"scenario_name": r["scenario_name"], "requested_by": r["requested_by"]}


# ─────────────────────────────────────────────────────────────────────────
# UI helpers (backend-independent).
# ─────────────────────────────────────────────────────────────────────────
def admin_unlocked(label: str = "Operator passcode (to complete / delete)") -> bool:
    """Sidebar passcode gate for destructive actions. Reads [admin] code from secrets;
    falls back to a local default so it works in dev. Set a real code in secrets for prod."""
    expected = (_secrets_section("admin") or {}).get("code", "operator")
    if st.session_state.get("_admin_ok"):
        return True
    code = st.sidebar.text_input(label, type="password", key="_admin_code")
    if code and code == str(expected):
        st.session_state["_admin_ok"] = True
    return bool(st.session_state.get("_admin_ok"))


def render_footer() -> None:
    """Shared StrategyXL footer link — call at the bottom of every page so the
    branding reads as consistent attribution, not a per-page ad. Understated:
    a divider + a muted caption with the link inline."""
    st.divider()
    st.caption(
        "Interested in backtesting stocks directly in Excel? "
        "→ [StrategyXL.com](https://strategyxl.com)"
    )


def check_password_gate() -> bool:
    """Optional shared-password gate. Returns True if access granted (or no gate configured).

    The login is remembered with a browser cookie so it persists across new tabs and
    reloads — drill-in links open new tabs, each a fresh Streamlit session, which would
    otherwise re-prompt. Cookie is READ synchronously via st.context.cookies (no prompt
    flash) and SET via a cookie component on success. Stores a SHA-256 of the password,
    not the password itself. Falls back to session-only (re-prompt per tab) if cookies
    are unavailable, so it never locks out or fails open.
    """
    auth = _secrets_section("auth")
    if not auth or "password" not in auth:
        return True   # no gate configured → open access

    expected = auth["password"]
    token = hashlib.sha256(("strategyxl-share::" + str(expected)).encode()).hexdigest()

    def _cookie_manager():
        try:
            import extra_streamlit_components as stx
            return stx.CookieManager(key="sxl_cookies")
        except Exception:
            return None

    # Already authed this session. If a cookie write is pending (set right after a
    # successful login), do it HERE on a clean run — there's no st.rerun() after, so
    # the component actually commits the write (a set()+rerun in the same run races
    # and the write gets discarded).
    if st.session_state.get("_auth_ok"):
        if st.session_state.pop("_set_cookie", False):
            cm = _cookie_manager()
            if cm is not None:
                try:
                    cm.set(_AUTH_COOKIE, token,
                           expires_at=datetime.datetime.now() + datetime.timedelta(days=7))
                except Exception:
                    pass
        return True

    # Remember-me cookie read. Reads are async (empty on the first render until the
    # component round-trips), so wait one rerun before prompting — an already-logged-in
    # visitor then never sees a password flash.
    cm = _cookie_manager()
    if cm is not None:
        cookies = cm.get_all() or {}
        if cookies.get(_AUTH_COOKIE) == token:
            st.session_state["_auth_ok"] = True
            return True
        if not cookies and not st.session_state.get("_cookie_checked"):
            st.session_state["_cookie_checked"] = True
            st.stop()

    pw = st.text_input("Password", type="password")
    if pw == "":
        st.stop()
    if pw == expected:
        st.session_state["_auth_ok"] = True
        st.session_state["_set_cookie"] = True   # written on the next clean run
        st.rerun()
    else:
        st.error("Incorrect password.")
        st.stop()
    return False
