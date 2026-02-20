"""
CRUD operations for orders
Handles snack order management and order items
"""
from supabase import Client
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from app.schemas.order import OrderCreate, OrderStatus
from app.core.exceptions import UnauthorizedException
import asyncio


class CRUDOrder:
    """Optimized order CRUD operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_order(self, user_id: UUID, order: OrderCreate) -> dict:
        """Create new snack order"""
        # Insert order with total amount calculated from items
        order_data = {
            "user_id": str(user_id),
            "status": OrderStatus.PENDING.value,
            "total_amount": 0,  # Will be calculated by database trigger
        }

        response = await asyncio.to_thread(
            lambda: self.client.table("orders")
                .insert(order_data)
                .select()
                .execute()
        )

        if not response.data:
            raise ValueError("Failed to create order")

        order_id = response.data[0]["id"]

        # Insert order items
        for item in order.items:
            item_data = {
                "order_id": order_id,
                "product_id": str(item.product_id),
                "quantity": item.quantity,
            }

            await asyncio.to_thread(
                lambda: self.client.table("order_items")
                    .insert(item_data)
                    .execute()
            )

        # Return full order with items
        return await self.get_order(order_id, user_id)

    async def get_order(
        self,
        order_id: UUID,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Get order by ID with authorization check"""
        response = await asyncio.to_thread(
            lambda: self.client.table("orders")
                .select("*, order_items(*)")
                .eq("id", str(order_id))
                .maybe_single()
                .execute()
        )

        order = response.data
        if not order:
            return None

        # Authorization check
        if not is_admin and UUID(order["user_id"]) != current_user_id:
            raise UnauthorizedException()

        return order

    async def get_user_orders(
        self,
        user_id: UUID,
        current_user_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        is_admin: bool = False
    ) -> List[dict]:
        """Get orders for a user with optional status filter"""
        # Authorization check
        if not is_admin and user_id != current_user_id:
            raise UnauthorizedException()

        def _fetch():
            query = self.client.table("orders") \
                .select("*, order_items(*)")

            if is_admin:
                # If admin, can filter by any user
                if user_id:
                    query = query.eq("user_id", str(user_id))
            else:
                # Non-admin can only see their own orders
                query = query.eq("user_id", str(current_user_id))

            if status:
                query = query.eq("status", status)

            return query \
                .order("created_at", desc=True) \
                .range(skip, skip + limit - 1) \
                .execute()

        response = await asyncio.to_thread(_fetch)
        return response.data or []

    async def get_all_orders(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        is_admin: bool = False
    ) -> List[dict]:
        """Get all orders (admin only)"""
        if not is_admin:
            raise UnauthorizedException()

        def _fetch():
            query = self.client.table("orders").select("*, order_items(*)")
            if status:
                query = query.eq("status", status)
            return query \
                .order("created_at", desc=True) \
                .range(skip, skip + limit - 1) \
                .execute()

        response = await asyncio.to_thread(_fetch)
        return response.data or []

    async def update_order_status(
        self,
        order_id: UUID,
        status: OrderStatus,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Update order status (admin only)"""
        if not is_admin:
            raise UnauthorizedException()

        response = await asyncio.to_thread(
            lambda: self.client.table("orders")
                .update({"status": status.value})
                .eq("id", str(order_id))
                .select("*, order_items(*)")
                .maybe_single()
                .execute()
        )

        return response.data

    async def cancel_order(
        self,
        order_id: UUID,
        current_user_id: UUID,
        is_admin: bool = False
    ) -> Optional[dict]:
        """Cancel order if still pending (user/admin)"""
        order = await self.get_order(order_id, current_user_id, is_admin)

        if not order:
            return None

        # Check if order can be cancelled
        if order["status"] != OrderStatus.PENDING.value and not is_admin:
            raise ValueError(f"Cannot cancel order with status: {order['status']}")

        response = await asyncio.to_thread(
            lambda: self.client.table("orders")
                .update({"status": OrderStatus.CANCELLED.value})
                .eq("id", str(order_id))
                .select("*, order_items(*)")
                .maybe_single()
                .execute()
        )

        return response.data

    async def delete_order(
        self,
        order_id: UUID,
        is_admin: bool = False
    ) -> bool:
        """Hard delete order (admin only)"""
        if not is_admin:
            raise UnauthorizedException()

        # Delete order items first
        await asyncio.to_thread(
            lambda: self.client.table("order_items")
                .delete()
                .eq("order_id", str(order_id))
                .execute()
        )

        # Delete order
        response = await asyncio.to_thread(
            lambda: self.client.table("orders")
                .delete()
                .eq("id", str(order_id))
                .execute()
        )

        return bool(response.data)
