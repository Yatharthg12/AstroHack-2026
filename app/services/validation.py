"""Small, explicit server-side validation helpers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


FOCUS_AREAS = {"career", "relationship", "finance", "education", "family", "personal growth"}
COMMUNICATION_PREFERENCES = {"concise", "supportive", "detailed"}
MOODS = {"grounded", "hopeful", "uncertain", "stretched", "low", "energised", "calm", "anxious"}
URGENCY_LEVELS = {"exploring", "soon", "time-sensitive"}
MODES = {"chat", "audio", "video"}
LANGUAGES = {"English", "Hindi", "Hinglish", "Tamil", "Telugu", "Bengali"}


class ValidationError(ValueError):
    """Expected client-input error with field-level details."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


def text_value(data: dict[str, Any], key: str, *, minimum: int = 1, maximum: int = 500) -> str:
    raw = data.get(key, "")
    if raw is None:
        raw = ""
    value = str(raw).strip()
    if len(value) < minimum:
        raise ValidationError(f"{key.replace('_', ' ').title()} is required.", key)
    if len(value) > maximum:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be {maximum} characters or fewer.", key)
    return value


def optional_text(data: dict[str, Any], key: str, *, maximum: int = 120) -> str | None:
    raw = data.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    value = str(raw).strip()
    if len(value) > maximum:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be {maximum} characters or fewer.", key)
    return value


def choice(data: dict[str, Any], key: str, allowed: set[str], *, normalize: bool = False) -> str:
    value = text_value(data, key, maximum=60)
    candidate = value.lower() if normalize else value
    lookup = {item.lower(): item for item in allowed} if normalize else {item: item for item in allowed}
    if candidate not in lookup:
        raise ValidationError(f"Choose a valid {key.replace('_', ' ')}.", key)
    return lookup[candidate]


def integer_value(data: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    try:
        value = int(data.get(key))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be a whole number.", key) from exc
    if not minimum <= value <= maximum:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be between {minimum} and {maximum}.", key)
    return value


def bool_value(data: dict[str, Any], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def iso_date(data: dict[str, Any], key: str, *, allow_future: bool = False) -> str:
    value = text_value(data, key, maximum=10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be a valid date.", key) from exc
    if not allow_future and parsed > date.today():
        raise ValidationError(f"{key.replace('_', ' ').title()} cannot be in the future.", key)
    if parsed.year < 1900:
        raise ValidationError(f"{key.replace('_', ' ').title()} must be after 1900.", key)
    return parsed.isoformat()


def optional_iso_time(data: dict[str, Any], key: str) -> str | None:
    raw = data.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    value = str(raw).strip()
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValidationError(
            f"{key.replace('_', ' ').title()} must be a valid 24-hour time.", key
        ) from exc
    return parsed.strftime("%H:%M")


def iso_future_date(data: dict[str, Any], key: str) -> str:
    value = text_value(data, key, maximum=25)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(value)
            parsed = datetime.combine(parsed_date, datetime.min.time())
        except ValueError as exc:
            raise ValidationError(f"{key.replace('_', ' ').title()} must be a valid date.", key) from exc
    return parsed.isoformat()
