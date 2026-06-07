"""Compare — side-by-side comparison of 2–4 runs.

Pick runs from the multiselect (searchable; supports ?runs=1,5,12 deep-link),
then see a KPI table with the best value in each row highlighted, a criteria
diff (only inputs that differ), and overlaid cumulative-return + drawdown curves.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data.db import load_scenario_runs, load_trade_log, check_password_gate, render_footer
from data.docs import explain, guide_link

st.set_page_config(page_title="Compare — StrategyXL", page_icon="⚖️", layout="wide")
check_password_gate()

st.title("Compare Runs")
guide_link()

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
explain("compare_kpis")
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
    ("Avg Win",          "kpi_avg_win",          lambda v: f"${v:,.0f}",     "max"),
    ("Avg Loss",         "kpi_avg_loss",         lambda v: f"${v:,.0f}",     "max"),   # least negative = best
    ("Win/Loss Ratio",   "kpi_win_loss_ratio",   lambda v: f"{v:.2f}",       "max"),
    ("Worst Loss",       "kpi_biggest_loss",     lambda v: f"${v:,.0f}",     "max"),   # least negative = best
    ("Net Realized P&L", "kpi_realized_pnl",     lambda v: f"${v:,.0f}",     "max"),
    ("Total Trades",     "kpi_total_trades",     lambda v: f"{int(v):,}",    "none"),
]
# Withdrawal rows — appended only if at least one selected run has withdrawals on.
if sub["in_withdrawals_on"].fillna(False).astype(bool).any():
    KPI_SPECS += [
        ("Total Withdrawn", "kpi_total_withdrawn",    lambda v: f"${v:,.0f}",     "none"),
        ("WD Coverage",     "kpi_coverage_pct",       lambda v: f"{v*100:,.1f}%", "max"),
        ("Avg Monthly WD",  "kpi_avg_monthly_income", lambda v: f"${v:,.0f}",     "none"),
        ("Months Full",     "kpi_months_full",        lambda v: f"{int(v):,}",    "max"),
        ("Months Partial",  "kpi_months_partial",     lambda v: f"{int(v):,}",    "min"),
        ("Months Zero",     "kpi_months_zero",        lambda v: f"{int(v):,}",    "min"),
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

st.dataframe(disp.style.apply(lambda _: style_df, axis=None), use_container_width=True,
             height=int((len(labels) + 1) * 35 + 3))   # fit all rows (incl. WD) — no inner scroll
st.caption("Green = best value in that row across the selected runs.")

# ─────────────────────────────────────────────────────────────────────────
# Criteria diff — only inputs that differ across the selected runs
# ─────────────────────────────────────────────────────────────────────────
st.subheader("Criteria differences")
explain("compare_criteria")

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
    ("Weekly Risk %", "in_weekly_risk_pct", _p),
    ("Max Weekly Risk", "in_max_weekly_risk", lambda v: "Uncapped" if pd.isna(v) else f"${v:,.0f}"),
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
explain("compare_curves")
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

# Cumulative withdrawn overlay — only if at least one selected run has withdrawals on.
if sub["in_withdrawals_on"].fillna(False).astype(bool).any():
    st.subheader("Cumulative Withdrawn")
    fig_wd = go.Figure()
    for rid, clab in zip(sel_ids, col_labels):
        tl = tlogs[rid]
        fig_wd.add_trace(go.Scatter(
            x=tl["trade_date"], y=tl["cum_withdrawn"].astype(float),
            mode="lines", name=clab))
    fig_wd.update_yaxes(tickformat="$,.0f")
    fig_wd.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10),
                         legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5))
    st.plotly_chart(fig_wd, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────
# Trade-by-trade comparison — every week each run traded, with filters
# ─────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Trade-by-Trade")
st.caption(
    "Every week each run actually traded, side by side — net P&L, the dollars at risk on "
    "that spread, and how it ended. Sort by Entry Date to line up the same week across runs; "
    "use the filters to focus on losers, a single year, or just the weeks where the runs diverged."
)


def _per_trade_rows(tl, rid):
    """Collapse a daily trade log into one row per closed trade."""
    if tl is None or tl.empty:
        return pd.DataFrame()
    _rp = pd.to_numeric(tl["realized_pnl_today"], errors="coerce").fillna(0)
    closes = tl[_rp != 0].copy()
    if closes.empty:
        return pd.DataFrame()
    closes["_ctn"] = closes["expiring_trade_num"].fillna(closes["trade_num"])
    closes["_rpnl"] = pd.to_numeric(closes["realized_pnl_today"], errors="coerce")
    closes["_exit"] = np.where(closes["expiring_trade_num"].notna(), "Expired",
                               closes["exit_reason"].fillna("—").astype(str))
    closes = closes.dropna(subset=["_ctn"])
    agg = closes.groupby("_ctn", as_index=False).agg(
        net_pnl=("_rpnl", "sum"), exit_label=("_exit", "last"), exit_date=("trade_date", "last"))
    ent = (tl[(tl["entry_day"] == 1) & tl["trade_num"].notna()]
           [["trade_num", "entry_date", "spx_close", "contracts", "max_loss", "spread_width_actual"]]
           .drop_duplicates("trade_num"))
    m = agg.merge(ent, left_on="_ctn", right_on="trade_num", how="left")
    m["Run"] = f"#{rid}"
    return m


_all = pd.concat([_per_trade_rows(tlogs[rid], rid) for rid in sel_ids], ignore_index=True)
if _all.empty:
    st.info("No closed trades to show for the selected runs.")
else:
    _all["entry_date"] = pd.to_datetime(_all["entry_date"])
    _all["net_pnl"] = pd.to_numeric(_all["net_pnl"], errors="coerce")
    _all["Result"] = np.where(_all["net_pnl"] >= 0, "Win", "Loss")
    _all["year"] = _all["entry_date"].dt.year

    fc1, fc2, fc3 = st.columns([2, 2, 3])
    _years = sorted(int(y) for y in _all["year"].dropna().unique())
    with fc1:
        sel_years = st.multiselect("Year", _years, default=_years, key="cmp_tt_years")
    with fc2:
        res_filter = st.radio("Result", ["All", "Wins", "Losses"], horizontal=True, key="cmp_tt_res")
    with fc3:
        disagree_only = st.checkbox(
            "Only weeks where the runs diverged (a run skipped it, or win-vs-loss split)",
            key="cmp_tt_dis")

    view = _all.copy()
    if sel_years:
        view = view[view["year"].isin(sel_years)]
    if res_filter == "Wins":
        view = view[view["Result"] == "Win"]
    elif res_filter == "Losses":
        view = view[view["Result"] == "Loss"]
    if disagree_only:
        _n = len(sel_ids)
        _div = _all.groupby("entry_date").filter(
            lambda g: (g["Run"].nunique() < _n) or (g["Result"].nunique() > 1))
        view = view[view["entry_date"].isin(_div["entry_date"].unique())]

    disp = pd.DataFrame({
        "Entry Date":  view["entry_date"].dt.date.astype(str),
        "Run":         view["Run"],
        "Width":       pd.to_numeric(view["spread_width_actual"], errors="coerce"),
        "Contracts":   pd.to_numeric(view["contracts"], errors="coerce"),
        "At Risk":     pd.to_numeric(view["max_loss"], errors="coerce").abs(),
        "Net P&L":     view["net_pnl"],
        "Result":      view["Result"],
        "Exit":        view["exit_label"],
        "SPX @ Entry": pd.to_numeric(view["spx_close"], errors="coerce"),
    }).sort_values(["Entry Date", "Run"], ascending=[False, True])

    st.caption(f"{len(disp):,} trades shown")
    st.dataframe(
        disp, use_container_width=True, hide_index=True, height=460,
        column_config={
            "Width":       st.column_config.NumberColumn(format="$%,.0f"),
            "Contracts":   st.column_config.NumberColumn(format="%,d"),
            "At Risk":     st.column_config.NumberColumn(format="$%,.0f"),
            "Net P&L":     st.column_config.NumberColumn(format="$%,.0f"),
            "SPX @ Entry": st.column_config.NumberColumn(format="%,.0f"),
        })

render_footer()
