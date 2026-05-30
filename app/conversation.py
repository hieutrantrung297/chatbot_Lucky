"""State machine — trung tâm điều phối hội thoại theo từng user (PSID)."""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from app.agent import get_agent_response
from app.config import get_settings
from app.models import ConversationRecord, ConversationState, OrderInProgress
from app.order_agent import process_order_turn
from app.order_handler import get_first_question, process_confirming

ORDERING_TIMEOUT_HOURS = 5

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


# ── Main handler ─────────────────────────────────────────────────────────────

async def handle_message(psid: str, user_text: str) -> str:
    """Xử lý 1 tin nhắn từ user, trả về reply text."""
    async with _get_lock(psid):
        record = _load_record(psid)

        # ── Auto-reset sau timeout ────────────────────────────────────────────
        _reset_states = (
            ConversationState.ORDERING,
            ConversationState.CONFIRMING,
            ConversationState.CONFIRMED,
        )
        if record.state in _reset_states:
            try:
                last = datetime.strptime(record.last_activity, "%d/%m/%Y %H:%M")
                if datetime.now() - last > timedelta(minutes=ORDERING_TIMEOUT_HOURS):
                    record.state = ConversationState.BROWSING
                    record.order_in_progress = OrderInProgress()
                    record.is_cream_cake = False
                    record.message_history = []
                    logger.info("Auto-reset hội thoại %s sau timeout", psid)
            except (ValueError, TypeError):
                pass

        record.last_activity = datetime.now().strftime("%d/%m/%Y %H:%M")
        record.message_history.append({"role": "user", "content": user_text})

        # ── CONFIRMING: xác nhận / sửa / hủy đơn ────────────────────────────
        if record.state == ConversationState.CONFIRMING:
            record, reply = process_confirming(record, user_text)

        # ── ORDERING: agentic order agent ────────────────────────────────────
        elif record.state == ConversationState.ORDERING:
            record, reply = await process_order_turn(record, user_text)

        # ── Trạng thái còn lại: browsing agent (RAG + tools) ─────────────────
        else:
            if record.state in (ConversationState.GREETING, ConversationState.CONFIRMED):
                record.state = ConversationState.BROWSING

            reply, wants_order = await get_agent_response(
                message_history=record.message_history[:-1],
                user_text=user_text,
            )

            # Agent phát hiện khách muốn đặt hàng
            if wants_order:
                record.state = ConversationState.ORDERING
                record.order_in_progress = OrderInProgress()
                record.is_cream_cake = False
                first_q = get_first_question()
                reply = (reply + "\n\n" + first_q).strip() if reply else first_q

        # Lưu reply vào lịch sử
        record.message_history.append({"role": "assistant", "content": reply})

        # Giới hạn 40 messages
        if len(record.message_history) > 40:
            record.message_history = record.message_history[-40:]

        _save_record(record)
        return reply
