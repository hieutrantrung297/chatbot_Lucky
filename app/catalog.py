"""Quản lý danh mục sản phẩm từ data/catalog.json."""

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).parent.parent / "data" / "catalog.json"


@lru_cache
def load_catalog() -> dict:
    """Load catalog từ file JSON (cache sau lần đầu)."""
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def get_catalog_text() -> str:
    """Trả về mô tả catalog dạng text để inject vào system prompt."""
    catalog = load_catalog()
    lines = []
    for product in catalog["products"]:
        lines.append(f"\n### {product['name']}")
        lines.append(f"Mô tả: {product['description']}")
        lines.append(f"Hương vị: {', '.join(product['flavors'])}")
        lines.append("Bảng giá:")
        for size, info in product["sizes"].items():
            lines.append(f"  - {size}: {info['price']:,}đ ({info['serves']})")
        if product.get("note"):
            lines.append(f"Lưu ý: {product['note']}")
    return "\n".join(lines)


def get_price(cake_type: str, size: str) -> float:
    """Tìm giá bánh theo tên và size. Trả về 0 nếu không tìm thấy."""
    catalog = load_catalog()
    cake_type_lower = cake_type.lower()
    size_lower = size.lower()
    for product in catalog["products"]:
        if product["name"].lower() in cake_type_lower or cake_type_lower in product["name"].lower():
            if size_lower in product["sizes"]:
                return float(product["sizes"][size_lower]["price"])
    return 0.0


def calculate_delivery_fee(distance_km: float = 0.0) -> float:
    """Tính phí giao hàng theo khoảng cách (mặc định miễn phí nếu không biết)."""
    catalog = load_catalog()
    policies = catalog.get("policies", {})
    free_km = policies.get("free_delivery_km", 5)
    fee_per_km = policies.get("delivery_fee_per_km", 15000)
    if distance_km <= free_km:
        return 0.0
    return (distance_km - free_km) * fee_per_km


def get_min_order_days() -> int:
    catalog = load_catalog()
    return catalog.get("policies", {}).get("min_order_days", 2)
