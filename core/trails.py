"""
core/trails.py
Rebuilds the Trails Upload sheet as a single-day snapshot.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from core.action_codes import resolve_action_code
from core.remarks import format_remark

TRAILS_COLUMNS = [
    "FINANCIER ID", "APPLICATION ID", "CUSTOMER ID", "USER ID",
    "ACTION DATE", "ACTION TIME", "ACTION CODE", "CONTACT MODE",
    "PERSON CONTACTED", "PLACE CONTACTED", "CURRENCY", "ACTION AMOUNT",
    "NEXT ACTION DATE", "NEXT ACTION TIME", "REMINDER MODE",
    "CONTACTED BY", "REMARKS",
]


def _fmt_date(ts: pd.Timestamp) -> str:
    """Format a Timestamp as MM.DD.YYYY for Trails Upload."""
    return ts.strftime("%m.%d.%Y")


def rebuild_trails(
    daily_df: pd.DataFrame,
    drr_df: Optional[pd.DataFrame],
    existing_trails_df: pd.DataFrame,
    report_date: pd.Timestamp,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Rebuild Trails Upload for the report date.

    For each account in daily_df:
    - ACTION DATE = report_date, NEXT ACTION DATE = report_date + 1 day
    - Look for DRR entries dated exactly report_date
    - If found: REMARKS = latest entry formatted, ACTION CODE = resolved code
    - If not found: REMARKS = blank, ACTION CODE = blank
    - FINANCIER ID, CUSTOMER ID, USER ID, CONTACT MODE, etc. preserved from existing row

    Returns: (new_trails_df, blanked_account_pns)
    """
    next_date = report_date + pd.Timedelta(days=1)
    action_date_str = _fmt_date(report_date)
    next_date_str = _fmt_date(next_date)

    # Build a lookup from APPLICATION ID (= PN as int) to existing trail row
    existing_lookup: dict[str, dict] = {}
    for _, row in existing_trails_df.iterrows():
        app_id = str(row.get("APPLICATION ID", "")).strip()
        if app_id and app_id != "nan":
            # Normalize: remove .0
            try:
                app_id = str(int(float(app_id)))
            except (ValueError, TypeError):
                pass
            existing_lookup[app_id] = row.to_dict()

    blanked_pns: list[str] = []
    rows = []

    for _, acct_row in daily_df.iterrows():
        pn_raw = acct_row.get("PN", "")
        pn = _normalize_pn(pn_raw)
        if not pn:
            continue

        # Get existing trail row for preserved fields
        existing = existing_lookup.get(pn, {})

        # Use most recent DRR entry up to and including report_date
        # (not just entries on exactly report_date — accounts may have no activity today)
        remarks_str = ""
        action_code_str = ""
        used_date = None

        if drr_df is not None and not drr_df.empty:
            acct_drr = drr_df[
                (drr_df["account_no"] == pn) &
                (drr_df["date_parsed"].notna()) &
                (drr_df["date_parsed"].dt.date <= report_date.date())
            ].sort_values(["date_parsed", "time_str"], ascending=False)

            if not acct_drr.empty:
                latest = acct_drr.iloc[0]
                remark_text = str(latest.get("remark", "")).strip()
                raw_code = str(latest.get("action_code", "")).strip()
                src = str(latest.get("remark_source", "RAW")).strip()
                used_date = latest["date_parsed"]

                if remark_text and remark_text.lower() != "nan":
                    # Use the actual entry date, not report_date, for the remark prefix
                    entry_date = used_date if pd.notna(used_date) else report_date
                    remarks_str = format_remark(entry_date, remark_text)
                action_code_str = resolve_action_code(raw_code, src)
            else:
                blanked_pns.append(pn)

        new_row = {
            "FINANCIER ID":    _preserve(existing, "FINANCIER ID"),
            "APPLICATION ID":  int(pn) if pn.isdigit() else pn,
            "CUSTOMER ID":     _preserve(existing, "CUSTOMER ID"),
            "USER ID":         _preserve(existing, "USER ID"),
            "ACTION DATE":     action_date_str,
            "ACTION TIME":     None,
            "ACTION CODE":     action_code_str or None,
            "CONTACT MODE":    _preserve(existing, "CONTACT MODE"),
            "PERSON CONTACTED":_preserve(existing, "PERSON CONTACTED"),
            "PLACE CONTACTED": _preserve(existing, "PLACE CONTACTED"),
            "CURRENCY":        None,
            "ACTION AMOUNT":   None,
            "NEXT ACTION DATE":next_date_str,
            "NEXT ACTION TIME":None,
            "REMINDER MODE":   None,
            "CONTACTED BY":    _preserve(existing, "CONTACTED BY"),
            "REMARKS":         remarks_str or None,
        }
        rows.append(new_row)

    df = pd.DataFrame(rows, columns=TRAILS_COLUMNS)
    return df, blanked_pns


def _preserve(existing: dict, col: str):
    """Return the existing value for a column if non-blank, else None."""
    v = existing.get(col)
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "nan", "None", "NaN"):
        return None
    return v


def _normalize_pn(val) -> str:
    if val is None:
        return ""
    try:
        f = float(str(val))
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return str(val).strip()
