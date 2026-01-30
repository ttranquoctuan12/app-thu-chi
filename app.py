import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import time
from io import BytesIO # <--- Thư viện cần thiết để xuất Excel

# --- CẤU HÌNH TRANG ---
st.set_page_config(page_title="Sổ Thu Chi Pro", page_icon="💎", layout="centered")

# --- KẾT NỐI GOOGLE APIS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def get_creds():
    return Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)

def get_gs_client():
    return gspread.authorize(get_creds())

# --- HÀM FORMAT TIỀN (DẤU CHẤM) ---
def format_vnd(amount):
    if pd.isna(amount): return "0"
    return "{:,.0f}".format(amount).replace(",", ".")

# --- HÀM XUẤT EXCEL (ĐÃ THÊM LẠI) ---
def convert_df_to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Format lại ngày tháng khi xuất ra Excel cho đẹp
        df_export = df.copy()
        if 'Ngay' in df_export.columns:
            df_export['Ngay'] = df_export['Ngay'].dt.strftime('%d/%m/%Y')
        df_export.to_excel(writer, index=False, sheet_name='SoThuChi')
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

# --- CÁC HÀM XỬ LÝ DỮ LIỆU ---
def load_data_with_index():
    try:
        client = get_gs_client()
        sheet = client.open("QuanLyThuChi").worksheet("data")
        data = sheet.get_all_records()
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['Row_Index'] = range(2, len(df) + 2)
        df['Ngay'] = pd.to_datetime(df['Ngay'], errors='coerce')
        # Ép kiểu int64 để tránh lỗi hiển thị, nhưng khi gửi đi phải convert lại int thường
        df['SoTien'] = pd.to_numeric(df['SoTien'], errors='coerce').fillna(0).astype('int64')
        return df
    except:
        return pd.DataFrame()

def add_transaction(date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    sheet.append_row([date.strftime('%Y-%m-%d'), category, int(amount), description, image_link])

def update_transaction(row_idx, date, category, amount, description, image_link):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    # Ép kiểu int() để tránh lỗi TypeError int64
    r_idx = int(row_idx)
    amt = int(amount)
    sheet.update(f"A{r_idx}:E{r_idx}", [[date.strftime('%Y-%m-%d'), category, amt, description, image_link]])

def delete_transaction(row_idx):
    client = get_gs_client()
    sheet = client.open("QuanLyThuChi").worksheet("data")
    # Ép kiểu int() để tránh lỗi TypeError int64
    sheet.delete_rows(int(row_idx))

# ================= GIAO DIỆN CHÍNH =================
st.title("💎 Quản Lý Thu Chi")

# TẢI DỮ LIỆU
df = load_data_with_index()

total_thu = 0
total_chi = 0
balance = 0

if not df.empty:
    total_thu = df[df['Loai'] == 'Thu']['SoTien'].sum()
    total_chi = df[df['Loai'] == 'Chi']['SoTien'].sum()
    balance = total_thu - total_chi

# DASHBOARD
text_color = "#2ecc71" if balance >= 0 else "#e74c3c"
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
