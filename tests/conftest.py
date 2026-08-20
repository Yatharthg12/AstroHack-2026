"""Shared pytest fixtures for isolated Orbit application tests."""

from __future__ import annotations

import pytest
from pathlib import Path
from uuid import uuid4

from app import create_app


@pytest.fixture()
def app():
    database = Path("instance") / "tests" / f"orbit-{uuid4().hex}.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-not-for-production",
        "SECRET_KEY_IS_FALLBACK": False,
        "DATABASE": str(database.resolve()),
        "SERVER_NAME": "localhost",
        "RATE_LIMIT_PER_MINUTE": 1000,
        "EXPERIMENT_RATE_LIMIT_PER_MINUTE": 1000,
    })
    yield application
    database.unlink(missing_ok=True)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def csrf_headers(client):
    with client.session_transaction() as state:
        state["csrf_token"] = "unit-test-csrf-token"
    return {"X-CSRF-Token": "unit-test-csrf-token"}


@pytest.fixture()
def onboarded_client(client):
    with client.session_transaction() as state:
        state["csrf_token"] = "unit-test-csrf-token"
    response = client.post("/onboarding", data={
        "csrf_token": "unit-test-csrf-token",
        "display_name": "Aarav",
        "birth_date": "1994-08-17",
        "birth_time": "08:45",
        "birth_city": "Jaipur",
        "focus_area": "career",
        "communication_preference": "concise",
        "save_consent": "yes",
        "circle_consent": "yes",
    })
    assert response.status_code == 302
    with client.session_transaction() as state:
        state["csrf_token"] = "unit-test-csrf-token"
    return client
