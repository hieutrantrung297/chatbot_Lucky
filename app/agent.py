"""Browsing agent — tư vấn, FAQ, tra cứu đơn hàng bằng RAG + tool calling."""

import json
import logging

from openai import OpenAI, RateLimitError

from app.config import get_settings
from app.knowledge_base import search as kb_search

logger = logging.getLogger(__name__)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Tìm kiếm thông tin về sản phẩm, giá cả, chính sách tiệm, "
                "hướng dẫn chọn bánh, câu hỏi thường gặp. "
                "Dùng tool này trước khi trả lời bất kỳ câu hỏi nào về tiệm."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Nội dung cần tìm kiếm (tiếng Việt)",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": (
                "Kiểm tra tồn kho hiện tại: bánh kem có sẵn size nào, "
                "bánh su kem còn bao nhiêu hộp. "
                "Dùng khi khách hỏi 'còn bánh không', 'hết hàng chưa', 'còn size X không'."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_order_status",
            "description": "Tra cứu trạng thái đơn hàng của khách theo số điện thoại.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Số điện thoại khách hàng (chỉ gồm chữ số)",
                    }
                },
                "required": ["phone"],
            },
        },
    },
]

_SYSTEM_PROMPT = """\
Bạn là Lucky — nhân viên tư vấn thân thiện của tiệm bánh Lucky tại Hoài Nhơn, Bình Định.
Nhiệm vụ: tư vấn sản phẩm, giải đáp thắc mắc, chăm sóc khách hàng.

Quy tắc sử dụng tool:
- Với MỌI câu hỏi về sản phẩm, giá, chính sách, gợi ý, hướng dẫn — gọi search_knowledge TRƯỚC, rồi trả lời dựa trên kết quả.
- Khi khách hỏi "còn hàng không", "hết bánh chưa", "còn size X không" — gọi check_inventory.
- Khi khách muốn kiểm tra đơn hàng và cung cấp số điện thoại — gọi check_order_status.
- Khi khách muốn đặt bánh (nhắn "đặt bánh", "mua bánh", "order"...) — trả lời ngắn rồi kết thúc bằng token đặc biệt __START_ORDER__

Quy tắc trả lời:
- Trả lời tự nhiên, thân thiện, ngắn gọn bằng tiếng Việt. Dùng emoji vừa phải.
- Không bịa thông tin — chỉ dùng nội dung từ kết quả tool.
- Nếu không tìm thấy thông tin trong knowledge, trả lời thật thà và hướng khách liên hệ 0977192509.
"""


def _format_order_status(orders: list[dict]) -> str:
    """Định dạng kết quả tra cứu đơn hàng."""
    if not orders:
        return "Không tìm thấy đơn hàng nào với số điện thoại này."

    lines = [f"Em tìm thấy {len(orders)} đơn hàng:\n"]
    for o in orders:
        lines.append(
            f"🧾 Mã đơn: {o.get('order_id', '—')}\n"
            f"   🎂 {o.get('cake_type', '—')} {o.get('size', '')}\n"
            f"   📅 Ngày giao: {o.get('delivery_date', '—')}\n"
            f"   📌 Trạng thái: {_status_label(o.get('status', ''))}\n"
        )
    return "\n".join(lines)


def _status_label(status: str) -> str:
    return {
        "pending": "⏳ Chờ xác nhận",
        "confirmed": "✅ Đã xác nhận",
        "preparing": "🍰 Đang làm bánh",
        "delivering": "🚚 Đang giao",
        "completed": "✔️ Hoàn thành",
        "cancelled": "❌ Đã hủy",
    }.get(status, status)


def _get_gh_client() -> OpenAI:
    s = get_settings()
    return OpenAI(base_url=s.github_models_endpoint, api_key=s.github_token)


def _get_oa_client() -> OpenAI | None:
    s = get_settings()
    return OpenAI(api_key=s.openai_api_key) if s.openai_api_key else None


async def get_agent_response(
    message_history: list[dict],
    user_text: str,
) -> tuple[str, bool]:
    """
    Chạy browsing agent.
    Trả về (reply_text, wants_to_order).
    wants_to_order=True nếu khách muốn bắt đầu đặt hàng.
    """
    import asyncio

    settings = get_settings()
    gh_client = _get_gh_client()
    oa_client = _get_oa_client()

    async def _call(msgs):
        try:
            return await asyncio.to_thread(
                gh_client.chat.completions.create,
                model=settings.ai_model,
                messages=msgs,
                tools=_TOOLS,
                tool_choice="auto",
                max_tokens=600,
                temperature=0.7,
            )
        except RateLimitError:
            logger.warning("agent: GitHub Models rate limit — fallback OpenAI")
            if oa_client:
                return await asyncio.to_thread(
                    oa_client.chat.completions.create,
                    model=settings.openai_model,
                    messages=msgs,
                    tools=_TOOLS,
                    tool_choice="auto",
                    max_tokens=600,
                    temperature=0.7,
                )
            raise

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages += message_history[-20:]
    messages.append({"role": "user", "content": user_text})

    # Agent loop — tối đa 5 lượt tool call
    for _ in range(5):
        response = await _call(messages)

        msg = response.choices[0].message

        # Không có tool call → đây là câu trả lời cuối
        if not msg.tool_calls:
            reply = (msg.content or "").strip()
            if "__START_ORDER__" in reply:
                reply = reply.replace("__START_ORDER__", "").strip()
                return reply, True
            return reply, False

        # Thêm assistant turn vào messages
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Thực thi từng tool call
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            if fn_name == "search_knowledge":
                result = kb_search(fn_args.get("query", ""))
            elif fn_name == "check_inventory":
                from app.inventory import get_inventory_status
                result = get_inventory_status()
            elif fn_name == "check_order_status":
                from app.sheets import get_orders_by_phone
                orders = get_orders_by_phone(fn_args.get("phone", ""))
                result = _format_order_status(orders)
            else:
                result = "Tool không hợp lệ."

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    logger.warning("Agent loop đạt giới hạn 5 lượt tool call")
    return "Dạ xin lỗi anh/chị, em đang gặp sự cố. Vui lòng thử lại sau! 🙏", False
