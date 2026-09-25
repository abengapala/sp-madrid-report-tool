"""
ui/ptp_review.py — Step 4: PTP review screen.

UPDATED (this revision):
- core.output now only ever appends NEW PTP INVENTORY rows and never
  rewrites the sheet from a full dataframe (existing PTP rows are
  historical record and must never be regenerated/reordered). This
  screen now builds `ptp_new_rows_df` — just the confirmed "Add" rows —
  and stores that in session state instead of a merged ptp_df.
- The REPO icon condition was already checking for "REPO" in the action
  code/remark to flag it visually; left as-is since core.ptp's trigger
  itself is now the tightened "REPO + outcome word" match, so anything
  reaching this screen already cleared that bar.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from core.ptp import detect_ptp_activity, PTPCandidate, PTPResult


def render_ptp_review():
    st.markdown("## 💰 Step 4 — PTP Review")
    st.markdown(
        "Review PTP/KEPT/REPO activity detected across DRR and field file. "
        "Follow-ups on existing rows are applied automatically (they update the "
        "account's STATUS REMARKS as usual — no separate PTP INVENTORY row is added). "
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
    st.markdown("*These are auto-applied via the normal STATUS REMARKS update. No action needed.*")
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
        "Includes PTP, KEPT, and REPO(+outcome)-tagged entries for accounts **in the current book**."
    )

    ptp_decisions: dict[str, str] = {}

    if ptp_result.new_ptps:
        for i, candidate in enumerate(ptp_result.new_ptps):
            is_repo = "REPO" in candidate.action_code.upper() or "REPO" in candidate.remark.upper()
            with st.expander(
                f"{'🔴' if is_repo else '🟡'} "
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
        "These accounts have PTP/KEPT/REPO(+outcome) activity in the source files **but are NOT in the current book**. "
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
    from core.ptp import build_ptp_inventory_row

    to_add = []
    for i, candidate in enumerate(ptp_result.new_ptps):
        key = f"{i}_{candidate.pn}"
        if ptp_decisions.get(key) == "add":
            to_add.append(candidate)

    # Build ONLY the new rows — existing PTP INVENTORY rows are never
    # touched or regenerated; core.output appends this dataframe as-is.
    new_rows = [
        build_ptp_inventory_row(daily_df, c.pn, c, report_date)
        for c in to_add
    ]
    ptp_new_rows_df = pd.DataFrame(new_rows) if new_rows else pd.DataFrame(columns=ptp_df.columns)

    st.session_state["ptp_new_rows_df"] = ptp_new_rows_df
    st.session_state["ptp_added_count"] = len(new_rows)
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
