import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
from io import BytesIO

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi + Ảnh", page_icon="📸", layout="centered")

# --- KẾT NỐI ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_creds():
    s_info = st.secrets["gcp_service_account"]
    return Credentials.from_service_account_info(s_info, scopes=SCOPES)

def get_gs_client():
    creds = get_creds()
    return gspread.authorize(creds)

# --- HÀM UPLOAD ẢNH LÊN DRIVE ---
def upload_image_to_drive(image_file, file_name):
    """Upload ảnh lên folder Drive và trả về link"""
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]

        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        
        # Chuẩn bị file để upload
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        
        # Thực hiện upload
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"Lỗi upload ảnh: {e}")
        return ""

# --- HÀM LƯU SHEET ---
def save_to_sheet(date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    date_str = date.strftime('%Y-%m-%d')
    # Lưu 5 cột: Ngày, Loại, Tiền, Mô tả, Link Ảnh
    sheet.append_row([date_str, category, int(amount), description, image_link])

def load_data():
    try:
        client = get_gs_client()
        sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame(columns=['Ngay', 'Loai', 'SoTien', 'MoTa', 'HinhAnh'])
        df = pd.DataFrame(data)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        return df
    except:
        return pd.DataFrame(columns=['Ngay', 'Loai', 'SoTien', 'MoTa', 'HinhAnh'])

# --- GIAO DIỆN ---
st.title("📸 Thu Chi & Lưu Hóa Đơn")

# Reset form
if 'in_tien' not in st.session_state: st.session_state.in_tien = 0
if 'in_mota' not in st.session_state: st.session_state.in_mota = ""

# 1. NHẬP LIỆU & CHỤP ẢNH
with st.container(border=True):
    st.subheader("1. Thông Tin & Hóa Đơn")
    
    col1, col2 = st.columns(2)
    with col1:
        date_val = st.date_input("Ngày", datetime.now())
        type_val = st.selectbox("Loại", ["Chi", "Thu"])
    with col2:
        amount_val = st.number_input("Số tiền", min_value=0, step=1000, value=st.session_state.in_tien)
    
    desc_val = st.text_input("Mô tả", value=st.session_state.in_mota)
    
    # Phần chụp ảnh
    st.markdown("---")
    st.caption("Đính kèm hình ảnh (Không bắt buộc)")
    img_option = st.radio("Chọn nguồn ảnh:", ["Không có", "Chụp ảnh", "Tải ảnh"], horizontal=True)
    
    image_data = None
    if img_option == "Chụp ảnh":
        image_data = st.camera_input("Chụp hóa đơn")
    elif img_option == "Tải ảnh":
        image_data = st.file_uploader("Chọn ảnh từ máy", type=['jpg', 'png', 'jpeg'])

    # Nút Lưu
    if st.button("Lưu Giao Dịch", type="primary", use_container_width=True):
        if amount_val > 0:
            link_anh = ""
            
            # Xử lý upload ảnh nếu có
            if image_data:
                with st.spinner("Đang tải ảnh lên Drive..."):
                    # Tạo tên file: YYYY-MM-DD_MoTa.jpg
                    file_name = f"{date_val.strftime('%Y-%m-%d')}_{desc_val}.jpg"
                    link_anh = upload_image_to_drive(image_data, file_name)
            
            # Lưu vào Sheet
            with st.spinner("Đang lưu dữ liệu..."):
                save_to_sheet(date_val, type_val, amount_val, desc_val, link_anh)
            
            st.success("✅ Đã lưu thành công!")
            st.session_state.in_tien = 0
            st.session_state.in_mota = ""
            st.rerun()
        else:
            st.warning("Số tiền phải lớn hơn 0")

# 2. DANH SÁCH GIAO DỊCH
st.divider()
st.subheader("📊 Danh Sách")

df = load_data()
if not df.empty:
    df = df.sort_values(by='Ngay', ascending=False)
    
    # Hiển thị bảng có cột Link Ảnh
    # Chúng ta dùng cấu hình cột của Streamlit để hiển thị Link dạng click được
    st.dataframe(
        df,
        column_config={
            "HinhAnh": st.column_config.LinkColumn("Hóa Đơn", display_text="Xem ảnh"),
            "SoTien": st.column_config.NumberColumn("Số Tiền", format="%d đ"),
            "Ngay": st.column_config.DateColumn("Ngày", format="DD/MM/YYYY"),
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Chưa có dữ liệu")
