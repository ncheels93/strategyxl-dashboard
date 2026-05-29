"""StrategyXL — SPX 7 DTE Put Credit Spread backtest dashboard.

Overview page: best-in-class callouts, sortable leaderboard, scatter chart,
sidebar filters. Click a run's number in the leaderboard to drill in.
"""

import streamlit as st
import plotly.express as px

from data.db import load_scenario_runs, check_password_gate

# ─────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StrategyXL — SPX 7 DTE Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

check_password_gate()

OFF_LABEL = "(filter off)"

# ─────────────────────────────────────────────────────────────────────────
# Title bar
# ─────────────────────────────────────────────────────────────────────────
st.title("SPX 7 DTE Put Credit Spread — Backtest Dashboard")
st.caption(
    "Strategy: enter Friday, 10-delta short, \\$50/\\$100/\\$200 widths, hold to expiration "
    "with 1DTE / breach exits. All P&L figures are NET of commission and slippage."
)

# ─────────────────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────────────────
df = load_scenario_runs()

if df.empty:
    st.warning("No scenarios in the database yet.")
    st.stop()

df = df.copy()
# Trend-filter-off runs store in_trend_filter_ma = NULL. Surface them as a real,
# selectable category so they are not silently dropped by the MA filter.
df["trend_ma_display"] = df["in_trend_filter_ma"].fillna(OFF_LABEL)

# ─────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ─────────────────────────────────────────────────────────────────────────
st.sidebar.header("Filters")

ma_options = sorted(df["trend_ma_display"].unique().tolist())
selected_mas = st.sidebar.multiselect("Trend filter MA", ma_options, default=ma_options)

width_options = sorted(df["in_spread_width"].dropna().unique().tolist())
selected_widths = st.sidebar.multiselect("Spread width", width_options, default=width_options)

withdrawals_filter = st.sidebar.radio(
    "Withdrawals",
    options=["Any", "On only", "Off only"],
    index=0,
    horizontal=True,
)

filtered = df.copy()
if selected_mas:
    filtered = filtered[filtered["trend_ma_display"].isin(selected_mas)]
if selected_widths:
    filtered = filtered[filtered["in_spread_width"].isin(selected_widths)]
if withdrawals_filter == "On only":
    filtered = filtered[filtered["in_withdrawals_on"] == True]
elif withdrawals_filter == "Off only":
    filtered = filtered[filtered["in_withdrawals_on"] == False]

st.sidebar.caption(f"{len(filtered)} of {len(df)} runs shown")

# ─────────────────────────────────────────────────────────────────────────
# Best-in-class callouts (NaN-safe)
# ─────────────────────────────────────────────────────────────────────────
def _best(col, want_max=True):
    s = filtered[col].dropna()
    if s.empty:
        return None
    return filtered.loc[s.idxmax() if want_max else s.idxmin()]

def _card(container, title, row, value_fn):
    with container:
        if row is None:
            st.metric(title, "—")
        else:
            rid = int(row["run_id"])
            st.metric(title, value_fn(row), help=str(row["run_label"] or ""))
            st.markdown(f"[Run #{rid} →](Run_Detail?run_id={rid})")

if not filtered.empty:
    a1, a2, a3 = st.columns(3)
    _card(a1, "Best CAGR",          _best("kpi_cagr"),          lambda r: f"{r['kpi_cagr']:.2%}")
    _card(a2, "Best Calmar",        _best("kpi_calmar"),        lambda r: f"{r['kpi_calmar']:.2f}")
    _card(a3, "Lowest Max DD",      _best("kpi_max_dd_pct"),    lambda r: f"{r['kpi_max_dd_pct']:.2%}")

    b1, b2, b3 = st.columns(3)
    _card(b1, "Best Sharpe",        _best("kpi_sharpe"),        lambda r: f"{r['kpi_sharpe']:.2f}")
    _card(b2, "Best Sortino",       _best("kpi_sortino"),       lambda r: f"{r['kpi_sortino']:.2f}")
    _card(b3, "Best Profit Factor", _best("kpi_profit_factor"), lambda r: f"{r['kpi_profit_factor']:.2f}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Scatter: CAGR vs Max Drawdown, colored by trend MA (filter-off is its own series).
# Click a dot to drill in (via on_select — Plotly dots can't be direct hyperlinks).
# ─────────────────────────────────────────────────────────────────────────
st.subheader("CAGR vs Max Drawdown")
chart_df = filtered.copy()
# Size by Calmar, but clip ≥ 0 so a (hypothetical) negative Calmar can't break Plotly sizing.
chart_df["_size"] = chart_df["kpi_calmar"].clip(lower=0.01).fillna(0.01)
fig = px.scatter(
    chart_df,
    x="kpi_max_dd_pct",
    y="kpi_cagr",
    color="trend_ma_display",
    size="_size",
    custom_data=["run_id", "run_label", "kpi_sharpe", "kpi_sortino",
                 "kpi_calmar", "kpi_total_trades", "in_spread_width"],
    labels={"kpi_max_dd_pct": "Max Drawdown", "kpi_cagr": "CAGR", "trend_ma_display": "Trend MA"},
)
fig.update_traces(hovertemplate=(
    "<b>Run #%{customdata[0]}</b> · %{customdata[1]}<br>"
    "CAGR %{y:.2%} · Max DD %{x:.2%}<br>"
    "Sharpe %{customdata[2]:.2f} · Sortino %{customdata[3]:.2f} · Calmar %{customdata[4]:.2f}<br>"
    "Width $%{customdata[6]:.0f} · Trades %{customdata[5]}<extra></extra>"
))
fig.update_xaxes(tickformat=".0%")
fig.update_yaxes(tickformat=".0%")
fig.update_layout(height=500)

event = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                        selection_mode=["points", "box", "lasso"], key="scatter_select")

_sel_pts = []
try:
    _sel_pts = event["selection"]["points"]
except (TypeError, KeyError):
    _sel_pts = []
_sel_rids = []
for _p in _sel_pts:
    _cd = _p.get("customdata")
    if _cd:
        _sel_rids.append(int(_cd[0]))
_sel_rids = list(dict.fromkeys(_sel_rids))  # dedupe, preserve order

if _sel_rids:
    _links = "  ·  ".join(f"[Run #{r} →](Run_Detail?run_id={r})" for r in _sel_rids)
    st.markdown(f"**Selected:** {_links}")
    if len(_sel_rids) >= 2:
        st.markdown(f"↳ [Compare these {len(_sel_rids)} runs →](Compare?runs={','.join(map(str, _sel_rids))})")
else:
    st.caption("Tip: click a dot for its detail link. Shift-click more dots — or use the box/lasso "
               "tools in the chart's top-right toolbar — to select several and compare.")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Leaderboard
# ─────────────────────────────────────────────────────────────────────────
st.subheader("Leaderboard")

sort_options = {
    "CAGR (desc)":          ("kpi_cagr",             False),
    "Sharpe (desc)":        ("kpi_sharpe",           False),
    "Sortino (desc)":       ("kpi_sortino",          False),
    "Calmar (desc)":        ("kpi_calmar",           False),
    "Profit Factor (desc)": ("kpi_profit_factor",    False),
    "Max DD (least bad)":   ("kpi_max_dd_pct",       False),
    "Ann Volatility (asc)": ("kpi_ann_return_stdev", True),
    "Ending Equity (desc)": ("kpi_ending_equity",    False),
    "Total Trades (desc)":  ("kpi_total_trades",     False),
    "Win Rate (desc)":      ("kpi_win_rate",         False),
}
sort_label = st.selectbox("Sort by", list(sort_options.keys()))
sort_col, sort_asc = sort_options[sort_label]
sorted_df = filtered.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

# Clickable drill-in: the Run # cell is a link to the Run Detail page.
sorted_df["drill_url"] = "Run_Detail?run_id=" + sorted_df["run_id"].astype(str)

display_cols = [
    "drill_url", "run_label", "trend_ma_display", "in_spread_width",
    "kpi_ending_equity", "kpi_cagr", "kpi_max_dd_pct", "kpi_calmar",
    "kpi_ann_return_stdev", "kpi_sharpe", "kpi_sortino",
    "kpi_total_trades", "kpi_win_rate", "kpi_profit_factor",
]
view = sorted_df[display_cols].copy()
view.columns = [
    "Run #", "Label", "Trend MA", "Width",
    "Ending Equity", "CAGR", "Max DD", "Calmar",
    "Ann Vol", "Sharpe", "Sortino",
    "Trades", "Win Rate", "PF",
]
# Pre-multiply ratio columns by 100 so the % format renders as "14.32%" not "0.14%".
for pct_col in ("CAGR", "Max DD", "Win Rate", "Ann Vol"):
    view[pct_col] = view[pct_col] * 100.0

st.dataframe(
    view,
    use_container_width=True,
    hide_index=True,
    height=500,
    column_config={
        "Run #":         st.column_config.LinkColumn("Run #", display_text=r"run_id=(\d+)", width="small"),
        "Ending Equity": st.column_config.NumberColumn(format="$%.0f"),
        "CAGR":          st.column_config.NumberColumn(format="%.2f%%"),
        "Max DD":        st.column_config.NumberColumn(format="%.2f%%"),
        "Calmar":        st.column_config.NumberColumn(format="%.2f"),
        "Ann Vol":       st.column_config.NumberColumn(format="%.2f%%"),
        "Sharpe":        st.column_config.NumberColumn(format="%.2f"),
        "Sortino":       st.column_config.NumberColumn(format="%.2f"),
        "Win Rate":      st.column_config.NumberColumn(format="%.2f%%"),
        "PF":            st.column_config.NumberColumn(format="%.2f"),
    },
)

st.caption("Click a run's number in the **Run #** column to open its full equity curve + trade log.")

# ─────────────────────────────────────────────────────────────────────────
# About / methodology
# ─────────────────────────────────────────────────────────────────────────
with st.expander("About this dashboard & metric definitions"):
    st.markdown(
        """
**Strategy.** SPX weekly put credit spreads: enter each Friday (or Thursday before a holiday),
sell the ~10-delta put, buy the put $50 lower (default), hold to expiration with optional
breach and 1-DTE close rules. Position sizing is a dynamic cap that reinvests a share of
profits, with a gated 25%-of-equity gross-exposure ceiling above $200k.

**Engine.** Every scenario is computed by a SQL Server engine cross-validated penny-for-penny
against an Excel model. All P&L is NET of commission and slippage.

**Risk-adjusted metrics** use **monthly** returns, annualized:
- **Annualized Volatility** — standard deviation of monthly returns × √12.
- **Sharpe** — mean monthly *excess* return (over the FRED 3-month risk-free rate) ÷ its standard deviation, × √12.
- **Sortino** — mean monthly return ÷ downside deviation (minimum acceptable return = 0), × √12.

**Trend filter.** Runs labeled **(filter off)** take every weekly entry; runs with a moving
average (e.g. `ema_9`, `sma_200`) only enter when SPX closes above that MA — so filter-off runs
have the most trades.
        """
    )
