"""Guide & methodology — the full long-form document for the dashboard."""

from __future__ import annotations

import streamlit as st

from data.db import check_password_gate, render_footer
from data.docs import TERMS, md

st.set_page_config(page_title="Guide — StrategyXL", page_icon="📖", layout="wide")
check_password_gate()

st.title("Guide, Definitions & Key Findings")
st.caption("Everything you need to read this dashboard — what the strategy is, how the "
           "controls work, what every number means, and what the results say.")

# ─────────────────────────────────────────────────────────────────────────
st.header("1 · What this is")
md(
    "This dashboard backtests a **weekly S&P 500 put credit spread**. Each Friday "
    "(or the Thursday before a holiday) the strategy:\n"
    "- **sells** an out-of-the-money put on the S&P 500 (SPX) about 10-delta — roughly a "
    "strike the market would have to fall to before the option matters,\n"
    "- **buys** a further-out put below it (the “width”, e.g. $50/$100/$200 lower) as a "
    "defined-risk hedge,\n"
    "- **collects the net premium** and holds ~7 days to expiration, closing early on a "
    "breach or a 1-DTE rule.\n\n"
    "You win the premium when the market doesn't fall sharply through your short strike — "
    "which is most weeks. The risk is a fast, deep drop. The whole point of this dashboard "
    "is to show, across **396 backtested configurations (2007–2026)**, how different "
    "sizing, trend-filter and withdrawal choices trade return against that downside."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("2 · How the dashboard is organized")
md(
    "- **Summary** — compare all runs at once: best-in-class cards, the CAGR-vs-drawdown "
    "scatter (with the S&P star and efficient frontier), a by-group roll-up, and the full "
    "leaderboard. The sidebar filters narrow everything on the page.\n"
    "- **Run Detail** — drill into one run: full KPIs, risk-adjusted metrics, equity & "
    "drawdown charts, the ten biggest winners/losers with entry context, and (if used) the "
    "withdrawal breakdown.\n"
    "- **Compare** — put 2–4 runs side by side: a metric table with the best value in each "
    "row highlighted, the inputs that differ, and overlaid return/drawdown curves.\n\n"
    "Every section has an **ⓘ What is this?** popover with a quick explanation and the "
    "definitions relevant to it."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("3 · The sizing model (the important one)")
md(
    "How big a position each week gets is the single biggest driver of both return and "
    "drawdown. Three controls interact:\n\n"
    "1. **Base Trading Cap** — the dollar exposure deployed each week when the account is "
    "at its starting value (default $20k on a $40k account).\n"
    "2. **Upside Reinvestment %** — once equity climbs above the starting capital, this is "
    "the share of those profits added back into the weekly cap. **0% = flat sizing** (never "
    "scale up — the account grows only from premium, not bigger positions). **50% = "
    "redeploy half of every dollar of profit.** **100% = full compounding** (most "
    "aggressive). This dial is what separates the FIX runs (0%) from RE25/RE50/RE100.\n"
    "3. **The gated ceiling — Max Gross % of Equity + Activation Equity** — a brake for the "
    "large-account regime. It does *nothing* until equity reaches the **Activation** level "
    "(default $200k); above that, the weekly cap can't exceed **Max Gross % × equity** "
    "(default 25%). It caps how big the reinvestment engine can push you once you're large.\n\n"
    "**How they combine:** Upside Reinvest scales you *up* with profits; the ceiling caps "
    "how big that can get at scale. With reinvest at 0% the ceiling never binds (the flat "
    "cap is always well under 25% of a grown account), which is why the FIX runs ignore it."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("4 · The trend filter")
md(
    "Optionally, the strategy only opens a new spread when the S&P closes **above a chosen "
    "moving average** (e.g. the 50- or 200-day). When the market is below that line, it "
    "sits in cash for the week. Runs labelled **(filter off)** take every weekly entry; "
    "runs tagged with an MA (e.g. `sma_200`) only trade in uptrends — so filter-off runs "
    "have the most trades. As the cycle table below shows, the filter's biggest value is in "
    "slow, grinding bear markets, where it keeps the strategy out of harm's way for months."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("5 · Withdrawals")
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
st.header("6 · Reading a group code & the filters")
md(
    "Each run carries a short **group code** in its label that encodes the regime, e.g. "
    "**`RE50-WD-100k`**:\n"
    "- **`FIX`** = 0% reinvest (flat sizing); **`RE25/RE50/RE100`** = that upside-reinvest %.\n"
    "- **`c35`** / **`a100k`** suffixes = a non-default ceiling (35% Max Gross) or activation "
    "($100k) — only shown when changed from the 25% / $200k defaults.\n"
    "- **`-NW`** = no withdrawals; **`-WD`** = withdrawals on.\n"
    "- a trailing **`-100k`** = a non-default starting capital ($100k instead of $40k).\n\n"
    "The sidebar **Group** filter jumps straight to any regime; the **Sizing** filters "
    "(reinvest %, max gross %, activation, starting capital) and **Strategy** filters "
    "(trend MA, width, withdrawals) slice across regimes. All filters combine."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("7 · Glossary")
md("Every metric on the dashboard, defined as it is computed here. All P&L is **net of "
   "commissions and slippage**; risk metrics use **monthly** returns with the 3-month "
   "T-bill as the risk-free rate.")
for _t, _d in TERMS.items():
    md(f"- **{_t}** — {_d}")

# ─────────────────────────────────────────────────────────────────────────
st.header("8 · Key findings")

st.subheader("Versus simply holding the S&P")
md(
    "Over 2007–2026 the S&P 500 returned about **9% a year (price) with a −56.8% worst "
    "drawdown**. The strategy's appeal is a far smoother ride for comparable or better "
    "return: the conservative configuration (**FIX-NW**) earned ~**11.7% CAGR with only a "
    "−16% max drawdown** — beating the index on return with under a third of the pain. More "
    "aggressive reinvestment pushed CAGR into the **20–27%** range, but with drawdowns of "
    "**−30% to −44%**. On the scatter, nearly the entire field sits up-and-left of the S&P "
    "★ — more return, less drawdown."
)

st.subheader("The reinvestment dial sets the risk/return")
md(
    "Moving from flat sizing to full compounding is a clean trade of smoothness for growth: "
    "**FIX** ~9–12% CAGR (≈ −16% DD) → **RE50** ~14–22% (≈ −28 to −30% DD) → **RE100** "
    "~16–25% (≈ −30 to −44% DD). The best *risk-adjusted* runs (highest Calmar) tend to be "
    "the moderate ones — e.g. **RE50 with an early ($100k) activation** or **RE25** — which "
    "is where the efficient frontier bends."
)

st.subheader("How it held up through market cycles")
md(
    "Peak-to-trough **equity drawdown** within each major selloff, for a conservative run "
    "(FIX-NW), a moderate run (RE50-NW, filter off), and that same moderate run with the "
    "**200-day trend filter** on — versus the S&P 500:"
)
st.markdown(
    "| Market cycle | S&P 500 | Conservative | Moderate | Moderate + 200-MA filter |\n"
    "|---|--:|--:|--:|--:|\n"
    "| GFC (2007–2009) | −56.8% | −24.5% | −26.0% | **−2.2%** |\n"
    "| 2011 selloff | −19.4% | −16.1% | −30.3% | −23.2% |\n"
    "| 2018 Q4 | −19.8% | −7.0% | −14.1% | −10.1% |\n"
    "| COVID crash (2020) | −33.9% | −13.1% | −28.6% | −15.3% |\n"
    "| 2022 bear market | −25.4% | −8.6% | −23.7% | **−8.6%** |\n"
)
md(
    "**Takeaways:**\n"
    "- **Conservative sizing rode through every selloff at a fraction of the index's "
    "drawdown** — most starkly the GFC (−24.5% vs −56.8%), COVID (−13.1% vs −33.9%) and "
    "2022 (−8.6% vs −25.4%).\n"
    "- **The 200-day trend filter was the standout in slow, grinding bears.** It sat out "
    "almost all of 2008 (−2.2% vs the index's −56.8%) and 2022 (−8.6% vs −25.4%) because "
    "the S&P spent those stretches below its 200-day average, so the strategy simply "
    "stopped entering.\n"
    "- **The trade-off:** aggressive sizing *without* a filter drew down close to the index "
    "in fast shocks (COVID −28.6%, the 2011 flash selloff −30.3%) — reinvested gains mean "
    "bigger positions when a sudden drop hits, and a fast crash falls through the short "
    "strike before a trend filter can react.\n"
    "- **One caveat:** 2011 was the lone cycle where some configurations underperformed the "
    "index on drawdown — a sharp, whipsawing selloff that punished both leverage and the "
    "filter."
)

st.subheader("Withdrawals — what the account can sustain")
md(
    "On a $40k account, ~**$100/mo** was fully sustainable (100% coverage) for the "
    "conservative configs at $50/$100 width. Stepping up to **$250/mo on $40k** only worked "
    "for some configurations — coverage fell as low as ~35% at the $200 width. Raising "
    "starting capital to **$100k funded $250/mo comfortably at every width (100% coverage)**. "
    "The lesson is the obvious-but-important one: withdrawal sustainability is about the "
    "withdrawal rate relative to account size, not the strategy tweak."
)

render_footer()
