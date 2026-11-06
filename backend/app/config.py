"""Runtime configuration.

Keys are read from the server environment only. A repo-root ``.env`` is parsed for
local development, but never echoed back, logged, or sent to the browser.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal ``.env`` reader: ``KEY=VALUE`` lines, no expansion, no override."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(Path(os.environ.get("MREAD_ENV_FILE") or REPO_ROOT / ".env"))

# Two data profiles keep development work and real research apart:
#   dev   -> <repo>/data/dev     scratch runs, fake-model trials, safe to delete
#   daily -> <repo>/data/daily   the researcher's real cases and uploads
# MREAD_DATA_DIR overrides both (tests point it at a temporary directory).
DATA_PROFILE = (os.environ.get("MREAD_PROFILE") or "dev").strip().lower() or "dev"
_DATA_ROOT = REPO_ROOT / "data"

if os.environ.get("MREAD_DATA_DIR"):
    DATA_DIR = Path(os.environ["MREAD_DATA_DIR"])
else:
    DATA_DIR = _DATA_ROOT / DATA_PROFILE

DB_PATH = DATA_DIR / "mread.db"
ASSET_DIR = DATA_DIR / "assets"

IMAGE_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
ARTICLE_SUFFIXES = {".pdf", ".txt", ".md"}

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_ARTICLE_BYTES = 10 * 1024 * 1024

# Provider selection: "fake" for deterministic flow tests, "openai" for a real
# OpenAI-compatible endpoint.
PROVIDER = os.environ.get("MREAD_PROVIDER") or ("openai" if os.environ.get("DEEPSEEK_API_KEY") else "fake")
OPENAI_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
OPENAI_BASE_URL = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL") or "deepseek-chat"
REQUEST_TIMEOUT = float(os.environ.get("MREAD_REQUEST_TIMEOUT") or 120)

# When the configured endpoint cannot read images, image parts are not attached and the
# run record says so. Flow correctness is unaffected; the researcher sees the limit.
TEXT_ONLY = os.environ.get("MREAD_TEXT_ONLY") == "1"

# Tests and the decision endpoint can run steps inline instead of in a background thread.
SYNC_RUNS = os.environ.get("MREAD_SYNC_RUNS") == "1"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)


def describe_data_location() -> str:
    """One line naming the data directory, for the server log. No material, no keys."""
    return f"MRead data: {DATA_DIR} (profile={DATA_PROFILE})"
