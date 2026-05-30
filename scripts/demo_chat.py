"""Demo script: chạy cuộc trò chuyện mẫu với chatbot."""
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


async def run_conv(title: str, psid: str, turns: list[str]):
    from app.conversation import handle_message
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    for msg in turns:
        print(f"\n[User] {msg}")
        reply = await handle_message(psid, msg)
        print(f"[Bot]  {reply}")


async def main():
    delivery = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y")

    with patch("app.sheets.append_order"), \
         patch("app.sheets.get_orders_by_phone", return_value=[]):

        # TC-1: Hỏi thông tin
        await run_conv("TC-1: FAQ - Hỏi giá & địa chỉ", "demo_faq", [
            "Xin chào, bánh kem sinh nhật 20cm giá bao nhiêu?",
            "Tiệm ở đâu vậy?",
        ])

        # TC-2: Happy path đặt hàng
        await run_conv("TC-2: Happy path - đặt bánh kem sinh nhật", "demo_order", [
            "tôi muốn đặt bánh sinh nhật",
            "Tên tôi là Nguyen Hieu, số điện thoại 0901234567",
            "Banh Kem Sinh Nhat",
            "20cm",
            "Vanilla",
            "Happy Birthday Lan",
            delivery,
            "97 Nguyen Chi Thanh, Hoai Nhon",
            "xac nhan",
        ])

        # TC-3: Sửa field ở bước xác nhận
        await run_conv("TC-3: Sua field o buoc xac nhan", "demo_edit", [
            "dat banh",
            "Minh Duc",
            "0912345678",
            "Banh Kem Co Ban",
            "16cm",
            "Dau",
            delivery,
            "50 Le Loi",
            "sua huong vi",          # sửa hương vị
            "Socola",
            "xac nhan",
        ])

        # TC-4: Hủy đơn
        await run_conv("TC-4: Huy don hang", "demo_cancel", [
            "dat banh",
            "Lan",
            "0945678901",
            "thoi huy",
        ])


if __name__ == "__main__":
    asyncio.run(main())
