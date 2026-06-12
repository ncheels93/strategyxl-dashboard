# StrategyXL — SPX 7-DTE Put Credit Spread Backtest Dashboard

Streamlit app that surfaces a SQL Server backtest engine's results as a shareable, read-only
dashboard. It backtests a **weekly S&P 500 (SPX) ~10-delta put credit spread**, 2007–present,
across a grid of sizing, trend-filter, and withdrawal choices.

**Live:** https://strategyxl-dashboard.streamlit.app (Streamlit Community Cloud → Azure SQL `StrategyXL_Share`)

## Pages

- **Summary** — best-in-class cards (return/risk, risk-adjusted, win/loss), the CAGR-vs-drawdown
  scatter with the S&P ★, efficient frontier and constant-Calmar rays, a **Breakdowns** section
  (roll-ups by spread width, starting capital, max weekly risk, trend filter and withdrawals), and
  the full leaderboard. Sidebar filters — led by a performance screen (min CAGR / worst Max DD /
  min Calmar) — narrow everything on the page.
- **Run Detail** — one run in depth: full KPIs, risk-adjusted metrics, equity + drawdown charts,
  the equity decomposition (Starting + Net Realized + Interest), the win/loss profile, the ten
  biggest winners/losers with entry context, the withdrawal breakdown (if used), and the full
  day-by-day trade log.
- **Compare** — 2–4 runs side by side: a metric table (best value per row highlighted), the inputs
  that differ, overlaid return/drawdown curves, and a trade-by-trade table.
- **Guide** — the strategy + methodology, every metric defined as it's computed, and the Key
  Findings (every number derived from the live data).
- **Request a Run** — submit a scenario to backtest (spread width, trend filter, weekly risk %,
  cap, withdrawals, and the friction/exit knobs). It joins a queue the operator runs; once complete
  you click straight from the request to its results. Submitting is open to everyone; the operator
  passcode (`[admin]` secret) gates mark-complete / delete and the queue-CSV export.

## The sizing model (capped)

Each week the dollars at risk = **MIN(weekly_risk_pct × equity, max_weekly_risk)** — risk a set %
of the account (default 50%) but never more than a hard dollar ceiling. The **cap is the risk
dial**: tighter = smoother. `max_weekly_risk` NULL ⇒ uncapped (rides the full % the whole way).
Friendly tiers: Conservative ($20k) · Cautious ($30k) · Moderate ($50k) · Aggressive ($75k) ·
Maximum (uncapped).

---

## 1. Local development (against your VM SQL Server)

### Prerequisites
- Python 3.11–3.13
- ODBC Driver 18 for SQL Server
- `StockDevVM` reachable with Windows auth

### Setup & run
```powershell
cd C:\VM_Files\Claude_SPX_Credit_Spreads\strategyxl_share
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run Summary.py
```
Opens at http://localhost:8501; `.py` edits hot-reload. Without `secrets.toml`, `db.py` falls back
to a Windows-auth connection to `StockDevVM` — convenient for dev. Add a local `[admin]` code in
`secrets.toml` to test the Request page's operator actions.

---

## 2. Deploy to Streamlit Community Cloud + Azure SQL

The deploy tooling is built and lives in this folder:
- **`_azure_schema_deploy.sql`** — DDL for the Azure tables (`Scenario_Runs`, `Scenario_TradeLog`,
  `Scenario_Queue`, `SPX_Daily_MAs`, `Scenario_Requests`). Run it against the target DB first.
  Data tables are drop+recreate; `SPX_Daily_MAs` and `Scenario_Requests` are guarded creates so a
  re-run never wipes the daily series or submitted requests.
- **`_migrate_to_azure.py`** — cursor-to-cursor data copy from local `StockDevVM` → Azure
  (IDENTITY_INSERT on `Scenario_Runs` to keep `run_id` stable, a column-set guard that aborts on
  local≠Azure schema drift, and a row-count verify).

Steps:
1. Create Azure SQL DB **`StrategyXL_Share`** (serverless free-tier is fine). Add a firewall rule
   for Streamlit Cloud — allow-all (`0.0.0.0`–`255.255.255.255`), since Cloud has no fixed egress IP.
2. `sqlcmd -S <srv>.database.windows.net -d StrategyXL_Share -U <admin> -C -i _azure_schema_deploy.sql`
3. `python _migrate_to_azure.py --server <srv>.database.windows.net --user <admin>` (prompts for
   password; `--database` defaults to `StrategyXL_Share`; `--truncate` to reload). When the daily
   series gains new dates, reload it too: `--tables SPX_Daily_MAs --truncate`.
4. Push `strategyxl_share/` to a GitHub repo; Streamlit Cloud → **New app** → main file `Summary.py`.
5. Cloud → **Settings → Secrets**:
   ```toml
   [database]
   server   = "your-server.database.windows.net"
   database = "StrategyXL_Share"
   username = "your-sql-user"
   password = "your-sql-password"

   # Optional shared-password gate (leave out for fully public):
   # [auth]
   # password = "viewer-password"

   # Operator passcode for the Request-a-Run page's complete/delete/CSV actions:
   # [admin]
   # code = "operator-passcode"
   ```
   > Cloud connects via **pymssql** (FreeTDS), so **no `driver` key** — this avoids the missing-ODBC
   > failure on Streamlit Cloud's image. Local dev uses pyodbc + Windows auth (no `[database]`).

The **Request a Run** page WRITES to `Scenario_Requests`. If the app's `[database]` login is the
server admin it already has write; otherwise grant it
`SELECT, INSERT, UPDATE, DELETE ON dbo.Scenario_Requests`.

---

## 3. Project structure

```
strategyxl_share/
├── Summary.py                  # entry page (Summary / Overview)
├── pages/
│   ├── 1_Run_Detail.py
│   ├── 2_Compare.py
│   ├── 3_Guide.py
│   ├── 4_AI_Analysis.py        # chart-backed findings across the whole grid (live data)
│   └── 5_Request_Run.py        # submit/track backtest requests (writes Scenario_Requests)
├── data/
│   ├── db.py                   # SQLAlchemy engine, cached queries, request CRUD, admin gate
│   └── docs.py                 # shared TERMS/SECTIONS for the popovers + the Guide
├── .streamlit/
│   ├── config.toml             # dark theme
│   └── secrets.toml.example    # template (real secrets via the Cloud UI)
├── _azure_schema_deploy.sql    # Azure table DDL
├── _migrate_to_azure.py        # local → Azure data migration
├── requirements.txt
└── README.md
```
Streamlit auto-discovers `pages/`; the numeric prefix controls sidebar order.

---

## 4. Cache management

- `@st.cache_resource` on the engine — held for the session (no reconnect per click).
- `@st.cache_data(ttl=300)` on `load_scenario_runs` — leaderboard refreshes every 5 min.
- `@st.cache_data(ttl=1800)` on `load_trade_log` — per-run trade log cached 30 min.
- Request lists are **not** cached (they change on submit/complete/delete).

Force a fresh fetch via the top-right menu → **Clear cache**.
