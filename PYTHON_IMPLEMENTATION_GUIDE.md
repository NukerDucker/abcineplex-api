# Theater Booking System - Python Backend Implementation Guide

## Overview

This is the complete Python/FastAPI backend implementation for the theater seat booking system with 3 screens (Large: 100 seats, Medium: 60 seats, Small: 40 seats) and automatic 5-minute payment expiry.

## Project Structure

```
abcineplex-api/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── core/
│   │   ├── config.py          # Configuration settings
│   │   └── supabase.py        # Supabase client
│   ├── schemas/
│   │   └── booking.py         # Pydantic models
│   ├── crud/
│   │   └── booking.py         # Database operations
│   ├── routes/
│   │   └── bookings.py        # API endpoints
│   └── workers/
│       └── expiry_worker.py   # Background worker
├── .env                        # Environment variables
├── requirements.txt           # Python dependencies
└── README.md
```

## Setup Instructions

### 1. Install Dependencies

```bash
cd abcineplex-api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here  # For admin operations

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Security
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=120

# Application
APP_NAME=abcineplex-api
DEBUG=True
```

### 3. Run Database Migrations

Run the SQL schema from `supabase_schema.sql` in your Supabase SQL Editor.

### 4. Start the Application

```bash
# Start the FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In a separate terminal, start the expiry worker
python -m app.workers.expiry_worker
```

The API will be available at `http://localhost:8000`
API documentation at `http://localhost:8000/docs`

## API Endpoints

### Seat Selection

#### Get All Screens
```http
GET /api/bookings/screens
```

**Response:**
```json
[
  {
    "screen_id": "uuid",
    "name": "Screen A",
    "size": "large",
    "total_seats": 100
  }
]
```

#### Get Available Seats for a Screen
```http
GET /api/bookings/screens/{screen_id}/seats
```

**Response:**
```json
[
  {
    "seat_id": "uuid",
    "row_label": "A",
    "seat_number": 1,
    "status": "available"
  }
]
```

#### Get All Seats (Including Reserved/Sold)
```http
GET /api/bookings/screens/{screen_id}/seats/all
```

### Booking Flow

#### Step 1: Reserve Seats
```http
POST /api/bookings/reserve
Content-Type: application/json

{
  "user_id": "user-uuid",
  "screen_id": "screen-uuid",
  "seat_ids": ["seat-uuid-1", "seat-uuid-2"],
  "price_per_seat": 15.00
}
```

**Success Response:**
```json
{
  "success": true,
  "booking_id": "booking-uuid",
  "payment_deadline": "2024-02-11T10:05:00Z",
  "total_amount": 30.00
}
```

**Failure Response:**
```json
{
  "success": false,
  "error": "Some seats are no longer available",
  "unavailable_seats": ["seat-uuid-1"]
}
```

#### Step 2: Confirm Payment
```http
POST /api/bookings/confirm-payment
Content-Type: application/json

{
  "booking_id": "booking-uuid",
  "payment_intent_id": "stripe_payment_id"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Payment confirmed successfully",
  "booking_id": "booking-uuid",
  "tickets": [
    {
      "ticket_id": "uuid",
      "booking_id": "uuid",
      "seat_id": "uuid",
      "row_label": "A",
      "seat_number": "1",
      "price_paid": 15.00,
      "qr_code_slug": "unique-qr-code"
    }
  ]
}
```

#### Cancel Booking
```http
POST /api/bookings/cancel
Content-Type: application/json

{
  "booking_id": "booking-uuid"
}
```

### Booking Information

#### Get Booking Details
```http
GET /api/bookings/{booking_id}
```

**Response:**
```json
{
  "booking_id": "uuid",
  "user_id": "uuid",
  "booking_status": "confirmed",
  "total_amount": 30.00,
  "payment_deadline": "2024-02-11T10:05:00Z",
  "created_at": "2024-02-11T10:00:00Z",
  "screen_name": "Screen A",
  "seats": ["A1", "A2"]
}
```

#### Get User's Bookings
```http
GET /api/bookings/user/{user_id}/bookings?status=confirmed
```

#### Get Tickets for Booking
```http
GET /api/bookings/{booking_id}/tickets
```

### Statistics

#### Get Screen Statistics
```http
GET /api/bookings/stats/screens
```

**Response:**
```json
[
  {
    "screen_id": "uuid",
    "screen_name": "Screen A",
    "total_seats": 100,
    "available_seats": 75,
    "reserved_seats": 5,
    "sold_seats": 18,
    "maintenance_seats": 2
  }
]
```

### Worker Endpoint

#### Release Expired Reservations (Internal)
```http
POST /api/bookings/internal/release-expired
```

## Python Client Examples

### Example 1: Complete Booking Flow

```python
import httpx
import asyncio
from datetime import datetime

BASE_URL = "http://localhost:8000"

async def complete_booking_flow():
    async with httpx.AsyncClient() as client:
        # 1. Get available screens
        response = await client.get(f"{BASE_URL}/api/bookings/screens")
        screens = response.json()
        screen_id = screens[0]['screen_id']
        print(f"Selected screen: {screens[0]['name']}")

        # 2. Get available seats
        response = await client.get(
            f"{BASE_URL}/api/bookings/screens/{screen_id}/seats"
        )
        seats = response.json()
        selected_seats = [seats[0]['seat_id'], seats[1]['seat_id']]
        print(f"Selected seats: {selected_seats}")

        # 3. Reserve seats
        reserve_data = {
            "user_id": "user-uuid-from-auth",
            "screen_id": screen_id,
            "seat_ids": selected_seats,
            "price_per_seat": 15.00
        }
        response = await client.post(
            f"{BASE_URL}/api/bookings/reserve",
            json=reserve_data
        )
        reservation = response.json()

        if not reservation['success']:
            print(f"Reservation failed: {reservation['error']}")
            return

        booking_id = reservation['booking_id']
        payment_deadline = reservation['payment_deadline']
        print(f"Booking ID: {booking_id}")
        print(f"Payment deadline: {payment_deadline}")

        # 4. Simulate payment processing
        # In real app, integrate with Stripe/PayPal here
        await asyncio.sleep(2)  # Simulate payment gateway
        payment_successful = True

        if payment_successful:
            # 5. Confirm payment
            confirm_data = {
                "booking_id": booking_id,
                "payment_intent_id": "stripe_pi_123456"
            }
            response = await client.post(
                f"{BASE_URL}/api/bookings/confirm-payment",
                json=confirm_data
            )
            confirmation = response.json()

            if confirmation['success']:
                print("✅ Booking confirmed!")
                print(f"Tickets: {confirmation['tickets']}")
            else:
                print(f"❌ Confirmation failed: {confirmation['message']}")

# Run the example
asyncio.run(complete_booking_flow())
```

### Example 2: Check User's Bookings

```python
import httpx
import asyncio

async def get_user_bookings(user_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8000/api/bookings/user/{user_id}/bookings",
            params={"status": "confirmed"}
        )
        data = response.json()

        print(f"Total bookings: {data['total_count']}")
        for booking in data['bookings']:
            print(f"\nBooking ID: {booking['booking_id']}")
            print(f"Screen: {booking['screen_name']}")
            print(f"Seats: {', '.join(booking['seats'])}")
            print(f"Total: ${booking['total_amount']}")

asyncio.run(get_user_bookings("user-uuid"))
```

### Example 3: Real-time Seat Availability Check

```python
import httpx
import asyncio

async def monitor_seat_availability(screen_id: str):
    """Poll seat availability every 5 seconds"""
    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"http://localhost:8000/api/bookings/screens/{screen_id}/seats/all"
            )
            seats = response.json()

            available = sum(1 for s in seats if s['status'] == 'available')
            reserved = sum(1 for s in seats if s['status'] == 'reserved')
            sold = sum(1 for s in seats if s['status'] == 'sold')

            print(f"\r Available: {available} | Reserved: {reserved} | Sold: {sold}", end='')

            await asyncio.sleep(5)

asyncio.run(monitor_seat_availability("screen-uuid"))
```

### Example 4: Cancel Booking

```python
import httpx

async def cancel_booking(booking_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/bookings/cancel",
            json={"booking_id": booking_id}
        )
        result = response.json()

        if result['success']:
            print("✅ Booking cancelled successfully")
        else:
            print(f"❌ Cancellation failed: {result['message']}")
```

## Integrating with Payment Gateways

### Stripe Integration Example

```python
import stripe
from fastapi import APIRouter, HTTPException
from app.crud.booking import CRUDBooking
from app.core.supabase import supabase

stripe.api_key = "sk_test_your_stripe_key"

router = APIRouter(prefix="/api/payments", tags=["payments"])
crud_booking = CRUDBooking(supabase)

@router.post("/create-payment-intent")
async def create_payment_intent(booking_id: str):
    """Create Stripe payment intent for a booking"""
    try:
        # Get booking details
        booking = await crud_booking.get_booking_by_id(booking_id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        if booking['status'] != 'pending':
            raise HTTPException(status_code=400, detail="Booking is not pending")

        # Create Stripe payment intent
        intent = stripe.PaymentIntent.create(
            amount=int(booking['total_amount'] * 100),  # Convert to cents
            currency="usd",
            metadata={"booking_id": booking_id}
        )

        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, "whsec_your_webhook_secret"
        )

        if event['type'] == 'payment_intent.succeeded':
            payment_intent = event['data']['object']
            booking_id = payment_intent['metadata']['booking_id']

            # Confirm the booking
            await crud_booking.confirm_payment(
                booking_id,
                payment_intent['id']
            )

            print(f"✅ Payment successful for booking {booking_id}")

        return {"status": "success"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

## Running the Expiry Worker

The expiry worker automatically releases expired reservations every minute.

### Option 1: Run as Separate Process

```bash
# Terminal 1: Start FastAPI server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Start expiry worker
python -m app.workers.expiry_worker
```

### Option 2: Using Supervisor (Production)

Create `/etc/supervisor/conf.d/abcineplex.conf`:

```ini
[program:abcineplex-api]
command=/path/to/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
directory=/path/to/abcineplex-api
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/abcineplex-api.err.log
stdout_logfile=/var/log/abcineplex-api.out.log

[program:abcineplex-worker]
command=/path/to/venv/bin/python -m app.workers.expiry_worker
directory=/path/to/abcineplex-api
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/abcineplex-worker.err.log
stdout_logfile=/var/log/abcineplex-worker.out.log
```

Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start abcineplex-api
sudo supervisorctl start abcineplex-worker
```

### Option 3: Using systemd

Create `/etc/systemd/system/abcineplex-worker.service`:

```ini
[Unit]
Description=ABCineplex Expiry Worker
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/abcineplex-api
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python -m app.workers.expiry_worker
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable abcineplex-worker
sudo systemctl start abcineplex-worker
sudo systemctl status abcineplex-worker
```

## Testing

### Manual Testing with cURL

```bash
# 1. Get screens
curl http://localhost:8000/api/bookings/screens

# 2. Get available seats
curl http://localhost:8000/api/bookings/screens/{screen_id}/seats

# 3. Reserve seats
curl -X POST http://localhost:8000/api/bookings/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-uuid",
    "screen_id": "screen-uuid",
    "seat_ids": ["seat-1", "seat-2"],
    "price_per_seat": 15.00
  }'

# 4. Confirm payment
curl -X POST http://localhost:8000/api/bookings/confirm-payment \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "booking-uuid",
    "payment_intent_id": "payment-id"
  }'

# 5. Manually trigger expiry release
curl -X POST http://localhost:8000/api/bookings/internal/release-expired
```

### Automated Testing with pytest

Create `tests/test_booking.py`:

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_get_screens():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/bookings/screens")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        assert "screen_id" in data[0]

@pytest.mark.asyncio
async def test_reserve_seats():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First get available seats
        screens_response = await client.get("/api/bookings/screens")
        screen_id = screens_response.json()[0]['screen_id']

        # Reserve seats
        reserve_data = {
            "user_id": "test-user",
            "screen_id": screen_id,
            "seat_ids": ["test-seat-1"],
            "price_per_seat": 15.00
        }
        response = await client.post("/api/bookings/reserve", json=reserve_data)
        assert response.status_code == 200
        data = response.json()
        assert "booking_id" in data
```

Run tests:
```bash
pytest tests/ -v
```

## Troubleshooting

### Issue: Seats stuck in reserved state

**Solution:**
```bash
# Manually trigger release
curl -X POST http://localhost:8000/api/bookings/internal/release-expired
```

### Issue: Worker not starting

**Check logs:**
```bash
# If using systemd
sudo journalctl -u abcineplex-worker -f

# If running manually
python -m app.workers.expiry_worker
```

### Issue: Database connection errors

**Check Supabase credentials in `.env`:**
```bash
# Test connection
python -c "from app.core.supabase import supabase; print(supabase.table('screens').select('*').execute())"
```

## Production Deployment

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Start both API and worker
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 & python -m app.workers.expiry_worker
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
      - SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
    restart: unless-stopped

  worker:
    build: .
    command: python -m app.workers.expiry_worker
    environment:
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
    restart: unless-stopped
```

Run:
```bash
docker-compose up -d
```

## Next Steps

1. Add authentication middleware
2. Implement payment gateway (Stripe/PayPal)
3. Add email notifications for bookings
4. Implement QR code generation for tickets
5. Add rate limiting
6. Set up monitoring and alerting
7. Add caching with Redis
