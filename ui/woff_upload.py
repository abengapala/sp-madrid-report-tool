"""
ui/woff_upload.py -- Write-Off Step 1: Upload source files.

Completely separate from Recovery. Uploads:
  1. Current Write-Off Status Report (.xlsx encrypted)
  2. DRR file for this week (Friday cutoff)
  3. OVERALL FIELD file (field visits)
"""
from __future__ import annotations

import io
import streamlit as st
import pandas as pd


def render_woff_upload():
    st.markdown("## \U0001f7e5 Write-Off Report — Step 1: Upload Files")
    st.markdown(
        "Upload the source files for the **Friday** Write-Off report. "
        "These are independent from the Recovery report — upload the DRR "
        "and field file as of **this Friday's** cutoff."
    )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### \U0001f4c4 Write-Off Status Report")
        woff_file = st.file_uploader(
            "Current Write-Off Report (.xlsx, encrypted cbs1234)",
            type=["xlsx"],
            key="woff_upload_report",
        )
        woff_pw = st.text_input(
            "Write-Off report password",
            value="cbs1234",
            type="password",
            key="woff_upload_pw",
        )

    with col2:
        st.markdown("### \U0001f4c5 Report Date (Friday)")
        report_date = st.date_input(
            "This Friday's report date",
            value=pd.Timestamp.today().normalize().to_pydatetime(),
            key="woff_date_input",
        )

    st.markdown("---")
    st.markdown("### \U0001f4ca DRR File")
    drr_file = st.file_uploader(
        "DRR (.xlsx or .csv) — as of this Friday",
        type=["xlsx", "csv", "xls"],
        key="woff_upload_drr",
    )

    st.markdown("### \U0001f3e2 Field File (OVERALL FIELD)")
    field_file = st.file_uploader(
        "OVERALL FIELD file (.xlsx or .csv)",
        type=["xlsx", "csv", "xls"],
        key="woff_upload_field",
    )

    st.markdown("---")

    all_ready = woff_file is not None
    if not all_ready:
        st.info("Upload the Write-Off Status Report to continue. DRR and Field files are optional but recommended.")

    if all_ready:
        if st.button("\u26a1 Load & Parse Files", type="primary", key="woff_btn_parse"):
            _parse_and_advance(woff_file, woff_pw, drr_file, field_file, pd.Timestamp(report_date))


def _parse_and_advance(woff_file, woff_pw, drr_file, field_file, report_date):
    from core.woff import load_woff_report
    from core.file_io import parse_drr, parse_field, set_date_anchor

    set_date_anchor(report_date)

    with st.spinner("Decrypting Write-Off report..."):
        try:
            woff_bytes = woff_file.read()
            woff_df, field_sheet_df, source_wb = load_woff_report(woff_bytes, woff_pw)
        except Exception as e:
            st.error(f"Failed to load Write-Off report: {e}")
            return

    st.session_state["woff_df_loaded"] = woff_df
    st.session_state["woff_field_sheet_df"] = field_sheet_df
    st.session_state["woff_source_wb"] = source_wb
    st.session_state["woff_source_bytes"] = woff_bytes
    st.session_state["woff_password"] = woff_pw
    st.session_state["woff_report_date"] = report_date

    if drr_file is not None:
        with st.spinner("Parsing DRR..."):
            try:
                drr_bytes = drr_file.read()
                drr_df = parse_drr(drr_bytes, drr_file.name)
                st.session_state["woff_drr_df"] = drr_df
            except Exception as e:
                st.warning(f"DRR parse warning: {e}")
                st.session_state["woff_drr_df"] = None
    else:
        st.session_state["woff_drr_df"] = None

    if field_file is not None:
        with st.spinner("Parsing Field file..."):
            try:
                field_bytes = field_file.read()
                field_df = parse_field(field_bytes, field_file.name)
                st.session_state["woff_field_df"] = field_df
            except Exception as e:
                st.warning(f"Field parse warning: {e}")
                st.session_state["woff_field_df"] = None
    else:
        st.session_state["woff_field_df"] = None

    st.success(
        f"Loaded {len(woff_df)} Write-Off accounts. "
        f"DRR: {'Yes' if st.session_state['woff_drr_df'] is not None else 'None'}. "
        f"Field: {'Yes' if st.session_state['woff_field_df'] is not None else 'None'}."
    )
    st.session_state["woff_step"] = 2
    st.rerun()
