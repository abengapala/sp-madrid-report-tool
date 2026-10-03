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


import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "database.pkl")


def _save_db(df: pd.DataFrame, sync_cloud: bool = True):
    """Persist database DataFrame to disk so it survives page refreshes, and sync to Google Sheets."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        df.to_pickle(DB_PATH)
    except Exception as e:
        print(f"Error saving local DB: {e}")

    if sync_cloud:
        try:
            from core.sheets_sync import is_sheets_configured, save_db_to_sheets
            if is_sheets_configured():
                save_db_to_sheets(df)
        except Exception as e:
            print(f"Error syncing DB to Google Sheets: {e}")


def _load_db():
    """Load database from disk or Google Sheets."""
    # 1. Try local disk cache
    if os.path.exists(DB_PATH):
        try:
            df = pd.read_pickle(DB_PATH)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

    # 2. Try Google Sheets if local cache is absent (e.g. Deep Freeze restart)
    try:
        from core.sheets_sync import is_sheets_configured, load_db_from_sheets
        if is_sheets_configured():
            df_cloud = load_db_from_sheets()
            if df_cloud is not None and not df_cloud.empty:
                _save_db(df_cloud, sync_cloud=False)
                return df_cloud
    except Exception as e:
        print(f"Error loading DB from Google Sheets: {e}")

    return None


def render_db_manager():
    from core.sheets_sync import is_sheets_configured, save_db_to_sheets, load_db_from_sheets

    # Auto-load from disk or Google Sheets on refresh if session state is empty
    if st.session_state.get("db_manager_df") is None:
        saved = _load_db()
        if saved is not None:
            st.session_state["db_manager_df"] = saved

    st.markdown("## Database Manager")
    st.markdown(
        "Upload `database.xlsx` to view and edit the account list. "
        "Optionally upload the **DataGrid** to see which accounts are no longer active."
    )

    sheets_ok = is_sheets_configured()
    col_c1, col_c2 = st.columns([3, 1])
    with col_c1:
        if sheets_ok:
            st.success("☁️ **Google Sheets Connected** (`SP_MADRID_DB`). Data persists across Deep Freeze reboots!", icon="☁️")
        elif os.path.exists(DB_PATH):
            import datetime
            mtime = os.path.getmtime(DB_PATH)
            saved_at = datetime.datetime.fromtimestamp(mtime).strftime("%b %d %Y %H:%M")
            st.caption(f"Database auto-saved to disk — last saved: {saved_at}")
    with col_c2:
        if sheets_ok:
            if st.button("🔄 Pull from Cloud", help="Pull latest database from Google Sheets tab SP_MADRID_DB", use_container_width=True):
                with st.spinner("Syncing from Google Sheets..."):
                    cloud_df = load_db_from_sheets()
                    if cloud_df is not None and not cloud_df.empty:
                        st.session_state["db_manager_df"] = cloud_df
                        _save_db(cloud_df, sync_cloud=False)
                        st.success(f"Synced {len(cloud_df)} accounts from Google Sheets!")
                        st.rerun()
                    else:
                        st.warning("Google Sheets tab SP_MADRID_DB is empty or not yet populated.")


    # ── Upload ──────────────────────────────────────────────────────────────
    col_db, col_dg = st.columns(2)
    with col_db:
        db_file = st.file_uploader(
            "📂 Upload database.xlsx",
            type=["xlsx"],
            key="dbmgr_upload",
        )
    with col_dg:
        dg_file = st.file_uploader(
            "📊 Upload DataGrid.xlsx (optional — compares active accounts)",
            type=["xlsx"],
            key="dbmgr_datagrid",
        )

    if db_file is not None:
        with st.spinner("Loading database..."):
            try:
                raw = db_file.read()
                df_loaded = pd.read_excel(io.BytesIO(raw))
                df_loaded.columns = [str(c).strip() for c in df_loaded.columns]
                df_loaded = df_loaded.dropna(how="all").reset_index(drop=True)
                st.session_state["db_manager_df"] = df_loaded
                st.session_state["db_manager_raw"] = raw
                _save_db(df_loaded)
                st.success(f"✅ Loaded {len(df_loaded)} accounts from database.")
            except Exception as e:
                st.error(f"Failed to load database: {e}")

    if dg_file is not None:
        with st.spinner("Loading DataGrid..."):
            try:
                dg_raw = pd.read_excel(io.BytesIO(dg_file.read()))
                dg_raw.columns = [str(c).strip() for c in dg_raw.columns]
                dg_raw = dg_raw.dropna(how="all")
                acct_col = next(
                    (c for c in dg_raw.columns if "ACCOUNT" in c.upper() and "NO" in c.upper()),
                    next((c for c in dg_raw.columns if "PN" in c.upper()), None),
                )
                if acct_col:
                    def _pn_dg(v):
                        try: return str(int(float(str(v))))
                        except: return str(v).strip()
                    datagrid_pns = set(dg_raw[acct_col].dropna().apply(_pn_dg).tolist())
                    st.session_state["db_manager_datagrid_pns"] = datagrid_pns
                    st.success(f"✅ DataGrid loaded: **{len(datagrid_pns)}** active accounts.")
                else:
                    st.error("DataGrid: could not find Account No. column.")
            except Exception as e:
                st.error(f"DataGrid error: {e}")

    df = st.session_state.get("db_manager_df")
    if df is None:
        st.info("Upload database.xlsx to get started.")
        return

    datagrid_pns = st.session_state.get("db_manager_datagrid_pns")

    # ── DataGrid Comparison ──────────────────────────────────────────────────
    if datagrid_pns is not None:
        def _pn_norm(v):
            try: return str(int(float(str(v))))
            except: return str(v).strip()

        pn_col_db = next(
            (c for c in df.columns if str(c).strip().upper() in ("PN_NO", "PN", "PN#")),
            None,
        )
        name_col_db  = next((c for c in df.columns if "CUST_NAME" in c.upper() or c.upper() == "NAME"), None)
        tag_col_db   = next((c for c in df.columns if c.upper() == "STATUS"), None)
        place_col_db = next((c for c in df.columns if c.upper() == "PLACEMENT"), None)

        if pn_col_db:
            df["_pn_norm"] = df[pn_col_db].apply(_pn_norm)
            not_in_dg = df[~df["_pn_norm"].isin(datagrid_pns)].copy()
            # Only flag active placements (ignore Curing which was never on a report)
            active_placements = {"RECOVERY", "WRITE OFF", "NEW WRITE OFF"}
            if place_col_db:
                not_in_dg = not_in_dg[
                    not_in_dg[place_col_db].astype(str).str.strip().str.upper().isin(active_placements)
                ]

            if not not_in_dg.empty:
                st.markdown("---")
                st.warning(
                    f"⚠️ **{len(not_in_dg)} account(s)** in your database are **NOT in the DataGrid** "
                    "(they may have been pulled out or repossessed). Review each one:"
                )
                OPTIONS = ["Keep (check later)", "Pulled Out", "Repossessed"]
                decisions = st.session_state.get("db_manager_dg_decisions", {})

                updated_decisions = {}
                for _, row in not_in_dg.iterrows():
                    pn   = row["_pn_norm"]
                    name = str(row.get(name_col_db, "")) if name_col_db else ""
                    placement = str(row.get(place_col_db, "")) if place_col_db else ""
                    c1, c2, c3 = st.columns([2, 2, 2])
                    with c1:
                        st.markdown(f"**`{pn}`**  {name}")
                    with c2:
                        st.caption(f"Placement: {placement}")
                    with c3:
                        current = decisions.get(pn, "Keep (check later)")
                        choice = st.selectbox(
                            "Decision",
                            OPTIONS,
                            index=OPTIONS.index(current) if current in OPTIONS else 0,
                            key=f"dbmgr_dg_{pn}",
                            label_visibility="collapsed",
                        )
                        updated_decisions[pn] = choice

                po_count   = sum(1 for v in updated_decisions.values() if v == "Pulled Out")
                repo_count = sum(1 for v in updated_decisions.values() if v == "Repossessed")

                if st.button(
                    f"✅ Apply Decisions ({po_count} Pulled Out, {repo_count} Repo)",
                    type="primary",
                    key="dbmgr_apply_dg",
                ):
                    st.session_state["db_manager_dg_decisions"] = updated_decisions
                    for pn, decision in updated_decisions.items():
                        mask = df["_pn_norm"] == pn
                        if decision == "Pulled Out":
                            if place_col_db:
                                df.loc[mask, place_col_db] = "PULLED OUT"
                            if tag_col_db:
                                df.loc[mask, tag_col_db] = "PULLED OUT"
                        elif decision == "Repossessed":
                            if tag_col_db:
                                df.loc[mask, tag_col_db] = "REPO"
                    df = df.drop(columns=["_pn_norm"], errors="ignore")
                    st.session_state["db_manager_df"] = df
                    _save_db(df)
                    st.session_state["db_manager_datagrid_pns"] = None  # clear so panel closes
                    st.success(f"✅ Applied — {po_count} marked Pulled Out, {repo_count} marked Repo.")
                    st.rerun()
            else:
                st.success("✅ All active accounts in your database are present in the DataGrid.")
            df = df.drop(columns=["_pn_norm"], errors="ignore")


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
                        _save_db(df)
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
                _save_db(df)
                st.success(f"Added {pn_val} — {new_vals.get('CUST_NAME', '')} to database.")
                st.rerun()


    # ── Status + Download ────────────────────────────────────────────────────
    st.markdown("---")
    st.success(
        "✅ This database is **automatically active** for all report generation. "
        "Any changes you make here (edits, new accounts) are immediately reflected "
        "when you switch to Recovery or Write-Off mode."
    )

    out_buf = io.BytesIO()
    df_clean = df.drop(columns=[c for c in df.columns if c.startswith("_")], errors="ignore")
    df_clean.to_excel(out_buf, index=False)
    out_buf.seek(0)
    st.download_button(
        label="📥 Download Updated database.xlsx",
        data=out_buf.read(),
        file_name="database_updated.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dbmgr_download",
    )
