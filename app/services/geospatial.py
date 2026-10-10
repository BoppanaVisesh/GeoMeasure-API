"""Geospatial data reading, feature extraction, and measurement services."""

import datetime
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pyproj
import shapely.geometry
import shapely
from shapely import transform as shapely_transform
from pyogrio.errors import (
    CRSError,
    DataLayerError,
    DataSourceError,
    FeatureError,
    FieldError,
    GeometryError,
)

from app.services.errors import (
    InvalidFileError,
    MissingCRSError,
    UnsupportedFileTypeError,
)

MAX_UNCOMPRESSED_ZIP_SIZE = 200 * 1024 * 1024  # 200 MB
SUPPORTED_EXTENSIONS = {".kml", ".zip"}
PYOGRIO_EXCEPTIONS = (
    CRSError,
    DataLayerError,
    DataSourceError,
    FeatureError,
    FieldError,
    GeometryError,
)


def _get_layer_names(layers: Any) -> list[str]:
    """Extract layer name strings from pyogrio list_layers output."""
    if layers is None or len(layers) == 0:
        return []
    if hasattr(layers, "ndim") and layers.ndim == 2:
        return [str(row[0]) for row in layers]
    return [
        str(item[0]) if isinstance(item, (list, tuple, np.ndarray)) else str(item)
        for item in layers
    ]


def _read_kml(path: Path) -> gpd.GeoDataFrame:
    """Read all layers from a KML file into a single GeoDataFrame."""
    try:
        raw_layers = pyogrio.list_layers(path)
    except Exception as exc:
        raise InvalidFileError(f"Failed to inspect KML layers: {exc}") from exc

    layer_names = _get_layer_names(raw_layers)
    if not layer_names:
        raise InvalidFileError("No layers found in KML file")

    frames: list[gpd.GeoDataFrame] = []
    for layer in layer_names:
        try:
            layer_gdf = gpd.read_file(path, layer=layer, engine="pyogrio")
            if not layer_gdf.empty:
                frames.append(layer_gdf)
        except Exception as exc:
            raise InvalidFileError(f"Error reading KML layer '{layer}': {exc}") from exc

    if not frames:
        raise InvalidFileError("No features found in KML layers")

    combined_gdf = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        crs=frames[0].crs,
    )

    # KML specification is strictly WGS84 (EPSG:4326)
    if combined_gdf.crs is None:
        combined_gdf.set_crs("EPSG:4326", inplace=True)

    return combined_gdf


def _read_zipped_shapefile(path: Path) -> gpd.GeoDataFrame:
    """Safely extract a ZIP archive and read all contained shapefiles."""
    if not zipfile.is_zipfile(path):
        raise InvalidFileError("File is not a valid ZIP archive")

    with zipfile.ZipFile(path, "r") as zf:
        total_uncompressed = sum(info.file_size for info in zf.infolist())
        if total_uncompressed > MAX_UNCOMPRESSED_ZIP_SIZE:
            raise InvalidFileError(
                f"Total uncompressed size ({total_uncompressed} bytes) exceeds limit of 200MB"
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir).resolve()

            for member in zf.infolist():
                target_path = (tmp_path / member.filename).resolve()
                if not target_path.is_relative_to(tmp_path):
                    raise InvalidFileError(
                        f"Zip-slip path traversal attempt detected in member: {member.filename}"
                    )
                zf.extract(member, tmp_path)

            shp_files = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix.lower() == ".shp"]
            if not shp_files:
                raise InvalidFileError("No .shp found in archive")

            frames: list[gpd.GeoDataFrame] = []
            for shp_path in shp_files:
                parent_dir = shp_path.parent
                stem_lower = shp_path.stem.lower()
                dir_filenames = {f.name.lower(): f for f in parent_dir.iterdir() if f.is_file()}

                has_shx = f"{stem_lower}.shx" in dir_filenames
                has_dbf = f"{stem_lower}.dbf" in dir_filenames

                if not (has_shx and has_dbf):
                    raise InvalidFileError(
                        f"Shapefile '{shp_path.name}' is missing companion .shx or .dbf file"
                    )

                try:
                    gdf = gpd.read_file(shp_path, engine="pyogrio")
                except Exception as exc:
                    raise InvalidFileError(
                        f"Failed reading shapefile '{shp_path.name}': {exc}"
                    ) from exc

                if gdf.crs is None:
                    raise MissingCRSError(
                        f"Shapefile '{shp_path.name}' is missing CRS/projection information (.prj file missing or invalid)"
                    )

                if not gdf.empty:
                    frames.append(gdf)

            if not frames:
                raise InvalidFileError("No features found in shapefiles")

            return gpd.GeoDataFrame(
                pd.concat(frames, ignore_index=True),
                crs=frames[0].crs,
            )


def read_geodata(path: Path, original_filename: str) -> gpd.GeoDataFrame:
    """Read a geospatial file (.kml or .zip shapefile) into a GeoDataFrame.

    Args:
        path: Path to the local file to read.
        original_filename: Original name of the uploaded file.

    Returns:
        A loaded geopandas.GeoDataFrame containing the extracted features.

    Raises:
        UnsupportedFileTypeError: If file extension is not .kml or .zip.
        InvalidFileError: If file is empty, malformed, or corrupt.
        MissingCRSError: If shapefile lacks CRS metadata.
    """
    ext = Path(original_filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            f"Unsupported file format '{ext}'. Only .kml and .zip (Shapefiles) are accepted."
        )

    if not path.is_file() or path.stat().st_size == 0:
        raise InvalidFileError("File is empty or does not exist")

    try:
        if ext == ".kml":
            gdf = _read_kml(path)
        else:
            gdf = _read_zipped_shapefile(path)
    except PYOGRIO_EXCEPTIONS as exc:
        raise InvalidFileError(f"Geospatial data decoding error: {exc}") from exc
    except (InvalidFileError, MissingCRSError, UnsupportedFileTypeError):
        raise
    except Exception as exc:
        raise InvalidFileError(f"Unexpected error processing file: {exc}") from exc

    if gdf.empty or len(gdf) == 0:
        raise InvalidFileError("No features found")

    return gdf


def _to_json_safe(val: Any) -> Any:
    """Convert pandas/numpy/datetime types into JSON-serializable primitives."""
    if pd.isna(val):
        return None
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, (np.floating, float)):
        return float(val)
    if isinstance(val, (np.bool_, bool)):
        return bool(val)
    if isinstance(val, (pd.Timestamp, datetime.datetime, datetime.date)):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace")
    return val


def extract_features(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Extract standard feature dictionaries from a GeoDataFrame.

    Args:
        gdf: Input GeoDataFrame.

    Returns:
        List of dictionaries with feature index, geometry type, GeoJSON geometry,
        CRS authority/string, and sanitized properties.
    """
    crs_str: str | None = None
    if gdf.crs is not None:
        auth = gdf.crs.to_authority()
        crs_str = f"{auth[0]}:{auth[1]}" if auth else gdf.crs.to_string()

    geom_col = gdf.geometry.name
    non_geom_cols = [c for c in gdf.columns if c != geom_col]

    features: list[dict[str, Any]] = []
    for idx, (_, row) in enumerate(gdf.iterrows()):
        geom = row[geom_col]

        if geom is None or (hasattr(geom, "is_empty") and geom.is_empty):
            geom_type = "None"
            geom_json = None
        else:
            geom_type = geom.geom_type
            geom_json = shapely.geometry.mapping(geom)

        props = {col: _to_json_safe(row[col]) for col in non_geom_cols}

        features.append(
            {
                "feature_id": idx,
                "geometry_type": geom_type,
                "geometry": geom_json,
                "crs": crs_str,
                "properties": props,
            }
        )

    return features


def get_utm_crs(lon: float, lat: float) -> str:
    """Calculate the best projected UTM/Polar CRS EPSG code for a given coordinate.

    Args:
        lon: Longitude in degrees [-180, 180].
        lat: Latitude in degrees [-90, 90].

    Returns:
        EPSG identifier string (e.g., 'EPSG:32644', 'EPSG:3413').
    """
    if lat > 84.0:
        return "EPSG:3413"  # WGS 84 / NSIDC Sea Ice Polar Stereographic North
    if lat < -80.0:
        return "EPSG:3031"  # WGS 84 / Antarctic Polar Stereographic

    clamped_lon = max(-180.0, min(180.0, lon))
    if clamped_lon == 180.0:
        zone = 60
    else:
        zone = int((clamped_lon + 180.0) / 6.0) + 1
    zone = max(1, min(60, zone))

    epsg_base = 32600 if lat >= 0 else 32700
    return f"EPSG:{epsg_base + zone}"


def measure_geometry(geom: Any, source_crs: Any) -> dict[str, Any]:
    """Calculate geodesic-accurate projected measurements (area/length) for a geometry.

    Known limitation: features spanning multiple UTM zones are measured in the UTM
    zone of their centroid/representative point, which may introduce minor scale
    distortion far from the central meridian.

    Args:
        geom: Shapely geometry object.
        source_crs: Coordinate Reference System of the input geometry.

    Returns:
        Dict matching FeatureMeasurement measurement fields.
    """
    if geom is None or (hasattr(geom, "is_empty") and geom.is_empty):
        return {
            "measurement_status": "UNSUPPORTED",
            "area": None,
            "area_unit": None,
            "length": None,
            "length_unit": None,
            "projected_crs": None,
            "message": "Geometry is empty or null",
        }

    geom_type = getattr(geom, "geom_type", "")
    if geom_type in ("Point", "MultiPoint"):
        return {
            "measurement_status": "NO_MEASUREMENT_REQUIRED",
            "area": None,
            "area_unit": None,
            "length": None,
            "length_unit": None,
            "projected_crs": None,
            "message": "Points do not require measurement",
        }

    if geom_type not in ("Polygon", "MultiPolygon", "LineString", "MultiLineString"):
        return {
            "measurement_status": "UNSUPPORTED",
            "area": None,
            "area_unit": None,
            "length": None,
            "length_unit": None,
            "projected_crs": None,
            "message": f"Geometry type '{geom_type}' is not supported for measurement",
        }

    if source_crs is None:
        return {
            "measurement_status": "UNSUPPORTED",
            "area": None,
            "area_unit": None,
            "length": None,
            "length_unit": None,
            "projected_crs": None,
            "message": "Missing coordinate reference system for geometry measurement",
        }

    try:
        src_crs_obj = pyproj.CRS.from_user_input(source_crs)

        # Transform to EPSG:4326 if necessary to find longitude/latitude for UTM zone selection
        if src_crs_obj.to_epsg() != 4326:
            to_wgs84 = pyproj.Transformer.from_crs(src_crs_obj, "EPSG:4326", always_xy=True)
            def _fwd(coords):
                x, y = to_wgs84.transform(coords[:, 0], coords[:, 1])
                return np.column_stack([x, y])
            geom_wgs84 = shapely_transform(geom, _fwd)
        else:
            geom_wgs84 = geom

        rep_pt = geom_wgs84.representative_point() if not geom_wgs84.is_empty else geom_wgs84.centroid
        utm_crs = get_utm_crs(rep_pt.x, rep_pt.y)

        # Transform original geometry to projected UTM CRS (in metres)
        to_utm = pyproj.Transformer.from_crs(src_crs_obj, utm_crs, always_xy=True)
        def _to_m(coords):
            x, y = to_utm.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])
        projected_geom = shapely_transform(geom, _to_m)

        repaired_note: str | None = None
        if geom_type in ("Polygon", "MultiPolygon") and not projected_geom.is_valid:
            projected_geom = shapely.make_valid(projected_geom)
            repaired_note = "Self-intersecting geometry was repaired before measurement"

        if geom_type in ("Polygon", "MultiPolygon"):
            area_val = round(float(projected_geom.area), 4)
            return {
                "measurement_status": "MEASURED",
                "area": area_val,
                "area_unit": "m²",
                "length": None,
                "length_unit": None,
                "projected_crs": utm_crs,
                "message": repaired_note,
            }
        else:  # LineString or MultiLineString
            length_val = round(float(projected_geom.length), 4)
            return {
                "measurement_status": "MEASURED",
                "area": None,
                "area_unit": None,
                "length": length_val,
                "length_unit": "m",
                "projected_crs": utm_crs,
                "message": repaired_note,
            }

    except Exception as exc:
        return {
            "measurement_status": "UNSUPPORTED",
            "area": None,
            "area_unit": None,
            "length": None,
            "length_unit": None,
            "projected_crs": None,
            "message": f"Measurement error: {exc}",
        }


def build_measurements(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    """Generate feature-level measurements for all geometries in a GeoDataFrame.

    Args:
        gdf: Input GeoDataFrame.

    Returns:
        List of dictionaries matching FeatureMeasurement schema.
    """
    features = extract_features(gdf)
    measurements: list[dict[str, Any]] = []

    geom_col = gdf.geometry.name
    for idx, f in enumerate(features):
        geom = gdf.iloc[idx][geom_col]
        meas = measure_geometry(geom, gdf.crs)

        feature_meas = {
            "feature_id": f["feature_id"],
            "geometry_type": f["geometry_type"],
            "crs": f["crs"],
            "properties": f["properties"],
            "geometry": f["geometry"],
            "measurement_status": meas["measurement_status"],
            "area": meas["area"],
            "area_unit": meas["area_unit"],
            "length": meas["length"],
            "length_unit": meas["length_unit"],
            "projected_crs": meas["projected_crs"],
            "message": meas["message"],
        }
        measurements.append(feature_meas)

    return measurements


def process_file(path: Path, original_filename: str) -> dict[str, Any]:
    """Orchestrate reading, feature extraction, and measurement calculation for a file.

    Args:
        path: Path to the geospatial file on disk.
        original_filename: Original name of the uploaded file.

    Returns:
        A complete record dictionary ready for persistence.
    """
    gdf = read_geodata(path, original_filename)
    measurements = build_measurements(gdf)

    crs_str: str | None = None
    if gdf.crs is not None:
        auth = gdf.crs.to_authority()
        crs_str = f"{auth[0]}:{auth[1]}" if auth else gdf.crs.to_string()

    return {
        "id": str(uuid.uuid4()),
        "filename": original_filename,
        "status": "COMPLETED",
        "feature_count": len(measurements),
        "crs": crs_str,
        "measurements": measurements,
    }
