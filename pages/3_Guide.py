"""Guide & definitions — how to use the dashboard, page by page."""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from data.db import check_password_gate, render_footer, load_scenario_runs
from data.docs import TERMS, md, capped_risk_pct

st.set_page_config(page_title="Guide — StrategyXL", page_icon="📖", layout="wide")
check_password_gate()

st.title("Guide & Definitions")
st.caption("How to use this dashboard — what the strategy is, what each page does, how the "
           "controls work, and what every number means. For what the results *say*, see the "
           "**AI Analysis** page.")

try:
    _runs_count = f"{len(load_scenario_runs()):,}"
except Exception:
    _runs_count = "thousands of"

# ─────────────────────────────────────────────────────────────────────────
st.header("1 · What this is")
md(
    "This dashboard backtests a **weekly S&P 500 put credit spread**. Each Friday "
    "(or the Thursday before a holiday) the strategy:\n"
    "- **sells** an out-of-the-money put on the S&P 500 (SPX) at a chosen **short delta** — "
    "5Δ (far out-of-the-money, conservative), **10Δ (the core strategy)**, 15Δ or 20Δ "
    "(closer to the money, more premium, more risk),\n"
    "- **buys** a further-out put below it (the “width”, anywhere from $10 to $200 lower) as a "
    "defined-risk hedge,\n"
    "- **collects the net premium** and holds ~7 days to expiration, closing early on a "
    "breach or a 1-DTE rule.\n\n"
    "You win the premium when the market doesn't fall sharply through your short strike — "
    "which is most weeks. The risk is a fast, deep drop. The dashboard shows, across "
    f"**a systematic grid of {_runs_count} backtested configurations (2007–2026)**, how "
    "different delta, width, sizing, trend-filter and withdrawal choices trade return "
    "against that downside."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("2 · The pages, top to bottom in the sidebar")
md(
    "Listed in the order they appear on the left. (For the order you'd actually *work* through "
    "them, see the typical workflow in section 3.)\n\n"
    "- **Summary** — compare all runs at once: best-in-class cards, the CAGR-vs-drawdown "
    "scatter (with the S&P star and efficient frontier), a **Breakdowns** section (roll-ups by "
    "short delta, spread width, starting capital, max weekly risk, trend filter and "
    "withdrawals), and the full leaderboard. The sidebar filters — led by a **performance "
    "screen** (slide a minimum CAGR, worst-acceptable Max DD, or minimum Calmar) — narrow "
    "everything on the page.\n"
    "- **Run Detail** — drill into one run: full KPIs, risk-adjusted metrics, equity & "
    "drawdown charts, the ten biggest winners/losers with entry context, the full trade log, "
    "and (if used) the withdrawal breakdown. Get here by clicking any **Run #** link.\n"
    "- **Compare** — put 2–4 runs side by side: a metric table with the best value in each "
    "row highlighted, the inputs that differ, overlaid return/drawdown curves, and a "
    "**trade-by-trade table** of every week each run traded (filterable to losers, a year, "
    "or just the weeks where the runs diverged). Get here by box-selecting dots on the "
    "Summary scatter, or from the Compare links on any selection.\n"
    "- **Guide** (this page) — how everything works, plus the glossary.\n"
    "- **AI Analysis** — the findings. A guided, chart-backed read of what the whole grid "
    "says: which delta fits which drawdown budget, what each dial does, a getting-started "
    "path for small accounts, when the historical pain came, and what was tested that "
    "*didn't* work (profit targets, stop losses, 20Δ).\n"
    "- **Request a Run** — submit a new scenario to backtest. Section 10 below walks through it.\n"
    "- **Strategy Finder** — the shortcut: type in your capital, your income or CAGR goal, and "
    "your drawdown tolerance, and it ranks the best-fitting configurations for you — no charts "
    "to read. Section 9 below covers it.\n"
    "- **Event Calendars** — reference tables of the FOMC and CPI dates behind the event-skip "
    "studies on AI Analysis (§11/§12), browsable by year and downloadable as CSV, with sources "
    "cited.\n\n"
    "Every section of every page has an **ⓘ What is this?** popover with a quick explanation "
    "and the definitions relevant to it."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("3 · A typical workflow")
md(
    "1. **Start on Summary.** Set the sidebar to your situation: your **starting capital** "
    "tier, the **short delta** you're considering, and slide the **Worst Max DD allowed** to "
    "the deepest drawdown you could genuinely sit through.\n"
    "2. **Read the scatter.** What's left is every configuration that fits your constraints. "
    "Dots near the top-left of the survivors are your candidates; the dotted efficient "
    "frontier marks the best CAGR available at each drawdown level.\n"
    "3. **Click 2–4 candidate dots** (shift-click or box-select) and open **Compare** — check "
    "where their equity curves differ, especially 2008, 2018, 2020 and 2022.\n"
    "4. **Open the winner's Run Detail** and read its worst trades and drawdown chart. If "
    "you couldn't have lived through that chart, loosen a dial and repeat.\n"
    "5. **Not in the grid? Request it.** The Request-a-Run page queues your exact "
    "configuration for the engine.\n\n"
    "If you'd rather start from conclusions than exploration, read the **AI Analysis** page "
    "top to bottom first — it ends in a concrete getting-started ladder. And if you'd rather "
    "skip exploring entirely, the **Strategy Finder** (§9) turns your goals straight into a "
    "ranked shortlist."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("4 · The sizing model (the important one)")
md(
    "How big a position each week gets is the single biggest driver of both return and "
    "drawdown. The model is one simple idea:\n\n"
    "> **Each week you risk a set % of your account — but never more than a hard dollar "
    "ceiling.**\n\n"
    "In one line: **the dollars you risk each week = whichever is smaller — your risk % × "
    "the account, or the cap.** You set just **two dials**:\n\n"
    "1. **Weekly Risk %** — the share of the account at risk each week. **50%** is the "
    "standard ($20k on a $40k account — half working, half buffer). It self-adjusts: after "
    "a loss you're risking 50% of a *smaller* account, so a bad run can't snowball.\n"
    "2. **Max Weekly Risk $** — the hard ceiling, *and the main risk dial*. While the "
    "account is small you risk the full %, but once 50% of equity would exceed the cap, "
    "you're held flat at the cap — so your risk **as a % of the account falls** as you grow.\n\n"
    "We name the cap levels as plain **risk profiles** so nobody has to think in dollars:\n\n"
    "- **Conservative** — $20k cap (≈ a constant $20k at risk; the tightest)\n"
    "- **Cautious** — $30k cap\n"
    "- **Moderate** — $50k cap\n"
    "- **Aggressive** — $75k cap\n"
    "- **Maximum** — uncapped (rides 50% of equity the whole way)\n\n"
    "**The key thing to know:** the *most* you ever risk in one week is the cap (and at most "
    "50% of the account, only while small). The chart below shows how each cap turns into a "
    "declining share of the account as it grows."
)

# ── Chart: % of account at risk vs account size, for each cap (at 50% weekly risk) ──
_profiles = [
    ("Conservative — $20k cap", 0.50, 20_000),
    ("Moderate — $50k cap",     0.50, 50_000),
    ("Aggressive — $75k cap",   0.50, 75_000),
    ("Maximum — uncapped",      0.50, None),
]
_equities = [40_000, 60_000, 80_000, 120_000, 160_000, 250_000,
             400_000, 640_000, 1_000_000, 1_600_000]
_fig = go.Figure()
for _name, _wrp, _cap in _profiles:
    _fig.add_trace(go.Scatter(
        x=_equities, y=[capped_risk_pct(_wrp, _cap, _e) * 100 for _e in _equities],
        mode="lines+markers", name=_name))
_fig.update_xaxes(title="Account size", type="log", tickprefix="$",
                  tickvals=[40_000, 80_000, 160_000, 320_000, 640_000, 1_280_000])
_fig.update_yaxes(title="% of account at risk that week", ticksuffix="%", rangemode="tozero")
_fig.update_layout(height=440, legend_title="Risk profile",
                   margin=dict(t=10, b=0, l=0, r=0))
st.plotly_chart(_fig, use_container_width=True)
st.caption("Every profile starts at 50% and flattens at its cap. The \\$20k cap (Conservative) "
           "is already flat at \\$40k — a constant \\$20k that becomes ~3% of a \\$640k account; "
           "Uncapped stays at 50% the whole way. That's the dial.")

# ─────────────────────────────────────────────────────────────────────────
st.header("5 · The trend filter")
md(
    "Optionally, the strategy only opens a new spread when the S&P closes **above a chosen "
    "moving average** (e.g. the 50- or 200-day). When the market is below that line, it "
    "sits in cash for the week. Runs labelled **(filter off)** take every weekly entry; "
    "runs tagged with an MA (e.g. the 200-day SMA) only trade in uptrends — so filter-off runs "
    "have the most trades. Which filter speed suits which delta is one of the study's main "
    "findings — see **AI Analysis §3**."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("6 · Withdrawals")
md(
    "Withdrawal runs model drawing a monthly income from the account:\n"
    "- **Target Monthly** grows each year by the **Inflation Adjust %**.\n"
    "- A **Floor** protects a minimum balance — the strategy never withdraws below it.\n"
    "- Withdrawals begin on the **Start Date**.\n\n"
    "Each scheduled month is then **Full** (paid the whole inflation-adjusted target), "
    "**Partial** (paid only what it could without breaching the floor), or **Zero** "
    "(already at/below the floor). **Coverage %** is the share of the total target actually "
    "paid — the headline “could the account sustain this income?” number."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("7 · Reading a run's label & the filters")
md(
    "Every run's label encodes its full configuration, segment by segment. Example: "
    "**|W50-C30k-NW|40k|10d|50s|s5 Entry Filter|Exit SPX below ShSt / 1D 2%|…**\n"
    "- **W50** = Weekly Risk % — 50% of the account at risk each week.\n"
    "- **C30k** = the cap — never more than $30k at risk in a week (**Uncap** = no cap).\n"
    "- **-NW / -WD** = no withdrawals / withdrawals on.\n"
    "- **40k** = starting capital ($40,000).\n"
    "- **10d** = the short-delta target (5d / 10d / 15d / 20d).\n"
    "- **50s** = the spread width ($50).\n"
    "- **s5 / e9 / No Entry Filter** = the trend filter (5-day SMA, 9-day EMA, or none).\n"
    "- The **tail** carries the exit & friction settings — breach close, the 1-DTE rule "
    "(“1D 2%”), **PT/SL** flags if a profit target or stop loss is on, and commission/slippage "
    "if they differ from the standard.\n\n"
    "You rarely need to decode this by hand — the **Risk profile** name (Conservative → "
    "Maximum) and the sidebar filters say the same things in plain language.\n\n"
    "The **sidebar filters** on Summary run top-to-bottom, most-used first:\n"
    "- **Performance screen** — slide a minimum **CAGR**, a worst-acceptable **Max DD**, or a "
    "minimum **Calmar**. These screen the *whole* page (cards, scatter, leaderboard) and shade "
    "the kept region green on the scatter; each is off until you move it.\n"
    "- **Structure** — **short delta**, spread width and starting capital.\n"
    "- **Sizing** — risk profile, the cap, and weekly risk %.\n"
    "- **Strategy** — the trend-filter MA.\n"
    "- **Withdrawals** — on/off and the monthly target.\n\n"
    "All filters combine."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("8 · How the engine builds each trade")
md(
    "Every run is the same weekly loop, applied to 19 years of real SPX option chains. "
    "Each week the engine:\n\n"
    "1. **Enters every Friday.** It opens one put credit spread expiring the *next* Friday "
    "(7 days out). If that Friday is a market holiday it enters Thursday instead, so the "
    "trade still spans a week.\n"
    "2. **Picks the short strike — your delta dial.** It sells the put whose delta is closest "
    "to your target (e.g. the 10-delta), searching within a small delta *band* around it so it "
    "can still trade on days the exact delta isn't quoted. Higher delta = closer to the money "
    "= more premium but more risk. This is the single biggest risk lever.\n"
    "3. **Picks the long strike — the protective leg, with a narrow-only tolerance.** It buys "
    "a further-OTM put `width` below the short (e.g. $50 lower for a $50 spread) to cap the "
    "loss. If no strike sits *exactly* `width` below, the engine takes the closest available "
    "strike that only **narrows** the spread — up to **10% narrower, never wider**. So a $200 "
    "spread uses any long strike from $200 down to $180 below the short, always preferring the "
    "widest (closest to the $200 target). Because narrowing can only *lower* the capital at "
    "risk, the exposure cap is always respected; the payoff is that more weeks can trade "
    "instead of being skipped for a missing exact strike. Narrow spreads ($10–$50) almost "
    "always find the exact strike so this rarely bites; wide spreads ($100–$200), where "
    "strikes are sparse, gain the most trades.\n"
    "4. **Sizes the position.** Contracts are set so the week's dollars at risk = "
    "`MIN(weekly-risk % × equity, the cap)` — the sizing model in §4.\n"
    "5. **Manages the exit — three ways out:**\n"
    "    - **Breach close** — if SPX closes at or below the short strike during the week, the "
    "spread is closed that day rather than ridden into expiration.\n"
    "    - **1-DTE OTM rule** — on the final day, if SPX is within a set distance of the short "
    "strike (default **2%**), the spread is closed to dodge last-day gamma risk.\n"
    "    - **Otherwise hold to expiration**, keeping the full credit.\n"
    "    (Profit targets and per-trade stop losses were tested and **don't help** — see "
    "**AI Analysis §10**.)\n"
    "6. **Nets costs.** Every trade is charged commission and slippage, so *all* P&L on the "
    "dashboard is after costs.\n\n"
    "The engine then walks day by day — marking the open spread to market, applying any "
    "withdrawals, and recording equity. Every chart and KPI is built from that daily equity."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("9 · The Strategy Finder — let it pick for you")
md(
    "Not sure where to start? This page does the narrowing for you. Pick the tab for your "
    "goal, enter a few numbers, and it ranks the backtested configurations by how well they "
    "fit — **no AI involved** (it's plain arithmetic on the stored results, so the same "
    "inputs always give the same ranking).\n\n"
    "- **📈 Grow it** — for *compounding* an account. Enter your **capital**, a **target CAGR "
    "range**, and the **deepest drawdown you can stand**. Optionally add a monthly-income "
    "goal — it converts that to a required annual return and sanity-checks whether it's "
    "realistic. You get the top 10 growth configs with CAGR, max drawdown, Calmar and an "
    "implied first-year $/month.\n"
    "- **💵 Live off it** — for *drawing income*. Enter your **capital**, the **monthly "
    "income** you want, and your **drawdown tolerance**. It ranks withdrawal runs by how much "
    "of that income they actually paid over 19 years (**coverage**) and how deep they drew "
    "down. Income runs are modeled at the $40k and $160k tiers today.\n\n"
    "Both tabs share a **Priority** slider — slide toward *protect capital* to weight "
    "drawdown, or toward *chase the goal* to weight return/income. Nothing is hard-filtered: "
    "the closest options always appear, and any config that breaches a limit you set is "
    "flagged in plain English (e.g. \"−28% exceeds your −25% limit\"). Each result links "
    "straight to its **Run Detail**, and a **How the Fit score works** expander shows the "
    "exact formula. If nothing fits — or your capital isn't one of the modeled tiers — it "
    "points you to **Request a Run** (next section) for your exact setup."
)
st.page_link("pages/6_Strategy_Finder.py", label="🎯  Open the Strategy Finder")

# ─────────────────────────────────────────────────────────────────────────
st.header("10 · Request a Run")
md(
    "Anyone can propose a new backtest from the **Request a Run** page — you fill a form, the "
    "operator runs it on the engine, and you click straight through to the results:\n"
    "1. **Fill the form** — give it a **scenario name** (and your name), then set the dials: "
    "spread width, trend filter, weekly risk %, the cap (or *Uncapped*), and withdrawals. The "
    "**Advanced** panel holds starting capital, the **short delta (5/10/15/20Δ)** and the "
    "friction/exit knobs (commission, slippage, profit target, stop loss, dates); its defaults "
    "are the validated settings. Hit **Submit** and the request appears below as **Pending**.\n"
    "2. **The operator runs it** on the backtest engine, then marks it **Complete** with the "
    "run's name (its queue label). Submitting is open to everyone; only the operator (with a "
    "passcode) can complete or delete a request.\n"
    "3. **Jump to results** — a completed request shows an **Open run →** link straight to its "
    "results, and the Run Detail page notes who requested it. Every pending request also has a "
    "**🔍 Full request details** view so the operator can see (or paste out) every setting."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("11 · Glossary")
md("Every metric on the dashboard, defined as it is computed here. All P&L is **net of "
   "commissions and slippage**; risk metrics use **monthly** returns with the 3-month "
   "T-bill as the risk-free rate.")
for _t, _d in TERMS.items():
    md(f"- **{_t}** — {_d}")

# ─────────────────────────────────────────────────────────────────────────
st.header("12 · Looking for the findings?")
md(
    "Everything interpretive — which configurations win at each risk level, what each dial "
    "really does, the getting-started ladder, the 2018 stress-test story, and the exit-rule "
    "experiments — lives on the **AI Analysis** page."
)
st.page_link("pages/4_AI_Analysis.py", label="🤖  Open the AI Analysis")

render_footer()
