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

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="wide")

# --- 2. CSS TỐI ƯU GIAO DIỆN & ẨN ICON THỪA ---
st.markdown("""
<style>
    /* 1. Cấu hình lề trang */
    .block-container { 
        padding-top: 1rem !important; 
        padding-bottom: 3rem !important; 
        padding-left: 0.5rem !important; 
        padding-right: 0.5rem !important; 
    }

    /* 2. ẨN CÁC THÀNH PHẦN HỆ THỐNG (Header, Toolbar, Deploy Button) */
    
    /* Ẩn dải màu trang trí trên cùng */
    [data-testid="stDecoration"] { display: none !important; }
    
    /* Ẩn TOÀN BỘ cụm nút bên phải (Fork, GitHub, Menu 3 chấm) */
    [data-testid="stToolbar"] { display: none !important; visibility: hidden !important; }
    [data-testid="stHeaderActionElements"] { display: none !important; visibility: hidden !important; }
    
    /* Ẩn nút "Deploy" (Vương miện/Tên lửa) ở góc phải */
    .stAppDeployButton { display: none !important; visibility: hidden !important; }
    
    /* Ẩn Widget trạng thái (Running/Stop) */
    [data-testid="stStatusWidget"] { display: none !important; }
    
    /* Ẩn Footer và Menu mặc định */
    footer { display: none !important; }
    #MainMenu { display: none !important; }

    /* QUAN TRỌNG: Làm trong suốt Header để không che nội dung, nhưng vẫn giữ nút Sidebar */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        z-index: 1; /* Thấp hơn nội dung */
    }
    
    /* Đảm bảo nút mở Sidebar (góc trái) luôn hiện rõ và bấm được */
    [data-testid="stSidebarCollapsedControl"] {
        display: block !important;
        visibility: visible !important;
        z-index: 999999; /* Đẩy lên lớp trên cùng */
        color: #333; /* Màu đen cho dễ nhìn */
    }

    /* 3. GIAO DIỆN APP */
    [data-testid="stCameraInput"] { width: 100% !important; }
    [data-testid="stCameraInput"] video { width: 100% !important; border-radius: 12px; border: 2px solid #eee; }
    
    .balance-box { 
        padding: 15px; 
        border-radius: 12px; 
        background-color: #f8f9fa; 
        border: 1px solid #e0e0e0; 
        margin-bottom: 20px; 
        text-align: center;
        position: relative; /* Để căn chỉnh chữ ký tuyệt đối bên trong */
    }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; }
    
    .history-row { padding: 8px 0; border-bottom: 1px solid #eee; }
    .desc-text { font-weight: 600; font-size: 1rem; color: #333; margin-bottom: 2px; }
    .date-text { font-size: 0.8rem; color: #888; }
    .amt-text { font-weight: bold; font-size: 1rem; }
    
    .stTextInput input, .stNumberInput input { font-weight: bold; }
    button[kind="secondary"] { padding: 0.25rem 0.5rem; border: 1px solid #eee; }
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

# --- CẤU HÌNH MÚI GIỜ VIỆT NAM ---
def get_vn_time():
    return datetime.now(pytz.timezone('Asia/Ho_Chi_Minh'))

# --- TIỆN ÍCH ---
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

# --- XỬ LÝ SỐ LIỆU ---
def process_report_data(df, start_date=None, end_date=None):
    if df.empty: return pd.DataFrame()
    df_all = df.sort_values(by=['Ngay', 'Row_Index'], ascending=[True, True]).copy()
    df_all['SignedAmount'] = df_all.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_all['ConLai'] = df_all['SignedAmount'].cumsum()

    if start_date and end_date:
        mask_before = df_all['Ngay'].dt.date < start_date
        df_before = df_all[mask_before]
        opening_balance = df_before.iloc[-1]['ConLai'] if not df_before.empty else 0
        
        mask_in = (df_all['Ngay'].dt.date >= start_date) & (df_all['Ngay'].dt.date <= end_date)
        df_proc = df_all[mask_in].copy()
        
        row_open = {'Row_Index': 0, 'Ngay': pd.Timestamp(start_date), 'Loai': 'Open', 'SoTien': 0, 'MoTa': f"Số dư đầu kỳ", 'HinhAnh': '', 'ConLai': opening_balance, 'SignedAmount': 0}
        df_open = pd.DataFrame([row_open])
        df_proc = pd.concat([df_open, df_proc], ignore_index=True)
    else:
        df_proc = df_all.copy()

    if df_proc.empty: return pd.DataFrame()

    df_proc['STT'] = range(1, len(df_proc) + 1)
    df_proc['Khoan'] = df_proc.apply(lambda x: x['MoTa'] if x['Loai'] == 'Open' else auto_capitalize(x['MoTa']), axis=1)
    def get_date_str(row): return "" if row['Loai'] == 'Open' or pd.isna(row['Ngay']) else row['Ngay'].strftime('%d/%m/%Y')
    df_proc['NgayChi'] = df_proc.apply(lambda x: get_date_str(x) if x['Loai'] == 'Chi' else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: get_date_str(x) if x['Loai'] == 'Thu' else "", axis=1)
    df_proc['SoTienShow'] = df_proc.apply(lambda x: x['SoTien'] if x['Loai'] != 'Open' else 0, axis=1)

    return df_proc[['STT', 'Khoan', 'NgayChi', 'NgayNhan', 'SoTienShow', 'ConLai', 'Loai']]

# --- EXCEL CUSTOM (UPDATE GIỜ VN) ---
def convert_df_to_excel_custom(df_report, start_date, end_date):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # --- ĐỊNH DẠNG ---
        fmt_title = workbook.add_format({'bold': True, 'font_size': 26, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman'})
        fmt_subtitle = workbook.add_format({'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'italic': True, 'font_name': 'Times New Roman'})
        fmt_info = workbook.add_format({'font_size': 11, 'align': 'center', 'valign': 'vcenter', 'font_name': 'Times New Roman', 'italic': True})
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFFFF', 'font_size': 11, 'text_wrap': True, 'valign': 'vcenter'})
        
        fmt_normal = workbook.add_format({'border': 1, 'font_size': 11, 'valign': 'vcenter'})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter'})
        fmt_thu_bg = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'font_size': 11, 'valign': 'vcenter'})
        fmt_thu_money = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter'})
        fmt_open_bg = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'bold': True, 'font_size': 11, 'valign': 'vcenter'})
        fmt_open_money = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'bold': True, 'num_format': '#,##0', 'font_size': 11, 'valign': 'vcenter'})
        fmt_red = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_color': 'red', 'bold': True, 'font_size': 11, 'valign': 'vcenter'})
        fmt_orange = workbook.add_format({'border': 1, 'num_format': '#,##0', 'bg_color': '#FF9900', 'bold': True, 'font_size': 11, 'valign': 'vcenter'}) 
        fmt_tot = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFF00', 'font_size': 14, 'valign': 'vcenter'})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'font_size': 14, 'valign': 'vcenter'})

        worksheet = workbook.add_worksheet("SoQuy")
        
        # --- HEADER ---
        worksheet.merge_range('A1:F1', "QUYẾT TOÁN", fmt_title)
        
        date_str = f"Từ ngày {start_date.strftime('%d/%m/%Y')} đến ngày {end_date.strftime('%d/%m/%Y')}"
        worksheet.merge_range('A2:F2', date_str, fmt_subtitle)
        
        # Lấy giờ Việt Nam để in vào file
        current_time_str = get_vn_time().strftime("%H:%M %d/%m/%Y")
        sys_info = f"Hệ thống Quyết toán - Xuất lúc: {current_time_str}"
        worksheet.merge_range('A3:F3', sys_info, fmt_info)
        
        creator_info = "Người tạo: TUẤN VDS.HCM"
        worksheet.merge_range('A4:F4', creator_info, fmt_info)
        
        headers = ["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): worksheet.write(4, c, h, fmt_header)
        
        worksheet.set_column('A:A', 6); worksheet.set_column('B:B', 40); worksheet.set_column('C:D', 15); worksheet.set_column('E:F', 18)

        start_row_idx = 5
        for i, row in df_report.iterrows():
            r = start_row_idx + i
            loai = row['Loai']
            bal = row['ConLai']
            if loai == 'Thu': c_fmt = fmt_thu_bg; m_fmt = fmt_thu_money; bal_fmt = fmt_orange
            elif loai == 'Open': c_fmt = fmt_open_bg; m_fmt = fmt_open_money; bal_fmt = fmt_open_money
            else: c_fmt = fmt_normal; m_fmt = fmt_money; bal_fmt = fmt_red if bal < 0 else fmt_money

            worksheet.write(r, 0, row['STT'], c_fmt)
            worksheet.write(r, 1, row['Khoan'], c_fmt)
            worksheet.write(r, 2, row['NgayChi'], c_fmt)
            worksheet.write(r, 3, row['NgayNhan'], c_fmt)
            if loai == 'Open': worksheet.write(r, 4, "", m_fmt)
            else: worksheet.write(r, 4, row['SoTienShow'], m_fmt)
            worksheet.write(r, 5, bal, bal_fmt)
            
        l_row = start_row_idx + len(df_report)
        fin_bal = df_report['ConLai'].iloc[-1] if not df_report.empty else 0
        worksheet.merge_range(l_row, 0, l_row, 4, "TỔNG", fmt_tot)
        worksheet.write(l_row, 5, fin_bal, fmt_tot_v)
        
        worksheet.set_row(0, 40); worksheet.set_row(1, 25); worksheet.set_row(4, 30)

    return output.getvalue()

# --- DRIVE & CRUD ---
def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

@st.cache_data(ttl=300)
def load_data_with_index():
    try:
        client = get_gs_client()
        sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype('int64')
        return df
    except: return pd.DataFrame()

def clear_data_cache():
    st.cache_data.clear()

def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link])
    clear_data_cache()

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    r = int(row_idx)
    sheet.update(f"A{r}:E{r}", [[date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link]])
    clear_data_cache()

def delete_transaction(row_idx):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(int(row_idx))
    clear_data_cache()

# ==================== VIEW MODULES ====================

def render_input_form():
    with st.container(border=True):
        st.subheader("➕ Nhập Giao Dịch")
        if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
        if 'new_desc' not in st.session_state: st.session_state.new_desc = ""

        c1, c2 = st.columns([1.5, 1])
        # SỬA LỖI: Dùng giờ VN làm mặc định
        d_date = c1.date_input("Ngày", get_vn_time(), key="d_new", label_visibility="collapsed")
        d_type = c2.selectbox("Loại", ["Chi", "Thu"], key="t_new", label_visibility="collapsed")
        
        st.write("💰 **Số tiền:**")
        d_amount = st.number_input("Số tiền", min_value=0, step=5000, value=st.session_state.new_amount, key="a_new", label_visibility="collapsed")
        st.write("📝 **Nội dung:**")
        d_desc = st.text_input("Mô tả", value=st.session_state.new_desc, key="desc_new", placeholder="VD: Ăn sáng...", label_visibility="collapsed")
        
        st.markdown("<br><b>📷 Hình ảnh</b>", unsafe_allow_html=True)
        cam_mode = st.toggle("Dùng Camera", value=False)
        img_data = st.camera_input("Chụp ảnh", key="cam_new", label_visibility="collapsed") if cam_mode else st.file_uploader("Tải ảnh", type=['jpg','png','jpeg'], key="up_new")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("LƯU GIAO DỊCH", type="primary", use_container_width=True):
            if d_amount > 0 and d_desc.strip() != "":
                with st.spinner("Đang lưu..."):
                    link = ""
                    if img_data:
                        fname = f"{d_date.strftime('%Y%m%d')}_{remove_accents(d_desc)}.jpg"
                        link = upload_image_to_drive(img_data, fname)
                    add_transaction(d_date, d_type, d_amount, d_desc, link)
                st.success("Đã lưu!")
                st.session_state.new_amount = 0; st.session_state.new_desc = ""; time.sleep(0.5); st.rerun()
            else: st.warning("Thiếu thông tin!")

def render_dashboard_box(bal, thu, chi):
    text_color = "#2ecc71" if bal >= 0 else "#e74c3c"
    # SỬA: Đưa chữ TUẤN VDS.HCM vào bên trong hộp (Góc dưới phải)
    st.markdown(f"""
<div class="balance-box">
    <div style="font-size: 1.2rem; font-weight: 900; color: #1565C0; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
        HỆ THỐNG CÂN ĐỐI QUYẾT TOÁN
    </div>
    <div style="color: #888; font-size: 0.9rem; text-transform: uppercase;">Số dư hiện tại</div>
    <div class="balance-text" style="color: {text_color};">{format_vnd(bal)}</div>
    <div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
        <div style="color: #27ae60; font-weight: bold;">⬇️ {format_vnd(thu)}</div>
        <div style="color: #c0392b; font-weight: bold;">⬆️ {format_vnd(chi)}</div>
    </div>
    
    <div style="position: absolute; bottom: 5px; right: 10px; font-size: 0.7rem; color: #aaa; font-style: italic; font-weight: bold; background-color: #f0f7ff; padding: 2px 6px; border-radius: 4px;">
        TUẤN VDS.HCM
    </div>
</div>
""", unsafe_allow_html=True)

def render_report_table(df):
    if df.empty: st.info("Chưa có dữ liệu."); return
    
    # SỬA LỖI: Mặc định 30 ngày theo giờ VN
    today = get_vn_time()
    d30 = today - timedelta(days=30)
    
    col_d1, col_d2 = st.columns(2)
    start_d = col_d1.date_input("Từ ngày", value=d30, key="v_start")
    end_d = col_d2.date_input("Đến ngày", value=today, key="v_end")
    
    df_report = process_report_data(df, start_d, end_d)
    if not df_report.empty:
        def highlight(row): 
            if row['Loai'] == 'Thu': return ['background-color: #FFFF00; color: black; font-weight: bold'] * len(row)
            if row['Loai'] == 'Open': return ['background-color: #E0E0E0; font-style: italic'] * len(row)
            return [''] * len(row)
        def color_red(val): return f'color: {"red" if isinstance(val, (int, float)) and val < 0 else "black"}'

        st.dataframe(
            df_report.style.apply(highlight, axis=1).map(color_red, subset=['ConLai']).format({"SoTienShow": "{:,.0f}", "ConLai": "{:,.0f}"}),
            column_config={"STT": st.column_config.NumberColumn("STT", width="small"), "Khoan": st.column_config.TextColumn("Khoản", width="large"), "NgayChi": "Ngày chi", "NgayNhan": "Ngày Nhận", "SoTienShow": "Số tiền", "ConLai": "Còn lại", "Loai": None},
            hide_index=True, use_container_width=True, height=500
        )
        final_bal = df_report['ConLai'].iloc[-1]
        st.markdown(f"<div style='background-color: #FFFF00; padding: 10px; text-align: right; font-weight: bold; font-size: 1.2rem; border: 1px solid #ddd;'>TỔNG SỐ DƯ CUỐI KỲ: <span style='color: {'red' if final_bal < 0 else 'black'}'>{format_vnd(final_bal)}</span></div>", unsafe_allow_html=True)
    else: st.warning("Không có dữ liệu.")

def render_history_list(df):
    if df.empty: st.info("Trống"); return
    
    if 'edit_row_index' not in st.session_state: st.session_state.edit_row_index = None
    if st.session_state.edit_row_index is not None:
        row_to_edit = df[df['Row_Index'] == st.session_state.edit_row_index]
        if not row_to_edit.empty:
            row_data = row_to_edit.iloc[0]
            with st.container(border=True):
                st.info(f"✏️ Đang sửa: {row_data['MoTa']}")
                ue1, ue2 = st.columns([1.5, 1])
                ud_date = ue1.date_input("Ngày", value=row_data['Ngay'], key="u_d")
                ud_type = ue2.selectbox("Loại", ["Chi", "Thu"], index=(0 if row_data['Loai'] == "Chi" else 1), key="u_t")
                ud_amt = st.number_input("Tiền", value=int(row_data['SoTien']), step=1000, key="u_a")
                ud_desc = st.text_input("Mô tả", value=row_data['MoTa'], key="u_desc")
                b1, b2 = st.columns(2)
                if b1.button("💾 LƯU", type="primary", use_container_width=True):
                    update_transaction(st.session_state.edit_row_index, ud_date, ud_type, ud_amt, ud_desc, row_data['HinhAnh'])
                    st.session_state.edit_row_index = None; st.rerun()
                if b2.button("❌ HỦY", use_container_width=True): st.session_state.edit_row_index = None; st.rerun()

    df_sorted = df.sort_values(by='Ngay', ascending=False)
    h1, h2, h3 = st.columns([2, 1, 1]); h1.caption("Nội dung"); h2.caption("Số tiền"); h3.caption("Thao tác"); st.divider()
    
    for index, row in df_sorted.head(50).iterrows():
        c1, c2, c3 = st.columns([2, 1, 1], gap="small")
        with c1:
            icon = "🟢" if row['Loai'] == 'Thu' else "🔴"
            st.markdown(f"<div class='desc-text'>{row['MoTa']}</div><div class='date-text'>{icon} {row['Ngay'].strftime('%d/%m/%Y')}</div>", unsafe_allow_html=True)
            if row['HinhAnh']: st.markdown(f"<a href='{row['HinhAnh']}' target='_blank' style='font-size:0.8rem;'>Xem ảnh</a>", unsafe_allow_html=True)
        with c2:
            color = "#27ae60" if row['Loai'] == 'Thu' else "#c0392b"
            st.markdown(f"<div class='amt-text' style='color:{color}'>{format_vnd(row['SoTien'])}</div>", unsafe_allow_html=True)
        with c3:
            bc1, bc2 = st.columns(2)
            if bc1.button("✏️", key=f"e_{row['Row_Index']}", help="Sửa"): st.session_state.edit_row_index = row['Row_Index']; st.rerun()
            if bc2.button("🗑️", key=f"d_{row['Row_Index']}", help="Xóa"): delete_transaction(row['Row_Index']); st.toast("Đã xóa"); time.sleep(0.5); st.rerun()
        st.markdown("<div style='border-bottom: 1px solid #f0f0f0; margin: 5px 0;'></div>", unsafe_allow_html=True)
    
    if len(df) > 50: st.caption("... và còn nhiều giao dịch cũ hơn")

def render_export(df):
    st.write("📥 **Xuất Excel Sổ Quỹ**")
    if not df.empty:
        c1, c2 = st.columns(2)
        d1 = c1.date_input("Từ", datetime.now().replace(day=1), key="ed1"); d2 = c2.date_input("Đến", datetime.now(), key="ed2")
        if st.button("Tải File", type="primary", use_container_width=True):
            with st.spinner("Đang tạo file..."):
                df_r = process_report_data(df, d1, d2)
                data = convert_df_to_excel_custom(df_r, d1, d2)
            st.download_button("⬇️ TẢI NGAY", data, f"SoQuy_{d1.strftime('%d%m')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
    else: st.info("Trống")

# ==================== MAIN ====================
df = load_data_with_index()
total_thu = 0; total_chi = 0; balance = 0
if not df.empty:
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum()
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum()
    balance = total_thu - total_chi

with st.sidebar:
    st.title("⚙️ Cài đặt")
    layout_mode = st.radio("Chế độ xem:", ["📱 Điện thoại", "💻 Laptop"])
    if st.button("🔄 Làm mới dữ liệu", use_container_width=True):
        clear_data_cache(); st.rerun()
    st.info("Phiên bản: 2.5 Clean UX")

if "Laptop" in layout_mode:
    col_left, col_right = st.columns([1, 1.8], gap="medium")
    with col_left: render_input_form()
    with col_right:
        render_dashboard_box(balance, total_thu, total_chi)
        pc_tab1, pc_tab2, pc_tab3 = st.tabs(["👁️ Sổ Quỹ", "📝 Lịch Sử", "📥 Xuất File"])
        with pc_tab1: render_report_table(df)
        with pc_tab2: render_history_list(df)
        with pc_tab3: render_export(df)
else:
    render_dashboard_box(balance, total_thu, total_chi)
    m_tab1, m_tab2, m_tab3, m_tab4 = st.tabs(["➕ NHẬP", "📝 LỊCH SỬ", "👁️ SỔ QUỸ", "📥 XUẤT"])
    with m_tab1: render_input_form()
    with m_tab2: render_history_list(df)
    with m_tab3: render_report_table(df)
    with m_tab4: render_export(df)
