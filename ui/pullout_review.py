"""
ui/pullout_review.py
Pull-out reconciliation screen.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd


def render_pullout_review():
    flagged   = st.session_state.get("pullout_flagged_pns", [])
    name_map  = st.session_state.get("pullout_name_map", {})
    decisions = st.session_state.get("pullout_decisions", {})

    st.markdown("## ⚠️ Pull-Out Review")
    st.markdown(
        f"**{len(flagged)} account(s)** are in your current report but were "
        "**not found in the DataGrid**. For each account below, choose what happened:"
    )
    st.info(
        "**Pulled Out** → removed from DAILY in the generated report  \n"
        "**Repossessed** → kept, PULLED\_OUT TAG set to REPO  \n"
        "**Keep (check later)** → no change"
    )
    st.markdown("---")

    OPTIONS = ["Keep (check later)", "Pulled Out", "Repossessed"]
    updated_decisions = {}

    for pn in flagged:
        name = name_map.get(pn, "")
        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown(f"**`{pn}`** — {name}")
        with col2:
            current = decisions.get(pn, "Keep (check later)")
            choice = st.selectbox(
                label="Decision",
                options=OPTIONS,
                index=OPTIONS.index(current) if current in OPTIONS else 0,
                key=f"pullout_{pn}",
                label_visibility="collapsed",
            )
            updated_decisions[pn] = choice

    st.markdown("---")
    po_count   = sum(1 for v in updated_decisions.values() if v == "Pulled Out")
    repo_count = sum(1 for v in updated_decisions.values() if v == "Repossessed")
    keep_count = sum(1 for v in updated_decisions.values() if v == "Keep (check later)")

    if po_count or repo_count:
        st.info(f"{po_count} will be removed | {repo_count} marked REPO | {keep_count} kept as-is")

    col_back, col_confirm = st.columns([1, 3])
    with col_back:
        if st.button("Back to Upload", key="pullout_back"):
            st.session_state["rec_step"] = 1
            st.rerun()
    with col_confirm:
        if st.button("Confirm and Continue to Step 2", type="primary", key="pullout_confirm"):
            st.session_state["pullout_decisions"] = updated_decisions
            sheets   = st.session_state.get("report_sheets", {})
            daily_df = sheets.get("DAILY", pd.DataFrame()).copy()
            pn_col = next(
                (c for c in daily_df.columns if str(c).strip().upper() in ("PN", "PN#", "PN NO")),
                None,
            )
            tag_col = next(
                (c for c in daily_df.columns if "PULLED" in str(c).upper() and "TAG" in str(c).upper()),
                None,
            )
            if pn_col:
                def _pn_s(v):
                    try: return str(int(float(str(v))))
                    except: return str(v).strip()
                pull_out_pns = {pn for pn, d in updated_decisions.items() if d == "Pulled Out"}
                repo_pns     = {pn for pn, d in updated_decisions.items() if d == "Repossessed"}
                daily_df["_pn_norm"] = daily_df[pn_col].apply(_pn_s)
                daily_df = daily_df[~daily_df["_pn_norm"].isin(pull_out_pns)].copy()
                if tag_col and repo_pns:
                    daily_df.loc[daily_df["_pn_norm"].isin(repo_pns), tag_col] = "REPO"
                daily_df = daily_df.drop(columns=["_pn_norm"])
                sheets["DAILY"] = daily_df
                st.session_state["report_sheets"] = sheets
            st.session_state["rec_step"] = 2
            st.rerun()
