"""
core/ptp.py
PTP detection and inventory management.

Triggers for PTP INVENTORY:
1. DRR action_code contains "PTP"
2. Field file has real PTP AMOUNT + PTP DATE (non-placeholder)
3. DRR remark or action_code contains "KEPT" or "REPO"

Partitions:
- followup_ptps: account already in PTP INVENTORY — auto-applied, informational only
- new_ptps: account in book, not in PTP INVENTORY — needs user confirmation
- out_of_book_ptps: account NOT in current book — report only, never add
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# Keywords that trigger PTP INVENTORY consideration
_PTP_KEYWORDS = re.compile(r"PTP|KEPT|REPO", re.IGNORECASE)
_PTP_STATUS_RE = re.compile(r"PTP", re.IGNORECASE)


@dataclass
class PTPCandidate:
    pn: str
    name: str
    source: str               # "DRR" | "FIELD"
    action_code: str
    remark: str
    ptp_amount: Optional[float]
    ptp_date: Optional[pd.Timestamp]
    date: Optional[pd.Timestamp]
    is_followup: bool = False  # True if already in PTP INVENTORY


@dataclass
class PTPResult:
    followup_ptps: list[PTPCandidate] = field(default_factory=list)
    new_ptps: list[PTPCandidate] = field(default_factory=list)
    out_of_book_ptps: list[PTPCandidate] = field(default_factory=list)


def detect_ptp_activity(
    drr_df: Optional[pd.DataFrame],
    field_df: Optional[pd.DataFrame],
    current_pns: set[str],
    ptp_inventory_df: pd.DataFrame,
    daily_df: pd.DataFrame,
) -> PTPResult:
    """
    Scan DRR and field file for PTP/KEPT/REPO activity.
    Partitions candidates into followup, new, and out-of-book groups.
    """
    result = PTPResult()

    # Build existing PTP INVENTORY set by PN
    existing_ptp_pns: set[str] = set()
    for _, row in ptp_inventory_df.iterrows():
        pn = _norm(row.get("PN", ""))
        if pn:
            existing_ptp_pns.add(pn)

    # Name lookup from DAILY
    pn_to_name = {}
    for _, row in daily_df.iterrows():
        pn = _norm(row.get("PN", ""))
        if pn:
            pn_to_name[pn] = str(row.get("NAME", "")).strip()

    seen: set[str] = set()  # (pn, source) dedup

    # --- Scan DRR ---
    if drr_df is not None and not drr_df.empty:
        for _, row in drr_df.iterrows():
            pn = _norm(row.get("account_no", ""))
            if not pn:
                continue

            action_code = str(row.get("action_code", "")).strip()
            remark = str(row.get("remark", "")).strip()
            combined = action_code + " " + remark

            if not _PTP_KEYWORDS.search(combined):
                continue

            key = (pn, "DRR")
            if key in seen:
                continue
            seen.add(key)

            candidate = PTPCandidate(
                pn=pn,
                name=pn_to_name.get(pn, ""),
                source="DRR",
                action_code=action_code,
                remark=remark,
                ptp_amount=None,
                ptp_date=None,
                date=row.get("date_parsed"),
                is_followup=(pn in existing_ptp_pns),
            )
            _classify(candidate, pn, current_pns, result)

    # --- Scan field file ---
    if field_df is not None and not field_df.empty:
        for _, row in field_df.iterrows():
            pn = _norm(row.get("pn", ""))
            if not pn:
                continue

            ptp_amount = row.get("ptp_amount")
            ptp_date = row.get("ptp_date")

            has_real_ptp = (
                _is_real_value(ptp_amount) or
                (ptp_date is not None and not pd.isna(ptp_date))
            )

            # Also check FV REMARK for keywords
            fv_remark = str(row.get("FV REMARK", "")).strip()
            has_keyword = _PTP_KEYWORDS.search(fv_remark)

            if not has_real_ptp and not has_keyword:
                continue

            key = (pn, "FIELD")
            if key in seen:
                continue
            seen.add(key)

            candidate = PTPCandidate(
                pn=pn,
                name=pn_to_name.get(pn, ""),
                source="FIELD",
                action_code="",
                remark=fv_remark,
                ptp_amount=float(ptp_amount) if _is_real_value(ptp_amount) else None,
                ptp_date=ptp_date if _is_real_timestamp(ptp_date) else None,
                date=row.get("date_parsed"),
                is_followup=(pn in existing_ptp_pns),
            )
            _classify(candidate, pn, current_pns, result)

    return result


def _classify(
    candidate: PTPCandidate,
    pn: str,
    current_pns: set[str],
    result: PTPResult,
) -> None:
    """Route a candidate to the correct bucket."""
    if pn not in current_pns:
        result.out_of_book_ptps.append(candidate)
    elif candidate.is_followup:
        result.followup_ptps.append(candidate)
    else:
        result.new_ptps.append(candidate)


def build_ptp_inventory_row(
    daily_df: pd.DataFrame,
    pn: str,
    candidate: PTPCandidate,
    report_date: pd.Timestamp,
) -> dict:
    """
    Build a PTP INVENTORY row for a new PTP candidate.
    Copies fields from the DAILY row; fills in PTP-specific data.
    """
    daily_row = daily_df[daily_df["PN"].astype(str).str.strip() == pn]
    if daily_row.empty:
        # Try normalized PN
        daily_row = daily_df[
            daily_df["PN"].apply(lambda x: _norm(x)) == pn
        ]

    if daily_row.empty:
        base = {}
    else:
        base = daily_row.iloc[0].to_dict()

    return {
        "DATE": report_date.strftime("%m/%d/%Y"),
        "PRODUCT": base.get("PRODUCT", "01 AL - AUTO LOAN"),
        "PN": int(pn) if pn.isdigit() else pn,
        "NAME": base.get("NAME", candidate.name),
        "OB": base.get("OB"),
        "DPD": base.get("DPD"),
        "BUCKET": base.get("BUCKET"),
        "ENDO DATE": base.get("ENDO DATE"),
        "FLOWING DATE": base.get("FLOWING DATE"),
        "COLL TAGGING": base.get("COLL TAGGING"),
        "ACTION CODE": candidate.action_code or base.get("ACTION CODE"),
        "STATUS REMARKS": candidate.remark,
        "FV REMARKS": base.get("FV REMARKS", "AWAITING FIELD STATUS"),
        "CLIENT STATUS": base.get("CLIENT STATUS"),
        "ADDRESS STATUS": base.get("ADDRESS STATUS", "FFV"),
        "UNIT STATUS": base.get("UNIT STATUS"),
        "PULLED_OUT TAG": base.get("PULLED_OUT TAG", "EXISTING"),
        "PULLED_OUT DATE": base.get("PULLED_OUT DATE"),
        "RFD": base.get("RFD", "LATE COLLECTION"),
        "GEO": base.get("GEO"),
        "AGENCY": "SP MADRID",
        "COLLECTOR": base.get("COLLECTOR"),
    }


def apply_ptp_decisions(
    ptp_inventory_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    new_ptps_to_add: list[PTPCandidate],
    report_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Add confirmed new PTP candidates to PTP INVENTORY.
    Returns the updated PTP INVENTORY dataframe.
    """
    df = ptp_inventory_df.copy()
    for candidate in new_ptps_to_add:
        new_row = build_ptp_inventory_row(daily_df, candidate.pn, candidate, report_date)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _norm(val) -> str:
    if val is None:
        return ""
    try:
        f = float(str(val))
        if f == int(f):
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return str(val).strip()


def _is_real_value(val) -> bool:
    if val is None:
        return False
    if isinstance(val, float) and (pd.isna(val) or val == 0):
        return False
    try:
        return float(val) != 0
    except (ValueError, TypeError):
        return False


def _is_real_timestamp(val) -> bool:
    if val is None:
        return False
    if isinstance(val, float) and pd.isna(val):
        return False
    try:
        ts = pd.Timestamp(val)
        return ts.year > 1900
    except Exception:
        return False
