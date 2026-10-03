"""
ui/woff_upload.py -- Write-Off Step 1: Upload source files.
Completely separate from Recovery.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_woff_upload():
    st.markdown("## Write-Off Report -- Step 1: Upload Files")
    st.markdown(
        "Upload the source files for the **Friday** Write-Off report. "
        "These are **independent** from the Recovery report -- "
        "upload the DRR and monitoring template as of **this Friday's** cutoff."
    )

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Write-Off Status Report")
        woff_file = st.file_uploader(
            "Current Write-Off Report (.xlsx, password: cbs1234)",
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
        st.markdown("### Report Date (Friday)")
        report_date = st.date_input(
            "This Friday's report date",
            value=pd.Timestamp.today().normalize().to_pydatetime(),
            key="woff_date_input",
        )

    st.markdown("---")

    st.markdown("### DRR Daily Remarks")
    drr_files = st.file_uploader(
        "DRR raw files (.csv or .xlsx) -- select all days Mon-Fri at once, tool merges them",
        type=["xlsx", "csv", "xls"],
        key="woff_upload_drr",
        accept_multiple_files=True,
    )

    st.markdown("### CBS Monitoring Template (Field File)")
    field_file = st.file_uploader(
        "CBS Monitoring Template (.xlsm or .xlsx) -- tool reads OVERALL FIELD sheet inside",
        type=["xlsm", "xlsx"],
        key="woff_upload_field",
    )

    st.markdown("---")

    if woff_file is None:
        st.info("Upload the Write-Off Status Report to continue. DRR and Field files are optional but recommended.")
    else:
        n_drr = len(drr_files) if drr_files else 0
        if n_drr > 0:
            st.success(f"{n_drr} DRR file(s) selected.")
        if st.button("Load & Parse Files", type="primary", key="woff_btn_parse"):
            _parse_and_advance(woff_file, woff_pw, drr_files or [], field_file, pd.Timestamp(report_date))


def _parse_and_advance(woff_file, woff_pw, drr_files, field_file, report_date):
    from core.woff import load_woff_report
    from core.file_io import load_drr, load_field_file, set_date_anchor

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

    warnings = []

    # Parse DRR -- multiple daily CSV/XLSX files, merged into one DataFrame
    drr_df = None
    if drr_files:
        with st.spinner(f"Parsing {len(drr_files)} DRR file(s)..."):
            parts = []
            for f in drr_files:
                try:
                    b = f.read()
                    part = load_drr(b, warnings=warnings)
                    parts.append(part)
                except Exception as e:
                    st.warning(f"DRR '{f.name}': {e}")
            if parts:
                drr_df = pd.concat(parts, ignore_index=True).drop_duplicates()
                max_date = drr_df["date_parsed"].dropna().max()
                if pd.notna(max_date):
                    warnings.append(
                        f"DRR: {len(drr_df)} entries merged from {len(parts)} file(s). "
                        f"Latest date: {max_date.strftime('%B %d, %Y')}"
                    )
    st.session_state["woff_drr_df"] = drr_df

    # Parse Field file (CBS monitoring template -- reads OVERALL FIELD sheet)
    field_df = None
    if field_file is not None:
        with st.spinner("Parsing Field file (OVERALL FIELD)..."):
            try:
                field_bytes = field_file.read()
                field_df, field_warnings = load_field_file(field_bytes)
                warnings.extend(field_warnings)
            except Exception as e:
                st.warning(f"Field parse warning: {e}")
    st.session_state["woff_field_df"] = field_df

    for w in warnings:
        st.info(w)

    n_drr = len(drr_df) if drr_df is not None else 0
    n_fld = len(field_df) if field_df is not None else 0
    st.success(
        f"Loaded {len(woff_df)} Write-Off accounts. "
        f"DRR: {n_drr} entries. Field: {n_fld} entries."
    )
    st.session_state["woff_step"] = 2
    st.rerun()
