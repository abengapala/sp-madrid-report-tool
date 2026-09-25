"""
ui/generate.py — Step 5: Generate and download the encrypted report.

UPDATED (this revision):
- generate_download's signature changed: it now edits `source_wb` (the
  actual decrypted original workbook) in place instead of building a
  fresh one, and takes `ptp_new_rows_df` (just the confirmed additions)
  instead of a full merged PTP dataframe — existing PTP INVENTORY rows
  are never passed back through the writer, since they must never be
  regenerated or reordered.
- Summary now reports PTP additions from `ptp_added_count` /
  `ptp_new_rows_df` rather than diffing ptp_df against original_ptp
  (that diff doesn't exist anymore since we don't build a merged ptp_df).
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_generate():
    st.markdown("## 📥 Step 5 — Generate Report")
    st.markdown(
        f"All decisions have been confirmed. Click **Generate** to build the encrypted `.xlsx` "
        f"for **{st.session_state['report_date'].strftime('%B %d, %Y')}**."
    )

    if st.button("⚡ Generate Report", type="primary", key="btn_generate"):
        _generate()

    if "output_bytes" in st.session_state:
        _render_summary()
        report_date = st.session_state['report_date']
        fname = f"SP_MADRID_Recovery_Status_Report_{report_date.strftime('%B_%d_%Y')}.xlsx"
        raw_bytes = st.session_state["output_bytes"]
        if hasattr(raw_bytes, "read"):
            raw_bytes = raw_bytes.read()
        raw_bytes = bytes(raw_bytes)
        st.download_button(
            label=f"📥 Download Encrypted Report — {report_date.strftime('%B %d, %Y')}",
            data=raw_bytes,
            file_name=fname,
            mime="application/octet-stream",
            key="btn_download",
        )
        st.success(f"Password: **{st.session_state.get('password', 'cbs1234')}**")

    col_back, _ = st.columns([1, 4])
    with col_back:
        if st.button("← Back", key="gen_back"):
            st.session_state["step"] = 4
            st.rerun()


def _generate():
    from core.output import generate_download
    from core.trails import rebuild_trails

    daily_df: pd.DataFrame = st.session_state["daily_df"]
    ptp_new_rows_df: pd.DataFrame = st.session_state.get(
        "ptp_new_rows_df", pd.DataFrame(columns=st.session_state["report_sheets"]["PTP INVENTORY"].columns)
    )
    source_wb = st.session_state.get("source_wb")
    drr_df = st.session_state.get("drr_df")
    existing_trails = st.session_state["report_sheets"]["Trails Upload"]
    report_date: pd.Timestamp = st.session_state["report_date"]
    password = st.session_state.get("password", "cbs1234")

    if source_wb is None:
        st.error("❌ Source workbook is missing — cannot edit in place. Re-upload the report and start over.")
        return

    with st.spinner("Building Trails Upload..."):
        trails_df, blanked_pns = rebuild_trails(daily_df, drr_df, existing_trails, report_date)
        st.session_state["final_trails"] = trails_df
        st.session_state["final_blanked"] = blanked_pns

    with st.spinner("Updating workbook in place and encrypting..."):
        try:
            output_bytes = generate_download(
                source_wb, daily_df, trails_df, ptp_new_rows_df, password
            )
            st.session_state["output_bytes"] = output_bytes
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to generate report: {e}")


def _render_summary():
    st.markdown("---")
    st.markdown("## 📊 Change Summary")

    daily_df: pd.DataFrame = st.session_state["daily_df"]
    original_daily: pd.DataFrame = st.session_state["report_sheets"]["DAILY"]
    ptp_added_count = st.session_state.get("ptp_added_count", 0)
    ptp_new_rows_df = st.session_state.get("ptp_new_rows_df", pd.DataFrame())
    original_ptp: pd.DataFrame = st.session_state["report_sheets"]["PTP INVENTORY"]
    ptp_result = st.session_state.get("ptp_result")
    zero_pns = st.session_state.get("zero_activity_pns", [])
    changed_fv_pns = st.session_state.get("changed_fv_pns", [])
    repo_ai_added_pns = st.session_state.get("repo_ai_added_pns", [])
    blanked_pns = st.session_state.get("final_blanked", [])
    trails_df = st.session_state.get("final_trails", pd.DataFrame())
    report_date: pd.Timestamp = st.session_state["report_date"]

    orig_pns = set(original_daily["PN"].astype(str))
    new_pns = set(daily_df["PN"].astype(str))
    added = new_pns - orig_pns
    dropped = orig_pns - new_pns  # should normally be empty — nothing here drops accounts

    st.markdown(f"### Report Date: {report_date.strftime('%B %d, %Y')}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Accounts", len(daily_df))
    col2.metric("Added", len(added), delta=f"+{len(added)}" if added else None)
    col3.metric("Dropped", len(dropped), delta=f"-{len(dropped)}" if dropped else None, delta_color="inverse")
    col4.metric("New PTP INVENTORY Rows", ptp_added_count, delta=f"+{ptp_added_count}" if ptp_added_count else None)

    st.markdown("---")

    st.markdown("**STATUS REMARKS Updates**")
    changed_sr = _count_changed(original_daily, daily_df, "STATUS REMARKS")
    st.markdown(f"- `{changed_sr}` accounts updated")
    if zero_pns:
        st.markdown(f"- ⚪ `{len(zero_pns)}` accounts with **no new DRR activity** (zero-effort list):")
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        for pn in zero_pns:
            st.markdown(f"  - `{pn}` — {pn_to_name.get(pn, '')}")

    st.markdown("---")

    st.markdown("**FV REMARKS Updates**")
    st.markdown(f"- `{len(changed_fv_pns)}` accounts updated")
    if repo_ai_added_pns:
        st.markdown(f"- 🏗️ `{len(repo_ai_added_pns)}` account(s) had a REPO AI entry mirrored into FV REMARKS:")
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        for pn in repo_ai_added_pns:
            st.markdown(f"  - `{pn}` — {pn_to_name.get(pn, '')}")

    st.markdown("---")

    st.markdown("**Trails Upload**")
    active_trails = len(trails_df) - len(blanked_pns)
    st.markdown(f"- `{active_trails}` accounts with activity | `{len(blanked_pns)}` blank (no activity on report date)")
    if blanked_pns:
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        with st.expander("Blank Trails accounts"):
            for pn in blanked_pns:
                st.markdown(f"- `{pn}` — {pn_to_name.get(pn, '')}")

    st.markdown("---")

    st.markdown("**PTP Activity**")
    if ptp_result:
        followups = len(ptp_result.followup_ptps)
        out_of_book = len(ptp_result.out_of_book_ptps)
        st.markdown(
            f"- `{followups}` follow-ups on existing PTP rows (auto-applied)\n"
            f"- `{ptp_added_count}` new row(s) added to PTP INVENTORY\n"
            f"- `{out_of_book}` out-of-book flags (not added)"
        )
        if ptp_added_count and not ptp_new_rows_df.empty:
            for _, r in ptp_new_rows_df.iterrows():
                st.markdown(f"  - `{r.get('PN')}` — {r.get('NAME', '')}")

    if added:
        st.markdown("---")
        st.markdown("**New accounts added to report:**")
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        for pn in sorted(added):
            st.markdown(f"- `{pn}` — {pn_to_name.get(pn, '')}")

    if dropped:
        st.markdown("**⚠️ Accounts missing from the updated list (unexpected — nothing in this tool drops accounts):**")
        pn_to_name_orig = {str(r["PN"]): str(r.get("NAME", "")) for _, r in original_daily.iterrows()}
        for pn in sorted(dropped):
            st.markdown(f"- `{pn}` — {pn_to_name_orig.get(pn, '')}")


def _count_changed(orig_df, new_df, col):
    orig_lookup = {str(r["PN"]): str(r.get(col, "") or "") for _, r in orig_df.iterrows()}
    new_lookup = {str(r["PN"]): str(r.get(col, "") or "") for _, r in new_df.iterrows()}
    return sum(1 for pn, val in new_lookup.items() if val.strip() != orig_lookup.get(pn, "").strip())
