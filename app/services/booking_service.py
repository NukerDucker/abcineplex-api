"""
Booking Service Layer
Handles business logic for booking operations.
Note: Most operations now delegate to CRUD layer which uses Supabase RPC functions.
"""
from datetime import datetime, timedelta
from uuid import UUID
from app.core.supabase import supabase
from app.schemas.booking import ReserveSeatRequest
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


def calculate_payment_deadline() -> datetime:
    """Calculate payment deadline (5 minutes from now)"""
    return datetime.utcnow() + timedelta(minutes=5)


async def validate_seats_available(screen_id: int, seat_ids: List[int]) -> bool:
    """
    Validate that all requested seats are available.
    Returns True if all seats can be reserved, False otherwise.
    """
    try:
        response = supabase.table('seats')\
            .select('id, status')\
            .eq('screen_id', screen_id)\
            .in_('id', seat_ids)\
            .execute()

        if not response.data:
            return False

        # All seats must have status 'available'
        for seat in response.data:
            if seat['status'] != 'available':
                return False

        return True
    except Exception as e:
        logger.error(f"Error validating seats: {e}")
        raise


async def get_booking_summary(booking_id: int) -> Optional[Dict[str, Any]]:
    """Get a summary of a booking for confirmation"""
    try:
        response = supabase.table('bookings')\
            .select('*')\
            .eq('id', booking_id)\
            .single()\
            .execute()

        if not response.data:
            return None

        booking = response.data

        # Get tickets for this booking
        tickets_response = supabase.table('tickets')\
            .select('*, seats(row_label, seat_number)')\
            .eq('booking_id', booking_id)\
            .execute()

        tickets = []
        if tickets_response.data:
            tickets = [{
                'seat_id': t['seat_id'],
                'row_label': t['seats']['row_label'],
                'seat_number': t['seats']['seat_number'],
                'price': t['price_paid'],
                'qr_code': t['qr_code_slug']
            } for t in tickets_response.data]

        return {
            'booking_id': booking['id'],
            'user_id': booking['user_id'],
            'screen_id': booking['screen_id'],
            'status': booking['status'],
            'total_amount': booking['total_amount'],
            'payment_deadline': booking['payment_deadline'],
            'tickets': tickets
        }
    except Exception as e:
        logger.error(f"Error getting booking summary: {e}")
        raise
