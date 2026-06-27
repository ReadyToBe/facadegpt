from __future__ import annotations

import os
from pathlib import Path
import csv

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
BOOKS_DIR = ROOT_DIR / "books"
KEYS_DIR = ROOT_DIR / "keys"


def load_env_files() -> None:
    for path in (ROOT_DIR / ".env", BACKEND_DIR / ".env"):
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _read_deepseek_key_file() -> str | None:
    path = KEYS_DIR / "ds.txt"
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8-sig", errors="ignore").strip().splitlines()
    return value[0].strip() if value else None


def _read_dashscope_key_file() -> str | None:
    if not KEYS_DIR.exists():
        return None
    for path in KEYS_DIR.glob("*.csv"):
        try:
            rows = list(csv.reader(path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()))
        except OSError:
            continue
        for row in rows:
            if len(row) >= 2 and row[0].strip().lower() in {"apikey", "api_key", "key"}:
                return row[1].strip()
    return None


load_env_files()


def openai_api_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or None


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-5.5")


def embedding_model() -> str:
    return os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "deepseek").lower()


def deepseek_api_key() -> str | None:
    return os.environ.get("DEEPSEEK_API_KEY") or _read_deepseek_key_file()


def deepseek_model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")


def deepseek_base_url() -> str:
    return os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")


def image_provider() -> str:
    return os.environ.get("IMAGE_PROVIDER", "dashscope").lower()


def dashscope_api_key() -> str | None:
    return os.environ.get("DASHSCOPE_API_KEY") or _read_dashscope_key_file()


def dashscope_image_model() -> str:
    return os.environ.get("DASHSCOPE_IMAGE_MODEL", "wan2.7-image")
