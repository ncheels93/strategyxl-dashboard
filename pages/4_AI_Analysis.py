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

def _n(s):
    return pd.to_numeric(s, errors="coerce")

# The grid runs every config at TWO spread-fill policies: "Snap Narrower" (fill the
# nearest narrower strike when the exact width is missing) and "Skip" (trade only the
# exact width). Snap Narrower is the CANONICAL set the playbook (§1–§9) is built on —
# it reflects what you'd actually fill in the market. The Skip set is the contrast in
# §4 ("Spread-fill handling"). `core` keeps both; `df` is the canonical Snap Narrower.
CANONICAL_HANDLING = "Snap Narrower"
core = df[~pd.to_numeric(df["batch_id"], errors="coerce").isin(ADHOC_BATCH_IDS)].copy()
core["cagr"]   = _n(core["kpi_cagr"]) * 100
core["maxdd"]  = _n(core["kpi_max_dd_pct"]) * 100
core["calmar"] = _n(core["kpi_calmar"])
core["winr"]   = _n(core["kpi_win_rate"]) * 100
core["pf"]     = _n(core["kpi_profit_factor"])
core["handling"] = core["in_spread_handling"].fillna("Snap Narrower")

# Display columns on `core` so BOTH the canonical `df` (derived below) and the
# `core` contrast set used in §4 carry them.
_sd = _n(core["in_short_delta_threshold"])
core["delta_disp"] = _sd.map(lambda v: f"{v*100:g}Δ" if pd.notna(v) else "—")
_sw = _n(core["in_spread_width"])
core["width_disp"] = _sw.map(lambda v: f"${int(v)}" if pd.notna(v) else "—")
_sc = _n(core["in_starting_capital"]).fillna(0)
core["start_disp"] = "$" + (_sc / 1000).round().astype(int).astype(str) + "k"
_cap = _n(core["in_max_weekly_risk"])
core["cap_disp"] = _cap.map(lambda v: f"${v/1000:g}k" if pd.notna(v) else "Uncapped")
core["trend_disp"] = core["in_trend_filter_ma"].fillna("(filter off)")
_tw = _n(core["in_target_monthly_withdrawal"])
core["target_disp"] = _tw.map(lambda v: f"${int(round(v)):,}/mo" if pd.notna(v) and v > 0 else "—")

df = core[core["handling"] == CANONICAL_HANDLING].copy()
if df.empty:
    st.warning("No core-grid scenarios in the database yet.")
    st.stop()

_DELTA_ORDER = [d for d in ("5Δ", "10Δ", "15Δ", "20Δ") if d in df["delta_disp"].unique()]
_DELTA_COLOR = {"5Δ": "#1D9E75", "10Δ": "#378ADD", "15Δ": "#EF9F27", "20Δ": "#E24B4A"}

nw = df[df["in_withdrawals_on"] != True]          # the apples-to-apples growth set
plot = df.dropna(subset=["cagr", "maxdd"])

md(f"**{len(df):,} runs** at the canonical **Snap-Narrower** fill — "
   f"{' / '.join(_DELTA_ORDER)} short deltas × widths "
   f"{'/'.join(s.strip('$') for s in sorted(df['width_disp'].unique(), key=lambda s: float(s.strip('$—') or 0) if s != '—' else 9e9))} "
   "× nine starting-capital tiers × the weekly-risk/cap grid × 13 trend-filter settings × "
   f"withdrawal plans, 2007 → today — plus a matched **{len(core)-len(df):,}-run Skip set** "
   "(exact-width-only) for the fill-handling contrast in §4.")

# ─────────────────────────────────────────────────────────────────────────
st.header("1 · The one-page playbook")
md(
    "If you read nothing else: **your drawdown tolerance picks your delta, your account size "
    "picks your width, and the weekly-risk cap sets how hard you push.** From the matched-pair "
    "study (every configuration run at all four deltas, everything else identical):\n\n"
    "| Your max-drawdown budget | Best tool for the job | What it earned (best in zone) |\n"
    "|---|---|--:|\n"
    "| up to ~−20% | **5Δ short + a fast trend filter** (5-day SMA) | ~13–16% CAGR |\n"
    "| ~−25% to −35% | **10Δ** — the balanced core strategy | ~16–22% CAGR |\n"
    "| any budget | ~~15Δ~~ and ~~20Δ~~ — dominated at every drawdown budget | — |\n\n"
    "**This is a sharper playbook than the older runs showed.** With the realistic Snap-Narrower "
    "fill, **5Δ owns everything out to ~−20%** (reaching ~16%) and **10Δ owns the middle and the "
    "deep end** (to ~22% at ~−35%). **15Δ no longer leads any zone** — its old apparent edge "
    "lived in wide-width runs whose drawdown was understated by *skipping* the sparse early-2008 "
    "weeks; once those weeks are actually traded (§4), 15Δ's drawdown deepens and 10Δ overtakes it. "
    "20Δ remains dominated everywhere.\n\n"
    "The scatter below is the whole canonical grid; the dotted lines trace the best frontier of "
    "each delta. Notice where the colors take over — that hand-off **is** the playbook."
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
st.caption("Each dot is one full 19-year backtest (canonical Snap-Narrower fill). Up and to the "
           "right is better. 5Δ (green) owns the shallow zone out to ~−20%; 10Δ (blue) owns the "
           "middle and the deep right; 15Δ (amber) and 20Δ (red) never lead the frontier.")

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
    "- **5Δ vs 10Δ:** gives up ~1½ points of CAGR but takes **~5–6 points *less* drawdown** "
    "(median −15% vs −21%), and wins the risk-adjusted contest outright (Calmar 0.49 vs 0.39). "
    "Win rate ~93%.\n"
    "- **15Δ vs 10Δ:** adds only **~¼ point** of median CAGR for **~5 points *more* drawdown** — "
    "and, unlike the older runs, **15Δ no longer leads even the aggressive zone.** Once the sparse "
    "early-period trades are actually taken (the Snap-Narrower fill — see §4), 15Δ's drawdown "
    "deepens enough that **10Δ tops it at every drawdown budget** (Calmar 0.32 vs 0.39).\n"
    "- **20Δ vs anything:** *dominated everywhere* — more drawdown than 15Δ and *less* return "
    "(median CAGR actually falls to ~5%, premium eaten by bigger, more frequent breaches), and no "
    "trend filter rescues it. **Selling closer to the money for \"more income\" stays the single "
    "most clearly refuted idea in the study.**\n"
    "- **Risk-adjusted return falls monotonically with delta:** median Calmar 0.49 → 0.39 → 0.32 "
    "→ 0.17. Median CAGR nudges up to 15Δ then drops, but drawdown grows faster the whole way — "
    "so the playbook tops out at **10Δ.**"
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
_fig.update_xaxes(type="category")   # $10/$25/… are categories, not a numeric axis
st.plotly_chart(_fig, use_container_width=True)
st.caption("Median CAGR by width × delta. The $50 width carries the highest medians for 10Δ/15Δ; "
           "the wide spreads trade CAGR for smoothness; the narrow ones depend heavily on delta.")

# ── Fill-handling contrast: Snap Narrower (canonical) vs Exact (Skip) ──────
st.subheader("Fill handling — trading the gaps (Narrow) vs exact-only (Exact)")
md(
    "Every config here was run **two ways**, and the choice quietly shapes everything above:\n"
    "- **Snap Narrower** *(canonical)* — when the exact `short − width` strike is missing, fill "
    "the nearest **narrower** strike. Sized to the same dollar risk, so a narrower fill just means "
    "*more contracts*. This is what you'd actually get filling orders.\n"
    "- **Exact** (the engine's `Skip`) — trade **only** when the exact width exists; otherwise sit "
    "the week out.\n\n"
    "The difference is almost entirely an **early-history** effect: from ~2012 on, dense chains "
    "mean the exact strike is nearly always there and the two are identical. In **2007–2011** — "
    "and only on the **wider** spreads — the chain was sparse, so Snap Narrower **trades those weeks "
    "at a much narrower effective width** (a \"$200\" spread averaged ~62-wide in 2007), while Exact "
    "skips them. That's why the wide-width drawdowns in §1/§4 are deeper than older runs showed: "
    "the hard early weeks are now *traded*, not sat out."
)
_hc = (core[core["in_withdrawals_on"] != True]
       .groupby(["width_disp", "handling"])["calmar"].median().reset_index())
_hc["_k"] = _hc["width_disp"].str.strip("$—").replace("", "0").astype(float)
_hc = _hc.sort_values("_k")
_fig = px.bar(_hc, x="width_disp", y="calmar", color="handling", barmode="group",
              category_orders={"width_disp": _hc["width_disp"].unique().tolist(),
                               "handling": ["Snap Narrower", "Skip"]},
              color_discrete_map={"Snap Narrower": "#378ADD", "Skip": "#9AA0A6"},
              labels={"width_disp": "Spread width", "calmar": "Median Calmar", "handling": "Fill policy"})
_fig.update_layout(height=360, margin=dict(t=10, b=0, l=0, r=0))
_fig.update_xaxes(type="category")   # $10/$25/… are categories, not a numeric axis
st.plotly_chart(_fig, use_container_width=True)
st.caption("Median Calmar by width × fill policy. Identical at $10–$25; they diverge as width "
           "grows — at $200, Exact looks smoother, but it's *sitting out* the hardest sparse-chain "
           "weeks rather than surviving them. The playbook uses **Snap Narrower** because it reflects "
           "real fills; Exact is the honest-but-incomplete comparison.")

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
    "table. **$1,000/mo wants a $160k base** (best ~95%), and **$2,000/mo tops out around ~83% "
    "even on $160k** (and only ~33% on $40k) — not a plan. A workable rule of thumb from the grid: "
    "target a monthly draw near **0.5–0.6% of starting capital**, and treat anything past 1% as "
    "hope, not a plan."
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
    "| $20k · $10 wide · 5Δ · 15% weekly risk ($6k cap) · sma_5 | 5.8% | −5.6% | 1.03 |\n\n"
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
    "true stress tests stand out — a mix of one modern shock and the early sparse-chain years:"
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
    "- **2018 is still the single worst year — it binds ~25% of the grid.** The February 2018 "
    "\"Volmageddon\" vol spike plus the Q4 selloff hit fast, from an uptrend — exactly the "
    "shape a put-credit-spread strategy (and its trend filter) handles worst.\n"
    "- **2007 is now second (~20%)** — new, and a direct consequence of the Snap-Narrower fill "
    "(§4): the sparse-chain 2007 weeks that older runs *skipped* on wide widths are now traded, "
    "so those drawdowns surface here.\n"
    "- **2023, COVID-2020 and 2025 follow** (~8–10% each) — 2020 is the same fast-from-highs shape; "
    "the later years bind more because accounts are bigger by then (a % drawdown needs more dollars), "
    "which is also why tight caps help most in the back half.\n"
    "- **2008 now binds ~6%** (was ~0 when those weeks were skipped) for the same early-fill reason, "
    "and **2022 stays low (~4%)** — a *slow* decline the trend filters largely sat out. **The lesson "
    "holds for the modern era: this strategy's enemy is the fast crash from an uptrend (2018, 2020), "
    "not the long bear.** Improvement work should target that shape — see §13."
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
    "5Δ / $25w · Calmar": [0.25, 0.20, 0.95, 1.18, 1.09],
    "10Δ / $50w · Calmar": [0.36, 0.97, 0.91, 0.81, 0.74],
    "15Δ / $50w · Calmar": [0.29, 0.28, 0.26, 0.26, 0.28],
})
st.dataframe(_x1, hide_index=True, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(format="%.2f")
                            for c in _x1.columns if c != "OTM threshold"})
md(
    "- **The 1-DTE exit itself is essential.** Turn it off and the balanced config's max "
    "drawdown explodes from −14% to −31%, the conservative one's from −10% to −43%. Most of "
    "the rule's value is avoiding the last-day gamma disaster.\n"
    "- **2% is the right ballpark — and clearly right for 5Δ.** At 5Δ a tighter trigger "
    "(0.5%) almost never fires until it's too late (−49% drawdown!), because a 5Δ strike "
    "sits far below spot; the threshold has to be *wide* to give any warning.\n"
    "- **At 10Δ a tighter 0.5% trigger looks best on this history** (Calmar 0.97 vs 0.81) — "
    "it fires rarely, keeping more final-day premium, and on this path dodged the same "
    "disasters. At 15Δ the threshold barely moves the needle (≈0.26–0.29 whatever you pick) "
    "because that config now carries a ~−65% drawdown no exit tweak can rescue. *Treat the 10Δ "
    "gain skeptically*: it rests on a handful of weeks, and small exit tweaks can shift which "
    "crisis the equity path meets at full size. The honest summary: **2% is a sound, "
    "conservative default; if anything, the threshold should scale with delta (wider for "
    "lower delta), and a 0.5–1% setting at 10Δ is a promising, not proven, refinement.**\n\n"
    "**Q2 — Would taking profits early (e.g. at 95% of max profit) help?**"
)
_x2 = pd.DataFrame({
    "Profit target": ["None (current)", "95%", "90%", "80%"],
    "5Δ / $25w · CAGR %": [11.55, 11.42, 11.16, 11.17],
    "5Δ · Calmar": [1.18, 1.16, 1.10, 1.05],
    "10Δ / $50w · CAGR %": [11.47, 11.31, 11.11, 10.89],
    "10Δ · Calmar": [0.81, 0.82, 0.77, 0.68],
    "15Δ / $50w · CAGR %": [17.94, 17.65, 17.64, 17.95],
    "15Δ · Calmar": [0.26, 0.27, 0.26, 0.28],
})
st.dataframe(_x2, hide_index=True, use_container_width=True,
             column_config={c: st.column_config.NumberColumn(format="%.2f")
                            for c in _x2.columns if c != "Profit target"})
md(
    "**Largely no — at this DTE, profit-taking mostly gives money back.** At every level tested "
    "(80/90/95%) and on all three configs, **CAGR fell**; risk-adjusted return barely moved — a "
    "hair *better* on the deeper-drawdown configs (taking profit early trims their worst dips), "
    "but never enough to justify the CAGR you forfeit. With ~7 days "
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
    "**The naive view looks alarming.** Line up every core run's *worst-drawdown date* against "
    "the FOMC calendar and **~29% of them bottom within a few days of a meeting**, against an "
    "**18.7% base rate** — about 1.5×. Case closed?\n\n"
    "**No — that's a turning-point illusion.** FOMC meetings are where stressed markets often "
    "*bottom and turn* (December 2018, the COVID low, the GFC low), not where the money is "
    "lost. The honest test is causal: compare the realized P&L of trades that actually *span* "
    "an FOMC decision against those that don't."
)
_fomc = pd.DataFrame({
    "Config": ["Conservative 5Δ / $25w", "Balanced 10Δ / $50w",
               "Aggressive 15Δ / $50w", "Pooled (all three)"],
    "FOMC-wk trades": [82, 83, 131, 296],
    "Loss rate · FOMC": [6.1, 10.8, 13.0, 10.5],
    "Loss rate · other": [7.0, 9.0, 12.8, 10.2],
    "Ret-on-risk · FOMC": [1.37, 1.70, -0.25, 0.75],
    "Ret-on-risk · other": [1.27, 1.58, 2.00, 1.69],
    "Worst trade · FOMC": [-28.4, -41.9, -127.8, -127.8],
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
    "Read the causal test and it's more nuanced than the overlay — but still not a clear win for skipping:\n"
    "- **FOMC weeks aren't more loss-prone, but they ARE less rewarding.** Pooled loss rate is "
    "**10.5% vs 10.2%** (a coin-flip), yet return-on-risk is **0.75 vs 1.69** — FOMC-overlap "
    "trades earn barely half as much per dollar risked.\n"
    "- **Pooled they still make money (+$44k), but not uniformly.** The conservative and balanced "
    "configs are net positive on FOMC weeks; the **aggressive 15Δ config actually *loses* on "
    "them (−$20k)**, and the single **worst trade in the sample is now an FOMC week** (−128% of "
    "risk, on that 15Δ config). The fat tail no longer sits cleanly *outside* FOMC weeks.\n"
    "- **For the configs you'd actually trade (5Δ/10Δ), skipping still forfeits money** — you'd "
    "drop ~**15% of all trades** to sit out weeks that are net positive there. (The 15Δ config "
    "that *would* benefit is itself dominated — §1.)\n\n"
    "**Why a calendar rule still isn't the answer:** the strategy's real enemy (§9) — the fast "
    "crash from an uptrend, met on the last day — is already handled by the trend filter and the "
    "1-DTE OTM exit (§10). The genuinely violent Fed moves (the 2008 and March-2020 *emergency* "
    "cuts) were **unscheduled** — invisible to a calendar in advance. A continuous "
    "**volatility-regime** signal (§13) targets the crash *shape* far better than a fixed date. "
    "**Verdict: FOMC-week skipping is at best a wash for the core strategy and a drag on return — "
    "we won't add it, though FOMC weeks are clearly the less-rewarding ones.**"
)

# ─────────────────────────────────────────────────────────────────────────
st.header("12 · Does skipping CPI weeks help? — same test, same answer")
md(
    "After FOMC (§11), the natural follow-up: **skip the entry when a monthly CPI release "
    "lands inside the trade's window.** CPI is the better suspect — hot inflation prints drove "
    "some of 2022's worst single sessions (the −4.3% day on the September 2022 report). Same "
    "cheap test, same three flagship configs, with release dates taken from the official BLS "
    "calendar.\n\n"
    "**This time even the naive overlay is empty.** Only **~17% of core runs** bottom their "
    "worst drawdown near a CPI release — *below* the **28.9% base rate**. Where FOMC at least "
    "*looked* alarming until the causal test debunked it, CPI shows no clustering at all."
)
_cpi = pd.DataFrame({
    "Config": ["Conservative 5Δ / $25w", "Balanced 10Δ / $50w",
               "Aggressive 15Δ / $50w", "Pooled (all three)"],
    "CPI-wk trades": [99, 100, 151, 350],
    "Loss rate · CPI": [7.1, 11.0, 11.9, 10.3],
    "Loss rate · other": [6.8, 8.9, 13.0, 10.2],
    "Ret-on-risk · CPI": [0.84, 1.04, 1.70, 1.27],
    "Ret-on-risk · other": [1.40, 1.73, 1.66, 1.61],
    "Worst trade · CPI": [-28.4, -46.2, -69.6, -69.6],
    "Worst trade · other": [-16.6, -46.8, -127.8, -127.8],
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
    "The verdict carries over from §11 — and CPI is the *cleaner* negative:\n"
    "- **Not more dangerous.** Pooled loss rate is **10.3% vs 10.2%**, and the worst single "
    "trade in the sample is — unlike FOMC — still a *non*-CPI week (−128% of risk vs −70%).\n"
    "- **Profitable in *every* config.** CPI-overlap trades were net positive across all three — "
    "**+$204k combined.** Skipping ~18% of trades forfeits it.\n"
    "- **A touch less lucrative for the core, even on the aggressive config:** CPI weeks earn "
    "a bit less per unit of risk at 5Δ/10Δ (≈0.8–1.0 vs 1.4–1.7), while the aggressive 15Δ is "
    "roughly even (1.70 vs 1.66). Still positive and no more tail-heavy — so skipping them would "
    "lower return to dodge risk that isn't there, and Calmar would fall, not rise.\n\n"
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
