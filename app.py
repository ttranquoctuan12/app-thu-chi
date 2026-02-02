import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import time
from io import BytesIO
import unicodedata
import pytz
import random
import string

# ==============================================================================
# 1. CẤU HÌNH & CSS (CLEAN CORE - NO CONFLICTS)
# ==============================================================================
st.set_page_config(
    page_title="HỆ THỐNG ERP",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    /* 1. TỐI ƯU KHÔNG GIAN */
    .block-container { padding-top: 1rem !important; padding-bottom: 3rem !important; }
    
    /* Chỉ ẩn những thứ thực sự không cần thiết, không can thiệp sâu vào layout core */
    footer { visibility: hidden; }
    #MainMenu { visibility: visible; } /* Giữ lại menu để debug nếu cần */
    
    /* 2. GIAO DIỆN THÍCH ỨNG (ADAPTIVE) */
    .balance-box {
        background-color: var(--secondary-background-color);
        padding: 15px; border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        margin-bottom: 20px; text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .bal-title { font-size: 0.9rem; opacity: 0.8; text-transform: uppercase; font-weight: 600; color: var(--text-color); }
    .bal-val { font-size: 2.2rem; font-weight: 900; color: var(--primary-color); }
    
    /* Input Form đậm đà hơn */
    .stTextInput input, .stNumberInput input, .stDateInput input, .stSelectbox div[data-baseweb="select"] {
        font-weight: 600; border-radius: 6px;
    }

    /* 3. BUTTONS */
    /* Nút Submit Form */
    [data-testid="stFormSubmitButton"] > button {
        width: 100%; background-color: #ff4b4b; color: white;
        font-weight: bold; border: none; padding: 0.6rem; border-radius: 6px;
    }
    [data-testid="stFormSubmitButton"] > button:hover { background-color: #d93434; transform: scale(1.02); }

    /* Nút Sửa/Xóa trong bảng (Icon nhỏ) */
    .small-btn {
        padding: 0px 5px !important; 
        font-size: 0.8rem !important;
        line-height: 1 !important;
        min-height: 0px !important;
        height: 30px !important;
    }

    /* 4. TABLE STYLE (EXCEL VIEW) */
    .excel-header {
        background-color: var(--secondary-background-color); padding: 10px 5px;
        font-weight: 800; font-size: 0.85rem; text-transform: uppercase;
        border-top: 1px solid rgba(128, 128, 128, 0.3); border-bottom: 2px solid rgba(128, 128, 128, 0.3);
        color: var(--text-color); display: flex; align-items: center;
    }
    .excel-row {
        border-bottom: 1px solid rgba(128, 128, 128, 0.1); padding: 8px 5px;
        font-size: 0.95rem; display: flex; align-items: center;
    }
    .excel-row:hover { background-color: rgba(128, 128, 128, 0.05); }
    
    .cell-main { font-weight: 700; color: var(--text-color); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    .cell-sub { font-size: 0.8rem; opacity: 0.7; font-style: italic; display: block; margin-top: 2px; }
    .money-inc { color: #22c55e !important; font-weight: 800; font-family: 'Consolas', monospace; }
    .money-exp { color: #ef4444 !important; font-weight: 800; font-family: 'Consolas', monospace; }
    
    .total-row {
        background-color: rgba(255, 165, 0, 0.15); color: #d97706; border: 1px solid #d97706;
        font-weight: 800; padding: 12px; border-radius: 6px; text-align: right; margin-top: 15px; font-size: 1.1rem;
    }

    /* Footer */
    .custom-footer { text-align: center; margin-top: 50px; padding-top: 10px; border-top: 1px dashed rgba(128,128,128,0.3); opacity: 0.6; font-size: 0.8rem; font-style: italic; }
    
    /* Login */
    .login-container { display: flex; justify-content: center; margin-top: 80px; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. KẾT NỐI API ====================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource(show_spinner=False)
def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

@st.cache_resource(show_spinner=False)
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
    """1.000.000 (Chẵn) hoặc 1.000,5 (Lẻ)"""
    if pd.isna(amount): return "0"
    try:
        val = float(amount)
        if val.is_integer(): return "{:,.0f}".format(val).replace(",", ".")
        else: return "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".").rstrip('0').rstrip(',')
    except: return "0"

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

# ==================== 3. DATA LAYER (STABLE) ====================
def clear_data_cache(): st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
def load_data_with_index():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame()
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype('float')
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def load_materials_master():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("dm_vattu")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if 'TenVT' not in df.columns: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        return df
    except: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])

@st.cache_data(ttl=300, show_spinner=False)
def load_project_data():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
        for col in ['SoLuong', 'DonGia', 'ThanhTien']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df['Row_Index'] = range(2, len(df) + 2)
        return df
    except: return pd.DataFrame()

# --- WRITE FUNCTIONS ---
def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([date.strftime('%Y-%m-%d'), category, amount, auto_capitalize(description), image_link])
    clear_data_cache()

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data"); r = int(row_idx)
    sheet.update_cell(r, 1, date.strftime('%Y-%m-%d'))
    sheet.update_cell(r, 2, category)
    sheet.update_cell(r, 3, amount)
    sheet.update_cell(r, 4, auto_capitalize(description))
    if image_link: sheet.update_cell(r, 5, image_link)
    clear_data_cache()

def delete_transaction(row_idx):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(int(row_idx)); clear_data_cache()

def save_project_material(proj_code, proj_name, mat_name, unit1, unit2, ratio, price_unit1, selected_unit, qty, note, is_new_item=False):
    client = get_gs_client(); wb = client.open("QuanLyThuChi")
    mat_code = ""
    proj_name = auto_capitalize(proj_name); mat_name = auto_capitalize(mat_name)
    unit1 = auto_capitalize(unit1); unit2 = auto_capitalize(unit2); note = auto_capitalize(note)

    if is_new_item:
        try: ws_master = wb.worksheet("dm_vattu")
        except: ws_master = wb.add_worksheet("dm_vattu", 1000, 6); ws_master.append_row(["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        mat_code = generate_material_code(mat_name)
        ws_master.append_row([mat_code, mat_name, unit1, unit2, ratio, price_unit1])
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
    ws_data.append_row([proj_code, proj_name, get_vn_time().strftime('%Y-%m-%d %H:%M:%S'), mat_code, mat_name, selected_unit, qty, final_price, thanh_tien, note])
    clear_data_cache()

def update_material_row(row_idx, qty, price, note):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
    r = int(row_idx)
    new_total = float(qty) * float(price)
    sheet.update_cell(r, 7, qty); sheet.update_cell(r, 9, new_total); sheet.update_cell(r, 10, auto_capitalize(note))
    clear_data_cache()

def delete_material_row(row_idx):
    client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
    sheet.delete_rows(int(row_idx)); clear_data_cache()

# ==================== 4. EXCEL EXPORT (CUSTOM FILENAME) ====================
def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        # Formats
        font_name = 'Times New Roman'
        fmt_title = workbook.add_format({'bold': True, 'font_size': 20, 'align': 'center', 'valign': 'vcenter', 'font_name': font_name})
        fmt_subtitle = workbook.add_format({'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': font_name})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D3D3D3', 'font_size': 11, 'font_name': font_name, 'text_wrap': True})
        fmt_cell = workbook.add_format({'border': 1, 'valign': 'vcenter', 'font_size': 11, 'font_name': font_name})
        fmt_num = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0', 'font_size': 11, 'font_name': font_name})
        fmt_tot_l = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'align': 'center', 'font_size': 12, 'font_name': font_name})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFCC00', 'num_format': '#,##0', 'font_size': 12, 'font_name': font_name})

        ws = workbook.add_worksheet("SoQuy")
        ws.merge_range('A1:F1', "QUYẾT TOÁN", fmt_title)
        ws.merge_range('A2:F2', f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}", fmt_subtitle)
        
        headers = ["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): ws.write(4, c, h, fmt_header)
        ws.set_column('B:B', 40); ws.set_column('C:D', 15); ws.set_column('E:F', 18)

        for i, row in df_report.iterrows():
            r = 5 + i
            ws.write(r, 0, row['STT'], fmt_cell)
            ws.write(r, 1, row['Khoan'], fmt_cell)
            ws.write(r, 2, row['NgayChi'], fmt_cell)
            ws.write(r, 3, row['NgayNhan'], fmt_cell)
            ws.write(r, 4, row['SoTienShow'] if row['Loai']!='Open' else "", fmt_num)
            ws.write(r, 5, row['ConLai'], fmt_num)
            
        l_row = 5 + len(df_report)
        ws.merge_range(l_row, 0, l_row, 4, "TỔNG CỘNG", fmt_tot_l)
        ws.write(l_row, 5, df_report.iloc[-1]['ConLai'] if not df_report.empty else 0, fmt_tot_v)
        
    return output.getvalue()

def export_project_materials_excel(df_proj, proj_code, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        font_name = 'Times New Roman'
        fmt_title = workbook.add_format({'bold': True, 'font_size': 20, 'align': 'center', 'valign': 'vcenter', 'font_name': font_name})
        fmt_subtitle = workbook.add_format({'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': font_name})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D3D3D3', 'font_size': 11, 'font_name': font_name})
        fmt_cell = workbook.add_format({'border': 1, 'valign': 'vcenter', 'font_size': 11, 'font_name': font_name})
        fmt_num = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0', 'font_size': 11, 'font_name': font_name})
        fmt_tot_l = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'align': 'center', 'font_size': 12, 'font_name': font_name})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFCC00', 'num_format': '#,##0', 'font_size': 12, 'font_name': font_name})
        
        ws = workbook.add_worksheet("BangKe")
        ws.merge_range('A1:G1', "BẢNG KÊ VẬT TƯ", fmt_title)
        ws.merge_range('A2:G2', f"Dự án: {proj_name}", fmt_subtitle)
        
        cols = ["STT", "Mã VT", "Tên VT", "ĐVT", "SL", "Đơn giá", "Thành tiền"]
        for i, h in enumerate(cols): ws.write(4, i, h, fmt_header)
        ws.set_column('B:B', 15); ws.set_column('C:C', 40); ws.set_column('E:G', 15)
        
        total = 0
        for i, row in df_proj.iterrows():
            r = 5 + i
            ws.write(r, 0, i+1, fmt_cell)
            ws.write(r, 1, row['MaVT'], fmt_cell)
            ws.write(r, 2, row['TenVT'], fmt_cell)
            ws.write(r, 3, row['DVT'], fmt_cell)
            ws.write(r, 4, row['SoLuong'], fmt_cell)
            ws.write(r, 5, row['DonGia'], fmt_num)
            ws.write(r, 6, row['ThanhTien'], fmt_num)
            total += row['ThanhTien']
            
        l_row = 5 + len(df_proj)
        ws.merge_range(l_row, 0, l_row, 5, "TỔNG CỘNG", fmt_tot_l)
        ws.write(l_row, 6, total, fmt_tot_v)
        
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
    st.markdown(f"""
    <div class='balance-box'>
        <div class='bal-title'>SỐ DƯ HIỆN TẠI</div>
        <div class='bal-val'>{format_vnd(bal)}</div>
        <div style="display:flex; justify-content:space-between; margin-top:15px; border-top:1px dashed rgba(128,128,128,0.3); padding-top:10px;">
            <div style="color:#22c55e; font-weight:700">⬇️ {format_vnd(thu)}</div>
            <div style="color:#ef4444; font-weight:700">⬆️ {format_vnd(chi)}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- AUTH ---
def check_password():
    if 'role' not in st.session_state: st.session_state.role = None
    if st.session_state.role is None:
        c1, c2, c3 = st.columns([1, 1.5, 1])
        with c2:
            st.markdown("<br><br><h2 style='text-align:center;'>🔐 HỆ THỐNG ERP</h2>", unsafe_allow_html=True)
            with st.form("login"):
                u = st.text_input("Tên đăng nhập:").strip()
                p = st.text_input("Mật khẩu:", type="password")
                if st.form_submit_button("ĐĂNG NHẬP"):
                    with st.spinner("Đang xác thực..."):
                        cfg = load_config()
                        if u == "admin" and p == cfg['admin_pwd']: st.session_state.role = "admin"; st.rerun()
                        elif u == "viewer" and p == cfg['viewer_pwd']: st.session_state.role = "viewer"; st.rerun()
                        else: st.error("Sai thông tin!")
        return False
    return True

def change_password_ui():
    with st.expander("🔐 Đổi mật khẩu"):
        with st.form("cp"):
            n = st.text_input("Mật khẩu mới:", type="password")
            if st.form_submit_button("Lưu"):
                update_password(st.session_state.role, n); st.success("Xong!")

# --- THU CHI UI ---
def render_thuchi_module(is_laptop):
    df = load_data_with_index()
    render_dashboard_box(
        df['SignedAmount' if 'SignedAmount' in df else 'SoTien'].sum() if not df.empty else 0,
        df[df['Loai']=='Thu']['SoTien'].sum() if not df.empty else 0,
        df[df['Loai']=='Chi']['SoTien'].sum() if not df.empty else 0
    )

    # INPUT FORM (FIX: Smart Input, No 0.00 delete needed)
    def render_input_tc():
        if st.session_state.role != 'admin': return
        if 'edit_tc_id' not in st.session_state: st.session_state.edit_tc_id = None
        
        d_d = get_vn_time(); d_t = "Chi"; d_a = None; d_desc = ""
        is_edit = st.session_state.edit_tc_id is not None
        
        if is_edit and not df.empty:
            row = df[df['Row_Index'] == st.session_state.edit_tc_id]
            if not row.empty:
                row = row.iloc[0]
                d_d = row['Ngay']; d_t = row['Loai']; d_a = float(row['SoTien']); d_desc = row['MoTa']
                st.info(f"✏️ Đang sửa: {d_desc}")

        with st.form("tc_form", clear_on_submit=not is_edit):
            c1, c2 = st.columns([1, 1])
            d_date = c1.date_input("Ngày", d_d)
            d_type = c2.selectbox("Loại", ["Chi", "Thu"], index=(0 if d_t=="Chi" else 1))
            
            # Use value=None to show placeholder
            d_amt = st.number_input("Số tiền", min_value=0.0, step=10000.0, value=d_a, placeholder="Nhập số tiền...")
            d_desc = st.text_input("Mô tả", value=d_desc)
            img = st.file_uploader("Ảnh", type=['jpg','png']) if not is_edit else None

            submitted = st.form_submit_button("LƯU / CẬP NHẬT")
            
            if submitted:
                amt_val = d_amt if d_amt is not None else 0.0
                if amt_val > 0 and d_desc:
                    if is_edit:
                        update_transaction(st.session_state.edit_tc_id, d_date, d_type, amt_val, d_desc, "")
                        st.session_state.edit_tc_id = None
                        st.success("Đã sửa!"); time.sleep(0.5); st.rerun()
                    else:
                        lnk = upload_image_to_drive(img, f"TC_{d_date}") if img else ""
                        add_transaction(d_date, d_type, amt_val, d_desc, lnk)
                        st.success("Đã thêm!"); time.sleep(0.5); st.rerun()
                else: st.warning("Nhập thiếu thông tin!")
        
        if is_edit:
            if st.button("Hủy Sửa", use_container_width=True): st.session_state.edit_tc_id = None; st.rerun()

    # LIST VIEW (FIX: Deterministic Key based on Row_Index)
    def render_list_tc():
        if df.empty: st.info("Chưa có dữ liệu"); return
        
        st.markdown("""<div class="excel-header" style="display:flex"><div style="width:15%">NGÀY</div><div style="width:45%">NỘI DUNG</div><div style="width:25%;text-align:right">SỐ TIỀN</div><div style="width:15%;text-align:center">...</div></div>""", unsafe_allow_html=True)
        
        # Scroll container logic
        height_val = 600 if is_laptop else None
        with st.container(height=height_val):
            for i, r in df.sort_values(by='Ngay', ascending=False).head(100).iterrows():
                c1, c2, c3, c4 = st.columns([1.5, 4.5, 2.5, 1.5])
                c1.markdown(f"<span class='cell-sub'>{r['Ngay'].strftime('%d/%m')}</span>", unsafe_allow_html=True)
                c2.markdown(f"<div class='cell-main'>{r['MoTa']}</div>", unsafe_allow_html=True)
                cls_m = "money-inc" if r['Loai']=='Thu' else "money-exp"
                c3.markdown(f"<div class='{cls_m}' style='text-align:right'>{format_vnd(r['SoTien'])}</div>", unsafe_allow_html=True)
                with c4:
                    if st.session_state.role == 'admin':
                        b1, b2 = st.columns(2)
                        # CRITICAL FIX: Deterministic Keys
                        if b1.button("✏️", key=f"btn_ed_tc_{r['Row_Index']}"): 
                            st.session_state.edit_tc_id = r['Row_Index']; st.rerun()
                        if b2.button("🗑️", key=f"btn_dl_tc_{r['Row_Index']}"): 
                            delete_transaction(r['Row_Index']); st.rerun()
                st.markdown("<div style='border-bottom:1px solid rgba(128,128,128,0.1)'></div>", unsafe_allow_html=True)

    # EXPORT TAB
    def render_export_tc():
        if not df.empty:
            d1 = st.date_input("Từ ngày", get_vn_time().replace(day=1), key="d1_tc")
            d2 = st.date_input("Đến ngày", get_vn_time(), key="d2_tc")
            
            # Pre-calculate data for download button
            now_str = get_vn_time().strftime('%d-%m-%Y %Hh%M')
            fname = f"Quyết toán từ {d1.strftime('%d-%m-%Y')} đến {d2.strftime('%d-%m-%Y')} {now_str}.xlsx"
            excel_data = convert_df_to_excel_custom(process_report_data(df, d1, d2), d1, d2)
            
            st.download_button("TẢI EXCEL", excel_data, fname, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else: st.warning("Không có dữ liệu")

    # LAYOUT
    if is_laptop:
        c1, c2 = st.columns([3.5, 6.5])
        with c1: render_input_tc()
        with c2:
            t1, t2, t3 = st.tabs(["LỊCH SỬ", "BÁO CÁO", "XUẤT"])
            with t1: render_list_tc()
            with t2:
                d1 = st.date_input("Từ", get_vn_time().replace(day=1), key="d1_rp")
                d2 = st.date_input("Đến", get_vn_time(), key="d2_rp")
                st.dataframe(process_report_data(df, d1, d2), use_container_width=True)
            with t3: render_export_tc()
    else:
        mt = st.tabs(["NHẬP", "LỊCH SỬ", "SỔ QUỸ", "XUẤT"])
        with mt[0]: render_input_tc()
        with mt[1]: render_list_tc()
        with mt[2]:
            d1 = st.date_input("Từ", get_vn_time().replace(day=1), key="m_d1_rp")
            d2 = st.date_input("Đến", get_vn_time(), key="m_d2_rp")
            st.dataframe(process_report_data(df, d1, d2), use_container_width=True)
        with mt[3]: render_export_tc()

def render_vattu_module(is_laptop):
    def render_input_vt():
        if st.session_state.role != 'admin': return
        with st.container(border=True):
            df_pj = load_project_data()
            ex = df_pj['TenDuAn'].unique().tolist() if not df_pj.empty else []
            p_opts = ["++ TẠO DỰ ÁN MỚI ++"] + list(reversed(ex))
            sel_p = st.selectbox("📁 Dự án:", p_opts, index=1 if len(ex)>0 else 0)
            
            fin_p = st.text_input("Tên dự án:") if sel_p == "++ TẠO DỰ ÁN MỚI ++" else sel_p
            fin_p = auto_capitalize(fin_p)
            
            if fin_p:
                st.session_state.curr_proj_name = fin_p
                pc = ""
                if sel_p != "++ TẠO DỰ ÁN MỚI ++" and not df_pj.empty:
                    f = df_pj[df_pj['TenDuAn'] == fin_p]
                    if not f.empty: pc = f.iloc[0]['MaDuAn']
                if not pc: pc = generate_project_code(fin_p)
                st.caption(f"Mã: {pc}")

        if 'curr_proj_name' in st.session_state and st.session_state.curr_proj_name:
            df_m = load_materials_master()
            mlst = df_m['TenVT'].unique().tolist() if not df_m.empty else []
            sel_vt = st.selectbox("📦 Vật tư:", ["", "++ TẠO VẬT TƯ MỚI ++"] + mlst)
            
            is_new = False; vt_final = ""; u1 = ""; u2 = ""; ratio = 1.0; p1 = 0.0
            if sel_vt == "++ TẠO VẬT TƯ MỚI ++":
                is_new = True; vt_final = st.text_input("Tên vật tư:")
                if vt_final and not df_m.empty:
                    m = difflib.get_close_matches(vt_final, df_m['TenVT'].tolist(), n=1, cutoff=0.6)
                    if m: st.warning(f"Gợi ý: {m[0]}")
            elif sel_vt:
                vt_final = sel_vt
                if not df_m.empty:
                    r = df_m[df_m['TenVT'] == sel_vt].iloc[0]
                    u1 = str(r.get('DVT_Cap1','')); u2 = str(r.get('DVT_Cap2',''))
                    try: ratio = float(r.get('QuyDoi',1)); p1 = float(r.get('DonGia_Cap1',0))
                    except: pass
            
            vt_final = auto_capitalize(vt_final)
            if vt_final:
                if is_new:
                    c1,c2,c3,c4 = st.columns(4)
                    u1 = c1.text_input("ĐVT Lớn"); u2 = c2.text_input("ĐVT Nhỏ")
                    ratio = c3.number_input("Quy đổi", 1.0); 
                    p1 = c4.number_input("Giá nhập", min_value=0.0, value=None, placeholder="0")
                
                with st.form("vt_add"):
                    # FIX: Radio Index Logic (1 item -> index 0)
                    unit_ops = []
                    if u1: unit_ops.append(f"{u1} (Cấp 1)")
                    if u2: unit_ops.append(f"{u2} (Cấp 2)")
                    if not unit_ops: unit_ops = ["Mặc định"]
                    
                    def_idx = 1 if len(unit_ops) > 1 else 0
                    u_ch = st.radio("Đơn vị:", unit_ops, horizontal=True, index=def_idx)
                    
                    c1, c2 = st.columns([1, 2])
                    qty = c1.number_input("Số lượng:", min_value=0.0, value=None, placeholder="0")
                    note = c2.text_input("Ghi chú")
                    
                    submitted = st.form_submit_button("➕ THÊM VÀO DỰ ÁN")
                    if submitted:
                        qty_val = qty if qty is not None else 0.0
                        price_val = p1 if p1 is not None else 0.0
                        
                        if qty_val > 0:
                            u1 = auto_capitalize(u1); u2 = auto_capitalize(u2)
                            sel_u = u_ch.split(" (")[0] if "(" in u_ch else u_ch
                            
                            p_sv = generate_project_code(st.session_state.curr_proj_name)
                            if sel_p != "++ TẠO DỰ ÁN MỚI ++" and not df_pj.empty:
                                f = df_pj[df_pj['TenDuAn'] == st.session_state.curr_proj_name]
                                if not f.empty: p_sv = f.iloc[0]['MaDuAn']
                            save_project_material(p_sv, st.session_state.curr_proj_name, vt_final, u1, u2, ratio, price_val, sel_u, qty_val, note, is_new)
                            st.success("OK"); time.sleep(0.5); st.rerun()

    def render_list_vt():
        df_pj = load_project_data()
        if not df_pj.empty:
            pjs = df_pj['TenDuAn'].unique().tolist()
            idx = 0
            if 'curr_proj_name' in st.session_state and st.session_state.curr_proj_name in pjs:
                idx = pjs.index(st.session_state.curr_proj_name)
            
            vp = st.selectbox("Xem dự án:", pjs, index=idx)
            if vp:
                dv = df_pj[df_pj['TenDuAn'] == vp]
                st.markdown("""<div class="excel-header" style="display:flex"><div style="width:40%">TÊN VẬT TƯ</div><div style="width:15%">SL</div><div style="width:25%;text-align:right">TIỀN</div><div style="width:20%;text-align:center">...</div></div>""", unsafe_allow_html=True)
                
                # Edit Form Logic
                if st.session_state.role == 'admin':
                    if 'edit_vt_id' not in st.session_state: st.session_state.edit_vt_id = None
                    if st.session_state.edit_vt_id:
                        re = df_pj[df_pj['Row_Index'] == st.session_state.edit_vt_id]
                        if not re.empty:
                            re = re.iloc[0]
                            with st.form("ed_vt"):
                                st.info(f"Sửa: {re['TenVT']}")
                                nq = st.number_input("SL mới:", value=float(re['SoLuong']))
                                nn = st.text_input("Ghi chú:", value=re['GhiChu'])
                                if st.form_submit_button("CẬP NHẬT"):
                                    update_material_row(st.session_state.edit_vt_id, nq, re['DonGia'], nn)
                                    st.session_state.edit_vt_id = None; st.rerun()
                                if st.form_submit_button("HỦY"): st.session_state.edit_vt_id = None; st.rerun()

                height_val = 600 if is_laptop else None
                with st.container(height=height_val):
                    for i, r in dv.iterrows():
                        c1, c2, c3, c4 = st.columns([4, 1.5, 2.5, 2])
                        c1.markdown(f"<div class='cell-main'>{r['TenVT']}</div><div class='cell-sub'>{r['DVT']} | {r['GhiChu']}</div>", unsafe_allow_html=True)
                        c2.write(f"{r['SoLuong']}")
                        c3.markdown(f"<div class='money-inc' style='text-align:right;color:#333 !important'>{format_vnd(r['ThanhTien'])}</div>", unsafe_allow_html=True)
                        with c4:
                            if st.session_state.role == 'admin':
                                b1, b2 = st.columns(2)
                                # CRITICAL FIX: Deterministic Keys
                                if b1.button("✏️", key=f"btn_edt_vt_{r['Row_Index']}"): 
                                    st.session_state.edit_vt_id = r['Row_Index']; st.rerun()
                                if b2.button("🗑️", key=f"btn_del_vt_{r['Row_Index']}"): 
                                    delete_material_row(r['Row_Index']); st.rerun()
                        st.markdown("<div style='border-bottom:1px solid rgba(128,128,128,0.1)'></div>", unsafe_allow_html=True)
                
                st.markdown(f"<div class='total-row'>TỔNG: {format_vnd(dv['ThanhTien'].sum())} VNĐ</div>", unsafe_allow_html=True)

    # --- TAB XUẤT VẬT TƯ CHUNG ---
    def render_export_vt():
        df_pj = load_project_data()
        if not df_pj.empty:
            xp = st.selectbox("Dự án xuất:", ["TẤT CẢ"] + df_pj['TenDuAn'].unique().tolist(), key="xp_vt_unique")
            
            now_full = get_vn_time().strftime('%d-%m-%Y %Hh%M')
            if xp == "TẤT CẢ": 
                fname = f"Vật tư đã xuất các dự án {now_full}.xlsx"
                agg = df_pj.groupby(['MaVT','TenVT','DVT'], as_index=False).agg({'SoLuong':'sum','ThanhTien':'sum'})
                agg['DonGia'] = agg.apply(lambda x: x['ThanhTien']/x['SoLuong'] if x['SoLuong']>0 else 0, axis=1)
                data_to_export = agg
                p_code = "ALL"; p_name = "TONG HOP"
            else: 
                fname = f"Vật tư {xp} {now_full}.xlsx"
                data_to_export = df_pj[df_pj['TenDuAn'] == xp]
                p_code = data_to_export.iloc[0]['MaDuAn'] if not data_to_export.empty else ""
                p_name = xp

            excel_data = export_project_materials_excel(data_to_export, p_code, p_name)
            st.download_button("TẢI EXCEL", excel_data, fname)

    if is_laptop:
        c1, c2 = st.columns([3.5, 6.5])
        with c1: render_input_vt()
        with c2:
            t1, t2, t3 = st.tabs(["CHI TIẾT DỰ ÁN", "KHO VẬT TƯ", "XUẤT"])
            with t1: render_list_vt()
            with t2: st.dataframe(load_materials_master(), use_container_width=True)
            with t3: render_export_vt()
    else:
        mt = st.tabs(["NHẬP", "CHI TIẾT", "KHO", "XUẤT"])
        with mt[0]: render_input_vt()
        with mt[1]: render_list_vt()
        with mt[2]: st.dataframe(load_materials_master(), use_container_width=True)
        with mt[3]: render_export_vt()

# ==================== 8. APP RUN ====================
if check_password():
    col_user, col_mode, col_logout = st.columns([6, 2, 1.5])
    with col_user:
        role = "ADMIN" if st.session_state.role == 'admin' else "VIEWER"
        st.markdown(f"**Xin chào: {role}**")
    with col_mode:
        is_laptop = st.toggle("💻 Laptop Mode", value=True)
    with col_logout:
        if st.button("🚪 Đăng xuất", key="top_out"):
            st.session_state.role = None; st.rerun()

    st.divider()

    with st.sidebar:
        st.header("⚙️ CÀI ĐẶT")
        change_password_ui()
        if st.session_state.role == 'admin':
            st.divider()
            if st.button("🔄 Làm mới dữ liệu", use_container_width=True): clear_data_cache(); st.rerun()

    main_tabs = st.tabs(["💰 QUẢN LÝ THU CHI", "🏗️ VẬT TƯ & DỰ ÁN"])
    with main_tabs[0]: render_thuchi_module(is_laptop)
    with main_tabs[1]: render_vattu_module(is_laptop)

    st.markdown("<div class='custom-footer'>Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)
