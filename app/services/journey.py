"""Onboarding, Pulse and timeline business rules."""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta

from flask import session

from app.db import get_db, query_all, query_one

from .validation import (
    COMMUNICATION_PREFERENCES,
    FOCUS_AREAS,
    MOODS,
    ValidationError,
    bool_value,
    choice,
    integer_value,
    iso_date,
    optional_iso_time,
    optional_text,
    text_value,
)


SIGN_DATES = (
    ((1, 20), "Aquarius"), ((2, 19), "Pisces"), ((3, 21), "Aries"),
    ((4, 20), "Taurus"), ((5, 21), "Gemini"), ((6, 21), "Cancer"),
    ((7, 23), "Leo"), ((8, 23), "Virgo"), ((9, 23), "Libra"),
    ((10, 23), "Scorpio"), ((11, 22), "Sagittarius"), ((12, 22), "Capricorn"),
)

REFLECTIONS = {
    "career": "Notice the choice that gives you clarity, not merely speed. Your {mood} energy can help you define one useful next step.",
    "relationship": "Make room for one honest, kind exchange today. Feeling {mood} is information, not a verdict on the relationship.",
    "finance": "Separate what needs attention today from what can be reviewed later. A {mood} state benefits from a calm written check.",
    "education": "Progress can be small and still count. Use your {mood} energy for one focused learning block.",
    "family": "A clear, gentle question may create more movement than an assumption. Let your {mood} state guide a pause first.",
    "personal growth": "Treat today's feeling of being {mood} as a signal to observe, not a fixed identity. Choose one action you can complete.",
}

ACTIONS = {
    "career": "Write the next decision as one sentence, then list the smallest reversible step.",
    "relationship": "Ask one open question and listen without preparing your reply.",
    "finance": "Spend ten minutes reviewing one category; avoid making an impulsive financial decision.",
    "education": "Set a 20-minute focus timer for the topic you have postponed.",
    "family": "Send a brief check-in to one family member without adding an agenda.",
    "personal growth": "Take five quiet minutes to name what is within your control today.",
}


def sun_sign(birth_date: str) -> str:
    parsed = date.fromisoformat(birth_date)
    month_day = (parsed.month, parsed.day)
    sign = "Capricorn"
    for boundary, candidate in SIGN_DATES:
        if month_day >= boundary:
            sign = candidate
    return sign


def _record_event(user_id: int, event_type: str, title: str, detail: str, related_id: int | None = None) -> None:
    get_db().execute(
        "INSERT INTO journey_events (user_id, event_type, title, detail, related_id) VALUES (?, ?, ?, ?, ?)",
        (user_id, event_type, title, detail, related_id),
    )


def create_user(data: dict) -> dict:
    if current_user() is not None:
        raise ValidationError("A demo journey is already active. Reset it before starting another.", "user")
    name = text_value(data, "display_name", maximum=60)
    birth_date = iso_date(data, "birth_date")
    birth_time = optional_iso_time(data, "birth_time")
    birth_city = optional_text(data, "birth_city", maximum=80)
    normalized = dict(data)
    normalized["focus_area"] = normalized.get("focus_area", normalized.get("focus", ""))
    if normalized["focus_area"] == "personal_growth":
        normalized["focus_area"] = "personal growth"
    preference_aliases = {
        "gentle": "supportive", "direct": "concise", "reflective": "detailed"
    }
    raw_preference = str(normalized.get("communication_preference", "")).lower()
    normalized["communication_preference"] = preference_aliases.get(raw_preference, raw_preference)
    focus = choice(normalized, "focus_area", FOCUS_AREAS, normalize=True)
    preference = choice(normalized, "communication_preference", COMMUNICATION_PREFERENCES, normalize=True)
    if not bool_value(data, "save_consent") and not bool_value(data, "consent_save"):
        raise ValidationError("Consent is required to save this demonstration journey.", "save_consent")
    circle = bool_value(data, "circle_consent") or bool_value(data, "consent_circle")
    owner_key = session.get("journey_owner_key")
    if not isinstance(owner_key, str) or len(owner_key) < 32:
        csrf_seed = session.get("csrf_token")
        if not isinstance(csrf_seed, str) or len(csrf_seed) < 16:
            raise ValidationError("Refresh onboarding before creating a journey.", "session")
        owner_key = f"journey-{csrf_seed}"
        session["journey_owner_key"] = owner_key
    public_id = secrets.token_urlsafe(12)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        existing = query_one(
            "SELECT id FROM demo_users WHERE journey_owner_key = ?", (owner_key,)
        )
        if existing:
            user_id = existing["id"]
        else:
            cursor = db.execute(
                """INSERT INTO demo_users
                   (public_id, journey_owner_key, display_name, birth_date, birth_time, birth_city,
                    focus_area, communication_preference, sun_sign)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (public_id, owner_key, name, birth_date, birth_time, birth_city, focus, preference,
                 sun_sign(birth_date)),
            )
            user_id = cursor.lastrowid
            db.executemany(
                "INSERT INTO consents (user_id, consent_type, granted) VALUES (?, ?, ?)",
                [(user_id, "save_journey", 1), (user_id, "circle_sharing", int(circle))],
            )
            _record_event(user_id, "onboarding", "Orbit journey started", f"Focus selected: {focus}.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    experiment_owner_key = session.get("experiment_owner_key")
    session.clear()
    session["user_id"] = user_id
    session["journey_owner_key"] = owner_key
    if isinstance(experiment_owner_key, str):
        session["experiment_owner_key"] = experiment_owner_key
    session.permanent = True
    row = query_one("SELECT * FROM demo_users WHERE id = ?", (user_id,))
    return dict(row) if row else {}


def current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = query_one("SELECT * FROM demo_users WHERE id = ?", (user_id,))
    return dict(row) if row else None


def require_user() -> dict:
    user = current_user()
    if not user:
        raise ValidationError("Start the Orbit demo before continuing.", "user")
    return user


def create_checkin(data: dict) -> dict:
    user = require_user()
    mood_data = dict(data)
    if "mood" in mood_data and "emotional_state" not in mood_data:
        mood_data["emotional_state"] = mood_data["mood"]
    mood_aliases = {"1": "stretched", "2": "low", "3": "grounded", "4": "hopeful", "5": "energised"}
    mood_data["emotional_state"] = mood_aliases.get(str(mood_data.get("emotional_state")), mood_data.get("emotional_state"))
    mood = choice(mood_data, "emotional_state", MOODS, normalize=True)
    confidence = integer_value(data, "confidence", 1, 5)
    concern = text_value(data, "concern", maximum=240)
    focus = user["focus_area"]
    reflection = REFLECTIONS[focus].format(mood=mood)
    micro_action = ACTIONS[focus]
    reason = f"Shown because you selected {focus} as your focus and described today as {mood}. No birth-chart inference was used."
    save = bool_value(data, "save", True)
    result = {
        "id": None,
        "emotional_state": mood,
        "confidence": confidence,
        "concern": concern,
        "reflection": reflection,
        "micro_action": micro_action,
        "reason": reason,
        "saved": save,
    }
    if save:
        db = get_db()
        cursor = db.execute(
            """INSERT INTO checkins
               (user_id, emotional_state, confidence, concern, reflection, micro_action, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user["id"], mood, confidence, concern, reflection, micro_action, reason),
        )
        result["id"] = cursor.lastrowid
        _record_event(user["id"], "checkin", "Pulse check-in saved", micro_action, cursor.lastrowid)
        db.commit()
        state = pulse_state(user["id"])
        result["streak"] = state["streak"]
        result["weekly"] = state["weekly"]
    return result


def pulse_state(user_id: int) -> dict:
    rows = query_all(
        "SELECT id, emotional_state, confidence, concern, reflection, micro_action, relevance, action_completed, created_at FROM checkins WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    dates = set()
    for row in rows:
        try:
            dates.add(datetime.fromisoformat(row["created_at"]).date())
        except ValueError:
            continue
    today = date.today()
    streak = 0
    cursor = today
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    weekly = [week_start + timedelta(days=i) in dates for i in range(7)]
    return {"checkins": [dict(row) for row in rows], "streak": streak, "weekly": weekly, "completed_this_week": sum(weekly)}


def set_checkin_feedback(checkin_id: int, relevant: str) -> None:
    user = require_user()
    if relevant not in {"yes", "no"}:
        raise ValidationError("Feedback must be yes or no.", "relevant")
    cursor = get_db().execute(
        "UPDATE checkins SET relevance = ? WHERE id = ? AND user_id = ?",
        (relevant, checkin_id, user["id"]),
    )
    if cursor.rowcount != 1:
        raise ValidationError("Check-in not found.", "checkin_id")
    get_db().execute(
        "INSERT INTO feedback (user_id, feedback_type, value) VALUES (?, 'pulse_relevance', ?)",
        (user["id"], relevant),
    )
    get_db().commit()


def complete_action(checkin_id: int) -> bool:
    user = require_user()
    db = get_db()
    cursor = db.execute(
        "UPDATE checkins SET action_completed = 1 WHERE id = ? AND user_id = ? AND action_completed = 0",
        (checkin_id, user["id"]),
    )
    if cursor.rowcount == 1:
        _record_event(user["id"], "action", "Micro-action completed", "A saved Pulse action was marked complete.", checkin_id)
        db.commit()
        return True
    exists = query_one("SELECT 1 FROM checkins WHERE id = ? AND user_id = ?", (checkin_id, user["id"]))
    if not exists:
        raise ValidationError("Action not found.", "checkin_id")
    db.commit()
    return False


def journey_timeline(user_id: int) -> list[dict]:
    return [dict(row) for row in query_all(
        "SELECT id, event_type, title, detail, related_id, created_at FROM journey_events WHERE user_id = ? ORDER BY created_at DESC, id DESC",
        (user_id,),
    )]


def reset_current_user() -> None:
    user = current_user()
    owner_key = session.get("experiment_owner_key")
    db = get_db()
    if user and isinstance(owner_key, str):
        db.execute(
            "DELETE FROM experiment_runs WHERE user_id = ? OR owner_key = ?",
            (user["id"], owner_key),
        )
    elif user:
        db.execute("DELETE FROM experiment_runs WHERE user_id = ?", (user["id"],))
    elif isinstance(owner_key, str):
        db.execute("DELETE FROM experiment_runs WHERE owner_key = ?", (owner_key,))
    if user:
        db.execute("DELETE FROM demo_users WHERE id = ?", (user["id"],))
    db.commit()
    session.clear()


def consent_status(user_id: int) -> dict[str, bool]:
    rows = query_all("SELECT consent_type, granted FROM consents WHERE user_id = ?", (user_id,))
    return {row["consent_type"]: bool(row["granted"]) for row in rows}


def set_consent(user_id: int, consent_type: str, granted: bool) -> None:
    get_db().execute(
        """INSERT INTO consents (user_id, consent_type, granted) VALUES (?, ?, ?)
           ON CONFLICT(user_id, consent_type) DO UPDATE SET granted = excluded.granted, recorded_at = CURRENT_TIMESTAMP""",
        (user_id, consent_type, int(granted)),
    )
    get_db().commit()
