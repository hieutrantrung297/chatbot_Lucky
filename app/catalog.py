"""Quản lý danh mục sản phẩm từ data/products.json."""

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_PRODUCTS_PATH = Path(__file__).parent.parent / "data" / "products.json"


@lru_cache
def _load_products() -> dict:
    return json.loads(_PRODUCTS_PATH.read_text(encoding="utf-8"))


def get_catalog_text() -> str:
    """Trả về mô tả catalog dạng text để inject vào order_agent system prompt."""
    data = _load_products()
    lines = []
    for product in data["products"]:
        lines.append(f"\n### {product['name']}")
        lines.append("Bảng giá:")
        for size, price in product["prices"].items():
            lines.append(f"  - {size}: {price:,}đ")
    return "\n".join(lines)


def get_price(cake_type: str, size: str) -> float:
    """Tìm giá bánh theo tên và size. Trả về 0 nếu không tìm thấy."""
    data = _load_products()
    cake_lower = cake_type.lower()
    size_lower = size.lower()
    for product in data["products"]:
        name_lower = product["name"].lower()
        if name_lower in cake_lower or cake_lower in name_lower:
            if size_lower in product["prices"]:
                return float(product["prices"][size_lower])
    return 0.0


def calculate_delivery_fee(distance_km: float = 0.0) -> float:
    """Tính phí giao hàng theo khoảng cách (mặc định miễn phí nếu không biết)."""
    data = _load_products()
    delivery = data.get("delivery", {})
    free_km = delivery.get("free_km", 5)
    fee_per_km = delivery.get("fee_per_km", 10000)
    if distance_km <= free_km:
        return 0.0
    return (distance_km - free_km) * fee_per_km


def get_min_order_days(cake_type: str = "") -> int:
    """Số ngày đặt trước tối thiểu. Truyền cake_type để lấy chính xác theo loại bánh."""
    data = _load_products()
    if cake_type:
        cake_lower = cake_type.lower()
        for product in data["products"]:
            name_lower = product["name"].lower()
            if name_lower in cake_lower or cake_lower in name_lower:
                return product.get("min_order_days", data.get("default_min_days", 1))
    return data.get("default_min_days", 1)
