from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.ml.features import FEATURES, feature_frame, validate_feature_contract
from app.ml.inference import load_predictor, predict_user
from scripts.generate_demo_data import generate
from scripts.train_models import chronological_split, train_all
from app.analytics import validate_demo_data


def test_synthetic_generation_is_reproducible_and_labelled():
    first = generate(rows=200, seed=2026)
    second = generate(rows=200, seed=2026)
    pd.testing.assert_frame_equal(first, second)
    assert first["data_provenance"].eq("synthetic_demo").all()
    assert first["user_id"].is_unique
    assert not first.isna().any().any()
    assert set(first["future_30d_churn"].unique()) <= {0, 1}
    assert set(first["future_14d_consultation"].unique()) <= {0, 1}
    assert (first["weekly_active_days"] <= first["sessions_7d"]).all()
    assert (first["weekly_active_days"] <= 7).all()
    assert (first["days_since_last_session"] < 7).eq(first["sessions_7d"] > 0).all()
    assert (first["days_since_last_session"] < 30).eq(first["sessions_30d"] > 0).all()
    assert first["pulse_completed"].eq(first["pulse_checkins_30d"] > 0).all()
    assert first["brief_created"].eq(first["briefs_started_30d"] > 0).all()
    inactive = first["sessions_30d"] == 0
    assert first.loc[inactive, "content_diversity_30d"].eq(0).all()
    assert first.loc[inactive, "pulse_checkins_30d"].eq(0).all()
    assert first.loc[inactive, "briefs_started_30d"].eq(0).all()


def test_feature_contract_rejects_known_outcomes():
    with pytest.raises(ValueError, match="leakage"):
        validate_feature_contract([*FEATURES, "future_30d_churn"])


def test_dataset_validation_rejects_funnel_and_provenance_errors():
    frame = generate(rows=120, seed=2026)
    validate_demo_data(frame)
    frame.loc[0, "pulse_completed"] = 1
    frame.loc[0, "onboarding_completed"] = 0
    with pytest.raises(ValueError, match="funnel"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    frame.loc[0, "data_provenance"] = "production"
    with pytest.raises(ValueError, match="provenance"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    frame.loc[0, "sessions_7d"] = -1
    with pytest.raises(ValueError, match="negative"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    frame.loc[0, "weekly_active_days"] = frame.loc[0, "sessions_7d"] + 1
    with pytest.raises(ValueError, match="weekly_active_days"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    frame.loc[0, "sessions_7d"] = 0
    frame.loc[0, "pulse_checkins_7d"] = 0
    frame.loc[0, "weekly_active_days"] = 0
    frame.loc[0, "days_since_last_session"] = 2
    with pytest.raises(ValueError, match="7-day session"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    frame.loc[0, "sessions_30d"] = 0
    frame.loc[0, "sessions_7d"] = 0
    frame.loc[0, "pulse_checkins_30d"] = 0
    frame.loc[0, "pulse_checkins_7d"] = 0
    frame.loc[0, "weekly_active_days"] = 0
    frame.loc[0, "days_since_last_session"] = 20
    with pytest.raises(ValueError, match="30-day session"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    pulse_row = frame.index[frame["pulse_checkins_30d"] > 0][0]
    frame.loc[pulse_row, "pulse_completed"] = 0
    frame.loc[pulse_row, "brief_created"] = 0
    frame.loc[pulse_row, "consultation_booked"] = 0
    with pytest.raises(ValueError, match="Pulse activation"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    brief_row = frame.index[frame["briefs_started_30d"] > 0][0]
    frame.loc[brief_row, "brief_created"] = 0
    frame.loc[brief_row, "consultation_booked"] = 0
    with pytest.raises(ValueError, match="Brief activation"):
        validate_demo_data(frame)
    frame = generate(rows=120, seed=2026)
    inactive_row = frame.index[frame["sessions_30d"] == 0][0]
    frame.loc[inactive_row, "content_diversity_30d"] = 1
    with pytest.raises(ValueError, match="30-day activity"):
        validate_demo_data(frame)


def test_training_rejects_invalid_dataset_contract_before_fitting(monkeypatch):
    frame = generate(rows=120, seed=2026)
    frame.loc[0, "data_provenance"] = "unverified_source"
    monkeypatch.setattr(pd, "read_csv", lambda _path: frame)
    with pytest.raises(ValueError, match="provenance"):
        train_all(Path("unused-invalid.csv"), Path("unused-model-output"))


def test_feature_frame_order_defaults_and_non_finite_guard():
    frame = feature_frame({"sessions_7d": 4})
    assert list(frame.columns) == FEATURES
    assert frame.iloc[0]["sessions_7d"] == 4
    with pytest.raises(ValueError, match="finite"):
        feature_frame({"sessions_7d": float("inf")})


def test_chronological_split_is_strict_and_complete():
    data = generate(rows=300, seed=2026)
    train, validation, test = chronological_split(data)
    assert len(train) + len(validation) + len(test) == len(data)
    assert train["as_of_date"].max() < validation["as_of_date"].min()
    assert validation["as_of_date"].max() < test["as_of_date"].min()
    assert set(train["user_id"]).isdisjoint(validation["user_id"])
    assert set(validation["user_id"]).isdisjoint(test["user_id"])


def test_json_model_round_trip_and_missing_fallback():
    result = predict_user("churn_risk", {"days_since_last_session": 30, "sessions_7d": 0})
    assert result.model_available
    assert 0 <= result.probability <= 1
    missing = predict_user("churn_risk", {}, model_dir=Path("does-not-exist"))
    assert missing.as_dict() == {
        "probability": 0.0,
        "label": False,
        "threshold": 1.0,
        "model_available": False,
        "model_version": "unavailable",
        "reason": "Model artifact unavailable; no automated risk/action assigned.",
    }


def test_integrity_check_rejects_tampered_artifact():
    source = load_predictor("consultation_intent")
    assert source is not None
    artifact_dir = Path(__file__).parent / "fixtures" / "tampered_models"
    assert load_predictor("consultation_intent", artifact_dir) is None
