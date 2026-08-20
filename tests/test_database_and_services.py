"""Database schema and core service boundary tests."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from app import create_app
from app.db import get_db
from app.services.experiments import simulate
from app.services.journey import sun_sign


def test_database_initialises_all_required_tables(app):
    expected = {
        "demo_users", "consents", "checkins", "consultation_briefs",
        "demo_bookings", "followups", "referrals", "referral_events",
        "journey_events", "feedback", "experiment_runs",
    }
    with app.app_context():
        actual = {row["name"] for row in get_db().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()}
        experiment_columns = {
            row["name"]
            for row in get_db().execute("PRAGMA table_info(experiment_runs)").fetchall()
        }
        followup_action_columns = {
            row["name"]
            for row in get_db().execute("PRAGMA table_info(followup_actions)").fetchall()
        }
    assert expected <= actual
    assert "owner_key" in experiment_columns
    assert "active" in followup_action_columns


def test_database_migrates_legacy_experiment_runs_without_data_loss():
    database = Path("instance/tests") / f"legacy-{uuid4().hex}.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE experiment_runs (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               user_id INTEGER,
               inputs_json TEXT NOT NULL,
               results_json TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    connection.execute(
        "INSERT INTO experiment_runs (inputs_json, results_json) VALUES ('{}', '{}')"
    )
    connection.commit()
    connection.close()
    try:
        application = create_app({
            "TESTING": True,
            "SECRET_KEY": "migration-test-secret",
            "SECRET_KEY_IS_FALLBACK": False,
            "DATABASE": str(database.resolve()),
        })
        with application.app_context():
            columns = {
                row["name"]
                for row in get_db().execute("PRAGMA table_info(experiment_runs)").fetchall()
            }
            row = get_db().execute(
                "SELECT inputs_json, results_json, owner_key FROM experiment_runs WHERE id = 1"
            ).fetchone()
        assert "owner_key" in columns
        assert row["inputs_json"] == "{}"
        assert row["results_json"] == "{}"
        assert row["owner_key"] is None
    finally:
        database.unlink(missing_ok=True)


@pytest.mark.parametrize(("birth_date", "expected"), [
    ("1990-01-19", "Capricorn"),
    ("1990-01-20", "Aquarius"),
    ("1990-03-21", "Aries"),
    ("1990-12-22", "Capricorn"),
])
def test_sun_sign_uses_documented_date_boundaries(birth_date, expected):
    assert sun_sign(birth_date) == expected


def test_simulator_is_reproducible_and_bounded(app):
    assumptions = {
        "eligible_users": 5000,
        "pulse_adoption": 0.2,
        "baseline_retention": 0.25,
        "retention_uplift": 0.08,
        "share_rate": 0.06,
        "invites_per_sharer": 1.3,
        "invite_conversion": 0.16,
        "baseline_consultation_conversion": 0.05,
        "consultation_conversion": 0.065,
        "repeat_consultation_uplift": 0.06,
        "trials": 10000,
        "seed": 11,
    }
    with app.app_context():
        first = simulate(assumptions, persist=False)
        second = simulate(assumptions, persist=False)
    assert first == second
    assert first["label"].startswith("Scenario estimate")
    assert first["inputs"]["trials"] >= 10000
    assert first["metrics"]["incremental_organic_users"]["p05"] >= 0
    assert first["revenue_supported"] is False
    assert len(first["sensitivity"]) >= 7


def test_simulator_revenue_only_when_input_supports_it(app):
    with app.app_context():
        without_revenue = simulate({}, persist=False)
        with_revenue = simulate({"average_consultation_revenue": 400}, persist=False)
    assert "incremental_revenue" not in without_revenue["metrics"]
    assert "incremental_revenue" in with_revenue["metrics"]
