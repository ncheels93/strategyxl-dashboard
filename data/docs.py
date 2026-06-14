"""Shared documentation — single source of truth for term definitions, per-section
explainers, and helpers used by the popovers and the Guide page.

Defining everything here once means a metric like Sharpe reads identically in every
popover and in the full guide. `md()` escapes '$' so Streamlit never mis-renders a
dollar amount as LaTeX math.
"""

import streamlit as st


def _esc(text: str) -> str:
    # Streamlit pairs '$' into KaTeX math; escape so dollar amounts render literally.
    return text.replace("$", "\\$")


def md(text: str) -> None:
    st.markdown(_esc(text))


def caption(text: str) -> None:
    st.caption(_esc(text))


def guide_link() -> None:
    """Prominent link to the full Guide page — call at the top of each page."""
    st.page_link("pages/3_Guide.py", label="📖  Full guide & definitions")


# ─────────────────────────────────────────────────────────────────────────
# Capped sizing — friendly risk-profile names + the cap math (single source).
#   Weekly $ at risk = MIN(weekly_risk_pct × equity, max_weekly_risk).
#   % of account at risk = MIN(weekly_risk_pct, max_weekly_risk / equity): starts
#   at weekly_risk_pct and flattens to the cap as the account grows. The cap is the
#   risk dial — tighter = smoother. max_weekly_risk NULL/blank ⇒ uncapped.
# ─────────────────────────────────────────────────────────────────────────


def _isnull(v) -> bool:
    return v is None or (isinstance(v, float) and v != v)   # None or NaN


def risk_profile(max_weekly_risk) -> str:
    """Map the weekly $ cap to a friendly risk-tier word (the cap is the risk dial)."""
    if _isnull(max_weekly_risk):
        return "Maximum"          # uncapped = most aggressive
    try:
        c = float(max_weekly_risk)
    except (TypeError, ValueError):
        return "—"
    if c <= 20000:
        return "Conservative"
    if c <= 30000:
        return "Cautious"
    if c <= 50000:
        return "Moderate"
    return "Aggressive"


def cap_display(max_weekly_risk) -> str:
    """'$20k cap' or 'uncapped'."""
    if _isnull(max_weekly_risk):
        return "uncapped"
    try:
        return f"${float(max_weekly_risk) / 1000:.0f}k cap"
    except (TypeError, ValueError):
        return "—"


def profile_label(max_weekly_risk) -> str:
    """Friendly profile, e.g. 'Conservative · $20k cap' or 'Maximum · uncapped'."""
    return f"{risk_profile(max_weekly_risk)} · {cap_display(max_weekly_risk)}"


def capped_risk_pct(weekly_risk_pct, max_weekly_risk, equity) -> float:
    """The % of the account at risk in a week at a given equity level."""
    p = float(weekly_risk_pct)
    if _isnull(max_weekly_risk):
        return p
    return min(p, float(max_weekly_risk) / float(equity))


# ─────────────────────────────────────────────────────────────────────────
# Glossary — term → plain-English definition (as THIS dashboard computes it)
# ─────────────────────────────────────────────────────────────────────────
TERMS = {
    "Short Delta":
        "The delta of the put the strategy sells — roughly the option market's estimate of "
        "the chance it finishes in the money. Lower delta (5Δ) = further out-of-the-money: "
        "higher win rate, shallower drawdowns, less premium. Higher delta (15Δ/20Δ) = closer "
        "to the money: more premium, more frequent and deeper losses. 10Δ is the core "
        "strategy; the engine picks the strike closest to the target within a band around it.",
    "CAGR":
        "Compound annual growth rate — the steady yearly rate that would turn the "
        "starting capital into the ending equity over the full period. One annualized "
        "number that smooths out the good and bad years.",
    "Total Return":
        "The total percentage gain from the first day to the last — not annualized.",
    "Money-Weighted Return (XIRR)":
        "The internal rate of return on the actual cash flows — starting capital in, any "
        "withdrawals out, ending value — annualized (ACT/365.25). For a no-withdrawal run it "
        "equals CAGR; for a withdrawal run it credits the income taken along the way, so it's "
        "the honest apples-to-apples return across withdrawal and non-withdrawal runs.",
    "Total-Value Return":
        "For withdrawal runs: the cumulative return counting BOTH the ending equity AND every "
        "dollar withdrawn, versus starting capital. Plain Total Return is ending-equity only, so "
        "it understates a run that paid out income along the way.",
    "Max Drawdown":
        "The largest peak-to-trough drop in account equity at any point in the backtest "
        "— the worst decline from a prior high-water mark. The best single gauge of "
        "“how bad did it get.”",
    "Calmar":
        "CAGR ÷ |Max Drawdown|. Return earned per unit of worst-case pain — higher is "
        "better. A Calmar of 1.0 means each year's return roughly equals the worst drop.",
    "Annualized Volatility":
        "The standard deviation of monthly returns, scaled to a yearly figure (× √12) — "
        "how much the month-to-month results bounce around.",
    "Sharpe":
        "Risk-adjusted return: the average monthly return *above the risk-free rate* "
        "(the 3-month T-bill) divided by the volatility of those returns, annualized "
        "(× √12). Higher = more reward per unit of total wobble; above 1.0 is good.",
    "Sortino":
        "Like Sharpe, but it only counts *downside* wobble — months below 0% — and "
        "ignores upside swings. Average monthly return ÷ downside deviation, annualized. "
        "Rewards strategies whose volatility is mostly to the upside, so it usually reads "
        "higher than Sharpe.",
    "Win Rate":
        "The share of closed trades that finished profitable.",
    "Profit Factor":
        "Gross profit ÷ gross loss across all trades. Above 1 means winners outweigh "
        "losers; 2.0 means $2 earned for every $1 lost.",
    "Avg Win":
        "The average net P&L of the trades that finished profitable — typically small (the "
        "premium collected).",
    "Avg Loss":
        "The average net P&L of the losing trades (a negative number). It's several times "
        "larger than the average win here — and the *average* (not median) is the honest gauge "
        "because it captures the occasional big breach that a median would hide.",
    "Win/Loss Ratio":
        "Average win ÷ |average loss| — the payoff ratio. Below 1.0 means a typical win is "
        "smaller than a typical loss; this strategy stays profitable on a high win rate, not "
        "on big wins.",
    "Worst Loss":
        "The single largest losing trade over the backtest — the tail risk in one number.",
    "Net Realized P&L":
        "Total booked profit/loss from closed trades, net of all commissions and slippage. "
        "This is *only* the trading result — it does **not** include interest earned on cash.",
    "Starting Capital":
        "The account balance the backtest begins with — varies by scenario across this study "
        "($5k–$160k; $40k is the most common).",
    "Ending Equity":
        "The account value on the last day — **Starting Capital + Net Realized P&L + interest "
        "earned on idle cash − any withdrawals** (plus the mark-to-market of any still-open "
        "position). Interest on cash is why ending equity is *more* than starting + realized "
        "P&L — and it's sizeable for low-risk, cash-heavy runs.",
    "Max Weekly Risk":
        "The hard dollar ceiling on how much can be at risk in a single week — the cap in the "
        "sizing model. It equals the weekly-risk % of equity while the account is small, then "
        "holds flat at the cap once the account grows past it (so the % at risk falls). "
        "'Uncapped' means no ceiling — risk stays at the full % the whole way.",
    "Total Trades":
        "How many weekly spreads were actually entered — a trend filter or tight sizing "
        "can skip weeks, so this is usually below the number of weeks in the period.",
    "Coverage":
        "For withdrawal runs: the share of the targeted withdrawals that were actually "
        "paid over the whole backtest. 100% means every scheduled withdrawal was fully "
        "funded without ever breaching the floor.",
    "Months Full / Partial / Zero":
        "Each scheduled withdrawal month is **Full** (paid the entire inflation-adjusted "
        "target), **Partial** (paid only what it could without dropping below the floor), "
        "or **Zero** (already at/below the floor, so nothing was paid).",
    "% above 200-SMA":
        "How far the S&P closed above (or below, if negative) its 200-day simple moving "
        "average on the trade's entry day — a quick read on how stretched or weak the "
        "market was when the position was opened.",
    "Efficient frontier":
        "The dotted line connects the “best-in-class” runs: for any given drawdown level, "
        "the run on the line delivered the highest return. Any run below the line is "
        "beaten by one on it.",
    "Calmar rays":
        "The faint dashed lines fanning out from the origin are constant-Calmar lines. "
        "Because Calmar = CAGR ÷ |Max Drawdown| is exactly the slope of the line from (0,0) "
        "to a point, every dot on a given ray shares that Calmar — and a dot sitting above a "
        "steeper ray has a higher Calmar. A quick visual read of risk-adjusted return.",
    "S&P benchmark (★)":
        "The gold star marks buy-and-hold of the S&P 500 over the same period (price "
        "return). Runs up and to the right of it beat the index on *both* return and "
        "drawdown.",
}


# ─────────────────────────────────────────────────────────────────────────
# Per-section explainers — key → (what-it-shows markdown, [relevant term keys])
# ─────────────────────────────────────────────────────────────────────────
SECTIONS = {
    # ---- Summary ----
    "summary_cards": (
        "The single best run for each headline metric across whatever the filters "
        "currently show, in three rows:\n"
        "- **Return & risk** — Best CAGR, Best Calmar, Lowest Max DD. The small line under "
        "each gives the *other two* of these three for that same run, so you can see the "
        "trade-off (the highest-CAGR run is rarely the smoothest).\n"
        "- **Risk-adjusted** — Best Sharpe, Best Sortino, Best Profit Factor.\n"
        "- **Trade profile** — Highest Win Rate, Best Win/Loss Ratio, and Smallest Worst "
        "Loss (the single biggest losing trade). These capture the “lots of small wins, the "
        "occasional big loss” shape of the strategy; their small line shows the supporting "
        "win/loss figures.\n\n"
        "Click **Run #N** on any card to open its detail.\n\n"
        "**Sanity check:** a run that barely trades can post a flattering Calmar or Profit "
        "Factor on a tiny sample — a tight cap at the $200 width may "
        "take very few positions until equity grows. If a card looks too good, confirm its "
        "**Total Trades** in the leaderboard before trusting it.",
        ["CAGR", "Calmar", "Max Drawdown", "Sharpe", "Sortino", "Profit Factor",
         "Win Rate", "Win/Loss Ratio", "Worst Loss", "Avg Win", "Avg Loss"],
    ),
    "summary_scatter": (
        "Every run plotted by **return (CAGR, vertical)** against **worst-case drawdown "
        "(horizontal)**. Up = more return; right = smaller drawdown — so the most "
        "attractive runs sit toward the top-right. Colour = trend-filter MA, bubble size "
        "= Calmar. The gold ★ is S&P buy-and-hold and the dotted line is the efficient "
        "frontier.\n\n"
        "The faint **dashed rays from the origin are constant-Calmar lines** — because Calmar "
        "= CAGR ÷ |Max DD| is the slope from (0,0), a dot sitting above a steeper ray has a "
        "higher Calmar, so you can read risk-adjusted return straight off the chart.\n\n"
        "Click a dot to drill in; box/lasso-select several to compare.",
        ["CAGR", "Max Drawdown", "Calmar", "Calmar rays", "Efficient frontier", "S&P benchmark (★)"],
    ),
    "summary_breakdowns": (
        "A set of roll-ups — one row per category — across several dimensions (use the tabs): "
        "**short delta**, **spread width**, **starting capital**, **max weekly risk** (the risk "
        "dial), **trend filter**, and **withdrawals**. Each row shows the **median** CAGR / Max DD / "
        "Calmar (the typical run in that bucket), the **best** CAGR / Calmar / Sharpe (its top "
        "run), and the **win/loss profile** (Median Avg Loss, Median W/L). Because every bucket "
        "spans the same surrounding configs, each tab isolates what that one dimension does. "
        "Structural tabs are sorted naturally (small → large); the Trend filter tab is sorted by "
        "Median Calmar.",
        ["Short Delta", "CAGR", "Max Drawdown", "Calmar", "Sharpe", "Avg Loss", "Win/Loss Ratio"],
    ),
    "summary_leaderboard": (
        "Every run in the current filter, ranked. Use **Sort by** (or click a column "
        "header) to re-rank, and click a **Run #** to open its full detail.",
        ["CAGR", "Money-Weighted Return (XIRR)", "Max Drawdown", "Calmar",
         "Annualized Volatility", "Sharpe", "Sortino",
         "Win Rate", "Profit Factor", "Avg Win", "Avg Loss", "Win/Loss Ratio", "Worst Loss"],
    ),
    # ---- Run Detail ----
    "detail_kpis": (
        "Headline results for this one run — capital in and out, return, worst drawdown, "
        "the weekly risk cap, and trade statistics.",
        ["Starting Capital", "Ending Equity", "Total Return", "CAGR",
         "Money-Weighted Return (XIRR)", "Max Drawdown",
         "Max Weekly Risk", "Net Realized P&L", "Win Rate", "Profit Factor", "Total Trades"],
    ),
    "detail_risk": (
        "Risk-adjusted measures, all computed from **monthly** returns and annualized.",
        ["Annualized Volatility", "Sharpe", "Sortino", "Calmar"],
    ),
    "detail_drawdown": (
        "Two views on one chart: **drawdown from the running peak** (blue, left axis — "
        "how far below the high-water mark) and **cumulative return from the start** "
        "(green, right axis — your profit cushion). When the green dips below 0%, equity "
        "has fallen back into the starting capital.",
        ["Max Drawdown"],
    ),
    "detail_top10": (
        "The ten biggest winning and losing trades, each with the market context at "
        "entry — where the S&P sat versus its moving averages when the position opened. "
        "Useful for seeing what conditions produced the outliers.",
        ["Net Realized P&L", "% above 200-SMA"],
    ),
    "detail_withdrawals": (
        "How the withdrawal plan played out: how much was taken, what share of the "
        "target that covered, and a month-by-month breakdown of full / partial / skipped "
        "payments. The **Total-Value Return** counts the income already paid out (not just "
        "ending equity), and the **per-year income chart + table** shows how much was "
        "withdrawn each year against the inflation-adjusted target.",
        ["Coverage", "Months Full / Partial / Zero", "Total-Value Return"],
    ),
    "detail_tradelog": (
        "The full day-by-day record behind this run — each trading day's position, option "
        "prices, P&L, cash and equity. The **Spread $** column (beside the long strike) is the "
        "actual width = short − long; it can land up to 10% under the nominal width when the "
        "exact long strike isn't listed. Use the filter to focus on entry / exit / open "
        "days; click a column header to sort.",
        [],
    ),
    # ---- Compare ----
    "compare_kpis": (
        "Side-by-side metrics for the selected runs; **green = best value in that row**. "
        "Withdrawal rows appear automatically when any selected run uses withdrawals.",
        ["CAGR", "Money-Weighted Return (XIRR)", "Total-Value Return", "Max Drawdown",
         "Calmar", "Sharpe", "Sortino", "Profit Factor", "Coverage"],
    ),
    "compare_criteria": (
        "Only the inputs that **differ** across the selected runs — i.e. the knobs that "
        "actually distinguish them. Identical inputs are hidden.",
        [],
    ),
    "compare_curves": (
        "The selected runs' **cumulative-return** and **drawdown** paths overlaid, so you "
        "can see how each behaved through the same markets (and, for withdrawal runs, how "
        "fast each drew the account down).",
        ["Max Drawdown"],
    ),
}


def explain(key: str, label: str = "ⓘ  What is this?") -> None:
    """Render a small popover next to a section header, with its blurb + relevant terms."""
    blurb, terms = SECTIONS[key]
    with st.popover(label):
        md(blurb)
        defined = [t for t in terms if t in TERMS]
        if defined:
            st.markdown("---")
            st.markdown("**Terms in this section**")
            for t in defined:
                md(f"- **{t}** — {TERMS[t]}")
