"""Run Detail — drill-in view for a single scenario.

Selects a run from a dropdown (or ?run_id=N URL param) and shows:
- Headline KPIs + criteria
- Equity curve, drawdown, annual returns
- Per-day trade log (filterable / searchable)
"""

from __future__ import annotations

import math

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from data.db import (load_scenario_runs, load_trade_log, load_spx_daily,
                     check_password_gate, render_footer, request_for_run_label)
from data.docs import explain, guide_link, profile_label, risk_profile

st.set_page_config(
    page_title="Run Detail — StrategyXL",
    page_icon="🔍",
    layout="wide",
)
check_password_gate()

# ─────────────────────────────────────────────────────────────────────────
# Run selector — URL param overrides dropdown
# ─────────────────────────────────────────────────────────────────────────
runs = load_scenario_runs()
if runs.empty:
    st.warning("No scenarios in the database.")
    st.stop()

# Build a label for each run that's friendly for the dropdown
runs = runs.copy()
runs["display"] = (
    runs["run_id"].astype(str)
    + "  —  "
    + runs["run_label"].fillna("(no label)").astype(str)
    + "  ["
    + runs["in_trend_filter_ma"].fillna("(no filter)").astype(str)
    + ", width $"
    + runs["in_spread_width"].astype(int).astype(str)
    + "]"
)

# URL param: ?run_id=12345
param_run_id = st.query_params.get("run_id")
default_idx = 0
if param_run_id and param_run_id.isdigit():
    matches = runs.index[runs["run_id"] == int(param_run_id)].tolist()
    if matches:
        default_idx = matches[0]

selected_label = st.selectbox(
    "Select a run",
    options=runs["display"].tolist(),
    index=default_idx,
)
selected_run_id = int(runs.loc[runs["display"] == selected_label, "run_id"].iloc[0])

# Keep URL param synced so the link is bookmarkable
if str(selected_run_id) != param_run_id:
    st.query_params["run_id"] = str(selected_run_id)

run = runs.loc[runs["run_id"] == selected_run_id].iloc[0]

# ─────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────
# Escape '$' so the label's dollar amounts don't trigger LaTeX math in the markdown title.
_run_lbl = str(run["run_label"] or "").replace("$", "\\$")
st.title(f"Run #{run['run_id']} — {_run_lbl}")
_ma = run["in_trend_filter_ma"]
_filter_txt = f"{_ma}" if (run["in_trend_filter_on"] and pd.notna(_ma)) else "OFF"
st.caption(
    f"{run['in_backtest_start']} to {run['in_backtest_end']}  ·  "
    f"trend filter: **{_filter_txt}**  ·  "
    f"width: **\\${run['in_spread_width']:.0f}**  ·  "
    f"starting cap: **\\${run['in_starting_capital']:,.0f}**"
)
_req = request_for_run_label(run["run_label"])
if _req:
    _by = f" · requested by {_req['requested_by']}" if _req.get("requested_by") else ""
    st.caption(f"📝 Requested as **{str(_req['scenario_name']).replace('$', chr(92) + '$')}**{_by}")
guide_link()

# ─────────────────────────────────────────────────────────────────────────
# Headline KPI cards
# ─────────────────────────────────────────────────────────────────────────
def fmt_pct(v):
    return "—" if pd.isna(v) else f"{v*100:,.2f}%"
def fmt_money(v):
    return "—" if pd.isna(v) else f"${v:,.2f}"
def fmt_money0(v):
    return "—" if pd.isna(v) else f"${v:,.0f}"
def fmt_num(v, dp=2):
    return "—" if pd.isna(v) else f"{v:.{dp}f}"

# ─────────────────────────────────────────────────────────────────────────
# Full criteria (collapsible) — every in_* input, logically grouped
# ─────────────────────────────────────────────────────────────────────────
with st.expander("Full criteria", expanded=False):
    def _b(v):  return "—" if pd.isna(v) else ("On" if bool(v) else "Off")
    def _m0(v): return "—" if pd.isna(v) else f"${v:,.0f}"
    def _m2(v): return "—" if pd.isna(v) else f"${v:,.2f}"
    def _p(v):  return "—" if pd.isna(v) else f"{round(float(v) * 100, 4):g}%"
    def _optp(v): return "Off" if pd.isna(v) else f"{round(float(v) * 100, 4):g}%"
    def _d(v):  return "—" if pd.isna(v) else f"{float(v):.2f}"
    def _t(v):  return "—" if (pd.isna(v) or str(v).strip() == "") else str(v)
    def _dt(v): return "—" if pd.isna(v) else str(v)

    def _grp(title, rows):
        md = f"| **{title}** | |\n|:--|--:|\n"
        for lbl, val in rows:
            v = str(val).replace("$", "\\$")   # escape so dollar amounts don't render as LaTeX
            md += f"| {lbl} | {v} |\n"
        st.markdown(md)

    g_universe = [
        ("Backtest Start", _dt(run["in_backtest_start"])),
        ("Backtest End", _dt(run["in_backtest_end"])),
        ("Short Delta Target", _d(run["in_short_delta_threshold"])),
        ("Short Delta Range",
         "—" if (pd.isna(run["in_short_delta_min"]) and pd.isna(run["in_short_delta_max"]))
         else f'{_d(run["in_short_delta_min"])} – {_d(run["in_short_delta_max"])}'),
        ("Spread Width", _m0(run["in_spread_width"])),
        ("Spread Handling", _t(run["in_spread_handling"])),
        ("Product Mode", _t(run["in_product_mode"])),
    ]
    g_trend = [
        ("Trend Filter", _b(run["in_trend_filter_on"])),
        ("Moving Average", _t(run["in_trend_filter_ma"])),
    ]
    g_sizing = [
        ("Risk Profile", profile_label(run["in_max_weekly_risk"])),
        ("Starting Capital", _m0(run["in_starting_capital"])),
        ("Weekly Risk %", _p(run["in_weekly_risk_pct"])),
        ("Max Weekly Risk", "Uncapped" if pd.isna(run["in_max_weekly_risk"]) else _m0(run["in_max_weekly_risk"])),
    ]
    g_exits = [
        ("Breach Close", _b(run["in_breach_close"])),
        ("1-DTE / OTM Close", _p(run["in_otm_close_threshold"])),
        ("Profit Target", _optp(run["in_profit_target"])),
        ("Stop Loss", _optp(run["in_stop_loss"])),
    ]
    g_costs = [
        ("Commission / Contract", _m2(run["in_commission_per_contract"])),
        ("Slippage / Leg", _m2(run["in_slippage_per_leg"])),
        ("Mid Source", _t(run["in_mid_source"])),
        ("Entry Fill", _t(run["in_entry_fill"])),
        ("Exit Fill", _t(run["in_exit_fill"])),
    ]
    g_benchmark = [
        ("Target CAGR", _p(run["in_target_cagr"])),
    ]
    g_withdrawals = [
        ("Withdrawals", _b(run["in_withdrawals_on"])),
        ("Target Monthly", _m0(run["in_target_monthly_withdrawal"])),
        ("Floor", _m0(run["in_withdrawal_floor"])),
        ("Start Date", _dt(run["in_withdrawal_start_date"])),
        ("Inflation Adjust", _p(run["in_inflation_adjust_pct"])),
    ]

    gc1, gc2, gc3 = st.columns(3)
    with gc1:
        _grp("Universe", g_universe)
        _grp("Trend Filter", g_trend)
    with gc2:
        _grp("Sizing", g_sizing)
        _grp("Exits", g_exits)
    with gc3:
        _grp("Costs", g_costs)
        _grp("Benchmark", g_benchmark)
        _grp("Withdrawals", g_withdrawals)

# Load the trade log up front so the equity-decomposition cards can sum interest exactly.
tlog = load_trade_log(selected_run_id)
_interest_income = (float(pd.to_numeric(tlog["interest_today"], errors="coerce").sum())
                    if (not tlog.empty and "interest_today" in tlog.columns) else 0.0)

explain("detail_kpis", "ⓘ  About these metrics")

# Equity decomposition shown as an equation:
#   Ending Equity = Starting Capital + Net Realized P&L + Interest Income (+ Open Position) (− Withdrawals)
_parts = [
    ("Ending Equity",    run["kpi_ending_equity"],   None,
     "Account value on the last day — the sum of everything to the right of the = sign."),
    ("Starting Capital", run["in_starting_capital"], "=",  None),
    ("Net Realized P&L", run["kpi_realized_pnl"],    "+",
     "Booked profit from closed trades, net of commission & slippage. Trading only — no interest."),
    ("Interest Income",  _interest_income,           "+",
     "Interest earned on the account's cash at the FRED 3-month T-bill rate, compounded daily."),
]

# Open position at the backtest end: if the final entry hadn't resolved by the end date
# (entered in the last week, expiring after it), its credit is booked into equity but its P&L
# is NOT counted in Net Realized P&L (only closed trades are). Show it as its own term so the
# equation reconciles. ~0 (and hidden) when the backtest ends with no trade open.
_withdrawn = float(run["kpi_total_withdrawn"]) if pd.notna(run.get("kpi_total_withdrawn")) else 0.0
_open_pos = (float(run["kpi_ending_equity"]) - float(run["in_starting_capital"])
             - float(run["kpi_realized_pnl"]) - _interest_income + _withdrawn)
if abs(_open_pos) > 1.0:
    _parts.append(("Open Position", abs(_open_pos), "+" if _open_pos >= 0 else "−",
                   "Net unrealized value of the trade still open on the backtest's end date — its "
                   "current mark-to-market less the commission paid to open it. It isn't in Net "
                   "Realized P&L yet (the trade hasn't closed), so it's shown here so the equation "
                   "foots exactly. Usually tiny — often just the open trade's entry commission."))

if _withdrawn > 0:
    _parts.append(("Withdrawals", run["kpi_total_withdrawn"], "−",
                   "Total cash withdrawn over the backtest — reduces ending equity."))

_eq_widths = []
for _lbl, _val, _op, _hlp in _parts:
    if _op is not None:
        _eq_widths.append(0.35)
    _eq_widths.append(2.2)
_eqc = st.columns(_eq_widths, vertical_alignment="center")
_ci = 0
for _lbl, _val, _op, _hlp in _parts:
    if _op is not None:
        _eqc[_ci].markdown(
            f"<div style='text-align:center;font-size:1.8rem;color:#8b95a3'>{_op}</div>",
            unsafe_allow_html=True)
        _ci += 1
    _eqc[_ci].metric(_lbl, fmt_money0(_val), help=_hlp)
    _ci += 1

st.write("")

# Remaining headline metrics
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Total Return", fmt_pct(run["kpi_total_return_pct"]))
    st.metric("CAGR",         fmt_pct(run["kpi_cagr"]))
    st.metric("Money-Weighted Return (XIRR)", fmt_pct(run.get("kpi_xirr")),
              help="Annualized internal rate of return over the actual cash flows (capital in, "
                   "withdrawals out, ending value). Equals CAGR when there are no withdrawals; for "
                   "withdrawal runs it credits the income taken along the way — the true "
                   "apples-to-apples return across WD and non-WD runs.")
    st.metric("Years",        fmt_num(run["kpi_years"], 2))
with c2:
    st.metric("Max Drawdown", fmt_pct(run["kpi_max_dd_pct"]))
    st.metric("Max DD Date",  str(run["kpi_max_dd_date"]) if not pd.isna(run["kpi_max_dd_date"]) else "—")
    _cap = run["in_max_weekly_risk"]
    _wrp = run["in_weekly_risk_pct"]
    if pd.notna(_wrp) and pd.isna(_cap):
        st.metric("Max Weekly Risk", f"{float(_wrp) * 100:.0f}% (uncapped)",
                  help="Uncapped — risk stays at this % of the account every week with no hard "
                       "dollar ceiling, so the dollar amount grows as the account grows.")
    elif pd.notna(_wrp):
        _bind = float(_cap) / float(_wrp)   # equity where the cap starts to bite
        st.metric("Max Weekly Risk", f"${float(_cap):,.0f}",
                  help=f"The hard ceiling — never more than this in a single week. Equals "
                       f"{float(_wrp) * 100:.0f}% of equity until the account passes "
                       f"\\${_bind:,.0f}, then it's a flat \\${float(_cap):,.0f} (a shrinking %).")
with c3:
    st.metric("Total Trades",  int(run["kpi_total_trades"]) if not pd.isna(run["kpi_total_trades"]) else "—")
    st.metric("Win Rate",      fmt_pct(run["kpi_win_rate"]))
    st.metric("Profit Factor", fmt_num(run["kpi_profit_factor"], 2))

st.divider()

# Risk-adjusted (monthly returns, annualized)
st.subheader("Risk-Adjusted Returns")
explain("detail_risk")
st.caption("Monthly returns, annualized  ·  risk-free = FRED 3-mo  ·  Sortino MAR = 0")
rc1, rc2, rc3, rc4 = st.columns(4)
with rc1: st.metric("Annualized Volatility", fmt_pct(run["kpi_ann_return_stdev"]),
                    help="Annualized standard deviation of monthly returns")
with rc2: st.metric("Sharpe Ratio",          fmt_num(run["kpi_sharpe"], 2))
with rc3: st.metric("Sortino Ratio",         fmt_num(run["kpi_sortino"], 2))
with rc4: st.metric("Calmar Ratio",          fmt_num(run["kpi_calmar"], 2),
                    help="CAGR ÷ |Max Drawdown|")

st.divider()

# Friction
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Cum Commission", fmt_money(run["kpi_cum_commission"]))
with c2: st.metric("Cum Slippage",   fmt_money(run["kpi_cum_slippage"]))
with c3:
    friction = (run.get("kpi_cum_commission") or 0) + (run.get("kpi_cum_slippage") or 0)
    st.metric("Total Friction",      f"${friction:,.0f}")
with c4:
    if run["kpi_ending_equity"]:
        st.metric("Friction % of Equity",
                  fmt_pct(friction / run["kpi_ending_equity"]))

# Withdrawals (if any)
if run.get("in_withdrawals_on"):
    st.divider()
    st.subheader("Withdrawals")
    explain("detail_withdrawals")
    st.caption(
        f"Starting target \\${run['in_target_monthly_withdrawal']:,.0f}/mo "
        f"(grows +{fmt_pct(run['in_inflation_adjust_pct'])}/yr with inflation)  ·  "
        f"floor \\${run['in_withdrawal_floor']/1000:,.0f}k  ·  "
        f"start {run['in_withdrawal_start_date']}"
    )
    st.metric("Total-Value Return", fmt_pct(run.get("kpi_total_value_return")),
              help="Cumulative return counting BOTH ending equity AND every dollar withdrawn. "
                   "Total Return (above) is ending-equity only, so it understates a withdrawal run.")
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Total Withdrawn",  fmt_money0(run["kpi_total_withdrawn"]))
    with c2: st.metric("Coverage",         fmt_pct(run["kpi_coverage_pct"]),
                       help="Share of the inflation-adjusted target actually paid")
    with c3: st.metric("Avg Monthly",      fmt_money0(run["kpi_avg_monthly_income"]),
                       help="Average actual monthly withdrawal. It exceeds the starting target "
                            "because the target is inflation-adjusted — later years pay more, so "
                            "the lifetime average lands above the starting $/mo figure.")
    with c4: st.metric("Worst Month",      fmt_money0(run["kpi_worst_single_month"]),
                       help="Smallest non-zero monthly withdrawal (an early, pre-inflation month)")

    def _miv(v): return "—" if pd.isna(v) else f"{int(v):,}"
    d1, d2, d3, d4 = st.columns(4)
    with d1: st.metric("Months Full",        _miv(run["kpi_months_full"]),
                       help="Months the full inflation-adjusted target was paid")
    with d2: st.metric("Months Partial",     _miv(run["kpi_months_partial"]),
                       help="Months only part of the target could be paid (would have breached the floor)")
    with d3: st.metric("Months Zero",        _miv(run["kpi_months_zero"]),
                       help="Months nothing was paid (already at/below floor)")
    with d4: st.metric("Months Not Started", _miv(run["kpi_months_not_started"]),
                       help="Months before the withdrawal start date")

    # Per-year income (cash flow generated) — bar chart + year-by-year table
    _w = tlog[["trade_date", "withdrawal_today", "target_withdrawal_today"]].copy()
    _w["Year"] = pd.to_datetime(_w["trade_date"]).dt.year
    _w["withdrawal_today"] = pd.to_numeric(_w["withdrawal_today"], errors="coerce").fillna(0.0)
    _w["target_withdrawal_today"] = pd.to_numeric(_w["target_withdrawal_today"], errors="coerce").fillna(0.0)
    _yr = _w.groupby("Year", as_index=False).agg(
        Withdrawn=("withdrawal_today", "sum"),
        Target=("target_withdrawal_today", "sum"),
        MonthsPaid=("withdrawal_today", lambda s: int((s > 0).sum())),
    )
    _yr["Coverage"] = [(w / t) if t > 0 else float("nan")
                       for w, t in zip(_yr["Withdrawn"], _yr["Target"])]

    st.markdown("**Income generated per year**")
    _figw = go.Figure()
    _figw.add_trace(go.Bar(x=_yr["Year"], y=_yr["Withdrawn"], name="Withdrawn",
                           marker_color="#2e7d32"))
    _figw.add_trace(go.Scatter(x=_yr["Year"], y=_yr["Target"], name="Target (infl-adj)",
                               mode="lines+markers", line=dict(color="#9aa0a6", dash="dot")))
    _figw.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                        barmode="group", legend=dict(orientation="h", y=1.12, x=0))
    _figw.update_yaxes(tickformat="$,.0f")
    st.plotly_chart(_figw, use_container_width=True)

    _disp = _yr.copy()
    _disp["Target"] = _disp["Target"].map(lambda v: f"${v:,.0f}")
    _disp["Withdrawn"] = _disp["Withdrawn"].map(lambda v: f"${v:,.0f}")
    _disp["Coverage"] = _disp["Coverage"].map(lambda v: "—" if pd.isna(v) else f"{v * 100:.1f}%")
    _disp = _disp.rename(columns={"MonthsPaid": "Months Paid"})
    st.dataframe(_disp[["Year", "Target", "Withdrawn", "Coverage", "Months Paid"]],
                 hide_index=True, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────
# Charts (require the trade log — already loaded above for the equity cards)
# ─────────────────────────────────────────────────────────────────────────
st.divider()
if tlog.empty:
    st.warning(f"No trade log rows found for run {selected_run_id}.")
    st.stop()

tlog = tlog.copy()
tlog["_dt"] = pd.to_datetime(tlog["trade_date"])


def _period_window(key: str):
    """Per-chart period slicer. When the run spans > 5 years, show a radio of
    'All' + three contiguous whole-year blocks and return the selected
    (start, end) Timestamps. Short runs get no radio (returns the full span)."""
    dmin, dmax = tlog["_dt"].min(), tlog["_dt"].max()
    if (dmax - dmin).days <= 5 * 365.25:
        return dmin, dmax
    y0, y1 = int(dmin.year), int(dmax.year)
    size = math.ceil((y1 - y0 + 1) / 3)
    blocks, s = [], y0
    while s <= y1:
        e = min(s + size - 1, y1)
        blocks.append((s, e))
        s = e + 1
    labels = [f"All ({y0}–{y1})"] + [f"{a}–{b}" for a, b in blocks]
    choice = st.radio("Period", labels, horizontal=True, key=key,
                      label_visibility="collapsed")
    i = labels.index(choice)
    if i == 0:
        return dmin, dmax
    a, b = blocks[i - 1]
    return pd.Timestamp(a, 1, 1), pd.Timestamp(b, 12, 31)


# Equity curve
st.subheader("Equity Curve")
_w0, _w1 = _period_window("per_eq")
eqd = tlog[(tlog["_dt"] >= _w0) & (tlog["_dt"] <= _w1)]
fig_eq = go.Figure()
fig_eq.add_trace(go.Scatter(
    x=eqd["trade_date"], y=eqd["equity_eod"],
    mode="lines", line=dict(color="#3D8B37", width=2),
    fill="tozeroy", fillcolor="rgba(61,139,55,0.1)",
    name="Equity",
))
fig_eq.add_hline(y=run["in_starting_capital"], line_dash="dash", line_color="gray",
                  annotation_text="Starting Capital", annotation_position="bottom right")
fig_eq.update_layout(height=400, margin=dict(l=10, r=10, t=20, b=10))
fig_eq.update_yaxes(tickformat="$,.0f")
st.plotly_chart(fig_eq, use_container_width=True)

# Drawdown & Profit Cushion — dual-axis overlay. Left axis = drawdown from peak
# (blue, hangs below 0). Right axis = cumulative return from start = equity/start − 1
# (red "profit cushion", sits on top). The two axes are scaled independently but
# share a zero line, so when the red cushion crosses below 0 the equity has dipped
# into starting capital. Purely a display derivation — the drawdown metric is untouched.
st.subheader("Drawdown & Profit Cushion")
explain("detail_drawdown")
st.caption(
    "Drawdown from peak (left axis, ≤ 0)  ·  cumulative return from start (right axis).  "
    "When the cushion drops below 0%, equity has dipped into starting capital."
)

_w0d, _w1d = _period_window("per_dd")
ddd = tlog[(tlog["_dt"] >= _w0d) & (tlog["_dt"] <= _w1d)]

start_cap = float(run["in_starting_capital"])
cum_ret = ddd["equity_eod"].astype(float) / start_cap - 1.0
dd = ddd["drawdown_pct"].astype(float)

cr_max = max(float(cum_ret.max()), 0.0)
cr_min = min(float(cum_ret.min()), 0.0)
dd_min = min(float(dd.min()), 0.0)

# Build aligned dual ranges: drawdown occupies the band below zero, cushion above.
pad = 0.10
span = max(cr_max - cr_min, 0.01)
r_top = cr_max + span * pad if cr_max > 0 else 0.05
r_bot_data = cr_min - span * pad if cr_min < 0 else 0.0
l_bot = dd_min - abs(dd_min) * pad if dd_min < 0 else -0.05

# Zero-fraction = share of plot height below zero (clamped for a balanced look),
# then force both axes to put 0 at the same fraction so the zero lines coincide.
f = abs(l_bot) / (abs(l_bot) + max(r_top, 0.01))
f = min(max(f, 0.40), 0.75)
r_bot = min(-f * r_top / (1 - f), r_bot_data)      # extend down if cushion goes negative
f = (0 - r_bot) / (r_top - r_bot)                  # recompute after pinning r_bot
l_top = abs(l_bot) * (1 - f) / f

# Drawdown-axis labels: only 0 and below (hide positive ticks).
step = 0.10
dd_ticks = [-step * i for i in range(0, int(abs(l_bot) / step) + 1)]

fig_dd = go.Figure()
fig_dd.add_trace(go.Scatter(
    x=ddd["trade_date"], y=dd, name="Drawdown from Peak",
    mode="lines", line=dict(color="#5B8AA6", width=1),
    fill="tozeroy", fillcolor="rgba(91,138,166,0.55)", yaxis="y",
))
fig_dd.add_trace(go.Scatter(
    x=ddd["trade_date"], y=cum_ret, name="Profit Cushion",
    mode="lines", line=dict(color="#3D8B37", width=1.2),  # same green as the Equity Curve
    fill="tozeroy", fillcolor="rgba(61,139,55,0.50)", yaxis="y2",
))
fig_dd.update_layout(
    height=440,
    margin=dict(l=10, r=10, t=20, b=10),
    yaxis=dict(title="Drawdown (%)", range=[l_bot, l_top],
               tickvals=dd_ticks, tickformat=".0%",
               zeroline=True, zerolinecolor="rgba(140,140,140,0.7)", showgrid=False),
    yaxis2=dict(title="Cumulative Return (%)", range=[r_bot, r_top],
                tickformat=".0%", overlaying="y", side="right",
                showgrid=True, gridcolor="rgba(150,150,150,0.18)"),
    legend=dict(orientation="h", yanchor="bottom", y=-0.28, xanchor="center", x=0.5),
    hovermode="x unified",
)
st.plotly_chart(fig_dd, use_container_width=True)

# Annual returns
st.subheader("Annual Returns")
_w0a, _w1a = _period_window("per_ann")
annd = tlog[(tlog["_dt"] >= _w0a) & (tlog["_dt"] <= _w1a)]
annual = (
    annd[["trade_date", "realized_pnl_today"]]
    .assign(year=lambda d: pd.to_datetime(d["trade_date"]).dt.year)
    .groupby("year", as_index=False)["realized_pnl_today"].sum()
)
fig_ann = px.bar(
    annual, x="year", y="realized_pnl_today",
    color=annual["realized_pnl_today"] > 0,
    color_discrete_map={True: "#3D8B37", False: "#C84B4B"},
)
fig_ann.update_layout(height=280, showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
fig_ann.update_yaxes(tickformat="$,.0f", title="Net P&L")
fig_ann.update_xaxes(title="Year", dtick=1)
st.plotly_chart(fig_ann, use_container_width=True)

# Cumulative withdrawn (only when withdrawals are on) — rises over time and
# flattens whenever the account sits at the floor and payments pause.
if run.get("in_withdrawals_on"):
    st.subheader("Cumulative Withdrawn")
    fig_wd = go.Figure()
    fig_wd.add_trace(go.Scatter(
        x=tlog["trade_date"], y=tlog["cum_withdrawn"].astype(float),
        mode="lines", line=dict(color="#C28A2B", width=1.5),
        fill="tozeroy", fillcolor="rgba(194,138,43,0.25)", name="Cumulative Withdrawn",
    ))
    fig_wd.update_layout(height=260, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
    fig_wd.update_yaxes(tickformat="$,.0f")
    st.plotly_chart(fig_wd, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────
# Top 10 winning / losing trades — with entry context
# ─────────────────────────────────────────────────────────────────────────
# Win / Loss profile — the small-wins / big-losses shape of the strategy
# ─────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Win / Loss Profile")
st.caption("A 7-DTE, 10-delta credit spread is lots of small wins and a few big losses — "
           "these size that. A win/loss ratio below 1 means each win is smaller than each loss; "
           "the high win rate is what makes it profitable.")
w1, w2, w3, w4, w5 = st.columns(5)
with w1: st.metric("Win Rate", fmt_pct(run["kpi_win_rate"]))
with w2: st.metric("Avg Win", fmt_money0(run["kpi_avg_win"]))
with w3: st.metric("Avg Loss", fmt_money0(run["kpi_avg_loss"]))
with w4:
    _wl = run["kpi_win_loss_ratio"]
    st.metric("Win/Loss Ratio", "—" if pd.isna(_wl) else f"{float(_wl):.2f}",
              help="Average win ÷ |average loss|. Below 1.0 means a typical win is smaller "
                   "than a typical loss.")
with w5: st.metric("Worst Loss", fmt_money0(run["kpi_biggest_loss"]))

# ─────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Top 10 Winning & Losing Trades")
explain("detail_top10")

# Per-trade NET P&L: realized_pnl_today is the friction-adjusted result, booked on
# the close day. Attribute it to the closing trade — the expiring trade on expir
# days, otherwise the current trade_num on early-exit days — then sum per trade.
closes = tlog[tlog["realized_pnl_today"].fillna(0) != 0].copy()
if closes.empty:
    st.caption("No closed trades to rank for this run.")
else:
    closes["closing_trade_num"] = closes["expiring_trade_num"].fillna(closes["trade_num"])
    closes["exit_label"] = np.where(closes["expiring_trade_num"].notna(), "Expire",
                                    closes["exit_reason"])
    closes = closes.dropna(subset=["closing_trade_num"])
    per_trade = closes.groupby("closing_trade_num", as_index=False).agg(
        net_pnl=("realized_pnl_today", "sum"),
        exit_label=("exit_label", "last"),
        exit_date=("trade_date", "last"),   # the day the trade actually closed (P&L books here)
    )

    # Entry context: one row per trade where entry_day == 1 (entry_date == trade_date).
    entries = (
        tlog[(tlog["entry_day"] == 1) & tlog["trade_num"].notna()]
        [["trade_num", "entry_date", "spx_close", "trend_ma"]]
        .rename(columns={"spx_close": "entry_spx", "trend_ma": "entry_ma"})
        .drop_duplicates("trade_num")
    )
    m = per_trade.merge(entries, left_on="closing_trade_num", right_on="trade_num", how="left")

    # Always-on 200-day SMA context, joined on entry_date.
    spx = load_spx_daily()[["trade_date", "sma_200"]].copy()
    spx["entry_date"] = pd.to_datetime(spx["trade_date"])
    m["entry_date"] = pd.to_datetime(m["entry_date"])
    m["exit_date"] = pd.to_datetime(m["exit_date"])
    m = m.merge(spx[["entry_date", "sma_200"]], on="entry_date", how="left")

    m["entry_spx"] = m["entry_spx"].astype(float)
    m["pct_above_ma"]  = (m["entry_spx"] / m["entry_ma"].astype(float) - 1.0) * 100.0
    m["pct_above_200"] = (m["entry_spx"] / m["sma_200"].astype(float) - 1.0) * 100.0

    _ma_name = run["in_trend_filter_ma"]
    _ma_on = bool(run["in_trend_filter_on"]) and pd.notna(_ma_name)
    _ma_col = f"% above {_ma_name}" if _ma_on else "% above entry MA"

    def _fmt_table(d: pd.DataFrame) -> pd.DataFrame:
        cols = {
            "Trade #":    d["closing_trade_num"].astype(int),
            "Entry Date": d["entry_date"].dt.date.astype(str),
            "Exit Date":  d["exit_date"].dt.date.astype(str),
            "Exit":       d["exit_label"].fillna("—"),
            "Net P&L":    d["net_pnl"].astype(float),
            "Entry SPX":  d["entry_spx"],
        }
        if _ma_on:   # filter-off runs have no entry-MA criterion → omit the column
            cols[_ma_col] = d["pct_above_ma"]
        cols["% above 200-SMA"] = d["pct_above_200"]
        return pd.DataFrame(cols)

    colcfg = {
        "Net P&L":         st.column_config.NumberColumn(format="$%,.0f"),
        "Entry SPX":       st.column_config.NumberColumn(format="%,.0f"),
        "% above 200-SMA": st.column_config.NumberColumn(format="%.2f%%"),
    }
    if _ma_on:
        colcfg[_ma_col] = st.column_config.NumberColumn(format="%.2f%%")

    if not _ma_on:
        st.caption("This run's trend filter is **off** — there's no entry-MA criterion, "
                   "so that column is omitted. The “% above 200-SMA” column still shows "
                   "where SPX sat relative to its 200-day average on each entry.")

    st.markdown("**🟢 Top 10 Winning Trades**")
    st.dataframe(_fmt_table(m.nlargest(10, "net_pnl")), use_container_width=True,
                 hide_index=True, column_config=colcfg)
    st.markdown("**🔴 Top 10 Losing Trades**")
    st.dataframe(_fmt_table(m.nsmallest(10, "net_pnl")), use_container_width=True,
                 hide_index=True, column_config=colcfg)

# ─────────────────────────────────────────────────────────────────────────
# Trade log
# ─────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Trade Log")
explain("detail_tradelog")

row_filter = st.radio(
    "Show", options=["All days", "Entry days", "Days with an open trade", "Exit days"],
    index=0, horizontal=True,
)

view_tlog = tlog.drop(columns=["_dt"]).copy()
if row_filter == "Entry days":
    view_tlog = view_tlog[view_tlog["entry_day"] == 1]
elif row_filter == "Days with an open trade":
    view_tlog = view_tlog[view_tlog["trade_num"].notna()]
elif row_filter == "Exit days":
    view_tlog = view_tlog[
        view_tlog["exit_reason"].notna() | view_tlog["expiring_trade_num"].notna()
    ]

st.caption(f"{len(view_tlog):,} rows shown of {len(tlog):,}  ·  click a column header to sort")

# Comma-format every numeric column for readability. SQL DECIMALs arrive as object/
# Decimal, so coerce to float first (dtype checks alone would miss them). Per-column
# overrides for precision; otherwise: whole numbers → 0 dp, big dollars → 0 dp, else 2 dp.
_tl_cfg = {}
_skip = {"trade_date", "entry_date", "expir_date", "product", "settlement",
         "exit_reason", "withdrawal_status"}
# Small, precision-sensitive values (deltas, fraction/ratio columns) → 4 decimals.
_four_dp = {"short_delta", "long_delta", "pct_of_max_profit", "pct_otm_vs_short",
            "drawdown_pct", "dd_vs_starting_pct", "dd_vs_target_cagr_pct"}
# Index-level values that read better with cents than as a whole number → 2 decimals.
_two_dp = {"spx_close", "trend_ma"}
for _col in view_tlog.columns:
    if _col in _skip:
        continue
    _num = pd.to_numeric(view_tlog[_col], errors="coerce")
    _nonnull = _num.dropna()
    if _nonnull.empty:
        continue  # not a numeric column
    view_tlog[_col] = _num
    if _col in _four_dp:
        _fmt = "%,.4f"                            # deltas & ratios — keep precision
    elif _col in _two_dp:
        _fmt = "%,.2f"                            # SPX close / trend MA — show cents
    elif (_nonnull % 1 == 0).all():
        _fmt = "%,d"                              # whole numbers (counts, widths, day_num)
    elif _nonnull.abs().max() >= 1000:
        _fmt = "%,.0f"                            # large dollar amounts — drop the cents
    else:
        _fmt = "%,.2f"                            # prices, per-share P&L — 2 decimals
    _tl_cfg[_col] = st.column_config.NumberColumn(format=_fmt)
st.dataframe(view_tlog, use_container_width=True, height=600, hide_index=True,
             column_config=_tl_cfg)

render_footer()
