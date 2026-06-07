"""Database connection + cached queries.

Connection mode is auto-detected:
- If `st.secrets["database"]` exists (Streamlit Cloud / explicit cloud secrets),
  use SQL auth against the configured server.
- Else fall back to Windows-authenticated connection to StockDevVM (local dev).
"""

from __future__ import annotations

import datetime
import hashlib
import time
from urllib.parse import quote_plus

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, DBAPIError
import pandas as pd

_AUTH_COOKIE = "sxl_auth"


def _secrets_section(name: str) -> dict | None:
    """Return a secrets section as a dict, or None if no secrets.toml is configured.
    Streamlit raises StreamlitSecretNotFoundError on bare `st.secrets` access when no
    file exists, so we need a try/except — not a simple `in` check."""
    try:
        if name in st.secrets:
            return dict(st.secrets[name])
    except Exception:
        pass
    return None


@st.cache_resource(show_spinner=False)
def get_engine():
    """Build a SQLAlchemy engine. Cached across reruns of the Streamlit session."""
    cs = _secrets_section("database")
    if cs:
        # Azure SQL via pymssql (FreeTDS). Chosen over pyodbc because Streamlit
        # Community Cloud's Debian image ships no Microsoft ODBC driver and
        # installing one via packages.txt is unreliable; pymssql is pure-pip and
        # bundles FreeTDS, which negotiates TLS with Azure automatically.
        user = quote_plus(cs["username"])
        pwd = quote_plus(cs["password"])
        conn_str = f"mssql+pymssql://{user}:{pwd}@{cs['server']}:1433/{cs['database']}"
        # login_timeout 90s rides through the serverless DB's cold-start resume
        # (~30–60s after auto-pause) instead of erroring; pool_pre_ping discards a
        # stale pooled connection so the next request reconnects cleanly.
        return create_engine(conn_str, pool_pre_ping=True,
                             connect_args={"login_timeout": 90, "timeout": 90})

    # Local dev: Windows-auth to StockDevVM via the installed ODBC driver.
    # ODBC Driver 18 defaults Encrypt=Mandatory; trust the local cert so the
    # connection isn't rejected (same reason sqlcmd needs -C against StockDevVM).
    conn_str = (
        "mssql+pyodbc://@StockDevVM/ORATS_Options"
        "?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes"
        "&Encrypt=yes&TrustServerCertificate=yes"
    )
    return create_engine(conn_str, pool_pre_ping=True)


# Azure serverless DBs auto-pause after ~1h idle. The first connection while the
# DB is resuming is REJECTED almost instantly with error 40613 ("…is not currently
# available. Please retry…"), so a big login_timeout doesn't help on its own — the
# server answers fast with an error rather than hanging. We catch that signature,
# show a friendly notice, and retry until the resume finishes (~30–60s).
_COLD_START_SIGNS = ("not currently available", "40613", "adaptive server connection failed")


def _is_cold_start(err: Exception) -> bool:
    s = str(err).lower()
    return any(sig in s for sig in _COLD_START_SIGNS)


def _read_sql(sql: str, params: dict | None = None, *,
              max_wait: int = 90, interval: int = 3) -> pd.DataFrame:
    """Run a query, transparently riding through an Azure serverless cold-start."""
    eng = get_engine()
    deadline = time.monotonic() + max_wait
    spacer = notice = None
    while True:
        try:
            with eng.connect() as cn:
                df = pd.read_sql(text(sql), cn, params=params or {})
            for ph in (notice, spacer):
                if ph is not None:
                    ph.empty()
            return df
        except (OperationalError, DBAPIError) as e:
            if not _is_cold_start(e) or time.monotonic() >= deadline:
                raise
            if notice is None:
                # The cache spinner ("Loading scenarios…") renders at this same spot;
                # add a little vertical space so the notice sits clear of it rather
                # than overlapping. Both placeholders are cleared once data arrives.
                spacer = st.empty()
                spacer.markdown("<br><br>", unsafe_allow_html=True)
                notice = st.empty()
            notice.info("⏳ Waking the database — this can take up to a minute after a "
                        "period of inactivity. Hang tight, the page will load itself…")
            time.sleep(interval)


@st.cache_data(ttl=300, show_spinner="Loading scenarios…")
def load_scenario_runs() -> pd.DataFrame:
    """All scenarios for the leaderboard. Cached 5 minutes."""
    return _read_sql("SELECT * FROM dbo.Scenario_Runs ORDER BY run_id DESC")


@st.cache_data(ttl=1800, show_spinner="Loading trade log…")
def load_trade_log(run_id: int) -> pd.DataFrame:
    """Per-day trade log for one run. Cached 30 minutes."""
    return _read_sql(
        "SELECT * FROM dbo.Scenario_TradeLog WHERE run_id = :run_id ORDER BY day_num",
        {"run_id": int(run_id)},
    )


@st.cache_data(ttl=3600, show_spinner="Loading SPX daily MAs…")
def load_spx_daily() -> pd.DataFrame:
    """SPX daily close + all moving averages (2007+ on the share DB). Cached 1 hour.
    Used to show each trade's entry context (% above the 200-day SMA, etc.)."""
    return _read_sql(
        "SELECT trade_date, spx_close, sma_5, sma_10, sma_20, sma_50, sma_100, "
        "sma_150, sma_200, ema_9, ema_20, ema_50, ema_200 "
        "FROM dbo.SPX_Daily_MAs ORDER BY trade_date"
    )


# ─────────────────────────────────────────────────────────────────────────
# Scenario Requests — submit / list / complete / delete.
# Needs WRITE access to dbo.Scenario_Requests (local Windows-auth has it; for the
# cloud app, grant INSERT/UPDATE/DELETE on that one table to the dashboard's SQL user).
# ─────────────────────────────────────────────────────────────────────────
REQUEST_INPUT_COLS = [
    "in_spread_width", "in_trend_filter_on", "in_trend_filter_ma",
    "in_weekly_risk_pct", "in_max_weekly_risk", "in_withdrawals_on",
    "in_target_monthly_withdrawal", "in_withdrawal_floor", "in_starting_capital",
    "in_short_delta_threshold", "in_commission_per_contract", "in_slippage_per_leg",
    "in_otm_close_threshold", "in_breach_close", "in_profit_target", "in_stop_loss",
    "in_backtest_start", "in_backtest_end", "in_inflation_adjust_pct",
]


def insert_request(scenario_name: str, requested_by: str, inputs: dict) -> None:
    cols = ["scenario_name", "requested_by"] + REQUEST_INPUT_COLS
    params = {"scenario_name": scenario_name, "requested_by": (requested_by or None)}
    params.update({c: inputs.get(c) for c in REQUEST_INPUT_COLS})
    sql = (f"INSERT INTO dbo.Scenario_Requests ({', '.join(cols)}) "
           f"VALUES ({', '.join(':' + c for c in cols)})")
    with get_engine().begin() as cn:
        cn.execute(text(sql), params)


def load_requests() -> pd.DataFrame:
    """All requests, newest first. Not cached — it changes on submit/complete/delete."""
    return _read_sql("SELECT * FROM dbo.Scenario_Requests ORDER BY requested_at DESC")


def complete_request(request_id: int, queue_name: str, notes: str | None = None) -> None:
    with get_engine().begin() as cn:
        cn.execute(text("UPDATE dbo.Scenario_Requests SET status='Complete', "
                        "result_queue_name=:q, notes=:n WHERE request_id=:id"),
                   {"q": queue_name, "n": (notes or None), "id": int(request_id)})


def reopen_request(request_id: int) -> None:
    with get_engine().begin() as cn:
        cn.execute(text("UPDATE dbo.Scenario_Requests SET status='Pending', "
                        "result_queue_name=NULL WHERE request_id=:id"), {"id": int(request_id)})


def delete_request(request_id: int) -> None:
    with get_engine().begin() as cn:
        cn.execute(text("DELETE FROM dbo.Scenario_Requests WHERE request_id=:id"),
                   {"id": int(request_id)})


def resolve_run_id(queue_name: str):
    """Latest run_id whose run_label equals this queue_name — for deep-linking a completed
    request to its results. Returns int or None (run not present yet)."""
    if not queue_name:
        return None
    df = _read_sql("SELECT TOP 1 run_id FROM dbo.Scenario_Runs WHERE run_label = :q "
                   "ORDER BY run_id DESC", {"q": queue_name})
    return int(df["run_id"].iloc[0]) if not df.empty else None


def request_for_run_label(run_label: str):
    """The completed request (if any) that produced a run with this label — lets Run Detail
    show who requested it. Returns a dict {scenario_name, requested_by} or None."""
    if not run_label:
        return None
    df = _read_sql("SELECT TOP 1 scenario_name, requested_by FROM dbo.Scenario_Requests "
                   "WHERE result_queue_name = :q AND status = 'Complete' "
                   "ORDER BY requested_at DESC", {"q": run_label})
    return None if df.empty else df.iloc[0].to_dict()


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
