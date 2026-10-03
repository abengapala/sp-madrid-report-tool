"""
ui/db_manager.py
Database Manager -- a dedicated page to view, filter, edit and update the
account database (database.xlsx).

The database is the source of truth for:
  - Which accounts are RECOVERY / WRITE OFF / NEW WRITE OFF / CURING
  - Which accounts have been pulled out
  - New endorsements added manually

When you generate a Recovery or Write-Off report, the tool uses this
loaded database to know what accounts belong on each report.
"""
from __future__ import annotations

import io
import streamlit as st
import pandas as pd

# Columns shown in the manager table (the rest are kept but not displayed)
DISPLAY_COLS = [
    "PLACEMENT", "PN_NO", "CUST_NAME", "OUTSTANDING_BALANCE",
    "DPD", "AGE", "ENDS_DATE", "ENDORSEMENT_TAG", "STATUS",
]

# Fields the user fills in when adding a new account
NEW_ACCT_FIELDS = [
    ("PLACEMENT",            "Placement",          ["RECOVERY", "WRITE OFF", "NEW WRITE OFF", "CURING"]),
    ("PN_NO",                "Account No. (PN)",   None),
    ("CUST_NAME",            "Customer Name",       None),
    ("OUTSTANDING_BALANCE",  "Outstanding Balance", None),
    ("DPD",                  "DPD",                 None),
    ("AGE",                  "Bucket / Age",        None),
    ("ENDS_DATE",            "Endorsement Date",    None),
    ("ENDORSEMENT_TAG",      "Endorsement Tag",     ["EXISTING", "NEW"]),
    ("AGENCY",               "Agency",              None),
    ("PRODUCT",              "Product",             ["01 AL - AUTO LOAN"]),
]

PLACEMENT_OPTIONS = ["ALL", "RECOVERY", "WRITE OFF", "NEW WRITE OFF", "CURING"]


def render_db_manager():
    st.markdown("## Database Manager")
    st.markdown(
        "Upload `database.xlsx` to view and edit the account list. "
        "Changes here are used when generating Recovery and Write-Off reports."
    )

    # ── Upload ──────────────────────────────────────────────────────────────
    col_up, col_info = st.columns([2, 1])
    with col_up:
        db_file = st.file_uploader(
            "Upload database.xlsx",
            type=["xlsx"],
            key="dbmgr_upload",
        )

    if db_file is not None:
        with st.spinner("Loading database..."):
            try:
                raw = db_file.read()
                df = pd.read_excel(io.BytesIO(raw))
                df.columns = [str(c).strip() for c in df.columns]
                df = df.dropna(how="all").reset_index(drop=True)
                st.session_state["db_manager_df"] = df
                st.session_state["db_manager_raw"] = raw
                st.success(f"Loaded {len(df)} accounts from database.")
            except Exception as e:
                st.error(f"Failed to load database: {e}")

    df = st.session_state.get("db_manager_df")
    if df is None:
        st.info("Upload database.xlsx to get started.")
        return

    # ── Summary counts ───────────────────────────────────────────────────────
    st.markdown("---")
    placement_counts = df["PLACEMENT"].value_counts() if "PLACEMENT" in df.columns else {}
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total", len(df))
    c2.metric("Recovery",      placement_counts.get("RECOVERY", 0))
    c3.metric("Write Off",     placement_counts.get("WRITE OFF", 0))
    c4.metric("New Write Off", placement_counts.get("NEW WRITE OFF", 0))
    c5.metric("Curing",        placement_counts.get("CURING", 0))

    # ── Filters ──────────────────────────────────────────────────────────────
    st.markdown("---")
    col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
    with col_f1:
        filter_placement = st.selectbox("Filter by Placement", PLACEMENT_OPTIONS, key="dbmgr_filter_placement")
    with col_f2:
        filter_tag = st.selectbox("Filter by Endorsement Tag", ["ALL", "EXISTING", "NEW"], key="dbmgr_filter_tag")
    with col_f3:
        search = st.text_input("Search name or PN", key="dbmgr_search", placeholder="Type name or PN...")

    # Apply filters
    view = df.copy()
    if filter_placement != "ALL" and "PLACEMENT" in view.columns:
        view = view[view["PLACEMENT"].str.strip().str.upper() == filter_placement]
    if filter_tag != "ALL" and "ENDORSEMENT_TAG" in view.columns:
        view = view[view["ENDORSEMENT_TAG"].astype(str).str.strip().str.upper() == filter_tag]
    if search.strip():
        mask = pd.Series([False] * len(view), index=view.index)
        for col in ["CUST_NAME", "PN_NO"]:
            if col in view.columns:
                mask |= view[col].astype(str).str.upper().str.contains(search.strip().upper(), na=False)
        view = view[mask]

    # Show only display columns that exist
    show_cols = [c for c in DISPLAY_COLS if c in view.columns]
    st.markdown(f"**{len(view)} accounts** matching filter")
    st.dataframe(view[show_cols].reset_index(drop=True), use_container_width=True, height=400)

    # ── Edit a single account's PLACEMENT / STATUS ─────────────────────────
    st.markdown("---")
    st.markdown("### Edit Account")
    with st.expander("Change PLACEMENT or mark as Pulled Out for a specific account"):
        edit_pn = st.text_input("Enter Account No. (PN) to edit", key="dbmgr_edit_pn")
        if edit_pn.strip():
            def _pn_s(v):
                try: return str(int(float(str(v))))
                except: return str(v).strip()
            pn_norm = _pn_s(edit_pn.strip())
            if "PN_NO" in df.columns:
                df["_pn_norm"] = df["PN_NO"].apply(_pn_s)
                matches = df[df["_pn_norm"] == pn_norm]
                if matches.empty:
                    st.warning(f"PN {pn_norm} not found in database.")
                else:
                    idx = matches.index[0]
                    cur_placement = str(df.at[idx, "PLACEMENT"]) if "PLACEMENT" in df.columns else "RECOVERY"
                    cur_status    = str(df.at[idx, "STATUS"])    if "STATUS"    in df.columns else ""
                    st.markdown(f"**{df.at[idx, 'CUST_NAME'] if 'CUST_NAME' in df.columns else pn_norm}**")

                    ec1, ec2 = st.columns(2)
                    with ec1:
                        new_placement = st.selectbox(
                            "Placement",
                            ["RECOVERY", "WRITE OFF", "NEW WRITE OFF", "CURING"],
                            index=["RECOVERY", "WRITE OFF", "NEW WRITE OFF", "CURING"].index(cur_placement)
                                  if cur_placement in ["RECOVERY", "WRITE OFF", "NEW WRITE OFF", "CURING"] else 0,
                            key="dbmgr_edit_placement",
                        )
                    with ec2:
                        new_status = st.selectbox(
                            "Status",
                            ["", "PULLED OUT", "REPO", "ACTIVE"],
                            index=["", "PULLED OUT", "REPO", "ACTIVE"].index(cur_status)
                                  if cur_status in ["", "PULLED OUT", "REPO", "ACTIVE"] else 0,
                            key="dbmgr_edit_status",
                        )
                    if st.button("Apply Changes", key="dbmgr_apply_edit"):
                        if "PLACEMENT" in df.columns:
                            df.at[idx, "PLACEMENT"] = new_placement
                        if "STATUS" in df.columns:
                            df.at[idx, "STATUS"] = new_status
                        df = df.drop(columns=["_pn_norm"])
                        st.session_state["db_manager_df"] = df
                        st.success(f"Updated {pn_norm}: PLACEMENT={new_placement}, STATUS={new_status}")
                        st.rerun()

    # ── Add new account ───────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Add New Endorsement")
    with st.expander("Fill in details for a new account"):
        new_vals = {}
        cols_a, cols_b = st.columns(2)
        for i, (field, label, options) in enumerate(NEW_ACCT_FIELDS):
            col = cols_a if i % 2 == 0 else cols_b
            with col:
                if options:
                    new_vals[field] = st.selectbox(label, options, key=f"dbnew_{field}")
                else:
                    new_vals[field] = st.text_input(label, key=f"dbnew_{field}")

        if st.button("Add Account to Database", type="primary", key="dbmgr_add_acct"):
            pn_val = str(new_vals.get("PN_NO", "")).strip()
            if not pn_val:
                st.error("Account No. (PN) is required.")
            else:
                # Build a full row with blanks for unused columns
                new_row = {col: "" for col in df.columns}
                for field, val in new_vals.items():
                    if field in new_row:
                        new_row[field] = val
                new_row["ENDORSEMENT_TAG"] = new_vals.get("ENDORSEMENT_TAG", "NEW")
                new_df = pd.DataFrame([new_row])
                df = pd.concat([df, new_df], ignore_index=True)
                st.session_state["db_manager_df"] = df
                st.success(f"Added {pn_val} — {new_vals.get('CUST_NAME', '')} to database.")
                st.rerun()

    # ── Save / Download ───────────────────────────────────────────────────────
    st.markdown("---")
    col_save1, col_save2 = st.columns([2, 2])
    with col_save1:
        if st.button("Use This Database for Reports", type="primary", key="dbmgr_use"):
            st.session_state["db_df"] = df
            st.success("Database is now active and will be used when generating reports.")

    with col_save2:
        out_buf = io.BytesIO()
        df_clean = df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore")
        df_clean.to_excel(out_buf, index=False)
        out_buf.seek(0)
        st.download_button(
            label="Download Updated database.xlsx",
            data=out_buf.read(),
            file_name="database_updated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dbmgr_download",
        )
