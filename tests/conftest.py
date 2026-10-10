"""Shared fixtures for the GeoMeasure API test suite."""

import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import pyproj
from fastapi.testclient import TestClient
from shapely import transform as shapely_transform
from shapely.geometry import LineString, Point, Polygon

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

# 1000 m x 1000 m square in UTM Zone 44N (EPSG:32644) then projected to WGS84
_UTM_SQUARE = Polygon(
    [(500000, 1400000), (501000, 1400000), (501000, 1401000), (500000, 1401000)]
)
_TO_WGS84 = pyproj.Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True)


def _wgs84_transform(coords):
    x, y = _TO_WGS84.transform(coords[:, 0], coords[:, 1])
    return np.column_stack([x, y])


SQUARE_WGS84 = shapely_transform(_UTM_SQUARE, _wgs84_transform)

# 1000 m horizontal line in UTM Zone 44N then projected to WGS84
_UTM_LINE = LineString([(500000, 1400000), (501000, 1400000)])
LINE_WGS84 = shapely_transform(_UTM_LINE, _wgs84_transform)


# ---------------------------------------------------------------------------
# File-building helpers
# ---------------------------------------------------------------------------

def make_kml(path: Path, geoms=None, names=None) -> None:
    """Write a KML file with the given geometries (defaults to poly + line + point)."""
    geoms = geoms or [
        Polygon([[78.47, 17.38], [78.474, 17.38], [78.474, 17.384], [78.47, 17.384], [78.47, 17.38]]),
        LineString([[78.47, 17.375], [78.475, 17.38], [78.48, 17.374]]),
        Point(78.472, 17.382),
    ]
    names = names or [f"feat_{i}" for i in range(len(geoms))]
    gdf = gpd.GeoDataFrame({"Name": names}, geometry=geoms, crs="EPSG:4326")
    gdf.to_file(path, driver="KML")


def make_shapefile_zip(path: Path, gdf_wgs84: gpd.GeoDataFrame | None = None) -> None:
    """Write a valid zipped shapefile (EPSG:4326, single geometry type = Polygon)."""
    import tempfile
    gdf = gdf_wgs84 or gpd.GeoDataFrame(
        {"name": ["poly"]},
        geometry=[Polygon([[78.47, 17.38], [78.474, 17.38], [78.474, 17.384], [78.47, 17.384], [78.47, 17.38]])],
        crs="EPSG:4326",
    )
    with tempfile.TemporaryDirectory() as tmp:
        shp = Path(tmp) / "data.shp"
        gdf.to_file(shp)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in Path(tmp).iterdir():
                zf.write(f, arcname=f.name)


def make_shapefile_zip_no_prj(path: Path) -> None:
    """Write a zipped shapefile with the .prj file omitted."""
    import tempfile
    gdf = gpd.GeoDataFrame(
        {"name": ["poly"]},
        geometry=[Polygon([[78.47, 17.38], [78.474, 17.38], [78.474, 17.384], [78.47, 17.384], [78.47, 17.38]])],
        crs="EPSG:4326",
    )
    with tempfile.TemporaryDirectory() as tmp:
        shp = Path(tmp) / "data.shp"
        gdf.to_file(shp)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in Path(tmp).iterdir():
                if f.suffix.lower() != ".prj":
                    zf.write(f, arcname=f.name)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    """Redirect the module-level store singleton to a temp directory."""
    monkeypatch.setenv("GEOMEASURE_DATA_DIR", str(tmp_path / "data"))
    from app.services.storage import FileStore
    fresh = FileStore(tmp_path / "data")
    monkeypatch.setattr("app.services.storage.store", fresh)
    monkeypatch.setattr("app.routes.store", fresh)
    return fresh


@pytest.fixture()
def client(tmp_store):
    """TestClient wired to a per-test isolated store."""
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def kml_file(tmp_path) -> Path:
    p = tmp_path / "sample.kml"
    make_kml(p)
    return p


@pytest.fixture()
def shapefile_zip(tmp_path) -> Path:
    p = tmp_path / "sample.zip"
    make_shapefile_zip(p)
    return p
