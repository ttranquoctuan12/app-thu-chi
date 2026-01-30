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

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="wide") # Layout wide để bảng rộng rãi hơn

# --- KẾT NỐI GOOGLE APIS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

def get_gs_client():
    return gspread.authorize(get_creds())

# --- HÀM TIỆN ÍCH ---
def remove_accents(input_str):
    """Chuyển tiếng việt có dấu thành không dấu"""
    if not isinstance(input_str, str): return str(input_str)
    s = unicodedata.normalize('NFD', input_str)
    s = "".join([c for c in s if unicodedata.category(c) != 'Mn'])
    return s.replace("đ", "d").replace("Đ", "D")

def auto_capitalize(text):
    """Viết hoa chữ cái đầu tiên"""
    if not text or not isinstance(text, str): return ""
    text = text.strip()
    if len(text) > 0:
        return text[0].upper() + text[1:]
    return text

def format_vnd(amount):
    """Format tiền có dấu chấm: 1.000.000"""
    if pd.isna(amount): return "0"
    return "{:,.0f}".format(amount).replace(",", ".")

# --- HÀM XUẤT EXCEL (CẬP NHẬT MỚI) ---
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export = df.copy()
        
        # 1. Xử lý dữ liệu trước khi xuất
        if 'Ngay' in df_export.columns:
            df_export['Ngay'] = df_export['Ngay'].dt.strftime('%d/%m/%Y')
        
        # Tự động viết hoa chữ cái đầu mô tả trong file Excel
        if 'MoTa' in df_export.columns:
            df_export['MoTa'] = df_export['MoTa'].apply(auto_capitalize)

        # 2. Chọn cột và Đổi tên cột (In Hoa, Tiếng Việt)
        cols_to_keep = ['Ngay', 'Loai', 'SoTien', 'MoTa', 'HinhAnh']
        cols_final = [c for c in cols_to_keep if c in df_export.columns]
        df_final = df_export[cols_final]
        
        rename_map = {
            'Ngay': 'NGÀY',
            'Loai': 'LOẠI',
            'SoTien': 'SỐ TIỀN',
            'MoTa': 'MÔ TẢ',
            'HinhAnh': 'HÌNH ẢNH'
        }
        df_final.rename(columns=rename_map, inplace=True)
        
        # 3. Xuất file
        df_final.to_excel(writer, index=False, sheet_name='QuyetToan')
        
        # 4. Format Excel
        workbook = writer.book
        worksheet = writer.sheets['QuyetToan']
        
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        cell_fmt = workbook.add_format({'border': 1, 'valign': 'top'})
        money_fmt = workbook.add_format({'border': 1, 'valign': 'top', 'num_format': '#,##0'})
        
        # Apply Header Format
        for col_num, value in enumerate(df_final.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            
        # Apply Column Width & Body Format
        worksheet.set_column('A:A', 15, cell_fmt) # Ngày
        worksheet.set_column('B:B', 10, cell_fmt) # Loại
        worksheet.set_column('C:C', 15, money_fmt) # Tiền
        worksheet.set_column('D:D', 40, cell_fmt) # Mô tả
        worksheet.set_column('E:E', 25, cell_fmt) # Ảnh
        
    return output.getvalue()

# --- HÀM UPLOAD DRIVE ---
def upload_image_to_drive(image_file, file_name):
    try:
        creds = get_creds()
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets["DRIVE_FOLDER_ID"]
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg')
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"Lỗi upload: {e}")
        return ""

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
    except:
        return pd.DataFrame()

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

# Load Data
df = load_data_with_index()

# Tính toán Dashboard
total_thu = 0
total_chi = 0
balance = 0
if not df.empty:
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum()
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum()
    balance = total_thu - total_chi

# CSS Tùy chỉnh (Giúp nút bấm đẹp hơn)
st.markdown("""
<style>
    div[data-testid="stMetricValue"] { font-size: 24px; }
    .big-font { font-size:30px !important; font-weight: bold; }
    button[kind="secondary"] { background-color: #f0f2f6; border: none; color: #ff4b4b; }
    button[kind="secondary"]:hover { color: #ff0000; background-color: #ffe6e6; }
</style>
""", unsafe_allow_html=True)

# --- DASHBOARD ---
text_color = "#2ecc71" if balance >= 0 else "#e74c3c"
st.markdown(f"""
    <div style="text-align: center; padding: 15px; border-radius: 12px; background-color: #f8f9fa; margin-bottom: 20px; border: 1px solid #ddd;">
        <h4 style="margin: 0; color: #666;">💰 SỐ DƯ HIỆN TẠI</h4>
        <h1 style="margin: 5px 0; font-size: 45px; color: {text_color};">{format_vnd(balance)} VNĐ</h1>
        <div style="display: flex; justify-content: center; gap: 40px;">
            <span style="color: #27ae60; font-weight: bold;">⬇️ Thu: {format_vnd(total_thu)}</span>
            <span style="color: #c0392b; font-weight: bold;">⬆️ Chi: {format_vnd(total_chi)}</span>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["➕ NHẬP MỚI", "🛠️ DANH SÁCH & SỬA/XÓA", "📥 XUẤT BÁO CÁO"])

# ================= TAB 1: NHẬP MỚI =================
with tab1:
    with st.container(border=True):
        if 'new_amount' not in st.session_state: st.session_state.new_amount = 0
        if 'new_desc' not in st.session_state: st.session_state.new_desc = ""

        c1, c2 = st.columns(2)
        d_date = c1.date_input("Ngày", datetime.now(), key="d_new")
        d_type = c2.selectbox("Loại", ["Chi", "Thu"], key="t_new")
        d_amount = st.number_input("Số tiền", min_value=0, step=1000, value=st.session_state.new_amount, key="a_new")
        d_desc = st.text_input("Mô tả (Bắt buộc)", value=st.session_state.new_desc, key="desc_new")
        
        st.caption("Hình ảnh (Tùy chọn)")
        img_opt = st.radio("Nguồn ảnh:", ["Không", "Chụp", "Tải"], horizontal=True, key="img_new_opt", label_visibility="collapsed")
        img_data = None
        if img_opt == "Chụp": img_data = st.camera_input("Camera", key="cam_new")
        elif img_opt == "Tải": img_data = st.file_uploader("Upload", type=['jpg','png','jpeg'], key="up_new")

        if st.button("Lưu Giao Dịch", type="primary", use_container_width=True):
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
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Vui lòng nhập Tiền > 0 và Mô tả.")

# ================= TAB 2: SỬA / XÓA (GIAO DIỆN MỚI) =================
with tab2:
    if not df.empty:
        # State để quản lý dòng đang sửa
        if 'edit_row_index' not in st.session_state: st.session_state.edit_row_index = None

        # Sắp xếp mới nhất lên đầu
        df_sorted = df.sort_values(by='Ngay', ascending=False)
        
        # --- KHUNG CHỈNH SỬA (Hiện ra khi bấm nút Sửa) ---
        if st.session_state.edit_row_index is not None:
            # Lấy dữ liệu dòng đang chọn
            row_to_edit = df[df['Row_Index'] == st.session_state.edit_row_index]
            if not row_to_edit.empty:
                row_data = row_to_edit.iloc[0]
                
                st.info(f"✏️ Đang sửa: **{row_data['MoTa']}** ({row_data['Ngay'].strftime('%d/%m')})")
                with st.container(border=True):
                    with st.form("update_form"):
                        ec1, ec2 = st.columns(2)
                        ud_date = ec1.date_input("Ngày", value=row_data['Ngay'])
                        idx_type = 0 if row_data['Loai'] == "Chi" else 1
                        ud_type = ec2.selectbox("Loại", ["Chi", "Thu"], index=idx_type)
                        ud_amt = st.number_input("Số tiền", min_value=0, step=1000, value=int(row_data['SoTien']))
                        ud_desc = st.text_input("Mô tả", value=row_data['MoTa'])
                        
                        # Nút Save / Cancel
                        cb1, cb2 = st.columns(2)
                        if cb1.form_submit_button("💾 Cập nhật", type="primary", use_container_width=True):
                            update_transaction(st.session_state.edit_row_index, ud_date, ud_type, ud_amt, ud_desc, row_data['HinhAnh'])
                            st.session_state.edit_row_index = None # Thoát chế độ sửa
                            st.success("Cập nhật xong!")
                            st.rerun()
                            
                        if cb2.form_submit_button("❌ Hủy bỏ", type="secondary", use_container_width=True):
                            st.session_state.edit_row_index = None
                            st.rerun()
                st.divider()

        # --- DANH SÁCH TOÀN BỘ (DẠNG BẢNG CÓ NÚT BẤM) ---
        st.write(f"**Danh sách giao dịch ({len(df)})**")
        
        # Tiêu đề bảng
        h1, h2, h3, h4, h5, h6 = st.columns([2, 1, 2, 4, 1, 2])
        h1.markdown("**Ngày**")
        h2.markdown("**Loại**")
        h3.markdown("**Số Tiền**")
        h4.markdown("**Mô Tả**")
        h5.markdown("**Ảnh**")
        h6.markdown("**Thao tác**")
        st.divider()

        # Lặp qua từng dòng để vẽ giao diện
        for index, row in df_sorted.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([2, 1, 2, 4, 1, 2], gap="small")
            
            c1.write(row['Ngay'].strftime('%d/%m/%Y'))
            
            # Tô màu loại
            if row['Loai'] == 'Thu':
                c2.markdown(f"<span style='color:green; font-weight:bold'>Thu</span>", unsafe_allow_html=True)
            else:
                c2.write("Chi")
                
            c3.write(f"**{format_vnd(row['SoTien'])}**")
            c4.write(row['MoTa'])
            
            if row['HinhAnh']:
                c5.markdown(f"[Xem]({row['HinhAnh']})")
            else:
                c5.write("-")
            
            # Nút thao tác
            with c6:
                bc1, bc2 = st.columns(2)
                # Nút Sửa
                if bc1.button("✏️", key=f"edit_{row['Row_Index']}", help="Sửa dòng này"):
                    st.session_state.edit_row_index = row['Row_Index']
                    st.rerun()
                
                # Nút Xóa
                if bc2.button("🗑️", key=f"del_{row['Row_Index']}", help="Xóa dòng này"):
                    delete_transaction(row['Row_Index'])
                    st.toast(f"Đã xóa: {row['MoTa']}")
                    time.sleep(1)
                    st.rerun()
            
            st.markdown("<hr style='margin: 5px 0; border-top: 1px dashed #eee;'>", unsafe_allow_html=True)

    else:
        st.info("Chưa có giao dịch nào.")

# ================= TAB 3: XUẤT EXCEL =================
with tab3:
    st.subheader("📥 Tải Báo Cáo")
    if not df.empty:
        # Tên file theo yêu cầu: "Quyết toán" + ngày tải + giờ tải
        # Lưu ý: Filename nên không dấu để an toàn, nhưng hiển thị vẫn hiểu được
        # Format: Quyet_toan_30012026_1730.xlsx
        
        current_time = datetime.now()
        file_name_download = f"Quyet_toan_{current_time.strftime('%d%m%Y_%H%M')}.xlsx"
        
        excel_data = convert_df_to_excel(df)
        
        col_dl1, col_dl2 = st.columns([2, 1])
        with col_dl1:
            st.info(f"Sẵn sàng tải xuống: **{file_name_download}**")
        with col_dl2:
            st.download_button(
                label="📥 TẢI FILE EXCEL",
                data=excel_data,
                file_name=file_name_download,
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
                type="primary"
            )
            
        # Preview bảng (Chỉ xem)
        st.write("Xem trước dữ liệu sẽ xuất:")
        st.dataframe(df.sort_values(by='Ngay', ascending=False).head(5), hide_index=True)
    else:
        st.warning("Chưa có dữ liệu để xuất file.")
