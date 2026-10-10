"""Tests for the measurements endpoint and per-feature measurement accuracy."""

import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, Point, Polygon

from app.services.geospatial import measure_geometry
from tests.conftest import SQUARE_WGS84, LINE_WGS84, make_kml


# ---------------------------------------------------------------------------
# Unit tests for measure_geometry (no HTTP layer)
# ---------------------------------------------------------------------------

class TestMeasureGeometryUnit:
    def test_polygon_area_within_half_percent(self):
        """1000m x 1000m square reprojected to WGS84 must measure ≈1,000,000 m²."""
        result = measure_geometry(SQUARE_WGS84, "EPSG:4326")
        assert result["measurement_status"] == "MEASURED"
        assert result["area"] is not None
        error_pct = abs(result["area"] - 1_000_000) / 1_000_000 * 100
        assert error_pct < 0.5, f"Area error {error_pct:.4f}% exceeds 0.5%: {result['area']} m²"
        assert result["area_unit"] == "m\u00b2"
        assert result["length"] is None

    def test_linestring_length_within_half_percent(self):
        """1000m line reprojected to WGS84 must measure ≈1,000 m."""
        result = measure_geometry(LINE_WGS84, "EPSG:4326")
        assert result["measurement_status"] == "MEASURED"
        assert result["length"] is not None
        error_pct = abs(result["length"] - 1_000) / 1_000 * 100
        assert error_pct < 0.5, f"Length error {error_pct:.4f}% exceeds 0.5%: {result['length']} m"
        assert result["length_unit"] == "m"
        assert result["area"] is None

    def test_point_returns_no_measurement_required(self):
        pt = Point(78.47, 17.38)
        result = measure_geometry(pt, "EPSG:4326")
        assert result["measurement_status"] == "NO_MEASUREMENT_REQUIRED"
        assert result["area"] is None
        assert result["length"] is None
        assert "Points" in (result["message"] or "")

    def test_geometry_collection_returns_unsupported_without_raising(self):
        gc = GeometryCollection([Point(78.47, 17.38), LineString([(78.47, 17.38), (78.48, 17.39)])])
        result = measure_geometry(gc, "EPSG:4326")
        assert result["measurement_status"] == "UNSUPPORTED"
        assert result["area"] is None
        assert result["length"] is None

    def test_none_geometry_returns_unsupported(self):
        result = measure_geometry(None, "EPSG:4326")
        assert result["measurement_status"] == "UNSUPPORTED"

    def test_empty_geometry_returns_unsupported(self):
        empty = Polygon()
        result = measure_geometry(empty, "EPSG:4326")
        assert result["measurement_status"] == "UNSUPPORTED"


# ---------------------------------------------------------------------------
# API-level measurements endpoint tests
# ---------------------------------------------------------------------------

class TestMeasurementsEndpoint:
    def _upload_kml(self, client, kml_file):
        with open(kml_file, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("sample.kml", fh, "application/octet-stream")})
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_measurements_returns_200(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/")
        assert resp.status_code == 200

    def test_feature_ids_are_sequential(self, client, kml_file):
        """feature_id must be 0-indexed and sequential for all features."""
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/")
        ids = [m["feature_id"] for m in resp.json()["measurements"]]
        assert ids == list(range(len(ids)))

    def test_mixed_geometry_kml_correct_statuses(self, client, kml_file):
        """KML with poly+line+point must return MEASURED, MEASURED, NO_MEASUREMENT_REQUIRED."""
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/")
        measurements = resp.json()["measurements"]
        statuses = {m["geometry_type"]: m["measurement_status"] for m in measurements}
        assert statuses["Polygon"] == "MEASURED"
        assert statuses["LineString"] == "MEASURED"
        assert statuses["Point"] == "NO_MEASUREMENT_REQUIRED"

    def test_polygon_has_area_not_length(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/")
        poly = next(m for m in resp.json()["measurements"] if m["geometry_type"] == "Polygon")
        assert poly["area"] is not None
        assert poly["area_unit"] == "m\u00b2"
        assert poly["length"] is None

    def test_linestring_has_length_not_area(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/")
        line = next(m for m in resp.json()["measurements"] if m["geometry_type"] == "LineString")
        assert line["length"] is not None
        assert line["length_unit"] == "m"
        assert line["area"] is None

    def test_include_geometry_false_gives_null_geometry(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/")
        for m in resp.json()["measurements"]:
            assert m["geometry"] is None, f"Expected null geometry for feature {m['feature_id']}"

    def test_include_geometry_true_gives_geojson(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/measurements/", params={"include_geometry": "true"})
        non_point = [m for m in resp.json()["measurements"] if m["geometry_type"] != "Point"]
        for m in non_point:
            assert m["geometry"] is not None, f"Expected GeoJSON geometry for {m['geometry_type']}"
            assert "type" in m["geometry"]
            assert "coordinates" in m["geometry"]

    def test_measurements_for_unknown_id_returns_404(self, client):
        resp = client.get("/api/files/00000000-0000-0000-0000-000000000000/measurements/")
        assert resp.status_code == 404

    def test_polygon_area_within_half_percent_via_api(self, client, tmp_path):
        """Upload a 1000m x 1000m square (WGS84) and verify API-reported area ≈ 1,000,000 m²."""
        kml = tmp_path / "square.kml"
        gdf = gpd.GeoDataFrame({"Name": ["sq"]}, geometry=[SQUARE_WGS84], crs="EPSG:4326")
        gdf.to_file(kml, driver="KML")

        with open(kml, "rb") as fh:
            up = client.post("/api/files/", files={"file": ("square.kml", fh, "application/octet-stream")})
        file_id = up.json()["id"]

        resp = client.get(f"/api/files/{file_id}/measurements/")
        m = resp.json()["measurements"][0]
        assert m["measurement_status"] == "MEASURED"
        error_pct = abs(m["area"] - 1_000_000) / 1_000_000 * 100
        assert error_pct < 0.5
