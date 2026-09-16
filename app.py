"""
app.py — SP Madrid Recovery Report Automation
Main Streamlit entry point. Manages step-driven navigation.
"""
import streamlit as st

st.set_page_config(
    page_title="SP Madrid Recovery Report Tool",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Custom styling ----
st.markdown("""
<style>
    /* Dark sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f36 0%, #0f1523 100%);
    }
    [data-testid="stSidebar"] * { color: #e0e6f0 !important; }

    /* Step indicator active */
    .step-active {
        background: #2563eb;
        color: white;
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: 700;
        display: block;
        margin: 4px 0;
    }
    .step-done {
        background: #16a34a;
        color: white;
        border-radius: 8px;
        padding: 8px 14px;
        display: block;
        margin: 4px 0;
    }
    .step-pending {
        background: #374151;
        color: #9ca3af;
        border-radius: 8px;
        padding: 8px 14px;
        display: block;
        margin: 4px 0;
    }

    /* Main content */
    .main .block-container { padding-top: 1.5rem; max-width: 1400px; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #1e293b;
        border-radius: 10px;
        padding: 12px 16px;
        border: 1px solid #334155;
    }
    [data-testid="stMetricValue"] { color: #60a5fa; font-size: 2rem; }
    [data-testid="stMetricLabel"] { color: #94a3b8; }

    /* Primary button */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #2563eb, #7c3aed);
        border: none;
        border-radius: 8px;
        font-weight: 600;
        font-size: 1rem;
        padding: 0.6rem 1.6rem;
        transition: opacity 0.2s;
    }
    .stButton > button[kind="primary"]:hover { opacity: 0.88; }

    /* Expander */
    .streamlit-expanderHeader {
        background: #1e293b !important;
        border-radius: 8px !important;
        border: 1px solid #334155 !important;
    }
</style>
""", unsafe_allow_html=True)


# ---- Session state init ----
if "step" not in st.session_state:
    st.session_state["step"] = 1


# ---- Sidebar ----
STEPS = [
    (1, "📂 Upload Files"),
    (2, "🔄 Reconcile Accounts"),
    (3, "📋 Preview Changes"),
    (4, "💰 PTP Review"),
    (5, "📥 Generate Report"),
]

with st.sidebar:
    st.markdown("## SP Madrid Recovery Tool")
    st.markdown("---")
    current_step = st.session_state["step"]
    for step_num, step_label in STEPS:
        if step_num == current_step:
            cls = "step-active"
        elif step_num < current_step:
            cls = "step-done"
        else:
            cls = "step-pending"
        st.markdown(f'<span class="{cls}">{step_label}</span>', unsafe_allow_html=True)

    st.markdown("---")

    # Show loaded file info if available
    if current_step > 1:
        rd = st.session_state.get("report_date")
        if rd:
            st.markdown(f"**Report Date**\n\n{rd.strftime('%B %d, %Y')}")
        daily = st.session_state.get("daily_df")
        if daily is None:
            daily = st.session_state.get("report_sheets", {}).get("DAILY")
        if daily is not None:
            st.markdown(f"**Accounts**: {len(daily)}")

    st.markdown("---")
    st.caption("Password: cbs1234 (default)")

    # Reset button
    if st.button("🔁 Start Over", key="btn_reset"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ---- Route to current step ----
step = st.session_state["step"]

if step == 1:
    from ui.upload import render_upload
    render_upload()

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
