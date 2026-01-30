import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import time

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="centered")

# --- KẾT NỐI GOOGLE APIS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_creds():
    """Lấy thông tin xác thực từ Secrets"""
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

def get_gs_client():
    """Kết nối Google Sheets"""
    return gspread.authorize(get_creds())

# --- HÀM FORMAT TIỀN VIỆT (DẤU CHẤM) ---
def format_vnd(amount):
    """Chuyển số 100000 thành chuỗi 100.000"""
    if pd.isna(amount): return "0"
    return "{:,.0f}".format(amount).replace(",", ".")

# --- HÀM UPLOAD ẢNH LÊN GOOGLE DRIVE ---
def upload_image_to_drive(image_file, file_name):
    """Upload ảnh và trả về link xem"""
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        # Lấy ID thư mục từ cấu hình Secrets
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        
        file_metadata = {'name': file_name, 'parents': [folder_id]}
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

# --- CÁC HÀM XỬ LÝ DỮ LIỆU (CRUD) ---
def load_data_with_index():
    """Tải dữ liệu kèm số dòng để sửa/xóa"""
    try:
        client = get_gs_client()
        sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        # Row Index bắt đầu từ 2 (do dòng 1 là tiêu đề)
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        # Chuyển tiền sang số nguyên để tính toán
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype(int)
        return df
    except:
        return pd.DataFrame()

def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([
        date.strftime('%Y-%m-%d'), 
        category, 
        int(amount), 
        description, 
        image_link
    ])

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    # Cập nhật range A:E tại dòng chỉ định
    sheet.update(
        f"A{row_idx}:E{row_idx}", 
        [[date.strftime('%Y-%m-%d'), category, int(amount), description, image_link]]
    )

def delete_transaction(row_idx):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.delete_rows(row_idx)

# ================= GIAO DIỆN CHÍNH =================
st.title("💎 Quản Lý Thu Chi")

# 1. TẢI DỮ LIỆU & TÍNH TOÁN DASHBOARD
df = load_data_with_index()

total_thu = 0
total_chi = 0
balance = 0

if not df.empty:
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum()
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum()
    balance = total_thu - total_chi

# Hiển thị Dashboard Số Dư (Canh giữa, Tô màu, Chữ to)
text_color = "#2ecc71" if balance >= 0 else "#e74c3c" # Xanh hoặc Đỏ
balance_str = f"{format_vnd(balance)} VNĐ"
thu_str = format_vnd(total_thu)
chi_str = format_vnd(total_chi)

st.markdown(f"""
    <div style="text-align: center; padding: 20px; border-radius: 15px; background-color: #f0f2f6; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h3 style="margin: 0; color: #555;">💰 SỐ DƯ HIỆN TẠI</h3>
        <h1 style="margin: 10px 0; font-size: 50px; font-weight: bold; color: {text_color};">
            {balance_str}
        </h1>
        <div style="display: flex; justify-content: center; gap: 30px; font-size: 18px;">
            <span style="color: #27ae60;">⬇️ Tổng Thu: <b>{thu_str}</b></span>
            <span style="color: #c0392b;">⬆️ Tổng Chi: <b>{chi_str}</b></span>
        </div>
    </div>
""", unsafe_allow_html=True)

# 2. CẤU TRÚC 3 TAB
tab1, tab2, tab3 = st.tabs(["➕ Nhập Mới", "🛠️ Sửa / Xóa", "📋 Danh Sách"])

# --- TAB 1: NHẬP MỚI ---
with tab1:
    with st.container(border=True):
        # Session state để reset form
        if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
        if 'new_desc' not in st.session_state: st.session_state.new_desc = ""

        c1, c2 = st.columns(2)
        d_date = c1.date_input("Ngày giao dịch", datetime.now(), key="d_new")
        d_type = c2.selectbox("Loại giao dịch", ["Chi", "Thu"], key="t_new")
        
        # Nhập số tiền
        d_amount = st.number_input("Số tiền (VNĐ)", min_value=0, step=1000, value=st.session_state.new_amount, key="a_new")
        
        # Nhập mô tả (Full width)
        d_desc = st.text_input("Nội dung / Mô tả (Bắt buộc)", value=st.session_state.new_desc, key="desc_new", placeholder="VD: Tiền xăng, Ăn trưa...")
        
        # Upload ảnh
        st.caption("Hình ảnh chứng từ (Tùy chọn)")
        img_opt = st.radio("Nguồn ảnh:", ["Không", "Chụp ảnh", "Tải ảnh"], horizontal=True, key="img_new_opt")
        img_data = None
        if img_opt == "Chụp ảnh": img_data = st.camera_input("Camera", key="cam_new")
        elif img_opt == "Tải ảnh": img_data = st.file_uploader("Upload", type=['jpg','png','jpeg'], key="up_new")

        # Nút Lưu
        if st.button("Lưu Giao Dịch", type="primary", use_container_width=True):
            if d_amount > 0 and d_desc.strip() != "":
                with st.spinner("Đang lưu dữ liệu và tải ảnh lên Drive..."):
                    link = ""
                    if img_data:
                        # Tên file: YYYYMMDD_MoTa.jpg
                        fname = f"{d_date.strftime('%Y%m%d')}_{d_desc}.jpg"
                        link = upload_image_to_drive(img_data, fname)
                    
                    add_transaction(d_date, d_type, d_amount, d_desc, link)
                
                st.success("✅ Đã lưu thành công!")
                # Reset form
                st.session_state.new_amount = 0
                st.session_state.new_desc = ""
                time.sleep(1)
                st.rerun()
            elif d_amount <= 0:
                st.warning("⚠️ Số tiền phải lớn hơn 0")
            elif d_desc.strip() == "":
                st.warning("⚠️ Vui lòng nhập nội dung mô tả")

# --- TAB 2: SỬA / XÓA ---
with tab2:
    if not df.empty:
        # Tạo Label hiển thị thông minh: Ngày - Mô Tả - Tiền (đã format)
        df['Label'] = df.apply(lambda x: f"{x['Ngay'].strftime('%d/%m')} - {x['MoTa']} ({format_vnd(x['SoTien'])})", axis=1)
        
        df_sorted = df.sort_values(by='Ngay', ascending=False)
        
        st.write("🔍 **Tìm giao dịch cần sửa:**")
        selected_label = st.selectbox("Chọn từ danh sách", df_sorted['Label'].tolist())
        
        # Lấy dòng dữ liệu tương ứng
        selected_row = df_sorted[df_sorted['Label'] == selected_label].iloc[0]
        
        st.divider()
        st.info(f"Đang thao tác: **{selected_row['MoTa']}**")
        
        with st.form("edit_form"):
            col_e1, col_e2 = st.columns(2)
            e_date = col_e1.date_input("Ngày", value=selected_row['Ngay'])
            
            # Chọn đúng index cho loại
            type_idx = 0 if selected_row['Loai'] == "Chi" else 1
            e_type = col_e2.selectbox("Loại", ["Chi", "Thu"], index=type_idx)
            
            e_amount = st.number_input("Số tiền", min_value=0, step=1000, value=int(selected_row['SoTien']))
            e_desc = st.text_input("Nội dung / Mô tả", value=selected_row['MoTa'])
            
            # Giữ nguyên link ảnh cũ (tính năng đổi ảnh nâng cao có thể thêm sau)
            e_link = selected_row['HinhAnh'] 
            if e_link: st.caption(f"[Xem ảnh hiện tại]({e_link})")
            
            c_btn1, c_btn2 = st.columns(2)
            # Nút Cập nhật
            if c_btn1.form_submit_button("💾 Cập nhật", type="primary", use_container_width=True):
                update_transaction(selected_row['Row_Index'], e_date, e_type, e_amount, e_desc, e_link)
                st.success("Đã cập nhật!")
                time.sleep(1)
                st.rerun()
            
            # Nút Xóa
            if c_btn2.form_submit_button("🗑️ Xóa vĩnh viễn", type="secondary", use_container_width=True):
                delete_transaction(selected_row['Row_Index'])
                st.warning("Đã xóa!")
                time.sleep(1)
                st.rerun()
    else:
        st.info("Chưa có dữ liệu để chỉnh sửa.")

# --- TAB 3: DANH SÁCH ---
with tab3:
    if not df.empty:
        df_view = df.sort_values(by='Ngay', ascending=False).copy()
        
        # Tạo cột hiển thị tiền dạng Text (để giữ dấu chấm)
        df_view['SoTien_HienThi'] = df_view['SoTien'].apply(lambda x: format_vnd(x) + " đ")
        
        # Cấu hình bảng
        st.dataframe(
            df_view,
            column_config={
                "HinhAnh": st.column_config.LinkColumn("Ảnh", display_text="Xem"),
                "SoTien_HienThi": st.column_config.TextColumn("Số Tiền"), # Dùng TextColumn
                "Ngay": st.column_config.DateColumn("Ngày", format="DD/MM/YYYY"),
                "MoTa": st.column_config.TextColumn("Nội dung", width="medium"), # Rộng hơn
                "Loai": st.column_config.TextColumn("Loại", width="small")
            },
            # Thứ tự hiển thị cột tối ưu
            column_order=["Ngay", "MoTa", "SoTien_HienThi", "Loai", "HinhAnh"],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Chưa có dữ liệu.")
