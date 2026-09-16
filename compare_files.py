import msoffcrypto, io, openpyxl, pandas as pd

def open_enc(path, pwd='cbs1234'):
    with open(path, 'rb') as f:
        enc = msoffcrypto.OfficeFile(f)
        enc.load_key(password=pwd)
        buf = io.BytesIO()
        enc.decrypt(buf)
        buf.seek(0)
        return openpyxl.load_workbook(buf)

def wb_to_df(wb, sheet):
    ws = wb[sheet]
    data = list(ws.values)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data[1:], columns=data[0])

tool_wb = open_enc(r'C:\Users\PATATA\Downloads\SP_MADRID_Recovery_Status_Report_as_of_September_16_2026.xlsx')
ref_wb  = open_enc(r'C:\Users\PATATA\Downloads\SP_MADRID Recovery Status Report as of September 09, 2026.xlsx')

print('=== SHEET ORDER ===')
print('TOOL:', tool_wb.sheetnames)
print('REF :', ref_wb.sheetnames)

print()
print('=== TRAILS UPLOAD - TOOL (first 3 rows) ===')
t = wb_to_df(tool_wb, 'Trails Upload')
print(t.head(3).to_string())

print()
print('=== TRAILS UPLOAD - REFERENCE (first 3 rows) ===')
r = wb_to_df(ref_wb, 'Trails Upload')
print(r.head(3).to_string())

print()
print('=== DAILY TOOL - column fill rate ===')
d = wb_to_df(tool_wb, 'DAILY')
for col in d.columns:
    non_null = d[col].dropna()
    non_null = non_null[non_null.astype(str).str.strip().str.upper() != 'NONE']
    non_null = non_null[non_null.astype(str).str.strip() != '']
    sample = str(non_null.iloc[0]) if len(non_null) > 0 else '(EMPTY)'
    print(f'  {col}: {len(non_null)}/{len(d)} filled | sample={sample}')

print()
print('=== DAILY REF - column fill rate ===')
d2 = wb_to_df(ref_wb, 'DAILY')
for col in d2.columns:
    non_null = d2[col].dropna()
    non_null = non_null[non_null.astype(str).str.strip().str.upper() != 'NONE']
    non_null = non_null[non_null.astype(str).str.strip() != '']
    sample = str(non_null.iloc[0]) if len(non_null) > 0 else '(EMPTY)'
    print(f'  {col}: {len(non_null)}/{len(d2)} filled | sample={sample}')
