"""
CRUD operations for products and categories
Handles snacks/products inventory and category management
"""
from supabase import Client
from typing import List, Optional
from uuid import UUID
from app.schemas.product import ProductCreate, ProductUpdate, CategoryBase
from app.core.exceptions import NotFoundException
import asyncio


class CRUDProduct:
    """Optimized product CRUD with memory-efficient operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    # ========== Product Operations ==========

    async def create_product(self, product: ProductCreate) -> dict:
        """Create new product, returns created record"""
        data = product.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("products").insert(data).execute()
        )
        return response.data[0]

    async def get_product(self, product_id: UUID) -> Optional[dict]:
        """Get product by ID with safe fallback"""
        response = await asyncio.to_thread(
            lambda: self.client.table("products")
                .select("*")
                .eq("id", str(product_id))
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_products(
        self,
        skip: int = 0,
        limit: int = 20,
        category_id: Optional[UUID] = None,
        in_stock: Optional[bool] = True
    ) -> List[dict]:
        """Get products with optional filters"""
        def _fetch():
            query = self.client.table("products").select("*")
            if category_id:
                query = query.eq("category_id", str(category_id))
            if in_stock is not None:
                query = query.eq("is_active", in_stock)
            return query.range(skip, skip + limit - 1).execute()

        response = await asyncio.to_thread(_fetch)
        return response.data or []

    async def update_product(self, product_id: UUID, product_in: dict) -> Optional[dict]:
        """Update product, returns updated record"""
        if not product_in:
            return await self.get_product(product_id)

        # Execute update (Supabase returns count by default)
        await asyncio.to_thread(
            lambda: self.client.table("products")
                .update(product_in)
                .eq("id", str(product_id))
                .execute()
        )

        # Fetch the updated product
        return await self.get_product(product_id)

    async def delete_product(self, product_id: UUID) -> bool:
        """Soft-delete product by marking is_active=false.
        Hard delete is avoided because order_items references products via FK.
        """
        response = await asyncio.to_thread(
            lambda: self.client.table("products")
                .update({"is_active": False})
                .eq("id", str(product_id))
                .execute()
        )
        return bool(response.data)

    # ========== Category Operations ==========

    async def create_category(self, category: CategoryBase) -> dict:
        """Create new product category"""
        data = category.model_dump(mode='json')
        response = await asyncio.to_thread(
            lambda: self.client.table("product_categories").insert(data).execute()
        )
        return response.data[0]

    async def get_category(self, category_id: UUID) -> Optional[dict]:
        """Get category by ID"""
        response = await asyncio.to_thread(
            lambda: self.client.table("product_categories")
                .select("*")
                .eq("id", str(category_id))
                .maybe_single()
                .execute()
        )
        return response.data

    async def get_categories(self, skip: int = 0, limit: int = 20) -> List[dict]:
        """Get all active categories ordered by display_order"""
        response = await asyncio.to_thread(
            lambda: self.client.table("product_categories")
                .select("*")
                .eq("is_active", True)
                .order("display_order", desc=False)
                .range(skip, skip + limit - 1)
                .execute()
        )
        return response.data or []

    async def update_category(self, category_id: UUID, category_in: dict) -> Optional[dict]:
        """Update category, returns updated record"""
        if not category_in:
            return await self.get_category(category_id)

        # Execute update (Supabase returns count by default)
        await asyncio.to_thread(
            lambda: self.client.table("product_categories")
                .update(category_in)
                .eq("id", str(category_id))
                .execute()
        )

        # Fetch the updated category
        return await self.get_category(category_id)

    async def delete_category(self, category_id: UUID) -> bool:
        """Soft delete category by setting is_active to False"""
        response = await asyncio.to_thread(
            lambda: self.client.table("product_categories")
                .update({"is_active": False})
                .eq("id", str(category_id))
                .execute()
        )
        return bool(response.data)
