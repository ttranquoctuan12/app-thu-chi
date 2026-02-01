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

# --- 2. CSS TỐI ƯU ---
st.markdown("""
<style>
    /* 1. Cấu hình lề trang */
    .block-container { 
        padding-top: 1rem !important; 
        padding-bottom: 3rem !important; 
        padding-left: 0.5rem !important; 
        padding-right: 0.5rem !important; 
    }

    /* 2. ẨN CÁC THÀNH PHẦN HỆ THỐNG */
    header { background-color: transparent !important; }
    [data-testid="stSidebarCollapsedControl"] { display: block !important; visibility: visible !important; z-index: 999999; color: #333; }
    
    [data-testid="stDecoration"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stHeaderActionElements"] { display: none !important; }
    .stAppDeployButton { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    footer { display: none !important; }
    #MainMenu { display: none !important; }

    /* 3. TÊN RIÊNG (GÓC PHẢI) */
    .custom-header-name {
        position: fixed; top: 0; right: 0; width: 100%; height: 40px;
        background-color: rgba(255, 255, 255, 0.9); z-index: 99999;
        border-bottom: 1px solid #eee; display: flex; align-items: center; justify-content: flex-end; padding-right: 15px;
    }
    .custom-name-text {
        font-family: 'Segoe UI', sans-serif; font-weight: 600; font-size: 0.85rem;
        color: #1565C0; background-color: #f0f7ff; padding: 4px 12px; border-radius: 12px;
        pointer-events: none; user-select: none;
    }

    /* 4. GIAO DIỆN APP */
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
<div class="custom-header-name"><span class="custom-name-text">TUẤN VDS.HCM</span></div>
""", unsafe_allow_html=True)

# --- KẾT NỐI API (TỐI ƯU CACHE RESOURCE) ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource # <--- Cache kết nối (Chỉ chạy 1 lần)
def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

@st.cache_resource # <--- Cache client Gspread (Chỉ chạy 1 lần)
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
    # Tính toán trên bản sao để không ảnh hưởng dữ liệu gốc
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
            worksheet.write(r, 4, "" if loai=='Open' else row['SoTienShow'], m_fmt)
            worksheet.write(r, 5, bal, bal_fmt)
            
        l_row = len(df_report) + 1
        fin_bal = df_report['ConLai'].iloc[-1] if not df_report.empty else 0
        fmt_tot = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFF00', 'font_size': 12})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'font_size': 12})
        worksheet.merge_range(l_row, 0, l_row, 4, "TỔNG SỐ DƯ CUỐI KỲ", fmt_tot)
        worksheet.write(l_row, 5, fin_bal, fmt_tot_v)
    return output.getvalue()

# --- DRIVE & CRUD (TỐI ƯU CACHE DATA) ---
def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

@st.cache_data(ttl=300) # <--- Tự động làm mới dữ liệu sau 300 giây (5 phút) nếu không có thao tác
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

# --- HÀM CLEAR CACHE KHI CÓ THAY ĐỔI ---
def clear_data_cache():
    st.cache_data.clear()

def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link])
    clear_data_cache() # <--- Xóa cache ngay sau khi thêm

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    r = int(row_idx)
    sheet.update(f"A{r}:E{r}", [[date.strftime('%Y-%m-%d'), category, int(amount), auto_capitalize(description), image_link]])
    clear_data_cache() # <--- Xóa cache sau khi sửa

def delete_transaction(row_idx):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(int(row_idx))
    clear_data_cache() # <--- Xóa cache sau khi xóa

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
        d_amount = st.number_input("Số tiền", min_value=0, step=5000, value=st.session_state.new_amount, key="a_new", label_visibility="collapsed")
        st.write("📝 **Nội dung:**")
        d_desc = st.text_input("Mô tả", value=st.session_state.new_desc, key="desc_new", placeholder="VD: Ăn sáng...", label_visibility="collapsed")
        
        st.markdown("<br><b>📷 Hình ảnh</b>", unsafe_allow_html=True)
        cam_mode = st.toggle("Dùng Camera", value=False)
        img_data = None
        if cam_mode: img_data = st.camera_input("Chụp ảnh", key="cam_new", label_visibility="collapsed")
        else: img_data = st.file_uploader("Tải ảnh", type=['jpg','png','jpeg'], key="up_new")

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
</div>
""", unsafe_allow_html=True)

def render_report_table(df):
    if df.empty: st.info("Chưa có dữ liệu."); return
    today = datetime.now(); d30 = today - timedelta(days=30)
    col_d1, col_d2 = st.columns(2)
    start_d = col_d1.date_input("Từ ngày", value=d30, key="v_start")
    end_d = col_d2.date_input("Đến ngày", value=today, key="v_end")
    
    # Process data with simple logic first to avoid blocking UI
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
        if not row_to_edit.empty
