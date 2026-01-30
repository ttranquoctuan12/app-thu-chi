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

# CSS Tùy chỉnh (
