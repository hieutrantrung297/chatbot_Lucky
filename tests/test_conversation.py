"""Integration tests — gọi handle_message với AI thật, mock Sheets + KB.

Đánh dấu @pytest.mark.integration để có thể chạy riêng:
    pytest tests/test_conversation.py -m integration -v
"""

import asyncio
import uuid

import pytest

from app.conversation import handle_message
from app.models import ConversationState


def _uid():
    return f"test_{uuid.uuid4().hex[:8]}"


# ── Helpers ──────────────────────────────────────────────────────────────────

async def chat(psid: str, *messages: str) -> list[str]:
    """Gửi nhiều tin nhắn tuần tự, trả về list reply tương ứng."""
    replies = []
    for msg in messages:
        reply = await handle_message(psid, msg)
        replies.append(reply)
    return replies


# ── TC-01: Chào hỏi cơ bản ──────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_basic_greeting(fresh_psid):
    reply = await handle_message(fresh_psid, "Xin chào")
    assert reply, "Reply không được rỗng"
    assert len(reply) > 10
    # Chatbot phải dùng tiếng Việt
    vietnamese_markers = ["ạ", "em", "anh", "chị", "bánh", "Lucky", "dạ"]
    assert any(m in reply for m in vietnamese_markers), f"Reply không có vẻ tiếng Việt: {reply}"


# ── TC-02: Hỏi giá ──────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_price(fresh_psid):
    reply = await handle_message(fresh_psid, "Bánh kem sinh nhật giá bao nhiêu vậy?")
    assert reply
    # Phải có giá (dấu đ hoặc số)
    has_price = any(c.isdigit() for c in reply) or "đ" in reply
    assert has_price, f"Reply không có giá: {reply}"


# ── TC-03: Hỏi giờ mở cửa / địa chỉ ────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_opening_hours(fresh_psid):
    reply = await handle_message(fresh_psid, "Tiệm mở cửa mấy giờ vậy?")
    assert reply
    # Phải có giờ (8, 20, hoặc "giờ")
    assert "8" in reply or "20" in reply or "giờ" in reply.lower(), f"Reply: {reply}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_ask_address(fresh_psid):
    reply = await handle_message(fresh_psid, "Tiệm ở đâu vậy?")
    assert reply
    # Phải có thông tin địa chỉ (Hoài Nhơn, Bình Định, hoặc đường)
    keywords = ["Hoài Nhơn", "Bình Định", "Nguyễn", "địa chỉ", "97"]
    assert any(k in reply for k in keywords), f"Reply không có địa chỉ: {reply}"


# ── TC-04: Trigger đặt hàng ──────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_trigger(fresh_psid):
    """'đặt bánh' phải chuyển sang ORDERING và hỏi tên."""
    reply = await handle_message(fresh_psid, "Tôi muốn đặt bánh sinh nhật")
    assert reply

    # Load record để kiểm tra state
    from app.conversation import _load_record
    record = _load_record(fresh_psid)
    assert record.state == ConversationState.ORDERING, f"State: {record.state}, Reply: {reply}"
    # Phải hỏi tên hoặc thông tin
    assert any(w in reply.lower() for w in ["tên", "thông tin", "hỗ trợ"]), f"Reply: {reply}"


# ── TC-05: Happy path — đặt hàng đầy đủ ────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_order_happy_path(fresh_psid, mock_sheets):
    """Đặt bánh kem sinh nhật từ đầu đến cuối, check order được ghi vào sheets."""
    from datetime import datetime, timedelta
    delivery_date = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")

    replies = await chat(
        fresh_psid,
        "Tôi muốn đặt bánh sinh nhật",
        "Nguyễn Hieu",                   # tên
        "0901234567",                    # SĐT
        "Bánh Kem Sinh Nhật",            # loại
        "20cm",                          # size
        "Vanilla",                       # hương vị
        "Happy Birthday Lan",            # chữ trên bánh
        delivery_date,                   # ngày giao
        "97 Nguyễn Chí Thanh, Hoài Nhơn",  # địa chỉ
    )

    # Reply cuối phải là tóm tắt đơn (CONFIRMING)
    from app.conversation import _load_record
    record = _load_record(fresh_psid)
    assert record.state == ConversationState.CONFIRMING, \
        f"Expected CONFIRMING, got {record.state}. Last reply: {replies[-1]}"

    # Xác nhận đơn
    confirm_reply = await handle_message(fresh_psid, "xác nhận")
    record = _load_record(fresh_psid)
    assert record.state == ConversationState.CONFIRMED, \
        f"Expected CONFIRMED, got {record.state}. Reply: {confirm_reply}"

    # Google Sheets phải được gọi
    assert mock_sheets["append"].called, "append_order không được gọi"
    order_arg = mock_sheets["append"].call_args[0][0]
    assert order_arg.name == "Nguyễn Hieu"
    assert order_arg.phone == "0901234567"
    assert order_arg.cake_type == "Bánh Kem Sinh Nhật"
    assert order_arg.size == "20cm"


# ── TC-06: SĐT sai format → yêu cầu nhập lại ────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_phone_retry(fresh_psid):
    await handle_message(fresh_psid, "Tôi muốn đặt bánh")
    await handle_message(fresh_psid, "Hieu")          # tên

    reply = await handle_message(fresh_psid, "0123-ABC")   # SĐT sai
    # Phải báo lỗi và yêu cầu nhập lại
    assert any(w in reply.lower() for w in ["số điện thoại", "sdt", "định dạng", "lại"]), \
        f"Không báo lỗi SĐT: {reply}"

    # Order chưa có phone
    from app.conversation import _load_record
    record = _load_record(fresh_psid)
    assert record.order_in_progress.phone is None, "Phone không nên được lưu khi sai format"


# ── TC-07: Ngày giao quá sớm → yêu cầu nhập lại ────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_date_too_soon(fresh_psid):
    from datetime import datetime, timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    await handle_message(fresh_psid, "Tôi muốn đặt bánh")
    await handle_message(fresh_psid, "Hieu")
    await handle_message(fresh_psid, "0901234567")
    await handle_message(fresh_psid, "Bánh Kem Sinh Nhật")
    await handle_message(fresh_psid, "20cm")
    await handle_message(fresh_psid, "Vanilla")
    await handle_message(fresh_psid, "Happy Birthday")

    reply = await handle_message(fresh_psid, tomorrow)   # quá sớm

    assert any(w in reply.lower() for w in ["đặt trước", "sớm nhất", "ngày", "tối thiểu"]), \
        f"Không báo lỗi ngày: {reply}"

    from app.conversation import _load_record
    record = _load_record(fresh_psid)
    assert record.order_in_progress.delivery_date is None, "Date không nên lưu khi quá sớm"


# ── TC-08: Hủy đơn giữa chừng ────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_cancel_during_ordering(fresh_psid):
    await handle_message(fresh_psid, "Tôi muốn đặt bánh")
    await handle_message(fresh_psid, "Hieu")
    await handle_message(fresh_psid, "0901234567")

    reply = await handle_message(fresh_psid, "thôi hủy đi")

    from app.conversation import _load_record
    record = _load_record(fresh_psid)
    assert record.state == ConversationState.CANCELLED
    assert "hủy" in reply.lower()


# ── TC-09: Sửa field ở bước CONFIRMING ──────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_edit_field_at_confirming(fresh_psid):
    from datetime import datetime, timedelta
    delivery_date = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")

    await chat(
        fresh_psid,
        "đặt bánh", "Hieu", "0901234567", "Bánh Kem Sinh Nhật",
        "20cm", "Vanilla", "Happy Birthday", delivery_date,
        "97 Nguyễn Chí Thanh",
    )

    from app.conversation import _load_record
    assert _load_record(fresh_psid).state == ConversationState.CONFIRMING

    reply = await handle_message(fresh_psid, "sửa địa chỉ")
    record = _load_record(fresh_psid)

    assert record.state == ConversationState.ORDERING, f"State: {record.state}"
    assert record.order_in_progress.address is None
    assert "địa chỉ" in reply.lower()


# ── TC-10: Nhiều field trong 1 tin nhắn ─────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_field_single_message(fresh_psid):
    """Agent phải extract được tên + SĐT từ 1 tin nhắn."""
    await handle_message(fresh_psid, "Tôi muốn đặt bánh")

    reply = await handle_message(
        fresh_psid,
        "Tên tôi là Hieu, số điện thoại 0901234567"
    )

    from app.conversation import _load_record
    record = _load_record(fresh_psid)
    # Sau khi extract được tên + SĐT, phải hỏi loại bánh
    assert record.order_in_progress.name is not None, f"Tên chưa được lưu. Reply: {reply}"
    assert record.order_in_progress.phone is not None, f"SĐT chưa được lưu. Reply: {reply}"


# ── TC-11: Tra cứu đơn hàng ──────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_status_lookup_not_found(fresh_psid, mock_sheets):
    mock_sheets["get"].return_value = []
    reply = await handle_message(
        fresh_psid,
        "Cho tôi kiểm tra đơn hàng SĐT 0901234567"
    )
    assert reply
    # Phải có phản hồi về tra cứu (không crash)
    assert len(reply) > 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_order_status_lookup_found(fresh_psid, mock_sheets):
    mock_sheets["get"].return_value = [{
        "order_id": "LUCKY-20260530-AB12",
        "cake_type": "Bánh Kem Sinh Nhật",
        "size": "20cm",
        "delivery_date": "05/06/2026",
        "status": "confirmed",
    }]
    reply = await handle_message(
        fresh_psid,
        "Kiểm tra đơn hàng số điện thoại 0901234567"
    )
    assert reply
    assert len(reply) > 5


# ── TC-12: Sau khi chốt đơn, hội thoại tiếp theo phải fresh ─────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_conversation_after_confirmed(fresh_psid, mock_sheets):
    """Sau khi xác nhận đơn, nhắn lại phải là hội thoại bình thường, không reference đơn cũ."""
    from datetime import datetime, timedelta
    delivery_date = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")

    await chat(
        fresh_psid,
        "đặt bánh", "Hieu", "0901234567", "Bánh Kem Sinh Nhật",
        "20cm", "Vanilla", "Happy Birthday", delivery_date,
        "97 Nguyễn Chí Thanh",
    )
    await handle_message(fresh_psid, "xác nhận")

    # Hội thoại mới
    reply = await handle_message(fresh_psid, "Xin chào, cho hỏi tiệm mở cửa mấy giờ?")
    assert reply
    assert len(reply) > 5
    # Không reference order ID cũ
    assert "LUCKY-" not in reply


# ── TC-13: Câu hỏi ngoài chủ đề bánh ───────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_off_topic_question(fresh_psid):
    reply = await handle_message(fresh_psid, "Bạn có biết dự báo thời tiết không?")
    assert reply
    # Chatbot phải lịch sự từ chối hoặc hướng về chủ đề bánh
    assert len(reply) > 5
