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

# --- 1. CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="wide")

# --- 2. CSS TỐI ƯU ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; padding-left: 1rem !important; padding-right: 1rem !important; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    
    /* Camera Full Width */
    [data-testid="stCameraInput"] { width: 100% !important; }
    [data-testid="stCameraInput"] video { width: 100% !important; border-radius: 12px; border: 2px solid #eee; }
    
    /* Balance Box */
    .balance-box { padding: 15px; border-radius: 12px; background-color: #f8f9fa; border: 1px solid #e0e0e0; margin-bottom: 15px; text-align: center; }
    .balance-text { font-size: 2rem !important; font-weight: 800; margin: 0; }
    
    /* Card & Table */
    .trans-card-date { color: #666; font-size: 0.85rem; }
    div[data-testid="stDataFrame"] { width: 100%; }
    
    /* Input Form Styling */
    .stTextInput input, .stNumberInput input { font-weight: bold; }
</style>
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

# --- XỬ LÝ DỮ LIỆU ---
def process_report_data(df, start_date=None, end_date=None):
    if start_date and end_date:
        mask = (df['Ngay'].dt.date >= start_date) & (df['Ngay'].dt.date <= end_date)
        df_proc = df.loc[mask].copy()
    else:
        df_proc = df.copy()

    if df_proc.empty: return pd.DataFrame()

    df_proc = df_proc.sort_values(by=['Ngay', 'Row_Index'], ascending=[True, True])
    df_proc['SignedAmount'] = df_proc.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_proc['ConLai'] = df_proc['SignedAmount'].cumsum()

    df_proc['STT'] = range(1, len(df_proc) + 1)
    df_proc['Khoan'] = df_proc['MoTa'].apply(auto_capitalize)
    df_proc['NgayChi'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai'] == 'Chi' else "", axis=1)
    df_proc['NgayNhan'] = df_proc.apply(lambda x: x['Ngay'].strftime('%d/%m/%Y') if x['Loai'] == 'Thu' else "", axis=1)
    
    return df_proc[['STT', 'Khoan', 'NgayChi', 'NgayNhan', 'SoTien', 'ConLai', 'Loai']]

# --- EXCEL CUSTOM ---
def convert_df_to_excel_custom(df_report):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        # (Định dạng giữ nguyên như cũ - đã rút gọn code để tập trung vào layout)
        fmt_header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFFFF'})
        fmt_normal = workbook.add_format({'border': 1})
        fmt_money = workbook.add_format({'border': 1, 'num_format': '#,##0'})
        fmt_thu_bg = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True})
        fmt_thu_money = workbook.add_format({'border': 1, 'bg_color': '#FFFF00', 'bold': True, 'num_format': '#,##0'})
        fmt_red = workbook.add_format({'border': 1, 'num_format': '#,##0', 'font_color': 'red', 'bold': True})
        fmt_orange = workbook.add_format({'border': 1, 'num_format': '#,##0', 'bg_color': '#FF9900', 'bold': True})
        
        worksheet = workbook.add_worksheet("SoQuy")
        headers = ["STT", "Khoản", "Ngày chi", "Ngày Nhận", "Số tiền", "Còn lại"]
        for c, h in enumerate(headers): worksheet.write(0, c, h, fmt_header)
        worksheet.set_column('B:B', 30); worksheet.set_column('E:F', 15)

        for i, row in df_report.iterrows():
            r = i + 1
            is_thu = (row['Loai'] == 'Thu')
            bal = row['ConLai']
            
            c_fmt = fmt_thu_bg if is_thu else fmt_normal
            m_fmt = fmt_thu_money if is_thu else fmt_money
            if is_thu: bal_fmt = fmt_orange 
            else: bal_fmt = fmt_red if bal < 0 else fmt_money

            worksheet.write(r, 0, row['STT'], c_fmt)
            worksheet.write(r, 1, row['Khoan'], c_fmt)
            worksheet.write(r, 2, row['NgayChi'], c_fmt)
            worksheet.write(r, 3, row['NgayNhan'], c_fmt)
            worksheet.write(r, 4, row['SoTien'], m_fmt)
            worksheet.write(r, 5, bal, bal_fmt)
            
        # Tổng footer
        l_row = len(df_report) + 1
        fin_bal = df_report['ConLai'].iloc[-1] if not df_report.empty else 0
        fmt_tot = workbook.add_format({'bold': True, 'border': 1, 'align': 'center', 'bg_color': '#FFFF00', 'font_size': 12})
        fmt_tot_v = workbook.add_format({'bold': True, 'border': 1, 'bg_color': '#FF9900', 'num_format': '#,##0', 'font_size': 12})
        worksheet.merge_range(l_row, 0, l_row, 4, "TỔNG", fmt_tot)
        worksheet.write(l_row, 5, fin_bal, fmt_tot_v)
    return output.getvalue()

# --- DRIVE ---
def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body={'name': file_name, 'parents': [folder_id]}, media_body=media, fields='webViewLink').execute()
        return file.get('webViewLink')
    except: return ""

# --- CRUD ---
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

# ==================== PHẦN HIỂN THỊ (VIEW) ====================

def render_input_form():
    """Form nhập liệu dùng chung cho cả 2 giao diện"""
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
        
        st.markdown("<br><b>📷 Chụp Hóa Đơn</b>", unsafe_allow_html=True)
        cam_mode = st.toggle("Dùng Camera", value=True)
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
                st.session_state.new_amount = 0
                st.session_state.new_desc = ""
                time.sleep(0.5)
                st.rerun()
            else: st.warning("Thiếu thông tin!")

def render_dashboard_box(bal, thu, chi):
    """Hộp số dư dùng chung"""
    text_color = "#2ecc71" if bal >= 0 else "#e74c3c"
    st.markdown(f"""
        <div class="balance-box">
            <div style="color: #888; font-size: 0.9rem; text-transform: uppercase;">Số dư hiện tại</div>
            <div class="balance-text" style="color: {text_color};">{format_vnd(bal)}</div>
            <div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
                <div style="color: #27ae60; font-weight: bold;">⬇️ {format_vnd(thu)}</div>
                <div style="color: #c0392b; font-weight: bold;">⬆️ {format_vnd(chi)}</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

def render_report_table(df):
    """Bảng Sổ Quỹ dùng chung"""
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return

    # Bộ lọc
    col_d1, col_d2 = st.columns(2)
    start_d = col_d1.date_input("Từ ngày", datetime.now().replace(day=1), key="v_start")
    end_d = col_d2.date_input("Đến ngày", datetime.now(), key="v_end")
    
    df_report = process_report_data(df, start_d, end_d)
    
    if not df_report.empty:
        def highlight_rows(row):
            return ['background-color: #FFFF00; color: black; font-weight: bold'] * len(row) if row['Loai'] == 'Thu' else [''] * len(row)
        def color_negative_red(val):
            color = 'red' if isinstance(val, (int, float)) and val < 0 else 'black'
            return f'color: {color}'

        st.dataframe(
            df_report.style.apply(highlight_rows, axis=1).map(color_negative_red, subset=['ConLai']).format({"SoTien": "{:,.0f}", "ConLai": "{:,.0f}"}),
            column_config={
                "STT": st.column_config.NumberColumn("STT", width="small"),
                "Khoan": st.column_config.TextColumn("Khoản", width="large"),
                "NgayChi": st.column_config.TextColumn("Ngày chi"),
                "NgayNhan": st.column_config.TextColumn("Ngày Nhận"),
                "SoTien": st.column_config.NumberColumn("Số tiền"),
                "ConLai": st.column_config.NumberColumn("Còn lại"),
                "Loai": None
            },
            hide_index=True, use_container_width=True, height=500
        )
        final_bal = df_report['ConLai'].iloc[-1]
        st.markdown(f"<div style='background-color: #FFFF00; padding: 10px; text-align: right; font-weight: bold; font-size: 1.2rem; border: 1px solid #ddd;'>TỔNG CÒN LẠI: <span style='color: {'red' if final_bal < 0 else 'black'}'>{format_vnd(final_bal)}</span></div>", unsafe_allow_html=True)
    else: st.warning("Không có dữ liệu.")

def render_history_list(df):
    """Danh sách thẻ Card View"""
    if df.empty:
        st.info("Trống")
        return
    
    # Form sửa/xóa
    if 'edit_row_index' not in st.session_state: st.session_state.edit_row_index = None
    if st.session_state.edit_row_index is not None:
        row_to_edit = df[df['Row_Index'] == st.session_state.edit_row_index]
        if not row_to_edit.empty:
            row_data = row_to_edit.iloc[0]
            with st.container(border=True):
                st.info("✏️ Sửa giao dịch")
                ue1, ue2 = st.columns([1.5, 1])
                ud_date = ue1.date_input("Ngày", value=row_data['Ngay'], key="u_d")
                idx_type = 0 if row_data['Loai'] == "Chi" else 1
                ud_type = ue2.selectbox("Loại", ["Chi", "Thu"], index=idx_type, key="u_t")
                ud_amt = st.number_input("Tiền", value=int(row_data['SoTien']), step=1000, key="u_a")
                ud_desc = st.text_input("Mô tả", value=row_data['MoTa'], key="u_desc")
                b1, b2 = st.columns(2)
                if b1.button("Lưu", type="primary", use_container_width=True):
                    update_transaction(st.session_state.edit_row_index, ud_date, ud_type, ud_amt, ud_desc, row_data['HinhAnh'])
                    st.session_state.edit_row_index = None
                    st.rerun()
                if b2.button("Hủy", use_container_width=True):
                    st.session_state.edit_row_index = None
                    st.rerun()

    # Danh sách
    df_sorted = df.sort_values(by='Ngay', ascending=False)
    for index, row in df_sorted.iterrows():
        with st.container(border=True):
            col_info, col_amt = st.columns([2, 1])
            icon = "🟢" if row['Loai'] == 'Thu' else "🔴"
            money_color = "green" if row['Loai'] == 'Thu' else "red"
            with col_info:
                st.markdown(f"**{row['MoTa']}**")
                st.markdown(f"<span class='trans-card-date'>{icon} {row['Ngay'].strftime('%d/%m')}</span>", unsafe_allow_html=True)
            with col_amt:
                st.markdown(f"<div style='text-align:right; color:{money_color}; font-weight:bold'>{format_vnd(row['SoTien'])}</div>", unsafe_allow_html=True)
                if row['HinhAnh']: st.markdown(f"<div style='text-align:right'><a href='{row['HinhAnh']}' target='_blank'>Xem ảnh</a></div>", unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            if c1.button("Sửa", key=f"e_{row['Row_Index']}", use_container_width=True):
                st.session_state.edit_row_index = row['Row_Index']
                st.rerun()
            if c2.button("Xóa", key=f"d_{row['Row_Index']}", use_container_width=True):
                delete_transaction(row['Row_Index'])
                st.toast("Đã xóa")
                time.sleep(0.5)
                st.rerun()

def render_export_tab(df):
    """Tab xuất Excel"""
    st.write("📥 **Xuất file**")
    if not df.empty:
        c1, c2 = st.columns(2)
        d1 = c1.date_input("Từ", datetime.now().replace(day=1), key="ex_d1")
        d2 = c2.date_input("Đến", datetime.now(), key="ex_d2")
        if st.button("Tải Sổ Quỹ (Excel)", type="primary", use_container_width=True):
            df_rep = process_report_data(df, d1, d2)
            if df_rep.empty: st.warning("Không có dữ liệu")
            else:
                data = convert_df_to_excel_custom(df_rep)
                fname = f"SoQuy_{d1.strftime('%d%m')}_{d2.strftime('%d%m')}.xlsx"
                st.download_button("⬇️ TẢI NGAY", data, fname, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
    else: st.info("Trống")

# ==================== MAIN APP LOGIC ====================

# 1. LOAD DATA
df = load_data_with_index()
total_thu = 0; total_chi = 0; balance = 0
if not df.empty:
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum()
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum()
    balance = total_thu - total_chi

# 2. THANH CHUYỂN ĐỔI GIAO DIỆN (NẰM TRÊN CÙNG)
layout_mode = st.radio("Chế độ xem:", ["📱 Điện thoại (Tabs)", "💻 Laptop (Chia đôi)"], horizontal=True)
st.divider()

# 3. ĐIỀU HƯỚNG GIAO DIỆN
if "Laptop" in layout_mode:
    # --- GIAO DIỆN LAPTOP (SPLIT SCREEN) ---
    col_left, col_right = st.columns([1, 1.8], gap="medium") # Bên phải rộng hơn chút
    
    with col_left:
        # Cột Trái: Chỉ để nhập liệu
        render_input_form()
    
    with col_right:
        # Cột Phải: Xem báo cáo và lịch sử
        render_dashboard_box(balance, total_thu, total_chi)
        
        # Tabs con bên phải
        pc_tab1, pc_tab2, pc_tab3 = st.tabs(["👁️ Sổ Quỹ", "📝 Lịch Sử", "📥 Xuất File"])
        with pc_tab1: render_report_table(df)
        with pc_tab2: render_history_list(df)
        with pc_tab3: render_export_tab(df)

else:
    # --- GIAO DIỆN MOBILE (TABS TRUYỀN THỐNG) ---
    render_dashboard_box(balance, total_thu, total_chi)
    
    m_tab1, m_tab2, m_tab3, m_tab4 = st.tabs(["➕ NHẬP", "📝 LỊCH SỬ", "👁️ SỔ QUỸ", "📥 XUẤT"])
    
    with m_tab1: render_input_form()
    with m_tab2: render_history_list(df)
    with m_tab3: render_report_table(df)
    with m_tab4: render_export_tab(df)
