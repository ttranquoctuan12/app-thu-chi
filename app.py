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
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="wide")

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
        color: #000000 !important; background-color: rgba(255, 255, 255, 0.8); border-radius: 5px;
        z-index: 1000000;
    }

    /* GIAO DIỆN CHUNG */
    [data-testid="stCameraInput"] { width: 100% !important; }
    .stTextInput input, .stNumberInput input { font-weight: bold; }
    
    /* UI VẬT TƯ */
    .vt-def-box { 
        background-color: #e3f2fd; padding: 15px; border-radius: 10px; border: 1px dashed #1565C0; 
        margin-bottom: 15px; color: #0d47a1 !important; font-weight: bold;
    }
    .vt-input-box { 
        background-color: #f1f8e9; padding: 15px; border-radius: 10px; border: 1px solid #81c784; 
        margin-bottom: 15px; color: #1b5e20 !important; font-weight: bold;
    }
    .total-row { 
        background-color: #fff3cd; color: #b71c1c !important; font-weight: bold; 
        padding: 10px; border-radius: 5px; text-align: right; margin-top: 10px; 
    }
    .balance-box { 
        padding: 15px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e0e0e0; 
        margin-bottom: 5px; text-align: center; position: relative;
    }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; }
    .app-footer { text-align: center; margin-top: 50px; padding-top: 20px; border-top: 1px dashed #eee; color: #999; font-size: 0.8rem; font-style: italic; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. TIỆN ÍCH HỆ THỐNG ====================
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

# ==================== 3. XỬ LÝ DỮ LIỆU (DATABASE) ====================
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

# --- GHI DỮ LIỆU ---
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
    if selected_unit == unit1: 
        final_price = float(price_unit1)
    else: 
        final_price = float(price_unit1) / ratio_val if ratio_val > 0 else 0
    
    thanh_tien = float(qty) * final_price
    
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

# ==================== 4. EXCEL EXPORT HELPERS ====================
def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter'})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        ws = workbook.add_worksheet("SoQuy")
        ws.merge_range('A1:F1', "QUYẾT TOÁN", fmt_title)
        headers = ["STT", "Khoản", "Ngày", "Loại", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): ws.write(4, c, h, workbook.add_format({'bold': True, 'border': 1}))
        row_idx = 5
        for i, row in df_report.iterrows():
            ws.write(row_idx, 0, row['STT'])
            ws.write(row_idx, 1, row['Khoan'])
            ws.write(row_idx, 2, str(row['NgayChi'] if row['NgayChi'] else row['NgayNhan']))
            ws.write(row_idx, 3, row['Loai'])
            ws.write(row_idx, 4, row['SoTienShow'], fmt_money)
            ws.write(row_idx, 5, row['ConLai'], fmt_money)
            row_idx += 1
    return output.getvalue()

def export_project_materials_excel(df_proj, proj_code, proj_name):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter'})
        fmt_total = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FFFF00', 'num_format': '#,##0'})
        fmt_num = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        
        ws = workbook.add_worksheet("BangKeVatTu")
        ws.merge_range('A1:G1', "BẢNG KÊ VẬT TƯ", fmt_title)
        ws.merge_range('A2:G2', f"Dự án: {proj_name} (Mã: {proj_code})", workbook.add_format({'align': 'center', 'bold': True, 'font_size': 14}))
        ws.merge_range('A3:G3', f"Xuất lúc: {get_vn_time().strftime('%H:%M %d/%m/%Y')}", workbook.add_format({'align': 'center', 'italic': True}))
        ws.merge_range('A4:G4', "Người tạo: TUẤN VDS.HCM", workbook.add_format({'align': 'center', 'italic': True}))
        
        cols = ["STT", "Mã VT", "Tên VT", "ĐVT", "SL", "Đơn giá", "Thành tiền"]
        for i, h in enumerate(cols): ws.write(4, i, h, workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#E0E0E0', 'align': 'center'}))
        
        ws.set_column('A:A', 5); ws.set_column('B:B', 12); ws.set_column('C:C', 35); ws.set_column('E:G', 15)
        
        row_idx = 5; total_money = 0
        for i, row in df_proj.iterrows():
            ws.write(row_idx, 0, i+1, workbook.add_format({'border': 1}))
            ws.write(row_idx, 1, row['MaVT'], workbook.add_format({'border': 1}))
            ws.write(row_idx, 2, row['TenVT'], workbook.add_format({'border': 1}))
            ws.write(row_idx, 3, row['DVT'], workbook.add_format({'border': 1}))
            ws.write(row_idx, 4, row['SoLuong'], workbook.add_format({'border': 1}))
            ws.write(row_idx, 5, row['DonGia'], fmt_num)
            ws.write(row_idx, 6, row['ThanhTien'], fmt_num)
            total_money += row['ThanhTien']; row_idx += 1
            
        ws.merge_range(row_idx, 0, row_idx, 5, "TỔNG CỘNG TIỀN", fmt_total)
        ws.write(row_idx, 6, total_money, fmt_total)
    return output.getvalue()

def process_report_data(df, start_date=None, end_date=None):
    if df.empty: return pd.DataFrame()
    df_all = df.sort_values(by=['Ngay', 'Row_Index']).copy()
    df_all['SignedAmount'] = df_all.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_all['ConLai'] = df_all['SignedAmount'].cumsum()
    if start_date and end_date:
        mask_in = (df_all['Ngay'].dt.date >= start_date) & (df_all['Ngay'].dt.date <= end_date)
        df_proc = df_all[mask_in].copy()
    else: df_proc = df_all.copy()
    if df_proc.empty: return pd.DataFrame()
    df_proc['STT'] = range(1, len(df_proc) + 1)
    df_proc['Khoan'] = df_proc.apply(lambda x: auto_capitalize(x['MoTa']), axis=1)
    df_proc['NgayChi'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai']=='Chi' else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai']=='Thu' else "", axis=1)
    df_proc['SoTienShow'] = df_proc['SoTien']
    return df_proc

# ==================== 5. UI COMPONENTS ====================

def render_dashboard_box(bal, thu, chi):
    text_color = "#2ecc71" if bal >= 0 else "#e74c3c"
    html_content = f"""
<div class="balance-box">
<div style="font-size: 1.2rem; font-weight: 900; color: #1565C0; margin-bottom: 8px;">HỆ THỐNG CÂN ĐỐI QUYẾT TOÁN</div>
<div style="color: #888;">Số dư hiện tại</div>
<div class="balance-text" style="color: {text_color};">{format_vnd(bal)}</div>
<div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
<div style="color: #27ae60; font-weight: bold;">⬇️ {format_vnd(thu)}</div>
<div style="color: #c0392b; font-weight: bold;">⬆️ {format_vnd(chi)}</div>
</div>
</div>
<div style="text-align: left; margin-top: 0px; margin-bottom: 10px; margin-left: 5px; font-size: 0.75rem; color: #aaa; font-style: italic; font-weight: 600;">TUẤN VDS.HCM</div>
"""
    st.markdown(html_content, unsafe_allow_html=True)

# --- THU CHI UI ---
def render_thuchi_input():
    with st.container(border=True):
        st.subheader("➕ Nhập Giao Dịch")
        if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
        if 'new_desc' not in st.session_state: st.session_state.new_desc = ""
        def auto_fill_callback():
            if "công tác phí" in st.session_state.desc_new.lower(): st.session_state.a_new = 150000; st.session_state.t_new = "Chi"; st.toast("💡 Auto-fill 150k!")
        c1, c2 = st.columns([1.5, 1])
        d_date = c1.date_input("Ngày", get_vn_time(), key="d_new")
        d_type = c2.selectbox("Loại", ["Chi", "Thu"], key="t_new")
        st.write("💰 **Số tiền:**"); d_amount = st.number_input("Số tiền", min_value=0, step=5000, value=st.session_state.new_amount, key="a_new")
        st.write("📝 **Nội dung:**"); d_desc = st.text_input("Mô tả", value=st.session_state.new_desc, key="desc_new", on_change=auto_fill_callback)
        st.markdown("<br><b>📷 Hình ảnh</b>", unsafe_allow_html=True)
        cam = st.toggle("Dùng Camera", value=False)
        img = st.camera_input("Chụp", key="cam") if cam else st.file_uploader("Tải ảnh", key="up")
        if st.button("LƯU GIAO DỊCH", type="primary", use_container_width=True):
            if d_amount > 0 and d_desc.strip():
                link = upload_image_to_drive(img, f"{d_date}_{d_desc}.jpg") if img else ""
                add_transaction(d_date, d_type, d_amount, d_desc, link)
                st.success("Đã lưu!"); time.sleep(0.5); st.rerun()

def render_thuchi_history(df):
    if df.empty: st.info("Trống"); return
    df_sorted = df.sort_values(by='Ngay', ascending=False)
    for i, r in df_sorted.head(50).iterrows():
        c1, c2, c3 = st.columns([2, 1, 1], gap="small")
        with c1: st.markdown(f"**{r['MoTa']}**<br><span style='color:grey;font-size:0.8em'>{r['Ngay'].strftime('%d/%m')}</span>", unsafe_allow_html=True)
        with c2: st.markdown(f"<span style='color:{'green' if r['Loai']=='Thu' else 'red'};font-weight:bold'>{format_vnd(r['SoTien'])}</span>", unsafe_allow_html=True)
        with c3: 
            if st.button("🗑️", key=f"del_{r['Row_Index']}"): delete_transaction(r['Row_Index']); st.rerun()
        st.divider()

def render_thuchi_report(df):
    if df.empty: st.info("Chưa có dữ liệu."); return
    d1 = st.date_input("Từ", get_vn_time().replace(day=1)); d2 = st.date_input("Đến", get_vn_time())
    df_r = process_report_data(df, d1, d2)
    st.dataframe(df_r, use_container_width=True)

def render_thuchi_export(df):
    if st.button("Tải Excel"):
        data = convert_df_to_excel_custom(process_report_data(df), datetime.now(), datetime.now())
        st.download_button("Download", data, "SoQuy.xlsx")

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
            t1, t2, t3 = st.tabs(["👁️ Sổ Quỹ", "📝 Lịch Sử", "📥 Xuất File"])
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
    vt_tabs = st.tabs(["➕ NHẬP VẬT TƯ", "📜 LỊCH SỬ", "📦 KHO", "📥 XUẤT"])
    
    with vt_tabs[0]: # NHẬP LIỆU
        with st.container(border=True):
            if 'curr_proj_name' not in st.session_state: st.session_state.curr_proj_name = ""
            p_name = st.text_input("📁 Tên Dự án:", value=st.session_state.curr_proj_name)
            if p_name:
                st.session_state.curr_proj_name = p_name
                st.text_input("Mã Dự án:", value=generate_project_code(p_name), disabled=True)

        if st.session_state.curr_proj_name:
            st.markdown("👇 **Nhập chi tiết vật tư**")
            df_m = load_materials_master()
            m_list = df_m['TenVT'].unique().tolist() if not df_m.empty and 'TenVT' in df_m.columns else []
            
            sel_vt = st.selectbox("📦 Chọn Vật tư:", [""] + m_list + ["++ TẠO VẬT TƯ MỚI ++"])
            
            is_new = False; vt_final = ""; u1, u2, ratio, p1 = "", "", 1.0, 0.0
            
            if sel_vt == "++ TẠO VẬT TƯ MỚI ++":
                is_new = True
                vt_final = st.text_input("Nhập tên vật tư mới:", placeholder="VD: Keo Silicon")
            elif sel_vt != "":
                vt_final = sel_vt
                if not df_m.empty and 'TenVT' in df_m.columns:
                    row = df_m[df_m['TenVT'] == vt_final].iloc[0]
                    u1 = str(row.get('DVT_Cap1', '')); u2 = str(row.get('DVT_Cap2', ''))
                    try: ratio = float(row.get('QuyDoi', 1)); p1 = float(row.get('DonGia_Cap1', 0))
                    except: ratio=1.0; p1=0.0

            if is_new and vt_final:
                st.markdown(f"<div class='vt-def-box'>✨ Định nghĩa: {vt_final}</div>", unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                u1 = c1.text_input("ĐVT Lớn:", placeholder="Thùng")
                u2 = c2.text_input("ĐVT Nhỏ:", placeholder="Cái")
                ratio = c3.number_input("Quy đổi (1 Lớn = ? Nhỏ):", min_value=1.0, value=1.0, help="QUAN TRỌNG: Nhập số lượng thực tế.\nVD: 1 Cuộn dài 100m -> Nhập 100.\n1 Thùng có 24 cái -> Nhập 24.")
                st.caption("⚠️ Lưu ý: Nhập số lượng quy đổi chính xác để tính giá đúng!")
                p1 = c4.number_input("Giá nhập (Lớn):", min_value=0.0, step=1000.0)

            if vt_final:
                st.markdown(f"<div class='vt-input-box'>🔽 Nhập số lượng sử dụng</div>", unsafe_allow_html=True)
                unit_ops = [f"{u1} (Cấp 1)", f"{u2} (Cấp 2)"] if u2 else [f"{u1} (Cấp 1)"]
                if not u1: unit_ops = ["Mặc định"]
                
                u_choice = st.radio("Đơn vị xuất:", unit_ops, horizontal=True)
                sel_u = u1 if u1 and u1 in u_choice else (u2 if u2 else "Mặc định")
                
                # Logic tính giá (QUAN TRỌNG)
                price_suggest = p1 if sel_u == u1 else (p1/ratio if ratio > 0 else 0)
                
                c1, c2 = st.columns([1, 2])
                qty = c1.number_input(f"Số lượng ({sel_u}):", min_value=0.0, step=1.0)
                c2.metric("Thành tiền (Tạm tính):", format_vnd(qty * price_suggest))
                note = st.text_input("Ghi chú:")
                
                if st.button("➕ THÊM VÀO DỰ ÁN", type="primary", use_container_width=True):
                    if qty > 0:
                        save_project_material(generate_project_code(st.session_state.curr_proj_name), st.session_state.curr_proj_name, vt_final, u1, u2, ratio, p1, sel_u, qty, note, is_new)
                        st.success("Đã thêm!"); time.sleep(0.5); st.rerun()
            
            # Show list
            df_pj = load_project_data()
            p_code = generate_project_code(st.session_state.curr_proj_name)
            if not df_pj.empty and 'MaDuAn' in df_pj.columns:
                curr = df_pj[df_pj['MaDuAn'] == p_code]
                if not curr.empty:
                    st.divider()
                    st.dataframe(curr[['TenVT', 'DVT', 'SoLuong', 'ThanhTien']], use_container_width=True)
                    st.markdown(f"<div class='total-row'>TỔNG: {format_vnd(curr['ThanhTien'].sum())}</div>", unsafe_allow_html=True)

    with vt_tabs[1]: # LỊCH SỬ
        df_pj = load_project_data()
        if not df_pj.empty:
            p_sel = st.selectbox("Chọn dự án:", df_pj['TenDuAn'].unique())
            if p_sel:
                view = df_pj[df_pj['TenDuAn'] == p_sel]
                st.dataframe(view)
                st.markdown(f"**Tổng:** {format_vnd(view['ThanhTien'].sum())}")

    with vt_tabs[2]: # KHO
        df_m = load_materials_master()
        if not df_m.empty and 'TenVT' in df_m.columns:
            st.dataframe(df_m)
            
    with vt_tabs[3]: # XUẤT (CÓ TỔNG HỢP)
        df_pj = load_project_data()
        if not df_pj.empty:
            # Thêm lựa chọn TỔNG HỢP
            p_opts = ["TẤT CẢ DỰ ÁN (TỔNG HỢP)"] + df_pj['TenDuAn'].unique().tolist()
            p_sel = st.selectbox("Chọn dự án xuất:", p_opts, key='xp')
            
            if st.button("Tải Excel"):
                if p_sel == "TẤT CẢ DỰ ÁN (TỔNG HỢP)":
                    # Logic Tổng hợp
                    df_agg = df_pj.groupby(['MaVT', 'TenVT', 'DVT'], as_index=False).agg({'SoLuong': 'sum', 'ThanhTien': 'sum'})
                    df_agg['DonGia'] = df_agg.apply(lambda x: x['ThanhTien']/x['SoLuong'] if x['SoLuong']>0 else 0, axis=1)
                    data = export_project_materials_excel(df_agg, "ALL", "TỔNG HỢP TẤT CẢ DỰ ÁN")
                    st.download_button("Download Tổng Hợp", data, "TongHopVatTu.xlsx")
                else:
                    # Logic dự án đơn lẻ
                    p_c = generate_project_code(p_sel)
                    d_xp = df_pj[df_pj['TenDuAn'] == p_sel]
                    data = export_project_materials_excel(d_xp, p_c, p_sel)
                    st.download_button("Download Chi Tiết", data, f"VatTu_{p_c}.xlsx")

# ==================== 8. CHẠY APP ====================
with st.sidebar:
    st.title("⚙️ Cài đặt")
    if st.button("🔄 Làm mới"): clear_data_cache(); st.rerun()

_, col_t = st.columns([2, 1.5])
with col_t: is_laptop = st.toggle("💻 Laptop Mode", value=False)
layout_mode = "Laptop" if is_laptop else "Mobile"

main_tabs = st.tabs(["💰 THU CHI", "🏗️ VẬT TƯ DỰ ÁN"])
with main_tabs[0]: render_thuchi_module(layout_mode)
with main_tabs[1]: render_vattu_module()

st.markdown("<div class='app-footer'>Phiên bản: 5.5 Final Complete - Powered by TUẤN VDS.HCM</div>", unsafe_allow_html=True)
