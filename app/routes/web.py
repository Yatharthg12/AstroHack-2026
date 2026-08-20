"""Server-rendered product and operator pages."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from app.services.consultations import (
    SAMPLE_ASTROLOGERS,
    booking_helpfulness,
    console_context,
    journey_followup_actions,
    latest_booking,
    latest_brief,
    latest_followup,
    recent_checkins,
)
from app.services.experiments import DEFAULTS, session_owner_key, simulate
from app.services.journey import (
    ValidationError,
    consent_status,
    create_user,
    current_user,
    journey_timeline,
    pulse_state,
)
from app.services.referrals import latest_referral, open_referral


web_bp = Blueprint("web", __name__)


def _user_or_onboarding():
    user = current_user()
    if not user:
        return None, redirect(url_for("web.onboarding"))
    return user, None


@web_bp.get("/")
def landing():
    return render_template("landing.html", user=current_user())


@web_bp.route("/onboarding", methods=["GET", "POST"])
def onboarding():
    if request.method == "GET":
        if current_user():
            return redirect(url_for("web.pulse"))
        return render_template("onboarding.html", user=current_user(), form={}, errors={})
    form = request.form.to_dict()
    try:
        create_user(form)
    except ValidationError as exc:
        return render_template(
            "onboarding.html",
            user=None,
            form=form,
            errors={exc.field or "form": str(exc)},
            error=str(exc),
        ), 400
    return redirect(url_for("web.pulse"))


@web_bp.get("/pulse")
def pulse():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    state = pulse_state(user["id"])
    return render_template(
        "pulse.html",
        user=user,
        pulse=state,
        streak=state["streak"],
        completed_days=state["completed_this_week"],
        now_weekday=date.today().weekday(),
        focus=user["focus_area"],
        latest_checkin=state["checkins"][0] if state["checkins"] else None,
    )


@web_bp.get("/bridge")
def bridge():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    brief = latest_brief(user["id"])
    latest_checkins = recent_checkins(user["id"])
    shareable_checkins = (
        brief["shared_checkins"]
        if brief and brief.get("include_checkins")
        else latest_checkins
    )
    return render_template(
        "bridge.html",
        user=user,
        brief=brief,
        shareable_checkins=shareable_checkins,
        latest_checkins=latest_checkins,
    )


@web_bp.get("/booking")
def booking():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    now = datetime.now().astimezone()
    first = now.replace(hour=18, minute=30, second=0, microsecond=0)
    if first <= now:
        first += timedelta(days=1)
    slots = [
        {"value": first.isoformat(), "label": first.strftime("%a, %d %b · %I:%M %p")},
        {"value": (first + timedelta(days=1)).replace(hour=10, minute=30).isoformat(), "label": (first + timedelta(days=1)).replace(hour=10, minute=30).strftime("%a, %d %b · %I:%M %p")},
        {"value": (first + timedelta(days=1)).replace(hour=19, minute=0).isoformat(), "label": (first + timedelta(days=1)).replace(hour=19, minute=0).strftime("%a, %d %b · %I:%M %p")},
    ]
    brief = latest_brief(user["id"])
    current_booking = latest_booking(user["id"], brief["id"]) if brief else None
    return render_template(
        "booking.html",
        user=user,
        brief=brief,
        booking=current_booking,
        astrologers=list(SAMPLE_ASTROLOGERS.values()),
        booking_slots=slots,
    )


@web_bp.get("/console")
def console():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    context = console_context(user["id"])
    approved_brief = context.get("brief")
    return render_template(
        "console.html",
        user=user,
        console=context,
        booking=(
            latest_booking(user["id"], approved_brief["id"])
            if approved_brief else None
        ),
    )


@web_bp.get("/follow-up")
def follow_up():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    current_booking = latest_booking(user["id"])
    return render_template(
        "follow_up.html",
        user=user,
        booking=current_booking,
        followup=(
            latest_followup(user["id"], current_booking["id"])
            if current_booking else None
        ),
        consultation_feedback=(
            booking_helpfulness(user["id"], current_booking["id"])
            if current_booking else None
        ),
    )


@web_bp.get("/circle")
def circle():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    return render_template(
        "circle.html",
        user=user,
        consents=consent_status(user["id"]),
        referral=latest_referral(user["id"]),
    )


@web_bp.get("/circle/<token>")
def circle_invite(token: str):
    try:
        invitation = open_referral(token)
        return render_template("circle_invite.html", user=current_user(), invitation=invitation, token=token, error=None)
    except ValidationError as exc:
        if exc.field == "rate_limit":
            status = 429
        else:
            status = 410 if "expired" in str(exc).lower() else 404
        headers = {"Retry-After": "60"} if status == 429 else {}
        return (
            render_template(
                "circle_invite.html",
                user=current_user(),
                invitation=None,
                token=token,
                error=str(exc),
            ),
            status,
            headers,
        )


@web_bp.get("/journey")
def journey():
    user, redirect_response = _user_or_onboarding()
    if redirect_response:
        return redirect_response
    state = pulse_state(user["id"])
    checkins_by_id = {item["id"]: item for item in state["checkins"]}
    events = []
    for item in journey_timeline(user["id"]):
        is_checkin = item["event_type"] == "checkin"
        try:
            display_date = datetime.fromisoformat(item["created_at"]).strftime("%d %b · %I:%M %p")
        except (TypeError, ValueError):
            display_date = "Recently"
        if is_checkin:
            checkin = checkins_by_id.get(item["related_id"])
            if not checkin:
                continue
            events.append({
                "id": checkin["id"],
                "type": "pulse-checkin",
                "title": "Pulse check-in",
                "description": checkin["reflection"],
                "timestamp": checkin["created_at"],
                "display_date": display_date,
                "pulse_checkin": checkin,
                "can_complete": False,
            })
            events.append({
                "id": checkin["id"],
                "type": "pulse-action",
                "title": "Pulse micro-action",
                "description": checkin["micro_action"],
                "timestamp": checkin["created_at"],
                "display_date": display_date,
                "completed": bool(checkin["action_completed"]),
                "can_complete": True,
                "action_endpoint": f"/api/journey/actions/{checkin['id']}/complete",
            })
            continue
        events.append({
            "id": item["id"],
            "type": item["event_type"],
            "title": item["title"],
            "description": item["detail"],
            "timestamp": item["created_at"],
            "display_date": display_date,
            "completed": False,
            "can_complete": False,
            "action_endpoint": None,
        })
    continuity_actions = journey_followup_actions(user["id"])
    for action in continuity_actions:
        events.append({
            "id": action["id"],
            "type": "followup-action",
            "title": "Approved follow-up action",
            "description": action["action_text"],
            "timestamp": action["created_at"],
            "display_date": f"Check in by {action['scheduled_checkin']}",
            "completed": bool(action["completed"]),
            "can_complete": True,
            "action_endpoint": f"/api/journey/follow-up-actions/{action['id']}/complete",
        })
    events.sort(key=lambda event: str(event.get("timestamp", "")), reverse=True)
    total_actions = len(state["checkins"]) + len(continuity_actions)
    completed_actions = (
        sum(bool(item["action_completed"]) for item in state["checkins"])
        + sum(bool(item["completed"]) for item in continuity_actions)
    )
    booking = latest_booking(user["id"])
    feedback_value = (
        booking_helpfulness(user["id"], booking["id"])
        if booking else None
    )
    return render_template(
        "journey.html",
        user=user,
        events=events,
        pulse=state,
        total_actions=total_actions,
        completed_actions=completed_actions,
        booking=booking,
        consultation_feedback=feedback_value,
    )


@web_bp.get("/growth")
def growth():
    from app.services.growth import growth_snapshot

    period = request.args.get("period", "90d")
    segment = request.args.get("segment", "all")
    focus = request.args.get("focus", "all")
    return render_template(
        "growth.html",
        user=current_user(),
        analytics=growth_snapshot(period=period, segment=segment, focus=focus),
        selected_filters={"period": period, "segment": segment, "focus": focus},
    )


@web_bp.get("/experiments")
def experiments():
    session_owner_key()
    return render_template(
        "experiments.html",
        user=current_user(),
        defaults=DEFAULTS,
        initial_result=simulate(DEFAULTS, persist=False),
    )


@web_bp.get("/privacy")
def privacy():
    return render_template("privacy.html", user=current_user())
