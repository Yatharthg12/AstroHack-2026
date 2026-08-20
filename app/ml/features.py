"""Leakage-safe feature definitions shared by training and inference."""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


FEATURES = [
    "account_age_days",
    "days_since_last_session",
    "sessions_7d",
    "sessions_30d",
    "pulse_checkins_7d",
    "pulse_checkins_30d",
    "weekly_active_days",
    "avg_session_minutes",
    "content_diversity_30d",
    "consultations_90d",
    "days_since_last_consultation",
    "briefs_started_30d",
    "referrals_created_90d",
    "feedback_helpful_rate",
]

TARGETS = {
    "churn_risk": "future_30d_churn",
    "consultation_intent": "future_14d_consultation",
}

# These fields are outcomes or happen after the prediction cutoff.  Keeping a
# named deny-list makes leakage tests and review straightforward.
FORBIDDEN_FEATURES = {
    *TARGETS.values(),
    "future_sessions_30d",
    "future_revenue_30d",
    "consultation_booked",
    "retained_d30",
}

DEFAULT_VALUES = {
    "account_age_days": 30.0,
    "days_since_last_session": 14.0,
    "sessions_7d": 0.0,
    "sessions_30d": 2.0,
    "pulse_checkins_7d": 0.0,
    "pulse_checkins_30d": 1.0,
    "weekly_active_days": 1.0,
    "avg_session_minutes": 5.0,
    "content_diversity_30d": 1.0,
    "consultations_90d": 0.0,
    "days_since_last_consultation": 180.0,
    "briefs_started_30d": 0.0,
    "referrals_created_90d": 0.0,
    "feedback_helpful_rate": 0.5,
}


def validate_feature_contract(features: list[str] | None = None) -> None:
    """Raise if a training feature is a known outcome or duplicated."""

    names = features or FEATURES
    leaked = set(names) & FORBIDDEN_FEATURES
    if leaked:
        raise ValueError(f"Target leakage detected: {sorted(leaked)}")
    if len(names) != len(set(names)):
        raise ValueError("Duplicate model features are not allowed")


def feature_frame(data: pd.DataFrame | Mapping[str, object]) -> pd.DataFrame:
    """Return a finite numeric frame in the canonical feature order.

    Missing fields use documented neutral defaults so the demo degrades
    gracefully for new users with sparse history.  Training data should still
    be validated separately and is not silently imputed by this function.
    """

    validate_feature_contract()
    if isinstance(data, Mapping):
        data = pd.DataFrame([data])
    frame = pd.DataFrame(index=data.index)
    for name in FEATURES:
        source = data[name] if name in data.columns else DEFAULT_VALUES[name]
        frame[name] = pd.to_numeric(source, errors="coerce")
        frame[name] = frame[name].fillna(DEFAULT_VALUES[name])
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Model features must be finite numeric values")
    return frame.astype(float)
