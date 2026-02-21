"""
Expiry Worker
Automatically releases expired seat reservations every minute.
This worker calls the release_expired_reservations function to free up seats
that have been reserved for more than 5 minutes without payment.
"""
import asyncio
import logging
from datetime import datetime
from app.crud.booking import CRUDBooking
from app.core.supabase import supabase

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

crud_booking = CRUDBooking(supabase)

async def release_expired_task():
    """Task to release expired reservations"""
    try:
        logger.info("Starting expiry check...")
        result = await crud_booking.release_expired_reservations()

        released_count = result.get('released_count', 0)
        if released_count > 0:
            booking_ids = result.get('booking_ids', [])
            logger.info(f"✅ Released {released_count} expired reservation(s)")
            logger.info(f"   Booking IDs: {booking_ids}")
        else:
            logger.info("No expired reservations found")

        return result

    except Exception as e:
        logger.error(f"❌ Error in expiry worker: {e}")
        raise


async def run_worker(interval_seconds: int = 60):
    """
    Run the expiry worker in an infinite loop.

    Args:
        interval_seconds: How often to check for expired reservations (default: 60 seconds)
    """
    logger.info(f"Expiry worker started - checking every {interval_seconds} seconds")

    while True:
        try:
            await release_expired_task()
        except Exception as e:
            logger.error(f"Worker error: {e}")

        # Wait before next check
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker(interval_seconds=60))
