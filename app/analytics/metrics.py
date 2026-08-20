"""Pure, testable calculations behind the Growth Cockpit."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


FUNNEL_STEPS = [
    ("Signed up", "signup_completed"),
    ("Onboarded", "onboarding_completed"),
    ("First Pulse", "pulse_completed"),
    ("Bridge brief", "brief_created"),
    ("Demo consultation", "consultation_booked"),
]


def _require(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"Missing analytics columns: {sorted(missing)}")


def safe_rate(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def activation_funnel(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Calculate a monotonic user funnel with step and overall conversion."""

    _require(frame, [column for _, column in FUNNEL_STEPS])
    eligible = pd.Series(True, index=frame.index)
    first_count = 0
    previous = 0
    result = []
    for index, (label, column) in enumerate(FUNNEL_STEPS):
        eligible &= frame[column].fillna(False).astype(bool)
        count = int(eligible.sum())
        if index == 0:
            first_count = count
            step_rate = 1.0 if count else 0.0
        else:
            step_rate = safe_rate(count, previous)
        result.append(
            {
                "step": label,
                "count": count,
                "step_conversion": round(step_rate, 4),
                "overall_conversion": round(safe_rate(count, first_count), 4),
            }
        )
        previous = count
    return result


def cohort_retention(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Return signup-month D1/D7/D30 retention for eligible cohorts."""

    columns = ["signup_date", "retained_d1", "retained_d7", "retained_d30"]
    _require(frame, columns)
    work = frame[columns].copy()
    work["signup_date"] = pd.to_datetime(work["signup_date"], errors="coerce")
    work = work.dropna(subset=["signup_date"])
    work["cohort"] = work["signup_date"].dt.to_period("M").astype(str)
    output = []
    for cohort, group in work.groupby("cohort", sort=True):
        output.append(
            {
                "cohort": cohort,
                "users": int(len(group)),
                "d1": round(float(group["retained_d1"].mean()), 4),
                "d7": round(float(group["retained_d7"].mean()), 4),
                "d30": round(float(group["retained_d30"].mean()), 4),
            }
        )
    return output


def k_factor(frame: pd.DataFrame) -> dict[str, float]:
    """Compute invites per eligible user × invite completion rate."""

    _require(frame, ["invites_created", "invites_opened", "invites_completed"])
    users = len(frame)
    created = max(float(frame["invites_created"].clip(lower=0).sum()), 0.0)
    opened = max(float(frame["invites_opened"].clip(lower=0).sum()), 0.0)
    completed = max(float(frame["invites_completed"].clip(lower=0).sum()), 0.0)
    invites_per_user = safe_rate(created, users)
    completion_rate = safe_rate(completed, created)
    return {
        "invites_per_user": round(invites_per_user, 4),
        "invite_rate": round(safe_rate((frame["invites_created"] > 0).sum(), users), 4),
        "invite_open_rate": round(safe_rate(opened, created), 4),
        "invite_completion_rate": round(completion_rate, 4),
        "k_factor": round(invites_per_user * completion_rate, 4),
    }


def assign_segments(frame: pd.DataFrame) -> pd.Series:
    """Transparent, mutually exclusive behavioural segments.

    Segments are descriptive rules, not inferred personality types.
    Priority makes the result stable when a user matches multiple rules.
    """

    needed = [
        "days_since_last_session",
        "pulse_checkins_30d",
        "consultations_90d",
        "briefs_started_30d",
        "referrals_created_90d",
    ]
    _require(frame, needed)
    conditions = [
        frame["days_since_last_session"] >= 21,
        (frame["briefs_started_30d"] > 0) | (frame["consultations_90d"] > 0),
        frame["referrals_created_90d"] > 0,
        frame["pulse_checkins_30d"] >= 8,
    ]
    choices = ["At-risk", "Guidance seeker", "Circle advocate", "Pulse regular"]
    return pd.Series(np.select(conditions, choices, default="Explorer"), index=frame.index)


def growth_summary(frame: pd.DataFrame) -> dict[str, object]:
    """Compute judge-facing headline metrics from one snapshot table."""

    _require(
        frame,
        [
            "weekly_active_days",
            "days_since_last_session",
            "sessions_7d",
            "sessions_30d",
            "pulse_checkins_7d",
            "consultations_90d",
            "repeat_consultation_90d",
            "retained_d1",
            "retained_d7",
            "retained_d30",
            "consultation_booked",
        ],
    )
    users = len(frame)
    # The snapshot has exact seven-day Pulse activity but only a 90-day
    # consultation aggregate. WGU therefore uses the defensible exact weekly
    # signal rather than pretending a 90-day consultation happened this week.
    weekly_guided = int((frame["pulse_checkins_7d"] > 0).sum())
    consultation_users = int((frame["consultations_90d"] > 0).sum())
    segments = assign_segments(frame).value_counts().to_dict()
    return {
        "users": users,
        "weekly_guided_users": weekly_guided,
        "weekly_guided_definition": "users with at least one Pulse check-in in the last 7 days",
        "dau_proxy": int((frame["days_since_last_session"] == 0).sum()),
        "wau": int((frame["sessions_7d"] > 0).sum()),
        "mau": int((frame["sessions_30d"] > 0).sum()),
        "retention": {
            "d1": round(float(frame["retained_d1"].mean()), 4) if users else 0.0,
            "d7": round(float(frame["retained_d7"].mean()), 4) if users else 0.0,
            "d30": round(float(frame["retained_d30"].mean()), 4) if users else 0.0,
        },
        "pulse_completion_rate": round(safe_rate((frame["pulse_checkins_7d"] > 0).sum(), users), 4),
        "consultation_conversion": round(safe_rate(frame["consultation_booked"].sum(), users), 4),
        "repeat_consultation_rate": round(
            safe_rate(frame["repeat_consultation_90d"].sum(), consultation_users), 4
        ),
        "referral": k_factor(frame),
        "segments": {str(key): int(value) for key, value in segments.items()},
        "provenance": "synthetic demonstration data; not measured AstroLive performance",
    }
