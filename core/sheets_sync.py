"""
core/sheets_sync.py
Google Sheets synchronization for Database Manager.

Allows persisting the database to a dedicated Google Sheet tab ('SP_MADRID_DB')
so it survives Deep Freeze reboots, PC resets, and works across multiple machines.
Existing worksheets in the user's spreadsheet are NEVER modified or touched.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple
import pandas as pd

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
WORKSHEET_NAME = "SP_MADRID_DB"


def _get_secrets() -> Optional[dict]:
    """Retrieve secrets from streamlit.secrets or .streamlit/secrets.toml."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            return {
                "sheets": dict(st.secrets.get("sheets", {})),
                "gcp_service_account": dict(st.secrets["gcp_service_account"]),
            }
    except Exception:
        pass

    secrets_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        ".streamlit",
        "secrets.toml",
    )
    if os.path.exists(secrets_path) and tomllib is not None:
        try:
            with open(secrets_path, "rb") as f:
                return tomllib.load(f)
        except Exception:
            return None
    return None


def is_sheets_configured() -> bool:
    """Check if Google Sheets credentials and spreadsheet URL are present."""
    sec = _get_secrets()
    if not sec:
        return False
    return bool(sec.get("gcp_service_account") and sec.get("sheets", {}).get("spreadsheet_url"))


def _get_worksheet():
    """Connect to gspread and get the dedicated SP_MADRID_DB worksheet."""
    import gspread
    from google.oauth2.service_account import Credentials

    sec = _get_secrets()
    if not sec:
        raise ValueError("Google Sheets secrets are not configured.")

    creds_dict = sec["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)

    url = sec["sheets"]["spreadsheet_url"]
    sh = gc.open_by_url(url)

    target_tab = sec.get("sheets", {}).get("worksheet_name", WORKSHEET_NAME)

    # Check if target tab exists, otherwise safely create it
    existing_titles = [ws.title for ws in sh.worksheets()]
    if target_tab not in existing_titles:
        ws = sh.add_worksheet(title=target_tab, rows=1000, cols=30)
    else:
        ws = sh.worksheet(target_tab)

    return ws


def load_db_from_sheets() -> Optional[pd.DataFrame]:
    """
    Fetch the database from the Google Sheets tab 'SP_MADRID_DB'.
    Returns DataFrame if data exists, else None.
    """
    if not is_sheets_configured():
        return None

    try:
        ws = _get_worksheet()
        records = ws.get_all_records()
        if not records:
            # Check if there are only header values or empty
            all_values = ws.get_all_values()
            if len(all_values) <= 1:
                return None
            headers = [str(h).strip() for h in all_values[0]]
            data = all_values[1:]
            df = pd.DataFrame(data, columns=headers)
        else:
            df = pd.DataFrame(records)

        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(how="all").reset_index(drop=True)

        if df.empty or len(df.columns) == 0:
            return None

        # Clean string/numeric columns
        for col in df.columns:
            if "PN" in col.upper() or "ACCOUNT" in col.upper():
                df[col] = df[col].astype(str).str.strip().apply(
                    lambda v: str(int(float(v))) if v and v.replace(".", "").isdigit() and not v.endswith(".0") else v
                )

        return df
    except Exception as e:
        print(f"Error loading database from Google Sheets: {e}")
        return None


def save_db_to_sheets(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Sync DataFrame to the Google Sheets tab 'SP_MADRID_DB'.
    WARNING: Only modifies the SP_MADRID_DB worksheet, leaving other sheets completely untouched.
    """
    if not is_sheets_configured():
        return False, "Google Sheets credentials not configured."

    try:
        ws = _get_worksheet()

        # Format dataframe for export
        export_df = df.copy()
        export_df = export_df.fillna("")

        # Convert datetime objects to string
        for col in export_df.columns:
            if pd.api.types.is_datetime64_any_dtype(export_df[col]):
                export_df[col] = export_df[col].dt.strftime("%m/%d/%Y")
            else:
                export_df[col] = export_df[col].astype(str).replace("nan", "").replace("None", "")

        header = list(export_df.columns)
        values = [header] + export_df.values.tolist()

        # Ensure sheet grid is large enough for all rows and columns
        req_rows = max(len(values) + 10, 100)
        req_cols = max(len(header) + 5, 20)
        if ws.row_count < req_rows or ws.col_count < req_cols:
            ws.resize(rows=max(ws.row_count, req_rows), cols=max(ws.col_count, req_cols))

        # Clear only this dedicated worksheet (SP_MADRID_DB)
        ws.clear()
        # Write values
        ws.update(values)

        return True, f"Successfully synced {len(export_df)} accounts to Google Sheet ('{ws.title}')"
    except Exception as e:
        return False, f"Failed to save to Google Sheet: {e}"
