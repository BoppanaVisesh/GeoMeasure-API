# GeoMeasure API

A REST API for uploading geospatial files (KML and zipped Shapefiles), extracting their
features, and computing geodesic-accurate area (m2) and length (m) measurements using
locally-appropriate UTM projections.

---

## Quick Start

```bash
git clone https://github.com/BoppanaVisesh/GeoMeasure-API.git
cd GeoMeasure-API
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

---

## 1. Project Title

**GeoMeasure API** -- a FastAPI service that processes KML and Shapefile uploads and
returns per-feature geodesic measurements.

---

## 2. Overview and Objectives

GeoMeasure API accepts a KML file or a zipped ESRI Shapefile, reads every feature inside
it, and computes a UTM-projected measurement for each:

- **Polygon / MultiPolygon** -- area in square metres.
- **LineString / MultiLineString** -- length in metres.
- **Point / MultiPoint** -- returned as-is; no measurement required.

The main objectives are:

1. Provide a clean REST API for uploading geospatial files and retrieving measurements.
2. Handle both geographic (EPSG:4326) and already-projected (e.g. EPSG:32644) inputs
   correctly by always re-projecting to the appropriate UTM zone before measuring.
3. Return structured JSON responses suitable for programmatic consumption.
4. Never leak stack traces to the client; map all errors to meaningful HTTP codes.
5. Persist uploaded records to disk so they survive server restarts.

---

## 3. Features

- Upload KML or zipped Shapefile via `POST /api/files/`.
- Per-feature measurements: area (m2) for polygons, length (m) for line strings.
- Automatic UTM zone selection based on each feature's representative point.
- Polar fallback: EPSG:3413 (Arctic) for lat > 84, EPSG:3031 (Antarctic) for lat < -80.
- KML is assumed to be WGS 84 (EPSG:4326) per the KML specification.
- Shapefiles without a `.prj` file are rejected with HTTP 422 (Missing CRS).
- ZIP archives are checked for zip-slip path traversal attacks.
- Uncompressed ZIP contents are capped at 200 MB; uploads at 50 MB (checked in chunks).
- Records are persisted as JSON files in `data/` and loaded from disk on restart.
- Optional `include_geometry` query parameter returns raw GeoJSON coordinates per feature.
- `/health` endpoint for liveness checks.
- OpenAPI documentation at `/docs`.

---

## 4. Technology Stack

| Component           | Library / Tool                        |
|---------------------|---------------------------------------|
| Web framework       | FastAPI                               |
| ASGI server         | Uvicorn (with standard extras)        |
| Multipart parsing   | python-multipart                      |
| Geospatial I/O      | GeoPandas, pyogrio                    |
| Geometry operations | Shapely                               |
| Coordinate transforms | pyproj                              |
| Data validation     | Pydantic v2                           |
| Testing             | pytest, httpx (via FastAPI TestClient)|
| Language            | Python 3.12                           |

---

## 5. Project Structure

```
GeoMeasure-API/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, logging config, /health endpoint
│   ├── routes.py                # Three API route handlers
│   ├── schemas.py               # Pydantic models (FileInfo, FeatureMeasurement, etc.)
│   └── services/
│       ├── __init__.py
│       ├── errors.py            # Custom exception hierarchy
│       ├── geospatial.py        # File reading, UTM selection, measurement logic
│       └── storage.py           # Thread-safe in-memory + JSON-on-disk record store
├── data/                        # Runtime: one JSON file per uploaded record (git-ignored)
├── sample_data/
│   ├── sample.kml               # 3-feature KML in EPSG:4326 (Hyderabad area)
│   ├── sample_shapefile.zip     # Same 3 features as Shapefile in EPSG:4326
│   ├── sample_projected_shapefile.zip  # Same 3 features in EPSG:32644 (UTM 44N)
│   └── sample_no_prj.zip        # Shapefile ZIP with .prj removed (triggers 422)
├── scripts/
│   └── make_sample_data.py      # Regenerates all four sample files from scratch
├── tests/
│   ├── conftest.py              # Shared fixtures: TestClient, isolated store, geometries
│   ├── test_crs.py              # Unit tests for get_utm_crs and projected-vs-geographic
│   ├── test_measurements.py     # Unit + API tests for measure_geometry
│   └── test_upload.py           # API tests for upload, GET info, and error cases
├── .gitignore
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## 6. Installation and Setup

### Prerequisites

- Python 3.12 or later
- `git`

### Clone the repository

```bash
git clone https://github.com/BoppanaVisesh/GeoMeasure-API.git
cd GeoMeasure-API
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `data/` directory is created automatically on first run.

---

## 7. Running the Application Locally

```bash
uvicorn app.main:app --reload
```

The server starts on `http://127.0.0.1:8000` by default.

| URL                                | Purpose                                              |
|------------------------------------|------------------------------------------------------|
| http://127.0.0.1:8000/health       | Liveness check -- returns `{"status": "ok"}`         |
| http://127.0.0.1:8000/docs         | Swagger / OpenAPI interactive documentation          |
| http://127.0.0.1:8000/redoc        | ReDoc alternative documentation                      |

To run on a different port:

```bash
uvicorn app.main:app --reload --port 8080
```

---

## 8. API Endpoints

### POST /api/files/

**Purpose:** Upload a `.kml` file or a `.zip` archive containing an ESRI Shapefile.
Returns a file record with processing status and feature count.

**Limits:**
- Maximum upload size: 50 MB (checked in 64 KB chunks; never fully loaded into memory first).
- Accepted extensions: `.kml`, `.zip`.

**curl example:**

```bash
curl -s -X POST http://127.0.0.1:8000/api/files/ \
  -F "file=@sample_data/sample.kml" | python -m json.tool
```

**Example response (HTTP 201):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

**Error codes:**

| Code | Meaning                                                               |
|------|-----------------------------------------------------------------------|
| 400  | File is empty, malformed, corrupt, or contains no features            |
| 413  | Upload exceeds 50 MB                                                  |
| 415  | File extension is not `.kml` or `.zip`                                |
| 422  | Shapefile ZIP is missing `.prj` (CRS unknown)                         |
| 500  | Unexpected server-side error (details are logged, not returned)       |

---

### GET /api/files/{file_id}/

**Purpose:** Retrieve summary metadata for a previously uploaded file by its UUID.

**curl example:**

```bash
curl -s http://127.0.0.1:8000/api/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890/ \
  | python -m json.tool
```

**Example response (HTTP 200):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "status": "COMPLETED"
}
```

**Error codes:**

| Code | Meaning                                                      |
|------|--------------------------------------------------------------|
| 404  | No record found for the given ID, or ID is not a valid UUID  |

---

### GET /api/files/{file_id}/measurements/

**Purpose:** Return per-feature measurements for all features in a processed file.

**Query parameters:**

| Parameter          | Type | Default | Description                                          |
|--------------------|------|---------|------------------------------------------------------|
| `include_geometry` | bool | `false` | Include raw GeoJSON geometry for each feature        |

**curl example (default -- no geometry):**

```bash
curl -s "http://127.0.0.1:8000/api/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890/measurements/" \
  | python -m json.tool
```

**Example response (HTTP 200) -- from `sample.kml` processed live:**

```json
{
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "crs": "EPSG:4326",
  "feature_count": 3,
  "measurements": [
    {
      "feature_id": 0,
      "geometry_type": "Polygon",
      "crs": "EPSG:4326",
      "properties": {
        "Name": "Hyderabad Zone A",
        "description": "~500m x 500m zone near Hyderabad"
      },
      "geometry": null,
      "measurement_status": "MEASURED",
      "area": 250000.0,
      "area_unit": "m2",
      "length": null,
      "length_unit": null,
      "projected_crs": "EPSG:32644",
      "message": null
    },
    {
      "feature_id": 1,
      "geometry_type": "LineString",
      "crs": "EPSG:4326",
      "properties": {
        "Name": "Hyderabad Road",
        "description": "~1 km road segment near Hyderabad"
      },
      "geometry": null,
      "measurement_status": "MEASURED",
      "area": null,
      "area_unit": null,
      "length": 1000.0,
      "length_unit": "m",
      "projected_crs": "EPSG:32644",
      "message": null
    },
    {
      "feature_id": 2,
      "geometry_type": "Point",
      "crs": "EPSG:4326",
      "properties": {
        "Name": "Hyderabad POI",
        "description": "Point of interest near Hyderabad"
      },
      "geometry": null,
      "measurement_status": "NO_MEASUREMENT_REQUIRED",
      "area": null,
      "area_unit": null,
      "length": null,
      "length_unit": null,
      "projected_crs": null,
      "message": "Points do not require measurement"
    }
  ]
}
```

**curl example (with geometry):**

```bash
curl -s "http://127.0.0.1:8000/api/files/a1b2c3d4-e5f6-7890-abcd-ef1234567890/measurements/?include_geometry=true" \
  | python -m json.tool
```

When `include_geometry=true`, each feature's `geometry` field contains a GeoJSON
geometry object with `type` and `coordinates`.

**Error codes:**

| Code | Meaning                                                      |
|------|--------------------------------------------------------------|
| 404  | No record found for the given ID, or ID is not a valid UUID  |

---

## 9. Architecture and File-Processing Flow

```
Client
  |
  |  POST /api/files/  (multipart, up to 50 MB)
  v
routes.py  upload_file()
  |
  |-- chunk-read into NamedTemporaryFile (64 KB chunks, abort if >50 MB)
  |
  v
services/geospatial.py  process_file()
  |
  |-- read_geodata()
  |     |-- .kml  -> _read_kml()
  |     |           (pyogrio: list layers, merge all, force CRS=EPSG:4326)
  |     |-- .zip  -> _read_zipped_shapefile()
  |                  (extract to tmpdir, find .shp, check .shx/.dbf/.prj, read)
  |
  |-- build_measurements()
  |     |-- extract_features()   (GeoDataFrame -> list of feature dicts)
  |     |-- measure_geometry()   for each feature
  |           |-- get_utm_crs()  (representative point -> UTM or polar EPSG code)
  |           |-- pyproj.Transformer: source_crs -> UTM
  |           |-- shapely.transform: project geometry to metres
  |           |-- .area  (Polygon) or .length (LineString)
  |
  |-- assign UUID, build record dict
  |
  v
services/storage.py  FileStore.save()
  |-- in-memory dict  (threading.Lock protected)
  |-- data/{uuid}.json  (written to disk, survives restart)
  |
  v
routes.py -> FileInfo JSON (HTTP 201)


Client
  |  GET /api/files/{id}/
  |  GET /api/files/{id}/measurements/?include_geometry=true|false
  v
routes.py -> FileStore.get() -> JSON response
```

---

## 10. Measurement Calculation Flow

```
measure_geometry(geom, source_crs)
  |
  +-- geom is None or empty          ->  UNSUPPORTED
  |
  +-- geom_type is Point/MultiPoint  ->  NO_MEASUREMENT_REQUIRED
  |
  +-- geom_type not in supported set ->  UNSUPPORTED
  |
  +-- source_crs is None             ->  UNSUPPORTED
  |
  +-- if source_crs != EPSG:4326:
  |       transform geom to EPSG:4326
  |       (pyproj.Transformer, always_xy=True)
  |
  +-- representative_point() on WGS-84 geometry
  |
  +-- get_utm_crs(lon, lat)
  |       lat > 84   ->  EPSG:3413  (Arctic polar stereographic North)
  |       lat < -80  ->  EPSG:3031  (Antarctic polar stereographic)
  |       otherwise  ->  zone = int((lon + 180) / 6) + 1
  |                      EPSG:326{zone} (N hemisphere) or EPSG:327{zone} (S)
  |
  +-- transform ORIGINAL geom from source_crs to UTM CRS
  |       (pyproj.Transformer, always_xy=True)
  |
  +-- Polygon / MultiPolygon    ->  .area   (m2), status MEASURED
  +-- LineString / MultiLineString -> .length (m), status MEASURED
  |
  +-- any exception              ->  UNSUPPORTED  (message stored, no crash)
```

Values are rounded to 4 decimal places.
Self-intersecting polygons are repaired with `shapely.make_valid` before measurement.

---

## 11. CRS Handling and Assumptions

| Scenario                              | Behaviour                                                                                          |
|---------------------------------------|----------------------------------------------------------------------------------------------------|
| KML upload                            | CRS assumed EPSG:4326 per KML 2.2 spec. If pyogrio reports none, EPSG:4326 is set explicitly.     |
| Shapefile with `.prj`                 | CRS read from the `.prj` file by pyogrio.                                                          |
| Shapefile without `.prj`              | HTTP 422 returned: "missing CRS/projection information".                                            |
| Geographic input (degrees, EPSG:4326) | Transformed to the chosen UTM zone for measurement; original CRS reported unchanged.               |
| Projected input (e.g. EPSG:32644)     | Transformed to EPSG:4326 for zone selection, then to the chosen UTM zone for measurement.          |
| Polar lat > 84 degrees                | EPSG:3413 (WGS 84 / NSIDC Sea Ice Polar Stereographic North).                                      |
| Polar lat < -80 degrees               | EPSG:3031 (WGS 84 / Antarctic Polar Stereographic).                                                |
| Feature spans multiple UTM zones      | Measured in the zone of its centroid; minor scale distortion possible at zone boundaries.           |

The `projected_crs` field in each measurement response shows the CRS used for that feature.

---

## 12. Error Handling Table

| HTTP Code | Cause                                  | Client `detail` message                                               |
|-----------|----------------------------------------|-----------------------------------------------------------------------|
| 400       | `InvalidFileError`                     | Empty file, malformed KML, no .shp in ZIP, corrupt archive, etc.      |
| 400       | Other `GeoMeasureError`                | Specific message from the service layer.                              |
| 413       | Upload > 50 MB                         | "File exceeds the 50 MB upload limit (received at least N bytes)."    |
| 415       | `UnsupportedFileTypeError`             | Extension is not `.kml` or `.zip`.                                    |
| 422       | `MissingCRSError`                      | Shapefile is missing `.prj` / CRS info.                               |
| 404       | Record not found or non-UUID id        | "No file record found for id '...'."                                  |
| 500       | Unexpected exception                   | Generic message; real error logged server-side, not returned.         |

All error responses have the shape `{"detail": "<message>"}`.

---

## 13. Running Tests

```bash
# Activate the virtual environment first, then:
pytest -v
```

The test suite sets `GEOMEASURE_DATA_DIR` via a fixture to a `tmp_path`-backed directory
so it never writes to the real `data/` folder.

**Test files:**

| File                       | What it covers                                                   |
|----------------------------|------------------------------------------------------------------|
| `tests/test_upload.py`     | Upload success (KML, ZIP), error codes (415, 400, 422), GET, 404 |
| `tests/test_measurements.py` | Polygon area, line length, point status, geometry inclusion, 404 |
| `tests/test_crs.py`        | `get_utm_crs` zone logic, polar fallbacks, projected vs geographic|

**Expected result:**

```
======================== 40 passed, 1 warning in 5.10s ========================
```

The single warning is a `StarletteDeprecationWarning` emitted by FastAPI's own
`testclient.py` about `httpx` vs `httpx2`. It is suppressed in `pytest.ini`
and does not affect test results.

---

## 14. Design Decisions and Alternatives

**UTM zone per feature, not per file.**
Each feature is projected to its own optimal UTM zone. A single CRS per file would be
simpler but would introduce large errors for files that span wide geographic areas.

**pyogrio as the I/O engine.**
pyogrio (GDAL bindings) was chosen over Fiona because it is faster for large files and
is the default engine in recent GeoPandas versions.

**Chunk-based upload size check.**
The 50 MB limit is enforced during chunk reads, before the file is fully buffered.
This prevents memory exhaustion from oversized uploads.

**JSON-on-disk persistence.**
Each record is written as `data/{uuid}.json`. Simple and sufficient for a single-process
server; a production deployment would use a database.

**Thread-safe in-memory cache.**
`threading.Lock` guards the in-memory dict and file writes. An `asyncio.Lock` was
considered but is unnecessary because storage operations are fast and CPU-bound.

**KML forced to EPSG:4326.**
The KML 2.2 specification requires WGS 84 coordinates. If pyogrio returns no CRS for a
KML layer, the code sets EPSG:4326 rather than raising an error.

**Shapefile without `.prj` raises 422, not 400.**
HTTP 422 (Unprocessable Entity) is more precise: the file is structurally valid but
cannot be processed without CRS information. 400 would imply a parsing failure.

---

## 15. What I Learned

- **CRS selection is the biggest correctness risk.** Computing area or length in
  degree-based coordinates produces values that are wrong by orders of magnitude.
  Choosing the right UTM zone per feature and using `always_xy=True` in every pyproj
  Transformer were the two most critical steps.

- **KML and Shapefile handle CRS fundamentally differently.** KML mandates WGS 84;
  Shapefiles encode CRS in a separate `.prj` file that may be absent. These differences
  require distinct code paths and different error strategies.

- **Zip-slip is a real attack.** Code that extracts user-provided ZIPs must verify every
  extracted path resolves inside the intended directory.

- **FastAPI's automatic validation does not replace explicit checks.** UUID validation,
  file extension filtering, and chunk-based size enforcement all required manual code.

- **Persistence design pays off immediately.** Writing each record to `data/{uuid}.json`
  on save and reading it back on miss makes restart-persistence trivial with no migration.

- **Sample data quality affects trust in the pipeline.** Early sample geometries produced
  ~188 k m2 and ~1.6 km -- both wrong. Rebuilding in UTM coordinates and converting to
  WGS 84 for export yielded exactly 250 000 m2 and 1 000 m, confirming the pipeline.

---

## 16. Future Scope

- **Database-backed persistence** -- replace JSON files with PostgreSQL + PostGIS or
  SQLite for multi-process deployments and efficient querying.
- **Async file I/O** -- use `aiofiles` for non-blocking disk writes in the storage layer.
- **GeoTIFF and GeoJSON support** -- extend `read_geodata` to accept additional formats.
- **Background processing** -- offload large file processing to a task queue (Celery, ARQ)
  so the HTTP response returns immediately with a job ID.
- **Pagination** -- the measurements list is returned whole; large files with thousands
  of features need paginated responses.
- **Authentication** -- add API key or OAuth2 bearer token protection.
- **Docker image** -- provide a `Dockerfile` and `docker-compose.yml` for containerised
  deployment.
- **Configurable limits** -- expose upload and uncompressed-ZIP size limits as environment
  variables instead of hard-coded constants.

---

## 17. Repository Information

| Item          | Value                                                    |
|---------------|----------------------------------------------------------|
| Repository    | https://github.com/BoppanaVisesh/GeoMeasure-API          |
| Clone command | `git clone https://github.com/BoppanaVisesh/GeoMeasure-API.git` |
| Language      | Python 3.12                                              |
| Framework     | FastAPI                                                  |

**Clone and run:**

```bash
git clone https://github.com/BoppanaVisesh/GeoMeasure-API.git
cd GeoMeasure-API
python -m venv .venv
# Windows:   .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# Open http://127.0.0.1:8000/docs
```
