from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

from app.routes.movies import router as movies_router
from app.routes.showtimes import router as showtimes_router
from app.routes.public import router as public_router
from app.routes.bookings import router as bookings_router
from app.routes.users import router as users_router
from app.routes.auth import router as auth_router
from app.routes.review import router as reviews_router
from app.routes.products import router as products_router
from app.routes.orders import router as orders_router
from app.routes.profiles import router as profiles_router
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
    description="Movie booking system API",
    version="1.0.0",
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

# Routers
for router in (
    auth_router, movies_router, showtimes_router, public_router,
    bookings_router, users_router, reviews_router, products_router,
    orders_router, profiles_router,
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