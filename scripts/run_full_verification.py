"""Full verification script: E2E + persistence + fresh copy + git status.

Run from project root:
    python scripts/run_full_verification.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PORT = 8002
BASE_URL = f"http://127.0.0.1:{PORT}"
SAMPLE = BASE / "sample_data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sep(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def http_get(url: str) -> tuple[int, dict]:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def http_post_file(url: str, file_path: Path, field: str = "file") -> tuple[int, dict]:
    """Multipart POST a single file."""
    import http.client, uuid as _uuid, mimetypes
    boundary = _uuid.uuid4().hex
    ct = f"multipart/form-data; boundary={boundary}"
    filename = file_path.name
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body_prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode()
    body_suffix = f"\r\n--{boundary}--\r\n".encode()
    data = body_prefix + file_path.read_bytes() + body_suffix
    parsed = urllib.request.urlparse(url)  # type: ignore[attr-defined]
    from urllib.parse import urlparse
    p = urlparse(url)
    conn = http.client.HTTPConnection(p.hostname, p.port, timeout=30)
    conn.request("POST", p.path, body=data, headers={"Content-Type": ct})
    resp = conn.getresponse()
    status = resp.status
    body = json.loads(resp.read())
    conn.close()
    return status, body


def wait_for_server(url: str, retries: int = 20, delay: float = 0.5) -> bool:
    for _ in range(retries):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(delay)
    return False


def start_uvicorn() -> subprocess.Popen:
    env = os.environ.copy()
    env["GEOMEASURE_DATA_DIR"] = str(BASE / "data")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BASE),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc


# ---------------------------------------------------------------------------
# PART B  –  Live end-to-end
# ---------------------------------------------------------------------------

def part_b_live_e2e(uploaded_ids: dict) -> None:
    sep("PART B: Live E2E — POST + GET + measurements for 3 sample files")

    files = {
        "sample.kml": SAMPLE / "sample.kml",
        "sample_shapefile.zip": SAMPLE / "sample_shapefile.zip",
        "sample_projected_shapefile.zip": SAMPLE / "sample_projected_shapefile.zip",
    }

    for label, fpath in files.items():
        print(f"\n--- {label} ---")

        # POST
        status, body = http_post_file(f"{BASE_URL}/api/files/", fpath)
        print(f"POST /api/files/ -> {status}")
        print(json.dumps(body, indent=2))
        assert status == 201, f"Expected 201 got {status}"

        file_id = body["id"]
        uploaded_ids[label] = file_id

        # GET file info
        status2, body2 = http_get(f"{BASE_URL}/api/files/{file_id}/")
        print(f"GET /api/files/{file_id}/ -> {status2}")
        print(json.dumps(body2, indent=2))
        assert status2 == 200

        # GET measurements (default: no geometry)
        status3, body3 = http_get(f"{BASE_URL}/api/files/{file_id}/measurements/")
        print(f"GET /api/files/{file_id}/measurements/ -> {status3}")
        assert status3 == 200
        print(f"  feature_count: {body3['feature_count']}")
        for m in body3["measurements"]:
            print(
                f"  feature_id={m['feature_id']}  geometry_type={m['geometry_type']}"
                f"  area={m.get('area')}  length={m.get('length')}"
                f"  projected_crs={m.get('projected_crs')}  status={m['measurement_status']}"
            )

    # include_geometry=true for sample.kml
    kml_id = uploaded_ids["sample.kml"]
    print(f"\n--- include_geometry=true for sample.kml (id={kml_id}) ---")
    status_g, body_g = http_get(f"{BASE_URL}/api/files/{kml_id}/measurements/?include_geometry=true")
    print(f"GET /measurements/?include_geometry=true -> {status_g}")
    assert status_g == 200
    for m in body_g["measurements"]:
        geom = m.get("geometry")
        if geom:
            coords = geom.get("coordinates")
            print(
                f"  feature_id={m['feature_id']}  geometry_type={m['geometry_type']}"
                f"  geom.type={geom.get('type')}  coords_present={coords is not None}"
            )
        else:
            print(f"  feature_id={m['feature_id']}  geometry_type={m['geometry_type']}  geometry=null")


# ---------------------------------------------------------------------------
# PART C  –  Error checks
# ---------------------------------------------------------------------------

def part_c_errors() -> None:
    sep("PART C: Error checks")

    # 1. sample_no_prj.zip → 422
    status, body = http_post_file(f"{BASE_URL}/api/files/", SAMPLE / "sample_no_prj.zip")
    print(f"sample_no_prj.zip -> HTTP {status}  body={body}")
    assert status == 422, f"Expected 422 got {status}"

    # 2. .txt → 415
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"hello world")
        txt_path = Path(f.name)
    status, body = http_post_file(f"{BASE_URL}/api/files/", txt_path)
    txt_path.unlink(missing_ok=True)
    print(f".txt file -> HTTP {status}  body={body}")
    assert status == 415, f"Expected 415 got {status}"

    # 3. Garbage bytes named .kml → 400
    with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as f:
        f.write(b"\x00\xff\x00garbage\xde\xad\xbe\xef")
        garbage_path = Path(f.name)
    status, body = http_post_file(f"{BASE_URL}/api/files/", garbage_path)
    garbage_path.unlink(missing_ok=True)
    print(f"garbage .kml -> HTTP {status}  body={body}")
    assert status == 400, f"Expected 400 got {status}"

    # 4. Unknown UUID on GET /api/files/{id}/ → 404
    fake_id = "00000000-0000-0000-0000-000000000000"
    status, body = http_get(f"{BASE_URL}/api/files/{fake_id}/")
    print(f"GET /api/files/{fake_id}/ -> HTTP {status}  body={body}")
    assert status == 404, f"Expected 404 got {status}"

    # 5. Unknown UUID on GET /api/files/{id}/measurements/ → 404
    status, body = http_get(f"{BASE_URL}/api/files/{fake_id}/measurements/")
    print(f"GET /api/files/{fake_id}/measurements/ -> HTTP {status}  body={body}")
    assert status == 404, f"Expected 404 got {status}"

    print("\nAll error checks PASSED.")


# ---------------------------------------------------------------------------
# PART D  –  Persistence across restart
# ---------------------------------------------------------------------------

def part_d_persistence(uvicorn_proc: subprocess.Popen, uploaded_ids: dict) -> None:
    sep("PART D: Persistence — restart uvicorn, re-GET same id")

    kml_id = uploaded_ids.get("sample.kml")
    if not kml_id:
        print("ERROR: sample.kml id not captured — skipping persistence test")
        return

    print(f"Stopping uvicorn (pid {uvicorn_proc.pid})...")
    uvicorn_proc.terminate()
    try:
        uvicorn_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        uvicorn_proc.kill()
    print("Uvicorn stopped.")

    print("Restarting uvicorn...")
    new_proc = start_uvicorn()
    if not wait_for_server(f"{BASE_URL}/health"):
        print("ERROR: Server did not restart in time.")
        return new_proc

    status, body = http_get(f"{BASE_URL}/api/files/{kml_id}/")
    print(f"GET /api/files/{kml_id}/ after restart -> HTTP {status}")
    print(json.dumps(body, indent=2))
    assert status == 200, f"Expected 200 got {status} — persistence FAILED"
    print("Persistence PASSED: record survived server restart.")
    return new_proc


# ---------------------------------------------------------------------------
# PART E  –  Fresh copy
# ---------------------------------------------------------------------------

def part_e_fresh_copy() -> None:
    sep("PART E: Fresh copy — copy repo, new venv, pip install, pytest")

    tmp_dir = Path(tempfile.mkdtemp(prefix="geomeasure_fresh_"))
    dest = tmp_dir / "GeoMeasure-API"
    print(f"Copying repo to {dest} (excluding .venv, .git, data, __pycache__)...")

    ignore = shutil.ignore_patterns(
        ".venv", ".git", "data", "__pycache__", "*.pyc",
        ".pytest_cache", ".idea", ".vscode",
    )
    shutil.copytree(str(BASE), str(dest), ignore=ignore)
    print("Copy done.")

    # Create venv
    print("Creating virtual environment...")
    result = subprocess.run(
        [sys.executable, "-m", "venv", str(dest / ".venv")],
        capture_output=True, text=True
    )
    print(result.stdout or "")
    if result.returncode != 0:
        print("ERROR creating venv:", result.stderr)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    venv_python = dest / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = dest / ".venv" / "bin" / "python"

    # pip install
    print("Running pip install -r requirements.txt...")
    result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt",
         "--quiet", "--disable-pip-version-check"],
        cwd=str(dest),
        capture_output=True, text=True
    )
    print(result.stdout[-2000:] if result.stdout else "")
    if result.returncode != 0:
        print("pip install FAILED:")
        print(result.stderr[-2000:])
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return
    print("pip install succeeded.")

    # Run pytest
    print("Running pytest -v...")
    env = os.environ.copy()
    env["GEOMEASURE_DATA_DIR"] = str(dest / "data_test")
    result = subprocess.run(
        [str(venv_python), "-m", "pytest", "-v"],
        cwd=str(dest),
        capture_output=True, text=True,
        env=env,
    )
    print(result.stdout[-5000:])
    if result.returncode != 0:
        print("pytest FAILED:")
        print(result.stderr[-2000:])
    else:
        print("Fresh-copy pytest PASSED.")

    # Cleanup
    print(f"Deleting temp folder {tmp_dir}...")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("Done.")


# ---------------------------------------------------------------------------
# PART F  –  git status
# ---------------------------------------------------------------------------

def part_f_git_status() -> None:
    sep("PART F: git status")

    result = subprocess.run(
        ["git", "status"],
        cwd=str(BASE),
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)

    # Confirm ignored
    ignored = [".venv", "data/", "__pycache__", ".pytest_cache", ".env"]
    for item in ignored:
        r = subprocess.run(
            ["git", "check-ignore", "-v", item],
            cwd=str(BASE), capture_output=True, text=True
        )
        status_str = "IGNORED" if r.returncode == 0 else "NOT ignored (check .gitignore)"
        print(f"  {item:30s} -> {status_str}  {r.stdout.strip()}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sep("Starting GeoMeasure API Full Verification")

    # Start uvicorn
    print(f"Starting uvicorn on port {PORT}...")
    uvicorn_proc = start_uvicorn()
    if not wait_for_server(f"{BASE_URL}/health"):
        print("ERROR: Uvicorn did not start. Aborting.")
        uvicorn_proc.kill()
        sys.exit(1)
    print(f"Server up at {BASE_URL}/health")

    try:
        uploaded_ids: dict = {}

        part_b_live_e2e(uploaded_ids)
        part_c_errors()
        result = part_d_persistence(uvicorn_proc, uploaded_ids)
        if result is not None:
            uvicorn_proc = result

    finally:
        print(f"\nStopping uvicorn (pid {uvicorn_proc.pid})...")
        uvicorn_proc.terminate()
        try:
            uvicorn_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            uvicorn_proc.kill()
        print("Uvicorn stopped.")

    part_e_fresh_copy()
    part_f_git_status()

    sep("Full verification complete")


if __name__ == "__main__":
    main()
