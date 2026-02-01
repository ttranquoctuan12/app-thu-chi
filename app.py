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

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="wide")

# --- 2. CSS TỐI ƯU (CHẾ ĐỘ ẨN TUYỆT ĐỐI) ---
st.markdown("""
<style>
    /* 1. ĐIỀU CHỈNH LỀ TRANG */
    .block-container { 
        padding-top: 1.5rem !important; 
        padding-bottom: 3rem !important; 
        padding-left: 0.5rem !important; 
        padding-right: 0.5rem !important; 
    }

    /* 2. ẨN TOÀN BỘ HEADER VÀ TOOLBAR (KHU VỰC CHỨA NÚT FORK/GITHUB) */
    
    /* Ẩn thẻ Header chính */
    header {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
    }
    
    /* Ẩn thanh công cụ (Toolbar) chứa các nút tác vụ */
    [data-testid="stToolbar"] {
        display: none !important;
        visibility: hidden !important;
        height: 0px !important;
    }
    
    /* Ẩn cụm nút hành động góc phải (Fork, Menu, v.v...) */
    [data-testid="stHeaderActionElements"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* Ẩn thanh trang trí màu sắc trên cùng */
    [data-testid="stDecoration"] {
        display: none !important;
        visibility: hidden !important;
    }

    /* 3. ẨN CÁC NÚT DEPLOY/MANAGE APP (KHU VỰC DƯỚI) */
    
    /* Ẩn nút Deploy (Vương miện/Tên lửa) */
    .stAppDeployButton, [data-testid="stAppDeployButton"] {
        display: none !important;
        visibility: hidden !important;
    }
    
    /* Ẩn Widget trạng thái (Người chạy/Dừng) */
    [data-testid="stStatusWidget"] {
        display: none !important;
        visibility: hidden !important;
    }
    
    /* Ẩn Menu chính (3 gạch) và Footer */
    #MainMenu { display: none !important; }
    footer { display: none !important; }

    /* 4. CHÈN TÊN RIÊNG "TUẤN VDS.HCM" */
    .custom-header-name {
        position: fixed;
        top: 0;
        right: 0;
        width: 100%; /* Trải dài toàn màn hình */
        height: 45px; /* Chiều cao cố định */
        background-color: white; /* Nền trắng che hết phần Header cũ */
        z-index: 99999999; /* Lớp cao nhất đè lên tất cả */
        border-bottom: 1px solid #eee;
        display: flex;
        align-items: center;
        justify-content: flex-end; /* Căn phải */
        padding-right: 20px;
    }
    
    .custom-name-text {
        font-family: 'Source Sans Pro', sans-serif;
        font-weight: 700;
        font-size: 1.1rem;
        color: #1565C0;
        background-color: #f0f7ff;
        padding: 5px 15px;
        border-radius: 20px;
        pointer-events: none; /* Không thể bấm */
        user-select: none;
    }

    /* 5. GIAO DIỆN APP */
    [data-testid="stCameraInput"] { width: 100% !important; }
    [data-testid="stCameraInput"] video { width: 100% !important; border-radius: 12px; border: 2px solid #eee; }
    .balance-box { padding: 15px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e0e0e0; margin-bottom: 20px; text-align: center; }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; }
    .history-row { padding: 8px 0; border-bottom: 1px solid #eee; }
    .desc-text { font-weight: 600; font-size: 1rem; color: #333; margin-bottom: 2px; }
    .date-text { font-size: 0.8rem; color: #888; }
    .amt-text { font-weight: bold; font-size: 1rem; }
    .stTextInput input, .stNumberInput input { font-weight: bold; }
    button[kind="secondary"] { padding: 0.25rem 0.5rem; border: 1px solid #eee; }
</style>

<div class="custom-header-name">
    <span class="custom-name-text">TUẤN VDS.HCM</span>
</div>
""", unsafe_allow_html=True)

# --- KẾT NỐI API ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
def get_gs_client():
    return gspread.authorize(get_creds())

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
    def get_date_str(row):
        if row['Loai'] == 'Open' or pd.isna(row['Ngay']): return "" 
        return row['Ngay'].strftime('%d/%m/%Y')
    df_proc['NgayChi'] = df_proc.apply(lambda x: get_date_str(x) if x['Loai'] == 'Chi' else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: get_date_str(x) if x['Loai'] == 'Thu' else "", axis=1)
    df_proc['SoTienShow'] = df_proc.apply(lambda x: x['SoTien'] if x['Loai'] != 'Open' else 0, axis=1)

    return df_proc[['STT', 'Khoan', 'NgayChi', 'NgayNhan', 'SoTienShow', 'ConLai', 'Loai']]

# --- EXCEL CUSTOM ---
def convert_df_to_excel_custom(df_report):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFFFF'})
        fmt_normal = workbook.add_format({'border': 1})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        fmt_thu_bg = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True})
        fmt_thu_money = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'num_format': '#,##0'})
        fmt_open_bg = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'bold': True})
        fmt_open_money = workbook.add_format({'border': 1, 'bg_color': '#E0E0E0', 'italic': True, 'bold': True, 'num_format': '#,##0'})
        fmt_red = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_color': 'red', 'bold': True})
        fmt_orange = workbook.add_format({'border': 1, 'num_format': '#,##0', 'bg_color': '#FF9900', 'bold': True})
        
        worksheet = workbook.add_worksheet("SoQuy")
        headers = ["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): worksheet.write(0, c, h, fmt_header)
        worksheet.set_column('B:B', 35); worksheet.set_column('E:F', 15)

        for i, row in df_report.iterrows():
            r = i + 1
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
            
        l_row = len(df_report) + 1
        fin_bal = df_report['ConLai'].iloc[-1] if not df_report.empty else 0
        fmt_tot = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFF00', 'font_size': 12})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'font_size': 12})
        worksheet.merge_range(l_row, 0, l_row, 4, "TỔNG SỐ DƯ CUỐI KỲ", fmt_tot)
        worksheet.write(l_row, 5, fin_bal, fmt_tot_v)
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

def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link])

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    r = int(row_idx)
    sheet.update(f"A{r}:E{r}", [[date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link]])

def delete_transaction(row_idx):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(int(row_idx))

# ==================== VIEW MODULES ====================

def render_input_form():
    with st.container(border=True):
        st.subheader("➕ Nhập Giao Dịch")
        if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
        if 'new_desc' not in st.session_state: st.session_state.new_desc = ""

        c1, c2 = st.columns([1.5, 1])
        d_date = c1.date_input("Ngày", datetime.now(), key="d_new", label_visibility="collapsed")
        d_type = c2.selectbox("Loại", ["Chi", "Thu"], key="t_new", label_visibility="collapsed")
        
        st.write("💰 **Số tiền:**")
        d_amount = st.number_input("Số tiền", min_value=0, step=5000, value=st.session_state.new_amount, key="a_
