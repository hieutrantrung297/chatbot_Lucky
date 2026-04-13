"""Xử lý luồng đặt hàng — thu thập thông tin tuần tự từ khách hàng."""

import logging
import re
import uuid
from datetime import datetime, timedelta

from app.catalog import calculate_delivery_fee, get_min_order_days, get_price
from app.models import ConversationRecord, ConversationState, Order, OrderStatus

logger = logging.getLogger(__name__)

# ── Câu hỏi cho từng field ──────────────────────────────────────────────────

FIELD_QUESTIONS = {
    "name": "Dạ, để em hỗ trợ đặt hàng, anh/chị cho em biết tên người nhận bánh là gì ạ? 😊",
    "phone": "Anh/chị cho em số điện thoại liên hệ nhé ạ? 📱",
    "cake_type": (
        "Anh/chị muốn đặt loại bánh gì ạ? Em có các loại:\n"
        "🎂 Bánh Kem Cơ Bản | Bánh Kem Sinh Nhật | Bánh Kem Socola\n"
        "🍓 Bánh Kem Trái Cây | Bánh Kem In Ảnh | Bánh Kem Fondant\n"
        "🍞 Bánh Mì | Bánh Ngọt"
    ),
    "size": (
        "Anh/chị muốn bánh size bao nhiêu ạ?\n"
        "📏 16cm (~4-6 người) | 20cm (~8-10 người) | 26cm (~12-16 người) | 30cm (~20-25 người)"
    ),
    "flavor": "Anh/chị chọn hương vị gì ạ? (VD: Vanilla, Dâu, Socola, Lá dứa, Matcha...) 🍫",
    "cake_message": (
        "Anh/chị muốn ghi gì lên bánh không ạ? 🖊️\n"
        "(VD: 'Happy Birthday Lan', 'Chúc mừng 10 tuổi', hoặc nhắn 'không cần' nếu để trống)"
    ),
    "delivery_date": "Anh/chị muốn nhận bánh vào ngày nào ạ? (Định dạng: DD/MM/YYYY) 📅",
    "address": "Anh/chị cho em địa chỉ giao bánh nhé ạ? 📍",
}


def needs_cake_message(cake_type: str) -> bool:
    """Chỉ hỏi chữ trên bánh nếu là bánh kem hoặc bánh sinh nhật."""
    keywords = ["bánh kem", "sinh nhật"]
    lower = cake_type.lower()
    return any(kw in lower for kw in keywords)


def _validate_phone(phone: str) -> bool:
    """Kiểm tra số điện thoại Việt Nam hợp lệ."""
    cleaned = re.sub(r"[\s\-.]", "", phone)
    return bool(re.match(r"^(0|\+84)(3|5|7|8|9)\d{8}$", cleaned))


def _validate_date(date_str: str) -> tuple[bool, str]:
    """
    Kiểm tra ngày giao hàng hợp lệ.
    Trả về (is_valid, error_message).
    """
    try:
        delivery_date = datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return False, "Ngày không đúng định dạng. Anh/chị nhập lại theo định dạng DD/MM/YYYY nhé ạ (VD: 20/04/2026)"

    today = datetime.now().date()
    min_days = get_min_order_days()
    earliest = today + timedelta(days=min_days)

    if delivery_date < earliest:
        return False, (
            f"Dạ tiệm cần đặt trước tối thiểu {min_days} ngày ạ. "
            f"Ngày giao sớm nhất là {earliest.strftime('%d/%m/%Y')}. "
            "Anh/chị chọn lại ngày nhé! 🙏"
        )
    return True, ""


def _generate_order_id() -> str:
    today = datetime.now().strftime("%Y%m%d")
    short_id = str(uuid.uuid4())[:4].upper()
    return f"LUCKY-{today}-{short_id}"


def _format_order_confirmation(order: Order) -> str:
    """Tạo tin nhắn xác nhận đơn hàng đẹp."""
    cake_msg_line = f"📝 Chữ trên bánh: {order.cake_message}\n" if order.cake_message else ""
    special_line = f"💬 Ghi chú: {order.special_requests}\n" if order.special_requests else ""

    return (
        f"✅ Đơn hàng của anh/chị đã được ghi nhận!\n\n"
        f"🧾 Mã đơn: {order.order_id}\n"
        f"👤 Tên: {order.name}\n"
        f"📱 SĐT: {order.phone}\n"
        f"🎂 Bánh: {order.cake_type} ({order.size})\n"
        f"🍫 Hương vị: {order.flavor}\n"
        f"{cake_msg_line}"
        f"📅 Ngày giao: {order.delivery_date}\n"
        f"📍 Địa chỉ: {order.address}\n"
        f"{special_line}\n"
        f"💰 Tổng tiền: {order.total_price:,.0f}đ\n"
        f"💳 Tiền cọc (50%): {order.deposit_required:,.0f}đ\n\n"
        f"Anh/chị vui lòng chuyển khoản tiền cọc để xác nhận đơn nhé! "
        f"Em sẽ liên hệ lại để xác nhận chi tiết. Cảm ơn anh/chị! 🎉"
    )


def process_ordering(record: ConversationRecord, user_text: str) -> tuple[ConversationRecord, str]:
    """
    Xử lý 1 lượt tin nhắn trong trạng thái ordering.
    Trả về (updated_record, reply_text).
    """
    order = record.order_in_progress
    is_cream = record.is_cream_cake
    next_field = order.next_missing_field(is_cream)

    # ── Khách muốn hủy ───────────────────────────────────────────────────────
    cancel_keywords = ["hủy", "thôi", "không đặt", "bỏ qua", "cancel"]
    if any(kw in user_text.lower() for kw in cancel_keywords):
        record.state = ConversationState.CANCELLED
        record.order_in_progress = type(order)()  # reset
        return record, "Dạ em đã hủy đơn hàng cho anh/chị rồi ạ. Nếu cần hỗ trợ gì thêm, anh/chị cứ nhắn em nhé! 😊"

    # ── Điền thông tin theo field hiện tại ──────────────────────────────────
    if next_field is None:
        # Không có field nào còn thiếu, đơn đã đủ — xử lý bên dưới
        pass
    elif next_field == "phone":
        if not _validate_phone(user_text):
            reply = "Số điện thoại chưa đúng định dạng ạ. Anh/chị nhập lại giúp em nhé! (VD: 0901234567) 📱"
            return record, reply
        order.phone = re.sub(r"[\s\-.]", "", user_text)

    elif next_field == "cake_type":
        order.cake_type = user_text.strip()
        # Xác định ngay sau khi biết loại bánh
        record.is_cream_cake = needs_cake_message(order.cake_type)
        is_cream = record.is_cream_cake

    elif next_field == "delivery_date":
        valid, err_msg = _validate_date(user_text)
        if not valid:
            return record, err_msg
        order.delivery_date = user_text.strip()

    elif next_field == "cake_message":
        # Khách có thể chọn "không cần" / "bỏ trống"
        skip_keywords = ["không", "không cần", "thôi", "bỏ trống", "ko", "k cần"]
        if any(kw in user_text.lower() for kw in skip_keywords):
            order.cake_message = ""   # Chuỗi rỗng = không ghi gì
        else:
            order.cake_message = user_text.strip()

    elif next_field == "size":
        # Chuẩn hóa size input
        size_map = {"16": "16cm", "20": "20cm", "26": "26cm", "30": "30cm"}
        cleaned = user_text.strip().lower().replace(" ", "")
        for k, v in size_map.items():
            if k in cleaned:
                order.size = v
                break
        else:
            order.size = cleaned  # Giữ nguyên nếu không match

    else:
        # Các field text thông thường (name, flavor, address)
        setattr(order, next_field, user_text.strip())

    record.order_in_progress = order

    # ── Kiểm tra xem đã đủ thông tin chưa ──────────────────────────────────
    next_field = order.next_missing_field(record.is_cream_cake)

    if next_field is not None:
        # Còn thiếu field — hỏi tiếp
        reply = FIELD_QUESTIONS.get(next_field, f"Anh/chị cho em biết {next_field} nhé ạ?")
        return record, reply

    # ── Đủ thông tin → tạo đơn hàng ─────────────────────────────────────────
    unit_price = get_price(order.cake_type or "", order.size or "")
    delivery_fee = 0.0  # Tính thêm nếu có tích hợp tính khoảng cách
    total = unit_price + delivery_fee
    deposit = total * 0.5

    completed_order = Order(
        order_id=_generate_order_id(),
        psid=record.psid,
        name=order.name or "",
        phone=order.phone or "",
        cake_type=order.cake_type or "",
        size=order.size or "",
        flavor=order.flavor or "",
        cake_message=order.cake_message if order.cake_message else None,
        delivery_date=order.delivery_date or "",
        address=order.address or "",
        special_requests=order.special_requests,
        unit_price=unit_price,
        delivery_fee=delivery_fee,
        total_price=total,
        deposit_required=deposit,
        status=OrderStatus.PENDING,
        created_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )

    # Ghi vào Google Sheets (import late để tránh circular)
    from app.sheets import append_order
    append_order(completed_order)

    record.state = ConversationState.CONFIRMED
    record.current_order_id = completed_order.order_id
    record.order_in_progress = type(order)()  # reset

    reply = _format_order_confirmation(completed_order)
    return record, reply


def get_first_question() -> str:
    """Câu hỏi đầu tiên khi bắt đầu luồng đặt hàng."""
    return FIELD_QUESTIONS["name"]
