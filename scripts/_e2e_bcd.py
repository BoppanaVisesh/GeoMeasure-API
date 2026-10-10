"""Parts B, C, D: Live E2E checks with a real uvicorn server on port 8002."""
import http.client
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as _uuid_mod
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PORT = 8002
BASE_URL = f"http://127.0.0.1:{PORT}"
SAMPLE = BASE / "sample_data"


def http_get(path: str):
    url = BASE_URL + path
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def http_post_file(path: str, file_path: Path):
    boundary = _uuid_mod.uuid4().hex
    filename = file_path.name
    body_prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body_suffix = f"\r\n--{boundary}--\r\n".encode()
    data = body_prefix + file_path.read_bytes() + body_suffix
    p = urllib.parse.urlparse(BASE_URL + path)
    conn = http.client.HTTPConnection(p.hostname, p.port, timeout=30)
    conn.request(
        "POST", p.path, body=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = conn.getresponse()
    status = resp.status
    body = json.loads(resp.read())
    conn.close()
    return status, body


def wait_for_server(retries=30, delay=0.5):
    for _ in range(retries):
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=2)
            return True
        except Exception:
            time.sleep(delay)
    return False


def start_uvicorn():
    env = os.environ.copy()
    env["GEOMEASURE_DATA_DIR"] = str(BASE / "data")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BASE), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ─── Start ────────────────────────────────────────────────────────────────────
print("=" * 70)
print("  PART B: Live E2E — POST + GET + measurements for 3 sample files")
print("=" * 70)

proc = start_uvicorn()
if not wait_for_server():
    print("ERROR: server did not start"); stop(proc); sys.exit(1)
print(f"Server up at {BASE_URL}/health\n")

uploaded_ids = {}

for label, fpath in [
    ("sample.kml", SAMPLE / "sample.kml"),
    ("sample_shapefile.zip", SAMPLE / "sample_shapefile.zip"),
    ("sample_projected_shapefile.zip", SAMPLE / "sample_projected_shapefile.zip"),
]:
    print(f"\n--- {label} ---")
    s, b = http_post_file("/api/files/", fpath)
    print(f"POST /api/files/ -> HTTP {s}")
    print(json.dumps(b, indent=2))
    assert s == 201, f"Expected 201 got {s}"
    file_id = b["id"]
    uploaded_ids[label] = file_id

    s2, b2 = http_get(f"/api/files/{file_id}/")
    print(f"GET /api/files/{file_id}/ -> HTTP {s2}")
    print(json.dumps(b2, indent=2))
    assert s2 == 200

    s3, b3 = http_get(f"/api/files/{file_id}/measurements/")
    print(f"GET /api/files/{file_id}/measurements/ -> HTTP {s3}")
    assert s3 == 200
    for m in b3["measurements"]:
        print(
            f"  feature_id={m['feature_id']}  geometry_type={m['geometry_type']}"
            f"  area={m.get('area')}  length={m.get('length')}"
            f"  projected_crs={m.get('projected_crs')}  status={m['measurement_status']}"
        )

# include_geometry=true for sample.kml
kml_id = uploaded_ids["sample.kml"]
print(f"\n--- include_geometry=true for sample.kml (id={kml_id}) ---")
s_g, b_g = http_get(f"/api/files/{kml_id}/measurements/?include_geometry=true")
print(f"GET /measurements/?include_geometry=true -> HTTP {s_g}")
assert s_g == 200
for m in b_g["measurements"]:
    geom = m.get("geometry")
    if geom:
        print(
            f"  feature_id={m['feature_id']}  geometry_type={m['geometry_type']}"
            f"  geom.type={geom.get('type')}  coords_present={geom.get('coordinates') is not None}"
        )
    else:
        print(f"  feature_id={m['feature_id']}  geometry_type={m['geometry_type']}  geometry=null")

print("\n" + "=" * 70)
print("  PART C: Error checks")
print("=" * 70)

# no_prj -> 422
s, b = http_post_file("/api/files/", SAMPLE / "sample_no_prj.zip")
print(f"sample_no_prj.zip -> HTTP {s}  detail={b.get('detail','')[:120]}")
assert s == 422, f"Expected 422 got {s}"

# .txt -> 415
with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
    f.write(b"hello world"); txt = Path(f.name)
s, b = http_post_file("/api/files/", txt)
txt.unlink(missing_ok=True)
print(f".txt file -> HTTP {s}  detail={b.get('detail','')[:120]}")
assert s == 415, f"Expected 415 got {s}"

# garbage bytes named .kml -> 400
with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as f:
    f.write(b"\x00\xff\xde\xadgarbagedata"); kml_bad = Path(f.name)
s, b = http_post_file("/api/files/", kml_bad)
kml_bad.unlink(missing_ok=True)
print(f"garbage .kml -> HTTP {s}  detail={b.get('detail','')[:120]}")
assert s == 400, f"Expected 400 got {s}"

# unknown UUID GET /api/files/ -> 404
fake = "00000000-0000-0000-0000-000000000000"
s, b = http_get(f"/api/files/{fake}/")
print(f"GET /api/files/{fake}/ -> HTTP {s}  detail={b.get('detail','')[:80]}")
assert s == 404, f"Expected 404 got {s}"

# unknown UUID GET /api/files/{id}/measurements/ -> 404
s, b = http_get(f"/api/files/{fake}/measurements/")
print(f"GET /api/files/{fake}/measurements/ -> HTTP {s}  detail={b.get('detail','')[:80]}")
assert s == 404, f"Expected 404 got {s}"

print("All error checks PASSED.")

print("\n" + "=" * 70)
print("  PART D: Persistence — restart uvicorn, re-GET same id")
print("=" * 70)

kml_id = uploaded_ids["sample.kml"]
print(f"Uploaded sample.kml id: {kml_id}")
print(f"Stopping uvicorn (pid {proc.pid})...")
stop(proc)
print("Stopped. Restarting...")
proc2 = start_uvicorn()
if not wait_for_server():
    print("ERROR: server did not restart"); stop(proc2); sys.exit(1)
print("Restarted.")
s, b = http_get(f"/api/files/{kml_id}/")
print(f"GET /api/files/{kml_id}/ after restart -> HTTP {s}")
print(json.dumps(b, indent=2))
assert s == 200, f"Expected 200 got {s} -- persistence FAILED"
print("Persistence PASSED: record survived server restart.")

stop(proc2)
print("Uvicorn stopped.")
print("\nParts B, C, D complete.")
