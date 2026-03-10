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
# 1. CẤU HÌNH & CSS (NO SIDEBAR - FULL WIDTH)
# ==============================================================================
st.set_page_config(page_title="HỆ THỐNG ERP PRO", page_icon="🏢", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 5rem !important; }
    [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stDecoration"], [data-testid="stToolbar"], header[data-testid="stHeader"], footer { display: none !important; }
    
    .system-title { font-size: 1.5rem; font-weight: 900; text-transform: uppercase; color: var(--primary-color); text-align: center; margin-bottom: 20px; border-bottom: 1px solid rgba(128,128,128,0.2); padding-bottom: 10px; }
    
    .balance-box { background-color: var(--secondary-background-color); padding: 20px; border-radius: 12px; border: 1px solid rgba(128, 128, 128, 0.2); margin-bottom: 25px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .bal-title { font-size: 0.9rem; opacity: 0.8; text-transform: uppercase; font-weight: 700; color: var(--text-color); }
    .bal-val { font-size: 2.5rem; font-weight: 900; color: #22c55e; }
    .bal-neg { color: #ef4444 !important; }

    .stTextInput input, .stNumberInput input, .stDateInput input, .stSelectbox div[data-baseweb="select"] { font-weight: 600; border-radius: 6px; }
    [data-testid="stFormSubmitButton"] > button { width: 100%; background-color: #ff4b4b; color: white; font-weight: bold; border: none; padding: 0.6rem; border-radius: 6px; }
    [data-testid="stFormSubmitButton"] > button:hover { background-color: #d93434; transform: scale(1.01); }

    div[data-testid="column"] button { padding: 0px 8px !important; min-height: 32px !important; height: auto !important; font-size: 0.8rem; border: 1px solid rgba(128, 128, 128, 0.3); background-color: var(--background-color); color: var(--text-color); }
    div[data-testid="column"] button:hover { border-color: #ff4b4b; color: #ff4b4b; }

    .excel-header { background-color: var(--secondary-background-color); padding: 10px 5px; font-weight: 800; font-size: 0.85rem; text-transform: uppercase; border-top: 1px solid rgba(128, 128, 128, 0.3); border-bottom: 2px solid rgba(128, 128, 128, 0.3); display: flex; align-items: center; }
    .excel-row { border-bottom: 1px solid rgba(128, 128, 128, 0.1); padding: 10px 5px; font-size: 0.95rem; display: flex; align-items: center; }
    .excel-row:hover { background-color: rgba(128, 128, 128, 0.05); }
    
    .money-inc { color: #22c55e !important; font-weight: 800; font-family: 'Consolas', monospace; }
    .money-exp { color: #ef4444 !important; font-weight: 800; font-family: 'Consolas', monospace; }
    .total-row { background-color: rgba(255, 165, 0, 0.15); color: #d97706; border: 1px solid #d97706; font-weight: 800; padding: 12px; border-radius: 6px; text-align: right; margin-top: 15px; font-size: 1.1rem; }
    .app-footer { text-align: center; margin-top: 50px; padding-top: 10px; border-top: 1px dashed rgba(128,128,128,0.3); opacity: 0.6; font-size: 0.75rem; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. KẾT NỐI API ====================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource(show_spinner=False)
def get_creds(): return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

@st.cache_resource(show_spinner=False)
def get_gs_client(): return gspread.authorize(get_creds())

def get_vn_time(): return datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))
def remove_accents(input_str):
    if not isinstance(input_str, str): return str(input_str)
    s = unicodedata.normalize('NFD', input_str)
    return "".join([c for c in s if unicodedata.category(c) != 'Mn']).replace("đ", "d").replace("Đ", "D")
def auto_capitalize(text): return text.strip()[0].upper() + text.strip()[1:] if text and text.strip() else ""
def format_vnd(amount):
    if pd.isna(amount): return "0"
    try:
        val = float(amount)
        if val.is_integer(): return "{:,.0f}".format(val).replace(",", ".")
        return "{:,.2f}".format(val).replace(",", "X").replace(".", ",").replace("X", ".").rstrip('0').rstrip(',')
    except: return "0"
def generate_project_code(name): return f"{''.join([w[0] for w in remove_accents(name).upper().split() if w.isalnum()])}{get_vn_time().strftime('%d%m%y')}" if name else ""
def generate_material_code(name): return f"VT{''.join([w[0] for w in remove_accents(name).upper().split() if w.isalnum()])[:3]}{''.join(random.choices(string.digits, k=3))}"
def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds(); service = build('drive', 'v3', credentials=creds); folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

# ==================== 3. DATA LAYER ====================
def clear_data_cache(): st.cache_data.clear()

@st.cache_data(ttl=60, show_spinner=False)
def load_config():
    client = get_gs_client(); wb = client.open("QuanLyThuChi")
    try: sheet = wb.worksheet("config")
    except:
        sheet = wb.add_worksheet("config", 100, 2)
        sheet.append_rows([["Key", "Value"], ["admin_pwd", "admin123"], ["viewer_pwd", "xem123"]])
    config = {row['Key']: str(row['Value']) for row in sheet.get_all_records()}
    if 'admin_pwd' not in config: config['admin_pwd'] = "admin123"
    if 'viewer_pwd' not in config: config['viewer_pwd'] = "xem123"
    if 'debt_1_name' not in config: config['debt_1_name'] = "SAMSUNG S1 HN"
    if 'debt_1_val' not in config: config['debt_1_val'] = "-4000000"
    if 'debt_2_name' not in config: config['debt_2_name'] = "TẾT 2025"
    if 'debt_2_val' not in config: config['debt_2_val'] = "-5000000"
    return config

def update_config_value(key, value):
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("config")
        cell = sheet.find(key)
        if cell: sheet.update_cell(cell.row, 2, str(value))
        else: sheet.append_row([key, str(value)])
        clear_data_cache(); return True
    except: return False

@st.cache_data(ttl=300, show_spinner=False)
def load_data_with_index():
    try:
        client = get_gs_client(); df = pd.DataFrame(client.open("QuanLyThuChi").worksheet("data").get_all_records())
        if df.empty: return pd.DataFrame()
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], dayfirst=True, errors='coerce')
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype('float')
        return df.dropna(subset=['Ngay'])
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def load_materials_master():
    try:
        client = get_gs_client(); df = pd.DataFrame(client.open("QuanLyThuChi").worksheet("dm_vattu").get_all_records())
        if 'TenVT' not in df.columns: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        df['Row_Index'] = range(2, len(df) + 2)
        return df
    except: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])

@st.cache_data(ttl=300, show_spinner=False)
def load_project_data():
    try:
        client = get_gs_client(); df = pd.DataFrame(client.open("QuanLyThuChi").worksheet("data_duan").get_all_records())
        if df.empty: return pd.DataFrame(columns=["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu", "LinkNCC"])
        for col in ['SoLuong', 'DonGia', 'ThanhTien']: df[col] = pd.to_numeric(df.get(col, 0), errors='coerce').fillna(0)
        if 'LinkNCC' not in df.columns: df['LinkNCC'] = ""
        df['Row_Index'] = range(2, len(df) + 2)
        return df
    except: return pd.DataFrame()

# --- WRITE FUNCTIONS ---
def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client(); client.open("QuanLyThuChi").worksheet("data").append_row([date.strftime('%Y-%m-%d'), category, amount, auto_capitalize(description), image_link])
    clear_data_cache()

def update_transaction(row_idx, date, category, amount, description, image_link):
    sheet = get_gs_client().open("QuanLyThuChi").worksheet("data")
    sheet.update_cell(int(row_idx), 1, date.strftime('%Y-%m-%d'))
    sheet.update_cell(int(row_idx), 2, category)
    sheet.update_cell(int(row_idx), 3, amount)
    sheet.update_cell(int(row_idx), 4, auto_capitalize(description))
    if image_link: sheet.update_cell(int(row_idx), 5, image_link)
    clear_data_cache()

def delete_transaction(sheet_name, row_idx):
    get_gs_client().open("QuanLyThuChi").worksheet(sheet_name).delete_rows(int(row_idx)); clear_data_cache()

def save_project_material(proj_code, proj_name, mat_name, unit1, unit2, ratio, price_unit1, selected_unit, qty, note, link_ncc, is_new_item=False):
    wb = get_gs_client().open("QuanLyThuChi")
    mat_code = ""
    proj_name = auto_capitalize(proj_name); mat_name = auto_capitalize(mat_name)
    
    if is_new_item:
        try: ws_master = wb.worksheet("dm_vattu")
        except: ws_master = wb.add_worksheet("dm_vattu", 1000, 6); ws_master.append_row(["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        mat_code = generate_material_code(mat_name)
        ws_master.append_row([mat_code, mat_name, auto_capitalize(unit1), auto_capitalize(unit2), ratio, price_unit1])
    else:
        df_master = load_materials_master()
        if not df_master.empty:
            found = df_master[df_master['TenVT'] == mat_name]
            if not found.empty: mat_code = found.iloc[0]['MaVT']
    
    final_price = float(price_unit1) if selected_unit == unit1 else (float(price_unit1) / float(ratio) if float(ratio) > 0 else 0)
    thanh_tien = float(qty) * final_price
    
    try: ws_data = wb.worksheet("data_duan")
    except: ws_data = wb.add_worksheet("data_duan", 1000, 11); ws_data.append_row(["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu", "LinkNCC"])
    
    headers = ws_data.row_values(1)
    row_data = [proj_code, proj_name, get_vn_time().strftime('%Y-%m-%d %H:%M:%S'), mat_code, mat_name, selected_unit, qty, final_price, thanh_tien, auto_capitalize(note)]
    if 'LinkNCC' in headers: row_data.append(link_ncc)
    elif len(headers) < 11: ws_data.update_cell(1, 11, "LinkNCC"); row_data.append(link_ncc)
    
    ws_data.append_row(row_data)
    clear_data_cache()

def update_material_row(row_idx, qty, price, note):
    sheet = get_gs_client().open("QuanLyThuChi").worksheet("data_duan")
    sheet.update_cell(int(row_idx), 7, qty)
    sheet.update_cell(int(row_idx), 8, price)
    sheet.update_cell(int(row_idx), 9, float(qty) * float(price))
    sheet.update_cell(int(row_idx), 10, auto_capitalize(note))
    clear_data_cache()

def update_master_material(row_idx, name, u1, u2, ratio, price):
    sheet = get_gs_client().open("QuanLyThuChi").worksheet("dm_vattu")
    sheet.update_cell(int(row_idx), 2, auto_capitalize(name))
    sheet.update_cell(int(row_idx), 3, auto_capitalize(u1))
    sheet.update_cell(int(row_idx), 4, auto_capitalize(u2))
    sheet.update_cell(int(row_idx), 5, ratio)
    sheet.update_cell(int(row_idx), 6, price)
    clear_data_cache()

# ==================== 4. EXCEL & BACKUP ====================
def generate_full_backup():
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        load_data_with_index().to_excel(writer, sheet_name='ThuChi', index=False)
        load_project_data().to_excel(writer, sheet_name='DuAn_ChiTiet', index=False)
        load_materials_master().to_excel(writer, sheet_name='KhoVatTu', index=False)
    return output.getvalue()

def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    cfg = load_config()
    d1_n = cfg.get('debt_1_name', "SAMSUNG S1 HN"); d1_v = float(cfg.get('debt_1_val', -4000000))
    d2_n = cfg.get('debt_2_name', "TẾT 2025"); d2_v = float(cfg.get('debt_2_val', -5000000))

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        fn = 'Times New Roman'
        f_title = wb.add_format({'bold': True, 'font_size': 20, 'align': 'center', 'valign': 'vcenter', 'font_name': fn})
        f_sub = wb.add_format({'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': fn})
        f_sys = wb.add_format({'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'font_name': fn, 'font_color': '#1e3a8a'})
        f_head = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D3D3D3', 'font_size': 11, 'font_name': fn})
        f_cell = wb.add_format({'border': 1, 'valign': 'vcenter', 'font_size': 11, 'font_name': fn})
        f_num = wb.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0', 'font_size': 11, 'font_name': fn})
        f_tot_l = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'align': 'center', 'font_size': 12, 'font_name': fn})
        f_tot_v = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#FFCC00', 'num_format': '#,##0', 'font_size': 12, 'font_name': fn})
        f_debt_t = wb.add_format({'font_size': 11, 'italic': True, 'align': 'right', 'font_name': fn})
        f_debt_n = wb.add_format({'font_size': 11, 'italic': True, 'align': 'right', 'font_name': fn, 'num_format': '#,##0', 'font_color': 'red', 'bold': True})

        ws = wb.add_worksheet("SoQuy")
        ws.merge_range('A1:F1', "QUYẾT TOÁN", f_title)
        ws.merge_range('A2:F2', f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}", f_sub)
        ws.merge_range('A3:F3', f"Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", f_sub)
        ws.merge_range('A4:F4', "HỆ THỐNG QUYẾT TOÁN", f_sys)
        ws.merge_range('A5:F5', "Người tạo: TUẤN VDS.HCM", f_sub)
        
        for c, h in enumerate(["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]): ws.write(5, c, h, f_head)
        ws.set_column('B:B', 40); ws.set_column('C:D', 15); ws.set_column('E:F', 18)

        df_c = df_report.reset_index(drop=True)
        for i, r in df_c.iterrows():
            ws.write(6+i, 0, r['STT'], f_cell); ws.write(6+i, 1, r['Khoan'], f_cell)
            ws.write(6+i, 2, r['NgayChi'], f_cell); ws.write(6+i, 3, r['NgayNhan'], f_cell)
            ws.write(6+i, 4, r['SoTienShow'] if r['Loai']!='Open' else "", f_num); ws.write(6+i, 5, r['ConLai'], f_num)
            
        lr = 6 + len(df_c)
        ws.merge_range(lr, 0, lr, 4, "TỔNG CỘNG", f_tot_l)
        lb = df_c.iloc[-1]['ConLai'] if not df_c.empty else 0
        ws.write(lr, 5, lb, f_tot_v)
        
        fr = lr + 3 
        ws.merge_range(fr, 3, fr, 4, d1_n, f_debt_t); ws.write(fr, 5, d1_v, f_debt_n); fr+=1
        ws.merge_range(fr, 3, fr, 4, d2_n, f_debt_t); ws.write(fr, 5, d2_v, f_debt_n); fr+=1
        ws.merge_range(fr, 0, fr, 4, "TỔNG TẠM TÍNH", f_tot_l); ws.write(fr, 5, lb + d1_v + d2_v, f_tot_v)
    return output.getvalue()

def export_project_materials_excel(df_proj, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        fn = 'Times New Roman'
        f_title = wb.add_format({'bold': True, 'font_size': 20, 'align': 'center', 'valign': 'vcenter', 'font_name': fn})
        f_sub = wb.add_format({'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': fn})
        f_sys = wb.add_format({'bold': True, 'font_size': 12, 'align': 'center', 'valign': 'vcenter', 'font_name': fn, 'font_color': '#1e3a8a'})
        f_head = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#D3D3D3', 'font_size': 11, 'font_name': fn})
        f_cell = wb.add_format({'border': 1, 'valign': 'vcenter', 'font_size': 11, 'font_name': fn})
        f_num = wb.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0', 'font_size': 11, 'font_name': fn})
        f_tot_l = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'align': 'center', 'font_size': 12, 'font_name': fn})
        f_tot_v = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#FFCC00', 'num_format': '#,##0', 'valign': 'vcenter', 'font_name': fn, 'font_size': 12})
        
        ws = wb.add_worksheet("BangKe")
        ws.merge_range('A1:H1', "BẢNG KÊ VẬT TƯ", f_title)
        ws.merge_range('A2:H2', f"Dự án: {proj_name}", f_sub)
        ws.merge_range('A3:H3', f"Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", f_sub)
        ws.merge_range('A4:H4', "HỆ THỐNG QUẢN LÝ VẬT TƯ DỰ ÁN", f_sys)
        ws.merge_range('A5:H5', "Người tạo: TUẤN VDS.HCM", f_sub)
        
        cols = ["STT", "Mã VT", "Tên VT", "ĐVT", "SL", "Đơn giá", "Thành tiền", "Link/NCC"]
        for i, h in enumerate(cols): ws.write(5, i, h, f_head)
        ws.set_column('B:B', 15); ws.set_column('C:C', 40); ws.set_column('E:G', 15); ws.set_column('H:H', 25)
        
        df_c = df_proj.reset_index(drop=True)
        tot = 0
        for i, r in df_c.iterrows():
            ws.write(6+i, 0, i+1, f_cell); ws.write(6+i, 1, r['MaVT'], f_cell)
            ws.write(6+i, 2, r['TenVT'], f_cell); ws.write(6+i, 3, r['DVT'], f_cell)
            ws.write(6+i, 4, r['SoLuong'], f_cell); ws.write(6+i, 5, r['DonGia'], f_num)
            ws.write(6+i, 6, r['ThanhTien'], f_num); ws.write(6+i, 7, r.get('LinkNCC', ''), f_cell)
            tot += r['ThanhTien']
            
        lr = 6 + len(df_c)
        ws.merge_range(lr, 0, lr, 5, "TỔNG CỘNG", f_tot_l); ws.write(lr, 6, tot, f_tot_v)
    return output.getvalue()

def process_report_data(df, start_date=None, end_date=None):
    if df.empty: return pd.DataFrame()
    df_all = df.sort_values(by=['Ngay', 'Row_Index']).copy()
    df_all['SignedAmount'] = df_all.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_all['ConLai'] = df_all['SignedAmount'].cumsum()
    if start_date and end_date:
        mask_before = df_all['Ngay'].dt.date < start_date
        ob = df_all[mask_before].iloc[-1]['ConLai'] if not df_all[mask_before].empty else 0
        df_proc = df_all[(df_all['Ngay'].dt.date >= start_date) & (df_all['Ngay'].dt.date <= end_date)].copy()
        if not df_proc.empty: df_proc['ConLai'] = ob + df_proc['SignedAmount'].cumsum()
        df_proc = pd.concat([pd.DataFrame([{'Row_Index': 0, 'Ngay': pd.Timestamp(start_date), 'Loai': 'Open', 'SoTien': 0, 'MoTa': "Số dư đầu kỳ", 'HinhAnh': '', 'ConLai': ob, 'SignedAmount': 0}]), df_proc], ignore_index=True)
    else: df_proc = df_all.copy()
    if df_proc.empty: return pd.DataFrame()
    df_proc['STT'] = range(1, len(df_proc) + 1)
    df_proc['Khoan'] = df_proc.apply(lambda x: x['MoTa'] if x['Loai'] == 'Open' else auto_capitalize(x['MoTa']), axis=1)
    df_proc['NgayChi'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai'] == 'Chi' else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai'] == 'Thu' else "", axis=1)
    df_proc['SoTienShow'] = df_proc.apply(lambda x: x['SoTien'] if x['Loai'] != 'Open' else 0, axis=1)
    return df_proc[['STT', 'Khoan', 'NgayChi', 'NgayNhan', 'SoTienShow', 'ConLai', 'Loai']]

# ==================== 5. UI COMPONENTS ====================
def render_pagination(total_items, items_per_page, key_prefix):
    total_pages = max(1, (total_items - 1) // items_per_page + 1)
    if total_pages == 1: return 1
    c1, c2, c3 = st.columns([8, 2, 2])
    with c2: st.write("Trang:")
    with c3: page = st.number_input("Trang", min_value=1, max_value=total_pages, value=1, label_visibility="collapsed", key=f"page_{key_prefix}")
    return page

# ==================== AUTHENTICATION & LOGIN UI ====================
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
    with st.form("cp"):
        n = st.text_input("Mật khẩu mới:", type="password")
        if st.form_submit_button("Đổi mật khẩu"):
            update_password(st.session_state.role, n); st.success("Xong!")

# --- THU CHI UI ---
def render_thuchi_module(is_laptop):
    st.markdown("<div class='system-title'>HỆ THỐNG QUYẾT TOÁN</div>", unsafe_allow_html=True)
    df = load_data_with_index()
    t_thu = df[df['Loai']=='Thu']['SoTien'].sum() if not df.empty else 0
    t_chi = df[df['Loai']=='Chi']['SoTien'].sum() if not df.empty else 0
    bal = t_thu - t_chi
    st.markdown(f"<div class='balance-box'><div class='bal-title'>SỐ DƯ HIỆN TẠI</div><div class='bal-val {'bal-neg' if bal<0 else ''}'>{format_vnd(bal)}</div><div style='display:flex; justify-content:space-between; margin-top:15px; border-top:1px dashed rgba(128,128,128,0.3); padding-top:10px;'><div style='color:#22c55e; font-weight:700'>⬇️ {format_vnd(t_thu)}</div><div style='color:#ef4444; font-weight:700'>⬆️ {format_vnd(t_chi)}</div></div></div>", unsafe_allow_html=True)

    if 'edit_tc_id' not in st.session_state: st.session_state.edit_tc_id = None

    def render_input_tc():
        if st.session_state.role != 'admin': return
        d_d = get_vn_time(); d_t = "Chi"; d_a = None; d_desc = ""
        is_edit = st.session_state.edit_tc_id is not None
        if is_edit and not df.empty:
            r = df[df['Row_Index'] == st.session_state.edit_tc_id]
            if not r.empty: d_d, d_t, d_a, d_desc = r.iloc[0]['Ngay'], r.iloc[0]['Loai'], float(r.iloc[0]['SoTien']), r.iloc[0]['MoTa']; st.info(f"✏️ Sửa: {d_desc}")

        with st.form("tc_form", clear_on_submit=not is_edit):
            c1, c2 = st.columns(2)
            d_date = c1.date_input("Ngày", d_d)
            d_type = c2.selectbox("Loại", ["Chi", "Thu"], index=(0 if d_t=="Chi" else 1))
            
            suggested_cats = [""] + list(df['MoTa'].unique()) if not df.empty else [""]
            col_desc1, col_desc2 = st.columns([1, 2])
            d_desc_sel = col_desc1.selectbox("Danh mục cũ", suggested_cats)
            d_desc_txt = col_desc2.text_input("Hoặc nhập mới", value=d_desc)
            final_desc = d_desc_txt if d_desc_txt else d_desc_sel
            
            d_amt = st.number_input("Số tiền", min_value=0.0, step=10000.0, value=d_a, placeholder="0")
            img = st.file_uploader("Ảnh (Không bắt buộc)", type=['jpg','png']) if not is_edit else None

            if st.form_submit_button("CẬP NHẬT" if is_edit else "LƯU GIAO DỊCH"):
                if (d_amt is not None and d_amt > 0) and final_desc:
                    if is_edit:
                        update_transaction(st.session_state.edit_tc_id, d_date, d_type, d_amt, final_desc, "")
                        st.session_state.edit_tc_id = None; st.success("Đã sửa!"); time.sleep(0.5); st.rerun()
                    else:
                        add_transaction(d_date, d_type, d_amt, final_desc, upload_image_to_drive(img, f"TC_{d_date}") if img else "")
                        st.success("Đã thêm!"); time.sleep(0.5); st.rerun()
                else: st.warning("Nhập thiếu thông tin!")
        if is_edit and st.button("Hủy Sửa", use_container_width=True): st.session_state.edit_tc_id = None; st.rerun()

        # DEBT CONFIG FOR ADMIN
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🛠️ CẤU HÌNH KHOẢN NỢ TẠM TÍNH", expanded=False):
            cfg = load_config()
            with st.form("debt_form"):
                st.caption("Các khoản này sẽ xuất hiện ở dưới cùng của file Excel.")
                d1_n = st.text_input("Tên Khoản 1:", value=cfg.get('debt_1_name', ''))
                d1_v = st.text_input("Giá trị 1 (Ghi số âm, vd: -4000000):", value=cfg.get('debt_1_val', ''))
                d2_n = st.text_input("Tên Khoản 2:", value=cfg.get('debt_2_name', ''))
                d2_v = st.text_input("Giá trị 2:", value=cfg.get('debt_2_val', ''))
                
                if st.form_submit_button("LƯU CẤU HÌNH"):
                    update_config_value('debt_1_name', d1_n); update_config_value('debt_1_val', d1_v)
                    update_config_value('debt_2_name', d2_n); update_config_value('debt_2_val', d2_v)
                    st.success("Đã lưu!"); time.sleep(0.5); st.rerun()

    def render_list_tc():
        if df.empty: st.info("Chưa có dữ liệu"); return
        st.markdown("""<div class="excel-header" style="display:flex"><div style="width:15%">NGÀY</div><div style="width:45%">NỘI DUNG</div><div style="width:25%;text-align:right">SỐ TIỀN</div><div style="width:15%;text-align:center">...</div></div>""", unsafe_allow_html=True)
        
        df_sorted = df.sort_values(by='Ngay', ascending=False)
        items_per_page = 20
        page = render_pagination(len(df_sorted), items_per_page, "tc")
        start_idx = (page - 1) * items_per_page
        df_paged = df_sorted.iloc[start_idx : start_idx + items_per_page]

        with st.container(height=600 if is_laptop else None):
            for i, r in df_paged.iterrows():
                c1, c2, c3, c4 = st.columns([1.5, 4.5, 2.5, 1.5])
                c1.markdown(f"<span class='cell-sub'>{r['Ngay'].strftime('%d/%m')}</span>", unsafe_allow_html=True)
                c2.markdown(f"<div class='cell-main'>{r['MoTa']}</div>", unsafe_allow_html=True)
                c3.markdown(f"<div class='{'money-inc' if r['Loai']=='Thu' else 'money-exp'}' style='text-align:right'>{format_vnd(r['SoTien'])}</div>", unsafe_allow_html=True)
                with c4:
                    if st.session_state.role == 'admin':
                        b1, b2 = st.columns(2)
                        if b1.button("✏️", key=f"e_tc_{r['Row_Index']}"): st.session_state.edit_tc_id = r['Row_Index']; st.rerun()
                        if b2.button("🗑️", key=f"d_tc_{r['Row_Index']}"): delete_transaction("data", r['Row_Index']); st.rerun()
                st.markdown("<div style='border-bottom:1px solid rgba(128,128,128,0.1)'></div>", unsafe_allow_html=True)

    if is_laptop and st.session_state.role == 'admin':
        c1, c2 = st.columns([3.5, 6.5])
        with c1: render_input_tc()
        with c2:
            t1, t2, t3 = st.tabs(["LỊCH SỬ", "BÁO CÁO", "XUẤT"])
            with t1: render_list_tc()
            with t2:
                d1, d2 = st.date_input("Từ", get_vn_time().replace(day=1), key="d1"), st.date_input("Đến", get_vn_time(), key="d2")
                st.dataframe(process_report_data(df, d1, d2), use_container_width=True)
            with t3:
                d1_e, d2_e = st.date_input("Từ", get_vn_time().replace(day=1), key="d1e"), st.date_input("Đến", get_vn_time(), key="d2e")
                if st.button("TẢI EXCEL"): st.download_button("DOWNLOAD FILE", convert_df_to_excel_custom(process_report_data(df, d1_e, d2_e), d1_e, d2_e), f"Quyết toán {get_vn_time().strftime('%Hh%M')}.xlsx")
    else:
        mt = st.tabs(["NHẬP", "LỊCH SỬ", "SỔ QUỸ", "XUẤT"]) if st.session_state.role == 'admin' else st.tabs(["LỊCH SỬ", "SỔ QUỸ", "XUẤT"])
        idx = 0
        if st.session_state.role == 'admin':
            with mt[0]: render_input_tc(); idx += 1
        with mt[idx]: render_list_tc()
        with mt[idx+1]: st.dataframe(process_report_data(df, st.date_input("Từ", get_vn_time().replace(day=1)), st.date_input("Đến", get_vn_time())), use_container_width=True)
        with mt[idx+2]:
            if st.button("TẢI EXCEL", key="m_ex"): st.download_button("DOWNLOAD", convert_df_to_excel_custom(process_report_data(df, get_vn_time().replace(day=1), get_vn_time()), get_vn_time().replace(day=1), get_vn_time()), f"Quyết toán.xlsx")

def render_vattu_module(is_laptop):
    st.markdown("<div class='system-title'>HỆ THỐNG QUẢN LÝ VẬT TƯ DỰ ÁN</div>", unsafe_allow_html=True)
    df_pj = load_project_data()
    p_opts = ["++ TẠO DỰ ÁN MỚI ++"] + list(reversed(df_pj['TenDuAn'].unique().tolist() if not df_pj.empty else []))
    if 'curr_proj_name' not in st.session_state: st.session_state.curr_proj_name = ""
    curr_idx = p_opts.index(st.session_state.curr_proj_name) if st.session_state.curr_proj_name in p_opts else 0

    def render_input_vt():
        if st.session_state.role != 'admin': return
        with st.container(border=True):
            sel_p = st.selectbox("📁 Dự án:", p_opts, index=curr_idx, on_change=lambda: st.session_state.update({'curr_proj_name': st.session_state.sel_pj_main}), key="sel_pj_main")
            fin_p = auto_capitalize(st.text_input("Tên dự án:") if sel_p == "++ TẠO DỰ ÁN MỚI ++" else sel_p)
            if fin_p and sel_p == "++ TẠO DỰ ÁN MỚI ++": st.session_state.curr_proj_name = fin_p; st.caption(f"Mã mới: {generate_project_code(fin_p)}")

        if st.session_state.curr_proj_name:
            df_m = load_materials_master()
            sel_vt = st.selectbox("📦 Vật tư:", ["", "++ TẠO VẬT TƯ MỚI ++"] + (df_m['TenVT'].unique().tolist() if not df_m.empty else []))
            is_new = (sel_vt == "++ TẠO VẬT TƯ MỚI ++")
            vt_final = st.text_input("Tên vật tư mới:") if is_new else sel_vt
            u1, u2, ratio, p1 = "", "", 1.0, 0.0
            
            if not is_new and sel_vt and not df_m.empty:
                r = df_m[df_m['TenVT'] == sel_vt].iloc[0]
                u1, u2 = str(r.get('DVT_Cap1','')), str(r.get('DVT_Cap2',''))
                try: ratio, p1 = float(r.get('QuyDoi',1)), float(r.get('DonGia_Cap1',0))
                except: pass

            if vt_final:
                if is_new:
                    c1, c2, c3, c4 = st.columns(4)
                    u1, u2 = c1.text_input("ĐVT Lớn"), c2.text_input("ĐVT Nhỏ")
                    ratio, p1 = c3.number_input("Quy đổi", 1.0), c4.number_input("Giá nhập", min_value=0.0, value=None)
                
                with st.form("vt_add"):
                    u_opts = []
                    if u1: u_opts.append(f"{u1} (Cấp 1)")
                    if u2: u_opts.append(f"{u2} (Cấp 2)")
                    u_ch = st.radio("Đơn vị:", u_opts if u_opts else ["Mặc định"], horizontal=True)
                    
                    c1, c2, c3 = st.columns([1, 1.5, 1.5])
                    qty = c1.number_input("Số lượng", min_value=0.0, value=None, placeholder="0")
                    note = c2.text_input("Ghi chú")
                    link_ncc = c3.text_input("Link/NCC")
                    
                    if st.form_submit_button("➕ THÊM VÀO DỰ ÁN"):
                        if qty is not None and qty > 0:
                            pc = df_pj[df_pj['TenDuAn'] == st.session_state.curr_proj_name].iloc[0]['MaDuAn'] if sel_p != "++ TẠO DỰ ÁN MỚI ++" and not df_pj.empty else generate_project_code(st.session_state.curr_proj_name)
                            save_project_material(pc, st.session_state.curr_proj_name, vt_final, u1, u2, ratio, p1 if p1 else 0, u_ch.split(" (")[0] if "(" in u_ch else u_ch, qty, note, link_ncc, is_new)
                            st.success("Đã thêm!"); time.sleep(0.5); st.rerun()

    def render_list_vt():
        vp = st.session_state.curr_proj_name if st.session_state.role == 'admin' else st.selectbox("Xem dự án:", p_opts, index=curr_idx)
        if vp and vp != "++ TẠO DỰ ÁN MỚI ++" and not df_pj.empty:
            dv = df_pj[df_pj['TenDuAn'] == vp]
            if st.session_state.role == 'admin': st.markdown(f"**Đang xem: {vp}**")
            st.markdown("""<div class="excel-header" style="display:flex"><div style="width:40%">TÊN VẬT TƯ</div><div style="width:15%">SL</div><div style="width:25%;text-align:right">TIỀN</div><div style="width:20%;text-align:center">...</div></div>""", unsafe_allow_html=True)
            
            if st.session_state.role == 'admin':
                if 'edit_vt_id' not in st.session_state: st.session_state.edit_vt_id = None
                if st.session_state.edit_vt_id:
                    re = df_pj[df_pj['Row_Index'] == st.session_state.edit_vt_id].iloc[0]
                    with st.form("ed_vt"):
                        st.info(f"Sửa: {re['TenVT']}")
                        c1, c2 = st.columns(2)
                        nq = c1.number_input("SL mới:", value=float(re['SoLuong']))
                        np = c2.number_input("Đơn giá mới:", value=float(re['DonGia']))
                        nn = st.text_input("Ghi chú:", value=re['GhiChu'])
                        if st.form_submit_button("CẬP NHẬT"): update_material_row(st.session_state.edit_vt_id, nq, np, nn); st.session_state.edit_vt_id = None; st.rerun()
                        if st.form_submit_button("HỦY"): st.session_state.edit_vt_id = None; st.rerun()

            page = render_pagination(len(dv), 20, "vt")
            dv_paged = dv.iloc[(page-1)*20 : page*20]

            with st.container(height=600 if is_laptop else None):
                for i, r in dv_paged.iterrows():
                    c1, c2, c3, c4 = st.columns([4, 1.5, 2.5, 2])
                    ncc_text = f" | NCC: {r.get('LinkNCC', '')}" if str(r.get('LinkNCC', '')) else ""
                    c1.markdown(f"<div class='cell-main'>{r['TenVT']}</div><div class='cell-sub'>{r['DVT']} | {r['GhiChu']}{ncc_text}</div>", unsafe_allow_html=True)
                    c2.write(f"{r['SoLuong']}")
                    c3.markdown(f"<div class='money-inc' style='text-align:right;color:#333 !important'>{format_vnd(r['ThanhTien'])}</div>", unsafe_allow_html=True)
                    with c4:
                        if st.session_state.role == 'admin':
                            b1, b2 = st.columns(2)
                            if b1.button("✏️", key=f"evt_{r['Row_Index']}"): st.session_state.edit_vt_id = r['Row_Index']; st.rerun()
                            if b2.button("🗑️", key=f"dvt_{r['Row_Index']}"): delete_transaction("data_duan", r['Row_Index']); st.rerun()
                    st.markdown("<div style='border-bottom:1px solid rgba(128,128,128,0.1)'></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='total-row'>TỔNG: {format_vnd(dv['ThanhTien'].sum())} VNĐ</div>", unsafe_allow_html=True)

    def render_master_data():
        df_m = load_materials_master()
        if 'edit_m_id' not in st.session_state: st.session_state.edit_m_id = None
        
        if st.session_state.edit_m_id and st.session_state.role == 'admin':
            re = df_m[df_m['Row_Index'] == st.session_state.edit_m_id].iloc[0]
            with st.form("ed_master"):
                st.info(f"Sửa Thông Tin Gốc: {re['TenVT']}")
                n_name = st.text_input("Tên VT", re['TenVT'])
                c1, c2, c3, c4 = st.columns(4)
                nu1 = c1.text_input("ĐVT 1", re['DVT_Cap1'])
                nu2 = c2.text_input("ĐVT 2", re['DVT_Cap2'])
                nrat = c3.number_input("Quy đổi", value=float(re.get('QuyDoi',1)))
                npri = c4.number_input("Giá chuẩn", value=float(re.get('DonGia_Cap1',0)))
                if st.form_submit_button("LƯU KHO"): update_master_material(st.session_state.edit_m_id, n_name, nu1, nu2, nrat, npri); st.session_state.edit_m_id = None; st.rerun()
                if st.form_submit_button("HỦY"): st.session_state.edit_m_id = None; st.rerun()

        st.dataframe(df_m, use_container_width=True)
        if st.session_state.role == 'admin' and not df_m.empty:
            st.caption("Nhập ID dòng để sửa (Row_Index):")
            idx_to_edit = st.number_input("Row Index", min_value=2, step=1, value=2)
            if st.button("Sửa thông tin gốc"): st.session_state.edit_m_id = idx_to_edit; st.rerun()

    def render_export_vt():
        if not df_pj.empty:
            xp = st.selectbox("Dự án xuất:", ["TẤT CẢ"] + df_pj['TenDuAn'].unique().tolist())
            if st.button("TẢI EXCEL KÊ VẬT TƯ"):
                data = df_pj.groupby(['MaVT','TenVT','DVT'], as_index=False).agg({'SoLuong':'sum','ThanhTien':'sum'}) if xp == "TẤT CẢ" else df_pj[df_pj['TenDuAn'] == xp]
                st.download_button("DOWNLOAD FILE", export_project_materials_excel(data, xp), f"VatTu_{xp}.xlsx")

    if is_laptop and st.session_state.role == 'admin':
        c1, c2 = st.columns([3.5, 6.5])
        with c1: render_input_vt()
        with c2:
            t1, t2, t3 = st.tabs(["CHI TIẾT DỰ ÁN", "KHO VẬT TƯ", "XUẤT"])
            with t1: render_list_vt()
            with t2: render_master_data()
            with t3: render_export_vt()
    else:
        tabs = ["CHI TIẾT DỰ ÁN", "KHO VẬT TƯ", "XUẤT"]
        if st.session_state.role == 'admin': tabs = ["NHẬP LIỆU"] + tabs
        mt = st.tabs(tabs)
        idx = 0
        if st.session_state.role == 'admin':
            with mt[0]: render_input_vt(); idx += 1
        with mt[idx]: render_list_vt()
        with mt[idx+1]: render_master_data()
        with mt[idx+2]: render_export_vt()

# ==================== MAIN APP RUN ====================
if check_password():
    c1, c2, c3, c4 = st.columns([5, 2, 2.5, 2.5])
    with c1: st.markdown(f"👋 **Xin chào: {'ADMIN' if st.session_state.role == 'admin' else 'VIEWER'}**")
    with c2: is_laptop = st.toggle("💻 Laptop", value=True)
    with c3:
        if st.session_state.role == 'admin':
            with st.expander("⚙️ CÀI ĐẶT & BACKUP", expanded=False):
                st.caption("Đổi mật khẩu")
                change_password_ui()
                st.divider()
                if st.button("🔄 LÀM MỚI APP", use_container_width=True): clear_data_cache(); st.rerun()
                if st.download_button("📥 TẢI BACKUP TOÀN HỆ THỐNG", data=generate_full_backup(), file_name=f"Backup_ERP_{get_vn_time().strftime('%d%m%Y')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True): pass
    with c4:
        if st.button("🚪 THOÁT", use_container_width=True): st.session_state.role = None; st.rerun()

    st.divider()
    main_tabs = st.tabs(["💰 QUẢN LÝ THU CHI", "🏗️ VẬT TƯ & DỰ ÁN"])
    with main_tabs[0]: render_thuchi_module(is_laptop)
    with main_tabs[1]: render_vattu_module(is_laptop)
    st.markdown("<div class='app-footer'>Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)
