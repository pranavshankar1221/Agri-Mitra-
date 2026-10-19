import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.api import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    docs_url=None if settings.APP_ENV.casefold() == "production" else "/docs",
    redoc_url=None if settings.APP_ENV.casefold() == "production" else "/redoc",
    openapi_url=(
        None
        if settings.APP_ENV.casefold() == "production"
        else f"{settings.API_V1_STR}/openapi.json"
    ),
)

if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

# Health check route — must be before the static file catch-all mount
@app.get("/health")
def health_check():
    return {"status": "ok", "environment": settings.APP_ENV}

# Include API routes BEFORE mounting static files so they are not shadowed
app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount the static frontend last (served from the project root's frontend folder)
# This is a catch-all, so it must come after all other routes
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
