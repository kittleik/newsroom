"""Newsroom configuration — reads from environment with sensible defaults."""

import os
from pathlib import Path

# Base directory (where app lives)
BASE_DIR = Path(__file__).parent

# Reports directory
REPORTS_DIR = Path(os.environ.get("NEWSROOM_REPORTS_DIR",
                   os.environ.get("REPORTS_DIR", str(BASE_DIR / "data" / "reports"))))

# Database path
DB_PATH = os.environ.get("NEWSROOM_DB_PATH", str(BASE_DIR / "newsroom.db"))

# Server config
HOST = os.environ.get("NEWSROOM_HOST", "0.0.0.0")
PORT = int(os.environ.get("NEWSROOM_PORT", "3118"))
DEBUG = os.environ.get("NEWSROOM_DEBUG", "").lower() in ("1", "true", "yes")
