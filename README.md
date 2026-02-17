# 🎬 ABCineplex API

A comprehensive FastAPI-based backend system for cinema booking management with real-time seat reservations, automated expiry handling, and complete movie theater operations.

## 📋 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Database Setup](#-database-setup)
- [Running the Application](#-running-the-application)
- [API Documentation](#-api-documentation)
- [Project Structure](#-project-structure)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)

## ✨ Features

### Booking Management
- **Real-time Seat Reservation**: Reserve seats with automatic 5-minute payment window
- **Automatic Expiry System**: Background worker releases expired reservations
- **Multi-Screen Support**: Manage multiple cinema screens with different capacities
- **Complete Booking Lifecycle**: Available → Reserved → Confirmed/Cancelled
- **QR Code Generation**: Unique QR codes for each ticket

### Movie Management
- **Movie CRUD Operations**: Create, read, update, and delete movies
- **Release Status Tracking**: Now showing, coming soon, ended
- **Genre Management**: Multiple genres per movie
- **Rich Metadata**: Posters, descriptions, ratings, duration

### Showtime Management
- **Flexible Scheduling**: Create showtimes for any movie and screen
- **Price Management**: Base pricing with potential seat modifiers
- **Seat Availability**: Real-time seat status per showtime

### User Management
- **Supabase Authentication**: Secure JWT-based authentication
- **User Profiles**: Extended user information and preferences
- **Booking History**: Track all user bookings
- **Loyalty Points System**: Track customer loyalty

### Public Content
- **Hero Carousel**: Dynamic homepage banner management
- **Promotional Events**: Marketing content and special offers
- **Public Movie Listings**: Browse movies without authentication

## 🛠 Tech Stack

- **Framework**: FastAPI 0.128.7
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth (JWT)
- **Validation**: Pydantic 2.12.5
- **Server**: Uvicorn 0.40.0
- **Package Manager**: [uv](https://github.com/astral-sh/uv)
- **Environment**: Python 3.13+

## 📦 Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) (Recommended)
- Supabase account and project
- Git (for version control)

## ⚙️ Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd abcineplex-api
```

### 2. Setup Environment and Dependencies

Using `uv` (Recommended):
```bash
# This will create a virtual environment and install all dependencies
uv sync
```

Alternatively, using standard `pip`:
```bash
# Create Virtual Environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install Dependencies
pip install -r requirements.txt
```

## 🔧 Configuration

### 1. Setup Environment Variables

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

### 2. Edit `.env` File

```env
# Supabase Database Connection (Direct Postgres connection)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres

# Supabase Project Configuration
SUPABASE_URL=https://[YOUR-PROJECT-REF].supabase.co
SUPABASE_ANON_KEY=[YOUR-ANON-KEY]

# Application Security
SECRET_KEY=your-super-secret-key-min-32-characters
DEBUG=True
```

**Where to find your Supabase credentials:**
- Go to your [Supabase Dashboard](https://app.supabase.com/)
- Select your project
- Navigate to **Settings** → **API**
- Copy the **URL** and **anon/public key**

## 🗄️ Database Setup

### 1. Access Supabase SQL Editor

1. Go to your Supabase project dashboard
2. Click **SQL Editor** in the left sidebar
3. Create a new query

### 2. Run Database Schema

You'll need to create the following tables and RPC functions in your Supabase database:

**Core Tables:**
- `users` - User profiles and authentication
- `movies` - Movie information
- `movie_genres` - Movie genre relationships
- `screens` - Cinema screens/theaters
- `seats` - Individual seats per screen
- `showtimes` - Movie screening times
- `bookings` - Booking records
- `tickets` - Individual tickets per booking
- `hero_carousel` - Homepage carousel slides
- `promo_events` - Promotional content

**Required RPC Functions:**
- `reserve_seats(p_user_id, p_screen_id, p_seat_ids, p_price_per_seat)`
- `confirm_payment(p_booking_id)`
- `cancel_booking(p_booking_id)`
- `release_expired_reservations()`

**Database Views:**
- `booking_details` - Detailed booking information with joins
- `screen_statistics` - Screen occupancy statistics

> **Note**: Contact your database administrator or refer to your Supabase schema documentation for the complete SQL setup scripts.

## 🚀 Running the Application

### Start the API Server

Using the helper script (Windows/PowerShell):
```powershell
./dev.ps1
```

Using `uv` directly:
```bash
# Development mode with auto-reload
uv run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Using standard `python`:
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Start the Expiry Worker (Required)

The expiry worker must run separately to automatically release expired seat reservations:

```bash
# Using uv
uv run python -m app.workers.expiry_worker

# Using standard python
python -m app.workers.expiry_worker
```

> **Important**: The expiry worker is critical for booking system functionality. Without it, expired reservations will never be released.

### Access the Application

- **API Endpoint**: http://localhost:8000
- **Interactive API Docs**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📚 API Documentation

### Authentication

All authenticated endpoints require a Bearer token from Supabase Auth.

**Header Format:**
```
Authorization: Bearer <supabase-access-token>
```

### API Endpoints

#### 🔐 Authentication

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/auth/me` | Get current user info | ✅ |

#### 🎬 Movies

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/movies` | List all movies | ❌ |
| GET | `/api/movies/{id}` | Get movie details | ❌ |
| POST | `/api/movies` | Create movie | ✅ |
| PUT | `/api/movies/{id}` | Update movie | ✅ |
| DELETE | `/api/movies/{id}` | Delete movie | ✅ |

**Query Parameters for GET /api/movies:**
- `skip` - Offset for pagination (default: 0)
- `limit` - Number of items (default: 20, max: 100)
- `status` - Filter by status: `NOW_SCREENING`, `COMING_SOON`

#### 🎭 Showtimes

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/showtimes/movie/{movie_id}` | Get showtimes for movie | ❌ |
| GET | `/api/showtimes/{id}` | Get showtime details | ❌ |
| GET | `/api/showtimes/{id}/seats` | Get seats for showtime | ❌ |
| POST | `/api/showtimes` | Create showtime | ✅ |
| PUT | `/api/showtimes/{id}` | Update showtime | ✅ |
| DELETE | `/api/showtimes/{id}` | Delete showtime | ✅ |

#### 🎫 Bookings

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/bookings/screens` | List all screens | ❌ |
| GET | `/api/bookings/screens/{id}` | Get screen details | ❌ |
| GET | `/api/bookings/screens/{id}/seats` | Get available seats | ❌ |
| GET | `/api/bookings/screens/{id}/seats/all` | Get all seats with status | ❌ |
| POST | `/api/bookings/reserve` | Reserve seats | ✅ |
| POST | `/api/bookings/confirm-payment` | Confirm payment | ✅ |
| POST | `/api/bookings/cancel` | Cancel booking | ✅ |
| GET | `/api/bookings/me` | Get my bookings | ✅ |
| GET | `/api/bookings/{id}` | Get booking details | ✅ |
| GET | `/api/bookings/{id}/tickets` | Get booking tickets | ✅ |
| GET | `/api/bookings/stats/screens` | Screen statistics | ✅ |

**Booking Flow:**

1. **Browse Seats**: `GET /api/bookings/screens/{id}/seats`
2. **Reserve Seats**: `POST /api/bookings/reserve` (starts 5-min timer)
3. **Process Payment**: (External payment gateway)
4. **Confirm Payment**: `POST /api/bookings/confirm-payment`
5. **Get Tickets**: `GET /api/bookings/{id}/tickets`

#### 👥 Users

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/users` | List users (admin) | ✅ |
| GET | `/api/users/{id}` | Get user details | ✅ |
| GET | `/api/users/email/{email}` | Get user by email | ✅ |
| PUT | `/api/users/{id}` | Update user | ✅ |
| DELETE | `/api/users/{id}` | Deactivate user | ✅ |

#### 🌐 Public Content

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/hero-carousel` | Get carousel slides | ❌ |
| GET | `/api/promo-events` | Get promotions | ❌ |
| POST | `/api/hero-carousel` | Create slide | ✅ |
| PUT | `/api/hero-carousel/{id}` | Update slide | ✅ |
| DELETE | `/api/hero-carousel/{id}` | Delete slide | ✅ |
| POST | `/api/promo-events` | Create promotion | ✅ |
| PUT | `/api/promo-events/{id}` | Update promotion | ✅ |
| DELETE | `/api/promo-events/{id}` | Delete promotion | ✅ |

### Example Requests

#### Reserve Seats

```bash
curl -X POST "http://localhost:8000/api/bookings/reserve" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-uuid",
    "screen_id": 1,
    "seat_ids": [1, 2, 3],
    "price_per_seat": 15.00
  }'
```

**Response:**
```json
{
  "success": true,
  "booking_id": 123,
  "payment_deadline": "2026-02-12T16:05:00",
  "total_amount": 45.00
}
```

#### Confirm Payment

```bash
curl -X POST "http://localhost:8000/api/bookings/confirm-payment" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": 123,
    "payment_intent_id": "pi_xxx"
  }'
```

#### Get Movies

```bash
curl -X GET "http://localhost:8000/api/movies?status=NOW_SCREENING&limit=10"
```

## 📁 Project Structure

```
abcineplex-api/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   │
│   ├── core/                   # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py          # Application configuration
│   │   ├── security.py        # JWT authentication
│   │   └── supabase.py        # Supabase client
│   │
│   ├── schemas/               # Pydantic models
│   │   ├── __init__.py
│   │   ├── auth.py           # Auth schemas
│   │   ├── booking.py        # Booking schemas
│   │   ├── movie.py          # Movie schemas
│   │   ├── public.py         # Public content schemas
│   │   ├── seat.py           # Seat schemas
│   │   ├── showtime.py       # Showtime schemas
│   │   └── user.py           # User schemas
│   │
│   ├── crud/                  # Database operations
│   │   ├── __init__.py
│   │   ├── booking.py        # Booking CRUD
│   │   ├── movie.py          # Movie CRUD
│   │   ├── public.py         # Public content CRUD
│   │   ├── showtime.py       # Showtime CRUD
│   │   └── user.py           # User CRUD
│   │
│   ├── routes/                # API endpoints
│   │   ├── __init__.py
│   │   ├── auth.py           # Auth endpoints
│   │   ├── bookings.py       # Booking endpoints
│   │   ├── movies.py         # Movie endpoints
│   │   ├── public.py         # Public endpoints
│   │   ├── showtimes.py      # Showtime endpoints
│   │   └── users.py          # User endpoints
│   │
│   └── workers/               # Background workers
│       ├── __init__.py
│       └── expiry_worker.py  # Booking expiry worker
│
├── .env                       # Environment variables (not in git)
├── .env.example              # Environment template
├── .gitignore                # Git ignore rules
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

## 💻 Development

### Code Style

This project follows Python best practices:

- **PEP 8** style guide
- **Type hints** for function parameters and returns
- **Docstrings** for all public functions and classes
- **Async/await** for all I/O operations

### Adding New Features

1. **Schema First**: Define Pydantic models in `app/schemas/`
2. **CRUD Operations**: Implement database logic in `app/crud/`
3. **API Routes**: Create endpoints in `app/routes/`
4. **Register Router**: Add router to `app/main.py`

### Testing

```bash
# Run the development server
uvicorn app.main:app --reload

# Access interactive docs for testing
# http://localhost:8000/docs
```

### Database Migrations

When updating the database schema:

1. Update your Supabase tables via SQL Editor
2. Update corresponding Pydantic schemas
3. Update CRUD operations if needed
4. Test thoroughly before deploying

## 🐛 Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Find process using port 8000
# Windows
netstat -ano | findstr :8000

# macOS/Linux
lsof -ti:8000

# Kill the process or use a different port
uvicorn app.main:app --port 8001
```

#### Supabase Connection Errors

- Verify your `.env` file has correct Supabase credentials
- Check if your Supabase project is active
- Ensure your IP is not blocked by Supabase

#### Import Errors

```bash
# Ensure you're in the virtual environment
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

#### Expiry Worker Not Running

The expiry worker MUST run separately:
```bash
python -m app.workers.expiry_worker
```

If bookings aren't expiring, check:
- Worker is running in a separate terminal
- Worker logs show no errors
- Database RPC function `release_expired_reservations` exists

### Logging

Enable debug logging by modifying `app/core/config.py`:

```python
debug: bool = True
```

View logs in console output from both the API server and expiry worker.

## 🚢 Deployment

### Production Checklist

- [ ] Set `debug: bool = False` in config
- [ ] Use strong `SECRET_KEY` (32+ characters)
- [ ] Configure proper CORS origins
- [ ] Use production database
- [ ] Enable HTTPS
- [ ] Set appropriate `ACCESS_TOKEN_EXPIRE_MINUTES`
- [ ] Configure proper logging
- [ ] Set up monitoring and alerting
- [ ] Run expiry worker as a system service
- [ ] Configure backup strategy

### Environment Variables for Production

```env
DEBUG=False
SECRET_KEY=<strong-random-key>
SUPABASE_URL=<production-url>
SUPABASE_ANON_KEY=<production-key>
```

## 📝 License

[Your License Here]

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📧 Support

For issues and questions:
- Open an issue on GitHub
- Contact: [Your Contact Info]

---

Built with ❤️ using FastAPI and Supabase
