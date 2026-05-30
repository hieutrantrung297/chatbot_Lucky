"""Google Sheets integration — ghi đơn hàng tự động vào spreadsheet."""

import json
import logging

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_settings
from app.models import Order

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SHEET_NAME = "Đơn Hàng"
HEADERS = [
    "Mã Đơn", "Thời Gian", "Tên KH", "SĐT",
    "Loại Bánh", "Size", "Hương Vị", "Chữ Trên Bánh",
    "Ngày Giao", "Địa Chỉ", "Ghi Chú",
    "Tổng Tiền", "Tiền Cọc", "Trạng Thái",
]


def _get_worksheet():
    """Kết nối và trả về worksheet 'Đơn Hàng'."""
    settings = get_settings()
    creds_info = json.loads(settings.google_service_account_json)
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(settings.google_sheet_id)

    # Tạo sheet nếu chưa tồn tại
    try:
        worksheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=20)
        worksheet.append_row(HEADERS)

    # Thêm header nếu sheet trống
    if worksheet.row_count == 0 or worksheet.cell(1, 1).value != HEADERS[0]:
        worksheet.insert_row(HEADERS, index=1)

    return worksheet


def get_orders_by_phone(phone: str) -> list[dict]:
    """Tra cứu tất cả đơn hàng theo số điện thoại. Trả về list dict hoặc [] nếu lỗi."""
    import re
    phone_clean = re.sub(r"[\s\-.()+]", "", phone)
    if phone_clean.startswith("84"):
        phone_clean = "0" + phone_clean[2:]
    try:
        worksheet = _get_worksheet()
        records = worksheet.get_all_records()
        matched = []
        for row in records:
            row_phone = re.sub(r"[\s\-.()+]", "", str(row.get("SĐT", "")))
            if row_phone == phone_clean:
                matched.append({
                    "order_id":     row.get("Mã Đơn", ""),
                    "created_at":   row.get("Thời Gian", ""),
                    "name":         row.get("Tên KH", ""),
                    "phone":        row.get("SĐT", ""),
                    "cake_type":    row.get("Loại Bánh", ""),
                    "size":         row.get("Size", ""),
                    "flavor":       row.get("Hương Vị", ""),
                    "delivery_date": row.get("Ngày Giao", ""),
                    "address":      row.get("Địa Chỉ", ""),
                    "total_price":  row.get("Tổng Tiền", ""),
                    "status":       row.get("Trạng Thái", ""),
                })
        return matched
    except Exception as exc:
        logger.error("Lỗi tra cứu đơn theo SĐT: %s", exc)
        return []


def append_order(order: Order) -> bool:
    """Ghi 1 đơn hàng mới vào Google Sheets. Trả về True nếu thành công."""
    print(f"[SHEETS] Đang ghi đơn {order.order_id} vào Google Sheets...")
    try:
        worksheet = _get_worksheet()
        print(f"[SHEETS] Kết nối worksheet thành công")
        row = [
            order.order_id,
            order.created_at,
            order.name,
            order.phone,
            order.cake_type,
            order.size,
            order.flavor,
            order.cake_message or "",
            order.delivery_date,
            order.address,
            order.special_requests or "",
            f"{order.total_price:,.0f}đ",
            f"{order.deposit_required:,.0f}đ",
            order.status.value,
        ]
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        logger.info("Đã ghi đơn %s vào Google Sheets", order.order_id)
        print(f"[SHEETS] ✅ Ghi đơn {order.order_id} thành công!")
        return True
    except Exception as exc:
        logger.error("Lỗi ghi Google Sheets: %s", exc)
        print(f"[SHEETS] ❌ Lỗi: {exc}")
        return False
