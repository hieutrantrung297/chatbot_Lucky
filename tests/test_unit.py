"""Unit tests — pure functions, không cần API hay mạng."""

from datetime import datetime, timedelta

import pytest

from app.models import ConversationRecord, ConversationState, OrderInProgress
from app.order_handler import (
    _detect_edit_field,
    _validate_date,
    _validate_phone,
    format_order_summary,
    needs_cake_message,
    process_confirming,
)


# ── Phone validation ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("phone", [
    "0901234567",
    "0912345678",
    "0398765432",
    "0765432109",
    "0856789012",
    "+84901234567",
    "0 901 234 567",   # spaces
    "090-123-4567",    # dashes
])
def test_validate_phone_valid(phone):
    assert _validate_phone(phone) is True, f"Expected valid: {phone}"


@pytest.mark.parametrize("phone", [
    "12345",
    "0123456789",   # starts with 01 (old format)
    "0201234567",   # prefix 02 không hợp lệ với mobile
    "090123456",    # thiếu 1 số
    "09012345678",  # dư 1 số
    "abcdefghij",
    "",
])
def test_validate_phone_invalid(phone):
    assert _validate_phone(phone) is False, f"Expected invalid: {phone}"


# ── Date validation ──────────────────────────────────────────────────────────

def test_validate_date_valid():
    future = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")
    ok, msg = _validate_date(future)
    assert ok is True
    assert msg == ""


def test_validate_date_too_soon():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    ok, msg = _validate_date(tomorrow)
    assert ok is False
    assert "đặt trước" in msg.lower() or "sớm nhất" in msg.lower()


def test_validate_date_today():
    today = datetime.now().strftime("%d/%m/%Y")
    ok, msg = _validate_date(today)
    assert ok is False


def test_validate_date_wrong_format():
    for bad in ["2026-06-01", "01-06-2026", "32/13/2026", "abc", ""]:
        ok, msg = _validate_date(bad)
        assert ok is False, f"Expected invalid date: {bad}"
        assert msg != ""


def test_validate_date_exactly_min_days():
    from app.catalog import get_min_order_days
    min_days = get_min_order_days()
    exact = (datetime.now() + timedelta(days=min_days)).strftime("%d/%m/%Y")
    ok, _ = _validate_date(exact)
    assert ok is True


# ── needs_cake_message ───────────────────────────────────────────────────────

@pytest.mark.parametrize("cake_type,expected", [
    ("Bánh Kem Sinh Nhật", True),
    ("Bánh Kem Cơ Bản", True),
    ("Bánh Kem Socola", True),
    ("Bánh Kem Trái Cây", True),
    ("Bánh Kem In Ảnh", True),
    ("Bánh Kem Fondant", True),
    ("BÁNH KEM CƠ BẢN", True),         # uppercase
    ("sinh nhật đặc biệt", True),       # contains keyword
    ("Bánh Mì", False),
    ("Bánh Ngọt / Bánh Nhỏ", False),
    ("Cupcake", False),
    ("", False),
])
def test_needs_cake_message(cake_type, expected):
    assert needs_cake_message(cake_type) == expected, f"Failed for: {cake_type}"


# ── OrderInProgress.next_missing_field ──────────────────────────────────────

def test_next_field_empty_order():
    order = OrderInProgress()
    assert order.next_missing_field(False) == "name"


def test_next_field_after_name():
    order = OrderInProgress(name="Hieu")
    assert order.next_missing_field(False) == "phone"


def test_next_field_cream_cake_needs_message():
    order = OrderInProgress(
        name="Hieu", phone="0901234567",
        cake_type="Bánh Kem Sinh Nhật", size="20cm", flavor="Vanilla"
    )
    assert order.next_missing_field(True) == "cake_message"


def test_next_field_cream_cake_no_message_needed():
    order = OrderInProgress(
        name="Hieu", phone="0901234567",
        cake_type="Bánh Mì", size="1 ổ", flavor="Thịt nguội"
    )
    # Non-cream cake → skip cake_message
    assert order.next_missing_field(False) == "delivery_date"


def test_next_field_complete_non_cream():
    order = OrderInProgress(
        name="Hieu", phone="0901234567",
        cake_type="Bánh Mì", size="1 ổ", flavor="Thịt nguội",
        delivery_date="25/06/2026", address="123 Lê Lợi"
    )
    assert order.next_missing_field(False) is None


def test_next_field_complete_cream():
    order = OrderInProgress(
        name="Hieu", phone="0901234567",
        cake_type="Bánh Kem Sinh Nhật", size="20cm", flavor="Vanilla",
        cake_message="Happy Birthday",
        delivery_date="25/06/2026", address="123 Lê Lợi"
    )
    assert order.next_missing_field(True) is None


def test_next_field_cream_empty_message_ok():
    """cake_message="" (không cần ghi) vẫn hợp lệ — không phải None."""
    order = OrderInProgress(
        name="Hieu", phone="0901234567",
        cake_type="Bánh Kem Sinh Nhật", size="20cm", flavor="Vanilla",
        cake_message="",  # empty string = đã trả lời "không cần"
        delivery_date="25/06/2026", address="123 Lê Lợi"
    )
    assert order.next_missing_field(True) is None


# ── _detect_edit_field ───────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_field", [
    ("sửa tên", "name"),
    ("đổi họ tên", "name"),
    ("sửa số điện thoại", "phone"),
    ("sửa sđt", "phone"),
    ("sửa loại bánh", "cake_type"),
    ("đổi bánh khác", "cake_type"),
    ("sửa size", "size"),
    ("đổi cỡ bánh", "size"),
    ("sửa hương vị", "flavor"),
    ("đổi vị", "flavor"),
    ("sửa chữ trên bánh", "cake_message"),
    ("đổi nội dung", "cake_message"),
    ("sửa ngày giao", "delivery_date"),
    ("đổi ngày nhận", "delivery_date"),
    ("sửa địa chỉ", "address"),
    ("giao đến địa chỉ khác", "address"),
])
def test_detect_edit_field(text, expected_field):
    result = _detect_edit_field(text)
    assert result == expected_field, f"'{text}' → expected {expected_field}, got {result}"


def test_detect_edit_field_unknown():
    assert _detect_edit_field("không biết sửa gì") is None
    assert _detect_edit_field("xác nhận") is None


# ── format_order_summary ─────────────────────────────────────────────────────

def test_format_order_summary_cream_cake():
    order = OrderInProgress(
        name="Nguyễn Hieu", phone="0901234567",
        cake_type="Bánh Kem Sinh Nhật", size="20cm", flavor="Vanilla",
        cake_message="Happy Birthday Lan",
        delivery_date="25/06/2026", address="97 Nguyễn Chí Thanh"
    )
    summary = format_order_summary(order, is_cream_cake=True, unit_price=320000)
    assert "Nguyễn Hieu" in summary
    assert "0901234567" in summary
    assert "Bánh Kem Sinh Nhật" in summary
    assert "Happy Birthday Lan" in summary
    assert "320.000đ" in summary
    assert "160.000đ" in summary   # tiền cọc 50%


def test_format_order_summary_non_cream():
    order = OrderInProgress(
        name="Hieu", phone="0901234567",
        cake_type="Bánh Mì", size="1 ổ", flavor="Thịt nguội",
        delivery_date="25/06/2026", address="123 Lê Lợi"
    )
    summary = format_order_summary(order, is_cream_cake=False, unit_price=25000)
    assert "Bánh Mì" in summary
    assert "Happy Birthday" not in summary   # không có cake_message
    assert "📝" not in summary               # không có dòng chữ trên bánh


# ── process_confirming ───────────────────────────────────────────────────────

def _make_confirming_record():
    record = ConversationRecord(
        psid="test",
        state=ConversationState.CONFIRMING,
        is_cream_cake=True,
        order_in_progress=OrderInProgress(
            name="Hieu", phone="0901234567",
            cake_type="Bánh Kem Sinh Nhật", size="20cm", flavor="Vanilla",
            cake_message="Happy Birthday",
            delivery_date="25/06/2026", address="97 Nguyễn Chí Thanh"
        )
    )
    return record


def test_process_confirming_cancel():
    record = _make_confirming_record()
    updated, reply = process_confirming(record, "hủy đơn đi")
    assert updated.state == ConversationState.CANCELLED
    assert "hủy" in reply.lower()


def test_process_confirming_confirm_keywords():
    for keyword in ["xác nhận", "ok", "oke", "đúng", "chốt", "yes", "đồng ý"]:
        record = _make_confirming_record()
        updated, reply = process_confirming(record, keyword)
        assert updated.state == ConversationState.CONFIRMED, f"keyword: {keyword}"
        assert updated.current_order_id is not None


def test_process_confirming_edit_field():
    record = _make_confirming_record()
    updated, reply = process_confirming(record, "sửa ngày giao")
    assert updated.state == ConversationState.ORDERING
    assert updated.order_in_progress.delivery_date is None
    assert "ngày" in reply.lower() or "delivery" in reply.lower()


def test_process_confirming_edit_phone():
    record = _make_confirming_record()
    updated, reply = process_confirming(record, "sửa số điện thoại")
    assert updated.state == ConversationState.ORDERING
    assert updated.order_in_progress.phone is None


def test_process_confirming_unclear():
    record = _make_confirming_record()
    updated, reply = process_confirming(record, "em không biết")
    assert updated.state == ConversationState.CONFIRMING   # vẫn ở CONFIRMING
    assert "xác nhận" in reply.lower() or "sửa" in reply.lower()


# ── No-diacritics support ────────────────────────────────────────────────────

def test_confirm_no_diacritics():
    """Khách nhắn không dấu 'xac nhan' vẫn chốt được đơn."""
    record = _make_confirming_record()
    updated, reply = process_confirming(record, "xac nhan")
    assert updated.state == ConversationState.CONFIRMED, f"Reply: {reply}"


def test_confirm_ok_works():
    for kw in ["ok", "OK", "oke", "yes"]:
        record = _make_confirming_record()
        updated, _ = process_confirming(record, kw)
        assert updated.state == ConversationState.CONFIRMED, f"keyword: {kw}"


def test_cancel_no_diacritics():
    record = _make_confirming_record()
    updated, reply = process_confirming(record, "huy don di")
    assert updated.state == ConversationState.CANCELLED


def test_edit_field_no_diacritics():
    """'sua ngay giao' (không dấu) phải nhận diện được là sửa delivery_date."""
    from app.order_handler import _detect_edit_field
    assert _detect_edit_field("sua ngay giao") == "delivery_date"
    assert _detect_edit_field("doi huong vi") == "flavor"
    assert _detect_edit_field("sua dia chi") == "address"
    assert _detect_edit_field("doi ten nguoi nhan") == "name"
    assert _detect_edit_field("sua so dien thoai") == "phone"
