"""Request a Run — submit a backtest scenario for the operator to run, then track it
through to its results. Anyone can submit; only the operator (passcode) can mark a
request complete or delete it."""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from data.db import (
    check_password_gate, render_footer, admin_unlocked,
    insert_request, load_requests, complete_request, reopen_request,
    delete_request, resolve_run_id,
)

st.set_page_config(page_title="Request a Run — StrategyXL", page_icon="📝", layout="wide")
check_password_gate()

st.title("Request a Backtest Run")
st.caption(
    "Fill out a scenario and submit it. The operator runs it on the backtest engine, "
    "marks it complete with its run name, and then you can click straight through to the "
    "results. Defaults below are the standard, validated settings — change only what you mean to."
)

# Trend-filter choices — match the universe build exactly.
MA_OPTIONS = ["Off", "ema_9", "ema_20", "ema_50", "ema_200", "sma_5", "sma_10",
              "sma_20", "sma_50", "sma_100", "sma_150", "sma_200", "sma_50>200"]


def _config_line(r) -> str:
    """One-line config summary for a request row ($ escaped so it doesn't render as math)."""
    parts = [
        f"width ${int(r['in_spread_width'])}",
        (r["in_trend_filter_ma"] if r["in_trend_filter_on"] else "no filter"),
        f"{float(r['in_weekly_risk_pct']) * 100:.0f}% / wk",
        ("uncapped" if pd.isna(r["in_max_weekly_risk"]) else f"cap ${float(r['in_max_weekly_risk']):,.0f}"),
    ]
    if r["in_withdrawals_on"]:
        parts.append(f"WD ${float(r['in_target_monthly_withdrawal'] or 0):,.0f}/mo, "
                     f"floor ${float(r['in_withdrawal_floor'] or 0):,.0f}")
    else:
        parts.append("no withdrawals")
    if float(r["in_slippage_per_leg"] or 0) > 0:
        parts.append(f"slippage ${float(r['in_slippage_per_leg']):.2f}/leg")
    return " · ".join(str(p) for p in parts).replace("$", "\\$")


def _money(v) -> str:
    return "—" if pd.isna(v) else f"${float(v):,.2f}"


def _pct(v) -> str:
    return "—" if pd.isna(v) else f"{float(v) * 100:.2f}%"


def _detail_md(r) -> str:
    """Full, paste-ready request detail as a markdown table — everything needed to run it."""
    wd_on = bool(r["in_withdrawals_on"])
    rows = [
        ("Requested by", r["requested_by"] or "—"),
        ("Submitted", str(r["requested_at"])[:16]),
        ("Status", r["status"]),
        ("Spread width", f"${int(r['in_spread_width'])}"),
        ("Trend filter", r["in_trend_filter_ma"] if r["in_trend_filter_on"] else "Off"),
        ("Weekly risk %", _pct(r["in_weekly_risk_pct"])),
        ("Max weekly risk", "Uncapped" if pd.isna(r["in_max_weekly_risk"]) else _money(r["in_max_weekly_risk"])),
        ("Withdrawals", "On" if wd_on else "Off"),
        ("Monthly withdrawal", _money(r["in_target_monthly_withdrawal"]) if wd_on else "—"),
        ("Withdrawal floor", _money(r["in_withdrawal_floor"]) if wd_on else "—"),
        ("Inflation adjust", _pct(r["in_inflation_adjust_pct"]) if wd_on else "—"),
        ("Starting capital", _money(r["in_starting_capital"])),
        ("Short delta", f"{float(r['in_short_delta_threshold']):.2f}"),
        ("Commission / contract", _money(r["in_commission_per_contract"])),
        ("Slippage / leg", _money(r["in_slippage_per_leg"])),
        ("1-DTE / OTM close", _pct(r["in_otm_close_threshold"])),
        ("Breach close", "On" if r["in_breach_close"] else "Off"),
        ("Profit target", _pct(r["in_profit_target"]) if pd.notna(r["in_profit_target"]) else "Off"),
        ("Stop loss", _pct(r["in_stop_loss"]) if pd.notna(r["in_stop_loss"]) else "Off"),
        ("Backtest range", f"{r['in_backtest_start']} → {r['in_backtest_end']}"),
    ]
    if pd.notna(r.get("result_queue_name")) and r.get("result_queue_name"):
        rows.append(("Run name (queue)", r["result_queue_name"]))
    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    name = str(r["scenario_name"]).replace("$", "\\$")
    table = ("| Field | Value |\n|---|---|\n" + body).replace("$", "\\$")
    return f"**Scenario:&nbsp; {name}**\n\n{table}"


# Exact column order of tbl_Scenario_Queue_Input in Excel (what Push_Scenario_Queue reads,
# cells 1..28). Emitting pending requests in THIS order lets the operator paste straight in.
QUEUE_COLS = [
    "Execute", "queue_label", "backtest_start", "backtest_end", "short_delta_threshold",
    "spread_width", "spread_handling", "product_mode", "starting_capital", "weekly_risk_pct",
    "max_weekly_risk", "target_cagr", "trend_filter_on", "trend_filter_ma", "breach_close",
    "otm_close_threshold", "profit_target", "stop_loss", "commission_per_contract",
    "slippage_per_leg", "mid_source", "entry_fill", "exit_fill", "withdrawals_on",
    "target_monthly_withdrawal", "withdrawal_floor", "withdrawal_start_date", "inflation_adjust_pct",
]


def _blank_if_null(v):
    return "" if pd.isna(v) else v


def _pending_to_queue_csv(pending: pd.DataFrame) -> str:
    """Pending requests → CSV in the exact Excel-queue column order, ready to paste into
    tbl_Scenario_Queue_Input. Locked/constant columns get the standard validated values;
    queue_label is left blank so the table's formula computes it on paste."""
    rows = []
    for _, r in pending.iterrows():
        wd_on = bool(r["in_withdrawals_on"])
        rows.append({
            "Execute": "Yes",
            "queue_label": "",  # Excel formula fills this in
            "backtest_start": str(r["in_backtest_start"]),
            "backtest_end": str(r["in_backtest_end"]),
            "short_delta_threshold": float(r["in_short_delta_threshold"]),
            "spread_width": int(r["in_spread_width"]),
            "spread_handling": "Skip",
            "product_mode": "Both",
            "starting_capital": float(r["in_starting_capital"]),
            "weekly_risk_pct": float(r["in_weekly_risk_pct"]),
            "max_weekly_risk": _blank_if_null(r["in_max_weekly_risk"]),
            "target_cagr": 0.10,
            "trend_filter_on": "Yes" if r["in_trend_filter_on"] else "No",
            "trend_filter_ma": r["in_trend_filter_ma"] if r["in_trend_filter_on"] else "",
            "breach_close": "Yes" if r["in_breach_close"] else "No",
            "otm_close_threshold": float(r["in_otm_close_threshold"]),
            "profit_target": _blank_if_null(r["in_profit_target"]),
            "stop_loss": _blank_if_null(r["in_stop_loss"]),
            "commission_per_contract": float(r["in_commission_per_contract"]),
            "slippage_per_leg": float(r["in_slippage_per_leg"]),
            "mid_source": "Calculated",
            "entry_fill": "Mid",
            "exit_fill": "Mid",
            "withdrawals_on": "Yes" if wd_on else "No",
            "target_monthly_withdrawal": float(r["in_target_monthly_withdrawal"] or 0) if wd_on else 0,
            "withdrawal_floor": _blank_if_null(r["in_withdrawal_floor"]) if wd_on else "",
            "withdrawal_start_date": str(r["in_backtest_start"]) if wd_on else "",
            "inflation_adjust_pct": _blank_if_null(r["in_inflation_adjust_pct"]) if wd_on else "",
        })
    return pd.DataFrame(rows, columns=QUEUE_COLS).to_csv(index=False)


# ─────────────────────────────────────────────────────────────────────────
# Submit form
# ─────────────────────────────────────────────────────────────────────────
# Plain widgets in a bordered container (NOT st.form) so the "Withdrawals on" checkbox
# can reveal/hide its inputs live and "Uncapped" can disable the cap field on the fly.
with st.container(border=True):
    st.subheader("New request")
    c1, c2 = st.columns(2)
    with c1:
        scenario_name = st.text_input("Scenario name *", placeholder="e.g. Conservative + 200-MA")
        requested_by = st.text_input("Your name", placeholder="optional")
        width = st.selectbox("Spread width", [50, 100, 200], index=1)
        ma = st.selectbox("Trend filter", MA_OPTIONS, index=1)
    with c2:
        risk_pct = st.number_input("Weekly risk %", min_value=1.0, max_value=100.0,
                                   value=50.0, step=5.0,
                                   help="Share of equity put at risk each week (before the cap).")
        uncapped = st.checkbox("Uncapped (no weekly $ cap)")
        cap = st.number_input("Max weekly risk ($)", min_value=1000, value=20000, step=5000,
                              disabled=uncapped, help="Hard ceiling on weekly dollars at risk — the risk dial.")
        withdrawals = st.checkbox("Withdrawals on")
        # WD inputs live directly under the checkbox and only appear when it's checked.
        if withdrawals:
            wd_monthly = st.number_input("Monthly withdrawal ($)", min_value=0, value=250, step=50)
            wd_floor = st.number_input("Withdrawal floor ($)", min_value=0, value=42500, step=2500,
                                       help="Withdrawals only skim equity ABOVE this floor.")
        else:
            wd_monthly, wd_floor = 0, None

    with st.expander("Advanced — friction, exits & dates (validated defaults)"):
        a1, a2, a3 = st.columns(3)
        with a1:
            start_cap = st.number_input("Starting capital ($)", min_value=1000, value=40000, step=5000)
            short_delta = st.selectbox("Short delta", options=[0.05, 0.10, 0.15, 0.20],
                                       index=1, format_func=lambda v: f"{v*100:g}Δ ({v:.2f})",
                                       help="Short-strike delta target. 10Δ is the core strategy; "
                                            "5Δ is the conservative variant, 15Δ the aggressive one. "
                                            "See the AI Analysis page before choosing 20Δ.")
            commission = st.number_input("Commission / contract ($)", min_value=0.0, value=0.65, step=0.05)
        with a2:
            slippage = st.number_input("Slippage / leg ($)", min_value=0.0, value=0.00, step=0.05)
            otm = st.number_input("1-DTE / OTM close %", min_value=0.0, value=2.0, step=0.5)
            breach = st.checkbox("Breach close", value=True)
        with a3:
            pt = st.number_input("Profit target % (0 = off)", min_value=0.0, value=0.0, step=5.0)
            sl = st.number_input("Stop loss % (0 = off)", min_value=0.0, value=0.0, step=5.0)
            infl = st.number_input("Inflation adjust % (withdrawals)", min_value=0.0, value=3.0, step=0.5)
        d1, d2 = st.columns(2)
        bt_start = d1.date_input("Backtest start", value=datetime.date(2007, 1, 3))
        bt_end = d2.date_input("Backtest end", value=datetime.date.today())

    submitted = st.button("Submit request", type="primary")

if submitted:
    if not scenario_name.strip():
        st.error("Scenario name is required.")
    else:
        inputs = {
            "in_spread_width": int(width),
            "in_trend_filter_on": 0 if ma == "Off" else 1,
            "in_trend_filter_ma": None if ma == "Off" else ma,
            "in_weekly_risk_pct": round(risk_pct / 100.0, 4),
            "in_max_weekly_risk": None if uncapped else float(cap),
            "in_withdrawals_on": 1 if withdrawals else 0,
            "in_target_monthly_withdrawal": float(wd_monthly) if withdrawals else 0,
            "in_withdrawal_floor": float(wd_floor) if withdrawals else None,
            "in_starting_capital": float(start_cap),
            "in_short_delta_threshold": round(short_delta, 4),
            "in_commission_per_contract": float(commission),
            "in_slippage_per_leg": float(slippage),
            "in_otm_close_threshold": round(otm / 100.0, 4),
            "in_breach_close": 1 if breach else 0,
            "in_profit_target": None if pt == 0 else round(pt / 100.0, 4),
            "in_stop_loss": None if sl == 0 else round(sl / 100.0, 4),
            "in_backtest_start": bt_start,
            "in_backtest_end": bt_end,
            "in_inflation_adjust_pct": round(infl / 100.0, 4),
        }
        try:
            insert_request(scenario_name.strip(), requested_by.strip(), inputs)
            st.success(f"Request '{scenario_name.strip()}' submitted — it'll appear below as Pending.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not submit the request: {e}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────
# Request lists — pending & completed
# ─────────────────────────────────────────────────────────────────────────
is_admin = admin_unlocked()
if not is_admin:
    st.caption("🔒 Enter the operator passcode in the sidebar to mark requests complete or delete them.")

reqs = load_requests()
pending = reqs[reqs["status"] == "Pending"]
completed = reqs[reqs["status"] == "Complete"].copy()

# ── Pending ──
st.subheader(f"Pending requests ({len(pending)})")
if is_admin and not pending.empty:
    st.download_button(
        "⬇️ Download queue CSV (paste into Excel)",
        data=_pending_to_queue_csv(pending),
        file_name="scenario_queue_paste.csv",
        mime="text/csv",
        help="All pending requests in the exact tbl_Scenario_Queue_Input column order. "
             "Paste the data rows into the Excel queue table; queue_label is left blank so "
             "its formula fills in (fill the formula down on the new rows).",
    )
if pending.empty:
    st.info("No pending requests right now.")
else:
    for _, r in pending.iterrows():
        with st.container(border=True):
            head = st.columns([4, 2, 2])
            head[0].markdown(f"**{str(r['scenario_name']).replace('$', chr(92) + '$')}**")
            head[1].caption(f"👤 {r['requested_by'] or '—'}")
            head[2].caption(f"🕓 {str(r['requested_at'])[:16]}")
            st.caption(_config_line(r))
            with st.popover("🔍 Full request details"):
                st.markdown(_detail_md(r))
            if is_admin:
                # A tiny form so pressing Enter in the queue_name box submits "Mark complete"
                # (a bare text_input + button needs an explicit button click — Enter alone
                # only commits the text and nothing happens).
                with st.form(key=f"complete_{r['request_id']}", clear_on_submit=False, border=False):
                    fc = st.columns([4, 1.4])
                    qn = fc[0].text_input(
                        "Run name (queue_name)",
                        placeholder="paste the run's queue_name, then Enter or click →",
                        label_visibility="collapsed",
                    )
                    done = fc[1].form_submit_button("✅ Mark complete", use_container_width=True,
                                                    type="primary")
                if done:
                    if qn.strip():
                        complete_request(int(r["request_id"]), qn.strip())
                        st.rerun()
                    else:
                        st.warning("Enter the queue_name first so the request links to its run.")
                if st.button("🗑 Delete", key=f"del_{r['request_id']}"):
                    delete_request(int(r["request_id"]))
                    st.rerun()

# ── Completed ──
st.subheader(f"Completed ({len(completed)})")
if completed.empty:
    st.info("No completed requests yet.")
else:
    # Resolve each queue_name to a run_id once, build a deep-link to Run Detail.
    qnames = [q for q in completed["result_queue_name"].dropna().unique()]
    id_map = {q: resolve_run_id(q) for q in qnames}
    completed["Run"] = completed["result_queue_name"].map(
        lambda q: (f"Run_Detail?run_id={id_map[q]}" if id_map.get(q) else None)
    )
    show = completed[["scenario_name", "requested_by", "requested_at",
                      "result_queue_name", "Run"]].copy()
    show.columns = ["Scenario Name", "Requester", "Submitted", "Queue name", "Run"]
    show["Submitted"] = show["Submitted"].astype(str).str[:16]
    st.dataframe(
        show, hide_index=True, use_container_width=True,
        column_config={
            "Run": st.column_config.LinkColumn(
                "Results", display_text="Open run →",
                help="Jumps to this request's run on the Run Detail page."),
            "Queue name": st.column_config.TextColumn(width="large"),
        },
    )
    # Note any queue_names that don't resolve yet (run not loaded / typo).
    missing = [q for q in qnames if not id_map.get(q)]
    if missing:
        st.caption("⚠️ These queue names don't match a loaded run yet (re-run pending or typo): "
                   + ", ".join(str(m) for m in missing[:5]).replace("$", "\\$"))
    if is_admin:
        with st.expander("Manage completed requests"):
            opts = {f"#{int(r.request_id)} · {r.scenario_name}": int(r.request_id)
                    for r in completed.itertuples()}
            pick = st.selectbox("Select a completed request", list(opts.keys()))
            _picked = completed[completed["request_id"] == opts[pick]].iloc[0]
            st.markdown(_detail_md(_picked))
            mc1, mc2 = st.columns(2)
            if mc1.button("↩ Reopen (back to pending)"):
                reopen_request(opts[pick])
                st.rerun()
            if mc2.button("🗑 Delete permanently"):
                delete_request(opts[pick])
                st.rerun()

render_footer()
