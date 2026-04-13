"""AI client dùng GitHub Models API (OpenAI-compatible) với model gpt-4o-mini."""

import logging
from pathlib import Path

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
_system_prompt_template: str | None = None


def _load_system_prompt() -> str:
    global _system_prompt_template
    if _system_prompt_template is None:
        _system_prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt_template


def _get_client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        base_url=settings.github_models_endpoint,
        api_key=settings.github_token,
    )


def build_system_message(catalog_text: str, current_state: str, order_in_progress: str) -> str:
    """Tạo system message với context hiện tại được inject vào."""
    template = _load_system_prompt()
    return template.format(
        catalog_text=catalog_text,
        current_state=current_state,
        order_in_progress=order_in_progress,
    )


def get_ai_response(
    message_history: list[dict],
    catalog_text: str,
    current_state: str,
    order_in_progress: str,
) -> str:
    """
    Gọi GitHub Models API để lấy phản hồi AI.
    message_history: list của {"role": "user"|"assistant", "content": "..."}
    """
    settings = get_settings()
    client = _get_client()

    system_content = build_system_message(catalog_text, current_state, order_in_progress)

    # Giới hạn lịch sử để tiết kiệm token
    max_msgs = settings.max_history_messages
    trimmed_history = message_history[-max_msgs:] if len(message_history) > max_msgs else message_history

    messages = [{"role": "system", "content": system_content}] + trimmed_history

    try:
        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=messages,
            max_tokens=500,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Lỗi gọi AI API: %s", exc)
        return "Dạ xin lỗi anh/chị, em đang gặp sự cố kỹ thuật. Anh/chị vui lòng thử lại sau ít phút nhé! 🙏"
