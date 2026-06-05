"""StrategyXL — SPX 7 DTE Put Credit Spread backtest dashboard.

Overview page: best-in-class callouts, sortable leaderboard, scatter chart,
sidebar filters. Click a run's number in the leaderboard to drill in.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data.db import load_scenario_runs, load_spx_daily, check_password_gate, render_footer
from data.docs import explain, guide_link

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

# Group code = leading token of the run label ( |CODE|... e.g. RE50-WD ).
df["group"] = df["run_label"].str.extract(r"^\|([^|]*)\|")[0].fillna("(ungrouped)")
# Sizing dimensions as friendly display strings (DB values arrive as Decimal).
_up = pd.to_numeric(df["in_upside_reinvest_pct"],    errors="coerce").fillna(0)
_mg = pd.to_numeric(df["in_max_gross_pct_equity"],   errors="coerce").fillna(0)
_ac = pd.to_numeric(df["in_gross_cap_activation_eq"], errors="coerce").fillna(0)
df["reinv_disp"] = (_up * 100).round().astype(int).astype(str) + "%"
df["maxg_disp"]  = (_mg * 100).round().astype(int).astype(str) + "%"
df["activ_disp"] = "$" + (_ac / 1000).round().astype(int).astype(str) + "k"
_sc = pd.to_numeric(df["in_starting_capital"], errors="coerce").fillna(0)
df["start_disp"] = "$" + (_sc / 1000).round().astype(int).astype(str) + "k"

# ─────────────────────────────────────────────────────────────────────────
# Sidebar filters
# ─────────────────────────────────────────────────────────────────────────
st.sidebar.header("Filters")

group_opts = sorted(df["group"].unique().tolist())
sel_groups = st.sidebar.multiselect(
    "Group", group_opts, default=group_opts,
    help="Sizing/withdrawal regime from the run label, e.g. RE50-WD "
         "(RE50 = 50% upside reinvest; WD = withdrawals on; NW = none). "
         "FIX = fixed base sizing, no reinvest.")

st.sidebar.caption("**Sizing**")
reinv_opts = sorted(df["reinv_disp"].unique().tolist(), key=lambda s: int(s.rstrip("%")))
sel_reinv = st.sidebar.multiselect("Upside reinvest %", reinv_opts, default=reinv_opts)
maxg_opts = sorted(df["maxg_disp"].unique().tolist(), key=lambda s: int(s.rstrip("%")))
sel_maxg = st.sidebar.multiselect("Max gross % of equity", maxg_opts, default=maxg_opts)
activ_opts = sorted(df["activ_disp"].unique().tolist(), key=lambda s: int(s.strip("$k")))
sel_activ = st.sidebar.multiselect("Gross-cap activation", activ_opts, default=activ_opts)
start_opts = sorted(df["start_disp"].unique().tolist(), key=lambda s: int(s.strip("$k")))
sel_start = st.sidebar.multiselect("Starting capital", start_opts, default=start_opts,
    help="Distinguishes same-regime groups that differ only by account size "
         "(e.g. RE50-WD at $40k vs $100k).")

st.sidebar.caption("**Strategy**")
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
if sel_groups:
    filtered = filtered[filtered["group"].isin(sel_groups)]
if sel_reinv:
    filtered = filtered[filtered["reinv_disp"].isin(sel_reinv)]
if sel_maxg:
    filtered = filtered[filtered["maxg_disp"].isin(sel_maxg)]
if sel_activ:
    filtered = filtered[filtered["activ_disp"].isin(sel_activ)]
if sel_start:
    filtered = filtered[filtered["start_disp"].isin(sel_start)]
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
# Top-line context strip (renders in the main area, just under the title)
# ─────────────────────────────────────────────────────────────────────────
_widths = "/".join(str(int(w)) for w in sorted(df["in_spread_width"].dropna().unique()))
_scope = (f"**{len(df)}** runs" if len(filtered) == len(df)
          else f"**{len(filtered)}** of {len(df)} runs")
_strip = (f"{_scope}  ·  **{filtered['group'].nunique()}** groups  ·  widths {_widths}  ·  "
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
            st.metric(title, value_fn(row), help=str(row["run_label"] or ""))
            if sub_fn:
                st.caption(sub_fn(row))   # the other two metrics, smaller; wraps (no arrow/clipping)
            st.markdown(f"[Run #{rid} →](Run_Detail?run_id={rid})")

# NaN-safe formatters for the parenthetical "other two metrics" shown on each card.
def _r2(v):  return "—" if pd.isna(v) else f"{float(v):.2f}"          # ratio (Calmar)
def _pct(v): return "—" if pd.isna(v) else f"{float(v) * 100:.2f}%"   # CAGR / Max DD

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
            "the most common cause is a sizing input that caps weekly exposure to \\$0 "
            "(e.g. Max Gross % = 0 with Activation Equity = \\$0).")
else:
    fig = px.scatter(
        plot_df,
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
        st.caption("Tip: click a dot for its detail link. Shift-click more dots — or use the box/lasso "
                   "tools in the chart's top-right toolbar — to select several and compare.")

    if _spx_cagr is not None:
        st.caption(f"★ **SPX buy & hold** over this period: CAGR {_spx_cagr*100:.1f}%, "
                   f"Max DD {_spx_dd*100:.1f}% (price return, excl. dividends) — the gold ★ above. "
                   "Points up and to the right of it beat the index on both return and drawdown.")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Group summary — regime-level rollup (one row per group)
# ─────────────────────────────────────────────────────────────────────────
st.subheader("By group")
explain("summary_group")
if filtered.empty:
    st.caption("No runs in the current filter.")
else:
    _gd = filtered.copy()
    for _c in ("kpi_cagr", "kpi_max_dd_pct", "kpi_calmar", "kpi_sharpe"):
        _gd[_c] = pd.to_numeric(_gd[_c], errors="coerce")
    grp = (_gd.groupby("group")
              .agg(Runs=("run_id", "count"),
                   MedCAGR=("kpi_cagr", "median"),
                   BestCAGR=("kpi_cagr", "max"),
                   MedMaxDD=("kpi_max_dd_pct", "median"),
                   BestCalmar=("kpi_calmar", "max"),
                   BestSharpe=("kpi_sharpe", "max"))
              .reset_index().rename(columns={"group": "Group"})
              .sort_values("BestCalmar", ascending=False))
    for _c in ("MedCAGR", "BestCAGR", "MedMaxDD"):
        grp[_c] = grp[_c] * 100
    st.dataframe(
        grp, use_container_width=True, hide_index=True,
        height=int((len(grp) + 1) * 35 + 3),
        column_config={
            "Group":      st.column_config.TextColumn("Group"),
            "Runs":       st.column_config.NumberColumn("Runs", format="%d"),
            "MedCAGR":    st.column_config.NumberColumn("Median CAGR", format="%.1f%%"),
            "BestCAGR":   st.column_config.NumberColumn("Best CAGR", format="%.1f%%"),
            "MedMaxDD":   st.column_config.NumberColumn("Median Max DD", format="%.1f%%"),
            "BestCalmar": st.column_config.NumberColumn("Best Calmar", format="%.2f"),
            "BestSharpe": st.column_config.NumberColumn("Best Sharpe", format="%.2f"),
        })
    st.caption("One row per group across the filtered set — median = the typical run, "
               "best = the top run in that group. Sorted by Best Calmar.")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Trend-filter summary — one row per trend_filter_ma (incl. (filter off))
# ─────────────────────────────────────────────────────────────────────────
st.subheader("By trend filter")
if filtered.empty:
    st.caption("No runs in the current filter.")
else:
    _td = filtered.copy()
    for _c in ("kpi_cagr", "kpi_max_dd_pct", "kpi_calmar", "kpi_sharpe"):
        _td[_c] = pd.to_numeric(_td[_c], errors="coerce")
    tf = (_td.groupby("trend_ma_display")
             .agg(Runs=("run_id", "count"),
                  MedCAGR=("kpi_cagr", "median"),
                  MedMaxDD=("kpi_max_dd_pct", "median"),
                  MedCalmar=("kpi_calmar", "median"),
                  BestCalmar=("kpi_calmar", "max"),
                  BestSharpe=("kpi_sharpe", "max"))
             .reset_index().rename(columns={"trend_ma_display": "Trend MA"})
             .sort_values("MedCalmar", ascending=False))
    for _c in ("MedCAGR", "MedMaxDD"):
        tf[_c] = tf[_c] * 100
    st.dataframe(
        tf, use_container_width=True, hide_index=True,
        height=int((len(tf) + 1) * 35 + 3),
        column_config={
            "Trend MA":   st.column_config.TextColumn("Trend MA"),
            "Runs":       st.column_config.NumberColumn("Runs", format="%d"),
            "MedCAGR":    st.column_config.NumberColumn("Median CAGR", format="%.1f%%"),
            "MedMaxDD":   st.column_config.NumberColumn("Median Max DD", format="%.1f%%"),
            "MedCalmar":  st.column_config.NumberColumn("Median Calmar", format="%.2f"),
            "BestCalmar": st.column_config.NumberColumn("Best Calmar", format="%.2f"),
            "BestSharpe": st.column_config.NumberColumn("Best Sharpe", format="%.2f"),
        })
    st.caption("One row per trend-filter MA across the filtered set — each MA spans the same "
               "group×width configs, so this is apples-to-apples. Median = the typical run. "
               "Sorted by Median Calmar: faster filters (ema_9, short SMAs) lead; the slow "
               "50>200 regime trails.")

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

render_footer()
