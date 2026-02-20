from pydantic import BaseModel, Field
from uuid import UUID
from decimal import Decimal
from typing import List, Optional
from datetime import datetime
from enum import Enum

# --- Enums for strict validation ---

class OrderStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class OrderItemBase(BaseModel):
    product_id: UUID
    quantity: int = Field(..., gt=0, example=1)

class OrderItemCreate(OrderItemBase):
    pass

class OrderItem(OrderItemBase):
    id: UUID
    unit_price: Decimal
    subtotal: Decimal

    class Config:
        from_attributes = True

# --- Order Schemas ---
class OrderCreate(BaseModel):
    # This is what the frontend sends
    items: List[OrderItemCreate]

class OrderResponse(BaseModel):
    # This is what the API returns
    id: UUID
    user_id: Optional[UUID]
    status: OrderStatus
    total_amount: Decimal
    items: List[OrderItem]
    created_at: datetime

    class Config:
        from_attributes = True