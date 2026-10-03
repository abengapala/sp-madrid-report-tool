"""
ui/upload.py — Step 1: File upload and parsing screen.
"""
from __future__ import annotations

import io
import streamlit as st
import pandas as pd


def render_upload():
    st.markdown("## 📂 Step 1 — Upload Files")
    st.markdown(
        "Upload the current report and any source files to process. "
        "Only the **current report** is required."
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        report_file = st.file_uploader(
            "Current Recovery Status Report (.xlsx) *required*",
            type=["xlsx"],
            key="upload_report",
        )
        password = st.text_input(
            "Report password",
            value="cbs1234",
            type="password",
            key="upload_password",
        )

    with col2:
        st.markdown("**Source Files**")
        drr_files = st.file_uploader(
            "DRR Daily Remarks (.csv or .xlsx) — "
            "Wednesday report: upload Fri→Wed DRRs | Friday report: upload Wed→Fri DRRs",
            type=["xlsx", "csv", "xls"],
            key="upload_drr",
            accept_multiple_files=True,
        )
        field_file = st.file_uploader(
            "CBS Monitoring Template (.xlsm or .xlsx) — tool reads OVERALL FIELD sheet inside",
            type=["xlsm", "xlsx"],
            key="upload_field",
        )

    # Report date
    st.markdown("---")
    st.markdown("**Report Date**")
    default_date = pd.Timestamp.today().normalize()
    report_date = st.date_input(
        "Report 'as of' date (auto-filled from DRR if available after parsing)",
        value=default_date,
        key="upload_date",
    )

    st.markdown("---")

    if st.button("\U0001f50d Load & Parse Files", type="primary", key="btn_load"):
        if report_file is None:
            st.error("\u274c The current report is required.")
            return
        _parse_and_advance(report_file, password, drr_files, field_file, report_date)


def _parse_and_advance(report_file, password, drr_files, field_file, report_date):
    from core.file_io import (
        load_report_sheets, load_report_workbook,
        load_drr, load_field_file,
        set_date_anchor,
    )

    warnings = []
    errors = []

    set_date_anchor(pd.Timestamp(report_date))

    with st.spinner("Decrypting and parsing report..."):
        try:
            report_bytes = report_file.read()
            sheets = load_report_sheets(report_bytes, password)
            source_wb = load_report_workbook(report_bytes, password)
            st.session_state["report_sheets"] = sheets
            st.session_state["source_wb"]     = source_wb
            st.session_state["report_bytes"]  = report_bytes
            st.session_state["password"]      = password
        except Exception as e:
            st.error(f"❌ Failed to load report: {e}")
            return

    field_bytes = field_file.read() if field_file is not None else None

    # 1. Parse DRR — multiple daily files merged
    drr_df = None
    drr_file_list = drr_files if drr_files else []
    if drr_file_list:
        with st.spinner(f"Parsing {len(drr_file_list)} DRR file(s)..."):
            parts = []
            for f in drr_file_list:
                try:
                    part = load_drr(f.read(), warnings=warnings)
                    parts.append(part)
                except Exception as e:
                    errors.append(f"DRR '{f.name}': {e}")
            if parts:
                drr_df = pd.concat(parts, ignore_index=True).drop_duplicates()
                max_date = drr_df["date_parsed"].dropna().max()
                if pd.notna(max_date):
                    st.session_state["auto_report_date"] = max_date
                    warnings.append(
                        f"\u2139\ufe0f DRR: **{len(drr_df)}** entries merged from **{len(parts)}** file(s). "
                        f"Latest date: **{max_date.strftime('%B %d, %Y')}**"
                    )
    elif field_bytes is not None:
        try:
            xl = pd.ExcelFile(io.BytesIO(field_bytes))
            drr_sheet = next((s for s in xl.sheet_names if "DRR" in s.strip().upper()), None)
            if drr_sheet:
                with st.spinner(f"Extracting DRR from '{drr_sheet}' in monitoring file..."):
                    drr_df = load_drr(field_bytes, sheet_name=drr_sheet, warnings=warnings)
                    max_date = drr_df["date_parsed"].dropna().max()
                    if pd.notna(max_date):
                        st.session_state["auto_report_date"] = max_date
                        warnings.append(f"\u2139\ufe0f Report date auto-detected: **{max_date.strftime('%B %d, %Y')}**")
        except Exception:
            pass

    # 2. Parse Field file (OVERALL FIELD sheet)
    field_df = None
    if field_bytes is not None:
        with st.spinner("Parsing field file..."):
            try:
                field_df, field_warnings = load_field_file(field_bytes)
                warnings.extend(field_warnings)
            except Exception as e:
                errors.append(f"Field file error: {e}")

    # Show errors
    if errors:
        for err in errors:
            st.error(f"\u274c {err}")
        return

    # Show warnings
    blocking = [w for w in warnings if "COLUMN ALIGNMENT WARNING" in w]
    soft     = [w for w in warnings if w not in blocking]
    for w in soft:
        st.warning(w) if w.startswith("\u26a0\ufe0f") else st.info(w)
    if blocking:
        for w in blocking:
            st.error(f"\U0001f6ab {w}")
        st.error("Column alignment issue — re-check the field file and try again.")
        return

    # Resolve report date
    auto_date = st.session_state.get("auto_report_date")
    final_report_date = auto_date if auto_date is not None else pd.Timestamp(report_date)
    st.session_state["report_date"] = final_report_date

    # Store parsed data
    st.session_state["drr_df"]   = drr_df
    st.session_state["field_df"] = field_df

    daily_df    = sheets["DAILY"]
    acct_count  = len(daily_df)
    drr_count   = len(drr_df)   if drr_df   is not None else 0
    field_count = len(field_df) if field_df is not None else 0

    st.success(
        f"\u2705 Loaded \u2014 **{acct_count}** accounts | "
        f"**{drr_count}** DRR entries | **{field_count}** field entries"
    )
    if auto_date:
        st.info(f"\U0001f4c5 Report date: **{final_report_date.strftime('%B %d, %Y')}**")

    # Advance to Step 2
    st.session_state["rec_step"] = 2
    st.rerun()
