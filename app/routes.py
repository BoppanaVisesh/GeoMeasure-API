"""API route handlers for GeoMeasure API."""

import logging
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from app.schemas import (
    ErrorResponse,
    FeatureMeasurement,
    FileInfo,
    FileStatus,
    MeasurementsResponse,
)
from app.services.errors import (
    GeoMeasureError,
    InvalidFileError,
    MissingCRSError,
    UnsupportedFileTypeError,
)
from app.services.geospatial import process_file
from app.services.storage import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

_50_MB = 50 * 1024 * 1024  # 50 MB in bytes
_CHUNK_SIZE = 64 * 1024    # 64 KB read chunks


def _is_valid_uuid(val: str) -> bool:
    """Return True if val is a valid UUID string."""
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=FileInfo,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or unreadable file"},
        413: {"model": ErrorResponse, "description": "File exceeds 50 MB limit"},
        415: {"model": ErrorResponse, "description": "Unsupported file format"},
        422: {"model": ErrorResponse, "description": "Missing CRS / projection info"},
        500: {"model": ErrorResponse, "description": "Unexpected server error"},
    },
    summary="Upload and process a geospatial file",
    description=(
        "Upload a **.kml** file or a **.zip** archive containing an ESRI Shapefile.\n\n"
        "The service extracts all features, projects geometries to an appropriate UTM CRS, "
        "and calculates area (Polygon) or length (LineString) in metres. "
        "Files must not exceed **50 MB**."
    ),
)
async def upload_file(file: UploadFile) -> FileInfo:
    """Receive a multipart file, process it, persist the record, and return summary info."""
    tmp_path: Path | None = None
    try:
        # Chunk-based size check — do not load the full file into memory first
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "upload").suffix) as tmp:
            tmp_path = Path(tmp.name)
            total = 0
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > _50_MB:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds the 50 MB upload limit (received at least {total} bytes).",
                    )
                tmp.write(chunk)

        record = process_file(tmp_path, file.filename or "upload")
        store.save(record)

        return FileInfo(
            id=record["id"],
            filename=record["filename"],
            feature_count=record["feature_count"],
            crs=record.get("crs"),
            status=FileStatus(record["status"]),
        )

    except HTTPException:
        raise
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)) from exc
    except MissingCRSError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InvalidFileError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except GeoMeasureError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error processing upload '%s': %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again or contact support.",
        ) from exc
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@router.get(
    "/{file_id}/",
    response_model=FileInfo,
    responses={
        404: {"model": ErrorResponse, "description": "File record not found"},
    },
    summary="Get file metadata",
    description="Retrieve summary metadata (feature count, CRS, processing status) for a previously uploaded file.",
)
def get_file_info(file_id: str) -> FileInfo:
    """Return summary metadata for a processed file by its UUID."""
    if not _is_valid_uuid(file_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No file record found for id '{file_id}'.",
        )

    record = store.get(file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No file record found for id '{file_id}'.",
        )

    return FileInfo(
        id=record["id"],
        filename=record["filename"],
        feature_count=record["feature_count"],
        crs=record.get("crs"),
        status=FileStatus(record["status"]),
    )


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "File record not found"},
    },
    summary="Get feature measurements",
    description=(
        "Return per-feature measurements (area, length) for a processed file.\n\n"
        "Set **include_geometry=true** to include raw GeoJSON geometry in each feature; "
        "by default geometry is omitted to keep responses compact."
    ),
)
def get_measurements(
    file_id: str,
    include_geometry: bool = Query(
        default=False,
        description="Include GeoJSON geometry in each feature. Defaults to false.",
    ),
) -> MeasurementsResponse:
    """Return feature-level measurements for a processed file."""
    if not _is_valid_uuid(file_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No file record found for id '{file_id}'.",
        )

    record = store.get(file_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No file record found for id '{file_id}'.",
        )

    measurements = [
        FeatureMeasurement(
            feature_id=m["feature_id"],
            geometry_type=m["geometry_type"],
            crs=m.get("crs"),
            properties=m.get("properties", {}),
            geometry=m.get("geometry") if include_geometry else None,
            measurement_status=m["measurement_status"],
            area=m.get("area"),
            area_unit=m.get("area_unit"),
            length=m.get("length"),
            length_unit=m.get("length_unit"),
            projected_crs=m.get("projected_crs"),
            message=m.get("message"),
        )
        for m in record.get("measurements", [])
    ]

    return MeasurementsResponse(
        file_id=record["id"],
        crs=record.get("crs"),
        feature_count=record["feature_count"],
        measurements=measurements,
    )
