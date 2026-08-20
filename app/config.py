"""Environment-driven configuration with safe development defaults."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
_configured_secret = os.environ.get("ORBIT_SECRET_KEY")


class Config:
    SECRET_KEY = _configured_secret or secrets.token_hex(32)
    SECRET_KEY_IS_FALLBACK = not bool(_configured_secret)
    DATABASE = os.environ.get("ORBIT_DATABASE", str(BASE_DIR / "instance" / "orbit.db"))
    MODEL_DIR = os.environ.get("ORBIT_MODEL_DIR", str(BASE_DIR / "artifacts" / "models"))
    DEMO_DATA_PATH = os.environ.get(
        "ORBIT_DEMO_DATA", str(BASE_DIR / "data" / "demo" / "synthetic_orbit_users.csv")
    )
    MAX_CONTENT_LENGTH = 64 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("ORBIT_SECURE_COOKIES", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    SESSION_REFRESH_EACH_REQUEST = False
    JSON_SORT_KEYS = False
    REFERRAL_TTL_HOURS = 168
    RATE_LIMIT_PER_MINUTE = 30
    EXPERIMENT_RATE_LIMIT_PER_MINUTE = 6
    EXPERIMENT_MAX_CONCURRENCY = 2
