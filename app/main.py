from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.movies import router as movies_router
from app.routes.showtimes import router as showtimes_router
from app.routes.public import router as public_router

app = FastAPI(
    title="ABCineplex API",
    description="Movie booking system API",
    version="1.0.0"
)

# Setup CORS so your Next.js frontend can talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],  # Next.js URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(movies_router)
app.include_router(showtimes_router)
app.include_router(public_router)


@app.get("/")
def root():
    return {
        "message": "ABCineplex API is running",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)