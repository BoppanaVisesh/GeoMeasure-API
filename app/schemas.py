"""Pydantic schemas and data models for GeoMeasure API."""

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class FileStatus(str, Enum):
    """Status of processed geospatial file."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileInfo(BaseModel):
    """Summary metadata and status for a processed geospatial file."""

    id: str
    filename: str
    feature_count: int
    crs: str | None = None
    status: FileStatus


class FeatureMeasurement(BaseModel):
    """Detailed measurement and geometry information for a single feature."""

    feature_id: int
    geometry_type: str
    crs: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] | None = None
    measurement_status: Literal["MEASURED", "NO_MEASUREMENT_REQUIRED", "UNSUPPORTED"] | str
    area: float | None = None
    area_unit: str | None = None
    length: float | None = None
    length_unit: str | None = None
    projected_crs: str | None = None
    message: str | None = None


class MeasurementsResponse(BaseModel):
    """Response model containing all feature measurements for a given file."""

    file_id: str
    crs: str | None = None
    feature_count: int
    measurements: list[FeatureMeasurement]


class ErrorResponse(BaseModel):
    """Standardized error response model."""

    detail: str
