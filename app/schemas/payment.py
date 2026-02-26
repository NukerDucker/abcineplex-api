"""Payment schema definitions for mock payment system (§5.7)"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class PaymentInitiateRequest(BaseModel):
    """Request to initiate a payment for a booking"""
    booking_id: UUID = Field(..., description="Booking ID (UUID)")
    payment_method: str = Field(
        default="mock_card",
        pattern="^(mock_card|mock_qr|mock_cash)$",
        description="Payment method: mock_card | mock_qr | mock_cash",
    )
    mock_should_succeed: bool = Field(
        default=True,
        description="For testing: True = payment succeeds, False = payment fails",
    )


class PaymentInitiateResponse(BaseModel):
    """Response after initiating a payment"""
    payment_id: str = Field(..., description="Payment ID")
    status: str = Field(..., description="Payment status: pending")
    amount: float = Field(..., description="Payment amount")
    payment_method: str = Field(..., description="Payment method used")


class PaymentConfirmRequest(BaseModel):
    """Request to confirm a payment result"""
    mock_result: bool = Field(
        default=True,
        description="Mock result: True = success, False = failure",
    )


class PaymentConfirmResponse(BaseModel):
    """Response after confirming a payment"""
    payment_id: str = Field(..., description="Payment ID")
    status: str = Field(..., description="Payment status: success | failed")
    booking_id: UUID = Field(..., description="Associated booking ID")
    booking_status: Optional[str] = Field(None, description="Updated booking status")
    points_earned: Optional[int] = Field(None, description="Reward points earned")
    message: Optional[str] = Field(None, description="Status message")


class PaymentStatusResponse(BaseModel):
    """Response with payment status details"""
    payment_id: str = Field(..., description="Payment ID")
    booking_id: UUID = Field(..., description="Associated booking ID")
    status: str = Field(..., description="Payment status")
    amount: float = Field(..., description="Payment amount")
    payment_method: str = Field(..., description="Payment method")
    paid_at: Optional[datetime] = Field(None, description="Payment completion timestamp")
