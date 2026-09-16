import msoffcrypto, io, openpyxl, pandas as pd, sys
sys.path.insert(0, r'C:\Users\PATATA\.gemini\antigravity-ide\scratch\sp-madrid-report-tool')
from core.file_io import load_drr

# Load the DRR
with open(r'C:\Users\PATATA\Downloads\DRR UPDATED.xlsx', 'rb') as f:
    drr_bytes = f.read()

warn = []
drr_df = load_drr(drr_bytes, warnings=warn)
print("DRR warnings:", warn)
print("DRR shape:", drr_df.shape)
print("DRR columns:", drr_df.columns.tolist())
print("DRR date range:", drr_df['date_parsed'].min(), "to", drr_df['date_parsed'].max())
print("DRR sample rows:")
print(drr_df.head(5).to_string())
print()
print("Unique action codes sample:", drr_df['action_code'].dropna().unique()[:20])
print()

# Check specific account that showed empty in trails
pn = '800200010125478'
acct_rows = drr_df[drr_df['account_no'] == pn]
print(f"DRR rows for PN {pn}: {len(acct_rows)}")
if len(acct_rows) > 0:
    print(acct_rows.head(5).to_string())

# Check what date is the report date
report_date = pd.Timestamp('2026-09-16')
today_rows = drr_df[drr_df['date_parsed'].notna() & (drr_df['date_parsed'].dt.date == report_date.date())]
print(f"\nDRR rows matching report date {report_date.date()}: {len(today_rows)}")
print(today_rows.head(5).to_string())
