"""FastAPI app — điểm vào chính của chatbot."""

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.conversation import handle_message
from app.messenger import parse_incoming, send_message, verify_signature, verify_webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Lucky Cake Chatbot", version="1.0.0")


@app.get("/")
async def health_check():
    """Health check endpoint — dùng để kiểm tra server đang chạy."""
    return {"status": "ok", "service": "Lucky Cake Chatbot"}


@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    Facebook gọi endpoint này để xác minh webhook khi cấu hình lần đầu.
    Query params: hub.mode, hub.verify_token, hub.challenge
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe":
        result = verify_webhook(token or "", challenge or "")
        if result:
            return PlainTextResponse(result)
        raise HTTPException(status_code=403, detail="Token xác minh không hợp lệ")

    return {"status": "ok"}


@app.post("/webhook")
async def webhook_receive(request: Request, background_tasks: BackgroundTasks):
    """
    Facebook gửi các sự kiện tin nhắn tới đây.
    Trả về 200 ngay lập tức, xử lý async để tránh timeout.
    """
    body_bytes = await request.body()

    # Xác minh chữ ký (bảo mật)
    signature = request.headers.get("X-Hub-Signature-256", "")
    if signature and not verify_signature(body_bytes, signature):
        logger.warning("Chữ ký webhook không hợp lệ — bỏ qua request")
        raise HTTPException(status_code=403, detail="Chữ ký không hợp lệ")

    body = await request.json() if not body_bytes else __import__("json").loads(body_bytes)

    # Xử lý tất cả tin nhắn trong background
    messages = parse_incoming(body)
    for psid, text in messages:
        background_tasks.add_task(_process_and_reply, psid, text)

    return {"status": "ok"}


async def _process_and_reply(psid: str, text: str) -> None:
    """Xử lý tin nhắn và gửi phản hồi."""
    try:
        reply = await handle_message(psid, text)
        await send_message(psid, reply)
    except Exception as exc:
        logger.error("Lỗi xử lý tin nhắn từ %s: %s", psid, exc)
        # Gửi tin nhắn lỗi thân thiện tới user
        try:
            await send_message(
                psid,
                "Dạ xin lỗi anh/chị, em đang gặp sự cố kỹ thuật. "
                "Anh/chị vui lòng thử lại sau ít phút nhé! 🙏",
            )
        except Exception:
            pass
