"""Custom exceptions for the GeoMeasure service."""


class GeoMeasureError(Exception):
    """Base exception for all GeoMeasure API errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileTypeError(GeoMeasureError):
    """Raised when an uploaded file format is not supported."""


class InvalidFileError(GeoMeasureError):
    """Raised when a file is corrupted, malformed, empty, or violates safety rules."""


class MissingCRSError(GeoMeasureError):
    """Raised when a dataset lacks required Coordinate Reference System (CRS) information."""
