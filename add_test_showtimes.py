#!/usr/bin/env python3
"""Add test showtimes to the database for testing the booking flow."""

import asyncio
import os
from datetime import datetime, timedelta
from app.core.supabase import supabase_admin

async def add_test_showtimes():
    """Insert test showtimes for movie 1319520."""

    # Get or create a screen first
    try:
        screens = await asyncio.to_thread(
            lambda: supabase_admin.table("screens").select("id").execute()
        )
        screen_ids = [s["id"] for s in (screens.data or [])]

        if not screen_ids:
            print("❌ No screens found in database. Please create a screen first.")
            print("\nTo create a screen, run:")
            print("""
supabase_admin.table("screens").insert({
    "name": "Hall A",
    "total_seats": 120
}).execute()
            """)
            return

        screen_id = screen_ids[0]
        print(f"✅ Using screen ID: {screen_id}")
    except Exception as e:
        print(f"❌ Error fetching screens: {e}")
        return

    # Create test showtimes for the next 7 days
    movie_id = 1319520
    base_price = 180.0

    showtimes_to_insert = []
    now = datetime.now()

    for day_offset in range(7):
        date = now + timedelta(days=day_offset)
        # Add 3 showtimes per day: 10 AM, 2 PM, 6 PM
        for hour in [10, 14, 18]:
            showtime = datetime(date.year, date.month, date.day, hour, 0)
            showtimes_to_insert.append({
                "movie_id": movie_id,
                "start_time": showtime.isoformat(),
                "base_price": base_price,
                "screen_id": screen_id,
            })

    try:
        result = await asyncio.to_thread(
            lambda: supabase_admin.table("showtimes").insert(showtimes_to_insert).execute()
        )
        inserted = len(result.data) if result.data else 0
        print(f"✅ Inserted {inserted} test showtimes for movie {movie_id}")
        print(f"\n📅 Showtimes created for the next 7 days:")
        print(f"   Times: 10:00 AM, 2:00 PM, 6:00 PM")
        print(f"   Price: {base_price}")
        print(f"\nNow reload the app and navigate to the movie booking page!")
    except Exception as e:
        print(f"❌ Error inserting showtimes: {e}")

if __name__ == "__main__":
    asyncio.run(add_test_showtimes())
