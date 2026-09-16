"""
ui/generate.py — Step 5: Generate and download the encrypted report.
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

    # If already generated, show download
    if "output_bytes" in st.session_state:
        _render_summary()
        report_date = st.session_state['report_date']
        fname = f"SP_MADRID_Recovery_Status_Report_{report_date.strftime('%B_%d_%Y')}.xlsx"
        # Ensure it's raw bytes, not BytesIO (UUID filename bug workaround)
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
    ptp_df: pd.DataFrame = st.session_state.get("ptp_df", st.session_state["report_sheets"]["PTP INVENTORY"])
    action_code_df: pd.DataFrame = st.session_state["report_sheets"]["ACTION CODE"]
    source_wb = st.session_state.get("source_wb")
    drr_df = st.session_state.get("drr_df")
    existing_trails = st.session_state["report_sheets"]["Trails Upload"]
    report_date: pd.Timestamp = st.session_state["report_date"]
    password = st.session_state.get("password", "cbs1234")

    with st.spinner("Building Trails Upload..."):
        trails_df, blanked_pns = rebuild_trails(daily_df, drr_df, existing_trails, report_date)
        st.session_state["final_trails"] = trails_df
        st.session_state["final_blanked"] = blanked_pns

    with st.spinner("Assembling and encrypting workbook..."):
        try:
            output_bytes = generate_download(
                daily_df, trails_df, ptp_df, action_code_df, source_wb, password
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
    ptp_df: pd.DataFrame = st.session_state.get("ptp_df", st.session_state["report_sheets"]["PTP INVENTORY"])
    original_ptp: pd.DataFrame = st.session_state["report_sheets"]["PTP INVENTORY"]
    ptp_result = st.session_state.get("ptp_result")
    zero_pns = st.session_state.get("zero_activity_pns", [])
    changed_fv_pns = st.session_state.get("changed_fv_pns", [])
    blanked_pns = st.session_state.get("final_blanked", [])
    trails_df = st.session_state.get("final_trails", pd.DataFrame())
    report_date: pd.Timestamp = st.session_state["report_date"]

    # Account counts
    orig_pns = set(original_daily["PN"].astype(str))
    new_pns = set(daily_df["PN"].astype(str))
    added = new_pns - orig_pns
    dropped = orig_pns - new_pns

    st.markdown(f"### Report Date: {report_date.strftime('%B %d, %Y')}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Accounts", len(daily_df))
    col2.metric("Added", len(added), delta=f"+{len(added)}" if added else None)
    col3.metric("Dropped", len(dropped), delta=f"-{len(dropped)}" if dropped else None, delta_color="inverse")
    col4.metric("PTP INVENTORY Rows", len(ptp_df))

    st.markdown("---")

    # STATUS REMARKS summary
    st.markdown("**STATUS REMARKS Updates**")
    changed_sr = _count_changed(original_daily, daily_df, "STATUS REMARKS")
    st.markdown(f"- `{changed_sr}` accounts updated")
    if zero_pns:
        st.markdown(f"- ⚪ `{len(zero_pns)}` accounts with **no new DRR activity** (zero-effort list):")
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        for pn in zero_pns:
            st.markdown(f"  - `{pn}` — {pn_to_name.get(pn, '')}")

    st.markdown("---")

    # FV REMARKS summary
    st.markdown("**FV REMARKS Updates**")
    st.markdown(f"- `{len(changed_fv_pns)}` accounts updated")

    st.markdown("---")

    # Trails Upload summary
    st.markdown("**Trails Upload**")
    active_trails = len(trails_df) - len(blanked_pns)
    st.markdown(f"- `{active_trails}` accounts with activity | `{len(blanked_pns)}` blank (no activity on report date)")
    if blanked_pns:
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        with st.expander("Blank Trails accounts"):
            for pn in blanked_pns:
                st.markdown(f"- `{pn}` — {pn_to_name.get(pn, '')}")

    st.markdown("---")

    # PTP summary
    st.markdown("**PTP Activity**")
    if ptp_result:
        followups = len(ptp_result.followup_ptps)
        new_added = len(ptp_df) - len(original_ptp)
        out_of_book = len(ptp_result.out_of_book_ptps)
        st.markdown(
            f"- `{followups}` follow-ups on existing PTP rows\n"
            f"- `{new_added}` new rows added to PTP INVENTORY\n"
            f"- `{out_of_book}` out-of-book flags (not added)"
        )

    if added:
        st.markdown("---")
        st.markdown("**New accounts added to report:**")
        pn_to_name = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        for pn in sorted(added):
            st.markdown(f"- `{pn}` — {pn_to_name.get(pn, '')}")

    if dropped:
        st.markdown("**Accounts dropped from report:**")
        pn_to_name_orig = {str(r["PN"]): str(r.get("NAME", "")) for _, r in original_daily.iterrows()}
        for pn in sorted(dropped):
            st.markdown(f"- `{pn}` — {pn_to_name_orig.get(pn, '')}")


def _count_changed(orig_df, new_df, col):
    orig_lookup = {str(r["PN"]): str(r.get(col, "") or "") for _, r in orig_df.iterrows()}
    new_lookup = {str(r["PN"]): str(r.get(col, "") or "") for _, r in new_df.iterrows()}
    return sum(1 for pn, val in new_lookup.items() if val.strip() != orig_lookup.get(pn, "").strip())
