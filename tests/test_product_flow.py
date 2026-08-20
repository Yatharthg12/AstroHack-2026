"""End-to-end API flow, consent, referral, and deletion tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from app.db import get_db
from app.services.consultations import console_context
from app.services.referrals import latest_referral


HEADERS = {"X-CSRF-Token": "unit-test-csrf-token"}


def _independent_guest(app, csrf_token="independent-guest-csrf"):
    guest = app.test_client()
    with guest.session_transaction() as state:
        state["csrf_token"] = csrf_token
    return guest, {"X-CSRF-Token": csrf_token}


def _checkin(client):
    response = client.post("/api/check-ins", json={
        "mood": "grounded",
        "confidence": 4,
        "concern": "I want to make a careful career decision.",
        "save": True,
    }, headers=HEADERS)
    assert response.status_code == 201
    return response.get_json()["data"]


def _brief(client, include_checkins=True):
    response = client.post("/api/briefs", json={
        "topic": "Career direction",
        "context": "I am comparing two paths and want a structured conversation.",
        "outcome": "Leave with clearer questions and a calm next step.",
        "questions": ["What trade-offs should I reflect on?", "What can I test before deciding?"],
        "language": "English",
        "mode": "audio",
        "urgency": "soon",
        "include_checkins": include_checkins,
    }, headers=HEADERS)
    assert response.status_code == 201
    draft = response.get_json()["data"]
    assert draft["approved"] == 0
    approval = client.post(
        f"/api/briefs/{draft['id']}/approve", json={"approved": True}, headers=HEADERS
    )
    assert approval.status_code == 200
    return approval.get_json()["data"]


def _booking(client, brief_id):
    response = client.post("/api/bookings", json={
        "brief_id": brief_id,
        "astrologer_id": "asha",
        "mode": "audio",
        "slot": (datetime.now() + timedelta(days=2)).replace(microsecond=0).isoformat(),
    }, headers=HEADERS)
    assert response.status_code == 201
    return response.get_json()["data"]


def test_complete_guidance_flow(onboarded_client, app):
    checkin = _checkin(onboarded_client)
    assert "No birth-chart inference" in checkin["reason"]
    assert checkin["saved"] is True

    feedback = onboarded_client.post(
        f"/api/check-ins/{checkin['id']}/feedback",
        json={"relevant": True},
        headers=HEADERS,
    )
    assert feedback.status_code == 200

    brief = _brief(onboarded_client)
    assert brief["approved"] == 1
    assert brief["include_checkins"] == 1
    booking = _booking(onboarded_client, brief["id"])
    assert booking["status"] == "demo_confirmed"

    followup = onboarded_client.post("/api/follow-up", json={
        "booking_id": booking["id"],
        "summary": "I will compare the options without treating the session as certainty.",
        "actions": ["Write one reversible next step", "Ask a trusted mentor"],
        "checkin_date": (datetime.now() + timedelta(days=7)).date().isoformat(),
        "helpfulness": 4,
        "approved": True,
    }, headers=HEADERS)
    assert followup.status_code == 201
    assert len(followup.get_json()["data"]["actions"]) == 2

    completed = onboarded_client.post(
        f"/api/journey/actions/{checkin['id']}/complete", headers=HEADERS
    )
    assert completed.status_code == 200
    with app.app_context():
        row = get_db().execute("SELECT action_completed FROM checkins WHERE id = ?", (checkin["id"],)).fetchone()
        events = get_db().execute("SELECT event_type FROM journey_events").fetchall()
    assert row["action_completed"] == 1
    assert {event["event_type"] for event in events} >= {"onboarding", "checkin", "brief", "booking", "followup", "action"}


def test_console_never_exposes_unconsented_checkins(onboarded_client, app):
    _checkin(onboarded_client)
    brief = _brief(onboarded_client, include_checkins=False)
    with app.test_request_context():
        with onboarded_client.session_transaction() as client_session:
            user_id = client_session["user_id"]
        # A request context cannot inherit the test client's cookie, so inspect with explicit id.
        context = console_context(user_id)
    assert brief["include_checkins"] == 0
    assert context["checkins"] == []
    assert "birth_date" not in context["brief"]


def test_referral_loop_is_random_expiring_and_privacy_safe(onboarded_client, app):
    _checkin(onboarded_client)
    created = onboarded_client.post("/api/referrals", headers=HEADERS)
    assert created.status_code == 201
    referral = created.get_json()["data"]
    token = referral["token"]
    assert len(token) >= 40
    assert "birth" not in referral["url"]
    assert "career" not in referral["url"]

    invitation_page = onboarded_client.get(f"/circle/{token}")
    assert invitation_page.status_code == 200
    assert invitation_page.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert b"1994-08-17" not in invitation_page.data
    assert b"careful career decision" not in invitation_page.data

    guest, guest_headers = _independent_guest(app)
    missing_preference = guest.post(
        f"/api/referrals/{token}/complete",
        json={"consent": True},
        headers=guest_headers,
    )
    assert missing_preference.status_code == 400
    assert missing_preference.get_json()["error"]["field"] == "conversation_style"

    completion = guest.post(f"/api/referrals/{token}/complete", json={
        "display_name": "Mira",
        "mood": "hopeful",
        "focus_area": "personal growth",
        "conversation_style": "listen",
        "consent": True,
    }, headers=guest_headers)
    assert completion.status_code == 200
    assert completion.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    safe = completion.get_json()["data"]
    assert safe["completed"] is True
    assert safe["mutual_insight"]
    assert safe["mutual_insight"].startswith("Both people consented.")
    assert "invited person selected listening" in safe["mutual_insight"]
    assert "both chose" not in safe["mutual_insight"].lower()
    assert "invitee_name" not in safe
    assert set(safe) <= {
        "token", "inviter_name", "status", "expires_at", "completed",
        "mutual_insight",
    }

    completed_page = onboarded_client.get(f"/circle/{token}")
    assert completed_page.status_code == 200
    assert b"data-invite-form" not in completed_page.data
    assert b"Mira" not in completed_page.data
    assert safe["mutual_insight"].encode() not in completed_page.data

    with app.app_context():
        stored = get_db().execute(
            """SELECT invitee_name, invitee_focus, invitee_state, mutual_insight
               FROM referrals WHERE token = ?""",
            (token,),
        ).fetchone()
        events = get_db().execute(
            "SELECT event_type FROM referral_events r JOIN referrals f ON f.id = r.referral_id WHERE f.token = ?",
            (token,),
        ).fetchall()
    assert stored["invitee_name"] is None
    assert stored["invitee_focus"] is None
    assert stored["invitee_state"] is None
    assert stored["mutual_insight"] == safe["mutual_insight"]
    assert {row["event_type"] for row in events} >= {"created", "opened", "consented_completion"}


def test_inviter_session_cannot_complete_its_own_circle_link(
    onboarded_client, app
):
    created = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    token = created["token"]
    rejected = onboarded_client.post(
        f"/api/referrals/{token}/complete",
        json={"conversation_style": "listen", "consent": True},
        headers=HEADERS,
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["error"]["field"] == "invitee"

    guest, guest_headers = _independent_guest(app, "self-check-guest-csrf")
    accepted = guest.post(
        f"/api/referrals/{token}/complete",
        json={"conversation_style": "listen", "consent": True},
        headers=guest_headers,
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["data"]["completed"] is True


def test_referral_open_event_is_idempotent(onboarded_client, app):
    created = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    token = created["token"]
    first = onboarded_client.get(f"/circle/{token}")
    refreshed = onboarded_client.get(f"/circle/{token}")
    assert first.status_code == 200
    assert refreshed.status_code == 200

    with app.app_context():
        referral = get_db().execute(
            "SELECT id, status FROM referrals WHERE token = ?", (token,)
        ).fetchone()
        opened_events = get_db().execute(
            """SELECT COUNT(*) AS count FROM referral_events
               WHERE referral_id = ? AND event_type = 'opened'""",
            (referral["id"],),
        ).fetchone()["count"]
    assert referral["status"] == "opened"
    assert opened_events == 1


def test_referral_rejects_invalid_and_expired_tokens(onboarded_client, app):
    invalid = onboarded_client.get("/circle/not-a-valid-token")
    assert invalid.status_code == 404
    created = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    with app.app_context():
        get_db().execute(
            "UPDATE referrals SET expires_at = ? WHERE token = ?",
            ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(), created["token"]),
        )
        get_db().commit()
    expired = onboarded_client.get(f"/circle/{created['token']}")
    assert expired.status_code == 410


def test_new_referral_atomically_revokes_prior_active_link(onboarded_client, app):
    first = onboarded_client.post("/api/referrals", headers=HEADERS)
    assert first.status_code == 201
    first_token = first.get_json()["data"]["token"]
    assert onboarded_client.get(f"/circle/{first_token}").status_code == 200

    second = onboarded_client.post("/api/referrals", headers=HEADERS)
    assert second.status_code == 201
    second_token = second.get_json()["data"]["token"]
    assert second_token != first_token
    assert onboarded_client.get(f"/circle/{first_token}").status_code == 404
    assert onboarded_client.get(f"/circle/{second_token}").status_code == 200

    with app.app_context():
        old = get_db().execute(
            "SELECT status, inviter_consent FROM referrals WHERE token = ?",
            (first_token,),
        ).fetchone()
        replacement_revocations = get_db().execute(
            """SELECT COUNT(*) AS count FROM referral_events e
               JOIN referrals r ON r.id = e.referral_id
               WHERE r.token = ? AND e.event_type = 'revoked'
                 AND e.metadata_json = '{"reason":"replaced"}'""",
            (first_token,),
        ).fetchone()["count"]
    assert dict(old) == {"status": "revoked", "inviter_consent": 0}
    assert replacement_revocations == 1


def test_concurrent_referral_creation_leaves_exactly_one_live_link(
    onboarded_client, app
):
    session_cookie = onboarded_client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    creators = [app.test_client(), app.test_client()]
    for creator in creators:
        creator.set_cookie(app.config["SESSION_COOKIE_NAME"], session_cookie.value)
    with onboarded_client.session_transaction() as state:
        user_id = state["user_id"]
    barrier = Barrier(2)

    def create(index):
        barrier.wait()
        return creators[index].post("/api/referrals", headers=HEADERS)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, range(2)))
    assert [response.status_code for response in responses] == [201, 201]
    tokens = [response.get_json()["data"]["token"] for response in responses]
    availability = [
        onboarded_client.get(f"/circle/{token}").status_code for token in tokens
    ]
    assert sorted(availability) == [200, 404]

    with app.app_context():
        live_count = get_db().execute(
            """SELECT COUNT(*) AS count FROM referrals
               WHERE inviter_user_id = ? AND inviter_consent = 1
                 AND status IN ('created', 'opened') AND expires_at > ?""",
            (user_id, datetime.now(timezone.utc).isoformat()),
        ).fetchone()["count"]
    assert live_count == 1


def test_circle_invite_rate_limit_returns_429_and_retry_after(onboarded_client, app):
    created = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    app.config["RATE_LIMIT_PER_MINUTE"] = 1
    remote = {"REMOTE_ADDR": "203.0.113.55"}
    first = onboarded_client.get(
        f"/circle/{created['token']}", environ_overrides=remote
    )
    limited = onboarded_client.get(
        f"/circle/{created['token']}", environ_overrides=remote
    )
    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"


def test_referral_revocation_blocks_open_completion_and_replay_overwrite(onboarded_client, app):
    created = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    token = created["token"]
    guest, guest_headers = _independent_guest(app, "revocation-guest-csrf")
    first = guest.post(f"/api/referrals/{token}/complete", json={
        "display_name": "First Guest", "mood": "grounded",
        "conversation_style": "listen", "consent": True,
    }, headers=guest_headers)
    assert first.status_code == 200
    replay = guest.post(f"/api/referrals/{token}/complete", json={
        "display_name": "Overwrite Attempt", "mood": "low", "consent": True,
    }, headers=guest_headers)
    assert replay.status_code == 200
    replay_data = replay.get_json()["data"]
    assert replay_data["completed"] is True
    assert "invitee_name" not in replay_data
    assert "mutual_insight" not in replay_data

    revoke = onboarded_client.post(
        "/api/consents/circle", json={"granted": False}, headers=HEADERS
    )
    assert revoke.status_code == 200
    assert onboarded_client.get(f"/circle/{token}").status_code == 404


def test_latest_referral_excludes_elapsed_and_revoked_links(onboarded_client, app):
    elapsed = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    with onboarded_client.session_transaction() as state:
        user_id = state["user_id"]
    with app.app_context():
        get_db().execute(
            "UPDATE referrals SET expires_at = ? WHERE token = ?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), elapsed["token"]),
        )
        get_db().commit()
        assert latest_referral(user_id) is None

    consent_withdrawn = onboarded_client.post(
        "/api/referrals", headers=HEADERS
    ).get_json()["data"]
    with app.app_context():
        get_db().execute(
            """UPDATE consents SET granted = 0
               WHERE user_id = ? AND consent_type = 'circle_sharing'""",
            (user_id,),
        )
        get_db().commit()
        assert latest_referral(user_id) is None
    assert onboarded_client.get(f"/circle/{consent_withdrawn['token']}").status_code == 404
    with app.app_context():
        get_db().execute(
            "UPDATE referrals SET status = 'revoked', inviter_consent = 0 WHERE token = ?",
            (consent_withdrawn["token"],),
        )
        get_db().execute(
            """UPDATE consents SET granted = 1
               WHERE user_id = ? AND consent_type = 'circle_sharing'""",
            (user_id,),
        )
        get_db().commit()

    revoked = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    with app.app_context():
        get_db().execute(
            "UPDATE referrals SET status = 'revoked', inviter_consent = 0 WHERE token = ?",
            (revoked["token"],),
        )
        get_db().commit()
        assert latest_referral(user_id) is None


def test_concurrent_referral_completion_is_single_use_and_minimized(
    onboarded_client, app
):
    created = onboarded_client.post("/api/referrals", headers=HEADERS).get_json()["data"]
    token = created["token"]
    guests = [app.test_client(), app.test_client()]
    csrf_tokens = ["guest-one-csrf", "guest-two-csrf"]
    for guest, csrf_token in zip(guests, csrf_tokens, strict=True):
        with guest.session_transaction() as state:
            state["csrf_token"] = csrf_token
    barrier = Barrier(2)

    def complete(index):
        barrier.wait()
        return guests[index].post(
            f"/api/referrals/{token}/complete",
            json={
                "display_name": f"Guest {index}",
                "mood": "hopeful" if index else "grounded",
                "conversation_style": "ideas" if index else "listen",
                "consent": True,
            },
            headers={"X-CSRF-Token": csrf_tokens[index]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(complete, range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    results = [response.get_json()["data"] for response in responses]
    winners = [result for result in results if "mutual_insight" in result]
    losers = [result for result in results if "mutual_insight" not in result]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0]["status"] == "completed"
    assert "invitee_name" not in losers[0]

    with app.app_context():
        row = get_db().execute(
            """SELECT invitee_name, invitee_focus, invitee_state, mutual_insight
               FROM referrals WHERE token = ?""",
            (token,),
        ).fetchone()
        completion_events = get_db().execute(
            """SELECT COUNT(*) AS count FROM referral_events e
               JOIN referrals r ON r.id = e.referral_id
               WHERE r.token = ? AND e.event_type = 'consented_completion'""",
            (token,),
        ).fetchone()["count"]
    assert row["invitee_name"] is None
    assert row["invitee_focus"] is None
    assert row["invitee_state"] is None
    assert row["mutual_insight"] == winners[0]["mutual_insight"]
    assert completion_events == 1


def test_concurrent_create_and_revoke_leave_no_active_link(onboarded_client, app):
    session_cookie = onboarded_client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    creator = app.test_client()
    revoker = app.test_client()
    creator.set_cookie(app.config["SESSION_COOKIE_NAME"], session_cookie.value)
    revoker.set_cookie(app.config["SESSION_COOKIE_NAME"], session_cookie.value)
    with onboarded_client.session_transaction() as state:
        user_id = state["user_id"]
    barrier = Barrier(2)

    def create():
        barrier.wait()
        return creator.post("/api/referrals", headers=HEADERS)

    def revoke():
        barrier.wait()
        return revoker.post(
            "/api/consents/circle", json={"granted": False}, headers=HEADERS
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        create_future = pool.submit(create)
        revoke_future = pool.submit(revoke)
        created_response = create_future.result()
        revoked_response = revoke_future.result()
    assert created_response.status_code in {201, 400}
    assert revoked_response.status_code == 200

    with app.app_context():
        consent = get_db().execute(
            """SELECT granted FROM consents
               WHERE user_id = ? AND consent_type = 'circle_sharing'""",
            (user_id,),
        ).fetchone()["granted"]
        active = get_db().execute(
            """SELECT COUNT(*) AS count FROM referrals
               WHERE inviter_user_id = ?
                 AND inviter_consent = 1
                 AND status NOT IN ('expired', 'revoked')""",
            (user_id,),
        ).fetchone()["count"]
        assert latest_referral(user_id) is None
    assert consent == 0
    assert active == 0


def test_booking_page_with_unapproved_draft_has_no_booking_form(onboarded_client):
    draft = onboarded_client.post("/api/briefs", json={
        "topic": "Career direction",
        "context": "I need a private draft before deciding whether to share it.",
        "outcome": "A clearer set of questions.",
        "questions": ["What should I compare?"],
        "language": "English",
        "mode": "audio",
        "urgency": "soon",
        "include_checkins": False,
    }, headers=HEADERS)
    assert draft.status_code == 201
    assert draft.get_json()["data"]["approved"] == 0

    page = onboarded_client.get("/booking")
    assert page.status_code == 200
    assert b"data-booking-form" not in page.data
    assert b"Approve your brief first" in page.data


def test_second_onboarding_cannot_orphan_prior_journey(onboarded_client, app):
    response = onboarded_client.post("/onboarding", data={
        "csrf_token": "unit-test-csrf-token",
        "display_name": "Second", "birth_date": "1990-01-01", "focus_area": "career",
        "communication_preference": "concise", "save_consent": "yes",
    })
    assert response.status_code == 400
    with app.app_context():
        count = get_db().execute("SELECT COUNT(*) AS count FROM demo_users").fetchone()["count"]
    assert count == 1


def test_circle_requires_separate_consent(client, csrf_headers):
    client.post("/onboarding", data={
        "display_name": "Riya", "birth_date": "1996-02-10", "focus_area": "education",
        "communication_preference": "supportive", "save_consent": "yes",
    }, headers=csrf_headers)
    with client.session_transaction() as state:
        state["csrf_token"] = "unit-test-csrf-token"
    denied = client.post("/api/referrals", headers=HEADERS)
    assert denied.status_code == 400
    assert "consent" in denied.get_json()["error"]["message"].lower()


def test_reset_deletes_local_demo_data(onboarded_client, app):
    _checkin(onboarded_client)
    reset = onboarded_client.post("/api/reset", json={"confirm": True}, headers=HEADERS)
    assert reset.status_code == 200
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) AS count FROM demo_users").fetchone()["count"] == 0
        assert get_db().execute("SELECT COUNT(*) AS count FROM checkins").fetchone()["count"] == 0
    assert onboarded_client.get("/pulse").status_code == 302
