"""Database connection + cached queries.

Connection mode is auto-detected:
- If `st.secrets["database"]` exists (Streamlit Cloud / explicit cloud secrets),
  use SQL auth against the configured server.
- Else fall back to Windows-authenticated connection to StockDevVM (local dev).
"""

from __future__ import annotations

import datetime
import hashlib
from urllib.parse import quote_plus

import streamlit as st
from sqlalchemy import create_engine, text
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


@st.cache_data(ttl=300, show_spinner="Loading scenarios…")
def load_scenario_runs() -> pd.DataFrame:
    """All scenarios for the leaderboard. Cached 5 minutes."""
    sql = """
        SELECT *
          FROM dbo.Scenario_Runs
         ORDER BY run_id DESC
    """
    with get_engine().connect() as cn:
        return pd.read_sql(text(sql), cn)


@st.cache_data(ttl=1800, show_spinner="Loading trade log…")
def load_trade_log(run_id: int) -> pd.DataFrame:
    """Per-day trade log for one run. Cached 30 minutes."""
    sql = """
        SELECT *
          FROM dbo.Scenario_TradeLog
         WHERE run_id = :run_id
         ORDER BY day_num
    """
    with get_engine().connect() as cn:
        return pd.read_sql(text(sql), cn, params={"run_id": int(run_id)})


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
