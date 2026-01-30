import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import json
from datetime import datetime

# --- CẤU HÌNH ỨNG DỤNG ---
st.set_page_config(page_title="Sổ Thu Chi Thông Minh", page_icon="💰", layout="centered")

# --- KẾT NỐI GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_connection():
    """Kết nối tới Google Sheet dùng thông tin từ Secrets"""
    s_info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(s_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

def load_data():
    """Tải dữ liệu về hiển thị"""
    try:
        client = get_connection()
        sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame(columns=['Ngay', 'Loai', 'SoTien', 'MoTa'])
        df = pd.DataFrame(data)
        # Chuyển đổi định dạng ngày tháng để tính toán
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce') 
        return df
    except Exception as e:
        # Nếu lỗi (ví dụ chưa có file), trả về bảng rỗng
        return pd.DataFrame(columns=['Ngay', 'Loai', 'SoTien', 'MoTa'])

def save_to_google_sheet(date, category, amount, description):
    """Lưu dòng mới vào Sheet"""
    client = get_connection()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    date_str = date.strftime('%Y-%m-%d')
    sheet.append_row([date_str, category, int(amount), description])

# --- TRÍ TUỆ NHÂN TẠO (AI) ---
def ai_scan_bill(image):
    """Dùng Gemini để đọc hóa đơn"""
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = """
        Phân tích hình ảnh hóa đơn này và trả về kết quả JSON thuần túy (không markdown) với 3 trường:
        - "ngay": YYYY-MM-DD (nếu không có lấy ngày hôm nay).
        - "so_tien": Số nguyên (bỏ dấu chấm phẩy, ví dụ 50000).
        - "mo_ta": Tóm tắt ngắn gọn món mua (tiếng Việt).
        """
        response = model.generate_content([prompt, image])
        txt = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(txt)
    except Exception as e:
        st.error(f"AI chưa đọc được: {e}")
        return None

# --- GIAO DIỆN CHÍNH ---
st.title("💰 Quản Lý Thu Chi AI")

# Session State: Bộ nhớ tạm để lưu thông tin khi AI đọc xong
if 'f_ngay' not in st.session_state: st.session_state.f_ngay = datetime.now()
if 'f_tien' not in st.session_state: st.session_state.f_tien = 0
if 'f_mota' not in st.session_state: st.session_state.f_mota = ""

# 1. QUÉT HÓA ĐƠN
with st.expander("📸 Quét Hóa Đơn (AI)", expanded=True):
    uploaded_file = st.file_uploader("Chọn ảnh hóa đơn...", type=['jpg','png','jpeg'])
    if uploaded_file and st.button("Trích xuất thông tin"):
        img = Image.open(uploaded_file)
        st.image(img, width=200)
        with st.spinner("AI đang đọc..."):
            info = ai_scan_bill(img)
            if info:
                try:
                    st.session_state.f_ngay = datetime.strptime(info['ngay'], '%Y-%m-%d')
                except: pass
                st.session_state.f_tien = info['so_tien']
                st.session_state.f_mota = info['mo_ta']
                st.success("Đã đọc xong! Kiểm tra bên dưới.")

# 2. NHẬP LIỆU
st.write("### 📝 Nhập Giao Dịch")
col1, col2 = st.columns(2)
with col1:
    d_ngay = st.date_input("Ngày", value=st.session_state.f_ngay)
    d_loai = st.selectbox("Loại", ["Chi", "Thu"])
with col2:
    d_tien = st.number_input("Số tiền", min_value=0, step=1000, value=int(st.session_state.f_tien))
    
d_mota = st.text_input("Mô tả", value=st.session_state.f_mota)

if st.button("Lưu Lại", type="primary"):
    if d_tien > 0:
        save_to_google_sheet(d_ngay, d_loai, d_tien, d_mota)
        st.toast("Đã lưu thành công!", icon="✅")
        # Reset
        st.session_state.f_tien = 0
        st.session_state.f_mota = ""
        st.rerun() # Tải lại trang
    else:
        st.warning("Số tiền phải lớn hơn 0")

# 3. THỐNG KÊ
st.divider()
st.write("### 📊 Thống Kê Theo Tuần")
df = load_data()

if not df.empty:
    # Tạo cột Tuần-Năm
    df['Tuan'] = df['Ngay'].dt.strftime('%V/%G') # Tuần/Năm
    
    # Gom nhóm
    summary = df.groupby(['Tuan', 'Loai'])['SoTien'].sum().unstack(fill_value=0)
    
    # Đảm bảo đủ cột
    for col in ['Thu', 'Chi']:
        if col not in summary.columns: summary[col] = 0
        
    summary['So_Du'] = summary['Thu'] - summary['Chi']
    summary = summary.sort_index(ascending=False) # Mới nhất lên đầu
    
    st.dataframe(summary.style.format("{:,.0f}"), use_container_width=True)
    st.bar_chart(summary[['Thu', 'Chi']])
else:

    st.info("Chưa có dữ liệu nào.")
