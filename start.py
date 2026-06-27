from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()


def npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def ensure_backend_deps(backend: Path) -> None:
    """Install backend requirements when any runtime dependency is missing."""
    required_modules = ("uvicorn", "fastapi", "pypdf", "joblib", "numpy", "xgboost")
    if all(importlib.util.find_spec(module) is not None for module in required_modules):
        return

    print("Backend dependencies not found. Installing from backend/requirements.txt...")
    print(f"Using Python interpreter: {sys.executable}")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(backend / "requirements.txt")],
        cwd=backend,
    )
    print("Backend dependencies installed.")


def main() -> None:
    frontend = ROOT / "frontend"
    backend = ROOT / "backend"
    env = os.environ.copy()
    env.setdefault("FACADEGPT_DB", str(backend / "facadegpt.db"))

    if not (frontend / "node_modules").exists():
        print("Installing frontend dependencies...")
        subprocess.check_call([npm_cmd(), "install"], cwd=frontend, env=env)

    ensure_backend_deps(backend)

    print("Starting FacadeGPT backend at http://127.0.0.1:8000")
    print(f"Using Python interpreter: {sys.executable}")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd=backend,
        env=env,
    )
    try:
        print("Starting FacadeGPT frontend at http://localhost:5173")
        subprocess.check_call([npm_cmd(), "run", "dev", "--", "--host", "127.0.0.1"], cwd=frontend, env=env)
    finally:
        backend_proc.terminate()


if __name__ == "__main__":
    main()
