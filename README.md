# StrategyXL — SPX 7 DTE Backtest Dashboard

Streamlit app that surfaces the SQL Server backtest engine results (`dbo.Scenario_Runs` + `dbo.Scenario_TradeLog`) as a sharable read-only dashboard. Two pages:

- **Overview** — best-in-class callouts, sortable leaderboard, scatter chart, sidebar filters
- **Run Detail** — KPI cards, equity curve, drawdown, annual returns, full trade log

---

## 1. Local development (against your VM SQL Server)

### Prerequisites
- Python 3.11 or 3.12 — [download](https://www.python.org/downloads/)
- ODBC Driver 18 for SQL Server — [download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- Your VM SQL Server (`StockDevVM`) reachable from this machine with Windows auth

### Setup
```powershell
cd C:\VM_Files\Claude_SPX_Credit_Spreads\strategyxl_share

# Create a virtual environment so you don't pollute system Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### Run locally
```powershell
streamlit run Summary.py
```

The app opens at http://localhost:8501. Edits to .py files hot-reload automatically.

Without `secrets.toml`, `db.py` falls back to a Windows-auth connection to `StockDevVM` — convenient for dev.

---

## 2. Deploy to Streamlit Community Cloud (free, public)

### One-time setup
1. **Push the `strategyxl_share/` folder to a public GitHub repo.** Files committed: everything except `.streamlit/secrets.toml` (use the `.example` template).
2. **Provision Azure SQL Database** (Basic tier ≈ $5/mo):
   - Azure Portal → Create resource → SQL Database
   - Server: new or existing logical SQL server, in a region near Joe's group (East US 2 if mixed US)
   - Compute + storage: **Basic** (5 DTU, 2 GB) — $4.99/mo
   - Allow Azure services + your IP through the firewall
   - **Username** + **password** — write down for the secrets file
3. **Migrate data from your VM to Azure SQL.** Three options, pick one:
   - **Option A — SSMS deploy** (one-time): SSMS → right-click `ORATS_Options` database → Tasks → Deploy Database to Microsoft Azure SQL Database → walk the wizard.
   - **Option B — SqlPackage CLI** (scriptable for ongoing sync): export `.bacpac` from local, import to Azure. See `_azure_sync_script.ps1` (TODO — not yet built).
   - **Option C — Selective: only push Scenario_Runs + Scenario_TradeLog** (lighter, see "Selective sync" below).
4. **Sign in to [share.streamlit.io](https://share.streamlit.io)** with your GitHub account.
5. **New app** → repo + branch + **main file `Summary.py`** → Deploy.
6. **Settings → Secrets** in the Streamlit Cloud UI, paste:
   ```toml
   [database]
   server = "your-server.database.windows.net"
   database = "StrategyXL_Share"
   username = "your-sql-user"
   password = "your-sql-password"

   # Optional shared-password gate. Leave commented out for fully public access.
   # [auth]
   # password = "your-shared-password"
   ```
   > The cloud path connects via **pymssql** (FreeTDS), not ODBC — so no `driver`
   > key is needed. This avoids the missing-ODBC-driver failure on Streamlit
   > Community Cloud's Debian image. Local dev still uses pyodbc + Windows auth.
7. Streamlit Cloud auto-rebuilds. Your app is live at `https://<your-app>.streamlit.app`.

### Selective sync (Option C — recommended for low cost)

The full `ORATS_Options` DB is huge (24M-row options table + others). The dashboard only needs `Scenario_Runs` + `Scenario_TradeLog`. Export just those two to a fresh `StrategyXL_Share` database on Azure SQL.

Quick approach:
```sql
-- On Azure SQL: create empty database StrategyXL_Share via portal first, then run the
-- CREATE TABLE statements from your local `_sql_01_create_scenario_tables.sql` against it.
-- Then INSERT data via SqlPackage, BCP, or a Python script (TODO).
```

A nightly sync script is the right next-step here. Easy to add later — for now, manual sync via Azure Data Studio's "Schema Compare" or "Generate Scripts" works fine for a few hundred scenarios.

---

## 3. Project structure

```
strategyxl_share/
├── Summary.py                   # Landing page = Summary/Overview (entry script)
├── pages/
│   ├── 1_Run_Detail.py          # Drill-in page (URL param ?run_id=N supported)
│   └── 2_Compare.py             # Side-by-side compare 2–4 runs (?runs=1,5,12 supported)
├── data/
│   ├── __init__.py
│   └── db.py                    # SQLAlchemy engine + cached query helpers
├── .streamlit/
│   ├── config.toml              # Dark theme + sage primary
│   └── secrets.toml.example     # Template (real secrets via Streamlit Cloud UI)
├── requirements.txt
└── README.md
```

Streamlit auto-discovers pages in `pages/`. The numeric prefix (`1_`) controls sidebar order.

---

## 4. Cost ladder

| Setup | $/mo | Notes |
|---|---|---|
| Streamlit Cloud (public) + Azure SQL Basic | **$5** | Fully public app, ≤10 simultaneous users, 2 GB DB |
| Streamlit Cloud (Hobby/private) + Azure SQL Basic | $20 | Adds login gate |
| Streamlit Cloud (public) + Azure SQL S0 | $15 | Faster queries, 250 GB DB |
| Streamlit Cloud (public) + Azure SQL Serverless | $0 idle, ~$0.50/active-hour | Best for bursty traffic |

Egress, monitoring, backups: negligible at this scale.

---

## 5. Adding pages

Drop a new file in `pages/`, prefix with a number to control sidebar order:
```
pages/
├── 1_Run_Detail.py
├── 2_Comparison.py       # TODO: side-by-side compare 2-3 runs
└── 3_About.py            # TODO: methodology + glossary
```

---

## 6. Cache management

- `@st.cache_resource` on the engine: held for the session (no reconnect per click).
- `@st.cache_data(ttl=300)` on `load_scenario_runs`: leaderboard refreshes every 5 min.
- `@st.cache_data(ttl=1800)` on `load_trade_log`: per-run trade log cached 30 min.

Click "Clear cache" in the menu (top-right hamburger → Clear cache) to force a fresh fetch.
