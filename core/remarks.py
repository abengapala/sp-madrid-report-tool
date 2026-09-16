"""
core/remarks.py
STATUS REMARKS and FV REMARKS update logic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# Date prefix pattern: MM.DD.YYYY (with optional space after)
_DATE_PREFIX_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s+")
# Split lookahead: split on ", " followed by a date prefix
_SPLIT_RE = re.compile(r",\s*(?=\d{2}\.\d{2}\.\d{4}\s)")


@dataclass
class RemarkEntry:
    date_str: str       # "MM.DD.YYYY"
    text: str           # full remark text (without the date prefix)
    full: str           # "MM.DD.YYYY text"
    date: Optional[pd.Timestamp] = None

    @property
    def sort_key(self) -> pd.Timestamp:
        return self.date if self.date is not None else pd.Timestamp.min


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_remarks_string(s: str) -> list[RemarkEntry]:
    """
    Split a remarks string into individual RemarkEntry objects.
    Splits on ", " only when followed immediately by a MM.DD.YYYY date prefix.
    This avoids breaking on commas inside remark text.
    """
    if not s or not isinstance(s, str) or s.strip() == "" or s.strip().lower() == "nan":
        return []

    parts = _SPLIT_RE.split(s.strip())
    entries = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = _DATE_PREFIX_RE.match(part)
        if m:
            date_str = m.group(1)
            text = part[m.end():].strip()
            ts = _parse_mm_dd_yyyy(date_str)
            entries.append(RemarkEntry(date_str=date_str, text=text, full=part, date=ts))
        else:
            # No date prefix — append to previous entry or keep as-is
            if entries:
                entries[-1] = RemarkEntry(
                    date_str=entries[-1].date_str,
                    text=entries[-1].text + " " + part,
                    full=entries[-1].full + " " + part,
                    date=entries[-1].date,
                )
            else:
                entries.append(RemarkEntry(date_str="", text=part, full=part, date=None))

    return entries


def _parse_mm_dd_yyyy(s: str) -> Optional[pd.Timestamp]:
    """Parse a MM.DD.YYYY string into a Timestamp."""
    try:
        parts = s.split(".")
        if len(parts) == 3:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
            return pd.Timestamp(year=y, month=m, day=d)
    except Exception:
        pass
    return None


def format_remark(date: pd.Timestamp, text: str) -> str:
    """Format a single remark entry as MM.DD.YYYY text."""
    return f"{date.strftime('%m.%d.%Y')} {text.strip()}"


# ---------------------------------------------------------------------------
# Build new remark entries from DRR
# ---------------------------------------------------------------------------

def build_remark_entries(acct_drr: pd.DataFrame) -> list[str]:
    """
    Convert DRR rows for one account into formatted remark strings.
    Returns list of "MM.DD.YYYY <remark>", newest first.
    Deduplicates by (date, remark text).
    """
    entries = []
    seen = set()
    # Sort newest first
    sorted_drr = acct_drr.sort_values("date_parsed", ascending=False)

    for _, row in sorted_drr.iterrows():
        date = row.get("date_parsed")
        remark = str(row.get("remark", "")).strip()

        if not isinstance(date, pd.Timestamp) or pd.isna(date):
            continue
        if not remark or remark.lower() == "nan":
            continue

        key = (date.date(), remark.lower())
        if key in seen:
            continue
        seen.add(key)

        entries.append(format_remark(date, remark))

    return entries


# ---------------------------------------------------------------------------
# Update STATUS REMARKS
# ---------------------------------------------------------------------------

def update_status_remarks(
    existing: str,
    acct_drr: pd.DataFrame,
    cutoff_date: pd.Timestamp,
) -> tuple[str, bool]:
    """
    Update the STATUS REMARKS string for one account.

    Logic:
    1. Parse existing → keep entries with date STRICTLY BEFORE cutoff_date.
    2. Build new entries from DRR (any date on/after cutoff), newest first.
    3. Join: new_entries + kept_old_entries, comma-separated.

    Returns: (new_remarks_string, had_new_entries: bool)
    """
    existing_entries = parse_remarks_string(existing)

    # Keep old entries before cutoff
    kept_old = [
        e for e in existing_entries
        if e.date is not None and e.date < cutoff_date
    ]

    # Build new entries from DRR on/after cutoff
    if acct_drr is not None and not acct_drr.empty:
        new_drr = acct_drr[
            acct_drr["date_parsed"].notna() &
            (acct_drr["date_parsed"] >= cutoff_date)
        ]
        new_entries = build_remark_entries(new_drr)
    else:
        new_entries = []

    had_new = len(new_entries) > 0

    all_entries = new_entries + [e.full for e in kept_old]
    result = ", ".join(e for e in all_entries if e)

    return result, had_new


# ---------------------------------------------------------------------------
# Update FV REMARKS
# ---------------------------------------------------------------------------

def update_fv_remarks(
    existing: str,
    acct_field: pd.DataFrame,
    is_overall: bool,
) -> tuple[str, bool]:
    """
    Update FV REMARKS for one account.

    - If is_overall: rebuild entirely from field entries (newest first).
    - Else: prepend new entries, skip duplicates.

    Returns: (new_fv_remarks_string, changed: bool)
    """
    if acct_field is None or acct_field.empty:
        return existing, False

    # Sort newest first
    sorted_fv = acct_field.sort_values("date_parsed", ascending=False)
    field_entries = []
    for _, row in sorted_fv.iterrows():
        fv_remark = str(row.get("FV REMARK", "")).strip()
        if fv_remark and fv_remark.lower() not in ("nan", "0", ""):
            field_entries.append(fv_remark)

    if not field_entries:
        return existing, False

    if is_overall:
        # Full rebuild — ignore existing
        new_str = ", ".join(field_entries)
        changed = new_str != (existing or "").strip()
        return new_str, changed

    # Incremental — prepend new entries, skip duplicates
    existing_entries = parse_remarks_string(existing)
    existing_fulls = {e.full.strip().lower() for e in existing_entries}

    new_to_prepend = [e for e in field_entries if e.strip().lower() not in existing_fulls]
    if not new_to_prepend:
        return existing, False

    old_parts = [e.full for e in existing_entries]
    all_parts = new_to_prepend + old_parts
    new_str = ", ".join(p for p in all_parts if p)
    return new_str, True


# ---------------------------------------------------------------------------
# Update status columns from field data
# ---------------------------------------------------------------------------

def update_status_columns(
    daily_row: dict,
    latest_field_row: Optional[pd.Series],
) -> dict:
    """
    Overwrite CLIENT STATUS / ADDRESS STATUS / UNIT STATUS / RFD
    only when the field value is non-blank, non-zero, non-null.
    Never overwrites a real value with a blank one.
    """
    if latest_field_row is None:
        return daily_row

    row = daily_row.copy()
    for col in ["CLIENT STATUS", "ADDRESS STATUS", "UNIT STATUS", "RFD"]:
        field_val = latest_field_row.get(col)
        if _is_real_value(field_val):
            row[col] = str(field_val).strip()

    return row


def _is_real_value(val) -> bool:
    """True if val is a non-blank, non-zero, non-null value."""
    if val is None:
        return False
    if isinstance(val, float) and (pd.isna(val) or val == 0):
        return False
    s = str(val).strip()
    return s not in ("", "0", "nan", "NaN", "None")


# ---------------------------------------------------------------------------
# Batch update for the full DAILY dataframe
# ---------------------------------------------------------------------------

def update_all_remarks(
    daily_df: pd.DataFrame,
    drr_df: Optional[pd.DataFrame],
    field_df: Optional[pd.DataFrame],
    cutoff_date: pd.Timestamp,
    report_date: pd.Timestamp,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Apply STATUS REMARKS and FV REMARKS updates to the entire DAILY dataframe.

    Returns:
        - updated_df
        - zero_activity_pns: list of PNs with no new DRR entries
        - changed_fv_pns: list of PNs whose FV REMARKS changed
    """
    df = daily_df.copy()
    is_overall = field_df.attrs.get("is_overall", False) if field_df is not None else False

    zero_activity_pns = []
    changed_fv_pns = []

    for idx, row in df.iterrows():
        pn = str(row.get("PN", "")).strip()
        if not pn or pn == "nan":
            continue

        # --- STATUS REMARKS ---
        if drr_df is not None and not drr_df.empty:
            acct_drr = drr_df[drr_df["account_no"] == pn]
            new_remarks, had_new = update_status_remarks(
                str(row.get("STATUS REMARKS", "") or ""),
                acct_drr,
                cutoff_date,
            )
            df.at[idx, "STATUS REMARKS"] = new_remarks
            if not had_new:
                zero_activity_pns.append(pn)

            # Update ACTION CODE to latest DRR Status for this account
            if not acct_drr.empty:
                sorted_acct = acct_drr.sort_values("date_parsed", ascending=False)
                latest = sorted_acct.iloc[0]
                from core.action_codes import resolve_action_code
                ac = resolve_action_code(
                    str(latest.get("action_code", "")),
                    str(latest.get("remark_source", "RAW")),
                )
                df.at[idx, "ACTION CODE"] = ac

        # --- FV REMARKS ---
        if field_df is not None and not field_df.empty:
            acct_field = field_df[field_df["pn"] == pn].sort_values("date_parsed", ascending=False)
            if not acct_field.empty:
                new_fv, changed = update_fv_remarks(
                    str(row.get("FV REMARKS", "") or ""),
                    acct_field,
                    is_overall,
                )
                df.at[idx, "FV REMARKS"] = new_fv
                if changed:
                    changed_fv_pns.append(pn)

                # Update status columns from latest field entry
                updated_row = update_status_columns(dict(df.iloc[idx]), acct_field.iloc[0])
                for col in ["CLIENT STATUS", "ADDRESS STATUS", "UNIT STATUS", "RFD"]:
                    df.at[idx, col] = updated_row.get(col, row.get(col))

        # Update DATE to report_date
        df.at[idx, "DATE"] = report_date

    return df, zero_activity_pns, changed_fv_pns
