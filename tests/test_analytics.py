from __future__ import annotations

from pathlib import Path

import pytest

from app.analytics import (
    activation_funnel,
    anonymized_drilldown,
    assign_segments,
    cohort_retention,
    k_factor,
    snapshot,
)
from scripts.generate_demo_data import generate


@pytest.fixture()
def synthetic():
    return generate(rows=300, seed=2026)


def test_activation_funnel_is_monotonic(synthetic):
    funnel = activation_funnel(synthetic)
    counts = [step["count"] for step in funnel]
    assert counts == sorted(counts, reverse=True)
    assert all(0 <= step["step_conversion"] <= 1 for step in funnel)


def test_cohort_retention_and_k_factor_ranges(synthetic):
    cohorts = cohort_retention(synthetic)
    assert cohorts
    assert all(0 <= row["d30"] <= row["d7"] <= row["d1"] <= 1 for row in cohorts)
    viral = k_factor(synthetic)
    assert 0 <= viral["invite_open_rate"] <= 1
    assert 0 <= viral["invite_completion_rate"] <= 1
    assert viral["k_factor"] == round(
        viral["invites_per_user"] * viral["invite_completion_rate"], 4
    )


def test_segments_are_complete_and_descriptive(synthetic):
    segments = assign_segments(synthetic)
    assert not segments.isna().any()
    assert set(segments) <= {
        "At-risk",
        "Guidance seeker",
        "Circle advocate",
        "Pulse regular",
        "Explorer",
    }


def test_snapshot_filters_and_anonymizes_users():
    result = snapshot(period="30d", focus="career")
    assert result["available"] is True
    assert result["summary"]["users"] > 0
    assert result["models"]["available"] is True
    assert all(user["anonymous_id"].startswith("U-") for user in result["users"])
    assert all("user_id" not in user for user in result["users"])
    assert all(user["focus_area"] == "career" for user in result["users"])


def test_snapshot_and_models_degrade_without_files():
    missing = Path(__file__).parent / "fixtures" / "missing"
    result = snapshot(data_path=missing / "data.csv", model_dir=missing / "models")
    assert result["available"] is False
    assert result["models"]["available"] is False


def test_invalid_filter_and_drilldown_limit(synthetic):
    with pytest.raises(ValueError, match="period"):
        snapshot(period="century")
    with pytest.raises(ValueError, match="limit"):
        anonymized_drilldown(synthetic, limit=101)
