"""
core/output.py
Assembles the final 4-sheet workbook and re-encrypts it.
"""
from __future__ import annotations

import io
from typing import Optional

import openpyxl
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.file_io import encrypt_workbook, DEFAULT_PASSWORD

# Exact column order per spec
DAILY_COLUMNS = [
    "DATE", "PRODUCT", "PN", "NAME", "OB", "DPD", "BUCKET",
    "ENDO DATE", "FLOWING DATE", "COLL TAGGING", "ACTION CODE",
    "STATUS REMARKS", "FV REMARKS", "CLIENT STATUS", "ADDRESS STATUS",
    "UNIT STATUS", "PULLED_OUT TAG", "PULLED_OUT DATE", "RFD",
    "GEO", "AGENCY", "COLLECTOR",
]

TRAILS_COLUMNS = [
    "FINANCIER ID", "APPLICATION ID", "CUSTOMER ID", "USER ID",
    "ACTION DATE", "ACTION TIME", "ACTION CODE", "CONTACT MODE",
    "PERSON CONTACTED", "PLACE CONTACTED", "CURRENCY", "ACTION AMOUNT",
    "NEXT ACTION DATE", "NEXT ACTION TIME", "REMINDER MODE",
    "CONTACTED BY", "REMARKS",
]

# Header style
_HEADER_FILL = PatternFill("solid", fgColor="2E4057")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)

_THIN = Side(style="thin", color="D0D0D0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _write_df_to_sheet(ws, df: pd.DataFrame, columns: list[str]) -> None:
    """Write a DataFrame to a worksheet with styled headers."""
    # Ensure all columns exist
    for col in columns:
        if col not in df.columns:
            df[col] = None

    # Write header
    for col_idx, col_name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.alignment = _HEADER_ALIGN
        cell.border = _BORDER

    # Write data rows
    for row_idx, (_, row) in enumerate(df[columns].iterrows(), start=2):
        for col_idx, col_name in enumerate(columns, start=1):
            val = row[col_name]
            # Convert NaN/NaT to None
            if isinstance(val, float) and pd.isna(val):
                val = None
            elif isinstance(val, pd.Timestamp):
                val = val.to_pydatetime()
            elif str(val) in ("nan", "NaT", "None"):
                val = None
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = _BORDER

    # Auto-width (capped at 60)
    for col_idx, col_name in enumerate(columns, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = len(col_name)
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx, min_row=2):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, min(len(str(cell.value)), 60))
        ws.column_dimensions[col_letter].width = max(12, min(max_len + 2, 60))


def _copy_action_code_sheet(ws_src, ws_dst) -> None:
    """Copy the ACTION CODE sheet verbatim from source to destination."""
    for row in ws_src.iter_rows(values_only=True):
        ws_dst.append(list(row))


def build_output_workbook(
    daily_df: pd.DataFrame,
    trails_df: pd.DataFrame,
    ptp_df: pd.DataFrame,
    action_code_df: pd.DataFrame,
    source_wb: Optional[openpyxl.Workbook] = None,
) -> openpyxl.Workbook:
    """
    Build the 4-sheet output workbook in exact spec order:
    1. DAILY
    2. Trails Upload
    3. PTP INVENTORY
    4. ACTION CODE
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # --- Sheet 1: Trails Upload (must be first per spec) ---
    ws_trails = wb.create_sheet("Trails Upload")
    _write_df_to_sheet(ws_trails, trails_df.copy(), TRAILS_COLUMNS)

    # --- Sheet 2: DAILY ---
    ws_daily = wb.create_sheet("DAILY")
    _write_df_to_sheet(ws_daily, daily_df.copy(), DAILY_COLUMNS)

    # --- Sheet 3: PTP INVENTORY ---
    ws_ptp = wb.create_sheet("PTP INVENTORY")
    _write_df_to_sheet(ws_ptp, ptp_df.copy(), DAILY_COLUMNS)

    # --- Sheet 4: ACTION CODE ---
    ws_ac = wb.create_sheet("ACTION CODE")
    if source_wb is not None and "ACTION CODE" in source_wb.sheetnames:
        # Copy verbatim from original workbook
        src_ws = source_wb["ACTION CODE"]
        for row in src_ws.iter_rows(values_only=True):
            ws_ac.append([v for v in row])
    else:
        # Write from dataframe
        for col_idx, col in enumerate(action_code_df.columns, start=1):
            ws_ac.cell(row=1, column=col_idx, value=col)
        for row_idx, (_, row) in enumerate(action_code_df.iterrows(), start=2):
            for col_idx, val in enumerate(row, start=1):
                ws_ac.cell(row=row_idx, column=col_idx, value=val)

    return wb


def generate_download(
    daily_df: pd.DataFrame,
    trails_df: pd.DataFrame,
    ptp_df: pd.DataFrame,
    action_code_df: pd.DataFrame,
    source_wb: Optional[openpyxl.Workbook],
    password: str = DEFAULT_PASSWORD,
) -> bytes:
    """Build, encrypt, and return the output .xlsx as bytes."""
    wb = build_output_workbook(daily_df, trails_df, ptp_df, action_code_df, source_wb)
    return encrypt_workbook(wb, password)
