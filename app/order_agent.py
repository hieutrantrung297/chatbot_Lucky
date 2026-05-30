"""Full agentic ordering — LLM tự nhiên hỏi + extract structured fields + validate."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from openai import OpenAI, RateLimitError

from app.catalog import get_catalog_text, get_min_order_days, get_price
from app.config import get_settings
from app.models import ConversationRecord, ConversationState, OrderInProgress
from app.order_handler import format_order_summary, needs_cake_message

logger = logging.getLogger(__name__)

# ── Validation helpers ───────────────────────────────────────────────────────

def _validate_phone(raw: str) -> tuple[bool, str, str]:
    """(ok, cleaned_phone, error_msg)"""
    cleaned = re.sub(r"[\s\-.()+]", "", raw)
    if cleaned.startswith("84"):
        cleaned = "0" + cleaned[2:]
    if re.match(r"^(0)(3|5|7|8|9)\d{8}$", cleaned):
        return True, cleaned, ""
    return False, "", f"Số điện thoại '{raw}' chưa đúng định dạng Việt Nam (VD: 0901234567)"


def _validate_date(raw: str) -> tuple[bool, str]:
    """(ok, error_msg)"""
    try:
        d = datetime.strptime(raw.strip(), "%d/%m/%Y").date()
    except ValueError:
        return False, f"Ngày '{raw}' không đúng định dạng DD/MM/YYYY (VD: 25/06/2026)"
    min_days = get_min_order_days()
    earliest = datetime.now().date() + timedelta(days=min_days)
    if d < earliest:
        return False, (
            f"Tiệm cần đặt trước {min_days} ngày. "
            f"Ngày sớm nhất là {earliest.strftime('%d/%m/%Y')} ạ."
        )
    return True, ""


def _normalize_size(raw: str) -> str:
    for s in ["16", "20", "26", "30"]:
        if s in raw:
            return f"{s}cm"
    return raw.strip()


# ── Tool schema — LLM bắt buộc phải gọi để extract + reply ─────────────────

_EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "update_order",
        "description": (
            "Trích xuất thông tin đặt hàng từ tin nhắn và tạo câu trả lời tự nhiên. "
            "Chỉ điền field nào khách đã cung cấp rõ ràng. Để null các field chưa biết."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name":          {"type": "string", "description": "Tên người nhận bánh"},
                "phone":         {"type": "string", "description": "Số điện thoại liên hệ"},
                "cake_type":     {"type": "string", "description": "Loại bánh (tên đầy đủ từ menu)"},
                "size":          {"type": "string", "description": "Size bánh: 16cm / 20cm / 26cm / 30cm"},
                "flavor":        {"type": "string", "description": "Hương vị bánh"},
                "cake_message":  {"type": "string", "description": "Chữ ghi lên bánh ('' nếu không cần)"},
                "delivery_date": {"type": "string", "description": "Ngày giao hàng định dạng DD/MM/YYYY"},
                "address":       {"type": "string", "description": "Địa chỉ giao hàng"},
                "reply":         {"type": "string", "description": "Câu trả lời tự nhiên gửi lại cho khách"},
            },
            "required": ["reply"],
        },
    },
}

# ── System prompt ────────────────────────────────────────────────────────────

def _build_system_prompt(order: OrderInProgress, is_cream: bool, catalog: str) -> str:
    missing = _missing_field_labels(order, is_cream)
    filled = _filled_summary(order)
    return f"""\
Bạn là Lucky — nhân viên tiệm bánh Lucky, đang hỗ trợ khách đặt hàng.

## Danh mục sản phẩm
{catalog}

## Trạng thái đơn hiện tại
Đã có: {filled if filled else "chưa có thông tin nào"}
Còn thiếu: {', '.join(missing) if missing else "đủ rồi"}

## Nhiệm vụ
Gọi tool update_order để:
1. Trích xuất thông tin mới từ tin nhắn khách (chỉ field khách vừa cung cấp)
2. Tạo câu reply tự nhiên, thân thiện — hỏi tiếp field còn thiếu (không hỏi nhiều hơn 2 field cùng lúc)

Quy tắc trích xuất:
- Chỉ điền field khách đã nói rõ, để null nếu chưa chắc
- Size: chuẩn hóa thành "16cm"/"20cm"/"26cm"/"30cm"
- cake_message: điền "" nếu khách nói "không cần" / "bỏ trống"
- Không bịa, không đoán mò

Quy tắc reply:
- Thân thiện, tự nhiên như nhân viên thật
- Xác nhận lại field vừa nhận được
- Hỏi tiếp field còn thiếu (ưu tiên hỏi field quan trọng trước: tên, SĐT, loại bánh)
- Nếu đã đủ tất cả: chỉ xác nhận field vừa nhận ("Dạ em ghi nhận..."), kết thúc bằng __READY_TO_CONFIRM__
  KHÔNG tóm tắt lại toàn bộ đơn — hệ thống sẽ hiển thị bảng tóm tắt chính thức sau đó.
"""


def _missing_field_labels(order: OrderInProgress, is_cream: bool) -> list[str]:
    labels = {
        "name": "tên người nhận",
        "phone": "số điện thoại",
        "cake_type": "loại bánh",
        "size": "size",
        "flavor": "hương vị",
        "cake_message": "chữ ghi trên bánh",
        "delivery_date": "ngày giao (DD/MM/YYYY)",
        "address": "địa chỉ giao",
    }
    fields = ["name", "phone", "cake_type", "size", "flavor"]
    if is_cream:
        fields.append("cake_message")
    fields += ["delivery_date", "address"]
    return [labels[f] for f in fields if getattr(order, f) is None]


def _filled_summary(order: OrderInProgress) -> str:
    parts = []
    if order.name:           parts.append(f"tên={order.name}")
    if order.phone:          parts.append(f"SĐT={order.phone}")
    if order.cake_type:      parts.append(f"bánh={order.cake_type}")
    if order.size:           parts.append(f"size={order.size}")
    if order.flavor:         parts.append(f"vị={order.flavor}")
    if order.cake_message is not None:
        val = order.cake_message if order.cake_message else "(không ghi)"
        parts.append(f"chữ={val}")
    if order.delivery_date:  parts.append(f"ngày={order.delivery_date}")
    if order.address:        parts.append(f"địa chỉ={order.address}")
    return ", ".join(parts)


# ── Apply extracted fields ───────────────────────────────────────────────────

def _apply_fields(
    order: OrderInProgress,
    extracted: dict,
    is_cream: bool,
) -> tuple[OrderInProgress, bool, list[str]]:
    """
    Áp dụng extracted fields vào order, validate.
    Trả về (updated_order, is_cream_updated, validation_errors).
    """
    errors: list[str] = []

    def _set(field: str, value):
        if value is not None and value != "":
            setattr(order, field, value)

    if extracted.get("name"):
        order.name = extracted["name"].strip()

    if extracted.get("phone"):
        ok, cleaned, err = _validate_phone(extracted["phone"])
        if ok:
            order.phone = cleaned
        else:
            errors.append(err)

    if extracted.get("cake_type"):
        order.cake_type = extracted["cake_type"].strip()
        is_cream = needs_cake_message(order.cake_type)

    if extracted.get("size"):
        order.size = _normalize_size(extracted["size"])

    if extracted.get("flavor"):
        order.flavor = extracted["flavor"].strip()

    # cake_message: "" = không cần, None = chưa hỏi
    if "cake_message" in extracted and extracted["cake_message"] is not None:
        order.cake_message = extracted["cake_message"].strip()

    if extracted.get("delivery_date"):
        ok, err = _validate_date(extracted["delivery_date"])
        if ok:
            order.delivery_date = extracted["delivery_date"].strip()
        else:
            errors.append(err)

    if extracted.get("address"):
        order.address = extracted["address"].strip()

    return order, is_cream, errors


# ── Main entry point ─────────────────────────────────────────────────────────

async def process_order_turn(
    record: ConversationRecord,
    user_text: str,
) -> tuple[ConversationRecord, str]:
    """
    Xử lý 1 lượt trong trạng thái ORDERING.
    Trả về (updated_record, reply_text).
    """
    settings = get_settings()
    gh_client = OpenAI(base_url=settings.github_models_endpoint, api_key=settings.github_token)
    oa_client = (
        OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
    )

    order = record.order_in_progress
    is_cream = record.is_cream_cake
    catalog = get_catalog_text()

    # Kiểm tra hủy đơn (hỗ trợ cả có/không dấu)
    import unicodedata as _ud

    def _nd(t: str) -> str:
        t = t.replace("đ", "d").replace("Đ", "D")
        return "".join(c for c in _ud.normalize("NFKD", t) if not _ud.combining(c))

    lower_text = user_text.lower()
    lower_nd = _nd(lower_text)
    cancel_kw = ["hủy", "thôi", "không đặt", "bỏ qua", "cancel"]
    if any(kw in lower_text or _nd(kw) in lower_nd for kw in cancel_kw):
        record.state = ConversationState.CANCELLED
        record.order_in_progress = OrderInProgress()
        return record, "Dạ em đã hủy đơn hàng rồi ạ. Anh/chị cần hỗ trợ gì thêm cứ nhắn em nhé! 😊"

    system_prompt = _build_system_prompt(order, is_cream, catalog)

    # Chỉ lấy lịch sử SAU separator đơn hàng cuối cùng.
    # Tránh LLM tự điền field từ đơn cũ khi khách bắt đầu đơn mới.
    raw_history = record.message_history[-20:]
    last_sep = -1
    for i, m in enumerate(raw_history):
        if m.get("content", "").startswith("[ĐƠN HÀNG"):
            last_sep = i
    order_history = raw_history[last_sep + 1:]  # messages after last separator

    messages = [{"role": "system", "content": system_prompt}]
    messages += order_history[:-1]  # Không tính tin vừa append
    messages.append({"role": "user", "content": user_text})

    async def _call_with_tools(msgs):
        """Gọi tool-use API, fallback sang OpenAI nếu GitHub Models 429."""
        try:
            return await asyncio.to_thread(
                gh_client.chat.completions.create,
                model=settings.ai_model,
                messages=msgs,
                tools=[_EXTRACT_TOOL],
                tool_choice={"type": "function", "function": {"name": "update_order"}},
                max_tokens=600,
                temperature=0.7,
            )
        except RateLimitError:
            logger.warning("order_agent: GitHub Models rate limit — fallback OpenAI")
            if oa_client:
                return await asyncio.to_thread(
                    oa_client.chat.completions.create,
                    model=settings.openai_model,
                    messages=msgs,
                    tools=[_EXTRACT_TOOL],
                    tool_choice={"type": "function", "function": {"name": "update_order"}},
                    max_tokens=600,
                    temperature=0.7,
                )
            raise

    async def _call_plain(msgs):
        """Gọi API thường (không tool), fallback sang OpenAI nếu GitHub Models 429."""
        try:
            return await asyncio.to_thread(
                gh_client.chat.completions.create,
                model=settings.ai_model,
                messages=msgs,
                max_tokens=300,
                temperature=0.6,
            )
        except RateLimitError:
            logger.warning("order_agent: GitHub Models rate limit — fallback OpenAI")
            if oa_client:
                return await asyncio.to_thread(
                    oa_client.chat.completions.create,
                    model=settings.openai_model,
                    messages=msgs,
                    max_tokens=300,
                    temperature=0.6,
                )
            raise

    # Gọi 1: bắt buộc extract fields + sinh reply
    try:
        response = await _call_with_tools(messages)
    except Exception as exc:
        logger.error("order_agent API error: %s", exc)
        return record, "Dạ xin lỗi anh/chị, em đang gặp sự cố kỹ thuật. Thử lại sau ít phút nhé! 🙏"

    msg = response.choices[0].message
    extracted: dict = {}
    raw_reply: str = ""

    if msg.tool_calls:
        try:
            extracted = json.loads(msg.tool_calls[0].function.arguments)
            raw_reply = extracted.pop("reply", "")
        except (json.JSONDecodeError, KeyError):
            pass
    elif msg.content:
        raw_reply = msg.content.strip()

    # Apply + validate extracted fields
    order, is_cream, errors = _apply_fields(order, extracted, is_cream)
    record.order_in_progress = order
    record.is_cream_cake = is_cream

    # Nếu có lỗi validation → gọi LLM lần 2 để tạo reply xin nhập lại
    if errors:
        error_context = "Thông tin vừa nhập có lỗi:\n" + "\n".join(f"- {e}" for e in errors)
        messages.append({"role": "assistant", "content": raw_reply or ""})
        messages.append({"role": "system", "content": error_context})
        try:
            r2 = await _call_plain(messages)
            raw_reply = (r2.choices[0].message.content or "").strip()
        except Exception:
            raw_reply = "\n".join(errors) + "\nAnh/chị vui lòng nhập lại giúp em ạ!"

    # Kiểm tra đủ thông tin → chuyển sang xác nhận
    ready = "__READY_TO_CONFIRM__" in raw_reply
    reply = raw_reply.replace("__READY_TO_CONFIRM__", "").strip()

    next_missing = order.next_missing_field(is_cream)

    if (ready or not next_missing) and not errors:
        if next_missing:
            # LLM nói sẵn sàng nhưng còn thiếu field — không chuyển, để tiếp tục
            pass
        else:
            unit_price = get_price(order.cake_type or "", order.size or "")
            record.state = ConversationState.CONFIRMING
            summary = format_order_summary(order, is_cream, unit_price)
            if reply:
                return record, reply + "\n\n" + summary
            return record, summary

    return record, reply
