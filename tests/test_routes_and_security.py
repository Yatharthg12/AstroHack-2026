"""Page/API routing, validation, headers, and production-safety tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from threading import Barrier

import pytest

import app.services.experiments as experiment_service
from app.db import get_db


PUBLIC_PAGES = ["/", "/onboarding", "/growth", "/experiments", "/privacy"]
AUTHENTICATED_PAGES = ["/pulse", "/bridge", "/booking", "/console", "/follow-up", "/circle", "/journey"]


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_public_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert b"AstroLive" in response.data
    assert response.headers["Cache-Control"] == "private, no-store"


def test_simulator_html_bounds_and_defaults_match_service_contract(client):
    response = client.get("/experiments")
    assert response.status_code == 200
    expected = {
        "eligible_users": ("10000", "100", "10000000", "100"),
        "invites_per_sharer": ("1.4", "0", "20", "0.1"),
        "consultation_conversion": ("0.072", "0", "1", "0.001"),
        "average_consultation_revenue": ("0.0", "0", "1000000", "10"),
        "trials": ("10000", "10000", "100000", "1000"),
    }
    for field, (value, minimum, maximum, step) in expected.items():
        match = re.search(fr'<input id="{field}"[^>]+>'.encode(), response.data)
        assert match, field
        markup = match.group(0)
        assert f'value="{value}"'.encode() in markup
        assert f'min="{minimum}"'.encode() in markup
        assert f'max="{maximum}"'.encode() in markup
        assert f'step="{step}"'.encode() in markup


@pytest.mark.parametrize("path", AUTHENTICATED_PAGES)
def test_primary_pages_render_for_demo_user(onboarded_client, path):
    response = onboarded_client.get(path)
    assert response.status_code == 200
    assert b"AstroLive" in response.data
    assert response.headers["Cache-Control"] == "private, no-store"


def test_astrologer_cards_expose_keyboard_focus_ring(onboarded_client):
    checkin = onboarded_client.post(
        "/api/check-ins",
        json={
            "mood": "grounded",
            "confidence": 4,
            "concern": "I want a clearer next step before a conversation.",
            "save": True,
        },
        headers={"X-CSRF-Token": "unit-test-csrf-token"},
    )
    assert checkin.status_code == 201
    draft = onboarded_client.post(
        "/api/briefs",
        json={
            "topic": "Career direction",
            "context": "I am comparing two paths and want a structured conversation.",
            "outcome": "Leave with clearer questions and a calm next step.",
            "questions": ["What trade-offs should I reflect on?"],
            "language": "English",
            "mode": "audio",
            "urgency": "soon",
            "include_checkins": False,
        },
        headers={"X-CSRF-Token": "unit-test-csrf-token"},
    )
    brief_id = draft.get_json()["data"]["id"]
    approved = onboarded_client.post(
        f"/api/briefs/{brief_id}/approve",
        json={"approved": True},
        headers={"X-CSRF-Token": "unit-test-csrf-token"},
    )
    assert approved.status_code == 200

    booking = onboarded_client.get("/booking")
    stylesheet = Path("app/static/css/orbit.css").read_text(encoding="utf-8")
    assert booking.status_code == 200
    assert b'class="astrologer-focus-ring" aria-hidden="true"' in booking.data
    assert ".astrologer input:focus-visible+.astrologer-focus-ring" in stylesheet


def test_chart_values_have_text_equivalents_and_reset_dialog_has_name(
    client, onboarded_client
):
    growth = client.get("/growth")
    assert b'id="lifecycle-chart-summary"' in growth.data
    assert b'aria-describedby="lifecycle-chart-summary"' in growth.data
    assert b"Lifecycle chart values:" in growth.data
    for task in (b"churn_risk", b"consultation_intent"):
        summary_id = task + b"-distribution-summary"
        assert b'id="' + summary_id + b'"' in growth.data
        assert b'aria-describedby="' + summary_id + b'"' in growth.data

    experiments = client.get("/experiments")
    assert b'id="scenario-chart-summary"' in experiments.data
    assert b'aria-describedby="scenario-chart-summary"' in experiments.data
    assert b"Median scenario values:" in experiments.data
    script = Path("app/static/js/orbit.js").read_text(encoding="utf-8")
    assert "summary.textContent=`Median scenario values:" in script

    journey = onboarded_client.get("/journey")
    assert b'aria-labelledby="reset-dialog-title"' in journey.data
    assert b'id="reset-dialog-title"' in journey.data


def test_rendered_error_with_session_state_is_private_no_store(client):
    response = client.get("/a-page-that-does-not-exist")
    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "private, no-store"


def test_health_endpoint_and_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"]["status"] == "healthy"
    assert payload["data"]["model_integrity"] == "ok"
    assert set(payload["data"]["models_available"]) == {
        "churn_risk", "consultation_intent",
    }
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_health_degrades_when_model_integrity_fails(app):
    app.config["MODEL_DIR"] = str(Path("tests/fixtures/tampered_models").resolve())
    response = app.test_client().get("/api/health")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["database"] == "ok"
    assert data["status"] == "degraded"
    assert data["model_integrity"] == "degraded"
    assert data["models"]["consultation_intent"]["available"] is False


def test_api_rejects_missing_csrf(onboarded_client):
    response = onboarded_client.post("/api/check-ins", json={
        "mood": "calm", "confidence": 3, "concern": "A valid but untrusted request"
    })
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "csrf_failed"


def test_onboarding_html_post_requires_hidden_session_csrf(client, app):
    page = client.get("/onboarding")
    assert page.status_code == 200
    assert page.headers["Cache-Control"] == "private, no-store"
    with client.session_transaction() as state:
        token = state["csrf_token"]
    assert b'name="csrf_token"' in page.data
    assert f'value="{token}"'.encode() in page.data

    form = {
        "display_name": "Riya",
        "birth_date": "1996-02-10",
        "focus_area": "education",
        "communication_preference": "supportive",
        "save_consent": "yes",
    }
    rejected = app.test_client().post("/onboarding", data=form)
    assert rejected.status_code == 403
    assert b"Refresh the page and try again" in rejected.data

    accepted = client.post("/onboarding", data={**form, "csrf_token": token})
    assert accepted.status_code == 302
    assert accepted.headers["Location"].endswith("/pulse")


def test_onboarding_rejects_invalid_optional_birth_time(client):
    page = client.get("/onboarding")
    assert page.status_code == 200
    with client.session_transaction() as state:
        token = state["csrf_token"]
    response = client.post(
        "/onboarding",
        data={
            "csrf_token": token,
            "display_name": "Riya",
            "birth_date": "1996-02-10",
            "birth_time": "not-a-time",
            "focus_area": "education",
            "communication_preference": "supportive",
            "save_consent": "yes",
        },
    )
    assert response.status_code == 400
    assert b"valid 24-hour time" in response.data


def test_api_protocol_errors_use_json_envelope(client, csrf_headers):
    wrong_method = client.get("/api/reset")
    assert wrong_method.status_code == 405
    assert wrong_method.get_json() == {
        "ok": False,
        "error": {"code": "method_not_allowed", "message": "Method not allowed."},
    }

    oversized = client.post(
        "/api/check-ins",
        data=b'{"concern":"' + (b"x" * 70_000) + b'"}',
        content_type="application/json",
        headers=csrf_headers,
    )
    assert oversized.status_code == 413
    assert oversized.get_json() == {
        "ok": False,
        "error": {"code": "request_too_large", "message": "Request body is too large."},
    }


def test_api_validation_is_consistent(onboarded_client, csrf_headers):
    response = onboarded_client.post("/api/check-ins", json={
        "mood": "impossible", "confidence": 99, "concern": "x"
    }, headers=csrf_headers)
    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["field"]


def test_analytics_and_experiment_apis(client, csrf_headers):
    analytics = client.get("/api/analytics?period=90d&segment=all&focus=all")
    assert analytics.status_code == 200
    assert "provenance" in analytics.get_json()["data"]
    experiment = client.post("/api/experiments", json={"trials": 10000, "seed": 2026}, headers=csrf_headers)
    assert experiment.status_code == 201
    result = experiment.get_json()["data"]
    assert result["run_id"]
    json_export = client.get(f"/api/experiments/{result['run_id']}.json")
    csv_export = client.get(f"/api/experiments/{result['run_id']}.csv")
    assert json_export.status_code == 200
    assert csv_export.status_code == 200
    assert json_export.headers["Cache-Control"] == "private, no-store"
    assert csv_export.headers["Cache-Control"] == "private, no-store"
    assert b"assumption" in csv_export.data
    assert b"result" in csv_export.data
    assert b"sensitivity" in csv_export.data


def test_experiment_exports_are_scoped_to_creating_session(app):
    owner = app.test_client()
    other = app.test_client()
    for browser, token in ((owner, "owner-csrf"), (other, "other-csrf")):
        with browser.session_transaction() as state:
            state["csrf_token"] = token

    with app.app_context():
        get_db().execute(
            """INSERT INTO experiment_runs
               (owner_key, inputs_json, results_json, created_at)
               VALUES ('stale-owner', '{}', '{}', datetime('now', '-25 hours'))"""
        )
        get_db().commit()

    owner_run = owner.post(
        "/api/experiments",
        json={"trials": 10000, "seed": 1},
        headers={"X-CSRF-Token": "owner-csrf"},
    ).get_json()["data"]["run_id"]
    other_run = other.post(
        "/api/experiments",
        json={"trials": 10000, "seed": 2},
        headers={"X-CSRF-Token": "other-csrf"},
    ).get_json()["data"]["run_id"]
    assert other_run > owner_run
    assert owner.get(f"/api/experiments/{owner_run}.json").status_code == 200
    assert other.get(f"/api/experiments/{other_run}.csv").status_code == 200

    cross_session = other.get(f"/api/experiments/{owner_run}.json")
    assert cross_session.status_code == 404
    assert cross_session.get_json()["error"]["code"] == "not_found"
    assert owner.get(f"/api/experiments/{other_run}.json").status_code == 404
    with owner.session_transaction() as state:
        owner_key = state["experiment_owner_key"]
        assert "experiment_run_ids" not in state
    with other.session_transaction() as state:
        other_key = state["experiment_owner_key"]
    assert owner_key != other_key
    with app.app_context():
        rows = get_db().execute(
            "SELECT id, owner_key FROM experiment_runs ORDER BY id"
        ).fetchall()
    assert {row["owner_key"] for row in rows} == {owner_key, other_key}


def test_experiment_owner_nonce_is_seeded_before_concurrent_posts(app):
    browser = app.test_client()
    assert browser.get("/experiments").status_code == 200
    with browser.session_transaction() as state:
        owner_key = state["experiment_owner_key"]
        csrf_token = state["csrf_token"]
    assert browser.get("/experiments").status_code == 200
    with browser.session_transaction() as state:
        assert state["experiment_owner_key"] == owner_key

    cookie = browser.get_cookie(app.config["SESSION_COOKIE_NAME"])
    clients = [app.test_client(), app.test_client()]
    for client in clients:
        client.set_cookie(app.config["SESSION_COOKIE_NAME"], cookie.value)
    barrier = Barrier(2)

    def create_run(index):
        barrier.wait()
        return clients[index].post(
            "/api/experiments",
            json={"trials": 10000, "seed": 100 + index},
            headers={"X-CSRF-Token": csrf_token},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create_run, range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    run_ids = [response.get_json()["data"]["run_id"] for response in responses]
    with app.app_context():
        stored_keys = {
            row["owner_key"]
            for row in get_db().execute(
                "SELECT owner_key FROM experiment_runs WHERE id IN (?, ?)", tuple(run_ids)
            ).fetchall()
        }
    assert stored_keys == {owner_key}
    assert all(
        browser.get(f"/api/experiments/{run_id}.json").status_code == 200
        for run_id in run_ids
    )


def test_experiment_abuse_limits_and_trial_cap(app):
    browser = app.test_client()
    with browser.session_transaction() as state:
        state["csrf_token"] = "simulator-limit-csrf"
    headers = {"X-CSRF-Token": "simulator-limit-csrf"}
    too_many_trials = browser.post(
        "/api/experiments",
        json={"trials": 100001},
        headers=headers,
        environ_overrides={"REMOTE_ADDR": "203.0.113.41"},
    )
    assert too_many_trials.status_code == 400
    assert too_many_trials.get_json()["error"]["field"] == "trials"

    app.config["EXPERIMENT_RATE_LIMIT_PER_MINUTE"] = 1
    first = browser.post(
        "/api/experiments",
        json={"trials": 10000, "seed": 41},
        headers=headers,
        environ_overrides={"REMOTE_ADDR": "203.0.113.42"},
    )
    second = browser.post(
        "/api/experiments",
        json={"trials": 10000, "seed": 42},
        headers=headers,
        environ_overrides={"REMOTE_ADDR": "203.0.113.42"},
    )
    assert first.status_code == 201
    assert second.status_code == 429


def test_experiment_concurrency_cap_returns_busy_429(app, monkeypatch):
    browser = app.test_client()
    with browser.session_transaction() as state:
        state["csrf_token"] = "simulator-busy-csrf"
    app.config["EXPERIMENT_MAX_CONCURRENCY"] = 1
    monkeypatch.setattr(experiment_service, "_active_experiments", 1)
    response = browser.post(
        "/api/experiments",
        json={"trials": 10000},
        headers={"X-CSRF-Token": "simulator-busy-csrf"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.43"},
    )
    assert response.status_code == 429
    assert "busy" in response.get_json()["error"]["message"].lower()


def test_reset_deletes_anonymous_and_user_runs_for_session(app):
    browser = app.test_client()
    browser.get("/experiments")
    with browser.session_transaction() as state:
        csrf_token = state["csrf_token"]
        owner_key = state["experiment_owner_key"]
    headers = {"X-CSRF-Token": csrf_token}
    anonymous = browser.post(
        "/api/experiments", json={"trials": 10000, "seed": 71}, headers=headers
    )
    assert anonymous.status_code == 201
    onboarding = browser.post("/onboarding", data={
        "csrf_token": csrf_token,
        "display_name": "Experiment Owner",
        "birth_date": "1992-05-06",
        "focus_area": "career",
        "communication_preference": "concise",
        "save_consent": "yes",
    })
    assert onboarding.status_code == 302
    with browser.session_transaction() as state:
        assert state["experiment_owner_key"] == owner_key
        state["csrf_token"] = "post-onboarding-csrf"
    headers = {"X-CSRF-Token": "post-onboarding-csrf"}
    user_run = browser.post(
        "/api/experiments", json={"trials": 10000, "seed": 72}, headers=headers
    )
    assert user_run.status_code == 201
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) AS count FROM experiment_runs WHERE owner_key = ?",
            (owner_key,),
        ).fetchone()["count"] == 2

    reset = browser.post("/api/reset", json={"confirm": True}, headers=headers)
    assert reset.status_code == 200
    with app.app_context():
        assert get_db().execute(
            "SELECT COUNT(*) AS count FROM experiment_runs WHERE owner_key = ?",
            (owner_key,),
        ).fetchone()["count"] == 0


def test_docker_runtime_can_write_only_instance_directory():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "chown -R orbit:orbit /app/instance" in dockerfile
    assert "chown -R orbit:orbit /app\n" not in dockerfile


def test_reset_requires_explicit_confirmation(onboarded_client, app, csrf_headers):
    rejected = onboarded_client.post("/api/reset", json={}, headers=csrf_headers)
    assert rejected.status_code == 400
    assert rejected.get_json()["error"]["field"] == "confirm"
    assert onboarded_client.get("/pulse").status_code == 200

    confirmed = onboarded_client.post(
        "/api/reset", json={"confirm": True}, headers=csrf_headers
    )
    assert confirmed.status_code == 200
    assert onboarded_client.get("/pulse").status_code == 302


def test_growth_page_degrades_when_dataset_is_missing(app):
    app.config["DEMO_DATA_PATH"] = str(
        __import__("pathlib").Path("instance/tests/definitely-absent.csv").resolve()
    )
    response = app.test_client().get("/growth")
    assert response.status_code == 200
    assert b"Analytics are unavailable" in response.data


@pytest.mark.parametrize(
    "query",
    [
        "period=&segment=&focus=",
        "period=not-a-window&segment=does-not-exist&focus=does-not-exist",
    ],
)
def test_growth_page_renders_for_empty_or_arbitrary_filters(client, query):
    response = client.get(f"/growth?{query}")
    assert response.status_code == 200
    assert b"No anonymised users match these filters" in response.data


def test_input_length_limit_returns_safe_client_error(client, csrf_headers):
    response = client.post("/onboarding", data={
        "display_name": "x" * 61,
        "birth_date": "1990-01-01",
        "focus_area": "career",
        "communication_preference": "concise",
        "save_consent": "yes",
    }, headers=csrf_headers)
    assert response.status_code == 400
    assert b"Traceback" not in response.data


def test_followup_requires_approval_and_nonpast_date(onboarded_client, csrf_headers):
    draft = onboarded_client.post("/api/briefs", json={
        "topic": "Career direction", "context": "Enough context for validation.",
        "outcome": "A calm decision framework.", "questions": ["What should I compare?"],
        "language": "English", "mode": "audio", "urgency": "soon",
        "include_checkins": False,
    }, headers=csrf_headers).get_json()["data"]
    onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve",
        json={"approved": True},
        headers=csrf_headers,
    )
    booking = onboarded_client.post("/api/bookings", json={
        "brief_id": draft["id"], "astrologer_id": "asha", "mode": "audio",
        "slot": "2099-01-01T10:00:00+05:30",
    }, headers=csrf_headers)
    assert booking.status_code == 201
    payload = {
        "booking_id": booking.get_json()["data"]["id"],
        "summary": "A reviewed summary.", "actions": ["One action"],
        "checkin_date": "2020-01-01", "helpfulness": 3,
    }
    missing_approval = onboarded_client.post("/api/follow-up", json=payload, headers=csrf_headers)
    assert missing_approval.status_code == 400
    payload["approved"] = True
    past = onboarded_client.post("/api/follow-up", json=payload, headers=csrf_headers)
    assert past.status_code == 400


def test_unknown_routes_use_safe_error_pages(client):
    page = client.get("/this-does-not-exist")
    api = client.get("/api/this-does-not-exist")
    assert page.status_code == 404
    assert b"Traceback" not in page.data
    assert api.status_code == 404
    assert api.get_json()["error"]["code"] == "not_found"
