"""Validation boundary for the public synthetic analytics table."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.features import FEATURES, TARGETS


BINARY_COLUMNS = [
    "signup_completed",
    "onboarding_completed",
    "pulse_completed",
    "brief_created",
    "consultation_booked",
    "repeat_consultation_90d",
    "retained_d1",
    "retained_d7",
    "retained_d30",
    *TARGETS.values(),
]


def validate_demo_data(frame: pd.DataFrame) -> None:
    """Raise a concise error when synthetic snapshot invariants are broken."""

    required = {
        "user_id",
        "data_provenance",
        "as_of_date",
        "signup_date",
        "focus_area",
        *FEATURES,
        *BINARY_COLUMNS,
        "invites_created",
        "invites_opened",
        "invites_completed",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset columns missing: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Dataset has no rows")
    if frame[list(required)].isna().any().any():
        raise ValueError("Dataset has missing required values")
    if frame["user_id"].duplicated().any():
        raise ValueError("Dataset has duplicate user IDs")
    if not frame["data_provenance"].eq("synthetic_demo").all():
        raise ValueError("Unexpected data provenance")
    for column in FEATURES:
        values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Feature {column} must be finite numeric data")
        if (values < 0).any():
            raise ValueError(f"Feature {column} cannot be negative")
    if (frame["weekly_active_days"] > 7).any():
        raise ValueError("weekly_active_days cannot exceed 7")
    if (frame["weekly_active_days"] > frame["sessions_7d"]).any():
        raise ValueError("weekly_active_days cannot exceed sessions_7d")
    if not frame["feedback_helpful_rate"].between(0, 1).all():
        raise ValueError("feedback_helpful_rate must be between 0 and 1")
    if (frame["sessions_7d"] > frame["sessions_30d"]).any() or (
        frame["pulse_checkins_7d"] > frame["pulse_checkins_30d"]
    ).any():
        raise ValueError("Short-window counts cannot exceed long-window counts")
    if (frame["pulse_checkins_7d"] > frame["sessions_7d"]).any() or (
        frame["pulse_checkins_30d"] > frame["sessions_30d"]
    ).any():
        raise ValueError("Pulse counts cannot exceed sessions")
    no_monthly_session = frame["sessions_30d"] == 0
    if (
        (frame.loc[no_monthly_session, "content_diversity_30d"] != 0).any()
        or (frame.loc[no_monthly_session, "pulse_checkins_30d"] != 0).any()
        or (frame.loc[no_monthly_session, "briefs_started_30d"] != 0).any()
    ):
        raise ValueError("30-day activity features require a 30-day session")
    seven_day_recency = frame["days_since_last_session"] < 7
    thirty_day_recency = frame["days_since_last_session"] < 30
    if not seven_day_recency.eq(frame["sessions_7d"] > 0).all():
        raise ValueError("7-day session count and recency are inconsistent")
    if not thirty_day_recency.eq(frame["sessions_30d"] > 0).all():
        raise ValueError("30-day session count and recency are inconsistent")
    for column in BINARY_COLUMNS:
        if not frame[column].isin([0, 1, False, True]).all():
            raise ValueError(f"Column {column} must be binary")
    as_of = pd.to_datetime(frame["as_of_date"], errors="coerce")
    signup = pd.to_datetime(frame["signup_date"], errors="coerce")
    if as_of.isna().any() or signup.isna().any() or (signup > as_of).any():
        raise ValueError("Invalid temporal coverage")
    if (frame[["invites_created", "invites_opened", "invites_completed"]] < 0).any().any():
        raise ValueError("Referral counts cannot be negative")
    if (frame["invites_completed"] > frame["invites_opened"]).any() or (
        frame["invites_opened"] > frame["invites_created"]
    ).any():
        raise ValueError("Referral funnel ordering is invalid")
    funnel = frame[
        ["signup_completed", "onboarding_completed", "pulse_completed", "brief_created", "consultation_booked"]
    ]
    if (np.diff(funnel.to_numpy(dtype=int), axis=1) > 0).any():
        raise ValueError("Activation funnel ordering is invalid")
    if not frame["pulse_completed"].eq(frame["pulse_checkins_30d"] > 0).all():
        raise ValueError("Pulse activation flag and 30-day count are inconsistent")
    if not frame["brief_created"].eq(frame["briefs_started_30d"] > 0).all():
        raise ValueError("Brief activation flag and 30-day count are inconsistent")
    retention = frame[["retained_d1", "retained_d7", "retained_d30"]]
    if (np.diff(retention.to_numpy(dtype=int), axis=1) > 0).any():
        raise ValueError("Retention ordering is invalid")
