"""
ui/woff_preview.py -- Write-Off Step 2: Run update and preview changes.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_woff_preview():
    st.markdown("## \U0001f7e5 Write-Off Report — Step 2: Preview Changes")

    woff_df     = st.session_state.get("woff_df_loaded")
    drr_df      = st.session_state.get("woff_drr_df")
    field_df    = st.session_state.get("woff_field_df")
    report_date = st.session_state.get("woff_report_date", pd.Timestamp.today().normalize())

    if woff_df is None:
        st.error("No Write-Off data loaded. Go back to Step 1.")
        if st.button("\u2190 Back", key="woff_prev_back_early"):
            st.session_state["woff_step"] = 1
            st.rerun()
        return

    # Cutoff = last Monday (start of this week)
    cutoff_date = report_date - pd.Timedelta(days=report_date.weekday())

    st.markdown(f"**Report Date:** {report_date.strftime('%B %d, %Y')}  |  "
                f"**Cutoff:** {cutoff_date.strftime('%B %d, %Y')} (Monday)")
    st.markdown(f"**Accounts:** {len(woff_df)}  |  "
                f"**DRR:** {'Loaded' if drr_df is not None else 'Not loaded'}  |  "
                f"**Field:** {'Loaded' if field_df is not None else 'Not loaded'}")

    st.markdown("---")

    if st.button("\u26a1 Run Update", type="primary", key="woff_btn_run"):
        _run_update(woff_df, drr_df, field_df, cutoff_date, report_date)

    if "woff_updated_df" in st.session_state:
        _show_preview()

        col_next, col_back = st.columns([1, 1])
        with col_next:
            if st.button("\u2192 Generate Report", type="primary", key="woff_prev_next"):
                st.session_state["woff_step"] = 3
                st.rerun()
        with col_back:
            if st.button("\u2190 Back", key="woff_prev_back"):
                st.session_state["woff_step"] = 1
                st.rerun()
    else:
        st.markdown("---")
        if st.button("\u2190 Back", key="woff_prev_back2"):
            st.session_state["woff_step"] = 1
            st.rerun()


def _run_update(woff_df, drr_df, field_df, cutoff_date, report_date):
    from core.woff import update_woff_status, rebuild_field_sheet

    with st.spinner("Updating WOFF STATUS from DRR and field data..."):
        try:
            updated_df, zero_pns, changed_fv, unmatched = update_woff_status(
                woff_df, drr_df, field_df, cutoff_date, report_date,
            )
            st.session_state["woff_updated_df"] = updated_df
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
        st.session_state["woff_new_field_df"] = new_field_df

    st.rerun()


def _show_preview():
    updated_df = st.session_state.get("woff_updated_df", pd.DataFrame())
    zero_pns   = st.session_state.get("woff_zero_pns", [])
    changed_fv = st.session_state.get("woff_changed_fv", [])
    unmatched  = st.session_state.get("woff_unmatched", [])
    new_field  = st.session_state.get("woff_new_field_df", pd.DataFrame())

    st.markdown("---")
    st.markdown("## \U0001f4ca Update Summary")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Accounts", len(updated_df))
    c2.metric("No DRR Activity", len(zero_pns))
    c3.metric("FV REMARKS Updated", len(changed_fv))
    c4.metric("FIELD sheet rows", len(new_field))

    pn_col = None
    name_col = None
    for c in updated_df.columns:
        if "PN" in c.upper() and "#" in c and pn_col is None:
            pn_col = c
        if "NAME" in c.upper() and name_col is None:
            name_col = c

    if zero_pns:
        with st.expander(f"\u26aa {len(zero_pns)} accounts with NO new DRR activity this week"):
            for pn in zero_pns:
                if pn_col and name_col:
                    match = updated_df[updated_df[pn_col].astype(str).str.contains(pn, na=False)]
                    name = match.iloc[0][name_col] if not match.empty else ""
                    st.markdown(f"- `{pn}` — {name}")
                else:
                    st.markdown(f"- `{pn}`")

    if changed_fv:
        with st.expander(f"\U0001f3e2 {len(changed_fv)} accounts with updated FV REMARKS"):
            for pn in changed_fv:
                st.markdown(f"- `{pn}`")

    if unmatched:
        with st.expander(f"\u26a0\ufe0f {len(unmatched)} accounts: DRR status not found in STATUS REFERENCE"):
            for pn in unmatched:
                st.markdown(f"- `{pn}`")
