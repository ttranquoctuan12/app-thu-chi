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

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="🏗️", layout="wide")

# --- 2. CSS TỐI ƯU ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 3rem !important; }
    
    /* ẨN THÀNH PHẦN THỪA */
    [data-testid="stDecoration"], [data-testid="stToolbar"], [data-testid="stHeaderActionElements"], 
    .stAppDeployButton, [data-testid="stStatusWidget"], footer, #MainMenu { display: none !important; }

    /* HEADER & SIDEBAR */
    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 999; }
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important; visibility: visible !important;
        color: #000000 !important; background-color: rgba(255, 255, 255, 0.5); border-radius: 5px;
    }

    /* GIAO DIỆN CHUNG */
    [data-testid="stCameraInput"] { width: 100% !important; }
    .balance-box { 
        padding: 15px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e0e0e0; margin-bottom: 5px; text-align: center; position: relative;
    }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; }
    
    .stTextInput input, .stNumberInput input { font-weight: bold; }
    
    /* STYLE BẢNG VẬT TƯ */
    .total-row { background-color: #fff3cd; font-weight: bold; padding: 10px; border-radius: 5px; text-align: right; margin-top: 10px; }
    .info-tag { font-size: 0.8rem; color: #1565C0; font-style: italic; margin-bottom: 5px; }
    
    /* FOOTER */
    .app-footer { text-align: center; margin-top: 50px; padding-top: 20px; border-top: 1px dashed #eee; color: #999; font-size: 0.8rem; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# --- KẾT NỐI API ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

@st.cache_resource
def get_gs_client():
    return gspread.authorize(get_creds())

# --- TIỆN ÍCH ---
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

# --- CACHE DATA ---
def clear_data_cache(): st.cache_data.clear()

@st.cache_data(ttl=300)
def load_data_with_index():
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype('int64')
        return df
    except: return pd.DataFrame()

# LOAD DANH MỤC VẬT TƯ (CẤU TRÚC MỚI)
@st.cache_data(ttl=300)
def load_materials_master():
    try:
        client = get_gs_client()
        sheet = client.open("QuanLyThuChi").worksheet("dm_vattu")
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])

@st.cache_data(ttl=300)
def load_project_data():
    try:
        client = get_gs_client()
        sheet = client.open("QuanLyThuChi").worksheet("data_duan")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame(columns=["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
        df = pd.DataFrame(data)
        for col in ['SoLuong', 'DonGia', 'ThanhTien']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

# --- HÀM GHI DỮ LIỆU ---
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

# --- HÀM GHI VẬT TƯ (CẬP NHẬT ĐA ĐƠN VỊ) ---
def save_project_material(proj_code, proj_name, mat_name, unit1, unit2, ratio, price_unit1, selected_unit, qty, note):
    client = get_gs_client(); wb = client.open("QuanLyThuChi")
    
    # 1. Lưu Master Data
    try: ws_master = wb.worksheet("dm_vattu")
    except:
        ws_master = wb.add_worksheet("dm_vattu", 1000, 6)
        ws_master.append_row(["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
    
    df_master = pd.DataFrame(ws_master.get_all_records())
    mat_code = ""
    # Check tồn tại
    check_name = remove_accents(mat_name).lower().strip()
    exists = False
    
    if not df_master.empty:
        for idx, row in df_master.iterrows():
            if remove_accents(str(row['TenVT'])).lower().strip() == check_name:
                mat_code = row['MaVT']; exists = True; break
    
    if not exists:
        mat_code = generate_material_code(mat_name)
        # Lưu thông tin gốc (Giá theo Cấp 1)
        ws_master.append_row([mat_code, auto_capitalize(mat_name), unit1, unit2, ratio, price_unit1])
    
    # 2. Tính toán giá thực tế cho Dự án
    final_price = 0
    if selected_unit == unit1: # Chọn cấp 1 (Cuộn)
        final_price = price_unit1
    else: # Chọn cấp 2 (Mét)
        if ratio > 0: final_price = price_unit1 / ratio
        else: final_price = 0
        
    thanh_tien = qty * final_price
    
    # 3. Lưu Data Dự án
    try: ws_data = wb.worksheet("data_duan")
    except:
        ws_data = wb.add_worksheet("data_duan", 1000, 10)
        ws_data.append_row(["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
        
    ws_data.append_row([
        proj_code, auto_capitalize(proj_name), get_vn_time().strftime('%Y-%m-%d %H:%M:%S'),
        mat_code, auto_capitalize(mat_name), selected_unit, # Lưu đơn vị đã chọn
        qty, final_price, thanh_tien, note
    ])
    clear_data_cache()

# --- EXCEL ---
def export_project_materials_excel(df_proj, proj_code, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        # Styles
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_subtitle = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_info = workbook.add_format({'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': 'Times New Roman'})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#E0E0E0', 'text_wrap': True, 'valign': 'vcenter'})
        fmt_cell = workbook.add_format({'border': 1, 'valign': 'vcenter'})
        fmt_num = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0'})
        fmt_dec = workbook.add_format({'border': 1, 'valign': 'vcenter', 'num_format': '#,##0.00'})
        fmt_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'num_format': '#,##0'})

        ws = workbook.add_worksheet("BangKeVatTu")
        ws.merge_range('A1:G1', "BẢNG KÊ VẬT TƯ", fmt_title)
        ws.merge_range('A2:G2', f"Dự án: {proj_name} (Mã: {proj_code})", fmt_subtitle)
        ws.merge_range('A3:G3', f"Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", fmt_info)
        ws.merge_range('A4:G4', "Người tạo: TUẤN VDS.HCM", fmt_info)
        
        cols = ["STT", "Mã VT", "Tên VT", "ĐVT", "Số lượng", "Đơn giá", "Thành tiền"]
        for i, h in enumerate(cols): ws.write(4, i, h, fmt_header)
        
        ws.set_column('A:A', 5); ws.set_column('B:B', 12); ws.set_column('C:C', 35); ws.set_column('D:D', 8); ws.set_column('E:G', 15)
        
        row_idx = 5; total_money = 0
        for i, row in df_proj.iterrows():
            ws.write(row_idx, 0, i+1, fmt_cell)
            ws.write(row_idx, 1, row['MaVT'], fmt_cell)
            ws.write(row_idx, 2, row['TenVT'], fmt_cell)
            ws.write(row_idx, 3, row['DVT'], fmt_cell)
            ws.write(row_idx, 4, row['SoLuong'], fmt_dec) # Số lượng có thể lẻ
            ws.write(row_idx, 5, row['DonGia'], fmt_num)
            ws.write(row_idx, 6, row['ThanhTien'], fmt_num)
            total_money += row['ThanhTien']; row_idx += 1
            
        ws.merge_range(row_idx, 0, row_idx, 5, "TỔNG CỘNG TIỀN", fmt_total)
        ws.write(row_idx, 6, total_money, fmt_total)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

# --- MODULE CŨ ---
def process_report_data(df, start_date=None, end_date=None):
    if df.empty: return pd.DataFrame()
    df_all = df.sort_values(by=['Ngay', 'Row_Index'], ascending=[True, True]).copy()
    df_all['SignedAmount'] = df_all.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_all['ConLai'] = df_all['SignedAmount'].cumsum()
    if start_date and end_date:
        mask_before = df_all['Ngay'].dt.date < start_date
        opening_balance = df_all[mask_before].iloc[-1]['ConLai'] if not df_all[mask_before].empty else 0
        mask_in = (df_all['Ngay'].dt.date >= start_date) & (df_all['Ngay'].dt.date <= end_date)
        df_proc = df_all[mask_in].copy()
        df_proc = pd.concat([pd.DataFrame([{'Row_Index': 0, 'Ngay': pd.Timestamp(start_date), 'Loai': 'Open', 'SoTien': 0, 'MoTa': f"Số dư đầu kỳ", 'HinhAnh': '', 'ConLai': opening_balance, 'SignedAmount': 0}]), df_proc], ignore_index=True)
    else: df_proc = df_all.copy()
    if df_proc.empty: return pd.DataFrame()
    df_proc['STT'] = range(1, len(df_proc) + 1)
    df_proc['Khoan'] = df_proc.apply(lambda x: x['MoTa'] if x['Loai'] == 'Open' else auto_capitalize(x['MoTa']), axis=1)
    df_proc['NgayChi'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai'] == 'Chi' and not pd.isna(x['Ngay']) else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai'] == 'Thu' and not pd.isna(x['Ngay']) else "", axis=1)
    df_proc['SoTienShow'] = df_proc.apply(lambda x: x['SoTien'] if x['Loai'] != 'Open' else 0, axis=1)
    return df_proc[['STT', 'Khoan', 'NgayChi', 'NgayNhan', 'SoTienShow', 'ConLai', 'Loai']]

def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_subtitle = workbook.add_format({'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': 'Times New Roman'})
        fmt_info = workbook.add_format({'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman', 'italic': True})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFFFF', 'font_size': 11, 'text_wrap': True, 'valign': 'vcenter'})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter'})
        fmt_thu = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'num_format': '#,##0', 'valign': 'vcenter'})
        fmt_open = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'num_format': '#,##0', 'valign': 'vcenter'})
        fmt_norm = workbook.add_format({'border': 1, 'num_format': '#,##0', 'valign': 'vcenter'})
        fmt_red = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_color': 'red', 'bold': True, 'valign': 'vcenter'})
        fmt_tot = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFF00', 'font_size': 14, 'valign': 'vcenter'})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'font_size': 14, 'valign': 'vcenter'})

        ws = workbook.add_worksheet("SoQuy")
        ws.merge_range('A1:F1', "QUYẾT TOÁN", fmt_title)
        ws.merge_range('A2:F2', f"Từ ngày {start_date.strftime('%d/%m/%Y')} đến ngày {end_date.strftime('%d/%m/%Y')}", fmt_subtitle)
        ws.merge_range('A3:F3', f"Hệ thống Quyết toán - Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", fmt_info)
        ws.merge_range('A4:F4', "Người tạo: TUẤN VDS.HCM", fmt_info)
        headers = ["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): ws.write(4, c, h, fmt_header)
        ws.set_column('B:B', 40); ws.set_column('C:D', 15); ws.set_column('E:F', 18)
        
        start_row = 5
        for i, row in df_report.iterrows():
            r = start_row + i; loai = row['Loai']
            if loai == 'Thu': c_fmt = fmt_thu
            elif loai == 'Open': c_fmt = fmt_open
            else: c_fmt = fmt_norm
            bal_fmt = fmt_red if row['ConLai'] < 0 else fmt_money
            ws.write(r, 0, row['STT'], c_fmt); ws.write(r, 1, row['Khoan'], c_fmt)
            ws.write(r, 2, row['NgayChi'], c_fmt); ws.write(r, 3, row['NgayNhan'], c_fmt)
            ws.write(r, 4, row['SoTienShow'] if loai != 'Open' else "", c_fmt)
            ws.write(r, 5, row['ConLai'], bal_fmt)
        l_row = start_row + len(df_report)
        ws.merge_range(l_row, 0, l_row, 4, "TỔNG", fmt_tot)
        ws.write(l_row, 5, df_report['ConLai'].iloc[-1] if not df_report.empty else 0, fmt_tot_v)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds(); service = build('drive', 'v3', credentials=creds); folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

# ==================== MODULE QUẢN LÝ VẬT TƯ (CẬP NHẬT) ====================
def render_vattu_module():
    st.subheader("🏗️ Quản Lý Vật Tư Dự Án")
    
    with st.container(border=True):
        st.markdown("**1. Thông tin Dự án**")
        if 'proj_name' not in st.session_state: st.session_state.proj_name = ""
        proj_name_input = st.text_input("Tên Dự án:", value=st.session_state.proj_name, placeholder="VD: Lắp đặt Camera A.Tuấn")
        
        if proj_name_input:
            st.session_state.proj_name = proj_name_input
            proj_code = generate_project_code(proj_name_input)
            st.info(f"🔑 Mã dự án: **{proj_code}**")
            
            # --- PHẦN NHẬP LIỆU THÔNG MINH ---
            st.divider()
            st.markdown("**2. Nhập vật tư sử dụng**")
            
            df_master = load_materials_master()
            master_names = df_master['TenVT'].unique().tolist() if not df_master.empty else []
            
            # Chọn vật tư
            c_name, c_empty = st.columns([3, 1])
            vt_name = c_name.selectbox("Tên vật tư:", options=[""] + master_names, index=0)
            if vt_name == "":
                vt_name = c_name.text_input("Hoặc nhập tên vật tư mới:", placeholder="VD: Dây điện Cadivi 2.5")
            
            # Tự động điền thông tin nếu đã có
            u1, u2, ratio, price1 = "", "", 1.0, 0.0
            if not df_master.empty and vt_name in master_names:
                row_data = df_master[df_master['TenVT'] == vt_name].iloc[0]
                u1 = row_data['DVT_Cap1']; u2 = row_data['DVT_Cap2']
                ratio = float(row_data['QuyDoi']); price1 = float(row_data['DonGia_Cap1'])
                st.caption(f"ℹ️ Thông tin lưu: 1 {u1} = {ratio} {u2}. Giá gốc: {format_vnd(price1)}/{u1}")

            # Nhập chi tiết đơn vị
            c1, c2, c3 = st.columns(3)
            vt_unit1 = c1.text_input("ĐVT Cấp 1 (Lớn):", value=u1, placeholder="VD: Cuộn, Thùng")
            vt_unit2 = c2.text_input("ĐVT Cấp 2 (Nhỏ):", value=u2, placeholder="VD: Mét, Cái")
            vt_ratio = c3.number_input("Quy đổi (1 Lớn = ? Nhỏ):", min_value=1.0, value=ratio, step=1.0)
            
            vt_price1 = st.number_input(f"Đơn giá theo {vt_unit1 if vt_unit1 else 'Cấp 1'}:", min_value=0.0, step=1000.0, value=price1, format="%.0f")
            
            # CHỌN ĐƠN VỊ SỬ DỤNG
            st.write("---")
            st.write(f"🔽 **Bạn đang nhập theo đơn vị nào?**")
            
            unit_opts = []
            if vt_unit1: unit_opts.append(f"{vt_unit1} (Cấp 1)")
            if vt_unit2: unit_opts.append(f"{vt_unit2} (Cấp 2)")
            
            if not unit_opts: unit_opts = ["Mặc định"]
            
            sel_unit_label = st.radio("Chọn đơn vị tính:", unit_opts, horizontal=True)
            
            # Xử lý logic giá theo đơn vị chọn
            sel_unit = ""
            final_price_suggest = 0.0
            
            if vt_unit1 and vt_unit1 in sel_unit_label:
                sel_unit = vt_unit1
                final_price_suggest = vt_price1
            elif vt_unit2 and vt_unit2 in sel_unit_label:
                sel_unit = vt_unit2
                if vt_ratio > 0: final_price_suggest = vt_price1 / vt_ratio
            else:
                sel_unit = vt_unit1
                final_price_suggest = vt_price1

            c_qty, c_total = st.columns(2)
            vt_qty = c_qty.number_input(f"Số lượng ({sel_unit}):", min_value=0.0, step=0.1, format="%.2f")
            c_total.metric(f"Thành tiền (Giá: {format_vnd(final_price_suggest)}/{sel_unit})", format_vnd(vt_qty * final_price_suggest))
            
            vt_note = st.text_input("Ghi chú:", placeholder="Dùng cho phòng khách...")
            
            if st.button("➕ Thêm vào Dự án", type="primary"):
                if vt_name and vt_unit1 and vt_qty > 0:
                    with st.spinner("Đang lưu..."):
                        save_project_material(proj_code, proj_name_input, vt_name, vt_unit1, vt_unit2, vt_ratio, vt_price1, sel_unit, vt_qty, vt_note)
                    st.success(f"Đã thêm: {vt_qty} {sel_unit} {vt_name}"); time.sleep(0.5); st.rerun()
                else: st.warning("Thiếu thông tin (Tên, ĐVT, Số lượng)!")

            # 3. DANH SÁCH & EXCEL
            st.divider()
            df_all_proj = load_project_data()
            if not df_all_proj.empty:
                df_curr = df_all_proj[df_all_proj['MaDuAn'] == proj_code].copy()
                if not df_curr.empty:
                    df_display = df_curr[['TenVT', 'DVT', 'SoLuong', 'DonGia', 'ThanhTien']].reset_index(drop=True)
                    df_display.columns = ['Tên VT', 'ĐVT', 'SL', 'Đơn Giá', 'Thành Tiền']
                    df_display.index += 1
                    st.dataframe(df_display, use_container_width=True)
                    
                    t_q = df_curr['SoLuong'].sum(); t_m = df_curr['ThanhTien'].sum()
                    st.markdown(f"<div class='total-row'>TỔNG TIỀN: {format_vnd(t_m)} VNĐ</div>", unsafe_allow_html=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    excel_data = export_project_materials_excel(df_curr, proj_code, proj_name_input)
                    st.download_button("⬇️ Tải Bảng Kê Vật Tư", excel_data, f"VatTu_{proj_code}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
                else: st.info("Chưa có vật tư.")

# ==================== MAIN APP ====================
def render_thuchi_module(layout_mode):
    df = load_data_with_index()
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum() if not df.empty else 0
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum() if not df.empty else 0
    balance = total_thu - total_chi
    render_dashboard_box(balance, total_thu, total_chi)
    if "Laptop" in layout_mode:
        c1, c2 = st.columns([1, 1.8], gap="medium")
        with c1: render_input_form()
        with c2:
            t1, t2, t3 = st.tabs(["👁️ Sổ Quỹ", "📝 Lịch Sử", "📥 Xuất File"])
            with t1: render_report_table(df)
            with t2: render_history_list(df)
            with t3: render_export(df)
    else:
        t1, t2, t3, t4 = st.tabs(["➕ NHẬP", "📝 LỊCH SỬ", "👁️ SỔ QUỸ", "📥 XUẤT"])
        with t1: render_input_form()
        with t2: render_history_list(df)
        with t3: render_report_table(df)
        with t4: render_export(df)

with st.sidebar:
    st.title("⚙️ Cài đặt")
    if st.button("🔄 Làm mới dữ liệu", use_container_width=True): clear_data_cache(); st.rerun()

_, col_toggle = st.columns([2, 1.5])
with col_toggle: is_laptop = st.toggle("💻 Chế độ Laptop", value=False)
layout_mode = "💻 Laptop" if is_laptop else "📱 Điện thoại"

main_tabs = st.tabs(["💰 THU CHI", "🏗️ VẬT TƯ DỰ ÁN"])
with main_tabs[0]: render_thuchi_module(layout_mode)
with main_tabs[1]: render_vattu_module()

st.markdown("<div class='app-footer'>Phiên bản: 4.1 Multi-Unit - Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)
