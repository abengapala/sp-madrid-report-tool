"""
ui/diff_preview.py — Step 3: Before/after diff preview for remarks and Trails.

UPDATED (this revision):
- update_all_remarks now returns 5 values (added repo_ai_added_pns and
  stale_fv_pns) instead of 3 — updated the call site accordingly.
- Added a new expander surfacing accounts whose FV REMARKS look stale
  (had content, but got nothing fresh this run). These are NOT reset
  automatically — the user picks which ones to reset via checkboxes,
  and confirming calls core.remarks.reset_stale_fv_remarks only for the
  ones actually checked. This matches the confirmed process: staleness
  has no hard cutoff, so it's a judgment call surfaced for review, never
  applied silently.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd


def render_diff_preview():
    st.markdown("## 📋 Step 3 — Preview Changes")

    daily_df: pd.DataFrame = st.session_state["daily_df"]
    drr_df = st.session_state.get("drr_df")
    field_df = st.session_state.get("field_df")
    report_date: pd.Timestamp = st.session_state["report_date"]

    original_daily = st.session_state["report_sheets"]["DAILY"]

    if "remarks_applied" not in st.session_state:
        with st.spinner("Computing remarks updates..."):
            from core.remarks import update_all_remarks

            cutoff_date = report_date
            if drr_df is not None and not drr_df.empty:
                min_drr = drr_df["date_parsed"].dropna().min()
                if pd.notna(min_drr):
                    cutoff_date = min_drr

            (updated_daily, zero_pns, changed_fv_pns,
             repo_ai_added_pns, stale_fv_pns) = update_all_remarks(
                daily_df, drr_df, field_df, cutoff_date, report_date
            )
            st.session_state["updated_daily"] = updated_daily
            st.session_state["zero_activity_pns"] = zero_pns
            st.session_state["changed_fv_pns"] = changed_fv_pns
            st.session_state["repo_ai_added_pns"] = repo_ai_added_pns
            st.session_state["stale_fv_pns"] = stale_fv_pns
            st.session_state["cutoff_date"] = cutoff_date
            st.session_state["remarks_applied"] = True

    updated_daily = st.session_state["updated_daily"]
    zero_pns = st.session_state["zero_activity_pns"]
    changed_fv_pns = st.session_state["changed_fv_pns"]
    repo_ai_added_pns = st.session_state.get("repo_ai_added_pns", [])
    stale_fv_pns = st.session_state.get("stale_fv_pns", [])

    pn_to_name = {
        str(r["PN"]): str(r.get("NAME", "")) for _, r in original_daily.iterrows()
    }

    # ---- Zero-activity alert (always pinned to top) ----
    if zero_pns:
        st.error(
            f"⚠️ **{len(zero_pns)} account(s) had NO new DRR activity** on or after the cutoff date. "
            f"These accounts will have their STATUS REMARKS unchanged from cutoff onward."
        )
        zero_rows = [{"PN": pn, "NAME": pn_to_name.get(pn, "")} for pn in zero_pns]
        st.dataframe(pd.DataFrame(zero_rows), use_container_width=True, hide_index=True)
        st.markdown("---")

    # ---- Stale FV REMARKS — needs an explicit per-account decision ----
    if stale_fv_pns:
        with st.expander(
            f"🟠 {len(stale_fv_pns)} account(s) have FV REMARKS with no fresh activity this run — reset to 'AWAITING FIELD STATUS'?",
            expanded=False,
        ):
            st.markdown(
                "These accounts have existing FV REMARKS content, but neither the field file "
                "nor a REPO AI entry supplied anything current for them this run. Check any you'd "
                "like reset back to the placeholder (this also resets ADDRESS STATUS to "
                "`(FOR FIELD VISIT)`) — nothing is reset unless you check it."
            )
            reset_choices = {}
            for pn in stale_fv_pns:
                name = pn_to_name.get(pn, "")
                current_fv = str(
                    updated_daily.loc[updated_daily["PN"].astype(str) == pn, "FV REMARKS"].values[0]
                    if (updated_daily["PN"].astype(str) == pn).any() else ""
                )
                reset_choices[pn] = st.checkbox(
                    f"`{pn}` — {name}: {current_fv[:80]}{'...' if len(current_fv) > 80 else ''}",
                    value=False,
                    key=f"stale_reset_{pn}",
                )
            st.session_state["stale_fv_reset_choices"] = reset_choices
        st.markdown("---")

    # ---- Tabs ----
    tab1, tab2, tab3 = st.tabs(["📝 STATUS REMARKS", "🏠 FV REMARKS", "📊 Trails Upload"])

    with tab1:
        _render_remarks_diff(original_daily, updated_daily, "STATUS REMARKS", zero_pns)

    with tab2:
        _render_remarks_diff(
            original_daily, updated_daily, "FV REMARKS", [],
            highlight_pns=changed_fv_pns, repo_pns=repo_ai_added_pns,
        )

    with tab3:
        _render_trails_preview(updated_daily, drr_df, report_date)

    st.markdown("---")
    col_back, col_apply = st.columns([1, 3])
    with col_back:
        if st.button("← Back", key="diff_back"):
            del st.session_state["remarks_applied"]
            st.session_state["step"] = 2
            st.rerun()
    with col_apply:
        if st.button("✅ Apply Changes & Continue", type="primary", key="diff_apply"):
            final_daily = updated_daily
            reset_choices = st.session_state.get("stale_fv_reset_choices", {})
            pns_to_reset = [pn for pn, checked in reset_choices.items() if checked]
            if pns_to_reset:
                from core.remarks import reset_stale_fv_remarks
                final_daily = reset_stale_fv_remarks(final_daily, pns_to_reset)
            st.session_state["daily_df"] = final_daily
            st.session_state["step"] = 4
            st.rerun()


def _render_remarks_diff(original_df, updated_df, col: str, zero_pns: list,
                          highlight_pns: list = None, repo_pns: list = None):
    orig_lookup = {str(r["PN"]): str(r.get(col, "") or "") for _, r in original_df.iterrows()}
    upd_lookup = {str(r["PN"]): str(r.get(col, "") or "") for _, r in updated_df.iterrows()}
    name_lookup = {str(r["PN"]): str(r.get("NAME", "")) for _, r in updated_df.iterrows()}
    repo_pns = repo_pns or []

    changed = []
    unchanged = []
    for pn, new_val in upd_lookup.items():
        old_val = orig_lookup.get(pn, "")
        if new_val.strip() != old_val.strip():
            changed.append(pn)
        else:
            unchanged.append(pn)

    st.markdown(f"**{len(changed)} account(s) changed** | {len(unchanged)} unchanged")

    for pn in changed:
        name = name_lookup.get(pn, "")
        label = f"`{pn}` — {name}"
        if pn in zero_pns:
            label += " ⚪ no new activity"
        if pn in repo_pns:
            label += " 🏗️ REPO AI mirrored"
        icon = "🟡" if highlight_pns and pn in highlight_pns else "🟢"
        with st.expander(f"{icon} {label}", expanded=False):
            c1, c2 = st.columns(2)
            c1.markdown("**BEFORE**")
            c1.text_area("", value=orig_lookup.get(pn, ""), height=150, disabled=True, key=f"b_{col}_{pn}")
            c2.markdown("**AFTER**")
            c2.text_area("", value=upd_lookup.get(pn, ""), height=150, disabled=True, key=f"a_{col}_{pn}")

    if unchanged:
        with st.expander(f"Show {len(unchanged)} unchanged accounts", expanded=False):
            for pn in unchanged:
                name = name_lookup.get(pn, "")
                st.markdown(f"- `{pn}` — {name}")


def _render_trails_preview(daily_df, drr_df, report_date):
    from core.trails import rebuild_trails
    existing_trails = st.session_state["report_sheets"]["Trails Upload"]

    if "preview_trails" not in st.session_state:
        with st.spinner("Building Trails Upload preview..."):
            trails_df, blanked_pns = rebuild_trails(daily_df, drr_df, existing_trails, report_date)
            st.session_state["preview_trails"] = trails_df
            st.session_state["blanked_pns"] = blanked_pns

    trails_df = st.session_state["preview_trails"]
    blanked_pns = st.session_state["blanked_pns"]

    held_pns = {
        str(r["PN"]) for _, r in daily_df.iterrows()
        if str(r.get("PULLED_OUT TAG", "") or "").strip().upper() not in ("EXISTING", "", "NAN")
    }
    if held_pns:
        st.caption(f"ℹ️ {len(held_pns)} held account(s) excluded from Trails Upload entirely (not counted below).")

    if blanked_pns:
        name_lookup = {str(r["PN"]): str(r.get("NAME", "")) for _, r in daily_df.iterrows()}
        st.warning(
            f"⚪ **{len(blanked_pns)} account(s) had no DRR activity on {report_date.strftime('%B %d, %Y')}** "
            f"— REMARKS and ACTION CODE will be blank in Trails Upload."
        )
        rows = [{"PN": p, "NAME": name_lookup.get(p, "")} for p in blanked_pns]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown(f"**Trails Upload preview** — {len(trails_df)} rows")
    display_cols = ["APPLICATION ID", "ACTION DATE", "ACTION CODE", "REMARKS", "NEXT ACTION DATE"]
    st.dataframe(
        trails_df[[c for c in display_cols if c in trails_df.columns]],
        use_container_width=True,
        hide_index=True,
    )
