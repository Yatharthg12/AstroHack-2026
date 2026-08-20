"""Growth Cockpit adapter with an honest graceful fallback."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from flask import current_app


@lru_cache(maxsize=12)
def _cached_snapshot(path: str, model_path: str, period: str, segment: str, focus: str) -> dict:
    try:
        from app.analytics.dashboard import snapshot

        return snapshot(
            period=period,
            segment=segment,
            focus=focus,
            data_path=Path(path),
            model_dir=Path(model_path),
        )
    except (ImportError, FileNotFoundError, ValueError, KeyError) as exc:
        return {
            "data_label": "Unavailable — generate the synthetic demo dataset locally",
            "source": "No supplied or generated behavioural dataset was found.",
            "north_star": {"name": "Weekly Guided Users", "value": None},
            "activity": {"dau": None, "wau": None, "mau": None},
            "retention": {"d1": None, "d7": None, "d30": None, "cohorts": []},
            "funnel": [],
            "referrals": {},
            "distributions": {"churn_risk": [], "consultation_intent": [], "segments": []},
            "model": {"status": "fallback", "limitations": ["Model artifacts are optional; deterministic product flows remain available."], "error": str(exc)},
            "users": [],
            "filters": {"period": period, "segment": segment, "focus": focus},
        }


def growth_snapshot(period: str = "90d", segment: str = "all", focus: str = "all") -> dict:
    if period not in {"30d", "90d", "180d", "all"}:
        period = "90d"
    if len(segment) > 50:
        segment = "all"
    if len(focus) > 50:
        focus = "all"
    return _cached_snapshot(
        current_app.config["DEMO_DATA_PATH"],
        current_app.config["MODEL_DIR"],
        period,
        segment,
        focus,
    )
