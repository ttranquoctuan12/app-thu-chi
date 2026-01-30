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

# --- 1. CẤU HÌNH TRANG (Mobile Optimization) ---
st.set_page_config(page_title="Sổ Thu Chi Mobile", page_icon="📱", layout="wide")

# --- 2. CSS TỐI ƯU GIAO DIỆN & CAMERA FULL WIDTH ---
st.markdown("""
<style>
    /* 1. Thu nhỏ lề trang web tối đa */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    
    /* Ẩn menu Streamlit thừa */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 2. TỐI ƯU CAMERA FULL MÀN HÌNH (QUAN TRỌNG) */
    /* Buộc khung camera mở rộng 100% chiều ngang */
    [data-testid="stCameraInput"] {
        width: 100% !important;
    }
    /* Chỉnh video bên trong cho đẹp */
    [data-testid="stCameraInput"] video {
        width: 100% !important;   /* Tràn viền */
        border-radius: 12px;      /* Bo góc */
        object-fit: cover;        /* Lấp đầy khung */
        border: 2px solid #eee;   /* Viền nhẹ */
    }
    /* Nút "Take Photo" to ra cho dễ bấm */
    button[kind="primary"] {
        width: 100% !important;
        height: 3rem !important;
        font-weight: bold !important;
    }

    /* Style số dư */
    .balance-box {
        padding: 15px; 
        border-radius: 15px; 
        background-color: #f8f9fa; 
        border: 1px solid #e0e0e0;
        margin-bottom: 15px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .balance-text { font-size: 2.2rem !important; font-weight: 800; margin: 0; }
    
    /* Style Card giao dịch */
    .trans-card-date { color: #666; font-size: 0.85rem; }
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

# --- LOGIC XUẤT EXCEL ---
def get_settlement_data(df):
    df_calc = df.sort_values(by=['Ngay', 'Row_Index'], ascending=[True, True]).copy()
    df_calc['SignedAmount'] = df_calc.apply(lambda x: x['SoTien'] if x['Loai'] == 'Thu' else -x['SoTien'], axis=1)
    df_calc['RunningBalance'] = df_calc['SignedAmount'].cumsum()
    current_balance = df_calc['RunningBalance'].iloc[-1] if not df_calc.empty else 0
    
    if current_balance == 0:
        return df_calc[df_calc['Loai'] == 'Thu'].copy()
    else:
        zero_points = df_calc.index[df_calc['RunningBalance'] == 0].tolist()
        if zero_points:
            last_zero_index = zero_points[-1]
            df_temp = df_calc.reset_index(drop=True)
            locs = df_temp.index[df_temp['RunningBalance'] == 0].tolist()
            return df_temp.iloc[locs[-1] + 1 : ].copy()
        else:
            return df_calc.copy()

def get_history_data(df, start_date, end_date):
    mask = (df['Ngay'].dt.date >= start_date) & (df['Ngay'].dt.date <= end_date)
    return df.loc[mask].sort_values(by='Ngay', ascending=True).copy()

def convert_df_to_excel(df, sheet_name="BaoCao"):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export = df.copy()
        if 'Ngay' in df_export.columns: df_export['Ngay'] = df_export['Ngay'].dt.strftime('%d/%m/%Y')
        if 'MoTa' in df_export.columns: df_export['MoTa'] = df_export['MoTa'].apply(auto_capitalize)

        cols_to_keep = ['Ngay', 'Loai', 'SoTien', 'MoTa', 'HinhAnh']
        cols_final = [c for c in cols_to_keep if c in df_export.columns]
        df_final = df_export[cols_final]
        
        rename_map = {'Ngay': 'NGÀY', 'Loai': 'LOẠI', 'SoTien': 'SỐ TIỀN', 'MoTa': 'MÔ TẢ', 'HinhAnh': 'HÌNH ẢNH'}
        df_final.rename(columns=rename_map, inplace=True)
        df_final.to_excel(writer, index=False, sheet_name=sheet_name)
        
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1, 'align': 'center'})
        for col_num, value in enumerate(df_final.columns.values): worksheet.write(0, col_num, value, header_fmt)
        worksheet.set_column('A:E', 20)
    return output.getvalue()

# --- DRIVE UPLOAD ---
def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except Exception as e: return ""

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
    final_desc = auto_capitalize(description)
    sheet.append_row([date.strftime('%Y-%m-%d'), category, int(amount), final_desc, image_link])

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    r_idx = int(row_idx)
    final_desc = auto_capitalize(description)
    sheet.update(f"A{r_idx}:E{r_idx}", [[date.strftime('%Y-%m-%d'), category, int(amount), final_desc, image_link]])

def delete_transaction(row_idx):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(int(row_idx))

# ================= GIAO DIỆN CHÍNH =================

df = load_data_with_index()

total_thu = 0
total_chi = 0
balance = 0
if not df.empty:
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum()
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum()
    balance = total_thu - total_chi

# --- DASHBOARD ---
text_color = "#2ecc71" if balance >= 0 else "#e74c3c"
st.markdown(f"""
    <div class="balance-box">
        <div style="color: #888; font-size: 0.9rem; text-transform: uppercase;">Số dư hiện tại</div>
        <div class="balance-text" style="color: {text_color};">{format_vnd(balance)}</div>
        <div style="display: flex; justify-content: space-between; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
            <div style="color: #27ae60; font-weight: bold;">⬇️ {format_vnd(total_thu)}</div>
            <div style="color: #c0392b; font-weight: bold;">⬆️ {format_vnd(total_chi)}</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["➕ NHẬP", "📝 LỊCH SỬ", "📤 BÁO CÁO"])

# ================= TAB 1: NHẬP MỚI =================
with tab1:
    if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
    if 'new_desc' not in st.session_state: st.session_state.new_desc = ""

    # FORM NHẬP LIỆU
    c1, c2 = st.columns([1.5, 1])
    d_date = c1.date_input("Ngày", datetime.now(), key="d_new", label_visibility="collapsed")
    d_type = c2.selectbox("Loại", ["Chi", "Thu"], key="t_new", label_visibility="collapsed")
    
    st.write("💰 **Số tiền:**")
    d_amount = st.number_input("Số tiền", min_value=0, step=5000, value=st.session_state.new_amount, key="a_new", label_visibility="collapsed")
    
    st.write("📝 **Nội dung:**")
    d_desc = st.text_input("Mô tả", value=st.session_state.new_desc, key="desc_new", placeholder="VD: Ăn sáng...", label_visibility="collapsed")
    
    # -----------------------------------------------------------
    # PHẦN CAMERA ĐƯỢC MỞ RỘNG (Đặt ngoài Expander để dễ thấy)
    # -----------------------------------------------------------
    st.markdown("<br><b>📷 Chụp Hóa Đơn (Full Width)</b>", unsafe_allow_html=True)
    
    # Logic chuyển đổi giữa Camera và Upload để đỡ rối
    cam_mode = st.toggle("Dùng Camera", value=True)
    
    img_data = None
    if cam_mode:
        # Camera Input: label_visibility="collapsed" để ẩn chữ, CSS sẽ làm nó full width
        img_data = st.camera_input("Chụp ảnh", key="cam_new", label_visibility="collapsed")
    else:
        img_data = st.file_uploader("Tải ảnh lên", type=['jpg','png','jpeg'], key="up_new")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # NÚT LƯU TO ĐÙNG
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
        else:
            st.warning("Nhập Tiền & Nội dung!")

# ================= TAB 2: DANH SÁCH =================
with tab2:
    if not df.empty:
        if 'edit_row_index' not in st.session_state: st.session_state.edit_row_index = None
        
        # FORM SỬA
        if st.session_state.edit_row_index is not None:
            row_to_edit = df[df['Row_Index'] == st.session_state.edit_row_index]
            if not row_to_edit.empty:
                row_data = row_to_edit.iloc[0]
                with st.container(border=True):
                    st.info("✏️ Đang chỉnh sửa")
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
                st.divider()

        # LIST VIEW
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

                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("Sửa", key=f"btn_e_{row['Row_Index']}", use_container_width=True):
                    st.session_state.edit_row_index = row['Row_Index']
                    st.rerun()
                if c_btn2.button("Xóa", key=f"btn_d_{row['Row_Index']}", use_container_width=True):
                    delete_transaction(row['Row_Index'])
                    st.toast("Đã xóa!")
                    time.sleep(0.5)
                    st.rerun()
    else: st.info("Trống.")

# ================= TAB 3: BÁO CÁO =================
with tab3:
    st.write("📊 **Xuất Excel**")
    if not df.empty:
        mode = st.radio("Chế độ:", ["Quyết Toán (Thông minh)", "Lịch Sử (Theo ngày)"])
        if "Quyết Toán" in mode:
            if st.button("Tải File Quyết Toán", type="primary", use_container_width=True):
                df_export = get_settlement_data(df)
                fname = f"Quyet_toan_{datetime.now().strftime('%d%m_%H%M')}.xlsx"
                data = convert_df_to_excel(df_export, "QuyetToan")
                st.download_button("⬇️ BẤM ĐỂ TẢI", data, fname, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        else:
            c1, c2 = st.columns(2)
            d1 = c1.date_input("Từ", datetime.now().replace(day=1))
            d2 = c2.date_input("Đến", datetime.now())
            if st.button("Tải File Lịch Sử", type="primary", use_container_width=True):
                df_hist = get_history_data(df, d1, d2)
                fname = f"Lich_su_{d1.strftime('%d%m')}_{d2.strftime('%d%m')}.xlsx"
                data = convert_df_to_excel(df_hist, "LichSu")
                st.download_button("⬇️ BẤM ĐỂ TẢI", data, fname, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
    else: st.info("Trống.")
