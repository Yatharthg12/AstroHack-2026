"""Regression coverage for frozen consultation context and Journey continuity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from threading import Barrier

from app.db import get_db


HEADERS = {"X-CSRF-Token": "unit-test-csrf-token"}


def _create_brief(client, *, checkin_ids: list[int] | None = None) -> dict:
    response = client.post("/api/briefs", json={
        "topic": "career",
        "context": "I am comparing two paths and want a structured conversation.",
        "outcome": "Leave with clearer questions and a calm next step.",
        "questions": ["Which trade-offs deserve attention?"],
        "language": "English",
        "mode": "audio",
        "urgency": "soon",
        "include_checkins": checkin_ids is not None,
        "checkin_ids": checkin_ids or [],
    }, headers=HEADERS)
    assert response.status_code == 201
    return response.get_json()["data"]


def _create_booking(client, brief_id: int) -> dict:
    response = client.post("/api/bookings", json={
        "brief_id": brief_id,
        "astrologer_id": "asha",
        "mode": "audio",
        "slot": (datetime.now() + timedelta(days=2)).replace(microsecond=0).isoformat(),
    }, headers=HEADERS)
    assert response.status_code == 201
    return response.get_json()["data"]


def test_brief_approves_exact_draft_snapshot_not_later_pulse(onboarded_client, app):
    first = onboarded_client.post("/api/check-ins", json={
        "mood": "grounded", "confidence": 4,
        "concern": "Reviewed context that may be shared.", "save": True,
    }, headers=HEADERS).get_json()["data"]
    review = onboarded_client.get("/bridge")
    assert b"Reviewed context that may be shared" in review.data
    assert f'name="checkin_ids" value="{first["id"]}"'.encode() in review.data

    draft = _create_brief(onboarded_client, checkin_ids=[first["id"]])
    assert [item["checkin_id"] for item in draft["shared_checkins"]] == [first["id"]]
    missing_consent = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={}, headers=HEADERS
    )
    assert missing_consent.status_code == 400
    assert missing_consent.get_json()["error"]["field"] == "approved"

    onboarded_client.post("/api/check-ins", json={
        "mood": "hopeful", "confidence": 5,
        "concern": "Later private context must not cross the approval boundary.", "save": True,
    }, headers=HEADERS)
    approved = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    )
    assert approved.status_code == 200
    console = onboarded_client.get("/console")
    assert b"Reviewed context that may be shared" in console.data
    assert b"Later private context must not cross" not in console.data

    revoked = onboarded_client.post(
        f"/api/briefs/{draft['id']}/revoke", json={"confirm": True}, headers=HEADERS
    )
    assert revoked.status_code == 200
    assert revoked.get_json()["data"]["approved"] == 0
    assert revoked.get_json()["data"]["shared_checkins"] == []
    assert b"No approved brief is available" in onboarded_client.get("/console").data
    with app.app_context():
        remaining = get_db().execute(
            "SELECT COUNT(*) AS count FROM brief_checkin_snapshots WHERE brief_id = ?",
            (draft["id"],),
        ).fetchone()["count"]
    assert remaining == 0


def test_followup_actions_render_and_complete_in_journey(onboarded_client, app):
    draft = _create_brief(onboarded_client)
    approved = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    ).get_json()["data"]
    booking = _create_booking(onboarded_client, approved["id"])
    response = onboarded_client.post("/api/follow-up", json={
        "booking_id": booking["id"],
        "summary": "I will keep ownership of the decision.",
        "actions": ["Write one reversible next step", "Ask a trusted mentor"],
        "checkin_date": (date.today() + timedelta(days=7)).isoformat(),
        "approved": True,
    }, headers=HEADERS)
    assert response.status_code == 201
    action_items = response.get_json()["data"]["action_items"]
    assert [item["text"] for item in action_items] == [
        "Write one reversible next step", "Ask a trusted mentor",
    ]

    journey = onboarded_client.get("/journey")
    assert b"Write one reversible next step" in journey.data
    assert b"Ask a trusted mentor" in journey.data
    action_id = action_items[0]["id"]
    endpoint = f"/api/journey/follow-up-actions/{action_id}/complete"
    assert f'data-action-endpoint="{endpoint}"'.encode() in journey.data
    completed = onboarded_client.post(endpoint, json={}, headers=HEADERS)
    assert completed.status_code == 200

    refreshed = onboarded_client.get("/journey")
    assert f'data-action-id="{action_id}"'.encode() in refreshed.data
    with app.app_context():
        row = get_db().execute(
            "SELECT completed, completed_at FROM followup_actions WHERE id = ?", (action_id,)
        ).fetchone()
    assert row["completed"] == 1
    assert row["completed_at"]


def test_followup_is_explicitly_scoped_to_owned_booking(onboarded_client, app):
    draft = _create_brief(onboarded_client)
    approved = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    ).get_json()["data"]
    first_booking = _create_booking(onboarded_client, approved["id"])
    first = onboarded_client.post("/api/follow-up", json={
        "booking_id": first_booking["id"],
        "summary": "This belongs only to the first sample conversation.",
        "actions": ["Review the first conversation"],
        "checkin_date": (date.today() + timedelta(days=4)).isoformat(),
        "approved": True,
    }, headers=HEADERS)
    assert first.status_code == 201

    second_booking = _create_booking(onboarded_client, approved["id"])
    page = onboarded_client.get("/follow-up")
    assert f'name="booking_id" value="{second_booking["id"]}"'.encode() in page.data
    assert b"This belongs only to the first sample conversation" not in page.data

    missing = onboarded_client.post("/api/follow-up", json={
        "summary": "No implicit latest-booking attachment.",
        "actions": ["Keep the ownership boundary explicit"],
        "checkin_date": (date.today() + timedelta(days=4)).isoformat(),
        "approved": True,
    }, headers=HEADERS)
    assert missing.status_code == 400
    assert missing.get_json()["error"]["field"] == "booking_id"

    other = app.test_client()
    with other.session_transaction() as state:
        state["csrf_token"] = HEADERS["X-CSRF-Token"]
        state["journey_owner_key"] = "independent-test-owner-key-0000000001"
    onboard = other.post("/onboarding", data={
        "csrf_token": HEADERS["X-CSRF-Token"],
        "display_name": "Mira",
        "birth_date": "1992-04-12",
        "focus_area": "career",
        "communication_preference": "concise",
        "save_consent": "yes",
    })
    assert onboard.status_code == 302
    with other.session_transaction() as state:
        state["csrf_token"] = HEADERS["X-CSRF-Token"]
    foreign = other.post("/api/follow-up", json={
        "booking_id": second_booking["id"],
        "summary": "This must not attach across owners.",
        "actions": ["Reject this request"],
        "checkin_date": (date.today() + timedelta(days=4)).isoformat(),
        "approved": True,
    }, headers=HEADERS)
    assert foreign.status_code == 400
    assert foreign.get_json()["error"]["field"] == "booking_id"
    foreign_feedback = other.post("/api/feedback", json={
        "type": "consultation",
        "value": "helpful",
        "booking_id": second_booking["id"],
    }, headers=HEADERS)
    assert foreign_feedback.status_code == 400
    assert foreign_feedback.get_json()["error"]["field"] == "booking_id"


def test_booking_helpfulness_is_canonical_across_followup_and_journey(
    onboarded_client, app
):
    draft = _create_brief(onboarded_client)
    approved = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    ).get_json()["data"]
    booking = _create_booking(onboarded_client, approved["id"])
    followup = onboarded_client.post("/api/follow-up", json={
        "booking_id": booking["id"],
        "summary": "This rating is tied to this conversation.",
        "actions": ["Keep one useful part"],
        "checkin_date": (date.today() + timedelta(days=5)).isoformat(),
        "helpfulness": 4,
        "approved": True,
    }, headers=HEADERS)
    assert followup.status_code == 201
    assert followup.get_json()["data"]["helpfulness"] == 5

    journey = onboarded_client.get("/journey")
    assert f'data-booking-id="{booking["id"]}"'.encode() in journey.data
    assert b'data-value="helpful" aria-pressed="true"' in journey.data

    changed = onboarded_client.post("/api/feedback", json={
        "type": "consultation",
        "value": "not_yet",
        "booking_id": booking["id"],
    }, headers=HEADERS)
    assert changed.status_code == 201
    changed_data = changed.get_json()["data"]
    assert changed_data["id"] > 0
    assert changed_data["type"] == "consultation"
    assert changed_data["value"] == "not_yet"
    assert changed_data["related_id"] == booking["id"]
    refreshed = onboarded_client.get("/follow-up")
    assert b'id="help_not_yet" type="button"' in refreshed.data
    assert b'data-helpfulness-value="not_yet" aria-pressed="true"' in refreshed.data
    with app.app_context():
        feedback_rows = get_db().execute(
            """SELECT value FROM feedback
               WHERE user_id = ? AND feedback_type = 'consultation' AND related_id = ?""",
            (booking["user_id"], booking["id"]),
        ).fetchall()
        stored_followup = get_db().execute(
            "SELECT helpfulness FROM followups WHERE id = ?",
            (followup.get_json()["data"]["id"],),
        ).fetchone()
    assert [row["value"] for row in feedback_rows] == ["not_yet"]
    assert stored_followup["helpfulness"] == 1


def test_new_followup_version_supersedes_prior_active_actions(onboarded_client, app):
    draft = _create_brief(onboarded_client)
    approved = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    ).get_json()["data"]
    booking = _create_booking(onboarded_client, approved["id"])
    first = onboarded_client.post("/api/follow-up", json={
        "booking_id": booking["id"],
        "summary": "First approved version.",
        "actions": ["Old plan action"],
        "checkin_date": (date.today() + timedelta(days=3)).isoformat(),
        "approved": True,
    }, headers=HEADERS).get_json()["data"]
    second = onboarded_client.post("/api/follow-up", json={
        "booking_id": booking["id"],
        "summary": "Replacement approved version.",
        "actions": ["Current plan action"],
        "checkin_date": (date.today() + timedelta(days=6)).isoformat(),
        "approved": True,
    }, headers=HEADERS)
    assert second.status_code == 201
    second_data = second.get_json()["data"]

    journey = onboarded_client.get("/journey")
    assert b"Current plan action" in journey.data
    assert b"Old plan action" not in journey.data
    followup_page = onboarded_client.get("/follow-up")
    assert b"Replacement approved version" in followup_page.data
    assert b"First approved version" not in followup_page.data

    old_action_id = first["action_items"][0]["id"]
    superseded_completion = onboarded_client.post(
        f"/api/journey/follow-up-actions/{old_action_id}/complete",
        json={},
        headers=HEADERS,
    )
    assert superseded_completion.status_code == 400
    with app.app_context():
        action_states = get_db().execute(
            """SELECT followup_id, active FROM followup_actions
               WHERE followup_id IN (?, ?) ORDER BY followup_id""",
            (first["id"], second_data["id"]),
        ).fetchall()
    assert [(row["followup_id"], row["active"]) for row in action_states] == [
        (first["id"], 0),
        (second_data["id"], 1),
    ]


def test_booking_creation_and_brief_revocation_serialize(onboarded_client, app):
    draft = _create_brief(onboarded_client)
    approved = onboarded_client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    )
    assert approved.status_code == 200
    cookie = onboarded_client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    booker = app.test_client()
    revoker = app.test_client()
    booker.set_cookie(app.config["SESSION_COOKIE_NAME"], cookie.value)
    revoker.set_cookie(app.config["SESSION_COOKIE_NAME"], cookie.value)
    barrier = Barrier(2)

    def create_booking_at_boundary():
        barrier.wait()
        return booker.post("/api/bookings", json={
            "brief_id": draft["id"],
            "astrologer_id": "asha",
            "mode": "audio",
            "slot": (datetime.now() + timedelta(days=2)).replace(
                microsecond=0
            ).isoformat(),
        }, headers=HEADERS)

    def revoke_at_boundary():
        barrier.wait()
        return revoker.post(
            f"/api/briefs/{draft['id']}/revoke",
            json={"confirm": True},
            headers=HEADERS,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        booking_future = pool.submit(create_booking_at_boundary)
        revoke_future = pool.submit(revoke_at_boundary)
        booking_response = booking_future.result()
        revoke_response = revoke_future.result()

    assert booking_response.status_code in {201, 400}
    assert revoke_response.status_code == 200
    with app.app_context():
        brief = get_db().execute(
            "SELECT approved, revoked FROM consultation_briefs WHERE id = ?",
            (draft["id"],),
        ).fetchone()
        bookings = get_db().execute(
            "SELECT COUNT(*) AS count FROM demo_bookings WHERE brief_id = ?",
            (draft["id"],),
        ).fetchone()["count"]
    assert dict(brief) == {"approved": 0, "revoked": 1}
    assert bookings == (1 if booking_response.status_code == 201 else 0)

    after_revoke = onboarded_client.post("/api/bookings", json={
        "brief_id": draft["id"],
        "astrologer_id": "asha",
        "mode": "audio",
        "slot": (datetime.now() + timedelta(days=3)).replace(microsecond=0).isoformat(),
    }, headers=HEADERS)
    assert after_revoke.status_code == 400
    assert after_revoke.get_json()["error"]["field"] == "brief_id"


def test_journey_renders_owned_pulse_content_separately_from_action(onboarded_client):
    checkin = onboarded_client.post("/api/check-ins", json={
        "mood": "grounded",
        "confidence": 4,
        "concern": "I want the saved concern visible only in my Journey.",
        "save": True,
    }, headers=HEADERS).get_json()["data"]

    page = onboarded_client.get("/journey")
    assert f'data-pulse-checkin-id="{checkin["id"]}"'.encode() in page.data
    assert b"I want the saved concern visible only in my Journey" in page.data
    assert checkin["reflection"].encode() in page.data
    assert f'data-pulse-action-for="{checkin["id"]}"'.encode() in page.data
    assert checkin["micro_action"].encode() in page.data
    endpoint = f"/api/journey/actions/{checkin['id']}/complete"
    assert f'data-action-endpoint="{endpoint}"'.encode() in page.data
