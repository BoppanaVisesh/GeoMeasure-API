"""Tests for CRS selection, projected measurements, and degree-based area rejection."""

import pyproj
import pytest
from shapely.geometry import Polygon

from app.services.geospatial import get_utm_crs, measure_geometry
from tests.conftest import SQUARE_WGS84, _UTM_SQUARE


# ---------------------------------------------------------------------------
# get_utm_crs zone selection
# ---------------------------------------------------------------------------

class TestGetUTMCRS:
    def test_hyderabad_returns_zone_44n(self):
        """Hyderabad (lon=78.47, lat=17.38) must fall in UTM Zone 44N (EPSG:32644)."""
        result = get_utm_crs(78.47, 17.38)
        assert result == "EPSG:32644"

    def test_southern_hemisphere_returns_327xx(self):
        """A southern-hemisphere point must return an EPSG:327xx code."""
        result = get_utm_crs(25.0, -30.0)  # South Africa, Zone 35S → EPSG:32735
        assert result.startswith("EPSG:327")

    def test_southern_hemisphere_correct_zone(self):
        result = get_utm_crs(25.0, -30.0)  # Zone = int((25+180)/6)+1 = 35
        assert result == "EPSG:32735"

    def test_north_polar_fallback(self):
        """Latitude > 84 must return EPSG:3413 (Arctic polar stereographic)."""
        result = get_utm_crs(0.0, 85.0)
        assert result == "EPSG:3413"

    def test_south_polar_fallback(self):
        """Latitude < -80 must return EPSG:3031 (Antarctic polar stereographic)."""
        result = get_utm_crs(0.0, -81.0)
        assert result == "EPSG:3031"

    def test_lon_180_does_not_raise(self):
        """Longitude exactly 180 must clamp cleanly to zone 60."""
        result = get_utm_crs(180.0, 0.0)
        assert result == "EPSG:32660"

    def test_lon_minus_180_returns_zone_1(self):
        result = get_utm_crs(-180.0, 0.0)
        assert result == "EPSG:32601"


# ---------------------------------------------------------------------------
# Projected CRS input vs geographic CRS input — same result
# ---------------------------------------------------------------------------

class TestProjectedVsGeographic:
    def test_utm_input_area_matches_wgs84_input(self):
        """Measuring the same polygon from EPSG:32644 and from EPSG:4326 must agree within 0.5%."""
        # Measure directly from UTM source (no intermediate re-projection)
        result_utm = measure_geometry(_UTM_SQUARE, "EPSG:32644")
        # Measure from WGS84 source
        result_wgs = measure_geometry(SQUARE_WGS84, "EPSG:4326")

        assert result_utm["measurement_status"] == "MEASURED"
        assert result_wgs["measurement_status"] == "MEASURED"

        area_utm = result_utm["area"]
        area_wgs = result_wgs["area"]
        error_pct = abs(area_utm - area_wgs) / max(area_utm, area_wgs) * 100
        assert error_pct < 0.5, (
            f"UTM ({area_utm}) vs WGS84 ({area_wgs}) area differ by {error_pct:.4f}%"
        )

    def test_utm_input_area_is_close_to_1000000(self):
        """The 1000m x 1000m square measured from EPSG:32644 must be ≈ 1,000,000 m²."""
        result = measure_geometry(_UTM_SQUARE, "EPSG:32644")
        error_pct = abs(result["area"] - 1_000_000) / 1_000_000 * 100
        assert error_pct < 0.5


# ---------------------------------------------------------------------------
# Degree-based area is NOT what the code returns
# ---------------------------------------------------------------------------

class TestNotDegreeArea:
    def test_result_is_not_raw_degree_area(self):
        """The raw .area property on the WGS84 geometry (in degrees²) must be much smaller
        than the projected measurement in m², proving the service never returns degree-based areas."""
        result = measure_geometry(SQUARE_WGS84, "EPSG:4326")
        measured_m2 = result["area"]

        raw_degree_area = SQUARE_WGS84.area  # tiny number in degrees²

        # Raw degree area ≈ 0.000016 deg² vs measured ≈ 1,000,000 m²
        # So measured must be orders of magnitude larger
        assert measured_m2 > raw_degree_area * 1_000, (
            f"Measured area ({measured_m2} m²) is not much larger than raw degree area ({raw_degree_area} deg²) "
            "– possible bug: measuring in degrees!"
        )

    def test_projected_crs_is_in_metres(self):
        """The projected CRS used must have metre as its linear unit, not degree."""
        result = measure_geometry(SQUARE_WGS84, "EPSG:4326")
        proj_crs = pyproj.CRS.from_user_input(result["projected_crs"])
        axis_units = [ax.unit_name for ax in proj_crs.axis_info]
        assert all("metre" in u.lower() or "meter" in u.lower() for u in axis_units), (
            f"Projected CRS {result['projected_crs']} does not use metres: {axis_units}"
        )
