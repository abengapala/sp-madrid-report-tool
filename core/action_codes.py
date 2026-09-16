"""
core/action_codes.py
Maps raw DRR Status values to ACTION CODE legend vocabulary.
Only used when CMS STATUS is unavailable (remark_source == 'RAW').
Rules are exactly as specified — no extra inference beyond what's listed.
"""
from __future__ import annotations


def map_raw_status(raw_status: str) -> str:
    """
    Apply the confirmed 4-rule mapping for raw DRR Status values.
    When CMS STATUS is unavailable and a raw Status must be classified.

    Rules (applied in order):
    1. Contains "EMAIL"                         → "EMAIL"
    2. Contains "SMS"                           → "SMS"
    3. Starts with "CALL" AND contains
       "WRONG NUMBER" or "NOT IN SERVICE"       → "NIS_KOR_CBR"
    4. Everything else                          → return raw text unchanged
    """
    if not raw_status or not isinstance(raw_status, str):
        return str(raw_status) if raw_status else ""

    s = raw_status.strip().upper()

    if "EMAIL" in s:
        return "EMAIL"
    if "SMS" in s:
        return "SMS"
    if s.startswith("CALL") and ("WRONG NUMBER" in s or "NOT IN SERVICE" in s):
        return "NIS_KOR_CBR"

    # Rule 4: leave as raw text — do NOT force into a legend code
    return raw_status.strip()


def resolve_action_code(action_code_raw: str, remark_source: str) -> str:
    """
    Return the correct ACTION CODE given the source column used.
    - If remark_source == 'CMS': use action_code_raw directly (already mapped).
    - Else: run through map_raw_status.
    """
    if remark_source == "CMS":
        return str(action_code_raw).strip() if action_code_raw and str(action_code_raw) != "nan" else ""
    return map_raw_status(str(action_code_raw) if action_code_raw else "")
