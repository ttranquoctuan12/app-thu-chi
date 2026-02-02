import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime, timedelta
import time
from io import BytesIO
import unicodedata
import pytz
import random
import string
import difflib

# ==================== 1. CẤU HÌNH & CSS ====================
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 3rem !important; }
    
    [data-testid="stDecoration"], [data-testid="stToolbar"], [data-testid="stHeaderActionElements"], 
    .stAppDeployButton, [data-testid="stStatusWidget"], footer, #MainMenu { display: none !important; }

    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 999; }
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important; visibility: visible !important;
        color: #000000 !important; background-color: rgba(255, 255, 255, 0.8); border-radius: 5px;
        z-index: 1000000;
    }

    [data-testid="stCameraInput"] { width: 100% !important; }
    .stTextInput input, .stNumberInput input { font-weight: bold; font-size: 0.9rem; min-height: 0px; }
    
    .balance-box { 
        padding: 15px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e0e0e0; 
        margin-bottom: 20px; text-align: center; position: relative;
    }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; color: #2ecc71; }
    
    .vt-def-box { background-color: #e3f2fd; padding: 15px; border-radius: 10px; border: 1px dashed #1565C0; margin-bottom: 15px; font-weight: bold; color: #0d47a1; }
    .vt-input-box { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border: 1px solid #81c784; margin-bottom: 15px; font-weight: bold; color: #1b5e20; }
    
    .suggestion-box {
        background-color: #fff9c4; border-left: 5px solid #fbc02d; padding: 10px;
        margin-top: -10px; margin-bottom: 15px; border-radius: 4px;
    }
    
    .total-row { background-color: #fff3cd; color: #b71c1c !important; font-weight: bold; padding: 10px; border-radius: 5px; text-align: right; margin-top: 10px; }
    .compact-row { border-bottom: 1px solid #f0f0f0; padding: 8px 0; font-size: 0.9rem; display: flex; align-items: center; }
    .c-name { font-weight: 600; color: #2c3e50; }
    
    /* Tối ưu nút Form */
    [data-testid="stFormSubmitButton"] > button { width: 100%; background-color: #ff4b4b; color: white; border: none; font-weight: bold; }
    [data-testid="stFormSubmitButton"] > button:hover { background-color: #ff2b2b; color: white; }

    .app-footer { text-align: center; margin-top: 50px; padding-top: 20px; border-top: 1px dashed #eee; color: #999; font-size: 0.8rem; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. KẾT NỐI API ====================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

@st.cache_resource
def get_gs_client():
    return gspread.authorize(get_creds())

def get_vn_time(): return datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))

def remove_accents(input_str):
    if not isinstance(input_str, str): return str(input_str)
    s = unicodedata.normalize('NFD', input_str)
    s = "".join([c for c in s if unicodedata.category(c) != 'Mn'])
    return s.replace("đ", "d").replace("Đ", "D")

def auto_capitalize(text):
    if not text or not isinstance(text, str): return ""
    text = text.strip()
    if len(text) > 0: return text[0].upper() + text[1:]
    return text

def format_vnd(amount):
    if pd.isna(amount): return "0"
    return "{:,.0f}".format(amount).replace(",", ".")

def generate_project_code(name):
    if not name: return ""
    clean = remove_accents(name).upper()
    initials = "".join([w[0] for w in clean.split() if w.isalnum()])
    date = get_vn_time().strftime('%d%m%y')
    return f"{initials}{date}"

def generate_material_code(name):
    clean = remove_accents(name).upper()
    initials = "".join([w[0] for w in clean.split() if w.isalnum()])[:3]
    suffix = ''.join(random.choices(string.digits, k=3))
    return f"VT{initials}{suffix}"

# ==================== 3. DATA LAYER ====================
def clear_data_cache(): st.cache_data.clear()

@st.cache_data(ttl=300)
def load_data_with_index():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame()
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype('int64')
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def load_materials_master():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("dm_vattu")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if 'TenVT' not in df.columns: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        return df
    except: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])

@st.cache_data(ttl=300)
def load_project_data():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
        for col in ['SoLuong', 'DonGia', 'ThanhTien']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df['Row_Index'] = range(2, len(df) + 2)
        return df
    except: return pd.DataFrame()

# --- CRUD ---
def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link])
    clear_data_cache()

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data"); r = int(row_idx)
    sheet.update(f"A{r}:E{r}", [[date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link]])
    clear_data_cache()

def delete_transaction(row_idx):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(int(row_idx)); clear_data_cache()

def save_project_material(proj_code, proj_name, mat_name, unit1, unit2, ratio, price_unit1, selected_unit, qty, note, is_new_item=False):
    client = get_gs_client(); wb = client.open("QuanLyThuChi")
    mat_code = ""
    if is_new_item:
        try: ws_master = wb.worksheet("dm_vattu")
        except: ws_master = wb.add_worksheet("dm_vattu", 1000, 6); ws_master.append_row(["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        mat_code = generate_material_code(mat_name)
        ws_master.append_row([mat_code, auto_capitalize(mat_name), unit1, unit2, ratio, price_unit1])
    else:
        df_master = load_materials_master()
        if not df_master.empty and 'TenVT' in df_master.columns:
            found = df_master[df_master['TenVT'] == mat_name]
            if not found.empty: mat_code = found.iloc[0]['MaVT']
    
    final_price = 0
    ratio_val = float(ratio) if ratio else 1.0
    if selected_unit == unit1: final_price = float(price_unit1)
    else: final_price = float(price_unit1) / ratio_val if ratio_val > 0 else 0
    thanh_tien = float(qty) * final_price
    
    try: ws_data = wb.worksheet("data_duan")
    except: ws_data = wb.add_worksheet("data_duan", 1000, 10); ws_data.append_row(["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
    ws_data.append_row([proj_code, auto_capitalize(proj_name), get_vn_time().strftime('%Y-%m-%d %H:%M:%S'), mat_code, auto_capitalize(mat_name), selected_unit, qty, final_price, thanh_tien, note])
    clear_data_cache()

def update_material_row(row_idx, qty, price, note):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
    r = int(row_idx)
    new_total = float(qty) * float(price)
    sheet.update_cell(r, 7, qty); sheet.update_cell(r, 9, new_total); sheet.update_cell(r, 10, note)
    clear_data_cache()

def delete_material_row(row_idx):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
    sheet.delete_rows(int(row_idx)); clear_data_cache()

def delete_material_master(row_idx):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("dm_vattu")
    sheet.delete_rows(int(row_idx)); clear_data_cache()

def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds(); service = build('drive', 'v3', credentials=creds); folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

# ==================== 4. EXCEL EXPORT ====================
def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_subtitle = workbook.add_format({'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': 'Times New Roman'})
        fmt_info = workbook.add_format({'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman', 'italic': True})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFFFF', 'font_size': 11, 'text_wrap': True, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_thu_bg = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_thu_money = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_open_bg = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'bold': True, 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_open_money = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'bold': True, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_red = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_color': 'red', 'bold': True, 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_tot = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFF00', 'font_size': 14, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'font_size': 14, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_normal = workbook.add_format({'border': 1, 'font_size': 11, 'valign': 'vcenter', 'font_name': 'Times New Roman'})

        ws = workbook.add_worksheet("SoQuy")
        ws.merge_range('A1:F1', "QUYẾT TOÁN", fmt_title)
        ws.merge_range('A2:F2', f"Từ ngày {start_date.strftime('%d/%m/%Y')} đến ngày {end_date.strftime('%d/%m/%Y')}", fmt_subtitle)
        ws.merge_range('A3:F3', f"Hệ thống Quyết toán - Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", fmt_info)
        ws.merge_range('A4:F4', "Người tạo: TUẤN VDS.HCM", fmt_info)
        
        headers = ["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): ws.write(4, c, h, fmt_header)
        ws.set_column('B:B', 40); ws.set_column('C:D', 15); ws.set_column('E:F', 18)

        start_row_idx = 5
        for i, row in df_report.iterrows():
            r = start_row_idx + i; loai = row['Loai']; bal = row['ConLai']
            if loai == 'Thu': c_fmt = fmt_thu_bg; m_fmt = fmt_thu_money; bal_fmt = fmt_money
            elif loai == 'Open': c_fmt = fmt_open_bg; m_fmt = fmt_open_money; bal_fmt = fmt_open_money
            else: c_fmt = fmt_normal; m_fmt = fmt_money; bal_fmt = fmt_red if bal < 0 else fmt_money

            ws.write(r, 0, row['STT'], c_fmt); ws.write(r, 1, row['Khoan'], c_fmt)
            ws.write(r, 2, row['NgayChi'], c_fmt); ws.write(r, 3, row['NgayNhan'], c_fmt)
            if loai == 'Open': ws.write(r, 4, "", m_fmt)
            else: ws.write(r, 4, row['SoTienShow'], m_fmt)
            ws.write(r, 5, bal, bal_fmt)
            
        l_row = start_row_idx + len(df_report)
        ws.merge_range(l_row, 0, l_row, 4, "TỔNG", fmt_tot)
        ws.write(l_row, 5, df_report['ConLai'].iloc[-1] if not df_report.empty else 0, fmt_tot_v)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

def export_project_materials_excel(df_proj, proj_code, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_subtitle = workbook.add_format({'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': 'Times New Roman'})
        fmt_info = workbook.add_format({'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman', 'italic': True})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFFFF', 'font_size': 11, 'text_wrap': True, 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_cell = workbook.add_format({'border': 1, 'valign': 'vcenter', 'font_name': 'Times New Roman', 'font_size': 11})
        fmt_num = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0', 'font_name': 'Times New Roman', 'font_size': 11})
        fmt_total_label = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman', 'font_size': 12})
        fmt_total_val = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'valign': 'vcenter', 'font_name': 'Times New Roman', 'font_size': 12})
        
        ws = workbook.add_worksheet("BangKeVatTu")
        ws.merge_range('A1:G1', "BẢNG KÊ VẬT TƯ", fmt_title)
        ws.merge_range('A2:G2', f"Dự án: {proj_name} (Mã: {proj_code})", fmt_subtitle)
        ws.merge_range('A3:G3', f"Hệ thống - Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", fmt_info)
        ws.merge_range('A4:G4', "Người tạo: TUẤN VDS.HCM", fmt_info)
        
        cols = ["STT", "Mã VT", "Tên VT", "ĐVT", "SL", "Đơn giá", "Thành tiền"]
        for i, h in enumerate(cols): ws.write(4, i, h, fmt_header)
        ws.set_column('A:A', 5); ws.set_column('B:B', 15); ws.set_column('C:C', 40); ws.set_column('D:D', 10); ws.set_column('E:G', 15)
        
        row_idx = 5; total_money = 0
        for i, row in df_proj.iterrows():
            ws.write(row_idx, 0, i+1, fmt_cell); ws.write(row_idx, 1, row['MaVT'], fmt_cell)
            ws.write(row_idx, 2, row['TenVT'], fmt_cell); ws.write(row_idx, 3, row['DVT'], fmt_cell)
            ws.write(row_idx, 4, row['SoLuong'], fmt_cell); ws.write(row_idx, 5, row['DonGia'], fmt_num)
            ws.write(row_idx, 6, row['ThanhTien'], fmt_num)
            total_money += row['ThanhTien']; row_idx += 1
            
        ws.merge_range(row_idx, 0, row_idx, 5, "TỔNG CỘNG TIỀN", fmt_total_label)
        ws.write(row_idx, 6, total_money, fmt_total_val)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

def process_report_data(df, start_date=None, end_date=None):
    if df.empty: return pd.DataFrame()
    df_all = df.sort_values(by=['Ngay', 'Row_Index']).copy()
    df_all['SignedAmount'] = df_all.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_all['ConLai'] = df_all['SignedAmount'].cumsum()
    
    if start_date and end_date:
        mask_before = df_all['Ngay'].dt.date < start_date
        df_before = df_all[mask_before]
        opening_balance = df_before.iloc[-1]['ConLai'] if not df_before.empty else 0
        mask_in = (df_all['Ngay'].dt.date >= start_date) & (df_all['Ngay'].dt.date <= end_date)
        df_proc = df_all[mask_in].copy()
        row_open = {'Row_Index': 0, 'Ngay': pd.Timestamp(start_date), 'Loai': 'Open', 'SoTien': 0, 'MoTa': f"Số dư đầu kỳ", 'HinhAnh': '', 'ConLai': opening_balance, 'SignedAmount': 0}
        df_proc = pd.concat([pd.DataFrame([row_open]), df_proc], ignore_index=True)
    else: df_proc = df_all.copy()

    if df_proc.empty: return pd.DataFrame()
    df_proc['STT'] = range(1, len(df_proc) + 1)
    df_proc['Khoan'] = df_proc.apply(lambda x: x['MoTa'] if x['Loai'] == 'Open' else auto_capitalize(x['MoTa']), axis=1)
    def get_date_str(row): return "" if row['Loai'] == 'Open' or pd.isna(row['Ngay']) else row['Ngay'].strftime('%d/%m/%Y')
    df_proc['NgayChi'] = df_proc.apply(lambda x: get_date_str(x) if x['Loai'] == 'Chi' else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: get_date_str(x) if x['Loai'] == 'Thu' else "", axis=1)
    df_proc['SoTienShow'] = df_proc.apply(lambda x: x['SoTien'] if x['Loai'] != 'Open' else 0, axis=1)
    return df_proc[['STT', 'Khoan', 'NgayChi', 'NgayNhan', 'SoTienShow', 'ConLai', 'Loai']]

# ==================== 5. UI COMPONENTS ====================

def render_dashboard_box(bal, thu, chi):
    text_color = "#2ecc71" if bal >= 0 else "#e74c3c"
    st.markdown(f"""
<div class="balance-box">
<div style="font-size: 1.2rem; font-weight: 900; color: #1565C0; margin-bottom: 5px;">HỆ THỐNG CÂN ĐỐI QUYẾT TOÁN</div>
<div style="color: #888; font-size: 0.8rem;">SỐ DƯ HIỆN TẠI</div>
<div class="balance-text" style="color: {text_color};">{format_vnd(bal)}</div>
<div style="display: flex; justify-content: space-between; margin-top: 5px; padding-top: 5px; border-top: 1px dashed #ddd; font-size: 0.9rem;">
<div style="color: #27ae60; font-weight: bold;">⬇️ {format_vnd(thu)}</div>
<div style="color: #c0392b; font-weight: bold;">⬆️ {format_vnd(chi)}</div>
</div>
</div>
<div style="text-align: left; margin-top: 0px; margin-bottom: 10px; margin-left: 5px; font-size: 0.7rem; color: #aaa; font-style: italic; font-weight: 600;">TUẤN VDS.HCM</div>
""", unsafe_allow_html=True)

# --- THU CHI UI (FORM) ---
def render_thuchi_input():
    with st.container(border=True):
        st.subheader("➕ Nhập Giao Dịch")
        with st.form("form_thu_chi", clear_on_submit=True):
            c1, c2 = st.columns([1.5, 1])
            d_date = c1.date_input("Ngày", get_vn_time())
            d_type = c2.selectbox("Loại", ["Chi", "Thu"])
            d_amount = st.number_input("Số tiền", min_value=0, step=5000)
            d_desc = st.text_input("Mô tả", placeholder="VD: Ăn sáng...")
            uploaded_file = st.file_uploader("Hình ảnh chứng từ", type=['jpg', 'png', 'jpeg'])
            submitted = st.form_submit_button("LƯU GIAO DỊCH")
            if submitted:
                if d_amount > 0 and d_desc.strip():
                    with st.spinner("Đang lưu dữ liệu..."):
                        link = ""
                        if uploaded_file: link = upload_image_to_drive(uploaded_file, f"{d_date}_{d_desc}.jpg")
                        add_transaction(d_date, d_type, d_amount, d_desc, link)
                    st.success("Đã lưu thành công!"); time.sleep(0.5); st.rerun()
                else: st.error("Vui lòng nhập số tiền và mô tả!")

def render_thuchi_history(df):
    if df.empty: st.info("Trống"); return
    df_sorted = df.sort_values(by='Ngay', ascending=False)
    for i, r in df_sorted.head(50).iterrows():
        c1, c2, c3 = st.columns([2, 1, 1], gap="small")
        with c1: st.markdown(f"**{r['MoTa']}**<br><span style='color:grey;font-size:0.8em'>{r['Ngay'].strftime('%d/%m')}</span>", unsafe_allow_html=True)
        with c2: st.markdown(f"<span style='color:{'green' if r['Loai']=='Thu' else 'red'};font-weight:bold'>{format_vnd(r['SoTien'])}</span>", unsafe_allow_html=True)
        with c3: 
            if st.button("🗑️", key=f"del_tc_{r['Row_Index']}"): delete_transaction(r['Row_Index']); st.rerun()
        st.markdown("<hr style='margin: 5px 0'>", unsafe_allow_html=True)

def render_thuchi_report(df):
    if df.empty: st.info("Chưa có dữ liệu."); return
    d1 = st.date_input("Từ", get_vn_time().replace(day=1), key="rp_d1"); d2 = st.date_input("Đến", get_vn_time(), key="rp_d2")
    df_r = process_report_data(df, d1, d2)
    st.dataframe(df_r, use_container_width=True)

def render_thuchi_export(df):
    st.markdown("**XUẤT BÁO CÁO QUYẾT TOÁN**")
    c1, c2 = st.columns(2)
    d1 = c1.date_input("Từ ngày", get_vn_time().replace(day=1), key="exp_d1")
    d2 = c2.date_input("Đến ngày", get_vn_time(), key="exp_d2")
    if st.button("TẢI BÁO CÁO EXCEL", type="primary", key="exp_tc_btn", use_container_width=True):
        with st.spinner("Đang tạo file..."):
            df_final = process_report_data(df, d1, d2)
            data = convert_df_to_excel_custom(df_final, d1, d2)
        st.success("Xong!")
        st.download_button("⬇️ DOWNLOAD FILE", data, f"QuyetToan_{d1.strftime('%d%m')}_{d2.strftime('%d%m')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

# ==================== 6. MODULE CONTAINERS ====================
def render_thuchi_module(layout_mode):
    df = load_data_with_index()
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum() if not df.empty else 0
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum() if not df.empty else 0
    render_dashboard_box(total_thu - total_chi, total_thu, total_chi)

    if "Laptop" in layout_mode:
        col_left, col_right = st.columns([1, 1.8], gap="medium")
        with col_left: render_thuchi_input()
        with col_right:
            t1, t2, t3 = st.tabs(["👁️ Sổ Quỹ", "📝 Lịch Sử", "📥 Xuất Báo Cáo"])
            with t1: render_thuchi_report(df)
            with t2: render_thuchi_history(df)
            with t3: render_thuchi_export(df)
    else:
        t1, t2, t3, t4 = st.tabs(["➕ NHẬP", "📝 LỊCH SỬ", "👁️ SỔ QUỸ", "📥 XUẤT"])
        with t1: render_thuchi_input()
        with t2: render_thuchi_history(df)
        with t3: render_thuchi_report(df)
        with t4: render_thuchi_export(df)

def render_vattu_module():
    vt_tabs = st.tabs(["➕ NHẬP VẬT TƯ", "📜 LỊCH SỬ (SỬA/XÓA)", "📦 KHO", "📥 XUẤT"])
    
    with vt_tabs[0]: # NHẬP LIỆU
        with st.container(border=True):
            df_pj = load_project_data()
            existing_projects = []
            if not df_pj.empty and 'TenDuAn' in df_pj.columns:
                existing_projects = df_pj['TenDuAn'].unique().tolist()
            
            sel_proj_option = st.selectbox("📁 Chọn Dự án:", [""] + existing_projects + ["➕ TẠO DỰ ÁN MỚI"], key="sel_proj_main")
            
            final_proj_name = ""
            if sel_proj_option == "➕ TẠO DỰ ÁN MỚI":
                final_proj_name = st.text_input("Nhập tên dự án mới:", placeholder="VD: Nhà A Tuấn...")
            elif sel_proj_option != "":
                final_proj_name = sel_proj_option
            
            if final_proj_name:
                st.session_state.curr_proj_name = final_proj_name
                proj_code = ""
                if sel_proj_option != "➕ TẠO DỰ ÁN MỚI" and not df_pj.empty:
                     found = df_pj[df_pj['TenDuAn'] == final_proj_name]
                     if not found.empty: proj_code = found.iloc[0]['MaDuAn']
                if not proj_code: proj_code = generate_project_code(final_proj_name)
                st.info(f"Mã Dự án: **{proj_code}**")

        if 'curr_proj_name' in st.session_state and st.session_state.curr_proj_name:
            st.markdown("👇 **Nhập chi tiết vật tư**")
            df_m = load_materials_master()
            m_list = df_m['TenVT'].unique().tolist() if not df_m.empty and 'TenVT' in df_m.columns else []
            # UX FIX: "TẠO VẬT TƯ MỚI" LÊN ĐẦU DANH SÁCH
            sel_vt = st.selectbox("📦 Chọn Vật tư:", ["", "++ TẠO VẬT TƯ MỚI ++"] + m_list)
            
            # --- SMART SUGGESTION ---
            if sel_vt == "++ TẠO VẬT TƯ MỚI ++":
                is_new = True
                vt_final = st.text_input("Nhập tên mới:")
                if vt_final and not df_m.empty and 'TenVT' in df_m.columns:
                    matches = difflib.get_close_matches(vt_final, df_m['TenVT'].tolist(), n=3, cutoff=0.5)
                    if matches:
                        st.markdown(f"<div class='suggestion-box'>💡 <b>Có phải bạn muốn nhập:</b></div>", unsafe_allow_html=True)
                        for match in matches:
                            if st.button(f"👉 {match}", key=f"sug_{match}"):
                                st.info(f"Vui lòng chọn **{match}** từ danh sách ở trên để tránh trùng lặp!")
            elif sel_vt != "":
                is_new = False
                vt_final = sel_vt
                if not df_m.empty and 'TenVT' in df_m.columns:
                    row = df_m[df_m['TenVT'] == vt_final].iloc[0]
                    u1 = str(row.get('DVT_Cap1', '')); u2 = str(row.get('DVT_Cap2', ''))
                    try: ratio = float(row.get('QuyDoi', 1)); p1 = float(row.get('DonGia_Cap1', 0))
                    except: ratio=1.0; p1=0.0
            else:
                is_new = False; vt_final = ""; u1, u2, ratio, p1 = "", "", 1.0, 0.0

            if is_new and vt_final:
                st.markdown(f"<div class='vt-def-box'>✨ Định nghĩa: {vt_final}</div>", unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                u1 = c1.text_input("ĐVT Lớn:", placeholder="Thùng")
                u2 = c2.text_input("ĐVT Nhỏ:", placeholder="Cái")
                ratio = c3.number_input("Quy đổi (Lớn=?Nhỏ):", min_value=1.0, value=1.0)
                p1 = c4.number_input("Giá nhập (Lớn):", min_value=0.0, step=1000.0)

            if vt_final:
                st.markdown(f"<div class='vt-input-box'>🔽 Nhập số lượng sử dụng</div>", unsafe_allow_html=True)
                
                # FORM NHẬP VẬT TƯ (TỐI ƯU TỐC ĐỘ)
                with st.form("vt_input_form", clear_on_submit=True):
                    unit_ops = [f"{u1} (Cấp 1)", f"{u2} (Cấp 2)"] if u2 else [f"{u1} (Cấp 1)"]
                    if not u1: unit_ops = ["Mặc định"]
                    
                    # Logic chọn Unit: MẶC ĐỊNH CẤP 2 (Index 1) NẾU CÓ
                    def_idx = 1 if u2 else 0
                    u_choice = st.radio("Đơn vị xuất:", unit_ops, horizontal=True, index=def_idx)
                    
                    c1, c2 = st.columns([1, 2])
                    qty = c1.number_input("Số lượng:", min_value=0.0, step=1.0)
                    note = c2.text_input("Ghi chú:")
                    
                    submitted = st.form_submit_button("➕ THÊM VÀO DỰ ÁN")
                    
                    if submitted:
                        if qty > 0:
                            # Tính lại giá khi Submit
                            sel_u = u1 if u1 and u1 in u_choice else (u2 if u2 else "Mặc định")
                            price_suggest = p1 if sel_u == u1 else (p1/ratio if ratio > 0 else 0)
                            
                            p_code_save = ""
                            if sel_proj_option != "➕ TẠO DỰ ÁN MỚI" and not df_pj.empty:
                                 f = df_pj[df_pj['TenDuAn'] == st.session_state.curr_proj_name]
                                 if not f.empty: p_code_save = f.iloc[0]['MaDuAn']
                            if not p_code_save: p_code_save = generate_project_code(st.session_state.curr_proj_name)

                            with st.spinner("Đang lưu..."):
                                save_project_material(p_code_save, st.session_state.curr_proj_name, vt_final, u1, u2, ratio, p1, sel_u, qty, note, is_new)
                            
                            st.success(f"Đã thêm: {qty} {sel_u}")
                            time.sleep(0.5); st.rerun()
                        else: st.error("Số lượng phải lớn hơn 0")
            
            # Show list
            if not df_pj.empty and 'MaDuAn' in df_pj.columns:
                p_code_curr = ""
                if sel_proj_option != "➕ TẠO DỰ ÁN MỚI":
                     f = df_pj[df_pj['TenDuAn'] == st.session_state.curr_proj_name]
                     if not f.empty: p_code_curr = f.iloc[0]['MaDuAn']
                if not p_code_curr: p_code_curr = generate_project_code(st.session_state.curr_proj_name)

                curr = df_pj[df_pj['MaDuAn'] == p_code_curr]
                if not curr.empty:
                    st.divider()
                    st.markdown(f"**Danh sách vừa thêm:**")
                    for i, row in curr.tail(5).iterrows():
                        st.markdown(f"<div class='compact-row'><span class='c-name'>{row['TenVT']}</span> <span class='c-meta'>({row['SoLuong']} {row['DVT']})</span> <span class='c-price' style='margin-left:auto'>{format_vnd(row['ThanhTien'])}</span></div>", unsafe_allow_html=True)

    with vt_tabs[1]: # LỊCH SỬ CHỈNH SỬA
        df_pj = load_project_data()
        if not df_pj.empty:
            proj_list = df_pj['TenDuAn'].unique()
            sel_pj = st.selectbox("Chọn dự án để chỉnh sửa:", proj_list, key="hist_sel")
            
            if 'edit_idx' not in st.session_state: st.session_state.edit_idx = None
            
            if st.session_state.edit_idx is not None:
                row_edit = df_pj[df_pj['Row_Index'] == st.session_state.edit_idx].iloc[0]
                with st.container(border=True):
                    st.info(f"✏️ Đang sửa: {row_edit['TenVT']}")
                    c1, c2 = st.columns(2)
                    n_qty = c1.number_input("Số lượng mới:", value=float(row_edit['SoLuong']), step=1.0, key="n_q")
                    n_note = c2.text_input("Ghi chú:", value=row_edit['GhiChu'], key="n_n")
                    if st.button("Lưu thay đổi", type="primary", key="s_ed"):
                        update_material_row(st.session_state.edit_idx, n_qty, row_edit['DonGia'], n_note)
                        st.session_state.edit_idx = None; st.rerun()
                    if st.button("Hủy", key="c_ed"): st.session_state.edit_idx = None; st.rerun()

            if sel_pj:
                view = df_pj[df_pj['TenDuAn'] == sel_pj]
                for i, row in view.iterrows():
                    c1, c2, c3, c4 = st.columns([0.5, 4, 2, 1.5])
                    c1.write(f"#{i+1}")
                    c2.markdown(f"<div class='c-name'>{row['TenVT']}</div><div class='c-meta'>{row['DVT']} | {row['GhiChu']}</div>", unsafe_allow_html=True)
                    c3.markdown(f"{row['SoLuong']} x {format_vnd(row['DonGia'])} = <b>{format_vnd(row['ThanhTien'])}</b>", unsafe_allow_html=True)
                    with c4:
                        bc1, bc2 = st.columns(2)
                        if bc1.button("✏️", key=f"e_{row['Row_Index']}"): st.session_state.edit_idx = row['Row_Index']; st.rerun()
                        if bc2.button("🗑️", key=f"d_{row['Row_Index']}"): delete_material_row(row['Row_Index']); st.rerun()
                    st.markdown("<div style='border-bottom:1px solid #eee; margin:2px 0'></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='total-row'>TỔNG CỘNG: {format_vnd(view['ThanhTien'].sum())}</div>", unsafe_allow_html=True)

    with vt_tabs[2]: # KHO
        df_m = load_materials_master()
        if not df_m.empty and 'TenVT' in df_m.columns: st.dataframe(df_m)
            
    with vt_tabs[3]: # XUẤT
        df_pj = load_project_data()
        if not df_pj.empty:
            p_opts = ["TẤT CẢ (TỔNG HỢP)"] + df_pj['TenDuAn'].unique().tolist()
            p_sel = st.selectbox("Chọn dự án xuất:", p_opts, key='xp_sel')
            if st.button("Tải Excel", key="xp_btn"):
                if "TẤT CẢ" in p_sel:
                    agg = df_pj.groupby(['MaVT', 'TenVT', 'DVT'], as_index=False).agg({'SoLuong': 'sum', 'ThanhTien': 'sum'})
                    agg['DonGia'] = agg.apply(lambda x: x['ThanhTien']/x['SoLuong'] if x['SoLuong']>0 else 0, axis=1)
                    data = export_project_materials_excel(agg, "ALL", "TỔNG HỢP")
                    st.download_button("Download Tổng Hợp", data, "TongHop.xlsx")
                else:
                    p_c = generate_project_code(p_sel)
                    data = export_project_materials_excel(df_pj[df_pj['TenDuAn'] == p_sel], p_c, p_sel)
                    st.download_button("Download Chi Tiết", data, f"VatTu_{p_c}.xlsx")

# ==================== 8. APP RUN ====================
with st.sidebar:
    st.title("⚙️ Cài đặt")
    if st.button("🔄 Làm mới"): clear_data_cache(); st.rerun()

_, col_t = st.columns([2, 1.5])
with col_t: is_laptop = st.toggle("💻 Laptop Mode", value=False)
layout_mode = "Laptop" if is_laptop else "Mobile"

main_tabs = st.tabs(["💰 THU CHI", "🏗️ VẬT TƯ DỰ ÁN"])
with main_tabs[0]: render_thuchi_module(layout_mode)
with main_tabs[1]: render_vattu_module()

st.markdown("<div class='app-footer'>Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)

