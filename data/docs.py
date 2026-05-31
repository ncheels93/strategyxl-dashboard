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
    st.page_link("pages/3_Guide.py", label="📖  Full guide, definitions & key findings")


# ─────────────────────────────────────────────────────────────────────────
# Glossary — term → plain-English definition (as THIS dashboard computes it)
# ─────────────────────────────────────────────────────────────────────────
TERMS = {
    "CAGR":
        "Compound annual growth rate — the steady yearly rate that would turn the "
        "starting capital into the ending equity over the full period. One annualized "
        "number that smooths out the good and bad years.",
    "Total Return":
        "The total percentage gain from the first day to the last — not annualized.",
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
    "Net Realized P&L":
        "Total booked profit/loss from closed trades, net of all commissions and slippage.",
    "Ending Equity":
        "The account value on the last day of the backtest.",
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
        "currently show. On the top three cards, the small line gives the *other two* "
        "metrics for that same run — so you can see the trade-off (the highest-CAGR run "
        "is rarely the smoothest). Click **Run #N** to open its detail.",
        ["CAGR", "Calmar", "Max Drawdown", "Sharpe", "Sortino", "Profit Factor"],
    ),
    "summary_scatter": (
        "Every run plotted by **return (CAGR, vertical)** against **worst-case drawdown "
        "(horizontal)**. Up = more return; right = smaller drawdown — so the most "
        "attractive runs sit toward the top-right. Colour = trend-filter MA, bubble size "
        "= Calmar. The gold ★ is S&P buy-and-hold and the dotted line is the efficient "
        "frontier. Click a dot to drill in; box/lasso-select several to compare.",
        ["CAGR", "Max Drawdown", "Calmar", "Efficient frontier", "S&P benchmark (★)"],
    ),
    "summary_group": (
        "A roll-up with one row per **group** (a sizing/withdrawal regime — e.g. RE50-WD), "
        "so you can compare regimes without scanning every run. *Median* is the typical "
        "run in the group; *Best* is its top run. Sorted by best Calmar.",
        ["CAGR", "Max Drawdown", "Calmar", "Sharpe"],
    ),
    "summary_leaderboard": (
        "Every run in the current filter, ranked. Use **Sort by** (or click a column "
        "header) to re-rank, and click a **Run #** to open its full detail.",
        ["CAGR", "Max Drawdown", "Calmar", "Annualized Volatility", "Sharpe", "Sortino",
         "Win Rate", "Profit Factor"],
    ),
    # ---- Run Detail ----
    "detail_kpis": (
        "Headline results for this one run — capital in and out, return, worst drawdown, "
        "and trade statistics.",
        ["Ending Equity", "Total Return", "CAGR", "Max Drawdown", "Net Realized P&L",
         "Win Rate", "Profit Factor", "Total Trades"],
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
        "payments.",
        ["Coverage", "Months Full / Partial / Zero"],
    ),
    "detail_tradelog": (
        "The full day-by-day record behind this run — each trading day's position, option "
        "prices, P&L, cash and equity. Use the filter to focus on entry / exit / open "
        "days; click a column header to sort.",
        [],
    ),
    # ---- Compare ----
    "compare_kpis": (
        "Side-by-side metrics for the selected runs; **green = best value in that row**. "
        "Withdrawal rows appear automatically when any selected run uses withdrawals.",
        ["CAGR", "Max Drawdown", "Calmar", "Sharpe", "Sortino", "Profit Factor", "Coverage"],
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
