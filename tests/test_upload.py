"""Tests for file upload and metadata endpoints."""

import zipfile

import pytest

from tests.conftest import make_shapefile_zip_no_prj


# ---------------------------------------------------------------------------
# POST /api/files/ — happy paths
# ---------------------------------------------------------------------------

class TestUploadKML:
    def test_valid_kml_returns_201(self, client, kml_file):
        with open(kml_file, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("sample.kml", fh, "application/octet-stream")})
        assert resp.status_code == 201

    def test_valid_kml_response_schema(self, client, kml_file):
        with open(kml_file, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("sample.kml", fh, "application/octet-stream")})
        body = resp.json()
        assert "id" in body
        assert body["filename"] == "sample.kml"
        assert body["feature_count"] == 3
        assert body["crs"] == "EPSG:4326"
        assert body["status"] == "COMPLETED"


class TestUploadShapefileZIP:
    def test_valid_zip_returns_201(self, client, shapefile_zip):
        with open(shapefile_zip, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("sample.zip", fh, "application/zip")})
        assert resp.status_code == 201

    def test_valid_zip_response_schema(self, client, shapefile_zip):
        with open(shapefile_zip, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("sample.zip", fh, "application/zip")})
        body = resp.json()
        assert "id" in body
        assert body["filename"] == "sample.zip"
        assert body["feature_count"] == 1
        assert body["status"] == "COMPLETED"
        assert body["crs"] is not None


# ---------------------------------------------------------------------------
# POST /api/files/ — error paths
# ---------------------------------------------------------------------------

class TestUploadErrors:
    def test_unsupported_extension_returns_415(self, client, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")
        with open(f, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("data.txt", fh, "text/plain")})
        assert resp.status_code == 415
        assert "detail" in resp.json()

    def test_malformed_kml_returns_400(self, client, tmp_path):
        f = tmp_path / "bad.kml"
        f.write_bytes(b"this is not valid kml content at all")
        with open(f, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("bad.kml", fh, "application/octet-stream")})
        assert resp.status_code == 400
        assert "detail" in resp.json()

    def test_empty_file_returns_400(self, client, tmp_path):
        f = tmp_path / "empty.kml"
        f.write_bytes(b"")
        with open(f, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("empty.kml", fh, "application/octet-stream")})
        assert resp.status_code == 400

    def test_random_bytes_zip_returns_400(self, client, tmp_path):
        f = tmp_path / "garbage.zip"
        f.write_bytes(b"\x00\x01\x02\x03" * 100)
        with open(f, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("garbage.zip", fh, "application/zip")})
        assert resp.status_code == 400

    def test_zip_with_no_shp_returns_400(self, client, tmp_path):
        z = tmp_path / "no_shp.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("readme.txt", "no shapefile here")
        with open(z, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("no_shp.zip", fh, "application/zip")})
        assert resp.status_code == 400
        assert "No .shp" in resp.json()["detail"]

    def test_zip_without_prj_returns_422(self, client, tmp_path):
        z = tmp_path / "no_prj.zip"
        make_shapefile_zip_no_prj(z)
        with open(z, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("no_prj.zip", fh, "application/zip")})
        assert resp.status_code == 422
        assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# GET /api/files/{id}/ — file info
# ---------------------------------------------------------------------------

class TestGetFileInfo:
    def _upload_kml(self, client, kml_file):
        with open(kml_file, "rb") as fh:
            resp = client.post("/api/files/", files={"file": ("sample.kml", fh, "application/octet-stream")})
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_get_file_info_returns_200(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/")
        assert resp.status_code == 200

    def test_get_file_info_body(self, client, kml_file):
        file_id = self._upload_kml(client, kml_file)
        resp = client.get(f"/api/files/{file_id}/")
        body = resp.json()
        assert body["id"] == file_id
        assert body["filename"] == "sample.kml"
        assert body["feature_count"] == 3
        assert body["status"] == "COMPLETED"

    def test_unknown_uuid_returns_404(self, client):
        resp = client.get("/api/files/00000000-0000-0000-0000-000000000000/")
        assert resp.status_code == 404
        assert "detail" in resp.json()

    def test_non_uuid_id_returns_404(self, client):
        resp = client.get("/api/files/not-a-valid-uuid/")
        assert resp.status_code == 404
        assert "detail" in resp.json()
