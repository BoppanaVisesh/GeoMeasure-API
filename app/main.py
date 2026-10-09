"""Main FastAPI application entry point for GeoMeasure API."""

import logging
import logging.config

from fastapi import FastAPI

from app.routes import router as files_router

# Configure structured logging before anything else
logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            }
        },
        "root": {"level": "INFO", "handlers": ["console"]},
    }
)

app = FastAPI(
    title="GeoMeasure API",
    description=(
        "Upload a **.kml** file or a **.zip** containing a Shapefile.\n\n"
        "The API extracts every feature and calculates:\n"
        "- **Area** in square metres for Polygon / MultiPolygon geometries\n"
        "- **Length** in metres for LineString / MultiLineString geometries\n"
        "- Points are returned without a measurement (no area or length needed)\n\n"
        "Projections are always computed in a locally-appropriate UTM CRS "
        "so measurements are never in degrees."
    ),
    version="0.1.0",
)

app.include_router(files_router)


@app.get("/health", tags=["health"], summary="Service liveness check")
def health_check() -> dict[str, str]:
    """Return ``{"status": "ok"}`` when the service is running."""
    return {"status": "ok"}
