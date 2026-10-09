"""Thread-safe persistent storage service for file records."""

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any


def validate_uuid(val: str) -> str:
    """Validate that a given string is a valid UUID representation.

    Args:
        val: The string to validate.

    Returns:
        The normalized lowercase UUID string.

    Raises:
        ValueError: If val is not a valid UUID.
    """
    try:
        parsed = uuid.UUID(str(val))
        return str(parsed)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid UUID: '{val}'") from exc


class FileStore:
    """In-memory and file-backed thread-safe store for processed file records."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        """Initialize the storage directory and in-memory cache."""
        dir_name = data_dir or os.getenv("GEOMEASURE_DATA_DIR", "data")
        self.data_dir = Path(dir_name)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def save(self, record: dict[str, Any]) -> None:
        """Save a record to the in-memory cache and persist as JSON on disk.

        Args:
            record: The dictionary record to store. Must include 'id' or 'file_id'.

        Raises:
            ValueError: If the record has no valid UUID identifier.
        """
        raw_id = record.get("id") or record.get("file_id")
        if not raw_id:
            raise ValueError("Record must contain 'id' or 'file_id'.")

        file_id = validate_uuid(str(raw_id))

        with self._lock:
            self._cache[file_id] = record
            file_path = self.data_dir / f"{file_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

    def get(self, file_id: str) -> dict[str, Any] | None:
        """Retrieve a record by its file ID, checking memory first, then disk.

        Args:
            file_id: The UUID of the file to retrieve.

        Returns:
            The record dictionary if found, or None if not found/invalid.
        """
        try:
            valid_id = validate_uuid(file_id)
        except ValueError:
            return None

        with self._lock:
            if valid_id in self._cache:
                return self._cache[valid_id]

            file_path = self.data_dir / f"{valid_id}.json"
            if file_path.is_file():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        record: dict[str, Any] = json.load(f)
                        self._cache[valid_id] = record
                        return record
                except (json.JSONDecodeError, OSError):
                    return None

            return None


# Module-level storage singleton instance
store = FileStore()
