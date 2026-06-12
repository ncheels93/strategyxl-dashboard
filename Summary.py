"""StrategyXL — SPX 7 DTE Put Credit Spread backtest dashboard.

Overview page: best-in-class callouts, sortable leaderboard, scatter chart,
sidebar filters. Click a run's number in the leaderboard to drill in.
"""

import math

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data.db import load_scenario_runs, load_spx_daily, check_password_gate, render_footer
from data.docs import explain, guide_link, risk_profile, profile_label

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
    "Strategy: enter Friday, sell the 5 / 10 / 15 / 20-delta put, \\$10–\\$200 widths, "
    "hold to expiration with 1DTE / breach exits. All P&L figures are NET of commission and slippage."
)
guide_link()

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

# Sizing dimensions as friendly display strings (DB values arrive as Decimal).
# Capped model: weekly $ at risk = MIN(weekly_risk_pct × equity, max_weekly_risk).
#   weekly_risk_pct = % of equity at risk each week (default 50%),
#   max_weekly_risk = hard $ ceiling (the risk dial); blank = uncapped.
_wrp = pd.to_numeric(df["in_weekly_risk_pct"], errors="coerce")
_cap = pd.to_numeric(df["in_max_weekly_risk"], errors="coerce")
df["risk_pct_disp"] = _wrp.map(lambda v: f"{v*100:.0f}%"  if pd.notna(v) else "—")
df["cap_disp"]      = _cap.map(lambda v: f"${v/1000:.0f}k" if pd.notna(v) else "Uncapped")
# Friendly risk-profile names derived from the cap (the risk dial): Conservative … Maximum.
df["risk_profile"]  = _cap.map(risk_profile)
df["profile_label"] = _cap.map(profile_label)
_sc = pd.to_numeric(df["in_starting_capital"], errors="coerce").fillna(0)
df["start_disp"] = "$" + (_sc / 1000).round().astype(int).astype(str) + "k"
# Withdrawal target as a friendly string ("—" for no-withdrawal runs).
_tw = pd.to_numeric(df["in_target_monthly_withdrawal"], errors="coerce")
df["target_disp"] = _tw.map(lambda v: f"${int(round(v)):,}/mo" if pd.notna(v) and v > 0 else "—")
# Display strings for the breakdown roll-ups.
_sw = pd.to_numeric(df["in_spread_width"], errors="coerce")
df["width_disp"] = _sw.map(lambda v: f"${int(v)}" if pd.notna(v) else "—")
# Short-strike delta target as a friendly string (0.05 → "5Δ").
_sd = pd.to_numeric(df["in_short_delta_threshold"], errors="coerce")
df["delta_disp"] = _sd.map(lambda v: f"{v*100:g}Δ" if pd.notna(v) else "—")
df["wd_disp"] = (df["in_withdrawals_on"] == True).map({True: "On", False: "Off"})

# ─────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ─────────────────────────────────────────────────────────────────────────
# Pinned at the very top of the sidebar (above the header) so the runs-shown count is
# visible without scrolling; its content is filled in after filtering below.
_count_slot = st.sidebar.empty()
st.sidebar.header("Filters")

# Numeric KPI columns used by the performance screen (coerce once, NaN-safe).
_cagr_n = pd.to_numeric(df["kpi_cagr"], errors="coerce")
_dd_n   = pd.to_numeric(df["kpi_max_dd_pct"], errors="coerce")
_cal_n  = pd.to_numeric(df["kpi_calmar"], errors="coerce")

# ── Performance screen (top). Thresholds that drive the WHOLE page — cards, scatter
#    and leaderboard all honor them. Each slider defaults to its open end (= no
#    screening) and only starts filtering once moved, so blank / 0-trade runs stay
#    visible until you deliberately screen them out.
st.sidebar.caption("**Performance screen**")

_cagr_lo = float(math.floor((_cagr_n.min() if _cagr_n.notna().any() else 0.0) * 100))
_cagr_hi = float(math.ceil((_cagr_n.max() if _cagr_n.notna().any() else 0.0) * 100))
if _cagr_hi <= _cagr_lo:
    _cagr_hi = _cagr_lo + 1.0
min_cagr = st.sidebar.slider(
    "Min CAGR ≥", min_value=_cagr_lo, max_value=_cagr_hi, value=_cagr_lo, step=1.0, format="%g%%",
    help="Hide runs whose CAGR is below this. Far left = off (show all).")

_dd_lo = float(math.floor((_dd_n.min() if _dd_n.notna().any() else 0.0) * 100))
if _dd_lo >= 0:
    _dd_lo = -1.0
max_dd_floor = st.sidebar.slider(
    "Worst Max DD allowed", min_value=_dd_lo, max_value=0.0, value=_dd_lo, step=1.0, format="%g%%",
    help="Hide runs with a drawdown worse (more negative) than this. Far left = off (allow any).")

_cal_lo = float(min(0.0, _cal_n.min())) if _cal_n.notna().any() else 0.0
_cal_hi = float(_cal_n.max()) if _cal_n.notna().any() else 1.0
_cal_lo, _cal_hi = round(_cal_lo, 2), round(max(_cal_hi, _cal_lo + 0.1), 2)
min_calmar = st.sidebar.slider(
    "Min Calmar ≥", min_value=_cal_lo, max_value=_cal_hi, value=_cal_lo, step=0.05,
    help="Hide runs with Calmar (CAGR ÷ |Max DD|) below this. Far left = off. "
         "This is usually the most useful single screen.")

# ── Structure — the big dimensions you usually pick first.
st.sidebar.caption("**Structure**")
delta_opts = sorted(df["delta_disp"].unique().tolist(),
                    key=lambda s: float(s.rstrip("Δ")) if s != "—" else 10**9)
sel_delta = st.sidebar.multiselect("Short delta", delta_opts, default=delta_opts,
    help="Short-strike delta target. Lower delta = further out-of-the-money: "
         "higher win rate and shallower drawdowns, but less premium collected.")
width_options = sorted(df["in_spread_width"].dropna().unique().tolist())
selected_widths = st.sidebar.multiselect("Spread width", width_options, default=width_options,
    help="Spread width in points; collateral per contract = width × \\$100.")
capstart_opts = sorted(df["start_disp"].unique().tolist(),
                       key=lambda s: int(s.strip("$k")) if s.strip("$k").isdigit() else 10**9)
sel_start = st.sidebar.multiselect("Starting capital", capstart_opts, default=capstart_opts,
    help="Account size at the start of the backtest.")

# ── Sizing (the risk dial).
st.sidebar.caption("**Sizing (cap = risk dial)**")
_prof_order = ["Conservative", "Cautious", "Moderate", "Aggressive", "Maximum"]
prof_opts = [p for p in _prof_order if p in df["risk_profile"].unique().tolist()]
sel_prof = st.sidebar.multiselect("Risk profile", prof_opts, default=prof_opts,
    help="Plain-language tier from the weekly \\$ cap: Conservative (\\$20k), Cautious (\\$30k), "
         "Moderate (\\$50k), Aggressive (\\$75k), Maximum (uncapped).")
cap_opts = sorted(df["cap_disp"].unique().tolist(),
                  key=lambda s: int(s.strip("$k")) if s.startswith("$") else 10**9)
sel_cap = st.sidebar.multiselect("Max weekly risk (cap)", cap_opts, default=cap_opts,
    help="The hard $ ceiling on weekly risk — the risk dial. 'Uncapped' rides "
         "the full weekly-risk % the whole way.")
risk_opts = sorted(df["risk_pct_disp"].unique().tolist())
sel_risk = st.sidebar.multiselect("Weekly risk %", risk_opts, default=risk_opts,
    help="% of the account at risk each week (50% is the standard).")

# ── Strategy.
st.sidebar.caption("**Strategy**")
ma_options = sorted(df["trend_ma_display"].unique().tolist())
selected_mas = st.sidebar.multiselect("Trend filter MA", ma_options, default=ma_options)

# ── Withdrawals.
st.sidebar.caption("**Withdrawals**")
withdrawals_filter = st.sidebar.radio(
    "Withdrawals", options=["Any", "On only", "Off only"], index=0, horizontal=True)
target_opts = sorted([t for t in df["target_disp"].unique().tolist() if t != "—"],
                     key=lambda s: int("".join(ch for ch in s if ch.isdigit()) or 10**9))
sel_targets = st.sidebar.multiselect("Withdrawal target", target_opts, default=target_opts,
    help="Monthly income target — applies to withdrawal runs only; "
         "no-withdrawal runs always pass through.")

# ─────────────────────────────────────────────────────────────────────────
# Apply filters
# ─────────────────────────────────────────────────────────────────────────
filtered = df.copy()
# Performance screen — each bites only when moved off its open end.
if min_cagr > _cagr_lo:
    filtered = filtered[pd.to_numeric(filtered["kpi_cagr"], errors="coerce") * 100 >= min_cagr]
if max_dd_floor > _dd_lo:
    filtered = filtered[pd.to_numeric(filtered["kpi_max_dd_pct"], errors="coerce") * 100 >= max_dd_floor]
if min_calmar > _cal_lo:
    filtered = filtered[pd.to_numeric(filtered["kpi_calmar"], errors="coerce") >= min_calmar]
# Config filters.
if sel_delta:
    filtered = filtered[filtered["delta_disp"].isin(sel_delta)]
if selected_widths:
    filtered = filtered[filtered["in_spread_width"].isin(selected_widths)]
if sel_start:
    filtered = filtered[filtered["start_disp"].isin(sel_start)]
if sel_prof:
    filtered = filtered[filtered["risk_profile"].isin(sel_prof)]
if sel_cap:
    filtered = filtered[filtered["cap_disp"].isin(sel_cap)]
if sel_risk:
    filtered = filtered[filtered["risk_pct_disp"].isin(sel_risk)]
if selected_mas:
    filtered = filtered[filtered["trend_ma_display"].isin(selected_mas)]
if withdrawals_filter == "On only":
    filtered = filtered[filtered["in_withdrawals_on"] == True]
elif withdrawals_filter == "Off only":
    filtered = filtered[filtered["in_withdrawals_on"] == False]
# Withdrawal target — applies to WD runs only; NW runs always pass through.
if target_opts and sel_targets and len(sel_targets) < len(target_opts):
    filtered = filtered[(filtered["in_withdrawals_on"] != True)
                        | filtered["target_disp"].isin(sel_targets)]

_count_slot.caption(f"**{len(filtered)} of {len(df)}** runs shown")

# ─────────────────────────────────────────────────────────────────────────
# Top-line context strip (renders in the main area, just under the title)
# ─────────────────────────────────────────────────────────────────────────
_widths = "/".join(str(int(w)) for w in sorted(df["in_spread_width"].dropna().unique()))
_scope = (f"**{len(df)}** runs" if len(filtered) == len(df)
          else f"**{len(filtered)}** of {len(df)} runs")
_strip = (f"{_scope}  ·  **{filtered['start_disp'].nunique()}** capital tiers  ·  widths {_widths}  ·  "
          f"{pd.to_datetime(df['in_backtest_start'].min()).date()} → "
          f"{pd.to_datetime(df['in_backtest_end'].max()).date()}")
_fc_strip = pd.to_numeric(filtered["kpi_cagr"], errors="coerce")
_fd_strip = pd.to_numeric(filtered["kpi_max_dd_pct"], errors="coerce")
if _fc_strip.notna().any():
    _strip += (f"  ·  median CAGR **{_fc_strip.median()*100:.1f}%**"
               f"  ·  median Max DD **{_fd_strip.median()*100:.1f}%**")
st.markdown(_strip)

# ─────────────────────────────────────────────────────────────────────────
# Best-in-class callouts (NaN-safe)
# ─────────────────────────────────────────────────────────────────────────
def _best(col, want_max=True):
    s = filtered[col].dropna()
    if s.empty:
        return None
    return filtered.loc[s.idxmax() if want_max else s.idxmin()]

def _card(container, title, row, value_fn, sub_fn=None):
    with container:
        if row is None:
            st.metric(title, "—")
        else:
            rid = int(row["run_id"])
            st.metric(title, value_fn(row), help=str(row["run_label"] or "").replace("$", "\\$"))
            if sub_fn:
                # escape $ so dollar amounts in the subtext don't render as LaTeX math
                st.caption(sub_fn(row).replace("$", "\\$"))   # the other two metrics, smaller
            st.markdown(f"[Run #{rid} →](Run_Detail?run_id={rid})")

# NaN-safe formatters for the parenthetical "other two metrics" shown on each card.
def _r2(v):    return "—" if pd.isna(v) else f"{float(v):.2f}"          # ratio (Calmar)
def _pct(v):   return "—" if pd.isna(v) else f"{float(v) * 100:.2f}%"   # CAGR / Max DD
def _money(v): return "—" if pd.isna(v) else f"${float(v):,.0f}"       # $ amounts (avg win/loss)

if not filtered.empty:
    explain("summary_cards", "ⓘ  About these cards")
    # Each headline card also shows the OTHER two of {CAGR, Calmar, Max DD} for that same
    # run, smaller, since the best on one metric usually trades off the others.
    a1, a2, a3 = st.columns(3)
    _card(a1, "Best CAGR",     _best("kpi_cagr"),       lambda r: f"{r['kpi_cagr']:.2%}",
          lambda r: f"(Calmar {_r2(r['kpi_calmar'])}, Max DD {_pct(r['kpi_max_dd_pct'])})")
    _card(a2, "Best Calmar",   _best("kpi_calmar"),     lambda r: f"{r['kpi_calmar']:.2f}",
          lambda r: f"(CAGR {_pct(r['kpi_cagr'])}, Max DD {_pct(r['kpi_max_dd_pct'])})")
    _card(a3, "Lowest Max DD", _best("kpi_max_dd_pct"), lambda r: f"{r['kpi_max_dd_pct']:.2%}",
          lambda r: f"(CAGR {_pct(r['kpi_cagr'])}, Calmar {_r2(r['kpi_calmar'])})")

    b1, b2, b3 = st.columns(3)
    _card(b1, "Best Sharpe",        _best("kpi_sharpe"),        lambda r: f"{r['kpi_sharpe']:.2f}")
    _card(b2, "Best Sortino",       _best("kpi_sortino"),       lambda r: f"{r['kpi_sortino']:.2f}")
    _card(b3, "Best Profit Factor", _best("kpi_profit_factor"), lambda r: f"{r['kpi_profit_factor']:.2f}")

    # Win/loss profile cards — the "small wins, big losses" shape
    c1, c2, c3 = st.columns(3)
    _card(c1, "Highest Win Rate",    _best("kpi_win_rate"),       lambda r: f"{r['kpi_win_rate']:.2%}",
          lambda r: f"(W/L {_r2(r['kpi_win_loss_ratio'])}, Avg Loss {_money(r['kpi_avg_loss'])})")
    _card(c2, "Best Win/Loss Ratio", _best("kpi_win_loss_ratio"), lambda r: f"{r['kpi_win_loss_ratio']:.2f}",
          lambda r: f"(Avg Win {_money(r['kpi_avg_win'])}, Avg Loss {_money(r['kpi_avg_loss'])})")
    _card(c3, "Smallest Worst Loss", _best("kpi_biggest_loss"),   lambda r: f"${r['kpi_biggest_loss']:,.0f}",
          lambda r: f"(CAGR {_pct(r['kpi_cagr'])}, Width ${int(float(r['in_spread_width']))})")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Scatter: CAGR vs Max Drawdown, colored by trend MA (filter-off is its own series).
# Click a dot to drill in (via on_select — Plotly dots can't be direct hyperlinks).
# ─────────────────────────────────────────────────────────────────────────
st.subheader("CAGR vs Max Drawdown")
explain("summary_scatter")
chart_df = filtered.copy()
# DB numerics arrive as object/Decimal; coerce so Plotly gets clean floats and NULLs
# (e.g. a degenerate run that took no trades) become NaN rather than crashing.
for _c in ("kpi_max_dd_pct", "kpi_cagr", "kpi_calmar"):
    chart_df[_c] = pd.to_numeric(chart_df[_c], errors="coerce")
# Size by Calmar, but clip ≥ 0 so a (hypothetical) negative Calmar can't break Plotly sizing.
chart_df["_size"] = chart_df["kpi_calmar"].clip(lower=0.01).fillna(0.01).astype(float)
plot_df = chart_df.dropna(subset=["kpi_max_dd_pct", "kpi_cagr"])

_sel_rids = []
if plot_df.empty:
    st.info("No runs with completed trades to plot. These scenarios recorded **0 trades** — "
            "the most common cause is a cap too small to afford one spread at the "
            "chosen width (e.g. a low start% at the \\$200 width, where the cap stays under "
            "\\$20k — one contract — until equity grows).")
else:
    # Order the trend-MA legend: filter-off first, then ema's and sma's by ascending period.
    def _ma_key(s):
        if s == OFF_LABEL:
            return (0, "", 0)
        pre, _, rest = s.partition("_")
        num = ""
        for ch in rest:
            if ch.isdigit():
                num += ch
            else:
                break
        return (1, pre, int(num) if num else 0, s)
    _ma_order = sorted(plot_df["trend_ma_display"].unique().tolist(), key=_ma_key)
    fig = px.scatter(
        plot_df,
        x="kpi_max_dd_pct",
        y="kpi_cagr",
        color="trend_ma_display",
        category_orders={"trend_ma_display": _ma_order},
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

    # Efficient frontier: runs where nothing else has BOTH higher CAGR and a
    # less-negative Max DD. Drawn as a dotted line through the Pareto-optimal points.
    _pf = plot_df[["kpi_max_dd_pct", "kpi_cagr"]].dropna().sort_values(
        ["kpi_max_dd_pct", "kpi_cagr"], ascending=[False, False])
    _front, _best = [], float("-inf")
    for _, _r in _pf.iterrows():
        if _r["kpi_cagr"] > _best:
            _front.append((_r["kpi_max_dd_pct"], _r["kpi_cagr"])); _best = _r["kpi_cagr"]
    if len(_front) >= 2:
        _front.sort(key=lambda p: p[0])
        fig.add_trace(go.Scatter(
            x=[p[0] for p in _front], y=[p[1] for p in _front], mode="lines",
            line=dict(color="rgba(220,220,220,0.65)", width=2, dash="dot"),
            name="Efficient frontier", hoverinfo="skip"))

    # Legend entry for the dashed Calmar rays (drawn as shapes below — no auto-legend).
    fig.add_trace(go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color="rgba(130,170,210,0.8)", width=1, dash="dash"),
        name="Calmar rays", hoverinfo="skip"))

    # SPX buy-and-hold benchmark over the runs' window (price return, from SPX_Daily_MAs).
    _spx_cagr = _spx_dd = None
    try:
        _spx = load_spx_daily().copy()
        _bs, _be = df["in_backtest_start"].min(), df["in_backtest_end"].max()
        _sd = pd.to_datetime(_spx["trade_date"])
        _spx = _spx[(_sd >= pd.Timestamp(_bs)) & (_sd <= pd.Timestamp(_be))].sort_values("trade_date")
        _cl = pd.to_numeric(_spx["spx_close"], errors="coerce").dropna().reset_index(drop=True)
        _yrs = max((pd.Timestamp(_be) - pd.Timestamp(_bs)).days / 365.25, 0.01)
        if len(_cl) > 1:
            _spx_cagr = (float(_cl.iloc[-1]) / float(_cl.iloc[0])) ** (1 / _yrs) - 1
            _spx_dd = float((_cl / _cl.cummax() - 1).min())
    except Exception:
        _spx_cagr = _spx_dd = None
    if _spx_cagr is not None:
        fig.add_trace(go.Scatter(
            x=[_spx_dd], y=[_spx_cagr], mode="markers+text",
            marker=dict(symbol="star", size=20, color="gold", line=dict(color="black", width=1)),
            text=["SPX"], textposition="top center", name="SPX buy &amp; hold",
            hovertemplate=f"SPX buy-and-hold<br>CAGR {_spx_cagr:.2%} · Max DD {_spx_dd:.2%}<extra></extra>"))

    # Iso-Calmar reference rays. On this chart Calmar = CAGR / |Max DD| = the slope of
    # the line from the origin to a point, so a constant-Calmar locus is a ray from
    # (0,0); a dot steeper/above a ray beats that Calmar. Drawn as shapes (layer below)
    # and clipped to the data box (incl. the SPX point) so they never rescale the axes.
    _x_lo = min(float(plot_df["kpi_max_dd_pct"].min()), _spx_dd if _spx_dd is not None else 0.0)
    _y_hi = max(float(plot_df["kpi_cagr"].max()), _spx_cagr if _spx_cagr is not None else 0.0)
    _y_lo = min(0.0, float(plot_df["kpi_cagr"].min()))
    # (_c, label-fraction): the fraction staggers each label down its ray so the
    # steep rays (which all exit near the top edge) don't pile their labels together.
    for _c, _lf in ((0.25, 0.92), (0.5, 0.85), (0.75, 0.66), (1.0, 0.5)):
        # endpoint where ray y = -_c*x exits the data box (left edge or top edge)
        if -_c * _x_lo <= _y_hi:
            _ex, _ey = _x_lo, -_c * _x_lo
        else:
            _ex, _ey = -_y_hi / _c, _y_hi
        fig.add_shape(type="line", x0=0, y0=0, x1=_ex, y1=_ey,
                      xref="x", yref="y", layer="below",
                      line=dict(color="rgba(130,170,210,0.35)", width=1, dash="dash"))
        fig.add_annotation(x=_lf * _ex, y=_lf * _ey, text=f"Calmar {_c:g}", showarrow=False,
                           font=dict(size=10, color="rgba(150,185,215,0.95)"),
                           bgcolor="rgba(14,17,23,0.55)")
    fig.update_xaxes(range=[_x_lo * 1.07, 0.006])
    fig.update_yaxes(range=[_y_lo - 0.012, _y_hi * 1.10])

    # Performance-screen acceptance box: shade the CAGR/DD region the sidebar sliders
    # are KEEPING (only drawn when one of those two screens is active). The Min Calmar
    # screen is a ray, so it isn't boxed — compare it against the dashed Calmar rays.
    if (min_cagr > _cagr_lo) or (max_dd_floor > _dd_lo):
        _box_x0 = max(max_dd_floor / 100.0, _x_lo * 1.07) if max_dd_floor > _dd_lo else _x_lo * 1.07
        _box_y0 = max(min_cagr / 100.0, _y_lo - 0.012) if min_cagr > _cagr_lo else _y_lo - 0.012
        fig.add_shape(type="rect", x0=_box_x0, x1=0.006, y0=_box_y0, y1=_y_hi * 1.10,
                      xref="x", yref="y", layer="below",
                      fillcolor="rgba(80,200,120,0.10)", line=dict(color="rgba(80,200,120,0.45)", width=1))

    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                            selection_mode=["points", "box", "lasso"], key="scatter_select")

    _sel_pts = []
    try:
        _sel_pts = event["selection"]["points"]
    except (TypeError, KeyError):
        _sel_pts = []
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
        st.caption(
            "- Click a dot to open its detail.\n"
            "- Shift-click more dots — or use the box / lasso tools at the chart's top-right — to select several.\n"
            "- With two or more selected, a **Compare** link appears here.\n"
            "- The dashed rays are constant-Calmar lines (see ⓘ above)."
        )

    if _spx_cagr is not None:
        st.caption(
            f"★ **SPX buy & hold** this period: CAGR {_spx_cagr*100:.1f}%, "
            f"Max DD {_spx_dd*100:.1f}% (price return, excl. dividends).\n\n"
            "Points up and to the right of the gold ★ beat the index on **both** return and drawdown."
        )

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Breakdowns — one row per category, across several dimensions (tabbed).
# ─────────────────────────────────────────────────────────────────────────
st.subheader("Breakdowns")
explain("summary_breakdowns")

_AGG_COLS = ("kpi_cagr", "kpi_max_dd_pct", "kpi_calmar", "kpi_sharpe",
             "kpi_avg_loss", "kpi_win_loss_ratio")

def _rollup(frame, dim_col, dim_label):
    """One row per distinct value of dim_col with the standard metric set."""
    d = frame.copy()
    for _c in _AGG_COLS:
        d[_c] = pd.to_numeric(d[_c], errors="coerce")
    return (d.groupby(dim_col)
              .agg(Runs=("run_id", "count"),
                   MedCAGR=("kpi_cagr", "median"),
                   BestCAGR=("kpi_cagr", "max"),
                   MedMaxDD=("kpi_max_dd_pct", "median"),
                   MedCalmar=("kpi_calmar", "median"),
                   BestCalmar=("kpi_calmar", "max"),
                   BestSharpe=("kpi_sharpe", "max"),
                   MedAvgLoss=("kpi_avg_loss", "median"),
                   MedWL=("kpi_win_loss_ratio", "median"))
              .reset_index().rename(columns={dim_col: dim_label}))

def _render_rollup(tbl, dim_label, caption):
    tbl = tbl.copy()
    for _c in ("MedCAGR", "BestCAGR", "MedMaxDD"):
        tbl[_c] = tbl[_c] * 100
    st.dataframe(
        tbl, use_container_width=True, hide_index=True,
        height=int((len(tbl) + 1) * 35 + 3),
        column_config={
            dim_label:    st.column_config.TextColumn(dim_label),
            "Runs":       st.column_config.NumberColumn("Runs", format="%,d"),
            "MedCAGR":    st.column_config.NumberColumn("Median CAGR", format="%.1f%%"),
            "BestCAGR":   st.column_config.NumberColumn("Best CAGR", format="%.1f%%"),
            "MedMaxDD":   st.column_config.NumberColumn("Median Max DD", format="%.1f%%"),
            "MedCalmar":  st.column_config.NumberColumn("Median Calmar", format="%.2f"),
            "BestCalmar": st.column_config.NumberColumn("Best Calmar", format="%.2f"),
            "BestSharpe": st.column_config.NumberColumn("Best Sharpe", format="%.2f"),
            "MedAvgLoss": st.column_config.NumberColumn("Median Avg Loss", format="$%,.0f"),
            "MedWL":      st.column_config.NumberColumn("Median W/L", format="%.2f",
                          help="Median win/loss ratio = avg win ÷ |avg loss|. Below 1 = wins smaller than losses (the norm here)."),
        })
    st.caption(caption)

if filtered.empty:
    st.caption("No runs in the current filter.")
else:
    _tab_d, _tab_w, _tab_cap, _tab_risk, _tab_trend, _tab_wd = st.tabs(
        ["Short delta", "Spread width", "Starting capital", "Max weekly risk", "Trend filter", "Withdrawals"])

    with _tab_d:
        _t = _rollup(filtered, "delta_disp", "Short delta")
        _t["_k"] = _t["Short delta"].map(lambda s: float(s.rstrip("Δ")) if s != "—" else 10**9)
        _render_rollup(_t.sort_values("_k").drop(columns="_k"), "Short delta",
            "One row per short-strike delta target. Lower delta sells further out-of-the-money — "
            "higher win rate and shallower drawdowns, but less premium, so lower CAGR; higher "
            "delta is the reverse trade-off.")

    with _tab_w:
        _t = _rollup(filtered, "width_disp", "Width")
        _t["_k"] = _t["Width"].str.replace("$", "", regex=False).astype(float)
        _render_rollup(_t.sort_values("_k").drop(columns="_k"), "Width",
            "One row per spread width across the filtered set. Wider spreads carry more premium "
            "per unit of width but need proportionally more capital per contract (width × \\$100).")

    with _tab_cap:
        _t = _rollup(filtered, "start_disp", "Starting capital")
        _t["_k"] = _t["Starting capital"].str.strip("$k").astype(float)
        _render_rollup(_t.sort_values("_k").drop(columns="_k"), "Starting capital",
            "One row per starting account size. Larger accounts hold more contracts at a given "
            "width, so they trade more smoothly (fewer 1-contract quantization jumps).")

    with _tab_risk:
        _t = _rollup(filtered, "cap_disp", "Max weekly risk")
        _t["_k"] = _t["Max weekly risk"].map(lambda s: int(s.strip("$k")) if s.startswith("$") else 10**9)
        _render_rollup(_t.sort_values("_k").drop(columns="_k"), "Max weekly risk",
            "One row per weekly-risk cap (the risk dial). Tighter caps de-risk sooner — lower CAGR, "
            "shallower drawdowns; 'Uncapped' rides the full weekly-risk % the whole way.")

    with _tab_trend:
        _t = _rollup(filtered, "trend_ma_display", "Trend MA")
        _render_rollup(_t.sort_values("MedCalmar", ascending=False), "Trend MA",
            "One row per trend-filter MA — each MA spans the same configs, so it's apples-to-apples. "
            "Sorted by Median Calmar: faster filters (ema_9, short SMAs) lead; the slow 50>200 regime trails.")

    with _tab_wd:
        _t = _rollup(filtered, "wd_disp", "Withdrawals")
        _t["_k"] = _t["Withdrawals"].map({"Off": 0, "On": 1}).fillna(2)
        _render_rollup(_t.sort_values("_k").drop(columns="_k"), "Withdrawals",
            "No-withdrawal vs withdrawal runs. WD runs trade the same engine but pull a monthly "
            "income — compare their CAGR / Calmar against the NW baseline.")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Leaderboard
# ─────────────────────────────────────────────────────────────────────────
st.subheader("Leaderboard")
explain("summary_leaderboard")

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
    "Win/Loss Ratio (desc)": ("kpi_win_loss_ratio",  False),
    "Avg Loss (least bad)":  ("kpi_avg_loss",        False),
    "Worst Loss (least bad)": ("kpi_biggest_loss",   False),
}
sort_label = st.selectbox("Sort by", list(sort_options.keys()))
sort_col, sort_asc = sort_options[sort_label]
sorted_df = filtered.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

# Clickable drill-in: the Run # cell is a link to the Run Detail page.
sorted_df["drill_url"] = "Run_Detail?run_id=" + sorted_df["run_id"].astype(str)

display_cols = [
    "drill_url", "risk_profile", "run_label", "trend_ma_display", "in_spread_width",
    "kpi_ending_equity", "kpi_cagr", "kpi_xirr", "kpi_max_dd_pct", "kpi_calmar",
    "kpi_ann_return_stdev", "kpi_sharpe", "kpi_sortino",
    "kpi_total_trades", "kpi_win_rate", "kpi_profit_factor",
    "kpi_avg_win", "kpi_avg_loss", "kpi_win_loss_ratio", "kpi_biggest_loss",
]
view = sorted_df[display_cols].copy()
view.columns = [
    "Run #", "Profile", "Label", "Trend MA", "Width",
    "Ending Equity", "CAGR", "XIRR", "Max DD", "Calmar",
    "Ann Vol", "Sharpe", "Sortino",
    "Trades", "Win Rate", "PF",
    "Avg Win", "Avg Loss", "W/L", "Worst Loss",
]
# Pre-multiply ratio columns by 100 so the % format renders as "14.32%" not "0.14%".
for pct_col in ("CAGR", "XIRR", "Max DD", "Win Rate", "Ann Vol"):
    view[pct_col] = view[pct_col] * 100.0

st.dataframe(
    view,
    use_container_width=True,
    hide_index=True,
    height=500,
    column_config={
        "Run #":         st.column_config.LinkColumn("Run #", display_text=r"run_id=(\d+)", width="small"),
        "Ending Equity": st.column_config.NumberColumn(format="$%,.0f"),
        "Trades":        st.column_config.NumberColumn(format="%,d"),
        "CAGR":          st.column_config.NumberColumn(format="%.2f%%"),
        "XIRR":          st.column_config.NumberColumn(format="%.2f%%",
                         help="Money-weighted return (IRR of the cash flows). Equals CAGR for "
                              "non-withdrawal runs; credits withdrawals for WD runs."),
        "Max DD":        st.column_config.NumberColumn(format="%.2f%%"),
        "Calmar":        st.column_config.NumberColumn(format="%.2f"),
        "Ann Vol":       st.column_config.NumberColumn(format="%.2f%%"),
        "Sharpe":        st.column_config.NumberColumn(format="%.2f"),
        "Sortino":       st.column_config.NumberColumn(format="%.2f"),
        "Win Rate":      st.column_config.NumberColumn(format="%.2f%%"),
        "PF":            st.column_config.NumberColumn(format="%.2f"),
        "Avg Win":       st.column_config.NumberColumn(format="$%,.0f"),
        "Avg Loss":      st.column_config.NumberColumn(format="$%,.0f"),
        "W/L":           st.column_config.NumberColumn(format="%.2f",
                         help="Avg win ÷ |avg loss| — below 1 means each win is smaller than each loss."),
        "Worst Loss":    st.column_config.NumberColumn(format="$%,.0f"),
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
sell a put at the chosen short delta (5Δ / 10Δ / 15Δ / 20Δ — 10Δ is the core), buy the put
\\$10–\\$200 lower, hold to expiration with optional breach and 1-DTE close rules. Position sizing is **simple and capped**: risk a set % of the
account each week (default 50%), never more than a hard dollar ceiling —
`weekly risk = MIN(weekly_risk_pct × equity, max_weekly_risk)`. The cap is the risk dial:
tighter de-risks sooner; uncapped rides the full % the whole way.

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

render_footer()
