"""
Order API Routes
Handles snack order management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from uuid import UUID
import asyncio
import logging

from app.crud.order import CRUDOrder
from app.schemas.order import OrderCreate, OrderResponse, OrderStatus
from app.core.supabase import supabase_admin
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import NotFoundException, UnauthorizedException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])
crud_order = CRUDOrder(supabase_admin)


@router.post("/", response_model=OrderResponse)
async def create_order(
    order: OrderCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create new snack order"""
    result = await crud_order.create_order(UUID(current_user.user_id), order)

    return result


@router.get("/", response_model=List[OrderResponse])
async def get_orders(
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the current user's own orders. Admins use /admin/orders for all orders."""
    return await crud_order.get_user_orders(
        UUID(current_user.user_id),
        UUID(current_user.user_id),
        skip,
        limit,
        status,
        is_admin=False
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get specific order by ID"""
    try:
        order = await crud_order.get_order(
            UUID(order_id),
            UUID(current_user.user_id),
            is_admin=current_user.is_admin
        )
    except UnauthorizedException:
        raise NotFoundException("Order", order_id)

    if not order:
        raise NotFoundException("Order", order_id)
    return order


@router.get("/user/{user_id}", response_model=List[OrderResponse])
async def get_user_orders(
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get orders for a specific user (admin or own user only)"""
    return await crud_order.get_user_orders(
        UUID(user_id),
        UUID(current_user.user_id),
        skip,
        limit,
        status,
        is_admin=current_user.is_admin
    )


@router.patch("/{order_id}/status/{new_status}")
async def update_order_status(
    order_id: str,
    new_status: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update order status (admin only)"""
    if not current_user.is_admin:
        raise UnauthorizedException()

    try:
        status = OrderStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    try:
        updated = await crud_order.update_order_status(
            UUID(order_id),
            status,
            UUID(current_user.user_id),
            is_admin=True
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not updated:
        raise NotFoundException("Order", order_id)
    return updated


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel order if pending (user/admin)"""
    cancelled = await crud_order.cancel_order(
        UUID(order_id),
        UUID(current_user.user_id),
        is_admin=current_user.is_admin
    )

    if not cancelled:
        raise NotFoundException("Order", order_id)
    return cancelled


@router.delete("/{order_id}")
async def delete_order(
    order_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete order (admin only)"""
    if not current_user.is_admin:
        raise UnauthorizedException()

    success = await crud_order.delete_order(UUID(order_id), is_admin=True)
    if not success:
        raise NotFoundException("Order", order_id)
    return {"status": "success"}
