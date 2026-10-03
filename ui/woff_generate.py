"""
ui/woff_generate.py -- Write-Off Step 3: Generate and download the report.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_woff_generate():
    st.markdown("## \U0001f7e5 Write-Off Report — Step 3: Generate Report")

    updated_df  = st.session_state.get("woff_updated_df")
    source_wb   = st.session_state.get("woff_source_wb")
    new_field   = st.session_state.get("woff_new_field_df", pd.DataFrame())
    report_date = st.session_state.get("woff_report_date", pd.Timestamp.today().normalize())
    password    = st.session_state.get("woff_password", "cbs1234")

    if updated_df is None or source_wb is None:
        st.error("Missing updated data. Go back to Step 2 and run the update first.")
        if st.button("\u2190 Back", key="woff_gen_back_early"):
            st.session_state["woff_step"] = 2
            st.rerun()
        return

    st.markdown(
        f"Ready to generate the Write-Off report for **{report_date.strftime('%B %d, %Y')}**."
        f" {len(updated_df)} accounts will be updated."
    )

    if st.button("\u26a1 Generate Write-Off Report", type="primary", key="woff_gen_btn"):
        _generate(updated_df, source_wb, new_field, password, report_date)

    if "woff_output_bytes" in st.session_state:
        rd = st.session_state["woff_report_date"]
        fname = f"SP_MADRID_CBS AUTO WRITEOFF STATUS REPORT as of {rd.strftime('%m%d%Y')}.xlsx"
        raw = st.session_state["woff_output_bytes"]
        if hasattr(raw, "read"):
            raw = raw.read()
        raw = bytes(raw)

        st.markdown("---")
        st.success("\u2705 Write-Off report generated successfully!")
        st.download_button(
            label=f"\U0001f4e5 Download Write-Off Report — {rd.strftime('%B %d, %Y')}",
            data=raw,
            file_name=fname,
            mime="application/octet-stream",
            key="woff_gen_download",
        )
        st.info(f"File password: **{password}**")

    st.markdown("---")
    col_back, _ = st.columns([1, 4])
    with col_back:
        if st.button("\u2190 Back", key="woff_gen_back"):
            st.session_state["woff_step"] = 2
            st.rerun()


def _generate(updated_df, source_wb, new_field, password, report_date):
    from core.woff import generate_woff_download

    with st.spinner("Writing and encrypting..."):
        try:
            output_bytes = generate_woff_download(source_wb, updated_df, new_field, password)
            st.session_state["woff_output_bytes"] = output_bytes
        except Exception as e:
            st.error(f"Failed to generate output: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    st.rerun()
