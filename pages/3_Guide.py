"""Guide & methodology — the full long-form document for the dashboard."""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go

from data.db import check_password_gate, render_footer
from data.docs import TERMS, md, capped_risk_pct

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
    "is to show, across **a systematic grid of 390 backtested configurations "
    "(2007–2026)**, how different sizing, trend-filter and withdrawal choices trade "
    "return against that downside."
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
    "row highlighted, the inputs that differ, overlaid return/drawdown curves, and a "
    "**trade-by-trade table** of every week each run traded (filterable to losers, a year, "
    "or just the weeks where the runs diverged).\n"
    "- **Request a Run** — submit a new scenario to backtest (spread width, trend filter, "
    "weekly risk %, cap, withdrawals, and the friction/exit knobs). It joins a queue the "
    "operator runs; once it's complete you can click straight from the request to its results.\n\n"
    "Every section has an **ⓘ What is this?** popover with a quick explanation and the "
    "definitions relevant to it."
)
md(
    "**Requesting a run.** Anyone can propose a new backtest on the **Request a Run** page:\n"
    "1. **Fill the form** — a **scenario name** (and your name), then the dials: spread "
    "width, trend filter, weekly risk %, the cap (or *Uncapped*), and withdrawals. The "
    "**Advanced** panel holds the friction/exit knobs (commission, slippage, profit target, "
    "stop loss, dates); its defaults are the validated settings, and short delta is locked at "
    "the 0.10 core strategy. Hit **Submit** and the request appears below as **Pending**.\n"
    "2. **The operator runs it** on the backtest engine, then marks it **Complete** with the "
    "run's name (its queue label). Submitting is open to everyone; only the operator (a "
    "passcode) can complete or delete a request.\n"
    "3. **Jump to results** — a completed request shows an **Open run →** link straight to its "
    "results, and the Run Detail page notes who requested it. Every pending request also has a "
    "**🔍 Full request details** view so the operator can see (or paste out) every setting."
)

# ─────────────────────────────────────────────────────────────────────────
st.header("3 · The sizing model (the important one)")
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
st.header("4 · The trend filter")
md(
    "Optionally, the strategy only opens a new spread when the S&P closes **above a chosen "
    "moving average** (e.g. the 50- or 200-day). When the market is below that line, it "
    "sits in cash for the week. Runs labelled **(filter off)** take every weekly entry; "
    "runs tagged with an MA (e.g. the 200-day SMA) only trade in uptrends — so filter-off runs "
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
    "Each run carries a short **group code** in its label that encodes the sizing, e.g. "
    "**W50-C20k-WD**:\n"
    "- **W50** = Weekly Risk % — 50% of the account at risk each week.\n"
    "- **C20k** = the cap — never more than $20k at risk in a week (Uncap = no cap).\n"
    "- **-NW** = no withdrawals; **-WD** = withdrawals on.\n\n"
    "The **tail of the full label** carries the exit & friction settings — e.g. "
    "**No PT / No SL** (no profit target or stop loss), **PT 50%** when a profit target is "
    "on, plus a flag if breach-close, commission, or slippage differs from the standard. "
    "You rarely need to read the raw code — the **Risk profile** name (Conservative → "
    "Maximum) says the same thing in plain language. The sidebar **Risk profile** filter "
    "jumps straight to a tier; the **Sizing** filters (weekly risk %, cap) and **Strategy** "
    "filters (trend MA, width, withdrawals) slice across everything. All filters combine."
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

st.subheader("Versus simply holding the S&P 500")
md(
    "Over 2007–2026 the S&P 500 returned roughly **9% a year (price) with a −56.8% worst "
    "drawdown**. Every configuration here rides a small fraction of that pain. The table is "
    "the peak-to-trough equity drawdown inside each major selloff for three representative "
    "runs — all 50% weekly risk, width $100, no withdrawals — versus the index:"
)
md(
    "| Market cycle | S&P 500 | Conservative ($20k cap) | Aggressive (uncapped) | Conservative + 200-day filter |\n"
    "|---|--:|--:|--:|--:|\n"
    "| GFC (2007–2009) | −56.8% | **−6.9%** | −6.9% | **−1.9%** |\n"
    "| 2011 selloff | −19.4% | **−5.1%** | −5.1% | −13.7% |\n"
    "| 2018 (vol spike + Q4) | −19.8% | −10.3% | −20.4% | −17.1% |\n"
    "| COVID crash (2020) | −33.9% | **−7.4%** | −20.1% | −15.3% |\n"
    "| 2022 bear market | −25.4% | **−7.0%** | −21.3% | −5.3% |\n"
)
md(
    "**Full-period:** Conservative ($20k cap) **8.3% CAGR / −10.3% max DD**; Aggressive "
    "(uncapped) **15.6% / −23.1%**; the 200-day-filter run **8.5% / −17.1%**.\n\n"
    "**Takeaways:**\n"
    "- **The conservative cap rode every crisis in single digits to low teens** — GFC −6.9%, "
    "COVID −7.4%, 2022 −7.0% — versus the index's −34% to −57%. That is the whole pitch: "
    "S&P-like return with a fraction of the drawdown.\n"
    "- **The cap is what absorbs the later crises.** The GFC and 2011 are identical for the "
    "$20k and uncapped runs — the account was still small, so both risked the same ~50%. By "
    "2018–2022 the account had grown, and the uncapped run rode those selloffs at full 50% "
    "(−20%+), while the $20k cap held its exposure flat (−7 to −10%).\n"
    "- **2018 is the binding drawdown** for the conservative cap (−10.3%), not 2008 — the "
    "February-2018 vol spike is this strategy's real stress test.\n"
    "- **The 200-day trend filter is a mixed bag.** It shines in the slow GFC grind (−1.9%, "
    "it sat out 2008) and in 2022, but it *whipsawed* in the sharp 2011 and 2018 selloffs "
    "(−13.7%, −17.1%) by re-entering right before fast drops. The faster 9-day EMA filter "
    "(the Conservative column) was steadier overall."
)

st.subheader("The cap is the risk dial")
md(
    "Holding everything else fixed (50% weekly risk, 9-day EMA filter, width $100, no "
    "withdrawals) and turning only the cap, return and drawdown move together — and the "
    "**tightest cap wins on a risk-adjusted basis**:"
)
md(
    "| Cap (risk profile) | CAGR | Max DD | Calmar |\n"
    "|---|--:|--:|--:|\n"
    "| $20k — Conservative | 8.3% | −10.3% | **0.81** |\n"
    "| $30k — Cautious | 9.8% | −13.3% | 0.73 |\n"
    "| $50k — Moderate | 11.5% | −20.4% | 0.56 |\n"
    "| $75k — Aggressive | 12.6% | −20.4% | 0.62 |\n"
    "| Uncapped — Maximum | 15.6% | −23.1% | 0.68 |\n"
)
md(
    "Loosening the cap buys CAGR but drawdown grows faster, so risk-adjusted return (Calmar) "
    "is best at the **$20k cap** — which is also the original *“risk $20k, keep a $20k "
    "buffer”* plan. Tighter = smoother; uncapped = the most growth for the most pain."
)

st.subheader("A surprising amount of the return is interest on cash")
md(
    "Because the conservative caps keep most of the account in cash, **interest on that cash "
    "(the 3-month T-bill rate, compounded daily) is a real contributor**, not a rounding "
    "error. On a representative $20k-cap run, of the ~$148k total gain on a $40k start (the "
    "account ends near $188k), about **$34k — roughly a quarter — was interest**, not option "
    "premium. The Run "
    "Detail page breaks every run into Starting Capital + Net Realized P&L + Interest so you "
    "can see the split."
)

st.subheader("Withdrawals — what the account can sustain")
md(
    "Drawing **$250/mo from a $40k account at 50% weekly risk is marginal** — it funded most "
    "of the income but pulled the account down toward its floor (coverage ~90%, deep "
    "drawdowns). The cap barely helps: a withdrawing account rarely grows enough for the cap "
    "to bind, so the binding constraint is the **withdrawal rate relative to account size**, "
    "not the sizing. A bigger starting balance or a smaller monthly draw is the lever."
)

render_footer()
