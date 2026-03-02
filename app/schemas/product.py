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
    is_active: bool = True
    stock_quantity: int = 0

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[UUID] = None
    price: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    description: Optional[str] = None
    image_url: Optional[HttpUrl] = None
    is_active: Optional[bool] = None
    stock_quantity: Optional[int] = None

class Product(ProductBase):
    id: UUID
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
