from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ConversationState(str, Enum):
    GREETING = "greeting"
    BROWSING = "browsing"
    SELECTING = "selecting"
    ORDERING = "ordering"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class CakeSize(str, Enum):
    SIZE_16CM = "16cm"
    SIZE_20CM = "20cm"
    SIZE_26CM = "26cm"
    SIZE_30CM = "30cm"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderInProgress(BaseModel):
    """Đơn hàng đang thu thập thông tin — tất cả field có thể None."""

    name: Optional[str] = None
    phone: Optional[str] = None
    cake_type: Optional[str] = None
    size: Optional[str] = None
    flavor: Optional[str] = None
    cake_message: Optional[str] = None   # Chữ ghi trên bánh (chỉ cho bánh kem/sinh nhật)
    delivery_date: Optional[str] = None  # DD/MM/YYYY
    address: Optional[str] = None
    special_requests: Optional[str] = None

    # Cờ nội bộ: đã xác định có phải bánh kem chưa (None = chưa xác định)
    _is_cream_cake: Optional[bool] = None

    def next_missing_field(self, is_cream_cake: bool) -> Optional[str]:
        """Trả về tên field tiếp theo cần thu thập, hoặc None nếu đã đủ."""
        fields = ["name", "phone", "cake_type", "size", "flavor"]
        # Thêm cake_message chỉ khi là bánh kem hoặc bánh sinh nhật
        if is_cream_cake:
            fields.append("cake_message")
        fields += ["delivery_date", "address"]

        for field in fields:
            if getattr(self, field) is None:
                return field
        return None

    def is_complete(self, is_cream_cake: bool) -> bool:
        return self.next_missing_field(is_cream_cake) is None


class Order(BaseModel):
    """Đơn hàng đã hoàn chỉnh, được lưu vào Google Sheets."""

    order_id: str
    psid: str
    name: str
    phone: str
    cake_type: str
    size: str
    flavor: str
    cake_message: Optional[str] = None
    delivery_date: str
    address: str
    special_requests: Optional[str] = None
    unit_price: float = 0.0
    delivery_fee: float = 0.0
    total_price: float = 0.0
    deposit_required: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = ""
    notes: Optional[str] = None


class ConversationRecord(BaseModel):
    """Toàn bộ trạng thái hội thoại của 1 user (keyed by PSID)."""

    psid: str
    state: ConversationState = ConversationState.GREETING
    order_in_progress: OrderInProgress = OrderInProgress()
    is_cream_cake: bool = False          # Được set khi cake_type đã thu thập
    message_history: list[dict] = []     # [{"role": "user"|"assistant", "content": "..."}]
    current_order_id: Optional[str] = None
    last_activity: str = ""
    created_at: str = ""

    model_config = {"arbitrary_types_allowed": True}
