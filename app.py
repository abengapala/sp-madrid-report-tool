"""
app.py -- SP Madrid Report Automation Tool
Two completely independent modes:
  - Recovery Report   (submitted every Wednesday and Friday)
  - Write-Off Report  (submitted every Friday only)

Each mode has its own session state prefix so uploads, steps, and
data never bleed between the two.
"""
import streamlit as st

st.set_page_config(
    page_title="SP Madrid Report Tool",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f36 0%, #0f1523 100%);
    }
    [data-testid="stSidebar"] * { color: #e0e6f0 !important; }

    .step-active {
        background: #2563eb; color: white; border-radius: 8px;
        padding: 8px 14px; font-weight: 700; display: block; margin: 4px 0;
    }
    .step-done {
        background: #16a34a; color: white; border-radius: 8px;
        padding: 8px 14px; display: block; margin: 4px 0;
    }
    .step-pending {
        background: #374151; color: #9ca3af; border-radius: 8px;
        padding: 8px 14px; display: block; margin: 4px 0;
    }
    .mode-badge-recovery {
        background: linear-gradient(135deg, #1d4ed8, #7c3aed);
        color: white; border-radius: 20px; padding: 4px 14px;
        font-size: 0.85rem; font-weight: 700; display: inline-block;
        margin-bottom: 8px;
    }
    .mode-badge-woff {
        background: linear-gradient(135deg, #b45309, #dc2626);
        color: white; border-radius: 20px; padding: 4px 14px;
        font-size: 0.85rem; font-weight: 700; display: inline-block;
        margin-bottom: 8px;
    }
    .main .block-container { padding-top: 1.5rem; max-width: 1400px; }
    [data-testid="stMetric"] {
        background: #1e293b; border-radius: 10px;
        padding: 12px 16px; border: 1px solid #334155;
    }
    [data-testid="stMetricValue"] { color: #60a5fa; font-size: 2rem; }
    [data-testid="stMetricLabel"] { color: #94a3b8; }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb, #7c3aed);
        border: none; border-radius: 8px; font-weight: 600;
        font-size: 1rem; padding: 0.6rem 1.6rem; transition: opacity 0.2s;
    }
    .stButton > button[kind="primary"]:hover { opacity: 0.88; }
    .streamlit-expanderHeader {
        background: #1e293b !important;
        border-radius: 8px !important;
        border: 1px solid #334155 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "mode" not in st.session_state:
    st.session_state["mode"] = None   # None = not chosen yet
if "rec_step" not in st.session_state:
    st.session_state["rec_step"] = 1
if "woff_step" not in st.session_state:
    st.session_state["woff_step"] = 1
if st.session_state.get("db_manager_df") is None:
    from ui.db_manager import _load_db
    _df = _load_db()
    if _df is not None:
        st.session_state["db_manager_df"] = _df

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
RECOVERY_STEPS = [
    (1, "\U0001f4c2 Upload Files"),
    (2, "\U0001f504 Reconcile Accounts"),
    (3, "\U0001f4cb Preview Changes"),
    (4, "\U0001f4b0 PTP Review"),
    (5, "\U0001f4e5 Generate Report"),
]

WOFF_STEPS = [
    (1, "\U0001f4c2 Upload Files"),
    (2, "\U0001f4cb Preview Changes"),
    (3, "\U0001f4e5 Generate Report"),
]

with st.sidebar:
    st.markdown("## SP Madrid Report Tool")
    st.markdown("---")

    # Mode selector
    mode_choice = st.radio(
        "Select Mode",
        options=["\U0001f7e6  Recovery Report", "\U0001f7e5  Write-Off Report", "\U0001f4cb  Database Manager"],
        index=0 if st.session_state["mode"] not in ("woff","db") else (1 if st.session_state["mode"]=="woff" else 2),
        key="mode_radio",
    )
    is_woff = "Write-Off" in mode_choice
    is_db   = "Database" in mode_choice
    new_mode = "woff" if is_woff else ("db" if is_db else "recovery")
    if st.session_state["mode"] != new_mode:
        st.session_state["mode"] = new_mode

    st.markdown("---")

    if is_db:
        st.markdown("\U0001f4cb **Database Manager**")
        db_df_loaded = st.session_state.get("db_manager_df")
        if db_df_loaded is not None:
            st.markdown(f"**Loaded:** {len(db_df_loaded)} accounts")
        else:
            st.caption("Upload database.xlsx to start")

    elif not is_woff:
        # Recovery steps
        st.markdown("\U0001f7e6 **Recovery Report** *(Wed + Fri)*")
        current_step = st.session_state["rec_step"]
        for step_num, step_label in RECOVERY_STEPS:
            if step_num == current_step:
                cls = "step-active"
            elif step_num < current_step:
                cls = "step-done"
            else:
                cls = "step-pending"
            st.markdown(f'<span class="{cls}">{step_label}</span>', unsafe_allow_html=True)

        st.markdown("---")
        rd = st.session_state.get("report_date")
        if rd is not None:
            st.markdown(f"**Report Date**\n\n{rd.strftime('%B %d, %Y')}")
        daily = st.session_state.get("daily_df")
        if daily is None:
            daily = st.session_state.get("report_sheets", {}).get("DAILY")
        if daily is not None:
            st.markdown(f"**Accounts**: {len(daily)}")

    else:
        # Write-Off steps
        st.markdown("\U0001f7e5 **Write-Off Report** *(Fri only)*")
        current_step = st.session_state["woff_step"]
        for step_num, step_label in WOFF_STEPS:
            if step_num == current_step:
                cls = "step-active"
            elif step_num < current_step:
                cls = "step-done"
            else:
                cls = "step-pending"
            st.markdown(f'<span class="{cls}">{step_label}</span>', unsafe_allow_html=True)

        st.markdown("---")
        rd = st.session_state.get("woff_report_date")
        if rd is not None:
            st.markdown(f"**Report Date**\n\n{rd.strftime('%B %d, %Y')}")
        woff_df = st.session_state.get("woff_df_loaded")
        if woff_df is not None:
            st.markdown(f"**Write-Off Accounts**: {len(woff_df)}")

    st.markdown("---")
    st.caption("Password: cbs1234 (default)")

    if st.button("\U0001f501 Start Over", key="btn_reset"):
        mode = st.session_state.get("mode", "recovery")
        # Only clear the current mode's keys
        if mode == "recovery":
            keep = {"mode", "woff_step", "woff_report_date", "woff_df_loaded",
                    "woff_drr_df", "woff_field_df", "woff_source_wb",
                    "woff_df", "woff_output_bytes", "woff_zero_pns",
                    "woff_changed_fv", "woff_unmatched", "woff_field_sheet_df",
                    "woff_df_original", "mode_radio"}
        else:
            keep = {"mode", "rec_step", "report_date", "daily_df", "drr_df",
                    "field_df", "source_wb", "report_sheets", "output_bytes",
                    "password", "mode_radio"}
        for key in list(st.session_state.keys()):
            if key not in keep:
                del st.session_state[key]
        if mode == "recovery":
            st.session_state["rec_step"] = 1
        else:
            st.session_state["woff_step"] = 1
        st.rerun()

# ---------------------------------------------------------------------------
# Route based on mode
# ---------------------------------------------------------------------------
mode = st.session_state["mode"]

if mode == "db":
    from ui.db_manager import render_db_manager
    render_db_manager()

elif mode == "recovery" or mode is None:
    step = st.session_state["rec_step"]
    if step == 1:
        from ui.upload import render_upload
        render_upload()
    elif step == "pullout":
        from ui.pullout_review import render_pullout_review
        render_pullout_review()
    elif step == 2:
        from ui.reconcile import render_reconcile
        render_reconcile()
    elif step == 3:
        from ui.diff_preview import render_diff_preview
        render_diff_preview()
    elif step == 4:
        from ui.ptp_review import render_ptp_review
        render_ptp_review()
    elif step == 5:
        from ui.generate import render_generate
        render_generate()


elif mode == "woff":
    step = st.session_state["woff_step"]
    if step == 1:
        from ui.woff_upload import render_woff_upload
        render_woff_upload()
    elif step == "pullout":
        import pandas as pd
        flagged   = st.session_state.get("woff_pullout_flagged", [])
        name_map  = st.session_state.get("woff_pullout_name_map", {})
        decisions = st.session_state.get("woff_pullout_decisions", {})

        st.markdown("## \u26a0\ufe0f Write-Off Pull-Out Review")
        st.markdown(
            f"**{len(flagged)} account(s)** are in your Write-Off report but were "
            "**not found in the DataGrid**. Choose what happened to each:"
        )
        st.info(
            "**Pulled Out** \u2192 removed from the Write-Off report  \n"
            "**Repossessed** \u2192 kept, PULLED\\_OUT TAG set to REPO  \n"
            "**Keep (check later)** \u2192 no change"
        )
        st.markdown("---")

        OPTIONS = ["Keep (check later)", "Pulled Out", "Repossessed"]
        updated = {}
        for pn in flagged:
            name = name_map.get(pn, "")
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown(f"**`{pn}`** \u2014 {name}")
            with c2:
                choice = st.selectbox(
                    "Decision", OPTIONS,
                    index=OPTIONS.index(decisions.get(pn, "Keep (check later)")),
                    key=f"woff_po_{pn}",
                    label_visibility="collapsed",
                )
                updated[pn] = choice

        st.markdown("---")
        po = sum(1 for v in updated.values() if v == "Pulled Out")
        rp = sum(1 for v in updated.values() if v == "Repossessed")
        if po or rp:
            st.info(f"{po} will be removed | {rp} marked REPO")

        cb, cc = st.columns([1, 3])
        with cb:
            if st.button("Back to Upload", key="woff_po_back"):
                st.session_state["woff_step"] = 1
                st.rerun()
        with cc:
            if st.button("Confirm and Continue", type="primary", key="woff_po_confirm"):
                st.session_state["woff_pullout_decisions"] = updated
                woff_df = st.session_state.get("woff_df_loaded", pd.DataFrame()).copy()
                pn_col = next(
                    (c for c in woff_df.columns if str(c).strip().upper() in ("PN", "PN#", "PN NO")),
                    None,
                )
                tag_col = next(
                    (c for c in woff_df.columns if "PULLED" in str(c).upper() and "TAG" in str(c).upper()),
                    None,
                )
                if pn_col:
                    def _p(v):
                        try: return str(int(float(str(v))))
                        except: return str(v).strip()
                    po_pns   = {pn for pn, d in updated.items() if d == "Pulled Out"}
                    repo_pns = {pn for pn, d in updated.items() if d == "Repossessed"}
                    woff_df["_pn"] = woff_df[pn_col].apply(_p)
                    woff_df = woff_df[~woff_df["_pn"].isin(po_pns)].copy()
                    if tag_col and repo_pns:
                        woff_df.loc[woff_df["_pn"].isin(repo_pns), tag_col] = "REPO"
                    woff_df = woff_df.drop(columns=["_pn"])
                    st.session_state["woff_df_loaded"] = woff_df
                st.session_state["woff_step"] = 2
                st.rerun()
    elif step == 2:
        from ui.woff_preview import render_woff_preview
        render_woff_preview()
    elif step == 3:
        from ui.woff_generate import render_woff_generate
        render_woff_generate()
