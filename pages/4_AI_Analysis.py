"""AI Analysis — Claude's deep-dive findings across the full scenario grid.

Every chart on this page is computed LIVE from the runs database, so it stays
current as new batches land. The narrative conclusions come from the June 2026
delta-sweep study (matched-pair analysis across 4 × 988 scenarios) and from
dedicated exit-rule experiments run on the backtest engine.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from data.db import load_scenario_runs, check_password_gate, render_footer
from data.docs import md

st.set_page_config(page_title="AI Analysis — StrategyXL", page_icon="🤖", layout="wide")
check_password_gate()

st.title("AI Analysis")
st.caption("A guided tour of what ~4,000 backtested configurations actually say — by dimension, "
           "with the supporting data. Charts are computed live from the run database. "
           "Backtested results, not investment advice; past performance doesn't guarantee future returns.")

# ─────────────────────────────────────────────────────────────────────────
# Load + shared display columns
# ─────────────────────────────────────────────────────────────────────────
df = load_scenario_runs().copy()
if df.empty:
    st.warning("No scenarios in the database yet.")
    st.stop()

# Core grid only. The systematic factorial sweep is the production run (a full
# re-run lands it all in one batch). Ad-hoc reader/community runs — custom exits,
# off-grid caps/commissions — are tagged batch_id 9 and excluded here so they
# don't pollute the matched-pair medians and frontiers. They stay fully visible
# on the Leaderboard, Compare and Run Detail pages.
# Convention: after each full re-run, tag the ad-hoc runs (profit-target set,
# commission ≠ 0.65, or the $50w/$40k-cap requests) to batch_id 9.
ADHOC_BATCH_IDS = (9,)
df = df[~pd.to_numeric(df["batch_id"], errors="coerce").isin(ADHOC_BATCH_IDS)].copy()
if df.empty:
    st.warning("No core-grid scenarios in the database yet.")
    st.stop()

def _n(s):
    return pd.to_numeric(s, errors="coerce")

df["cagr"]   = _n(df["kpi_cagr"]) * 100
df["maxdd"]  = _n(df["kpi_max_dd_pct"]) * 100
df["calmar"] = _n(df["kpi_calmar"])
df["winr"]   = _n(df["kpi_win_rate"]) * 100
df["pf"]     = _n(df["kpi_profit_factor"])

_sd = _n(df["in_short_delta_threshold"])
df["delta_disp"] = _sd.map(lambda v: f"{v*100:g}Δ" if pd.notna(v) else "—")
_sw = _n(df["in_spread_width"])
df["width_disp"] = _sw.map(lambda v: f"${int(v)}" if pd.notna(v) else "—")
_sc = _n(df["in_starting_capital"]).fillna(0)
df["start_disp"] = "$" + (_sc / 1000).round().astype(int).astype(str) + "k"
_cap = _n(df["in_max_weekly_risk"])
df["cap_disp"] = _cap.map(lambda v: f"${v/1000:g}k" if pd.notna(v) else "Uncapped")
df["trend_disp"] = df["in_trend_filter_ma"].fillna("(filter off)")
_tw = _n(df["in_target_monthly_withdrawal"])
df["target_disp"] = _tw.map(lambda v: f"${int(round(v)):,}/mo" if pd.notna(v) and v > 0 else "—")

_DELTA_ORDER = [d for d in ("5Δ", "10Δ", "15Δ", "20Δ") if d in df["delta_disp"].unique()]
_DELTA_COLOR = {"5Δ": "#1D9E75", "10Δ": "#378ADD", "15Δ": "#EF9F27", "20Δ": "#E24B4A"}

nw = df[df["in_withdrawals_on"] != True]          # the apples-to-apples growth set
plot = df.dropna(subset=["cagr", "maxdd"])

md(f"**{len(df):,} runs** in the core grid — "
   f"{' / '.join(_DELTA_ORDER)} short deltas × widths "
   f"{'/'.join(s.strip('$') for s in sorted(df['width_disp'].unique(), key=lambda s: float(s.strip('$—') or 0) if s != '—' else 9e9))} "
   "× nine starting-capital tiers × the weekly-risk/cap grid × 13 trend-filter settings × "
   "withdrawal plans, 2007 → today.")

# ─────────────────────────────────────────────────────────────────────────
st.header("1 · The one-page playbook")
md(
    "If you read nothing else: **your drawdown tolerance picks your delta, your account size "
    "picks your width, and the weekly-risk cap sets how hard you push.** From the matched-pair "
    "study (every configuration run at all four deltas, everything else identical):\n\n"
    "| Your max-drawdown budget | Best tool for the job | What it earned (best in zone) |\n"
    "|---|---|--:|\n"
    "| up to ~−15% | **5Δ short + a fast trend filter** (5-day SMA) | ~12% CAGR |\n"
    "| ~−20% | **10Δ** — the balanced core strategy | ~16% CAGR |\n"
    "| ~−30% | **15Δ with no trend filter** | ~19% CAGR |\n"
    "| any budget | ~~20Δ~~ — dominated at every risk level | — |\n\n"
    "The scatter below is the whole grid; the dotted lines trace the best frontier of each "
    "delta. Notice where the colors take over from each other — that hand-off **is** the playbook."
)

_fig = px.scatter(
    plot, x="maxdd", y="cagr", color="delta_disp",
    category_orders={"delta_disp": _DELTA_ORDER},
    color_discrete_map=_DELTA_COLOR, opacity=0.30,
    labels={"maxdd": "Max drawdown (%)", "cagr": "CAGR (%)", "delta_disp": "Short delta"},
    hover_data={"run_label": True, "maxdd": ":.1f", "cagr": ":.1f"},
)
_fig.update_traces(marker=dict(size=5))
for _d in _DELTA_ORDER:
    _sub = plot[plot["delta_disp"] == _d][["maxdd", "cagr"]].dropna().sort_values(
        ["maxdd", "cagr"], ascending=[False, False])
    _front, _best = [], float("-inf")
    for _, _r in _sub.iterrows():
        if _r["cagr"] > _best:
            _front.append((_r["maxdd"], _r["cagr"])); _best = _r["cagr"]
    if len(_front) >= 2:
        _front.sort(key=lambda p: p[0])
        _fig.add_trace(go.Scatter(
            x=[p[0] for p in _front], y=[p[1] for p in _front], mode="lines",
            line=dict(color=_DELTA_COLOR.get(_d, "#888"), width=2, dash="dot"),
            name=f"{_d} frontier", hoverinfo="skip"))
_fig.update_layout(height=480, legend_title="Short delta", margin=dict(t=10, b=0, l=0, r=0))
st.plotly_chart(_fig, use_container_width=True)
st.caption("Each dot is one full 19-year backtest. Up and to the right is better. The frontiers "
           "cross: 5Δ (green) owns the shallow-drawdown zone, 10Δ (blue) the middle and the far "
           "right, 15Δ (amber) a band around −25% to −35%. 20Δ (red) never leads.")

# ─────────────────────────────────────────────────────────────────────────
st.header("2 · Short delta — the risk dial with a sweet spot")
md(
    "The short strike's delta is roughly the market's price of *\"how often does this option "
    "finish in trouble?\"* Selling closer to the money (higher delta) collects more premium but "
    "loses more often, and loses bigger. The medians across each complete 988-run set:"
)
_dt = (nw.groupby("delta_disp")
         .agg(Runs=("run_id", "count"), MedCAGR=("cagr", "median"), MedMaxDD=("maxdd", "median"),
              MedCalmar=("calmar", "median"), MedWinRate=("winr", "median"), MedPF=("pf", "median"))
         .reindex(_DELTA_ORDER).reset_index().rename(columns={"delta_disp": "Delta"}))
st.dataframe(_dt, hide_index=True, use_container_width=True,
             column_config={
                 "Runs": st.column_config.NumberColumn(format="%,d"),
                 "MedCAGR": st.column_config.NumberColumn("Median CAGR", format="%.1f%%"),
                 "MedMaxDD": st.column_config.NumberColumn("Median Max DD", format="%.1f%%"),
                 "MedCalmar": st.column_config.NumberColumn("Median Calmar", format="%.2f"),
                 "MedWinRate": st.column_config.NumberColumn("Median Win Rate", format="%.1f%%"),
                 "MedPF": st.column_config.NumberColumn("Median Profit Factor", format="%.2f"),
             })
md(
    "What the matched pairs showed (same scenario, only the delta changed):\n"
    "- **5Δ vs 10Δ:** gives up ~1½ points of CAGR but takes ~8 points *less* drawdown, and wins "
    "the risk-adjusted contest in the conservative zone outright. Win rate rises to ~93%.\n"
    "- **15Δ vs 10Δ:** adds only ~½ point of CAGR for ~3 points *more* drawdown — a poor trade "
    "on average, **except** in the no-filter aggressive zone, where it clearly leads (~19% CAGR "
    "at −32%).\n"
    "- **20Δ vs anything:** *dominated everywhere.* More drawdown than 15Δ and less return — "
    "median CAGR actually falls (premium gains are eaten by breaches getting bigger and more "
    "frequent), and no trend filter rescues it. **Selling closer to the money for \"more "
    "income\" is the single most clearly refuted idea in the study.**\n"
    "- Median CAGR **peaks at 15Δ and then falls** — the risk/return curve bends back past 15Δ. "
    "That's why the playbook stops there."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("3 · Trend filters — and why each delta wants a different one")
md(
    "A trend filter skips the week's entry when SPX closes below a chosen moving average. "
    "Its value depends on **what kind of trouble your delta is exposed to**, which produced the "
    "study's most interesting structural finding:\n"
    "- **5Δ needs a *fast* filter** (5–10-day): its risk is the sudden crash, and a fast MA "
    "steps aside quickest. Every top conservative run uses the 5-day SMA. Without any filter, "
    "5Δ keeps most of the drawdown it was supposed to avoid while still earning the smallest "
    "premium — the worst of both.\n"
    "- **15Δ wants a *slow* filter or none**: it gets paid to ride out frequent small dips. A "
    "fast filter whipsaws it — exits after every wobble, re-enters late, *and* still catches the "
    "fast crashes. Paired with ema_20/sma_10/sma_20 it took on **9–12 points more drawdown** "
    "than its 10Δ twin; paired with the 200-day SMA or the 50>200 regime it gained a full CAGR "
    "point at roughly flat drawdown.\n"
    "- **10Δ sits in between** and is the least filter-sensitive — the 9-day EMA and short SMAs "
    "have historically been steadiest.\n\n"
    "The heatmap shows median Calmar for every delta × filter pairing in the grid:"
)
_ord = ["(filter off)", "sma_5", "ema_9", "sma_10", "ema_20", "sma_20", "sma_50", "ema_50",
        "sma_100", "sma_150", "ema_200", "sma_200", "sma_50>200"]
_hm = (nw.groupby(["delta_disp", "trend_disp"])["calmar"].median().reset_index())
_hm = _hm.pivot(index="delta_disp", columns="trend_disp", values="calmar")
_hm = _hm.reindex(index=_DELTA_ORDER, columns=[c for c in _ord if c in _hm.columns])
_fig = px.imshow(_hm, text_auto=".2f", aspect="auto", color_continuous_scale="RdYlGn",
                 labels=dict(x="Trend filter (fast → slow)", y="Short delta", color="Median Calmar"))
_fig.update_layout(height=320, margin=dict(t=10, b=0, l=0, r=0), coloraxis_showscale=False)
st.plotly_chart(_fig, use_container_width=True)
st.caption("Greener = better risk-adjusted return (median Calmar). Read along each row: 5Δ is "
           "greenest at the fast end, 15Δ/20Δ improve toward the slow end and filter-off, 10Δ "
           "is the flattest row — robust to the choice.")

# ─────────────────────────────────────────────────────────────────────────
st.header("4 · Spread width — five different products")
md(
    "Width is **not** \"the same strategy, bigger\": each width needs `width × $100` of "
    "collateral per contract, so the *same* dollar account holds very different contract counts "
    "— and that changes the character of the equity curve.\n"
    "- **$10–$25 — the small-account widths.** One contract risks $1,000–$2,500, so a "
    "$10k–$25k account can size genuinely small. Paired with 5Δ these produce the smoothest "
    "curves in the whole grid (max drawdowns in single digits). The cost: modest CAGR.\n"
    "- **$50 — the growth sweet spot.** Big enough to earn real premium, small enough to size "
    "in steps on a $25k–$40k account. The best balanced configs in the grid (10Δ) and the best "
    "aggressive ones (15Δ) are nearly all $50-wide.\n"
    "- **$100–$200 — the smoothness widths.** On the capital they genuinely need ($80k–$160k+), "
    "they post the grid's highest Calmars at tiny drawdowns — capital-preservation tools more "
    "than growth engines.\n\n"
    "Median CAGR vs median drawdown by width and delta (no-withdrawal runs):"
)
_wt = (nw.groupby(["width_disp", "delta_disp"])
         .agg(MedCAGR=("cagr", "median"), MedMaxDD=("maxdd", "median"), Runs=("run_id", "count"))
         .reset_index())
_wt["_k"] = _wt["width_disp"].str.strip("$—").replace("", "0").astype(float)
_wt = _wt.sort_values("_k")
_fig = px.bar(_wt, x="width_disp", y="MedCAGR", color="delta_disp", barmode="group",
              category_orders={"delta_disp": _DELTA_ORDER,
                               "width_disp": _wt["width_disp"].unique().tolist()},
              color_discrete_map=_DELTA_COLOR,
              labels={"width_disp": "Spread width", "MedCAGR": "Median CAGR (%)",
                      "delta_disp": "Short delta"})
_fig.update_layout(height=380, margin=dict(t=10, b=0, l=0, r=0))
st.plotly_chart(_fig, use_container_width=True)
st.caption("Median CAGR by width × delta. The $50 width carries the highest medians for 10Δ/15Δ; "
           "the wide spreads trade CAGR for smoothness; the narrow ones depend heavily on delta.")

# ─────────────────────────────────────────────────────────────────────────
st.header("5 · Starting capital — match the width, mind the steps")
md(
    "Two things matter about account size:\n"
    "1. **It must match the width.** The account should comfortably hold *several* contracts "
    "at your width — one-contract accounts can't size down after losses (the next step below "
    "one contract is zero, a week off, which distorts the model).\n"
    "2. **Bigger accounts trade more smoothly.** More contracts = finer sizing steps = the "
    "weekly-risk % tracks its target instead of jumping. You can see it in the medians — at the "
    "same width, larger capital tiers show better Calmars before the cap even matters.\n\n"
    "Rules of thumb from the grid: **$5k–$20k → $10–$25 wide · ~$25k–$50k → $25–$50 · "
    "$80k+ → $100 · $160k+ → $200.**"
)
_ct = (nw.groupby(["start_disp", "width_disp"])
         .agg(MedCalmar=("calmar", "median"), Runs=("run_id", "count")).reset_index())
_ct["_k"] = _ct["start_disp"].str.strip("$k").astype(float)
_ct["_w"] = _ct["width_disp"].str.strip("$—").replace("", "0").astype(float)
_ct = _ct.sort_values(["_k", "_w"])
_fig = px.bar(_ct, x="start_disp", y="MedCalmar", color="width_disp", barmode="group",
              category_orders={"start_disp": _ct["start_disp"].unique().tolist(),
                               "width_disp": sorted(_ct["width_disp"].unique(), key=lambda s: float(s.strip("$—") or 0))},
              labels={"start_disp": "Starting capital", "MedCalmar": "Median Calmar",
                      "width_disp": "Width"})
_fig.update_layout(height=380, margin=dict(t=10, b=0, l=0, r=0))
st.plotly_chart(_fig, use_container_width=True)
st.caption("Median Calmar by starting capital × width. Each capital tier has a width 'home' "
           "where risk-adjusted return is best — capital and width are one decision, not two.")

# ─────────────────────────────────────────────────────────────────────────
st.header("6 · The weekly-risk cap — what saves the later years")
md(
    "Sizing is `weekly risk = MIN(risk % × equity, cap)`. The cap is the master risk dial, and "
    "it has a specific *time signature*: **early on, when the account is small, the cap doesn't "
    "bind** — every cap level rides the same ~50% of equity, so the GFC-era drawdowns look "
    "identical. The cap earns its keep **later**, once the account has grown: tighter caps held "
    "exposure flat through 2018, 2020 and 2022 while uncapped runs rode them at full size.\n\n"
    "Turning only the cap (10Δ, $50 width, $40k start, 50% weekly risk, 5-day SMA, "
    "no withdrawals):"
)
_capset = nw[(nw["delta_disp"] == "10Δ") & (nw["width_disp"] == "$50")
             & (nw["start_disp"] == "$40k") & (nw["trend_disp"] == "sma_5")
             & (_n(nw["in_weekly_risk_pct"]) == 0.5)]
_cs = (_capset.groupby("cap_disp").agg(CAGR=("cagr", "median"), MaxDD=("maxdd", "median"),
                                       Calmar=("calmar", "median")).reset_index())
_cs["_k"] = _cs["cap_disp"].map(lambda s: float(s.strip("$k")) if s.startswith("$") else 9e9)
_cs = _cs.sort_values("_k")
_fig = go.Figure()
_fig.add_trace(go.Bar(x=_cs["cap_disp"], y=_cs["CAGR"], name="CAGR %", marker_color="#378ADD"))
_fig.add_trace(go.Bar(x=_cs["cap_disp"], y=_cs["MaxDD"], name="Max DD %", marker_color="#E24B4A"))
_fig.update_layout(height=360, barmode="group", margin=dict(t=10, b=0, l=0, r=0),
                   yaxis_title="%", xaxis_title="Weekly-risk cap (tight → loose)")
st.plotly_chart(_fig, use_container_width=True)
st.caption("Loosening the cap buys CAGR, but drawdown grows faster — risk-adjusted return is "
           "best at the tight end. The cap, not the entry rule, is what kept conservative runs "
           "in single-digit drawdowns through 2018/2020/2022.")

# ─────────────────────────────────────────────────────────────────────────
st.header("7 · Withdrawals — what an account can actually pay")
md(
    "Withdrawal runs draw a monthly income (inflation-adjusted yearly, never below a floor). "
    "**Coverage %** — the share of the target actually paid over 19 years — is the headline. "
    "The pattern is blunt: **sustainability is set by the draw relative to account size**, not "
    "by sizing finesse. The cap barely matters because a withdrawing account rarely grows "
    "enough for the cap to bind."
)
_wd = df[df["in_withdrawals_on"] == True].copy()
if not _wd.empty:
    _wd["cov"] = _n(_wd["kpi_coverage_pct"]) * 100
    _wt2 = (_wd.groupby(["start_disp", "target_disp"])
              .agg(Runs=("run_id", "count"), AvgCov=("cov", "mean"), BestCov=("cov", "max"))
              .reset_index())
    _wt2["_k"] = _wt2["start_disp"].str.strip("$k").astype(float)
    _wt2["_t"] = _wt2["target_disp"].str.replace(r"[^\d]", "", regex=True).astype(float)
    _wt2 = _wt2.sort_values(["_k", "_t"]).drop(columns=["_k", "_t"])
    st.dataframe(_wt2, hide_index=True, use_container_width=True,
                 column_config={
                     "start_disp": st.column_config.TextColumn("Starting capital"),
                     "target_disp": st.column_config.TextColumn("Monthly target"),
                     "Runs": st.column_config.NumberColumn(format="%,d"),
                     "AvgCov": st.column_config.NumberColumn("Avg coverage", format="%.1f%%"),
                     "BestCov": st.column_config.NumberColumn("Best coverage", format="%.1f%%"),
                 })
md(
    "Reading the table: a **$250/mo draw on $40k** (≈ 7.5%/yr of the start) is *almost* "
    "sustainable — the best configs cover ~98% — but the average run leaves income on the "
    "table. **$1,000/mo wants a $160k base** (best ~90%), and $2,000/mo isn't sustainable on "
    "any tier tested. A workable rule of thumb from the grid: target a monthly draw near "
    "**0.5–0.6% of starting capital**, and treat anything past 1% as hope, not a plan."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("8 · Getting started — the slow, low-risk path")
md(
    "If you're new to this and want to enter gradually with strictly limited capital at risk, "
    "the grid has a specific corner for you: **small width, low delta, low weekly-risk %.**\n\n"
    "**The starter profile:** $10–$25 wide spreads · 5Δ short · 5–10% weekly risk · a fast "
    "(5-day SMA) trend filter · $10k–$25k account. Real examples from the grid:\n\n"
    "| Setup | CAGR | Max DD | Calmar |\n"
    "|---|--:|--:|--:|\n"
    "| $20k · $10 wide · 5Δ · 5% weekly risk ($2k cap) · sma_5 | 2.8% | **−2.1%** | 1.35 |\n"
    "| $10k · $10 wide · 5Δ · 10% weekly risk ($2k cap) · sma_5 | 4.0% | −4.0% | 1.00 |\n"
    "| $20k · $10 wide · 5Δ · 15% weekly risk ($6k cap) · sma_5 | 5.7% | −5.6% | 1.02 |\n\n"
    "Those drawdowns are *single-digit through the GFC, 2018, COVID and 2022 combined*. The "
    "returns are modest — that's the honest price of the safety — but the **dollars at risk in "
    "any single week are capped at $1,000–$2,000**, which is what makes the learning period "
    "survivable.\n\n"
    "**A sensible ladder** (each step only after you're comfortable with the last):\n"
    "1. **Paper first.** Pick one starter config above, open the Run Detail page, and follow "
    "its trade log against the live market for a few weeks — entry day, strike selection, the "
    "1-DTE exit — until the mechanics are boring.\n"
    "2. **Go live at the bottom rung** — 1 contract, $10–$25 wide, 5Δ, fast filter. One "
    "contract of a $10-wide spread risks at most ~$1,000 less the credit.\n"
    "3. **Step up the weekly-risk %** (5% → 10% → 15%) *before* stepping up width or delta — "
    "it's the gentlest dial and the easiest to step back down.\n"
    "4. **Then width** ($25 → $50) as the account grows past ~$25k.\n"
    "5. **Delta last.** Moving 5Δ → 10Δ roughly doubles the typical drawdown — it's the "
    "biggest single jump in character. Make it only with a drawdown budget you've already "
    "lived through.\n\n"
    "Use **Request a Run** to test your exact ladder rung (your capital, your width, your "
    "risk %) before committing real money to it."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("9 · When the pain came — 2018 above all")
md(
    "Every run records the date of its worst drawdown. Cluster those dates and the strategy's "
    "true stress tests stand out — and they are **not** the famous bear markets:"
)
_dd = df.dropna(subset=["kpi_max_dd_date"]).copy()
_dd["yr"] = pd.to_datetime(_dd["kpi_max_dd_date"]).dt.year
_hist = _dd.groupby("yr")["run_id"].count().reset_index(name="runs")
_hist["share"] = _hist["runs"] / _hist["runs"].sum() * 100
_fig = px.bar(_hist, x="yr", y="share", labels={"yr": "Year of the run's worst drawdown",
                                                "share": "% of all runs"})
_fig.update_traces(marker_color="#7F77DD")
_fig.update_layout(height=340, margin=dict(t=10, b=0, l=0, r=0))
_fig.update_xaxes(dtick=2)
st.plotly_chart(_fig, use_container_width=True)
md(
    "- **2018 is the binding year for roughly a third of the entire grid.** The February 2018 "
    "\"Volmageddon\" vol spike plus the Q4 selloff hit fast, from an uptrend — exactly the "
    "shape a put-credit-spread strategy (and its trend filter) handles worst.\n"
    "- **COVID 2020 is second** (~15%) — same shape: fast, from highs.\n"
    "- **2023 and 2025 follow** — later-period drawdowns matter more because accounts are "
    "bigger by then (a percentage drawdown needs more dollars), which is also why tight caps "
    "help most in the back half.\n"
    "- **2008 almost never binds** (<1%) and **2022 surprisingly little** (~6%): both were "
    "*slow* declines that the trend filters largely sat out, and in 2008 most configs were "
    "still small enough to be at full size anyway. **The lesson: this strategy's enemy is the "
    "fast crash from an uptrend, not the long bear.** Any improvement work should target "
    "exactly that shape — see §13."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("10 · Exit rules under the microscope")
md(
    "Two reader questions, answered with dedicated engine experiments (June 2026) on three "
    "flagship configs — conservative (5Δ/$25w), balanced (10Δ/$50w), aggressive (15Δ/$50w, "
    "no filter).\n\n"
    "**Q1 — Is the 1-DTE exit threshold (close if SPX is within 2% of the short strike on the "
    "last day) the right number?**"
)
_x1 = pd.DataFrame({
    "OTM threshold": ["Off (0%)", "0.5%", "1%", "2% (current)", "3%"],
    "5Δ / $25w · Calmar": [0.24, 0.19, 0.93, 1.15, 1.05],
    "10Δ / $50w · Calmar": [0.34, 0.95, 0.88, 0.86, 0.83],
    "15Δ / $50w · Calmar": [0.58, 0.59, 0.56, 0.60, 0.58],
})
st.dataframe(_x1, hide_index=True, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(format="%.2f")
                            for c in _x1.columns if c != "OTM threshold"})
md(
    "- **The 1-DTE exit itself is essential.** Turn it off and the balanced config's max "
    "drawdown explodes from −13% to −33%, the conservative one's from −10% to −45%. Most of "
    "the rule's value is avoiding the last-day gamma disaster.\n"
    "- **2% is the right ballpark — and clearly right for 5Δ.** At 5Δ a tighter trigger "
    "(0.5%) almost never fires until it's too late (−51% drawdown!), because a 5Δ strike "
    "sits far below spot; the threshold has to be *wide* to give any warning.\n"
    "- **At 10Δ a tighter 0.5% trigger looked better on this history** (Calmar 0.95 vs "
    "0.86) — it fires rarely, keeping more final-day premium, and on this path dodged the "
    "same disasters. At 15Δ that edge disappears (≈0.59 vs 0.60). *Treat any such gain "
    "skeptically*: it rests on a handful of weeks, and our sizing study showed small exit "
    "tweaks can shift which crisis the equity path meets at full size — this very re-run "
    "deepened the 15Δ config's drawdown and erased its apparent 0.5% advantage. The honest "
    "summary: **2% is a sound, conservative default; if anything, the threshold should scale "
    "with delta (wider for lower delta), and a 0.5–1% setting at 10Δ is a promising, not "
    "proven, refinement.**\n\n"
    "**Q2 — Would taking profits early (e.g. at 95% of max profit) help?**"
)
_x2 = pd.DataFrame({
    "Profit target": ["None (current)", "95%", "90%", "80%"],
    "5Δ / $25w · CAGR %": [11.48, 11.33, 11.08, 11.09],
    "5Δ · Calmar": [1.15, 1.11, 1.06, 1.00],
    "10Δ / $50w · CAGR %": [11.43, 11.26, 11.06, 10.86],
    "10Δ · Calmar": [0.86, 0.85, 0.83, 0.81],
    "15Δ / $50w · CAGR %": [18.97, 18.62, 18.56, 18.78],
    "15Δ · Calmar": [0.60, 0.55, 0.54, 0.58],
})
st.dataframe(_x2, hide_index=True, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(format="%.2f")
                            for c in _x2.columns if c != "Profit target"})
md(
    "**No — at this DTE, profit-taking only gives money back.** At every level tested "
    "(80/90/95%) and on all three configs, CAGR fell and drawdown didn't improve. With ~7 days "
    "in a trade, the final days' decay *is* a large share of the edge, and the 1-DTE OTM rule "
    "already provides the protective exit a profit target would duplicate. (Per-trade stop "
    "losses at 35/50/65% of credit were tested in earlier batches with the same verdict; a "
    "50% stop, a 50% profit target, and a reader-submitted 95% profit target were re-checked "
    "on the current data — the stop didn't help and both profit targets gave return back.) "
    "What deserves credit instead: the **breach close** and the **1-DTE rule** — they are the "
    "exits doing the real work."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("11 · Does skipping FOMC weeks help? — the most-requested test")
md(
    "A reader favorite: **skip the week's entry whenever a scheduled Fed (FOMC) decision "
    "falls inside the trade's 7-day window.** We tested it the cheap way first — directly on "
    "the realized trades already in the log, across the three flagship configs — before "
    "building anything.\n\n"
    "**The naive view looks damning.** Line up every core run's *worst-drawdown date* against "
    "the FOMC calendar and **37% of them bottom within a few days of a meeting**, against an "
    "**18.7% base rate** — nearly 2×. Case closed?\n\n"
    "**No — that's a turning-point illusion.** FOMC meetings are where stressed markets often "
    "*bottom and turn* (December 2018, the COVID low, the GFC low), not where the money is "
    "lost. The honest test is causal: compare the realized P&L of trades that actually *span* "
    "an FOMC decision against those that don't."
)
_fomc = pd.DataFrame({
    "Config": ["Conservative 5Δ / $25w", "Balanced 10Δ / $50w",
               "Aggressive 15Δ / $50w", "Pooled (all three)"],
    "FOMC-wk trades": [80, 82, 127, 289],
    "Loss rate · FOMC": [6.3, 11.0, 13.4, 10.7],
    "Loss rate · other": [6.8, 9.0, 12.9, 10.2],
    "Ret-on-risk · FOMC": [1.38, 1.68, 0.43, 1.05],
    "Ret-on-risk · other": [1.27, 1.61, 2.04, 1.72],
    "Worst trade · FOMC": [-28.4, -41.9, -75.2, -75.2],
    "Worst trade · other": [-22.3, -46.8, -107.9, -107.9],
})
st.dataframe(_fomc, hide_index=True, use_container_width=True,
             column_config={
                 "FOMC-wk trades": st.column_config.NumberColumn(format="%d"),
                 "Loss rate · FOMC": st.column_config.NumberColumn(format="%.1f%%"),
                 "Loss rate · other": st.column_config.NumberColumn(format="%.1f%%"),
                 "Ret-on-risk · FOMC": st.column_config.NumberColumn(format="%.2f%%"),
                 "Ret-on-risk · other": st.column_config.NumberColumn(format="%.2f%%"),
                 "Worst trade · FOMC": st.column_config.NumberColumn(format="%.1f%%"),
                 "Worst trade · other": st.column_config.NumberColumn(format="%.1f%%"),
             })
st.caption("Per-trade outcomes split by whether a scheduled FOMC decision fell inside the "
           "trade's holding window. 'Return on risk' = the trade's realized P&L as a share of "
           "its max loss; 'worst trade' is the most negative single trade. 2007 → 2026-06-12.")
md(
    "Read it and the idea falls apart:\n"
    "- **FOMC weeks are not more dangerous.** Pooled loss rate is **10.7% vs 10.2%** — a "
    "coin-flip difference — and the **worst single trade in the whole sample is a *non*-FOMC "
    "week** (−108% of risk, vs −75% on the worst FOMC week). The fat tail lives *outside* "
    "FOMC weeks.\n"
    "- **Those trades make money.** FOMC-overlap trades were net positive in *every* config — "
    "**+$98k combined** across the three. Skipping them throws that away.\n"
    "- **So you'd pay to make things worse:** drop ~**15% of all trades** (forgone premium) to "
    "sit out weeks that carry *normal* risk and *positive* return.\n\n"
    "**Why it fails:** the strategy's real enemy (§9) — the fast crash from an uptrend, met on "
    "the last day — is already handled by the trend filter and the 1-DTE OTM exit (§10). A "
    "scheduled-meeting calendar adds no information those don't already have, and the genuinely "
    "violent Fed moves (the 2008 and March-2020 *emergency* cuts) were **unscheduled** — "
    "invisible to a calendar rule in advance. A continuous **volatility-regime** signal (§13) "
    "targets the crash *shape* far better than any fixed date. **Verdict: FOMC-week skipping is "
    "mildly hurtful — we won't add it.**"
)

# ─────────────────────────────────────────────────────────────────────────
st.header("12 · Does skipping CPI weeks help? — same test, same answer")
md(
    "After FOMC (§11), the natural follow-up: **skip the entry when a monthly CPI release "
    "lands inside the trade's window.** CPI is the better suspect — hot inflation prints drove "
    "some of 2022's worst single sessions (the −4.3% day on the September 2022 report). Same "
    "cheap test, same three flagship configs, with release dates taken from the official BLS "
    "calendar.\n\n"
    "**This time even the naive overlay is empty.** Only **20% of core runs** bottom their "
    "worst drawdown near a CPI release — *below* the **28.9% base rate**. Where FOMC at least "
    "*looked* alarming until the causal test debunked it, CPI shows no clustering at all."
)
_cpi = pd.DataFrame({
    "Config": ["Conservative 5Δ / $25w", "Balanced 10Δ / $50w",
               "Aggressive 15Δ / $50w", "Pooled (all three)"],
    "CPI-wk trades": [98, 100, 149, 347],
    "Loss rate · CPI": [7.1, 11.0, 12.1, 10.4],
    "Loss rate · other": [6.7, 8.9, 13.1, 10.2],
    "Ret-on-risk · CPI": [0.85, 1.07, 1.57, 1.22],
    "Ret-on-risk · other": [1.39, 1.76, 1.85, 1.70],
    "Worst trade · CPI": [-28.4, -46.2, -69.6, -69.6],
    "Worst trade · other": [-16.6, -46.8, -107.9, -107.9],
})
st.dataframe(_cpi, hide_index=True, use_container_width=True,
             column_config={
                 "CPI-wk trades": st.column_config.NumberColumn(format="%d"),
                 "Loss rate · CPI": st.column_config.NumberColumn(format="%.1f%%"),
                 "Loss rate · other": st.column_config.NumberColumn(format="%.1f%%"),
                 "Ret-on-risk · CPI": st.column_config.NumberColumn(format="%.2f%%"),
                 "Ret-on-risk · other": st.column_config.NumberColumn(format="%.2f%%"),
                 "Worst trade · CPI": st.column_config.NumberColumn(format="%.1f%%"),
                 "Worst trade · other": st.column_config.NumberColumn(format="%.1f%%"),
             })
st.caption("Per-trade outcomes split by whether a CPI release fell inside the trade's holding "
           "window. 'Return on risk' = realized P&L as a share of max loss; 'worst trade' is the "
           "most negative single trade. Release dates from the BLS/FRED calendar. 2007 → 2026-06-12.")
md(
    "The verdict carries straight over from §11:\n"
    "- **Not more dangerous.** Pooled loss rate is **10.4% vs 10.2%**, and the worst single "
    "trade in the sample is again a *non*-CPI week (−108% of risk vs −70%).\n"
    "- **Profitable.** CPI-overlap trades were net positive in *every* config — **+$207k "
    "combined.** Skipping ~19% of trades forfeits it.\n"
    "- **One real difference from FOMC:** CPI weeks are *consistently* a touch less lucrative "
    "per unit of risk across all three configs (FOMC was mixed). But they're still positive and "
    "no more tail-heavy — so skipping them would lower return to dodge risk that isn't there, "
    "and Calmar would fall, not rise.\n\n"
    "**Verdict: like FOMC, CPI-week skipping is mildly hurtful — we won't add it.** Two "
    "scheduled-calendar filters now tested, one result: this strategy's protection comes from "
    "the trend filter and the 1-DTE exit, not from sitting out known dates. A continuous "
    "**volatility-regime** signal (§13) remains the more promising direction."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("13 · Where improvement might still be found")
md(
    "Honest assessment: within the dials this grid already sweeps (delta, width, capital, "
    "risk %, cap, 13 filters, exits), the frontier is now well-mapped — further grid-searching "
    "the same dials is more likely to overfit than to discover. The genuinely promising "
    "directions add *new information* the entry decision can't currently see, aimed squarely "
    "at the §9 finding (fast crashes from uptrends):\n\n"
    "- **Event-calendar awareness — mostly a dead end.** Skipping **FOMC** (§11) and **CPI** "
    "(§12) weeks were both tested; neither helped. The only scheduled-calendar idea still "
    "unchecked is quarterly **OPEX** — a flow/positioning effect rather than a data surprise — "
    "but two clean negatives lower the prior that a third calendar is the answer.\n"
    "- **Volatility-regime sizing.** VIX level, VIX term-structure slope (backwardation = "
    "stress), or IV rank could scale the weekly risk % continuously — sit at full size in calm "
    "contango, automatically shrink when the vol market itself is warning. This targets the "
    "crash *shape* better than any price MA can, because vol leads price on the way down.\n"
    "- **Delta-switching by regime.** The playbook (§1) is static today — a run picks one "
    "delta forever. A regime rule (e.g. 5Δ when below the 200-day or VIX > 25, 15Δ when above "
    "and calm) would trade the frontier hand-off dynamically. The matched-pair data says the "
    "edge exists; the question is whether a tradable rule captures it after whipsaw.\n"
    "- **A finer 1-DTE threshold by delta** (§10): replace the flat 2% with a delta-scaled "
    "trigger. Promising, cheap to test, needs out-of-sample discipline.\n"
    "- **Continuously-tapering sizing.** The current cap is a hard kink; a smooth taper of "
    "risk % as equity grows removes the path-dependence where a run's fate hinges on *when* "
    "it crosses its cap (the reason a small tweak can swap a −9% history for a −18% one).\n\n"
    "What we'd caution **against**: more exit knobs (PT/SL — tested, they subtract), higher "
    "deltas (tested, dominated), and cherry-picking the single best run in any zone — "
    "neighboring configs' results are the better estimate of what to expect."
)

render_footer()
