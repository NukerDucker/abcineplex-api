from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

logging.basicConfig(level=logging.INFO)

from app.routes.auth import router as auth_router
from app.routes.movies import router as movies_router
from app.routes.showtimes import router as showtimes_router
from app.routes.bookings import router as bookings_router
from app.routes.users import router as users_router
from app.routes.review import router as reviews_router
from app.routes.public import router as public_router
from app.routes.payments import router as payments_router
from app.routes.products import router as products_router
from app.routes.orders import router as orders_router
from app.routes.admin import router as admin_router
from app.core.config import settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    generic_exception_handler,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="ABCineplex API",
    description="Movie booking system API — ABCineplex Group 4, KMITL",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Routers (auth first, then public routes, then admin)
for router in (
    auth_router,
    movies_router, showtimes_router, bookings_router, users_router,
    public_router, reviews_router, payments_router, products_router, orders_router,
    admin_router,  # Admin routes last
):
    app.include_router(router)


@app.get("/")
def root():
    return {"message": "ABCineplex API is running", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)