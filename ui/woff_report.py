"""
ui/woff_report.py -- Step 6: Write-Off Status Report automation.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_woff_report():
    st.markdown("## \U0001f4cb Step 6 \u2014 Write-Off Status Report")
    st.markdown(
        "Upload the current **Write-Off Status Report** to update it with "
        "the same DRR and field data loaded in Step 1."
    )

    drr_df = st.session_state.get("drr_df")
    field_df = st.session_state.get("field_df")
    report_date = st.session_state.get("report_date", pd.Timestamp.today().normalize())
    password = st.session_state.get("password", "cbs1234")

    if drr_df is None and field_df is None:
        st.warning(
            "No DRR or field data loaded yet. "
            "Go back to Step 1 and load your source files first."
        )

    st.markdown("---")
    col1, col2 = st.columns([2, 1])
    with col1:
        woff_file = st.file_uploader(
            "Write-Off Status Report (.xlsx) -- encrypted with cbs1234",
            type=["xlsx"],
            key="upload_woff",
        )
        woff_password = st.text_input(
            "Write-Off report password",
            value=password,
            type="password",
            key="woff_password",
        )
    with col2:
        st.markdown(f"**Report Date:** {report_date.strftime('%B %d, %Y')}")
        if drr_df is not None:
            st.metric("DRR entries loaded", len(drr_df))
        if field_df is not None:
            st.metric("Field entries loaded", len(field_df))

    st.markdown("---")

    if woff_file is not None:
        if st.button("Update Write-Off Report", type="primary", key="btn_woff_update"):
            _process_woff(woff_file, woff_password, drr_df, field_df, report_date)

    if "woff_output_bytes" in st.session_state:
        _render_woff_summary()
        rd = st.session_state["report_date"]
        fname = f"SP_MADRID_CBS AUTO WRITEOFF STATUS REPORT as of {rd.strftime('%m%d%Y')}.xlsx"
        raw = st.session_state["woff_output_bytes"]
        if hasattr(raw, "read"):
            raw = raw.read()
        raw = bytes(raw)
        st.download_button(
            label=f"Download Write-Off Report -- {rd.strftime('%B %d, %Y')}",
            data=raw,
            file_name=fname,
            mime="application/octet-stream",
            key="btn_woff_download",
        )
        st.success(f"Password: **{woff_password}**")

    st.markdown("---")
    col_back, _ = st.columns([1, 4])
    with col_back:
        if st.button("Back", key="woff_back"):
            st.session_state["step"] = 5
            st.rerun()


def _process_woff(woff_file, password, drr_df, field_df, report_date):
    from core.woff import load_woff_report, update_woff_status, rebuild_field_sheet, generate_woff_download

    cutoff_date = report_date - pd.Timedelta(days=report_date.weekday())

    with st.spinner("Decrypting Write-Off report..."):
        try:
            woff_bytes = woff_file.read()
            woff_df, orig_field_df, source_wb = load_woff_report(woff_bytes, password)
            st.session_state["woff_df_original"] = woff_df.copy()
            st.session_state["woff_source_wb"] = source_wb
        except Exception as e:
            st.error(f"Failed to load Write-Off report: {e}")
            return

    st.info(f"Loaded {len(woff_df)} Write-Off accounts.")

    with st.spinner("Updating WOFF STATUS from DRR and field data..."):
        try:
            updated_df, zero_pns, changed_fv, unmatched = update_woff_status(
                woff_df, drr_df, field_df, cutoff_date, report_date,
            )
            st.session_state["woff_df"] = updated_df
            st.session_state["woff_zero_pns"] = zero_pns
            st.session_state["woff_changed_fv"] = changed_fv
            st.session_state["woff_unmatched"] = unmatched
        except Exception as e:
            st.error(f"Update failed: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    with st.spinner("Rebuilding FIELD sheet..."):
        new_field_df = rebuild_field_sheet(updated_df)
        st.session_state["woff_field_df"] = new_field_df

    with st.spinner("Writing back and encrypting..."):
        try:
            output_bytes = generate_woff_download(source_wb, updated_df, new_field_df, password)
            st.session_state["woff_output_bytes"] = output_bytes
        except Exception as e:
            st.error(f"Failed to generate output: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    st.rerun()


def _render_woff_summary():
    st.markdown("---")
    st.markdown("## Write-Off Update Summary")

    woff_df    = st.session_state.get("woff_df", pd.DataFrame())
    zero_pns   = st.session_state.get("woff_zero_pns", [])
    changed_fv = st.session_state.get("woff_changed_fv", [])
    unmatched  = st.session_state.get("woff_unmatched", [])
    field_df   = st.session_state.get("woff_field_df", pd.DataFrame())

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Accounts", len(woff_df))
    col2.metric("No DRR Activity", len(zero_pns))
    col3.metric("FV Updated", len(changed_fv))
    col4.metric("FIELD sheet rows", len(field_df))

    st.markdown("---")

    pn_col = None
    name_col = None
    for c in woff_df.columns:
        if "PN" in c.upper() and pn_col is None:
            pn_col = c
        if "NAME" in c.upper() and name_col is None:
            name_col = c

    if zero_pns:
        with st.expander(f"{len(zero_pns)} accounts with NO new DRR activity"):
            for pn in zero_pns:
                if pn_col and name_col:
                    match = woff_df[woff_df[pn_col].astype(str).str.contains(pn, na=False)]
                    name = match.iloc[0][name_col] if not match.empty else ""
                    st.markdown(f"- `{pn}` -- {name}")
                else:
                    st.markdown(f"- `{pn}`")

    if changed_fv:
        with st.expander(f"{len(changed_fv)} accounts with updated FV REMARKS"):
            for pn in changed_fv:
                st.markdown(f"- `{pn}`")

    if unmatched:
        with st.expander(f"{len(unmatched)} accounts with DRR status not in STATUS REFERENCE"):
            for pn in unmatched:
                st.markdown(f"- `{pn}`")

    st.success("Write-Off report updated and ready to download.")
