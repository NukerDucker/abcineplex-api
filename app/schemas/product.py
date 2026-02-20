from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from decimal import Decimal
from typing import Optional, List
from datetime import datetime

# --- Category Schemas ---
class CategoryBase(BaseModel):
    name: str
    display_order: int = 0

class Category(CategoryBase):
    id: UUID
    is_active: bool

    class Config:
        from_attributes = True

# --- Product Schemas ---
class ProductBase(BaseModel):
    name: str
    category_id: UUID
    price: Decimal = Field(..., max_digits=10, decimal_places=2)
    description: Optional[str] = None
    image_url: Optional[HttpUrl] = None
    in_stock: bool = True

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True