"""
scratch_test.py
End-to-end verification script for all core modules.
"""
import pandas as pd
import numpy as np
from core.reconciler import reconcile, apply_reconcile, ReconcileResult
from core.remarks import parse_remarks_string, update_status_remarks, update_fv_remarks, format_remark
from core.trails import rebuild_trails
from core.ptp import detect_ptp_activity, apply_ptp_decisions, PTPCandidate
from core.action_codes import resolve_action_code, map_raw_status
from core.file_io import _is_numeric, _clean_ptp_date, _parse_date_flexible

def test_all():
    print("Testing action codes...")
    assert map_raw_status("Email sent to customer") == "EMAIL"
    assert map_raw_status("SMS delivered") == "SMS"
    assert map_raw_status("CALL WRONG NUMBER") == "NIS_KOR_CBR"
    assert resolve_action_code("PTP", "CMS") == "PTP"

    print("Testing reconciler...")
    daily_df = pd.DataFrame([
        {"PN": "800200010296001", "NAME": "Alice", "STATUS REMARKS": "09.01.2026 called"},
        {"PN": "800200010296002", "NAME": "Bob", "STATUS REMARKS": "09.01.2026 sms"},
        {"PN": "800200010296003", "NAME": "Charlie (Manual)", "STATUS REMARKS": "09.02.2026 visit"},
    ])
    
    db_df = pd.DataFrame([
        {"PN_NO": "800200010296001", "CUST_NAME": "Alice", "OUTSTANDING_BALANCE": 50000, "PLACEMENT": "RECOVERY", "AGENCY": "SP MADRID"},
        {"PN_NO": "800200010296002", "CUST_NAME": "Bob", "OUTSTANDING_BALANCE": 75000, "PLACEMENT": "RECOVERY", "AGENCY": "SP MADRID"},
        {"PN_NO": "800200010296004", "CUST_NAME": "David", "OUTSTANDING_BALANCE": 120000, "PLACEMENT": "RECOVERY", "AGENCY": "SP MADRID"},
    ])

    res = reconcile(daily_df, db_df, set())
    assert set(res.current_accounts) == {"800200010296001", "800200010296002", "800200010296003"}, f"Expected 3 accounts, got {res.current_accounts}"
    assert res.manually_added == ["800200010296003"], f"Expected manually_added ['800200010296003'], got {res.manually_added}"
    assert res.new_candidates == ["800200010296004"], f"Expected new_candidates ['800200010296004'], got {res.new_candidates}"

    # Apply adding 800200010296004
    report_date = pd.Timestamp("2026-09-16")
    updated = apply_reconcile(daily_df, db_df, None, None, report_date, res, pns_to_add=["800200010296004"])
    assert len(updated) == 4, f"Expected 4 rows, got {len(updated)}"
    assert "800200010296004" in updated["PN"].values
    assert "800200010296003" in updated["PN"].values # Manually added retained!

    print("Testing remarks logic...")
    existing_remark = "09.10.2026 Promised to pay on Friday, 09.01.2026 Initial call"
    entries = parse_remarks_string(existing_remark)
    assert len(entries) == 2, f"Expected 2 entries, got {len(entries)}"
    assert entries[0].date_str == "09.10.2026"
    assert entries[1].date_str == "09.01.2026"

    # DRR update with cutoff 09.10.2026
    drr_acct = pd.DataFrame([
        {"account_no": "800200010296001", "date_parsed": pd.Timestamp("2026-09-12"), "remark": "Client said will pay tomorrow", "action_code": "PTP", "remark_source": "CMS"},
        {"account_no": "800200010296001", "date_parsed": pd.Timestamp("2026-09-11"), "remark": "Called no answer", "action_code": "NA", "remark_source": "CMS"},
    ])
    new_remarks, had_new = update_status_remarks(existing_remark, drr_acct, cutoff_date=pd.Timestamp("2026-09-10"))
    assert had_new is True
    # Should contain 09.12.2026 and 09.11.2026 at the front, followed by kept entries before 09.10 (09.01.2026)
    assert "09.12.2026" in new_remarks
    assert "09.11.2026" in new_remarks
    assert "09.01.2026 Initial call" in new_remarks
    assert "09.10.2026" not in new_remarks # 09.10 was at or after cutoff, so replaced by new DRR

    print("Testing PTP detection...")
    drr_ptp = pd.DataFrame([
        {"account_no": "800200010296001", "date_parsed": pd.Timestamp("2026-09-16"), "remark": "KEPT - unit in warehouse", "action_code": "KEPT", "remark_source": "CMS"},
        {"account_no": "800200010296002", "date_parsed": pd.Timestamp("2026-09-16"), "remark": "REPO unit voluntarily surrendered", "action_code": "REPO", "remark_source": "CMS"},
        {"account_no": "800200099999999", "date_parsed": pd.Timestamp("2026-09-16"), "remark": "PTP 5000 on Friday", "action_code": "PTP", "remark_source": "CMS"},
    ])
    ptp_inventory = pd.DataFrame(columns=["PN", "NAME", "STATUS REMARKS"])
    ptp_res = detect_ptp_activity(drr_ptp, None, {"800200010296001", "800200010296002", "800200010296003", "800200010296004"}, ptp_inventory, updated)
    assert len(ptp_res.new_ptps) == 2, f"Expected 2 new PTPs (1001, 1002), got {len(ptp_res.new_ptps)}"
    assert len(ptp_res.out_of_book_ptps) == 1, f"Expected 1 out of book (9999), got {len(ptp_res.out_of_book_ptps)}"
    assert ptp_res.out_of_book_ptps[0].pn == "800200099999999"

    print("Testing trails rebuild...")
    existing_trails = pd.DataFrame([
        {"APPLICATION ID": 800200010296001, "FINANCIER ID": "CBS", "CUSTOMER ID": "CUST-1", "USER ID": "U1", "CONTACT MODE": "PHONE", "PERSON CONTACTED": "BORROWER", "PLACE CONTACTED": "HOME", "CONTACTED BY": "AGENT1"}
    ])
    trails_df, blanked = rebuild_trails(updated, drr_ptp, existing_trails, report_date=pd.Timestamp("2026-09-16"))
    assert len(trails_df) == 4
    # Account 800200010296001 had DRR on 2026-09-16
    row_a = trails_df[trails_df["APPLICATION ID"] == 800200010296001].iloc[0]
    assert row_a["ACTION DATE"] == "09.16.2026"
    assert row_a["NEXT ACTION DATE"] == "09.17.2026"
    assert row_a["FINANCIER ID"] == "CBS"
    assert row_a["CUSTOMER ID"] == "CUST-1"
    print("Testing Excel I/O with multi-sheet detection...")
    import io
    from core.file_io import load_database, load_field_file, load_drr

    # Create a mock multi-sheet workbook containing OVERALL FIELD and DATABASE
    out_buf = io.BytesIO()
    with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
        field_mock = pd.DataFrame([
            {"PN": "800200010296001", "DATE": "2026-09-16", "FV REMARK": "House visit done", "CLIENT STATUS": "POSITIVE", "ADDRESS STATUS": "POSITIVE", "UNIT STATUS": "POSITIVE", "PTP AMOUNT": 5000, "PTP-Date": "2026-09-20"},
        ])
        field_mock.to_excel(writer, sheet_name="OVERALL FIELD", index=False)
        
        db_mock = pd.DataFrame([
            {"PN_NO": "800200010296001", "CUST_NAME": "Alice", "PLACEMENT": "RECOVERY", "AGENCY": "SP MADRID", "OUTSTANDING_BALANCE": 50000},
            {"PN_NO": "800200010296002", "CUST_NAME": "Eve", "PLACEMENT": "RECOVERY", "AGENCY": "SP MADRID", "OUTSTANDING_BALANCE": 35000},
        ])
        db_mock.to_excel(writer, sheet_name="DATABASE", index=False)
    
    excel_bytes = out_buf.getvalue()
    
    # 1. Test loading field sheet
    f_df, f_warns = load_field_file(excel_bytes)
    assert len(f_df) == 1, f"Expected 1 field row, got {len(f_df)} (warns: {f_warns})"
    assert f_df.iloc[0]["pn"] == "800200010296001"
    assert f_df.iloc[0]["ptp_amount"] == 5000

    # 3. Test multi-sheet workbook with DRR + OVERALL FIELD + DATABASE
    full_buf = io.BytesIO()
    with pd.ExcelWriter(full_buf, engine="openpyxl") as writer:
        pd.DataFrame([{"Account No.": "800200010296001", "Date": "2026-09-16", "CMS STATUS": "PTP", "FINAL REMARK": "Promised to pay 5000"}]).to_excel(writer, sheet_name="DRR UPDATED", index=False)
        pd.DataFrame([{"PN": "800200010296001", "DATE": "2026-09-16", "FV REMARK": "Positive contact", "CLIENT STATUS": "POSITIVE"}]).to_excel(writer, sheet_name="OVERALL FIELD", index=False)
        pd.DataFrame([{"PN_NO": "800200010296001", "CUST_NAME": "Alice", "PLACEMENT": "RECOVERY", "AGENCY": "SP MADRID"}]).to_excel(writer, sheet_name="DATABASE", index=False)
    
    full_bytes = full_buf.getvalue()
    drr_auto = load_drr(full_bytes)
    field_auto, _ = load_field_file(full_bytes)
    db_auto, _ = load_database(full_bytes)

    assert len(drr_auto) == 1 and drr_auto.iloc[0]["account_no"] == "800200010296001"
    assert len(field_auto) == 1 and field_auto.iloc[0]["pn"] == "800200010296001"
    assert len(db_auto) == 1 and db_auto.iloc[0]["PN_NO"] == "800200010296001"

    print("ALL TESTS PASSED SUCCESSFULLY! [OK]")

if __name__ == "__main__":
    test_all()
