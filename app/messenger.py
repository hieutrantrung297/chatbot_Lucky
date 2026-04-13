"""Facebook Messenger Graph API client."""

import hashlib
import hmac
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v19.0/me/messages"


def verify_webhook(token: str, challenge: str) -> str | None:
    """Xác minh webhook từ Facebook. Trả về challenge nếu token đúng, None nếu sai."""
    settings = get_settings()
    if token == settings.verify_token:
        return challenge
    return None


def verify_signature(payload: bytes, signature_header: str) -> bool:
    """Xác minh chữ ký X-Hub-Signature-256 từ Facebook."""
    settings = get_settings()
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.app_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


async def send_message(psid: str, text: str) -> bool:
    """Gửi tin nhắn văn bản tới user qua Facebook Messenger."""
    settings = get_settings()
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                GRAPH_API_URL,
                params={"access_token": settings.page_access_token},
                json=payload,
            )
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.error("Lỗi gửi tin nhắn tới %s: %s", psid, exc)
            return False


def parse_incoming(body: dict) -> list[tuple[str, str]]:
    """
    Parse webhook payload từ Facebook.
    Trả về list các (psid, text) — có thể nhiều message trong 1 request.
    """
    messages: list[tuple[str, str]] = []
    for entry in body.get("entry", []):
        for event in entry.get("messaging", []):
            psid = event.get("sender", {}).get("id")
            message = event.get("message", {})
            text = message.get("text", "").strip()
            # Bỏ qua echo (tin nhắn của chính page) và các event không phải text
            if psid and text and not message.get("is_echo"):
                messages.append((psid, text))
    return messages
