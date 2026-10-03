"""
core/status_lookup.py
Loads the STATUS REFERENCE table and provides lookup functions.

Two lookup tables (mirroring the original XLSM ACCT_TBL formulas):

LEFT TABLE  -- DRR/Call Status lookup:
    Input : "Status" text from DRR  (e.g. "CALL - KEPT_FULL UPDATE")
    Output: ACTION CODE, CLIENT STATUS, ADDRESS STATUS, UNIT STATUS, RFD, RANK

RIGHT TABLE -- FV (Field Visit) unique-status lookup:
    Input : "UNIQUE STATUS" from field file (e.g. "POS_CLIENT REFUSED TO TALK")
    Output: ADDRESS STATUS, RFD
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

_BUNDLED_REF = os.path.join(os.path.dirname(__file__), "status_reference.xlsx")
_SHEET_NAME = "STATUS REFERENCE"


@dataclass
class DRRLookupResult:
    action_code: str = ""
    client_status: str = ""
    address_status: str = ""
    unit_status: str = ""
    rfd: str = ""
    rank: Optional[float] = None
    matched: bool = False


@dataclass
class FVLookupResult:
    address_status: str = ""
    rfd: str = ""
    fv_rank: Optional[float] = None
    matched: bool = False


class StatusLookup:
    """Loads both lookup tables from STATUS REFERENCE and exposes fast dict lookups."""

    def __init__(self, reference_path: Optional[str] = None):
        path = reference_path or _BUNDLED_REF
        self._drr_table: dict[str, DRRLookupResult] = {}
        self._fv_table: dict[str, FVLookupResult] = {}
        self._load(path)

    def _load(self, path: str) -> None:
        try:
            df = pd.read_excel(path, sheet_name=_SHEET_NAME, header=0)
        except Exception as e:
            raise ValueError(f"Could not load STATUS REFERENCE from '{path}': {e}") from e

        df.columns = [str(c).strip() for c in df.columns]

        # LEFT TABLE: DRR/Call statuses
        for _, row in df.iterrows():
            status_raw = row.get("Status")
            if pd.isna(status_raw) or str(status_raw).strip() == "":
                continue
            status_key = _norm(str(status_raw))
            rank_val = _to_float(row.get("RANK"))
            result = DRRLookupResult(
                action_code=_clean(row.get("ACTION CODE", "")),
                client_status=_clean(row.get("CLIENT STATUS", "")),
                address_status=_clean(row.get("ADDRESS STATUS", "")),
                unit_status=_clean(row.get("UNIT STATUS", "")),
                rfd=_clean(row.get("RFD", "")),
                rank=rank_val,
                matched=True,
            )
            existing = self._drr_table.get(status_key)
            if existing is None:
                self._drr_table[status_key] = result
            elif rank_val is not None and (existing.rank is None or rank_val < existing.rank):
                self._drr_table[status_key] = result

        # RIGHT TABLE: FV unique statuses
        addr_fv_col = next(
            (c for c in df.columns if "ADDRESS STATUS" in c.upper() and c != "ADDRESS STATUS"),
            "ADDRESS STATUS.1",
        )
        rfd_fv_col = next(
            (c for c in df.columns if c.upper().startswith("RFD") and c != "RFD"),
            "RFD.1",
        )
        for _, row in df.iterrows():
            unique_raw = row.get("UNIQUE STATUS")
            if pd.isna(unique_raw) or str(unique_raw).strip() == "":
                continue
            unique_key = _norm(str(unique_raw))
            fv_rank_val = _to_float(row.get("FV RANK"))
            fv_result = FVLookupResult(
                address_status=_clean(row.get(addr_fv_col, "")),
                rfd=_clean(row.get(rfd_fv_col, "")),
                fv_rank=fv_rank_val,
                matched=True,
            )
            existing_fv = self._fv_table.get(unique_key)
            if existing_fv is None:
                self._fv_table[unique_key] = fv_result
            elif fv_rank_val is not None and (existing_fv.fv_rank is None or fv_rank_val < existing_fv.fv_rank):
                self._fv_table[unique_key] = fv_result

    def lookup_drr_status(self, status_text: str) -> DRRLookupResult:
        if not status_text or not isinstance(status_text, str):
            return DRRLookupResult()
        key = _norm(status_text)
        if key in self._drr_table:
            return self._drr_table[key]
        candidates = [
            (ref_key, r) for ref_key, r in self._drr_table.items()
            if key in ref_key or ref_key in key
        ]
        if candidates:
            candidates.sort(key=lambda t: (t[1].rank or 999))
            return candidates[0][1]
        return DRRLookupResult()

    def lookup_fv_status(self, unique_status: str) -> FVLookupResult:
        if not unique_status or not isinstance(unique_status, str):
            return FVLookupResult()
        key = _norm(unique_status)
        if key in self._fv_table:
            return self._fv_table[key]
        candidates = [
            (ref_key, r) for ref_key, r in self._fv_table.items()
            if key in ref_key or ref_key in key
        ]
        if candidates:
            candidates.sort(key=lambda t: (t[1].fv_rank or 999))
            return candidates[0][1]
        return FVLookupResult()

    def drr_count(self) -> int:
        return len(self._drr_table)

    def fv_count(self) -> int:
        return len(self._fv_table)


_singleton: Optional[StatusLookup] = None


def get_lookup() -> StatusLookup:
    global _singleton
    if _singleton is None:
        _singleton = StatusLookup()
    return _singleton


def reload_lookup(reference_path: Optional[str] = None) -> StatusLookup:
    global _singleton
    _singleton = StatusLookup(reference_path)
    return _singleton


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().upper())


def _clean(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def _to_float(val) -> Optional[float]:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None
