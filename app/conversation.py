"""State machine — trung tâm điều phối hội thoại theo từng user (PSID)."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from app.ai_client import get_ai_response
from app.catalog import get_catalog_text
from app.config import get_settings
from app.models import ConversationRecord, ConversationState, OrderInProgress
from app.order_handler import get_first_question, process_ordering

logger = logging.getLogger(__name__)

# ── Per-user async lock để tránh race condition ──────────────────────────────
_user_locks: dict[str, asyncio.Lock] = {}


def _get_lock(psid: str) -> asyncio.Lock:
    if psid not in _user_locks:
        _user_locks[psid] = asyncio.Lock()
    return _user_locks[psid]


# ── Persistence helpers ──────────────────────────────────────────────────────

def _conversations_path() -> Path:
    settings = get_settings()
    path = Path(settings.data_dir) / "conversations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_all() -> dict:
    path = _conversations_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all(data: dict) -> None:
    path = _conversations_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_record(psid: str) -> ConversationRecord:
    all_data = _load_all()
    if psid in all_data:
        try:
            return ConversationRecord.model_validate(all_data[psid])
        except Exception:
            pass
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return ConversationRecord(psid=psid, created_at=now, last_activity=now)


def _save_record(record: ConversationRecord) -> None:
    all_data = _load_all()
    all_data[record.psid] = record.model_dump()
    _save_all(all_data)


# ── Keyword detection ────────────────────────────────────────────────────────

_ORDER_KEYWORDS = [
    "đặt bánh", "đặt hàng", "mua bánh", "order bánh",
    "muốn mua", "cần bánh", "đặt cho mình", "đặt cho tôi",
    "tôi muốn đặt", "mình muốn đặt", "cho mình đặt",
]


def _user_wants_to_order(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _ORDER_KEYWORDS)


# ── Main handler ─────────────────────────────────────────────────────────────

async def handle_message(psid: str, user_text: str) -> str:
    """
    Xử lý 1 tin nhắn từ user, trả về reply text.
    Toàn bộ logic được bảo vệ bởi per-user lock.
    """
    async with _get_lock(psid):
        record = _load_record(psid)
        record.last_activity = datetime.now().strftime("%d/%m/%Y %H:%M")

        # Thêm tin nhắn của user vào lịch sử
        record.message_history.append({"role": "user", "content": user_text})

        # ── Trạng thái đang đặt hàng → order_handler xử lý ──────────────────
        if record.state == ConversationState.ORDERING:
            record, reply = process_ordering(record, user_text)

        # ── Phát hiện ý định đặt hàng → chuyển sang ordering ─────────────────
        elif _user_wants_to_order(user_text) and record.state not in (
            ConversationState.CONFIRMED, ConversationState.ORDERING
        ):
            record.state = ConversationState.ORDERING
            record.order_in_progress = OrderInProgress()
            record.is_cream_cake = False
            reply = get_first_question()

        # ── Hội thoại tự do → AI xử lý ───────────────────────────────────────
        else:
            if record.state == ConversationState.GREETING:
                record.state = ConversationState.BROWSING

            catalog_text = get_catalog_text()
            order_summary = (
                record.order_in_progress.model_dump_json()
                if record.state == ConversationState.ORDERING
                else "Chưa có đơn hàng"
            )

            reply = get_ai_response(
                message_history=record.message_history[:-1],  # Không tính tin vừa append
                catalog_text=catalog_text,
                current_state=record.state.value,
                order_in_progress=order_summary,
            )

            # Nếu AI phát hiện khách muốn đặt hàng và đề nghị (dự phòng)
            order_trigger_in_reply = any(
                kw in reply.lower()
                for kw in ["để em hỗ trợ", "bắt đầu đặt hàng", "cho em biết tên"]
            )
            if order_trigger_in_reply and record.state != ConversationState.ORDERING:
                record.state = ConversationState.ORDERING
                record.order_in_progress = OrderInProgress()
                record.is_cream_cake = False
                reply = reply + "\n\n" + get_first_question()

        # Thêm phản hồi vào lịch sử
        record.message_history.append({"role": "assistant", "content": reply})

        # Giới hạn lịch sử tối đa 40 messages (20 turns)
        if len(record.message_history) > 40:
            record.message_history = record.message_history[-40:]

        _save_record(record)
        return reply
