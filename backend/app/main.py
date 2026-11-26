from fastapi import FastAPI

from backend.app.api.routes import router
from backend.app.core.config import settings
from backend.app.core.logging_config import configure_logging


configure_logging()


app = FastAPI(
    title="Smart Invoice Analyzer",
    description=(
        "OCR-powered invoice extraction, validation and analysis API."
    ),
    version="0.1.0",
)

app.include_router(router)


@app.get("/health", tags=["System"])
def health():
    return {
        "status": "healthy",
        "application": "Smart Invoice Analyzer",
        "environment": settings.app_env,
    }


@app.get("/", tags=["System"])
def root():
    return {
        "application": "Smart Invoice Analyzer",
        "version": "0.1.0",
        "documentation": "/docs",
        "health": "/health",
    }