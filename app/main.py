"""Main FastAPI application entry point for GeoMeasure API."""

from fastapi import FastAPI

from app.routes import router as files_router

app = FastAPI(
    title="GeoMeasure API",
    description="Geospatial file processing and measurement API for KML and Shapefile formats.",
    version="0.1.0",
)

app.include_router(files_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Health check endpoint to verify service availability."""
    return {"status": "ok"}
