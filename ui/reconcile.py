"""
ui/reconcile.py — Step 2: Account list reconciliation screen.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from core.reconciler import reconcile, ReconcileResult


def _pick_db_df() -> pd.DataFrame | None:
    """Return the first non-empty DB dataframe: Database Manager first, then old db_df."""
    for key in ("db_manager_df", "db_df"):
        df = st.session_state.get(key)
        if df is not None and not df.empty:
            return df
    return None


def _toggle_all(pns: list[str]) -> None:
    """Callback: set every new-account checkbox to match 'Select all'."""
    val = st.session_state["chk_select_all_new"]
    for pn in pns:
        st.session_state[f"new_cand_{pn}"] = val


def render_reconcile():
    st.markdown("## 🔄 Step 2 — Reconcile Account List")
    st.markdown(
        "The **current report's account list is the master list** (including all accounts you previously added manually). "
        "No accounts from your report will be removed."
    )

    daily_df: pd.DataFrame = st.session_state["report_sheets"]["DAILY"]
    # Use Database Manager if loaded; otherwise fall back to old db_df
    db_df: pd.DataFrame | None = _pick_db_df()
    drr_df = st.session_state.get("drr_df")
    field_df = st.session_state.get("field_df")
    report_date: pd.Timestamp = st.session_state["report_date"]

    result: ReconcileResult = reconcile(daily_df, db_df, set())

    # ----- Summary metrics -----
    col1, col2, col3 = st.columns(3)
    col1.metric("Current Report Accounts (Kept)", len(result.current_accounts))
    col2.metric(
        "New Candidates (from DB)",
        len(result.new_candidates),
        delta=f"+{len(result.new_candidates)}" if result.new_candidates else None,
    )
    col3.metric("Manually Added / Non-DB (Kept)", len(result.manually_added))

    st.markdown("---")

    # ----- New accounts from DB (optional to add) -----
    new_include = {}
    if result.new_candidates:
        with st.expander(
            f"➕ New accounts detected in database ({len(result.new_candidates)})",
            expanded=True,
        ):
            st.markdown(
                "These accounts exist in the database but are **not yet in your current report**. "
                "Select which ones (if any) you would like to add to this report run:"
            )

            st.checkbox(
                "Select all new accounts",
                value=True,
                key="chk_select_all_new",
                on_change=_toggle_all,
                args=(result.new_candidates,),
            )

            for pn in result.new_candidates:
                name = result.pn_to_name.get(pn, "")
                st.session_state.setdefault(f"new_cand_{pn}", True)
                new_include[pn] = st.checkbox(
                    f"Add **{pn}** — {name}",
                    key=f"new_cand_{pn}",
                )
    else:
        if db_df is not None and not db_df.empty:
            st.info("✅ All accounts in the database are already present in your report.")
        else:
            st.info("ℹ️ No database uploaded — using the current report's account list as-is.")

    st.session_state["new_include"] = new_include

    # ----- Manually added accounts (informational) -----
    if result.manually_added:
        with st.expander(
            f"📌 Manually added / Non-DB accounts in report ({len(result.manually_added)})",
            expanded=False,
        ):
            st.markdown(
                "These accounts are in your report and are **automatically retained**:"
            )
            for pn in result.manually_added:
                name = result.pn_to_name.get(pn, "")
                st.markdown(f"- `{pn}` — {name}")

    # ----- Carried over (informational) -----
    with st.expander(
        f"✅ Current report accounts ({len(result.current_accounts)}) — retained",
        expanded=False,
    ):
        for pn in result.current_accounts:
            name = result.pn_to_name.get(pn, "")
            st.markdown(f"- `{pn}` — {name}")

    st.markdown("---")

    col_back, col_confirm = st.columns([1, 3])
    with col_back:
        if st.button("← Back", key="reconcile_back"):
            st.session_state["rec_step"] = 1
            st.rerun()

    with col_confirm:
        if st.button(
            "✅ Confirm Account List & Continue",
            type="primary",
            key="reconcile_confirm",
        ):
            _apply_and_advance(result, daily_df, db_df, drr_df, field_df, report_date)


def _apply_and_advance(result, daily_df, db_df, drr_df, field_df, report_date):
    from core.reconciler import apply_reconcile

    new_include = st.session_state.get("new_include", {})
    pns_to_add = [pn for pn, include in new_include.items() if include]

    updated_daily = apply_reconcile(
        daily_df=daily_df,
        db_df=db_df,
        drr_df=drr_df,
        field_df=field_df,
        report_date=report_date,
        result=result,
        pns_to_add=pns_to_add,
    )
    st.session_state["daily_df"] = updated_daily
    # Reset downstream state so fresh remarks are computed
    st.session_state.pop("remarks_applied", None)
    st.session_state.pop("preview_trails", None)
    st.session_state.pop("ptp_result", None)
    st.session_state.pop("output_bytes", None)
    st.session_state["rec_step"] = 3
    st.rerun()
