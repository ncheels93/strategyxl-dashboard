"""Database connection + cached queries.

Connection mode is auto-detected:
- If `st.secrets["database"]` exists (Streamlit Cloud / explicit cloud secrets),
  use SQL auth against the configured server.
- Else fall back to Windows-authenticated connection to StockDevVM (local dev).
"""

from __future__ import annotations

from urllib.parse import quote_plus

import streamlit as st
from sqlalchemy import create_engine, text
import pandas as pd


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
    else:
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
    """Optional shared-password gate. Returns True if access granted (or no gate configured)."""
    auth = _secrets_section("auth")
    if not auth or "password" not in auth:
        return True   # no gate configured → open access
    if st.session_state.get("_auth_ok"):
        return True
    pw = st.text_input("Password", type="password")
    if pw == "":
        st.stop()
    if pw == auth["password"]:
        st.session_state["_auth_ok"] = True
        st.rerun()
    else:
        st.error("Wrong password.")
        st.stop()
    return False
