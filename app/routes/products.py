"""
Product and Category API Routes
Handles all snack product and category endpoints
"""
from fastapi import APIRouter, Depends
from typing import List
from uuid import UUID

from app.crud.product import CRUDProduct
from app.schemas.product import (
    Product, ProductCreate, ProductUpdate,
    Category, CategoryBase
)
from app.core.supabase import supabase
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import NotFoundException

router = APIRouter(prefix="/api/products", tags=["products"])
crud_product = CRUDProduct(supabase)


# ========== Category Endpoints (must be before {product_id} routes) ==========

@router.post("/categories", response_model=Category)
async def create_category(
    category: CategoryBase,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create product category (admin only)"""
    if not current_user.is_admin:
        raise NotFoundException("You are not authorized to create categories")

    return await crud_product.create_category(category)


@router.get("/categories", response_model=List[Category])
async def get_categories(
    skip: int = 0,
    limit: int = 20,
):
    """Get product categories (public endpoint)"""
    return await crud_product.get_categories(skip, limit)


@router.get("/categories/{category_id}", response_model=Category)
async def get_category(category_id: str):
    """Get category by ID (public endpoint)"""
    category = await crud_product.get_category(UUID(category_id))
    if not category:
        raise NotFoundException("Category", category_id)
    return category


@router.put("/categories/{category_id}", response_model=Category)
async def update_category(
    category_id: str,
    category_in: CategoryBase,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update category (admin only)"""
    if not current_user.is_admin:
        raise NotFoundException("You are not authorized to update categories")

    data = category_in.model_dump(exclude_unset=True, mode='json')
    updated = await crud_product.update_category(UUID(category_id), data)
    if not updated:
        raise NotFoundException("Category", category_id)
    return updated


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete category (admin only)"""
    if not current_user.is_admin:
        raise NotFoundException("You are not authorized to delete categories")

    success = await crud_product.delete_category(UUID(category_id))
    if not success:
        raise NotFoundException("Category", category_id)
    return {"status": "success"}


# ========== Product Endpoints ==========

@router.post("/", response_model=Product)
async def create_product(
    product: ProductCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create new product (admin only)"""
    if not current_user.is_admin:
        raise NotFoundException("You are not authorized to create products")

    return await crud_product.create_product(product)


@router.get("/", response_model=List[Product])
async def get_products(
    skip: int = 0,
    limit: int = 20,
    category_id: str = None,
    in_stock: bool = True,
):
    """Get products with optional filters (public endpoint)"""
    category_uuid = UUID(category_id) if category_id else None
    return await crud_product.get_products(skip, limit, category_uuid, in_stock)


@router.get("/{product_id}", response_model=Product)
async def get_product(product_id: str):
    """Get product by ID (public endpoint)"""
    product = await crud_product.get_product(UUID(product_id))
    if not product:
        raise NotFoundException("Product", product_id)
    return product


@router.put("/{product_id}", response_model=Product)
async def update_product(
    product_id: str,
    product_in: ProductUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update product (admin only)"""
    if not current_user.is_admin:
        raise NotFoundException("You are not authorized to update products")

    data = product_in.model_dump(exclude_unset=True, mode='json')
    updated = await crud_product.update_product(UUID(product_id), data)
    if not updated:
        raise NotFoundException("Product", product_id)
    return updated


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete product (admin only)"""
    if not current_user.is_admin:
        raise NotFoundException("You are not authorized to delete products")

    success = await crud_product.delete_product(UUID(product_id))
    if not success:
        raise NotFoundException("Product", product_id)
    return {"status": "success"}
