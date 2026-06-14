"""Strategy Finder — match a person's goals to the best-fitting backtested configs.

Pure, deterministic scoring over the existing run KPIs — NO live AI call. Every
recommendation is a ranked best-fit against what the user enters; the scoring
rubric is shown on the page so there is no black box. Two modes:
  • Grow it    — reinvested growth, ranked on CAGR + drawdown (full capital grid)
  • Live off it — cash income, ranked on coverage/income delivered + drawdown
                  (withdrawal runs; modeled at the $40k and $160k tiers today)
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data.db import load_scenario_runs, check_password_gate, render_footer
from data.docs import md

st.set_page_config(page_title="Strategy Finder — StrategyXL", page_icon="🎯", layout="wide")
check_password_gate()

st.title("Strategy Finder")
st.caption("Tell it your goals; it ranks the backtested configurations by how well they fit. "
           "This is a plain scoring of stored results — no AI call, instant and reproducible. "
           "Backtested results, not investment advice; past performance doesn't guarantee future returns.")

# ─────────────────────────────────────────────────────────────────────────
df = load_scenario_runs().copy()
if df.empty:
    st.warning("No scenarios in the database yet.")
    st.stop()

CORE_BATCH_IDS = (1, 2, 3, 4)          # same core grid the AI Analysis uses
df = df[pd.to_numeric(df["batch_id"], errors="coerce").isin(CORE_BATCH_IDS)].copy()

def _n(s):
    return pd.to_numeric(s, errors="coerce")

df["cagr"]   = _n(df["kpi_cagr"]) * 100
df["maxdd"]  = _n(df["kpi_max_dd_pct"]) * 100        # negative
df["ddabs"]  = df["maxdd"].abs()
df["calmar"] = _n(df["kpi_calmar"])
df["cap"]    = _n(df["in_starting_capital"])
df["cov"]    = _n(df["kpi_coverage_pct"]) * 100
df["inc"]    = _n(df["kpi_avg_monthly_income"])
df["worstmo"] = _n(df["kpi_worst_single_month"])

def delta_disp(v):  v = pd.to_numeric(v, errors="coerce"); return f"{v*100:g}Δ" if pd.notna(v) else "—"
def width_disp(v):  v = pd.to_numeric(v, errors="coerce"); return f"${int(v)}" if pd.notna(v) else "—"
def risk_disp(v):   v = pd.to_numeric(v, errors="coerce"); return f"{v*100:g}%" if pd.notna(v) else "—"
def cap_disp(v):    v = pd.to_numeric(v, errors="coerce"); return f"${v/1000:g}k" if pd.notna(v) else "Uncapped"
def filt_disp(v):   return v if isinstance(v, str) and v.strip() else "None"

def _nearest(value, choices):
    return min(choices, key=lambda c: abs(c - value))

def band_fit(x, lo, hi, scale):
    """1.0 inside [lo,hi]; linear decay to 0 over `scale` units outside."""
    if lo <= x <= hi:
        return 1.0
    d = (lo - x) if x < lo else (x - hi)
    return max(0.0, 1.0 - d / scale)

def dd_fit(ddabs, tol, scale=10.0):
    """1.0 if drawdown within tolerance; decays beyond it (soft, never a hard cut)."""
    if ddabs <= tol:
        return 1.0
    return max(0.0, 1.0 - (ddabs - tol) / scale)

def _config_cols(d):
    return pd.DataFrame({
        "Run #": "Run_Detail?run_id=" + d["run_id"].astype(int).astype(str),
        "Δ": d["in_short_delta_threshold"].map(delta_disp),
        "Width": d["in_spread_width"].map(width_disp),
        "Capital": d["cap"].map(lambda v: f"${v/1000:g}k"),
        "Filter": d["in_trend_filter_ma"].map(filt_disp),
        "Weekly risk": d["in_weekly_risk_pct"].map(risk_disp),
        "Risk cap": d["in_max_weekly_risk"].map(cap_disp),
    }, index=d.index)

_LINKCOL = st.column_config.LinkColumn("Run #", display_text=r"run_id=(\d+)", width="small")

grow_tab, live_tab = st.tabs(["📈  Grow it", "💵  Live off it"])

# ═════════════════════════════════════════════════════════════════════════
# GROW IT  — reinvested growth
# ═════════════════════════════════════════════════════════════════════════
with grow_tab:
    g = df[df["in_withdrawals_on"] != True].dropna(subset=["cagr", "ddabs", "cap"]).copy()
    tiers = sorted(t for t in g["cap"].dropna().unique())
    md("**You reinvest everything and let it compound.** Enter your account size and goals; "
       "the finder ranks every growth configuration at your capital tier by how closely it "
       "matches. Drawdown tolerance is *soft* — a config a little past your limit can still "
       "appear if it nails the rest, flagged so you can see it.")

    c1, c2, c3 = st.columns(3)
    with c1:
        cap_in = st.number_input("Capital to deploy ($)", min_value=1000, value=40000,
                                 step=1000, key="g_cap")
        inc_in = st.number_input("Avg monthly income wanted ($, optional)", min_value=0,
                                 value=0, step=100, key="g_inc",
                                 help="Reinvested-growth view: this converts to a required "
                                      "annual return and is used as a reality check.")
    with c2:
        cagr_lo = st.number_input("Target CAGR — min (%)", value=10.0, step=1.0, key="g_clo")
        cagr_hi = st.number_input("Target CAGR — max (%)", value=18.0, step=1.0, key="g_chi")
    with c3:
        dd_tol = st.number_input("Max drawdown I can stand (%)", min_value=1.0, value=25.0,
                                 step=1.0, key="g_dd",
                                 help="Enter as a positive number, e.g. 25 means −25%.")
        w_ret = st.slider("Priority", 0, 100, 50, key="g_w",
                          help="0 = protect capital (weight drawdown), 100 = chase returns "
                               "(weight CAGR). 50 = balanced.") / 100.0

    if cagr_hi < cagr_lo:
        cagr_lo, cagr_hi = cagr_hi, cagr_lo
    cap_tier = _nearest(cap_in, tiers)
    if abs(cap_tier - cap_in) > 1:
        st.info(f"Matched to the **${cap_tier/1000:g}k** modeled tier (closest of "
                f"{', '.join(f'${t/1000:g}k' for t in tiers)} to your ${cap_in:,.0f}). "
                "Use **Request a Run** to test your exact capital.")

    req_cagr = (inc_in * 12 / cap_in * 100) if inc_in > 0 else None
    if req_cagr is not None:
        verdict = ("✅ realistic" if req_cagr <= cagr_hi else
                   "⚠️ above your CAGR range" if req_cagr <= 25 else
                   "🚩 beyond anything the strategy has done — raise capital or lower the target")
        md(f"Your income goal of **${inc_in:,.0f}/mo** on **${cap_in:,.0f}** needs a "
           f"**~{req_cagr:.1f}%/yr** return — {verdict}.")

    cand = g[g["cap"] == cap_tier].copy()
    if cand.empty:
        st.warning("No growth runs at that capital tier.")
    else:
        cand["f_cagr"] = cand["cagr"].map(lambda x: band_fit(x, cagr_lo, cagr_hi, 8.0))
        cand["f_dd"]   = cand["ddabs"].map(lambda x: dd_fit(x, dd_tol))
        cand["fit"]    = (w_ret * cand["f_cagr"] + (1 - w_ret) * cand["f_dd"]) * 100
        cand["mo"]     = cap_tier * cand["cagr"] / 100 / 12

        def _note(r):
            if r["ddabs"] > dd_tol:
                return f"⚠ −{r['ddabs']:.0f}% drawdown exceeds your −{dd_tol:.0f}% limit"
            if r["cagr"] < cagr_lo:
                return f"below your {cagr_lo:g}% CAGR goal"
            if r["cagr"] > cagr_hi:
                return "above your CAGR goal (bonus)"
            return "✓ within all your targets"
        cand["Notes"] = cand.apply(_note, axis=1)

        top = cand.sort_values(["fit", "calmar"], ascending=False).head(10)
        out = _config_cols(top)
        out["CAGR"] = top["cagr"]; out["Max DD"] = top["maxdd"]
        out["Calmar"] = top["calmar"]; out["≈ $/mo (yr 1)"] = top["mo"]
        out["Fit"] = top["fit"]; out["Notes"] = top["Notes"]

        st.dataframe(out, hide_index=True, use_container_width=True, column_config={
            "Run #": _LINKCOL,
            "CAGR": st.column_config.NumberColumn(format="%.1f%%"),
            "Max DD": st.column_config.NumberColumn(format="%.1f%%"),
            "Calmar": st.column_config.NumberColumn(format="%.2f"),
            "≈ $/mo (yr 1)": st.column_config.NumberColumn(format="$%,.0f"),
            "Fit": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
        })
        st.caption("“≈ $/mo (yr 1)” is the first-year average monthly profit at your capital "
                   "(it compounds upward over time). Click a Run # to open its full detail.")

# ═════════════════════════════════════════════════════════════════════════
# LIVE OFF IT  — cash withdrawals
# ═════════════════════════════════════════════════════════════════════════
with live_tab:
    w = df[df["in_withdrawals_on"] == True].dropna(subset=["cap", "ddabs"]).copy()
    wtiers = sorted(t for t in w["cap"].dropna().unique())
    md("**You draw a monthly income** (inflation-adjusted, never below a floor). The finder "
       "ranks withdrawal runs by how much of your target they actually paid over 19 years "
       "(**coverage**) and how deep they drew down. Income runs are modeled at the "
       f"{', '.join(f'${t/1000:g}k' for t in wtiers)} tiers today — use **Request a Run** for others.")

    c1, c2 = st.columns(2)
    with c1:
        lcap_in = st.number_input("Capital to deploy ($)", min_value=1000, value=40000,
                                  step=1000, key="l_cap")
        ldd_tol = st.number_input("Max drawdown I can stand (%)", min_value=1.0, value=25.0,
                                  step=1.0, key="l_dd")
    with c2:
        linc_in = st.number_input("Monthly income wanted ($)", min_value=50, value=400,
                                  step=50, key="l_inc")
        lw_ret = st.slider("Priority", 0, 100, 50, key="l_w",
                           help="0 = protect capital, 100 = chase the income. 50 = balanced.") / 100.0

    lcap_tier = _nearest(lcap_in, wtiers)
    if abs(lcap_tier - lcap_in) > 1:
        st.info(f"Matched to the **${lcap_tier/1000:g}k** modeled tier (closest to your "
                f"${lcap_in:,.0f}).")

    lcand = w[w["cap"] == lcap_tier].copy()
    if lcand.empty:
        st.warning("No withdrawal runs at that capital tier.")
    else:
        # income axis: did it deliver your target (60%), and was it sustainable (40% coverage)
        lcand["meets"] = (lcand["inc"] / linc_in).clip(upper=1.0).fillna(0)
        lcand["f_inc"] = 0.6 * lcand["meets"] + 0.4 * (lcand["cov"] / 100).clip(upper=1.0)
        lcand["f_dd"]  = lcand["ddabs"].map(lambda x: dd_fit(x, ldd_tol))
        lcand["fit"]   = (lw_ret * lcand["f_inc"] + (1 - lw_ret) * lcand["f_dd"]) * 100

        best_inc = lcand["inc"].max()
        if pd.notna(best_inc) and best_inc < linc_in:
            md(f"🚩 **No modeled config sustainably pays ${linc_in:,.0f}/mo on "
               f"${lcap_tier/1000:g}k.** The best delivers about **${best_inc:,.0f}/mo**. "
               "Consider more capital or a smaller draw (see §7 of the AI Analysis).")

        def _lnote(r):
            if r["ddabs"] > ldd_tol:
                return f"⚠ −{r['ddabs']:.0f}% exceeds your −{ldd_tol:.0f}% limit"
            if pd.notna(r["inc"]) and r["inc"] < linc_in:
                return f"pays ~${r['inc']:,.0f}/mo of your ${linc_in:,.0f} goal"
            if pd.notna(r["cov"]) and r["cov"] < 90:
                return f"front-loads (covers {r['cov']:.0f}% of its target)"
            return "✓ meets your income within your drawdown limit"
        lcand["Notes"] = lcand.apply(_lnote, axis=1)

        ltop = lcand.sort_values(["fit", "cov"], ascending=False).head(10)
        lout = _config_cols(ltop)
        lout["Target/mo"] = _n(ltop["in_target_monthly_withdrawal"])
        lout["Avg paid/mo"] = ltop["inc"]; lout["Coverage"] = ltop["cov"]
        lout["Max DD"] = ltop["maxdd"]; lout["Worst mo"] = ltop["worstmo"]
        lout["Fit"] = ltop["fit"]; lout["Notes"] = ltop["Notes"]

        st.dataframe(lout, hide_index=True, use_container_width=True, column_config={
            "Run #": _LINKCOL,
            "Target/mo": st.column_config.NumberColumn(format="$%,.0f"),
            "Avg paid/mo": st.column_config.NumberColumn(format="$%,.0f"),
            "Coverage": st.column_config.NumberColumn(format="%.0f%%"),
            "Max DD": st.column_config.NumberColumn(format="%.1f%%"),
            "Worst mo": st.column_config.NumberColumn(format="$%,.0f"),
            "Fit": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
        })
        st.caption("“Coverage” = share of the monthly target actually paid over 19 years. "
                   "Click a Run # to open its full detail.")

# ─────────────────────────────────────────────────────────────────────────
with st.expander("How the Fit score works (no AI — just arithmetic)"):
    md(
        "Every candidate is scored 0–100 on how well it matches *your* inputs, then ranked. "
        "All criteria are **soft** — nothing is hard-filtered out, so the closest options "
        "always appear, with any breached limit flagged in **Notes**.\n\n"
        "- **Grow it:** `Fit = priority × CAGR-fit + (1−priority) × drawdown-fit`. CAGR-fit is "
        "1.0 inside your target range and fades over the ~8 points outside it; drawdown-fit is "
        "1.0 within your tolerance and fades ~10 points beyond. Capital snaps to the nearest "
        "modeled tier (KPIs are specific to account size).\n"
        "- **Live off it:** `Fit = priority × income-fit + (1−priority) × drawdown-fit`, where "
        "income-fit blends *how much of your target it paid* (60%) with *coverage* (40%) so a "
        "config that front-loads income then runs dry is penalised.\n\n"
        "The “priority” slider just moves weight between chasing the goal and protecting "
        "capital. Because it's pure arithmetic on stored results, the same inputs always give "
        "the same ranking."
    )

render_footer()
