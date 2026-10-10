"""Generate reproducible sample geospatial files into sample_data/.

Run from the project root:
    python scripts/make_sample_data.py
"""

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pyproj
from shapely.geometry import LineString, Point, Polygon

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO_ROOT / "sample_data"
SAMPLE_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Shared geometry (built in EPSG:32644 - UTM Zone 44N near Hyderabad)
# ---------------------------------------------------------------------------
# Convert reference coordinate (lon 78.47, lat 17.38) to UTM Zone 44N
_TO_UTM = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32644", always_xy=True)
_X0, _Y0 = _TO_UTM.transform(78.470, 17.380)

# Exact 500 m x 500 m square polygon (Area = 250,000 m²)
POLYGON_UTM = Polygon([
    (_X0, _Y0),
    (_X0 + 500.0, _Y0),
    (_X0 + 500.0, _Y0 + 500.0),
    (_X0, _Y0 + 500.0),
    (_X0, _Y0),
])

# Exact 1000 m straight line (Length = 1000 m)
LINESTRING_UTM = LineString([
    (_X0, _Y0 - 200.0),
    (_X0 + 1000.0, _Y0 - 200.0),
])

# Point of interest
POINT_UTM = Point(_X0 + 250.0, _Y0 + 250.0)


def _make_utm_gdf() -> gpd.GeoDataFrame:
    """Return a 3-feature GeoDataFrame in EPSG:32644 (UTM Zone 44N)."""
    return gpd.GeoDataFrame(
        {
            "Name": ["Hyderabad Zone A", "Hyderabad Road", "Hyderabad POI"],
            "type": ["polygon", "linestring", "point"],
            "descr": [
                "~500m x 500m zone near Hyderabad",
                "~1 km road segment near Hyderabad",
                "Point of interest near Hyderabad",
            ],
        },
        geometry=[POLYGON_UTM, LINESTRING_UTM, POINT_UTM],
        crs="EPSG:32644",
    )


def _make_wgs84_gdf() -> gpd.GeoDataFrame:
    """Return a 3-feature GeoDataFrame in EPSG:4326 converted from exact UTM geometries."""
    return _make_utm_gdf().to_crs("EPSG:4326")


# ---------------------------------------------------------------------------
# 1. sample.kml
# ---------------------------------------------------------------------------
def make_sample_kml() -> Path:
    """Write sample.kml to sample_data/."""
    out = SAMPLE_DIR / "sample.kml"
    gdf = _make_wgs84_gdf()
    gdf.to_file(out, driver="KML")
    print(f"  Created {out.name} ({out.stat().st_size:,} bytes)")
    return out


# ---------------------------------------------------------------------------
# 2. sample_shapefile.zip  (EPSG:4326, homogeneous type shapefiles)
# ---------------------------------------------------------------------------
def make_sample_shapefile_zip() -> Path:
    """Write three shapefiles (polygon, line, point) zipped in EPSG:4326."""
    out = SAMPLE_DIR / "sample_shapefile.zip"
    gdf = _make_wgs84_gdf()

    poly_gdf = gdf.iloc[[0]].copy()
    line_gdf = gdf.iloc[[1]].copy()
    pt_gdf = gdf.iloc[[2]].copy()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        poly_gdf.to_file(tmp_path / "polygon.shp")
        line_gdf.to_file(tmp_path / "linestring.shp")
        pt_gdf.to_file(tmp_path / "point.shp")

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tmp_path.iterdir()):
                zf.write(f, arcname=f.name)

    print(f"  Created {out.name} ({out.stat().st_size:,} bytes)")
    return out


# ---------------------------------------------------------------------------
# 3. sample_projected_shapefile.zip  (EPSG:32644 — UTM Zone 44N)
# ---------------------------------------------------------------------------
def make_projected_shapefile_zip() -> Path:
    """Write shapefiles in EPSG:32644 (UTM Zone 44N) to demonstrate projected input."""
    out = SAMPLE_DIR / "sample_projected_shapefile.zip"
    gdf = _make_utm_gdf()

    poly_gdf = gdf.iloc[[0]].copy()
    line_gdf = gdf.iloc[[1]].copy()
    pt_gdf = gdf.iloc[[2]].copy()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        poly_gdf.to_file(tmp_path / "polygon_utm.shp")
        line_gdf.to_file(tmp_path / "linestring_utm.shp")
        pt_gdf.to_file(tmp_path / "point_utm.shp")

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tmp_path.iterdir()):
                zf.write(f, arcname=f.name)

    print(f"  Created {out.name} ({out.stat().st_size:,} bytes)")
    return out


# ---------------------------------------------------------------------------
# 4. sample_no_prj.zip  (.prj deliberately removed to trigger MissingCRSError)
# ---------------------------------------------------------------------------
def make_no_prj_zip() -> Path:
    """Write a shapefile zip missing the .prj file to demonstrate MissingCRSError."""
    out = SAMPLE_DIR / "sample_no_prj.zip"
    gdf = _make_wgs84_gdf().iloc[[0]].copy()  # single polygon is enough

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        gdf.to_file(tmp_path / "no_crs.shp")

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(tmp_path.iterdir()):
                if f.suffix.lower() != ".prj":  # deliberately exclude projection file
                    zf.write(f, arcname=f.name)

    print(f"  Created {out.name} ({out.stat().st_size:,} bytes)  [.prj omitted]")
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating sample data...\n")
    make_sample_kml()
    make_sample_shapefile_zip()
    make_projected_shapefile_zip()
    make_no_prj_zip()
    print("\nDone. All files written to sample_data/")
