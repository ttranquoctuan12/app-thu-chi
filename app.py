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

# ==================== 1. CẤU HÌNH & CSS ====================
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="🏗️", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 3rem !important; }
    
    /* ẨN ICON THỪA */
    [data-testid="stDecoration"], [data-testid="stToolbar"], [data-testid="stHeaderActionElements"], 
    .stAppDeployButton, [data-testid="stStatusWidget"], footer, #MainMenu { display: none !important; }

    /* HEADER & SIDEBAR */
    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 999; }
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important; visibility: visible !important;
        color: #000000 !important; background-color: rgba(255, 255, 255, 0.5); border-radius: 5px;
        z-index: 1000000;
    }

    /* GIAO DIỆN CHUNG */
    [data-testid="stCameraInput"] { width: 100% !important; }
    .stTextInput input, .stNumberInput input { font-weight: bold; }
    
    /* BOX SỐ DƯ */
    .balance-box { 
        padding: 15px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e0e0e0; 
        margin-bottom: 5px; text-align: center; position: relative;
    }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; }
    
    /* UI VẬT TƯ */
    .vt-def-box { background-color: #e3f2fd; padding: 15px; border-radius: 10px; border: 1px dashed #1565C0; margin-bottom: 15px; }
    .vt-input-box { background-color: #f1f8e9; padding: 15px; border-radius: 10px; border: 1px solid #81c784; margin-bottom: 15px; }
    .total-row { background-color: #fff3cd; font-weight: bold; padding: 10px; border-radius: 5px; text-align: right; margin-top: 10px; }
    
    /* FOOTER */
    .app-footer { text-align: center; margin-top: 50px; padding-top: 20px; border-top: 1px dashed #eee; color: #999; font-size: 0.8rem; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. KẾT NỐI & TIỆN ÍCH ====================
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
def load_data_with_index(): # Thu Chi
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
def load_materials_master(): # Danh mục VT
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("dm_vattu")
        return pd.DataFrame(sheet.get_all_records())
    except: return pd.DataFrame(columns=["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])

@st.cache_data(ttl=300)
def load_project_data(): # Data Dự án
    try:
        client = get_gs_client(); sheet = client.open("QuanLyThuChi").worksheet("data_duan")
        data = sheet.get_all_records(); df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
        for col in ['SoLuong', 'DonGia', 'ThanhTien']: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df
    except: return pd.DataFrame()

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
    # 1. Cập nhật Danh mục (nếu mới)
    if is_new_item:
        try: ws_master = wb.worksheet("dm_vattu")
        except: ws_master = wb.add_worksheet("dm_vattu", 1000, 6); ws_master.append_row(["MaVT", "TenVT", "DVT_Cap1", "DVT_Cap2", "QuyDoi", "DonGia_Cap1"])
        
        mat_code = generate_material_code(mat_name)
        ws_master.append_row([mat_code, auto_capitalize(mat_name), unit1, unit2, ratio, price_unit1])
    else:
        df_master = load_materials_master()
        found = df_master[df_master['TenVT'] == mat_name]
        if not found.empty: mat_code = found.iloc[0]['MaVT']
    
    # 2. Tính giá
    final_price = 0
    if selected_unit == unit1: final_price = price_unit1
    else: 
        if float(ratio) > 0: final_price = float(price_unit1) / float(ratio)
    
    thanh_tien = qty * final_price
    
    # 3. Ghi vào Data Du An
    try: ws_data = wb.worksheet("data_duan")
    except: ws_data = wb.add_worksheet("data_duan", 1000, 10); ws_data.append_row(["MaDuAn", "TenDuAn", "NgayNhap", "MaVT", "TenVT", "DVT", "SoLuong", "DonGia", "ThanhTien", "GhiChu"])
        
    ws_data.append_row([proj_code, auto_capitalize(proj_name), get_vn_time().strftime('%Y-%m-%d %H:%M:%S'), mat_code, auto_capitalize(mat_name), selected_unit, qty, final_price, thanh_tien, note])
    clear_data_cache()

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
        fmt_info = workbook.add_format({'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': 'Times New Roman'})
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
            bal_fmt = fmt_red if row['ConLai'] < 0 else fmt_money
            c_fmt = fmt_thu if loai == 'Thu' else (fmt_open if loai == 'Open' else fmt_norm)
            ws.write(r, 0, row['STT'], c_fmt); ws.write(r, 1, row['Khoan'], c_fmt)
            ws.write(r, 2, row['NgayChi'], c_fmt); ws.write(r, 3, row['NgayNhan'], c_fmt)
            ws.write(r, 4, row['SoTienShow'] if loai != 'Open' else "", c_fmt)
            ws.write(r, 5, row['ConLai'], bal_fmt)
        l_row = start_row + len(df_report)
        ws.merge_range(l_row, 0, l_row, 4, "TỔNG", fmt_tot)
        ws.write(l_row, 5, df_report['ConLai'].iloc[-1] if not df_report.empty else 0, fmt_tot_v)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

def export_project_materials_excel(df_proj, proj_code, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
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
            ws.write(row_idx, 0, i+1, fmt_cell); ws.write(row_idx, 1, row['MaVT'], fmt_cell)
            ws.write(row_idx, 2, row['TenVT'], fmt_cell); ws.write(row_idx, 3, row['DVT'], fmt_cell)
            ws.write(row_idx, 4, row['SoLuong'], fmt_dec); ws.write(row_idx, 5, row['DonGia'], fmt_num)
            ws.write(row_idx, 6, row['ThanhTien'], fmt_num)
            total_money += row['ThanhTien']; row_idx += 1
        ws.merge_range(row_idx, 0, row_idx, 5, "TỔNG CỘNG TIỀN", fmt_total)
        ws.write(row_idx, 6, total_money, fmt_total)
        ws.set_row(0, 40); ws.set_row(1, 25); ws.set_row(4, 30)
    return output.getvalue()

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

# ==================== 5. UI COMPONENTS ====================
def render_dashboard_box(bal, thu, chi):
    text_color = "#2ecc71" if bal >= 0 else "#e74c3c"
    html_content = f"""
<div class="balance-box">
<div style="font-size: 1.2rem; font-weight: 900; color: #1565C0; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">HỆ THỐNG CÂN ĐỐI QUYẾT TOÁN</div>
<div style="color: #888; font-size: 0.9rem; text-transform: uppercase;">Số dư hiện tại</div>
<div class="balance-text" style="color: {text_color};">{format_vnd(bal)}</div>
<div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
<div style="color: #27ae60; font-weight: bold;">⬇️ {format_vnd(thu)}</div>
<div style="color: #c0392b; font-weight: bold;">⬆️ {format_vnd(chi)}</div>
</div>
</div>
<div style="text-align: left; margin-top: 0px; margin-bottom: 10px; margin-left: 5px; font-size: 0.75rem; color: #aaa; font-style: italic; font-weight: 600;">TUẤN VDS.HCM</div>
"""
    st.markdown(html_content, unsafe_allow_html=True)

def render_tc_input():
    with st.container(border=True):
        st.subheader("➕ Nhập Giao Dịch")
        if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
        if 'new_desc' not in st.session_state: st.session_state.new_desc = ""
        def auto_fill_callback():
            if "công tác phí" in st.session_state.desc_new.lower(): st.session_state.a_new = 150000; st.session_state.t_new = "Chi"; st.toast("💡 Đã tự động điền 150k công tác phí!")
        c1, c2 = st.columns([1.5, 1])
        d_date = c1.date_input("Ngày", get_vn_time(), key="d_new", label_visibility="collapsed")
        d_type = c2.selectbox("Loại", ["Chi", "Thu"], key="t_new", label_visibility="collapsed")
        st.write("💰 **Số tiền:**"); d_amount = st.number_input("Số tiền", min_value=0, step=5000, value=st.session_state.new_amount, key="a_new", label_visibility="collapsed")
        st.write("📝 **Nội dung:**"); d_desc = st.text_input("Mô tả", value=st.session_state.new_desc, key="desc_new", placeholder="VD: Ăn sáng...", label_visibility="collapsed", on_change=auto_fill_callback)
        st.markdown("<br><b>📷 Hình ảnh</b>", unsafe_allow_html=True)
        cam_mode = st.toggle("Dùng Camera", value=False)
        img_data = st.camera_input("Chụp ảnh", key="cam_new", label_visibility="collapsed") if cam_mode else st.file_uploader("Tải ảnh", type=['jpg','png','jpeg'], key="up_new")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("LƯU GIAO DỊCH", type="primary", use_container_width=True):
            if d_amount > 0 and d_desc.strip() != "":
                with st.spinner("Đang lưu..."):
                    link = ""
                    if img_data: link = upload_image_to_drive(img_data, f"{d_date.strftime('%Y%m%d')}_{remove_accents(d_desc)}.jpg")
                    add_transaction(d_date, d_type, d_amount, d_desc, link)
                st.success("Đã lưu!"); st.session_state.new_amount = 0; st.session_state.new_desc = ""; st.session_state.a_new = 0; st.session_state.desc_new = ""; time.sleep(0.5); st.rerun()
            else: st.warning("Thiếu thông tin!")

def render_tc_history(df):
    if df.empty: st.info("Trống"); return
    if 'edit_row_index' not in st.session_state: st.session_state.edit_row_index = None
    if st.session_state.edit_row_index is not None:
        row = df[df['Row_Index'] == st.session_state.edit_row_index].iloc[0]
        with st.container(border=True):
            st.info(f"✏️ Đang sửa: {row['MoTa']}")
            c1, c2 = st.columns([1.5, 1])
            u_d = c1.date_input("Ngày", value=row['Ngay'], key="u_d")
            u_t = c2.selectbox("Loại", ["Chi", "Thu"], index=(0 if row['Loai'] == "Chi" else 1), key="u_t")
            u_a = st.number_input("Tiền", value=int(row['SoTien']), step=1000, key="u_a")
            u_desc = st.text_input("Mô tả", value=row['MoTa'], key="u_desc")
            b1, b2 = st.columns(2)
            if b1.button("💾 LƯU", type="primary", use_container_width=True): update_transaction(st.session_state.edit_row_index, u_d, u_t, u_a, u_desc, row['HinhAnh']); st.session_state.edit_row_index = None; st.rerun()
            if b2.button("❌ HỦY", use_container_width=True): st.session_state.edit_row_index = None; st.rerun()
    for i, r in df.sort_values(by='Ngay', ascending=False).head(50).iterrows():
        c1, c2, c3 = st.columns([2, 1, 1], gap="small")
        with c1: st.markdown(f"<div class='desc-text'>{r['MoTa']}</div><div class='date-text'>{'🟢' if r['Loai']=='Thu' else '🔴'} {r['Ngay'].strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True); 
        if r['HinhAnh']: st.markdown(f"<a href='{r['HinhAnh']}' target='_blank' style='font-size:0.8rem;'>Xem ảnh</a>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='amt-text' style='color:{'#27ae60' if r['Loai']=='Thu' else '#c0392b'}'>{format_vnd(r['SoTien'])}</div>", unsafe_allow_html=True)
        with c3:
            b1, b2 = st.columns(2)
            if b1.button("✏️", key=f"e_{r['Row_Index']}"): st.session_state.edit_row_index = r['Row_Index']; st.rerun()
            if b2.button("🗑️", key=f"d_{r['Row_Index']}"): delete_transaction(r['Row_Index']); st.toast("Đã xóa"); time.sleep(0.5); st.rerun()
        st.markdown("<div style='border-bottom: 1px solid #f0f0f0; margin: 5px 0;'></div>", unsafe_allow_html=True)

def render_tc_report(df):
    if df.empty: st.info("Chưa có dữ liệu."); return
    today = get_vn_time(); d30 = today - timedelta(days=30)
    col_d1, col_d2 = st.columns(2)
    start_d = col_d1.date_input("Từ ngày", value=d30, key="v_start")
    end_d = col_d2.date_input("Đến ngày", value=today, key="v_end")
    df_report = process_report_data(df, start_d, end_d)
    if not df_report.empty:
        def color_red(val): return f'color: {"red" if isinstance(val, (int, float)) and val < 0 else "black"}'
        def highlight(row): return ['background-color: #FFFF00; color: black; font-weight: bold'] * len(row) if row['Loai'] == 'Thu' else (['background-color: #E0E0E0; font-style: italic'] * len(row) if row['Loai'] == 'Open' else [''] * len(row))
        st.dataframe(df_report.style.apply(highlight, axis=1).map(color_red, subset=['ConLai']).format({"SoTienShow": "{:,.0f}", "ConLai": "{:,.0f}"}), column_config={"STT": st.column_config.NumberColumn("STT", width="small"), "Khoan": st.column_config.TextColumn("Khoản", width="large"), "NgayChi": "Ngày chi", "NgayNhan": "Ngày Nhận", "SoTienShow": "Số tiền", "ConLai": "Còn lại", "Loai": None}, hide_index=True, use_container_width=True, height=500)
        st.markdown(f"<div style='background-color: #FFFF00; padding: 10px; text-align: right; font-weight: bold; font-size: 1.2rem; border: 1px solid #ddd;'>TỔNG SỐ DƯ CUỐI KỲ: <span style='color: {'red' if df_report['ConLai'].iloc[-1] < 0 else 'black'}'>{format_vnd(df_report['ConLai'].iloc[-1])}</span></div>", unsafe_allow_html=True)
    else: st.warning("Không có dữ liệu.")

def render_tc_export(df):
    st.write("📥 **Xuất Excel Sổ Quỹ**")
    if not df.empty:
        c1, c2 = st.columns(2); d1 = c1.date_input("Từ", datetime.now().replace(day=1), key="ed1"); d2 = c2.date_input("Đến", datetime.now(), key="ed2")
        if st.button("Tải File", type="primary", use_container_width=True):
            with st.spinner("Đang tạo file..."):
                df_r = process_report_data(df, d1, d2); data = convert_df_to_excel_custom(df_r, d1, d2)
            st.download_button("⬇️ TẢI NGAY", data, f"SoQuy_{d1.strftime('%d%m')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
    else: st.info("Trống")

# ==================== 6. MODULE THU CHI & VẬT TƯ ====================

def render_thuchi_module(layout_mode):
    df = load_data_with_index()
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum() if not df.empty else 0
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum() if not df.empty else 0
    render_dashboard_box(total_thu - total_chi, total_thu, total_chi)

    if "Laptop" in layout_mode:
        col_left, col_right = st.columns([1, 1.8], gap="medium")
        with col_left: render_input_form()
        with col_right:
            t1, t2, t3 = st.tabs(["👁️ Sổ Quỹ", "📝 Lịch Sử", "📥 Xuất File"])
            with t1: render_tc_report(df)
            with t2: render_tc_history(df)
            with t3: render_tc_export(df)
    else:
        t1, t2, t3, t4 = st.tabs(["➕ NHẬP", "📝 LỊCH SỬ", "👁️ SỔ QUỸ", "📥 XUẤT"])
        with t1: render_input_form()
        with t2: render_tc_history(df)
        with t3: render_tc_report(df)
        with t4: render_tc_export(df)

def render_vattu_module():
    vt_tabs = st.tabs(["➕ NHẬP VẬT TƯ", "📜 LỊCH SỬ DỰ ÁN", "📦 QUẢN LÝ KHO", "📥 XUẤT BÁO CÁO"])
    
    # === TAB 1: NHẬP VẬT TƯ (LINEAR FLOW) ===
    with vt_tabs[0]:
        # 1. CHỌN DỰ ÁN
        with st.container(border=True):
            if 'curr_proj_name' not in st.session_state: st.session_state.curr_proj_name = ""
            proj_col1, proj_col2 = st.columns([3, 1])
            with proj_col1:
                proj_name = st.text_input("📁 Tên Dự án (Nhập mới hoặc Chọn):", value=st.session_state.curr_proj_name, placeholder="VD: Nhà A Tuấn...")
            with proj_col2:
                if proj_name:
                    proj_code = generate_project_code(proj_name)
                    st.text_input("Mã Dự án:", value=proj_code, disabled=True)
                    st.session_state.curr_proj_name = proj_name

        if st.session_state.curr_proj_name:
            # 2. CHỌN VẬT TƯ
            st.markdown("👇 **Nhập chi tiết vật tư**")
            df_master = load_materials_master()
            master_list = df_master['TenVT'].unique().tolist()
            
            selected_vt = st.selectbox("📦 Chọn Tên Vật tư:", [""] + master_list + ["++ TẠO VẬT TƯ MỚI ++"])
            
            is_new = False
            vt_name_final = ""
            u1, u2, ratio, p1 = "", "", 1.0, 0.0
            
            if selected_vt == "++ TẠO VẬT TƯ MỚI ++":
                is_new = True
                vt_name_final = st.text_input("Nhập tên vật tư mới:", placeholder="VD: Keo Silicon A500")
            elif selected_vt != "":
                vt_name_final = selected_vt
                # Load thông tin cũ
                row_data = df_master[df_master['TenVT'] == vt_name_final].iloc[0]
                u1 = row_data['DVT_Cap1']; u2 = row_data['DVT_Cap2']
                ratio = float(row_data['QuyDoi']); p1 = float(row_data['DonGia_Cap1'])

            # 3. ĐỊNH NGHĨA (CHỈ HIỆN KHI MỚI)
            if is_new and vt_name_final:
                st.markdown(f"<div class='vt-def-box'>✨ <b>Định nghĩa cho: {vt_name_final}</b></div>", unsafe_allow_html=True)
                d1, d2, d3, d4 = st.columns(4)
                u1 = d1.text_input("ĐVT Lớn (C1):", placeholder="Thùng")
                u2 = d2.text_input("ĐVT Nhỏ (C2):", placeholder="Cái")
                ratio = d3.number_input("Quy đổi:", min_value=1.0, value=1.0)
                p1 = d4.number_input("Giá nhập (C1):", min_value=0.0, step=1000.0)
            
            # 4. NHẬP SỐ LƯỢNG (LUÔN HIỆN BÊN DƯỚI)
            if vt_name_final:
                st.markdown(f"<div class='vt-input-box'>🔽 <b>Nhập số lượng sử dụng</b></div>", unsafe_allow_html=True)
                
                # Logic chọn đơn vị
                opt_labels = [f"{u1} (Cấp 1)", f"{u2} (Cấp 2)"] if u2 else [f"{u1} (Cấp 1)"]
                if not u1: opt_labels = ["Mặc định"] # Fallback nếu chưa nhập ĐVT
                
                unit_choice = st.radio("Đơn vị xuất:", opt_labels, horizontal=True)
                
                sel_u = u1 if u1 and u1 in unit_choice else (u2 if u2 else "Mặc định")
                price_suggest = p1 if sel_u == u1 else (p1/ratio if ratio > 0 else 0)
                
                q1, q2 = st.columns([1, 2])
                qty_out = q1.number_input(f"Số lượng ({sel_u}):", min_value=0.0, step=1.0)
                total_row = qty_out * price_suggest
                q2.metric("Thành tiền (Tạm tính):", format_vnd(total_row))
                
                note_out = st.text_input("Ghi chú:", placeholder="Dùng cho...")
                
                if st.button("➕ THÊM VÀO DỰ ÁN", type="primary", use_container_width=True):
                    if qty_out > 0:
                        save_project_material(proj_code, st.session_state.curr_proj_name, vt_name_final, u1, u2, ratio, p1, sel_u, qty_out, note_out, is_new)
                        st.success(f"Đã thêm {vt_name_final}"); time.sleep(0.5); st.rerun()
                    else: st.warning("Nhập số lượng!")

            # BẢNG KÊ
            st.divider()
            df_pj = load_project_data()
            if not df_pj.empty and 'MaDuAn' in df_pj.columns:
                df_curr = df_pj[df_pj['MaDuAn'] == proj_code]
                if not df_curr.empty:
                    st.markdown(f"📋 **Vật tư đã dùng: {st.session_state.curr_proj_name}**")
                    st.dataframe(df_curr[['TenVT', 'DVT', 'SoLuong', 'ThanhTien', 'GhiChu']], use_container_width=True)
                    st.markdown(f"<div class='total-row'>TỔNG: {format_vnd(df_curr['ThanhTien'].sum())}</div>", unsafe_allow_html=True)

    # === TAB 2: LỊCH SỬ ===
    with vt_tabs[1]:
        df_pj = load_project_data()
        if not df_pj.empty:
            proj_list = df_pj['TenDuAn'].unique()
            sel_pj = st.selectbox("Chọn dự án để xem:", proj_list)
            if sel_pj:
                df_view = df_pj[df_pj['TenDuAn'] == sel_pj]
                st.dataframe(df_view)
                st.markdown(f"**Tổng tiền dự án:** {format_vnd(df_view['ThanhTien'].sum())}")
        else: st.info("Chưa có dữ liệu dự án.")

    # === TAB 3: KHO ===
    with vt_tabs[2]:
        st.markdown("**Danh mục Vật tư & Quy đổi**")
        df_m = load_materials_master()
        if not df_m.empty:
            for i, row in df_m.iterrows():
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                c1.write(f"**{row['TenVT']}**")
                c2.caption(f"1 {row['DVT_Cap1']} = {row['QuyDoi']} {row['DVT_Cap2']}")
                c3.caption(f"Giá gốc: {format_vnd(row['DonGia_Cap1'])}")
                if c4.button("Xóa", key=f"del_vt_{i}"):
                    delete_material_master(i + 2); st.rerun()
                st.divider()
        else: st.info("Kho trống.")

    # === TAB 4: XUẤT BÁO CÁO ===
    with vt_tabs[3]:
        df_pj = load_project_data()
        if not df_pj.empty:
            p_list = df_pj['TenDuAn'].unique()
            p_sel = st.selectbox("Chọn dự án xuất Excel:", p_list, key="exp_sel")
            if st.button("Tải File Báo Cáo", type="primary"):
                p_code = df_pj[df_pj['TenDuAn'] == p_sel].iloc[0]['MaDuAn']
                df_exp = df_pj[df_pj['TenDuAn'] == p_sel]
                data = export_project_materials_excel(df_exp, p_code, p_sel)
                st.download_button("⬇️ Download Excel", data, f"VatTu_{p_code}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==================== 7. APP EXECUTION ====================
with st.sidebar:
    st.title("⚙️ Cài đặt")
    if st.button("🔄 Làm mới dữ liệu", use_container_width=True): clear_data_cache(); st.rerun()

_, col_toggle = st.columns([2, 1.5])
with col_toggle: is_laptop = st.toggle("💻 Chế độ Laptop", value=False)
layout_mode = "💻 Laptop" if is_laptop else "📱 Điện thoại"

main_tabs = st.tabs(["💰 THU CHI", "🏗️ VẬT TƯ DỰ ÁN"])
with main_tabs[0]: render_thuchi_module(layout_mode)
with main_tabs[1]: render_vattu_module()

st.markdown("<div class='app-footer'>Phiên bản: 5.1 Linear Flow - Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)
