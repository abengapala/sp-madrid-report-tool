"""
core/database.py
Database comparison engine.

Compares the uploaded CBS database export against the current report
to identify:
  1. NEW accounts  (ENDORSEMENT_TAG == 'NEW ENDS' in DB, not in report yet)
  2. PULLED OUT accounts (in report but completely absent from DB)
  3. OB / DPD / Bucket updates for existing accounts

Works for both Recovery (PLACEMENT=RECOVERY) and
Write-Off (PLACEMENT=WRITE OFF or NEW WRITE OFF).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


# ---------------------------------------------------------------------------
# DB column aliases
# ---------------------------------------------------------------------------
DB_PN_ALIASES      = ["PN_NO", "PN NO", "PN#", "PN", "ACCOUNT NO", "ACCOUNT NUMBER"]
DB_NAME_ALIASES    = ["CUST_NAME", "CUSTOMER NAME", "ACCOUNT NAME", "NAME"]
DB_OB_ALIASES      = ["OUTSTANDING_BALANCE", "OB", "BALANCE", "OUTSTANDING BALANCE"]
DB_DPD_ALIASES     = ["DPD", "DAYS PAST DUE"]
DB_BUCKET_ALIASES  = ["AGE", "BUCKET", "AGE BRACKET"]
DB_ENDO_ALIASES    = ["ENDS_DATE", "ENDORSEMENT DATE", "ENDO DATE"]
DB_TAG_ALIASES     = ["ENDORSEMENT_TAG", "ENDO TAG", "TAG"]
DB_PLACE_ALIASES   = ["PLACEMENT"]
DB_COLLECTOR_ALIASES = ["AGENCY", "COLLECTOR", "COLLECTOR NAME"]
DB_CUST_ID_ALIASES   = ["CUST_ID", "CUSTOMER ID", "CLIENT ID"]


def _find_col(df: pd.DataFrame, aliases: list) -> Optional[str]:
    for alias in aliases:
        for col in df.columns:
            if alias.upper().strip() == col.upper().strip():
                return col
        for col in df.columns:
            if alias.upper() in col.upper():
                return col
    return None


def _pn_str(val) -> str:
    try:
        return str(int(float(str(val)))) if val and str(val).replace(".", "").isdigit() else str(val).strip()
    except Exception:
        return str(val).strip()


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class DBCompareResult:
    new_accounts: pd.DataFrame        # accounts in DB with NEW ENDS not in report
    pulled_out_pns: list[str]         # PNs in report but not in DB at all
    ob_updates: dict[str, float]      # PN -> new OB
    dpd_updates: dict[str, int]       # PN -> new DPD
    bucket_updates: dict[str, str]    # PN -> new bucket/age
    placement_changes: dict[str, str] # PN -> new PLACEMENT (e.g. RECOVERY -> WRITE OFF)
    db_pns: set[str]                  # all PNs currently in DB for this placement


# ---------------------------------------------------------------------------
# Load database
# ---------------------------------------------------------------------------
def load_database_file(file_bytes: bytes) -> pd.DataFrame:
    """Load the CBS database export. Returns a cleaned DataFrame."""
    import io
    buf = io.BytesIO(file_bytes)

    try:
        df = pd.read_excel(buf, sheet_name=0, header=0)
    except Exception:
        buf.seek(0)
        df = pd.read_csv(buf)

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)

    # Normalize PN
    pn_col = _find_col(df, DB_PN_ALIASES)
    if pn_col:
        df["_pn"] = df[pn_col].apply(_pn_str)
    else:
        raise ValueError(f"Database missing PN column. Available: {list(df.columns)}")

    # Normalize placement
    place_col = _find_col(df, DB_PLACE_ALIASES)
    if place_col:
        df["_placement"] = df[place_col].astype(str).str.strip().str.upper()
    else:
        df["_placement"] = "UNKNOWN"

    return df


# ---------------------------------------------------------------------------
# Compare DB against report
# ---------------------------------------------------------------------------
def compare_db_to_report(
    db_df: pd.DataFrame,
    report_pns: set[str],
    target_placement: str = "RECOVERY",
) -> DBCompareResult:
    """
    Compare database to the current report for a specific placement.

    Args:
        db_df: Full database DataFrame (from load_database_file).
        report_pns: Set of PN strings currently in the report.
        target_placement: 'RECOVERY' or 'WRITEOFF' (matches PLACEMENT column).

    Returns:
        DBCompareResult with new/pulled-out/updated accounts.
    """
    placement_upper = target_placement.strip().upper()

    # Filter DB to the relevant placement(s)
    if "WRITE" in placement_upper:
        # Include both 'WRITE OFF' and 'NEW WRITE OFF'
        db_slice = db_df[
            db_df["_placement"].str.contains("WRITE", na=False)
        ].copy()
    else:
        # RECOVERY only
        db_slice = db_df[
            db_df["_placement"] == "RECOVERY"
        ].copy()

    db_pns = set(db_slice["_pn"].dropna().unique())

    # --- New accounts (NEW ENDS tag, not in report) ---
    tag_col = _find_col(db_slice, DB_TAG_ALIASES)
    new_accounts = pd.DataFrame()
    if tag_col:
        new_mask = (
            db_slice[tag_col].astype(str).str.upper().str.strip().isin(
                ["NEW ENDS", "NEW ENDORSEMENT", "NEW"]
            )
        ) & (~db_slice["_pn"].isin(report_pns))
        new_accounts = db_slice[new_mask].copy()

    # --- Pulled out (in report but not in DB for this placement) ---
    pulled_out_pns = [pn for pn in report_pns if pn not in db_pns]

    # --- OB / DPD / Bucket updates for existing accounts ---
    ob_updates: dict = {}
    dpd_updates: dict = {}
    bucket_updates: dict = {}
    placement_changes: dict = {}

    ob_col     = _find_col(db_slice, DB_OB_ALIASES)
    dpd_col    = _find_col(db_slice, DB_DPD_ALIASES)
    bucket_col = _find_col(db_slice, DB_BUCKET_ALIASES)
    place_col  = _find_col(db_slice, DB_PLACE_ALIASES)

    existing_pns = report_pns & db_pns
    for pn in existing_pns:
        rows = db_slice[db_slice["_pn"] == pn]
        if rows.empty:
            continue
        row = rows.iloc[0]
        if ob_col:
            try:
                ob_updates[pn] = float(row[ob_col])
            except (ValueError, TypeError):
                pass
        if dpd_col:
            try:
                dpd_updates[pn] = int(float(row[dpd_col]))
            except (ValueError, TypeError):
                pass
        if bucket_col:
            bkt = str(row.get(bucket_col, "") or "").strip()
            if bkt and bkt.lower() not in ("nan", "none", ""):
                bucket_updates[pn] = bkt
        if place_col:
            pl = str(row.get(place_col, "") or "").strip().upper()
            if pl and pl != placement_upper and "WRITE" not in placement_upper:
                placement_changes[pn] = pl

    return DBCompareResult(
        new_accounts=new_accounts,
        pulled_out_pns=pulled_out_pns,
        ob_updates=ob_updates,
        dpd_updates=dpd_updates,
        bucket_updates=bucket_updates,
        placement_changes=placement_changes,
        db_pns=db_pns,
    )


# ---------------------------------------------------------------------------
# Build a new report row from a DB row (for new accounts)
# ---------------------------------------------------------------------------
def build_account_row_from_db(db_row: pd.Series, template_columns: list[str]) -> dict:
    """
    Build a new report row dict from a DB row.
    Maps DB columns to report columns, leaves the rest blank.
    Used when adding a NEW ENDS account to the report.
    """
    pn_col     = _find_col(pd.DataFrame([db_row]), DB_PN_ALIASES)
    name_col   = _find_col(pd.DataFrame([db_row]), DB_NAME_ALIASES)
    ob_col     = _find_col(pd.DataFrame([db_row]), DB_OB_ALIASES)
    dpd_col    = _find_col(pd.DataFrame([db_row]), DB_DPD_ALIASES)
    bucket_col = _find_col(pd.DataFrame([db_row]), DB_BUCKET_ALIASES)
    endo_col   = _find_col(pd.DataFrame([db_row]), DB_ENDO_ALIASES)
    coll_col   = _find_col(pd.DataFrame([db_row]), DB_COLLECTOR_ALIASES)

    row_dict: dict = {col: "" for col in template_columns}

    # Map common report column names
    for col in template_columns:
        col_up = col.strip().upper()
        if "PN" in col_up and pn_col:
            row_dict[col] = _pn_str(db_row.get(pn_col, ""))
        elif "NAME" in col_up and name_col:
            row_dict[col] = str(db_row.get(name_col, "") or "").strip()
        elif col_up in ("OB", "OUTSTANDING", "BALANCE") and ob_col:
            try:
                row_dict[col] = float(db_row.get(ob_col, 0))
            except (ValueError, TypeError):
                pass
        elif col_up in ("DPD",) and dpd_col:
            try:
                row_dict[col] = int(float(db_row.get(dpd_col, 0)))
            except (ValueError, TypeError):
                pass
        elif "BUCKET" in col_up and bucket_col:
            row_dict[col] = str(db_row.get(bucket_col, "") or "").strip()
        elif "ENDO" in col_up and endo_col:
            try:
                raw = db_row.get(endo_col)
                if pd.notna(raw):
                    row_dict[col] = pd.Timestamp(raw).strftime("%m/%d/%Y")
            except Exception:
                pass
        elif "COLLECT" in col_up and coll_col:
            row_dict[col] = str(db_row.get(coll_col, "") or "").strip()

    return row_dict
