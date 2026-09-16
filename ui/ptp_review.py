"""
ui/ptp_review.py — Step 4: PTP review screen.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from core.ptp import detect_ptp_activity, PTPCandidate, PTPResult


def render_ptp_review():
    st.markdown("## 💰 Step 4 — PTP Review")
    st.markdown(
        "Review PTP/KEPT/REPO activity detected across DRR and field file. "
        "Follow-ups on existing rows are applied automatically. "
        "New candidates require your explicit decision."
    )

    daily_df: pd.DataFrame = st.session_state["daily_df"]
    drr_df = st.session_state.get("drr_df")
    field_df = st.session_state.get("field_df")
    ptp_df: pd.DataFrame = st.session_state["report_sheets"]["PTP INVENTORY"]
    report_date: pd.Timestamp = st.session_state["report_date"]

    current_pns = {str(r["PN"]).strip() for _, r in daily_df.iterrows()}

    if "ptp_result" not in st.session_state:
        with st.spinner("Scanning for PTP/KEPT/REPO activity..."):
            ptp_result = detect_ptp_activity(drr_df, field_df, current_pns, ptp_df, daily_df)
            st.session_state["ptp_result"] = ptp_result

    ptp_result: PTPResult = st.session_state["ptp_result"]

    # --- Section A: Follow-ups (auto-applied, informational) ---
    st.markdown("### ✅ Section A — Follow-ups on Existing PTP INVENTORY Rows")
    st.markdown("*These are auto-applied. No action needed.*")
    if ptp_result.followup_ptps:
        rows = _candidates_to_df(ptp_result.followup_ptps)
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No follow-up PTP activity detected.")

    st.markdown("---")

    # --- Section B: New / Ambiguous (need user decision) ---
    st.markdown("### ❓ Section B — New / Ambiguous PTP Candidates")
    st.markdown(
        "Each candidate below needs an explicit **Add** or **Skip** decision. "
        "Includes PTP, KEPT, and REPO-tagged entries for accounts **in the current book**."
    )

    ptp_decisions: dict[str, str] = {}  # pn -> "add" | "skip"

    if ptp_result.new_ptps:
        for i, candidate in enumerate(ptp_result.new_ptps):
            with st.expander(
                f"{'🔴' if 'REPO' in candidate.action_code.upper() or 'REPO' in candidate.remark.upper() else '🟡'} "
                f"`{candidate.pn}` — {candidate.name} | Source: {candidate.source} | "
                f"Code: {candidate.action_code or 'N/A'}",
                expanded=True,
            ):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**Remark:** {candidate.remark}")
                    if candidate.ptp_amount:
                        st.markdown(f"**PTP Amount:** {candidate.ptp_amount:,.2f}")
                    if candidate.ptp_date:
                        st.markdown(f"**PTP Date:** {candidate.ptp_date.strftime('%m/%d/%Y')}")
                    if candidate.date:
                        st.markdown(f"**Entry Date:** {candidate.date.strftime('%m/%d/%Y')}")
                with col2:
                    decision = st.radio(
                        "Decision",
                        options=["Add to PTP INVENTORY", "Skip"],
                        key=f"ptp_decision_{i}_{candidate.pn}",
                        index=1,  # Default: Skip (never auto-add)
                    )
                    ptp_decisions[f"{i}_{candidate.pn}"] = (
                        "add" if decision == "Add to PTP INVENTORY" else "skip"
                    )
    else:
        st.info("No new PTP candidates detected.")

    st.session_state["ptp_decisions"] = ptp_decisions
    st.session_state["ptp_result"] = ptp_result

    st.markdown("---")

    # --- Section C: Out-of-book (report only) ---
    st.markdown("### 🔍 Section C — Out-of-Book PTP Flags *(informational only)*")
    st.markdown(
        "These accounts have PTP/KEPT/REPO activity in the source files **but are NOT in the current book**. "
        "No action will be taken — shown here so nothing is silently skipped."
    )
    if ptp_result.out_of_book_ptps:
        rows = _candidates_to_df(ptp_result.out_of_book_ptps)
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No out-of-book PTP flags.")

    st.markdown("---")
    col_back, col_confirm = st.columns([1, 3])
    with col_back:
        if st.button("← Back", key="ptp_back"):
            del st.session_state["ptp_result"]
            st.session_state["step"] = 3
            st.rerun()
    with col_confirm:
        if st.button("✅ Confirm PTP Decisions & Continue", type="primary", key="ptp_confirm"):
            _apply_and_advance(ptp_result, ptp_decisions, ptp_df, daily_df, report_date)


def _apply_and_advance(ptp_result, ptp_decisions, ptp_df, daily_df, report_date):
    from core.ptp import apply_ptp_decisions

    # Collect candidates to add
    to_add = []
    for i, candidate in enumerate(ptp_result.new_ptps):
        key = f"{i}_{candidate.pn}"
        if ptp_decisions.get(key) == "add":
            to_add.append(candidate)

    updated_ptp = apply_ptp_decisions(ptp_df, daily_df, to_add, report_date)
    st.session_state["ptp_df"] = updated_ptp
    st.session_state["step"] = 5
    st.rerun()


def _candidates_to_df(candidates: list[PTPCandidate]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "PN": c.pn,
            "Name": c.name,
            "Source": c.source,
            "Action Code": c.action_code,
            "Remark": c.remark[:120] + "..." if len(c.remark) > 120 else c.remark,
            "PTP Amount": c.ptp_amount,
            "PTP Date": c.ptp_date.strftime("%m/%d/%Y") if c.ptp_date else "",
            "Date": c.date.strftime("%m/%d/%Y") if c.date else "",
        }
        for c in candidates
    ])
