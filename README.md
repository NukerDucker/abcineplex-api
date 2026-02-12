# ABCineplex API - Theater Booking System

Complete Python/FastAPI backend for theater seat booking with automatic reservation expiry.

## Features

- 3 screens (Large: 100 seats, Medium: 60 seats, Small: 40 seats)
- Real-time seat availability
- Automatic 5-minute payment window
- Reserved seats automatically released after timeout
- Complete booking lifecycle: available → reserved → sold
- RESTful API with full documentation
- Background worker for expired reservation clean up

## Quick Start

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your Supabase credentials:

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Run Database Setup

Run the SQL schema from `/supabase_schema.sql` in your Supabase SQL Editor.

### 4. Start the Application

```bash
# Terminal 1: Start API server
uvicorn app.main:app --reload --port 8000

# Terminal 2: Start expiry worker
python -m app.workers.expiry_worker
```

Visit `http://localhost:8000/docs` for interactive API documentation.

## API Endpoints

### Booking Flow

1. **GET** `/api/bookings/screens` - Get all screens
2. **GET** `/api/bookings/screens/{id}/seats` - Get available seats
3. **POST** `/api/bookings/reserve` - Reserve seats (starts5-min timer)
4. **POST** `/api/bookings/confirm-payment` - Confirm payment (finalizes booking)
5. **POST** `/api/bookings/cancel` - Cancel reservation

### Information

- **GET** `/api/bookings/{booking_id}` - Get booking details
- **GET** `/api/bookings/user/{user_id}/bookings` - Get user's bookings
- **GET** `/api/bookings/{booking_id}/tickets` - Get tickets with QR codes
- **GET** `/api/bookings/stats/screens` - Get screen statistics

## Complete Documentation

See `PYTHON_IMPLEMENTATION_GUIDE.md` for:
- Complete API documentation
- Python client examples
- Payment gateway integration (Stripe)
- Production deployment guide
- Testing examples
- Troubleshooting

## Project Structure

```
abcineplex-api/
├── app/
│   ├── main.py              # FastAPI app
│   ├── core/
│   │   ├── config.py        # Settings
│   │   └── supabase.py      # Database client
│   ├── schemas/
│   │   └── booking.py       # Data models
│   ├── crud/
│   │   └── booking.py       # Database operations
│   ├── routes/
│   │   └── bookings.py      # API endpoints
│   └── workers/
│       └── expiry_worker.py # Background worker
├── .env                      # Configuration
└── requirements.txt          # Dependencies
```

## Example Request

### Reserve Seats

```bash
curl -X POST http://localhost:8000/api/bookings/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-uuid",
    "screen_id": "screen-uuid",
    "seat_ids": ["seat-1", "seat-2"],
    "price_per_seat": 15.00
  }'
```

**Response:**
```json
{
  "success": true,
  "booking_id": "booking-uuid",
  "payment_deadline": "2024-02-11T10:05:00Z",
  "total_amount": 30.00
}
```

## Support

For detailed implementation examples, see:
- `PYTHON_IMPLEMENTATION_GUIDE.md` - Complete Python guide
- `/docs` - Interactive API documentation
- `../supabase_schema.sql` - Database schema
- `../booking_implementation_guide.md` - General booking logic

## License

MIT
