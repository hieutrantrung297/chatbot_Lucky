"""Quản lý tồn kho — bánh kem (available/unavailable) và bánh su kem (số lượng cụ thể)."""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_INVENTORY_PATH = Path(__file__).parent.parent / "data" / "inventory.json"


def _load() -> dict:
    try:
        return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Không đọc được inventory.json: %s", exc)
        return {}


def _save(data: dict) -> None:
    data["updated_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    _INVENTORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Query functions ───────────────────────────────────────────────────────────

def get_inventory_status() -> str:
    """Trả về trạng thái tồn kho dạng text để LLM trả lời khách."""
    inv = _load()
    lines = ["## Tồn kho hiện tại\n"]

    banh_kem = inv.get("banh_kem", {})
    lines.append("**Bánh Kem:**")
    for size, info in banh_kem.items():
        status = "✅ Có sẵn" if info.get("available", True) else "❌ Tạm hết / cần đặt trước"
        lines.append(f"  - {size}: {status}")

    su_kem = inv.get("banh_su_kem", {})
    qty = su_kem.get("quantity")
    if qty is None:
        su_status = "✅ Còn hàng"
    elif qty == 0:
        su_status = "❌ Hết hàng hôm nay"
    else:
        su_status = f"✅ Còn {qty} hộp"
    lines.append(f"\n**Bánh Su Kem:** {su_status}")

    updated = inv.get("updated_at", "")
    if updated:
        lines.append(f"\n_Cập nhật lúc: {updated}_")

    return "\n".join(lines)


def is_su_kem_available() -> tuple[bool, int | None]:
    """(available, quantity). quantity=None nếu không theo dõi số lượng."""
    inv = _load()
    qty = inv.get("banh_su_kem", {}).get("quantity")
    if qty is None:
        return True, None
    return qty > 0, qty


def is_banh_kem_available(size: str) -> bool:
    inv = _load()
    return inv.get("banh_kem", {}).get(size, {}).get("available", True)


# ── Update functions (chủ tiệm cập nhật) ─────────────────────────────────────

def set_su_kem_quantity(quantity: int) -> None:
    """Cập nhật số lượng bánh su kem còn lại."""
    inv = _load()
    if "banh_su_kem" not in inv:
        inv["banh_su_kem"] = {}
    inv["banh_su_kem"]["quantity"] = quantity
    _save(inv)
    logger.info("Cập nhật bánh su kem: còn %d hộp", quantity)


def set_banh_kem_available(size: str, available: bool) -> None:
    """Cập nhật trạng thái có sẵn của bánh kem theo size."""
    inv = _load()
    if "banh_kem" not in inv:
        inv["banh_kem"] = {}
    if size not in inv["banh_kem"]:
        inv["banh_kem"][size] = {}
    inv["banh_kem"][size]["available"] = available
    _save(inv)
    logger.info("Cập nhật bánh kem %s: available=%s", size, available)
