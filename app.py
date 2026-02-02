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

# ==============================================================================
# 1. CẤU HÌNH HỆ THỐNG & GIAO DIỆN (UI CONFIG)
# ==============================================================================
st.set_page_config(
    page_title="HỆ THỐNG ERP CÁ NHÂN",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS TÙY CHỈNH ---
st.markdown("""
<style>
    /* Tổng quan */
    .block-container { padding-top: 1.5rem !important; padding-bottom: 3rem !important; }
    
    /* Ẩn các thành phần mặc định của Streamlit */
    [data-testid="stDecoration"], [data-testid="stToolbar"], [data-testid="stHeaderActionElements"], 
    .stAppDeployButton, [data-testid="stStatusWidget"], footer, #MainMenu { display: none !important; }

    /* Header trong suốt */
    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 999; }
    
    /* Nút đóng mở Sidebar đẹp hơn */
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important; visibility: visible !important;
        color: #333 !important; background-color: rgba(255, 255, 255, 0.8); 
        border-radius: 5px; z-index: 1000000;
    }

    /* Input đậm */
    .stTextInput input, .stNumberInput input, .stDateInput input { font-weight: 600; font-size: 0.95rem; }
    
    /* Box Số dư Dashboard */
    .balance-box { 
        padding: 20px; border-radius: 15px; 
        background: linear-gradient(135deg, #fdfbfb 0%, #ebedee 100%); 
        border: 1px solid #d1d5db; 
        margin-bottom: 25px; text-align: center; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .balance-title { font-size: 1rem; color: #6b7280; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }
    .balance-value { font-size: 2.5rem !important; font-weight: 900; margin: 0; color: #10b981; text-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
    
    /* UI Vật tư */
    .vt-def-box { background-color: #eff6ff; padding: 15px; border-radius: 8px; border-left: 4px solid #3b82f6; margin-bottom: 15px; font-weight: 600; color: #1e40af; }
    .vt-input-box { background-color: #f0fdf4; padding: 15px; border-radius: 8px; border-left: 4px solid #22c55e; margin-bottom: 15px; font-weight: 600; color: #15803d; }
    
    .suggestion-box {
        background-color: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px;
        margin-top: -10px; margin-bottom: 15px; border-radius: 4px; font-size: 0.9rem;
    }
    
    /* Danh sách gọn */
    .compact-row { 
        border-bottom: 1px solid #f3f4f6; padding: 10px 0; 
        font-size: 0.95rem; display: flex; align-items: center; justify-content: space-between;
    }
    .c-name { font-weight: 700; color: #1f2937; }
    .c-meta { color: #6b7280; font-size: 0.85rem; font-style: italic; }
    
    .total-row { 
        background-color: #fff7ed; color: #c2410c !important; font-weight: 800; 
        padding: 12px; border-radius: 6px; text-align: right; margin-top: 15px; font-size: 1.1rem; border: 1px solid #fed7aa;
    }
    
    /* Nút bấm tối ưu */
    [data-testid="stFormSubmitButton"] > button { width: 100%; background-color: #ef4444; color: white; border: none; font-weight: 700; transition: all 0.3s; }
    [data-testid="stFormSubmitButton"] > button:hover { background-color: #dc2626; transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.2); }

    /* Footer */
    .app-footer { text-align: center; margin-top: 60px; padding-top: 20px; border-top: 1px dashed #e5e7eb; color: #9ca3af; font-size: 0.8rem; font-style: italic; }
    
    /* Logo Banner */
    .banner-img { width: 100%; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. KẾT NỐI API & TIỆN ÍCH (BACKEND UTILS)
# ==============================================================================
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

def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds(); service = build('drive', 'v3', credentials=creds); folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

# ==============================================================================
# 3. QUẢN LÝ DỮ LIỆU (DATA LAYER - CACHED)
# ==============================================================================
def clear_data_cache(): st.cache_data.clear()

@st.cache_data(ttl=60)
def load_config():
    client = get_gs_client(); wb = client.open("QuanLyThuChi")
    try: sheet = wb.worksheet("config")
    except:
        sheet = wb.add_worksheet("config", 100, 2)
        sheet.append_row(["Key", "Value"]); sheet.append_row(["admin_pwd", "admin123"]); sheet.append_row(["viewer_pwd", "xem123"])
    records = sheet.get_all_records()
    config = {row['Key']: str(row['Value']) for row in records}
    if 'admin_pwd' not in config: config['admin_pwd'] = "admin123"
    if 'viewer_pwd' not in config: config['viewer_pwd'] = "xem123"
    return config

def update_password(role, new_pass):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("config")
    cell = sheet.find(f"{role}_pwd")
    if cell: sheet.update_cell(cell.row, 2, new_pass); clear_data_cache(); return True
    return False

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

# --- CÁC HÀM GHI (WRITE) - KHÔNG CACHE ---
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
    # Cập nhật danh mục nếu là mới
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
    
    # Tính giá
    final_price = 0
    ratio_val = float(ratio) if ratio else 1.0
    if selected_unit == unit1: final_price = float(price_unit1)
    else: final_price = float(price_unit1) / ratio_val if ratio_val > 0 else 0
    thanh_tien = float(qty) * final_price
    
    # Ghi dữ liệu
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

# ==============================================================================
# 4. EXCEL EXPORT (REPORTING LAYER)
# ==============================================================================
def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        # Styles
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
        date_str = f"Từ ngày {start_date.strftime('%d/%m/%Y')} đến ngày {end_date.strftime('%d/%m/%Y')}"
        ws.merge_range('A2:F2', date_str, fmt_subtitle)
        current_time_str = get_vn_time().strftime("%H:%M %d/%m/%Y")
        ws.merge_range('A3:F3', f"Hệ thống ERP Cá Nhân - Xuất lúc: {current_time_str}", fmt_info)
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
        fin_bal = df_report['ConLai'].iloc[-1] if not df_report.empty else 0
        ws.merge_range(l_row, 0, l_row, 4, "TỔNG", fmt_tot)
        ws.write(l_row, 5, fin_bal, fmt_tot_v)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

def export_project_materials_excel(df_proj, proj_code, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        # Styles
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
        ws.merge_range('A3:G3', f"Hệ thống ERP Cá Nhân - Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", fmt_info)
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

# ==============================================================================
# 5. CÁC MODULE GIAO DIỆN (UI MODULES)
# ==============================================================================

# --- MÀN HÌNH ĐĂNG NHẬP ---
def render_login_screen():
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #1e3a8a;'>HỆ THỐNG ERP CÁ NHÂN</h1>", unsafe_allow_html=True)
        st.markdown("<div style='text-align:center; color: #6b7280; margin-bottom: 20px;'>Đăng nhập để tiếp tục</div>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            user = st.text_input("Tên đăng nhập (admin/viewer):").lower().strip()
            pwd = st.text_input("Mật khẩu:", type="password")
            submit = st.form_submit_button("ĐĂNG NHẬP")
            
            if submit:
                with st.spinner("Đang xác thực..."):
                    config = load_config()
                    if user == "admin" and pwd == config['admin_pwd']:
                        st.session_state.role = "admin"; st.rerun()
                    elif user == "viewer" and pwd == config['viewer_pwd']:
                        st.session_state.role = "viewer"; st.rerun()
                    else: st.error("❌ Tên đăng nhập hoặc mật khẩu không đúng!")

# --- THANH BÊN (SIDEBAR) ---
def render_sidebar():
    with st.sidebar:
        # Logo/Banner Placeholder
        st.markdown("### 🏢 TUẤN VDS.HCM")
        
        role_label = "QUẢN TRỊ VIÊN (ADMIN)" if st.session_state.role == 'admin' else "KHÁCH (VIEWER)"
        st.success(f"Xin chào: **{role_label}**")
        
        st.divider()
        
        # Menu Cài đặt
        st.markdown("### ⚙️ CÀI ĐẶT")
        with st.expander("Đổi mật khẩu"):
            with st.form("change_pass"):
                new_p = st.text_input("Mật khẩu mới:", type="password")
                cfm_p = st.text_input("Nhập lại:", type="password")
                if st.form_submit_button("Cập nhật"):
                    if new_p and new_p == cfm_p:
                        if update_password(st.session_state.role, new_p): st.success("Thành công!")
                    else: st.error("Mật khẩu không khớp!")
        
        if st.button("Đăng xuất", type="secondary"): st.session_state.role = None; st.rerun()
        if st.session_state.role == 'admin':
            if st.button("🔄 Làm mới dữ liệu"): clear_data_cache(); st.rerun()

# --- MODULE THU CHI ---
def render_thuchi_module(is_laptop):
    df = load_data_with_index()
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum() if not df.empty else 0
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum() if not df.empty else 0
    
    # Dashboard
    st.markdown(f"""
    <div class='balance-box'>
        <div class='balance-title'>SỐ DƯ HIỆN TẠI</div>
        <div class='balance-value'>{format_vnd(total_thu - total_chi)}</div>
        <div style='display: flex; justify-content: space-between; margin-top: 15px; font-weight: 600;'>
            <div style='color: #10b981;'>⬇️ THU: {format_vnd(total_thu)}</div>
            <div style='color: #ef4444;'>⬆️ CHI: {format_vnd(total_chi)}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Tabs
    tabs_titles = ["📝 LỊCH SỬ", "👁️ BÁO CÁO", "📥 XUẤT EXCEL"]
    if st.session_state.role == 'admin': tabs_titles.insert(0, "➕ NHẬP LIỆU")
    
    tabs = st.tabs(tabs_titles)
    
    # Tab Nhập
    if st.session_state.role == 'admin':
        with tabs[0]:
            with st.form("tc_input", clear_on_submit=True):
                c1, c2 = st.columns([1.5, 1])
                d_date = c1.date_input("Ngày", get_vn_time())
                d_type = c2.selectbox("Loại", ["Chi", "Thu"])
                d_amt = st.number_input("Số tiền", min_value=0, step=10000)
                d_desc = st.text_input("Mô tả")
                img = st.file_uploader("Chứng từ (Ảnh)", type=['jpg','png'])
                if st.form_submit_button("LƯU GIAO DỊCH"):
                    if d_amt > 0 and d_desc:
                        with st.spinner("Đang lưu..."):
                            link = upload_image_to_drive(img, f"TC_{d_date}_{d_desc}") if img else ""
                            add_transaction(d_date, d_type, d_amt, d_desc, link)
                        st.success("Đã lưu!"); time.sleep(0.5); st.rerun()
                    else: st.warning("Nhập thiếu thông tin!")
    
    # Các Tab khác (History, Report, Export) - Logic giữ nguyên từ v7.2 nhưng đặt vào đúng tab index
    idx_off = 1 if st.session_state.role == 'admin' else 0
    
    with tabs[idx_off]: # Lịch sử
        if df.empty: st.info("Chưa có dữ liệu")
        else:
            for i, r in df.sort_values(by='Ngay', ascending=False).head(50).iterrows():
                c1, c2, c3 = st.columns([3, 1.5, 0.5])
                with c1: st.markdown(f"**{r['MoTa']}**<br><span style='font-size:0.8rem;color:#666'>{r['Ngay'].strftime('%d/%m/%Y')}</span>", unsafe_allow_html=True)
                with c2: st.markdown(f"<span style='color:{'#10b981' if r['Loai']=='Thu' else '#ef4444'};font-weight:bold'>{format_vnd(r['SoTien'])}</span>", unsafe_allow_html=True)
                with c3:
                    if st.session_state.role == 'admin':
                        if st.button("🗑️", key=f"del_tc_{r['Row_Index']}"): delete_transaction(r['Row_Index']); st.rerun()
                st.divider()

    with tabs[idx_off+1]: # Sổ quỹ
        d1 = st.date_input("Từ ngày", get_vn_time().replace(day=1), key="d1_tc")
        d2 = st.date_input("Đến ngày", get_vn_time(), key="d2_tc")
        st.dataframe(process_report_data(df, d1, d2), use_container_width=True)

    with tabs[idx_off+2]: # Xuất
        st.info("Chọn khoảng thời gian ở Tab Báo Cáo trước khi xuất.")
        if st.button("TẢI FILE EXCEL", key="exp_tc"):
            data = convert_df_to_excel_custom(process_report_data(df, d1, d2), d1, d2)
            st.download_button("⬇️ DOWNLOAD", data, "QuyetToan.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# --- MODULE VẬT TƯ ---
def render_vattu_module():
    tabs_titles = ["📦 KHO & QUY ĐỔI", "📜 LỊCH SỬ DỰ ÁN", "📥 XUẤT BÁO CÁO"]
    if st.session_state.role == 'admin': tabs_titles.insert(0, "➕ NHẬP VẬT TƯ")
    vt_tabs = st.tabs(tabs_titles)
    
    # 1. NHẬP (ADMIN)
    if st.session_state.role == 'admin':
        with vt_tabs[0]:
            # Chọn dự án
            with st.container(border=True):
                df_pj = load_project_data()
                projs = df_pj['TenDuAn'].unique().tolist() if not df_pj.empty else []
                p_sel = st.selectbox("📁 Dự án:", [""]+projs+["➕ TẠO MỚI"], key="p_sel")
                
                final_p = st.text_input("Tên dự án mới:") if p_sel == "➕ TẠO MỚI" else p_sel
                if final_p:
                    st.session_state.curr_proj_name = final_p
                    p_code = ""
                    if p_sel != "➕ TẠO MỚI" and not df_pj.empty:
                        found = df_pj[df_pj['TenDuAn'] == final_p]
                        if not found.empty: p_code = found.iloc[0]['MaDuAn']
                    if not p_code: p_code = generate_project_code(final_p)
                    st.caption(f"Mã dự án: {p_code}")

            if 'curr_proj_name' in st.session_state and st.session_state.curr_proj_name:
                st.markdown("---")
                df_m = load_materials_master()
                m_list = df_m['TenVT'].unique().tolist() if not df_m.empty else []
                
                # Smart Select
                sel_vt = st.selectbox("📦 Chọn Vật tư:", ["", "++ TẠO MỚI ++"] + m_list)
                
                # Logic điền form
                is_new = False; vt_final = ""; u1 = ""; u2 = ""; ratio = 1.0; p1 = 0.0
                
                if sel_vt == "++ TẠO MỚI ++":
                    is_new = True
                    vt_final = st.text_input("Tên vật tư mới:")
                    # Fuzzy match suggestion
                    if vt_final and not df_m.empty:
                        matches = difflib.get_close_matches(vt_final, df_m['TenVT'].tolist(), n=3, cutoff=0.5)
                        if matches: st.warning(f"Gợi ý: Có phải '{matches[0]}'? Hãy chọn ở trên để tránh trùng!")
                elif sel_vt:
                    vt_final = sel_vt
                    if not df_m.empty:
                        row = df_m[df_m['TenVT'] == vt_final].iloc[0]
                        u1 = str(row.get('DVT_Cap1', '')); u2 = str(row.get('DVT_Cap2', ''))
                        try: ratio = float(row.get('QuyDoi', 1)); p1 = float(row.get('DonGia_Cap1', 0))
                        except: pass
                
                # Form Input
                if vt_final:
                    if is_new:
                        c1, c2, c3, c4 = st.columns(4)
                        u1 = c1.text_input("ĐVT Lớn (C1):")
                        u2 = c2.text_input("ĐVT Nhỏ (C2):")
                        ratio = c3.number_input("Quy đổi (1 C1 = ? C2):", min_value=1.0)
                        p1 = c4.number_input("Giá nhập (theo C1):", min_value=0.0)
                    
                    with st.form("vt_add"):
                        unit_opts = [f"{u1} (Cấp 1)", f"{u2} (Cấp 2)"] if u2 else [f"{u1} (Cấp 1)"]
                        if not u1: unit_opts = ["Mặc định"]
                        
                        u_choice = st.radio("Đơn vị xuất:", unit_opts, horizontal=True, index=(1 if u2 else 0))
                        c1, c2 = st.columns([1, 2])
                        qty = c1.number_input("Số lượng:", min_value=0.0)
                        note = c2.text_input("Ghi chú:")
                        
                        if st.form_submit_button("➕ THÊM VÀO DỰ ÁN"):
                            if qty > 0:
                                sel_u = u1 if u1 and u1 in u_choice else (u2 if u2 else "Mặc định")
                                p_save = generate_project_code(st.session_state.curr_proj_name) 
                                if p_sel != "➕ TẠO MỚI" and not df_pj.empty: # Lấy lại mã cũ nếu có
                                    f = df_pj[df_pj['TenDuAn'] == st.session_state.curr_proj_name]
                                    if not f.empty: p_save = f.iloc[0]['MaDuAn']
                                
                                with st.spinner("Đang lưu..."):
                                    save_project_material(p_save, st.session_state.curr_proj_name, vt_final, u1, u2, ratio, p1, sel_u, qty, note, is_new)
                                st.success(f"Đã thêm {qty} {sel_u}"); time.sleep(0.5); st.rerun()

    # Các Tab Xem/Sửa/Xóa/Xuất (Logic index lệch tùy theo role)
    idx_base = 1 if st.session_state.role == 'admin' else 0
    
    with vt_tabs[idx_base + 1]: # LỊCH SỬ DỰ ÁN
        df_pj = load_project_data()
        if not df_pj.empty:
            all_pj = df_pj['TenDuAn'].unique().tolist()
            view_pj = st.selectbox("Xem dự án:", all_pj, key="v_pj")
            
            if view_pj:
                data_view = df_pj[df_pj['TenDuAn'] == view_pj]
                
                # Chế độ Sửa (Chỉ Admin)
                if st.session_state.role == 'admin':
                    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
                    if st.session_state.edit_id:
                        r_edit = df_pj[df_pj['Row_Index'] == st.session_state.edit_id].iloc[0]
                        with st.form("edit_form"):
                            st.info(f"Sửa: {r_edit['TenVT']}")
                            nq = st.number_input("Số lượng mới:", value=float(r_edit['SoLuong']))
                            nn = st.text_input("Ghi chú:", value=r_edit['GhiChu'])
                            if st.form_submit_button("Lưu thay đổi"):
                                update_material_row(st.session_state.edit_id, nq, r_edit['DonGia'], nn)
                                st.session_state.edit_id = None; st.rerun()
                
                # Hiển thị list
                for i, r in data_view.iterrows():
                    c1, c2, c3 = st.columns([3, 2, 1])
                    c1.markdown(f"**{r['TenVT']}**<br><span style='color:#666;font-size:0.9em'>{r['DVT']} | {r['GhiChu']}</span>", unsafe_allow_html=True)
                    c2.markdown(f"{r['SoLuong']} x {format_vnd(r['DonGia'])} = **{format_vnd(r['ThanhTien'])}**")
                    with c3:
                        if st.session_state.role == 'admin':
                            if st.button("✏️", key=f"e_{r['Row_Index']}"): st.session_state.edit_id = r['Row_Index']; st.rerun()
                            if st.button("🗑️", key=f"d_{r['Row_Index']}"): delete_material_row(r['Row_Index']); st.rerun()
                    st.divider()
                st.success(f"TỔNG CỘNG: {format_vnd(data_view['ThanhTien'].sum())} VNĐ")

    with vt_tabs[idx_base]: # KHO (Đảo vị trí cho hợp lý)
        df_m = load_materials_master()
        st.dataframe(df_m, use_container_width=True)

    with vt_tabs[idx_base + 2]: # XUẤT
        df_pj = load_project_data()
        if not df_pj.empty:
            opts = ["TẤT CẢ (TỔNG HỢP)"] + df_pj['TenDuAn'].unique().tolist()
            xp_sel = st.selectbox("Chọn dự án xuất:", opts)
            if st.button("TẢI EXCEL", key="xp_btn"):
                if "TẤT CẢ" in xp_sel:
                    # Logic tổng hợp
                    agg = df_pj.groupby(['MaVT', 'TenVT', 'DVT'], as_index=False).agg({'SoLuong': 'sum', 'ThanhTien': 'sum'})
                    agg['DonGia'] = agg.apply(lambda x: x['ThanhTien']/x['SoLuong'] if x['SoLuong']>0 else 0, axis=1)
                    data = export_project_materials_excel(agg, "ALL", "TỔNG HỢP TOÀN BỘ")
                    n = "TongHop.xlsx"
                else:
                    # Logic chi tiết
                    p_code = ""
                    f = df_pj[df_pj['TenDuAn'] == xp_sel]
                    if not f.empty: p_code = f.iloc[0]['MaDuAn']
                    else: p_code = generate_project_code(xp_sel)
                    data = export_project_materials_excel(f, p_code, xp_sel)
                    n = f"VatTu_{p_code}.xlsx"
                
                st.download_button("⬇️ DOWNLOAD", data, n, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==============================================================================
# 7. CHẠY APP (MAIN ENTRY)
# ==============================================================================
if 'role' not in st.session_state: st.session_state.role = None

if st.session_state.role is None:
    render_login_screen()
else:
    render_sidebar()
    _, col_main = st.columns([0.1, 10]) # Căn giữa nội dung chút
    with col_main:
        is_laptop = st.toggle("💻 Chế độ Laptop/PC", value=True)
        main_tabs = st.tabs(["💰 QUẢN LÝ THU CHI", "🏗️ VẬT TƯ & DỰ ÁN"])
        with main_tabs[0]: render_thuchi_module(is_laptop)
        with main_tabs[1]: render_vattu_module()

    st.markdown("<div class='app-footer'>Phiên bản: 8.0 Ultimate ERP - Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)
