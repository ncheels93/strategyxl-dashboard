"""Compare — side-by-side comparison of 2–4 runs.

Pick runs from the multiselect (searchable; supports ?runs=1,5,12 deep-link),
then see a KPI table with the best value in each row highlighted, a criteria
diff (only inputs that differ), and overlaid cumulative-return + drawdown curves.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.db import load_scenario_runs, load_trade_log, check_password_gate

st.set_page_config(page_title="Compare — StrategyXL", page_icon="⚖️", layout="wide")
check_password_gate()

st.title("Compare Runs")

runs = load_scenario_runs()
if runs.empty:
    st.warning("No scenarios in the database.")
    st.stop()

runs = runs.copy()
runs["display"] = runs["run_id"].astype(str) + "  —  " + runs["run_label"].fillna("(no label)").astype(str)
disp_to_id = dict(zip(runs["display"], runs["run_id"]))

# Optional deep-link: ?runs=1,5,12
seed = []
qp = st.query_params.get("runs")
if qp:
    seed_ids = [int(x) for x in qp.split(",") if x.strip().isdigit()]
    seed = runs.loc[runs["run_id"].isin(seed_ids), "display"].tolist()

sel = st.multiselect("Select 2–4 runs to compare", options=runs["display"].tolist(),
                     default=seed, max_selections=4)
sel_ids = [int(disp_to_id[s]) for s in sel]

if len(sel_ids) < 2:
    st.info("Pick at least 2 runs (up to 4) to compare.")
    st.stop()

sub = runs[runs["run_id"].isin(sel_ids)].set_index("run_id")
col_labels = [f"Run #{rid}" for rid in sel_ids]

links = "  ·  ".join(f"[Run #{rid} →](Run_Detail?run_id={rid})" for rid in sel_ids)
st.markdown("**Comparing:** " + links)

# ─────────────────────────────────────────────────────────────────────────
# KPI comparison table — best value in each row highlighted
# ─────────────────────────────────────────────────────────────────────────
st.subheader("KPIs")
KPI_SPECS = [
    ("Ending Equity",    "kpi_ending_equity",    lambda v: f"${v:,.0f}",     "max"),
    ("Total Return",     "kpi_total_return_pct", lambda v: f"{v*100:,.2f}%", "max"),
    ("CAGR",             "kpi_cagr",             lambda v: f"{v*100:,.2f}%", "max"),
    ("Max Drawdown",     "kpi_max_dd_pct",       lambda v: f"{v*100:,.2f}%", "max"),  # least negative = best
    ("Calmar",           "kpi_calmar",           lambda v: f"{v:.2f}",       "max"),
    ("Ann Volatility",   "kpi_ann_return_stdev", lambda v: f"{v*100:,.2f}%", "min"),
    ("Sharpe",           "kpi_sharpe",           lambda v: f"{v:.2f}",       "max"),
    ("Sortino",          "kpi_sortino",          lambda v: f"{v:.2f}",       "max"),
    ("Win Rate",         "kpi_win_rate",         lambda v: f"{v*100:,.2f}%", "max"),
    ("Profit Factor",    "kpi_profit_factor",    lambda v: f"{v:.2f}",       "max"),
    ("Net Realized P&L", "kpi_realized_pnl",     lambda v: f"${v:,.0f}",     "max"),
    ("Total Trades",     "kpi_total_trades",     lambda v: f"{int(v):,}",    "none"),
]
labels = [s[0] for s in KPI_SPECS]
disp = pd.DataFrame(index=labels, columns=col_labels, dtype=object)
raw = pd.DataFrame(index=labels, columns=col_labels, dtype=float)
for (lab, col, fmt, _dir) in KPI_SPECS:
    for rid, clab in zip(sel_ids, col_labels):
        v = sub.loc[rid, col]
        raw.loc[lab, clab] = float(v) if pd.notna(v) else float("nan")
        disp.loc[lab, clab] = "—" if pd.isna(v) else fmt(v)

style_df = pd.DataFrame("", index=labels, columns=col_labels)
for (lab, col, fmt, direction) in KPI_SPECS:
    if direction == "none":
        continue
    rv = raw.loc[lab]
    if rv.notna().sum() < 2:
        continue
    best = rv.max() if direction == "max" else rv.min()
    for clab in col_labels:
        if pd.notna(rv[clab]) and rv[clab] == best:
            style_df.loc[lab, clab] = "background-color: rgba(61,139,55,0.30)"

st.dataframe(disp.style.apply(lambda _: style_df, axis=None), use_container_width=True)
st.caption("Green = best value in that row across the selected runs.")

# ─────────────────────────────────────────────────────────────────────────
# Criteria diff — only inputs that differ across the selected runs
# ─────────────────────────────────────────────────────────────────────────
st.subheader("Criteria differences")

def _b(v):    return "—" if pd.isna(v) else ("On" if bool(v) else "Off")
def _m0(v):   return "—" if pd.isna(v) else f"${v:,.0f}"
def _m2(v):   return "—" if pd.isna(v) else f"${v:,.2f}"
def _p(v):    return "—" if pd.isna(v) else f"{round(float(v) * 100, 4):g}%"
def _optp(v): return "Off" if pd.isna(v) else f"{round(float(v) * 100, 4):g}%"
def _d(v):    return "—" if pd.isna(v) else f"{float(v):.2f}"
def _t(v):    return "—" if (pd.isna(v) or str(v).strip() == "") else str(v)
def _dt(v):   return "—" if pd.isna(v) else str(v)

CRIT_SPECS = [
    ("Backtest Start", "in_backtest_start", _dt),
    ("Backtest End", "in_backtest_end", _dt),
    ("Short Delta Target", "in_short_delta_threshold", _d),
    ("Short Delta Min", "in_short_delta_min", _d),
    ("Short Delta Max", "in_short_delta_max", _d),
    ("Spread Width", "in_spread_width", _m0),
    ("Spread Handling", "in_spread_handling", _t),
    ("Product Mode", "in_product_mode", _t),
    ("Starting Capital", "in_starting_capital", _m0),
    ("Base Trading Cap", "in_base_trading_cap", _m0),
    ("Upside Reinvest", "in_upside_reinvest_pct", _p),
    ("Max Gross % Equity", "in_max_gross_pct_equity", _p),
    ("Gross-Cap Activation", "in_gross_cap_activation_eq", _m0),
    ("Target CAGR", "in_target_cagr", _p),
    ("Trend Filter", "in_trend_filter_on", _b),
    ("Moving Average", "in_trend_filter_ma", _t),
    ("Breach Close", "in_breach_close", _b),
    ("1-DTE / OTM Close", "in_otm_close_threshold", _p),
    ("Profit Target", "in_profit_target", _optp),
    ("Stop Loss", "in_stop_loss", _optp),
    ("Commission / Contract", "in_commission_per_contract", _m2),
    ("Slippage / Leg", "in_slippage_per_leg", _m2),
    ("Mid Source", "in_mid_source", _t),
    ("Entry Fill", "in_entry_fill", _t),
    ("Exit Fill", "in_exit_fill", _t),
    ("Withdrawals", "in_withdrawals_on", _b),
    ("Target Monthly", "in_target_monthly_withdrawal", _m0),
    ("Withdrawal Floor", "in_withdrawal_floor", _m0),
    ("Withdrawal Start", "in_withdrawal_start_date", _dt),
    ("Inflation Adjust", "in_inflation_adjust_pct", _p),
]
diff_rows = []
for (lab, col, fmt) in CRIT_SPECS:
    formatted = [fmt(sub.loc[rid, col]) for rid in sel_ids]
    if len(set(formatted)) > 1:
        diff_rows.append([lab] + formatted)

if diff_rows:
    diff_df = pd.DataFrame(diff_rows, columns=["Criteria"] + col_labels).set_index("Criteria")
    st.dataframe(diff_df, use_container_width=True)
else:
    st.success("These runs share identical criteria.")

# ─────────────────────────────────────────────────────────────────────────
# Overlaid curves
# ─────────────────────────────────────────────────────────────────────────
tlogs = {rid: load_trade_log(rid) for rid in sel_ids}

st.subheader("Cumulative Return")
fig_cr = go.Figure()
for rid, clab in zip(sel_ids, col_labels):
    tl = tlogs[rid]
    sc = float(sub.loc[rid, "in_starting_capital"])
    fig_cr.add_trace(go.Scatter(
        x=tl["trade_date"], y=tl["equity_eod"].astype(float) / sc - 1.0,
        mode="lines", name=clab))
fig_cr.update_yaxes(tickformat=".0%")
fig_cr.update_layout(height=400, margin=dict(l=10, r=10, t=20, b=10),
                     legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5))
st.plotly_chart(fig_cr, use_container_width=True)

st.subheader("Drawdown from Peak")
fig_dd = go.Figure()
for rid, clab in zip(sel_ids, col_labels):
    tl = tlogs[rid]
    fig_dd.add_trace(go.Scatter(
        x=tl["trade_date"], y=tl["drawdown_pct"].astype(float),
        mode="lines", name=clab))
fig_dd.update_yaxes(tickformat=".0%")
fig_dd.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10),
                     legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
st.plotly_chart(fig_dd, use_container_width=True)
