"""Generate the reproducible, explicitly synthetic Orbit behavioural dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


SEED = 2026
ROWS = 2400
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "demo" / "synthetic_orbit_users.csv"


def sigmoid(value: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(value, -35, 35)))


def generate(rows: int = ROWS, seed: int = SEED) -> pd.DataFrame:
    """Create one consent-safe behavioural snapshot per fictional user.

    Outcomes are sampled from future windows relative to ``as_of_date``.  No
    names, birth details, free text, locations, contact details, or actual
    AstroLive records are represented.
    """

    if rows < 100:
        raise ValueError("At least 100 rows are required for stable demo splits")
    rng = np.random.default_rng(seed)
    user_ids = [f"SYN-{number:05d}" for number in range(1, rows + 1)]
    start = np.datetime64("2026-01-01")
    as_of_offsets = rng.integers(0, 212, rows)
    as_of = start + as_of_offsets.astype("timedelta64[D]")
    account_age = rng.integers(30, 540, rows)
    signup = as_of - account_age.astype("timedelta64[D]")

    affinity = rng.normal(0, 1, rows)
    recent_interest = 0.75 * affinity + rng.normal(0, 0.75, rows)
    friction = rng.normal(0, 1, rows)

    sessions_30d = np.clip(rng.poisson(np.exp(1.15 + 0.43 * recent_interest)), 0, 45)
    weekly_fraction = np.clip(0.16 + 0.12 * recent_interest + rng.normal(0, 0.08, rows), 0, 0.7)
    sessions_7d = np.minimum(sessions_30d, rng.binomial(sessions_30d, weekly_fraction))
    weekly_active_days = np.minimum(
        sessions_7d,
        np.minimum(7, rng.binomial(7, sigmoid(-1.5 + recent_interest))),
    )
    pulse_30d = np.minimum(sessions_30d, rng.binomial(sessions_30d, sigmoid(-0.15 + 0.45 * affinity)))
    pulse_7d = np.minimum(
        pulse_30d,
        np.minimum(sessions_7d, rng.binomial(sessions_7d, sigmoid(-0.05 + 0.4 * affinity))),
    )
    recency_mean = np.clip(11 - 3.4 * recent_interest + 2.0 * friction, 0.8, 35)
    raw_recency = np.clip(rng.exponential(recency_mean), 0, 75).astype(int)
    # Session windows and recency describe the same event history. Enforce the
    # exact bidirectional contract used by analytics and production ingestion:
    # <7 days iff the 7-day count is positive; <30 iff the 30-day count is.
    days_since_session = np.where(
        sessions_7d > 0,
        np.minimum(raw_recency, 6),
        np.where(
            sessions_30d > 0,
            np.clip(raw_recency, 7, 29),
            np.maximum(raw_recency, 30),
        ),
    )
    avg_minutes = np.clip(rng.normal(5.5 + 1.15 * affinity, 2.2, rows), 1, 25)
    diversity = np.clip(np.rint(rng.normal(2.2 + 0.45 * affinity, 1.05, rows)), 0, 7).astype(int)
    diversity = np.where(sessions_30d > 0, diversity, 0)

    consult_probability = sigmoid(-2.0 + 0.42 * affinity + 0.17 * sessions_30d)
    consultations_90d = np.clip(rng.poisson(consult_probability * 1.25), 0, 5)
    had_consult = consultations_90d > 0
    days_since_consult = np.where(had_consult, rng.integers(1, 91, rows), 180)
    brief_lambda = np.clip(0.12 + 0.08 * sessions_7d + 0.2 * (affinity > 0), 0.02, 2.8)
    briefs = np.clip(rng.poisson(brief_lambda), 0, 5)
    briefs = np.where(pulse_30d > 0, briefs, 0)
    referral_probability = sigmoid(-2.5 + 0.55 * affinity + 0.12 * pulse_30d)
    referrals_90d = np.clip(rng.binomial(3, referral_probability), 0, 3)
    helpful_rate = np.clip(rng.beta(4.5 + np.maximum(affinity, 0), 2.2, rows), 0, 1)

    # Future targets depend only on features available at the prediction cutoff.
    churn_logit = (
        -0.9
        + 0.085 * days_since_session
        - 0.13 * sessions_7d
        - 0.045 * pulse_30d
        - 0.14 * weekly_active_days
        + 0.4 * friction
        + rng.normal(0, 0.42, rows)
    )
    future_churn = rng.binomial(1, sigmoid(churn_logit))
    intent_logit = (
        -2.0
        + 0.23 * sessions_7d
        + 0.36 * briefs
        + 0.25 * diversity
        + 0.3 * had_consult
        - 0.004 * days_since_consult
        + 0.2 * helpful_rate
        + rng.normal(0, 0.38, rows)
    )
    future_consult = rng.binomial(1, sigmoid(intent_logit))

    retained_d1 = rng.binomial(1, sigmoid(-0.1 + 0.38 * recent_interest))
    retained_d7 = retained_d1 * rng.binomial(1, sigmoid(-0.38 + 0.36 * recent_interest))
    retained_d30 = retained_d7 * rng.binomial(1, sigmoid(-0.6 + 0.28 * recent_interest))

    signup_completed = np.ones(rows, dtype=int)
    onboarding = np.maximum(
        rng.binomial(1, sigmoid(1.7 + 0.2 * affinity)),
        (pulse_30d > 0).astype(int),
    )
    pulse_completed = (pulse_30d > 0).astype(int)
    brief_created = (briefs > 0).astype(int)
    booked = brief_created * rng.binomial(1, sigmoid(-0.15 + 0.32 * briefs))
    repeat_consult = (consultations_90d >= 2).astype(int)

    invites_created = referrals_90d
    invites_opened = np.array([rng.binomial(value, 0.64) for value in invites_created])
    invites_completed = np.array([rng.binomial(value, 0.46) for value in invites_opened])

    focus = rng.choice(
        ["career", "relationship", "finance", "education", "family", "personal_growth"],
        size=rows,
        p=[0.26, 0.23, 0.17, 0.11, 0.10, 0.13],
    )
    frame = pd.DataFrame(
        {
            "user_id": user_ids,
            "data_provenance": "synthetic_demo",
            "as_of_date": pd.to_datetime(as_of).strftime("%Y-%m-%d"),
            "signup_date": pd.to_datetime(signup).strftime("%Y-%m-%d"),
            "focus_area": focus,
            "account_age_days": account_age,
            "days_since_last_session": days_since_session,
            "sessions_7d": sessions_7d,
            "sessions_30d": sessions_30d,
            "pulse_checkins_7d": pulse_7d,
            "pulse_checkins_30d": pulse_30d,
            "weekly_active_days": weekly_active_days,
            "avg_session_minutes": np.round(avg_minutes, 2),
            "content_diversity_30d": diversity,
            "consultations_90d": consultations_90d,
            "days_since_last_consultation": days_since_consult,
            "briefs_started_30d": briefs,
            "referrals_created_90d": referrals_90d,
            "feedback_helpful_rate": np.round(helpful_rate, 4),
            "signup_completed": signup_completed,
            "onboarding_completed": onboarding,
            "pulse_completed": pulse_completed,
            "brief_created": brief_created,
            "consultation_booked": booked,
            "repeat_consultation_90d": repeat_consult,
            "invites_created": invites_created,
            "invites_opened": invites_opened,
            "invites_completed": invites_completed,
            "retained_d1": retained_d1,
            "retained_d7": retained_d7,
            "retained_d30": retained_d30,
            "future_30d_churn": future_churn,
            "future_14d_consultation": future_consult,
        }
    )
    return frame.sort_values(["as_of_date", "user_id"]).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=ROWS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    frame = generate(args.rows, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    print(f"Wrote {len(frame):,} synthetic rows to {args.output}")
    print("This file contains fictional demonstration observations only.")


if __name__ == "__main__":
    main()
