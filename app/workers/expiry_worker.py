"""
Expiry Worker
Automatically releases expired seat reservations and deactivates past showtimes.
- Releases seat reservations held for more than 5 minutes without payment
- Deactivates showtimes where start_time + 40 minutes has passed (no late bookings)
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


async def deactivate_expired_showtimes_task():
    """Task to deactivate showtimes that started more than 40 minutes ago"""
    try:
        logger.info("Checking for expired showtimes...")

        # Call database function (atomic, efficient)
        result = await asyncio.to_thread(
            lambda: supabase.rpc('deactivate_expired_showtimes').execute()
        )

        data = result.data if result and result.data else {}
        deactivated_count = data.get('deactivated_count', 0)
        deactivated_ids = data.get('showtime_ids', [])

        if deactivated_count > 0:
            logger.info(f"✅ Deactivated {deactivated_count} expired showtime(s)")
            logger.info(f"   Showtime IDs: {deactivated_ids}")
        else:
            logger.info("No expired showtimes found")

        return data

    except Exception as e:
        logger.error(f"❌ Error deactivating expired showtimes: {e}")
        raise


async def run_worker(interval_seconds: int = 60):
    """
    Run the expiry worker in an infinite loop.
    Runs both seat release and showtime deactivation tasks.

    Args:
        interval_seconds: How often to check for expirations (default: 60 seconds)
    """
    logger.info(f"Expiry worker started - checking every {interval_seconds} seconds")

    while True:
        try:
            # Release expired seat reservations
            await release_expired_task()

            # Deactivate expired showtimes (ran 40+ minutes ago)
            await deactivate_expired_showtimes_task()

        except Exception as e:
            logger.error(f"Worker error: {e}")

        # Wait before next check
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker(interval_seconds=60))
