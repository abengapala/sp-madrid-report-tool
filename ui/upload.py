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
            "DRR Daily Remarks (.csv or .xlsx) — select all days Mon–Fri at once",
            type=["xlsx", "csv", "xls"],
            key="upload_drr",
            accept_multiple_files=True,
        )
        field_file = st.file_uploader(
            "CBS Monitoring Template (.xlsm or .xlsx) — tool reads OVERALL FIELD sheet inside",
            type=["xlsm", "xlsx"],
            key="upload_field",
        )
        db_file = st.file_uploader("Account Database (.xlsx)", type=["xlsx"], key="upload_db")

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
        _parse_and_advance(report_file, password, drr_files, field_file, db_file, report_date)


def _parse_and_advance(report_file, password, drr_files, field_file, db_file, report_date):
    from core.file_io import (
        load_report_sheets, load_report_workbook,
        load_drr, load_field_file, load_database,
        set_date_anchor,
    )

    warnings = []
    errors = []

    # Set the date anchor FIRST so all subsequent date parsing resolves
    # ambiguous MM/DD vs DD/MM based on the user-selected report date.
    set_date_anchor(pd.Timestamp(report_date))

    with st.spinner("Decrypting and parsing report..."):
        try:
            report_bytes = report_file.read()
            sheets = load_report_sheets(report_bytes, password)
            source_wb = load_report_workbook(report_bytes, password)
            st.session_state["report_sheets"] = sheets
            st.session_state["source_wb"] = source_wb
            st.session_state["report_bytes"] = report_bytes
            st.session_state["password"] = password
        except Exception as e:
            st.error(f"❌ Failed to load report: {e}")
            return

    # drr_files is now a list (multi-file upload)
    field_bytes = None
    if field_file is not None:
        field_bytes = field_file.read()

    db_bytes = None
    if db_file is not None:
        db_bytes = db_file.read()

    # 1. Parse DRR — accepts multiple daily CSV/XLSX files, merges them all
    drr_df = None
    drr_file_list = drr_files if drr_files else []
    if drr_file_list:
        with st.spinner(f"Parsing {len(drr_file_list)} DRR file(s)..."):
            parts = []
            for f in drr_file_list:
                try:
                    b = f.read()
                    part = load_drr(b, warnings=warnings)
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
        # Fallback: check if monitoring template contains a DRR sheet
        try:
            xl = pd.ExcelFile(io.BytesIO(field_bytes))
            drr_sheet = next((s for s in xl.sheet_names if "DRR" in s.strip().upper()), None)
            if drr_sheet:
                with st.spinner(f"Extracting DRR from '{drr_sheet}' in monitoring file..."):
                    drr_df = load_drr(field_bytes, sheet_name=drr_sheet, warnings=warnings)
                    warnings.append(f"\u2139\ufe0f DRR entries auto-detected from sheet '{drr_sheet}' in monitoring file.")
                    max_date = drr_df["date_parsed"].dropna().max()
                    if pd.notna(max_date):
                        st.session_state["auto_report_date"] = max_date
                        warnings.append(f"\u2139\ufe0f Report date auto-detected from DRR: **{max_date.strftime('%B %d, %Y')}**")
        except Exception:
            pass

    # 2. Parse Field file
    field_df = None
    field_warnings = []
    if field_bytes is not None:
        with st.spinner("Parsing field file..."):
            try:
                field_df, field_warnings = load_field_file(field_bytes)
                warnings.extend(field_warnings)
            except Exception as e:
                errors.append(f"Field file error: {e}")
    elif drr_bytes is not None:
        # Check if DRR file contains OVERALL FIELD sheet
        try:
            xl = pd.ExcelFile(io.BytesIO(drr_bytes))
            field_sheet = next((s for s in xl.sheet_names if "FIELD" in s.strip().upper()), None)
            if field_sheet:
                with st.spinner(f"Extracting field remarks from '{field_sheet}'..."):
                    field_df, field_warnings = load_field_file(drr_bytes, sheet_name=field_sheet)
                    warnings.append(f"ℹ️ Field remarks auto-detected from sheet '{field_sheet}'.")
                    warnings.extend(field_warnings)
        except Exception:
            pass

    # 3. Parse Database
    db_df = None
    if db_bytes is not None:
        with st.spinner("Parsing account database..."):
            try:
                db_df, db_warnings = load_database(db_bytes)
                warnings.extend(db_warnings)
            except Exception as e:
                errors.append(f"Database error: {e}")
    else:
        # Check field_bytes or drr_bytes for DATABASE sheet
        for source_b, source_label in [(field_bytes, "monitoring file"), (drr_bytes, "uploaded file")]:
            if source_b is not None:
                try:
                    xl = pd.ExcelFile(io.BytesIO(source_b))
                    db_sheet = next((s for s in xl.sheet_names if s.strip().upper() in ("DATABASE", "DB", "ACCOUNTS")), None)
                    if db_sheet:
                        with st.spinner(f"Extracting account database from '{db_sheet}' in {source_label}..."):
                            db_df, db_warnings = load_database(source_b, sheet_name=db_sheet)
                            warnings.append(f"ℹ️ Account database auto-detected from sheet '{db_sheet}' in {source_label}.")
                            warnings.extend(db_warnings)
                            break
                except Exception:
                    pass

    # Show errors (hard errors that prevent loading)
    if errors:
        for err in errors:
            st.error(f"❌ {err}")
        st.warning("Please check the uploaded files or upload them in the corresponding slots.")
        return

    # Show warnings — separate hard column shift warnings from soft info
    blocking_warnings = [w for w in warnings if "COLUMN ALIGNMENT WARNING" in w]
    soft_warnings = [w for w in warnings if w not in blocking_warnings]

    for w in soft_warnings:
        if w.startswith("⚠️"):
            st.warning(w)
        else:
            st.info(w)

    # Only block if there is a genuine column shift (majority of PNs are not account numbers)
    if blocking_warnings:
        for w in blocking_warnings:
            st.error(f"🚫 {w}")
        st.error(
            "The field file columns appear to be shifted or headers are missing. "
            "The PN column is mostly not account numbers. Please re-check the file and try again."
        )
        return

    # Resolve report date
    auto_date = st.session_state.get("auto_report_date")
    final_report_date = auto_date if auto_date is not None else pd.Timestamp(report_date)
    st.session_state["report_date"] = final_report_date

    # Store parsed data
    st.session_state["drr_df"] = drr_df
    st.session_state["field_df"] = field_df
    st.session_state["db_df"] = db_df

    daily_df = sheets["DAILY"]
    acct_count = len(daily_df)
    drr_count = len(drr_df) if drr_df is not None else 0
    field_count = len(field_df) if field_df is not None else 0

    st.success(
        f"✅ Loaded successfully — **{acct_count}** accounts in report | "
        f"**{drr_count}** DRR entries | **{field_count}** field entries"
    )

    if auto_date:
        st.info(f"📅 Report date set to: **{final_report_date.strftime('%B %d, %Y')}**")

    # Advance
    st.session_state["rec_step"] = 2
    st.rerun()
