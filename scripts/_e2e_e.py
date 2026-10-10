"""Part E: Fresh copy test -- copy repo (no .venv/.git/data), new venv, pip install, pytest."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
tmp_dir = Path(tempfile.mkdtemp(prefix="gm_fresh_"))
dest = tmp_dir / "GeoMeasure-API"

print("=" * 70)
print("  PART E: Fresh copy")
print("=" * 70)

print(f"\nCopying repo to: {dest}")
print("(Excluding: .venv, .git, data, __pycache__, .pytest_cache)")

ignore = shutil.ignore_patterns(
    ".venv", ".git", "data", "__pycache__", "*.pyc",
    ".pytest_cache", ".idea", ".vscode",
)
shutil.copytree(str(BASE), str(dest), ignore=ignore)
print("Copy complete.")

# Remove helper scripts that are not part of the repo itself
for helper in ["_e2e_bcd.py", "_grep_readme.py", "_e2e_e.py", "run_full_verification.py"]:
    p = dest / "scripts" / helper
    if p.exists():
        p.unlink()

print("\nCreating virtual environment...")
r = subprocess.run([sys.executable, "-m", "venv", str(dest / ".venv")],
                   capture_output=True, text=True)
print(r.stdout or "(no stdout)")
if r.returncode != 0:
    print("VENV FAILED:", r.stderr)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    sys.exit(1)
print("Venv created.")

venv_py = dest / ".venv" / "Scripts" / "python.exe"
if not venv_py.exists():
    venv_py = dest / ".venv" / "bin" / "python"

print("\nRunning: pip install -r requirements.txt")
r = subprocess.run(
    [str(venv_py), "-m", "pip", "install", "-r", "requirements.txt",
     "--quiet", "--disable-pip-version-check"],
    cwd=str(dest), capture_output=True, text=True
)
print(r.stdout[-1000:] if r.stdout else "(no stdout)")
if r.returncode != 0:
    print("PIP INSTALL FAILED:")
    print(r.stderr[-2000:])
    shutil.rmtree(tmp_dir, ignore_errors=True)
    sys.exit(1)
print("pip install succeeded.")

print("\nRunning: pytest -v")
env = os.environ.copy()
env["GEOMEASURE_DATA_DIR"] = str(dest / "data_test")
r = subprocess.run(
    [str(venv_py), "-m", "pytest", "-v"],
    cwd=str(dest), capture_output=True, text=True, env=env
)
print(r.stdout)
if r.stderr:
    print("[stderr]", r.stderr[-500:])
if r.returncode == 0:
    print("Fresh-copy pytest: PASSED")
else:
    print("Fresh-copy pytest: FAILED")

print(f"\nDeleting temp folder: {tmp_dir}")
shutil.rmtree(tmp_dir, ignore_errors=True)
print("Done.")
