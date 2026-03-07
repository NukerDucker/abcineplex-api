"""
CRUD operations for snack orders
Handles snack order management and order items
"""
from supabase import Client
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
from app.schemas.order import OrderCreate, OrderStatus
from app.core.exceptions import UnauthorizedException
import asyncio

_VALID_ORDER_TRANSITIONS: dict[str, set] = {
    "pending":   {"confirmed", "cancelled"},
    "confirmed": {"preparing", "cancelled"},
    "preparing": {"ready"},
    "ready":     {"completed"},
    "completed": set(),
    "cancelled": set(),
}


class CRUDOrder:
    """Optimized order CRUD operations"""
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    async def create_order(self, user_id: UUID, order: OrderCreate) -> dict:
        """Create new snack order"""
        # Fetch unit prices for all products in one query
        product_ids = list({str(item.product_id) for item in order.items})
        price_res = await asyncio.to_thread(
            lambda: self.client.table("products")
                .select("id, price")
                .in_("id", product_ids)
                .execute()
        )
        price_map = {row["id"]: row["price"] for row in (price_res.data or [])}

        # Calculate total amount
        total_amount = sum(
            float(price_map.get(str(item.product_id), 0)) * item.quantity
            for item in order.items
        )

        order_data = {
            "user_id": str(user_id),
            "order_status": OrderStatus.PENDING.value,
            "total_amount": total_amount,
        }

        response = await asyncio.to_thread(
            lambda: self.client.table("orders")
                .insert(order_data)
                .execute()
        )

        if not response.data:
            raise ValueError("Failed to create order")

        order_id = response.data[0]["id"]

        # Insert order items with unit_price
        for item in order.items:
            item_data = {
                "order_id": order_id,
                "product_id": str(item.product_id),
                "quantity": item.quantity,
                "unit_price": float(price_map.get(str(item.product_id), 0)),
            }

            await asyncio.to_thread(
                lambda d=item_data: self.client.table("order_items")
                    .insert(d)
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
                query = query.eq("order_status", status)

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
                query = query.eq("order_status", status)
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

        current = await self.get_order(order_id, current_user_id, is_admin=True)
        if not current:
            return None
        current_status = current.get("order_status", "")
        allowed = _VALID_ORDER_TRANSITIONS.get(current_status, set())
        if status.value not in allowed:
            raise ValueError(
                f"Cannot transition order from '{current_status}' to '{status.value}'"
            )

        await asyncio.to_thread(
            lambda: self.client.table("orders")
                .update({"order_status": status.value})
                .eq("id", str(order_id))
                .execute()
        )

        return await self.get_order(order_id, current_user_id, is_admin=True)

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
        if order["order_status"] != OrderStatus.PENDING.value and not is_admin:
            raise ValueError(f"Cannot cancel order with status: {order['order_status']}")

        await asyncio.to_thread(
            lambda: self.client.table("orders")
                .update({"order_status": OrderStatus.CANCELLED.value})
                .eq("id", str(order_id))
                .execute()
        )

        return await self.get_order(order_id, current_user_id, is_admin)

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
