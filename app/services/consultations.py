"""Consultation preparation, demo booking and follow-up services."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from app.db import get_db, query_all, query_one

from .journey import _record_event, require_user
from .validation import (
    LANGUAGES,
    MODES,
    URGENCY_LEVELS,
    ValidationError,
    bool_value,
    choice,
    iso_future_date,
    text_value,
)


SPECIALITIES = {
    "career": ("Career & purpose", "Your topic is about work, direction or professional decisions."),
    "relationship": ("Relationships", "Your topic centres on communication or relationship patterns."),
    "finance": ("Finance reflection", "Your topic concerns money choices; the session must remain reflective, not financial advice."),
    "education": ("Education & direction", "Your topic concerns learning, exams or an education choice."),
    "family": ("Family dynamics", "Your topic concerns a family relationship or shared decision."),
    "personal_growth": ("Personal growth", "Your topic is best served by a broad reflective-guidance speciality."),
}


TOPIC_ALIASES = {
    "career direction": "career",
    "relationships": "relationship",
    "financial habits": "finance",
    "education direction": "education",
    "family relationships": "family",
    "personal growth": "personal_growth",
}

CONSULTATION_HELPFULNESS = {
    "not_yet": 1,
    "somewhat": 3,
    "helpful": 5,
}

HELPFULNESS_ALIASES = {
    "1": "not_yet",
    "2": "somewhat",
    "3": "somewhat",
    "4": "helpful",
    "5": "helpful",
    "not yet": "not_yet",
    "not_yet": "not_yet",
    "somewhat": "somewhat",
    "helpful": "helpful",
    "yes": "helpful",
    "no": "not_yet",
}


def _booking_view(row) -> dict | None:
    if not row:
        return None
    result = dict(row)
    try:
        parsed = datetime.fromisoformat(str(result["scheduled_for"]))
        label = parsed.strftime("%a, %d %b %Y · %I:%M %p")
        offset = parsed.strftime("%z")
        result["scheduled_label"] = (
            f"{label} · UTC{offset[:3]}:{offset[3:]}" if offset else f"{label} · local time"
        )
    except (KeyError, TypeError, ValueError):
        result["scheduled_label"] = "Sample time saved"
    return result


def _normalized_topic(data: dict) -> str:
    raw = text_value(data, "topic", maximum=100).lower().replace("-", " ").replace("_", " ")
    compact = " ".join(raw.split())
    canonical = TOPIC_ALIASES.get(compact, compact.replace(" ", "_"))
    if canonical not in SPECIALITIES:
        raise ValidationError("Choose a valid consultation topic.", "topic")
    return canonical


def _speciality_for_topic(topic: str) -> tuple[str, str]:
    """Derive the transparent suggestion from the brief topic, never hidden profile data."""

    speciality, _ = SPECIALITIES[topic]
    readable_topic = topic.replace("_", " ")
    return speciality, f"Suggested because the approved brief topic is {readable_topic!r}; no birth details or hidden score were used."

SAMPLE_ASTROLOGERS = {
    "asha": {"id": "asha", "name": "Asha Mehta", "speciality": "Career & purpose", "price": 399.0, "languages": ["Hindi", "English", "Hinglish"]},
    "dev": {"id": "dev", "name": "Dev Iyer", "speciality": "Relationships", "price": 449.0, "languages": ["English", "Tamil"]},
    "meera": {"id": "meera", "name": "Meera Sen", "speciality": "Personal growth", "price": 349.0, "languages": ["English", "Hindi", "Bengali"]},
}


def _questions(data: dict) -> list[str]:
    raw = data.get("questions", [])
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.replace("\r", "").split("\n") if part.strip()]
    if not isinstance(raw, list):
        raise ValidationError("Questions must be a list or one question per line.", "questions")
    values = [str(item).strip() for item in raw if str(item).strip()]
    if not values:
        raise ValidationError("Add at least one question for the astrologer.", "questions")
    if len(values) > 5 or any(len(item) > 240 for item in values):
        raise ValidationError("Use up to five questions, each no longer than 240 characters.", "questions")
    return values


def _write_consultation_consent(user_id: int, granted: bool) -> None:
    """Write consultation-context consent inside the caller's transaction."""

    get_db().execute(
        """INSERT INTO consents (user_id, consent_type, granted)
           VALUES (?, 'consultation_context', ?)
           ON CONFLICT(user_id, consent_type) DO UPDATE
           SET granted = excluded.granted, recorded_at = CURRENT_TIMESTAMP""",
        (user_id, int(granted)),
    )


def create_brief(data: dict) -> dict:
    user = require_user()
    topic = _normalized_topic(data)
    context = text_value(data, "context", maximum=1200)
    outcome_key = "outcome" if "outcome" in data else "desired_outcome"
    outcome = text_value(data, outcome_key, maximum=500)
    questions = _questions(data)
    language = choice(data, "language" if "language" in data else "preferred_language", LANGUAGES, normalize=True)
    mode = choice(data, "mode" if "mode" in data else "preferred_mode", MODES, normalize=True)
    normalized = dict(data)
    urgency_aliases = {"this_week": "soon", "today": "time-sensitive"}
    normalized["urgency"] = urgency_aliases.get(str(normalized.get("urgency", "")).lower(), normalized.get("urgency"))
    urgency = choice(normalized, "urgency", URGENCY_LEVELS, normalize=True)
    include_checkins = bool_value(data, "include_checkins")
    selected_checkins: list[dict] = []
    if include_checkins:
        raw_ids = data.get("checkin_ids", [])
        if isinstance(raw_ids, (str, int)):
            raw_ids = [raw_ids]
        if not isinstance(raw_ids, list) or len(raw_ids) > 3:
            raise ValidationError("Choose up to three reviewed Pulse entries.", "checkin_ids")
        try:
            selected_ids = list(dict.fromkeys(int(value) for value in raw_ids))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Choose valid reviewed Pulse entries.", "checkin_ids") from exc
        if selected_ids:
            placeholders = ",".join("?" for _ in selected_ids)
            selected_checkins = [dict(row) for row in query_all(
                f"""SELECT id, emotional_state, confidence, concern, created_at
                    FROM checkins WHERE user_id = ? AND id IN ({placeholders})
                    ORDER BY created_at DESC, id DESC""",
                (user["id"], *selected_ids),
            )]
            if {item["id"] for item in selected_checkins} != set(selected_ids):
                raise ValidationError("One or more reviewed Pulse entries are unavailable.", "checkin_ids")
    speciality, explanation = _speciality_for_topic(topic)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        approved_ids = [row["id"] for row in query_all(
            "SELECT id FROM consultation_briefs WHERE user_id = ? AND approved = 1",
            (user["id"],),
        )]
        if approved_ids:
            if not bool_value(data, "replace_approved"):
                raise ValidationError(
                    "Confirm that the replacement draft withdraws current console access.",
                    "replace_approved",
                )
            db.execute(
                "UPDATE consultation_briefs SET approved = 0, revoked = 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND approved = 1",
                (user["id"],),
            )
            db.executemany(
                "DELETE FROM brief_checkin_snapshots WHERE brief_id = ?",
                [(item_id,) for item_id in approved_ids],
            )
            _record_event(
                user["id"], "brief_revoked", "Prior consultation access withdrawn",
                "Creating a replacement draft withdrew the previously approved console context.",
                approved_ids[-1],
            )
        _write_consultation_consent(user["id"], False)
        cursor = db.execute(
            """INSERT INTO consultation_briefs
               (user_id, topic, context, desired_outcome, questions_json, preferred_language,
                preferred_mode, urgency, include_checkins, speciality, explanation, approved)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (user["id"], topic, context, outcome, json.dumps(questions), language, mode, urgency,
             int(include_checkins), speciality, explanation),
        )
        brief_id = cursor.lastrowid
        if selected_checkins:
            db.executemany(
                """INSERT INTO brief_checkin_snapshots
                   (brief_id, checkin_id, emotional_state, confidence, concern, checkin_created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (brief_id, item["id"], item["emotional_state"], item["confidence"],
                     item["concern"], item["created_at"])
                    for item in selected_checkins
                ],
            )
        _record_event(
            user["id"], "brief_draft", "Consultation brief drafted",
            f"Prepared for {speciality}; not shared until explicit approval.", brief_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_brief(brief_id, user["id"])


def get_brief(brief_id: int, user_id: int) -> dict:
    row = query_one("SELECT * FROM consultation_briefs WHERE id = ? AND user_id = ?", (brief_id, user_id))
    if not row:
        raise ValidationError("Consultation brief not found.", "brief_id")
    result = dict(row)
    result["questions"] = json.loads(result.pop("questions_json"))
    result["shared_checkins"] = [dict(item) for item in query_all(
        """SELECT checkin_id, emotional_state, confidence, concern, checkin_created_at AS created_at
           FROM brief_checkin_snapshots WHERE brief_id = ? ORDER BY checkin_created_at DESC, id DESC""",
        (brief_id,),
    )]
    return result


def recent_checkins(user_id: int, limit: int = 3) -> list[dict]:
    """Return the exact Pulse rows eligible for an explicit Bridge snapshot."""

    safe_limit = max(0, min(int(limit), 3))
    return [dict(row) for row in query_all(
        """SELECT id, emotional_state, confidence, concern, created_at
           FROM checkins WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?""",
        (user_id, safe_limit),
    )]


def latest_brief(user_id: int) -> dict | None:
    row = query_one("SELECT id FROM consultation_briefs WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", (user_id,))
    return get_brief(row["id"], user_id) if row else None


def approve_brief(brief_id: int) -> dict:
    """Approve a previously reviewed draft and record the context boundary."""

    user = require_user()
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = query_one(
            "SELECT approved, revoked, include_checkins, speciality FROM consultation_briefs WHERE id = ? AND user_id = ?",
            (brief_id, user["id"]),
        )
        if not row:
            raise ValidationError("Consultation brief not found.", "brief_id")
        if row["revoked"]:
            raise ValidationError(
                "A withdrawn brief cannot be re-approved. Create and review a new draft.", "brief_id"
            )
        latest = query_one(
            "SELECT id FROM consultation_briefs WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (user["id"],),
        )
        if not latest or latest["id"] != brief_id:
            raise ValidationError(
                "Only the current latest draft can be approved. Review it in Bridge.", "brief_id"
            )
        if not row["approved"]:
            previous_ids = [item["id"] for item in query_all(
                "SELECT id FROM consultation_briefs WHERE user_id = ? AND approved = 1 AND id != ?",
                (user["id"], brief_id),
            )]
            db.execute(
                "UPDATE consultation_briefs SET approved = 0, revoked = 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND approved = 1",
                (user["id"],),
            )
            if previous_ids:
                db.executemany(
                    "DELETE FROM brief_checkin_snapshots WHERE brief_id = ?",
                    [(item_id,) for item_id in previous_ids],
                )
            db.execute(
                "UPDATE consultation_briefs SET approved = 1, revoked = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (brief_id, user["id"]),
            )
            _write_consultation_consent(user["id"], bool(row["include_checkins"]))
            _record_event(
                user["id"], "brief", "Consultation brief approved",
                f"Approved for {row['speciality']}; recent check-ins {'included' if row['include_checkins'] else 'withheld'}.",
                brief_id,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_brief(brief_id, user["id"])


def revoke_brief(brief_id: int) -> dict:
    """Withdraw an approved brief and its frozen Pulse-context snapshot."""

    user = require_user()
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        brief = query_one(
            "SELECT approved, revoked FROM consultation_briefs WHERE id = ? AND user_id = ?",
            (brief_id, user["id"]),
        )
        if not brief:
            raise ValidationError("Consultation brief not found.", "brief_id")
        if brief["approved"]:
            db.execute(
                "UPDATE consultation_briefs SET approved = 0, revoked = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (brief_id, user["id"]),
            )
            db.execute("DELETE FROM brief_checkin_snapshots WHERE brief_id = ?", (brief_id,))
            _write_consultation_consent(user["id"], False)
            _record_event(
                user["id"], "brief_revoked", "Consultation access withdrawn",
                "The brief and any snapshotted Pulse context are no longer available in the console.", brief_id,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_brief(brief_id, user["id"])


def latest_approved_brief(user_id: int) -> dict | None:
    row = query_one(
        "SELECT id FROM consultation_briefs WHERE user_id = ? AND approved = 1 ORDER BY updated_at DESC, id DESC LIMIT 1",
        (user_id,),
    )
    return get_brief(row["id"], user_id) if row else None


def console_context(user_id: int) -> dict:
    brief = latest_approved_brief(user_id)
    if not brief:
        return {"brief": None, "checkins": []}
    checkins: list[dict] = brief["shared_checkins"] if brief["include_checkins"] else []
    return {"brief": brief, "checkins": checkins}


def create_booking(data: dict) -> dict:
    user = require_user()
    try:
        brief_id = int(data.get("brief_id"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Choose an approved consultation brief.", "brief_id") from exc
    astrologer_id = str(data.get("astrologer_id", "")).strip().lower()
    if astrologer_id not in SAMPLE_ASTROLOGERS:
        raise ValidationError("Choose a sample astrologer.", "astrologer_id")
    astrologer = SAMPLE_ASTROLOGERS[astrologer_id]
    mode = choice(data, "mode", MODES, normalize=True)
    slot_raw = data.get("slot") or data.get("scheduled_for")
    now = datetime.now()
    slot_aliases = {
        "today_1830": now.replace(hour=18, minute=30, second=0, microsecond=0),
        "tomorrow_1030": (now + timedelta(days=1)).replace(hour=10, minute=30, second=0, microsecond=0),
        "tomorrow_1900": (now + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0),
    }
    if slot_raw in slot_aliases:
        candidate = slot_aliases[slot_raw]
        if candidate <= now:
            candidate += timedelta(days=1)
        slot_raw = candidate.isoformat()
    if not slot_raw:
        slot_raw = (datetime.now() + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0).isoformat()
    slot = iso_future_date({"slot": slot_raw}, "slot")
    parsed_slot = datetime.fromisoformat(slot)
    comparison_now = datetime.now(parsed_slot.tzinfo) if parsed_slot.tzinfo else datetime.now()
    if parsed_slot <= comparison_now:
        raise ValidationError("Choose a future sample time.", "slot")
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        brief = query_one(
            """SELECT id FROM consultation_briefs
               WHERE id = ? AND user_id = ? AND approved = 1 AND revoked = 0""",
            (brief_id, user["id"]),
        )
        if not brief:
            raise ValidationError(
                "Choose the current approved consultation brief before booking.",
                "brief_id",
            )
        cursor = db.execute(
            """INSERT INTO demo_bookings
               (user_id, brief_id, astrologer_name, mode, scheduled_for, sample_price)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user["id"], brief_id, astrologer["name"], mode, slot, astrologer["price"]),
        )
        booking_id = cursor.lastrowid
        _record_event(
            user["id"], "booking", "Demo consultation reserved",
            f"Sample {mode} session with {astrologer['name']}. No real booking or charge occurred.",
            booking_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _booking_view(query_one("SELECT * FROM demo_bookings WHERE id = ?", (booking_id,)))


def latest_booking(user_id: int, brief_id: int | None = None) -> dict | None:
    if brief_id is None:
        row = query_one(
            "SELECT * FROM demo_bookings WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (user_id,),
        )
    else:
        row = query_one(
            """SELECT * FROM demo_bookings WHERE user_id = ? AND brief_id = ?
               ORDER BY created_at DESC, id DESC LIMIT 1""",
            (user_id, brief_id),
        )
    return _booking_view(row)


def owned_booking(booking_id: int, user_id: int) -> dict:
    """Load one explicitly selected booking without crossing user ownership."""

    row = query_one(
        "SELECT * FROM demo_bookings WHERE id = ? AND user_id = ?",
        (booking_id, user_id),
    )
    if not row:
        raise ValidationError("Sample booking not found.", "booking_id")
    return _booking_view(row)


def _canonical_helpfulness(value) -> tuple[str, int]:
    key = str(value).strip().lower().replace("-", "_")
    canonical = HELPFULNESS_ALIASES.get(key)
    if canonical is None:
        raise ValidationError(
            "Helpfulness must be helpful, somewhat, or not yet.", "helpfulness"
        )
    return canonical, CONSULTATION_HELPFULNESS[canonical]


def _write_booking_helpfulness(
    user_id: int, booking_id: int, canonical: str, score: int
) -> None:
    """Keep the booking's one canonical rating and legacy numeric snapshot aligned."""

    db = get_db()
    updated = db.execute(
        """UPDATE feedback SET value = ?, created_at = CURRENT_TIMESTAMP
           WHERE user_id = ? AND feedback_type = 'consultation' AND related_id = ?""",
        (canonical, user_id, booking_id),
    )
    if updated.rowcount == 0:
        db.execute(
            """INSERT INTO feedback (user_id, feedback_type, value, related_id)
               VALUES (?, 'consultation', ?, ?)""",
            (user_id, canonical, booking_id),
        )
    db.execute(
        "UPDATE followups SET helpfulness = ? WHERE user_id = ? AND booking_id = ?",
        (score, user_id, booking_id),
    )


def booking_helpfulness(user_id: int, booking_id: int) -> str | None:
    row = query_one(
        """SELECT value FROM feedback
           WHERE user_id = ? AND feedback_type = 'consultation' AND related_id = ?
           ORDER BY id DESC LIMIT 1""",
        (user_id, booking_id),
    )
    if row:
        return HELPFULNESS_ALIASES.get(str(row["value"]).strip().lower())
    legacy = query_one(
        """SELECT helpfulness FROM followups
           WHERE user_id = ? AND booking_id = ? AND helpfulness IS NOT NULL
           ORDER BY created_at DESC, id DESC LIMIT 1""",
        (user_id, booking_id),
    )
    if legacy:
        return HELPFULNESS_ALIASES.get(str(legacy["helpfulness"]))
    return None


def set_booking_helpfulness(booking_id: int, value) -> str:
    """Record the canonical helpfulness state for one owned sample booking."""

    user = require_user()
    canonical, score = _canonical_helpfulness(value)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        owned_booking(booking_id, user["id"])
        _write_booking_helpfulness(user["id"], booking_id, canonical, score)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return canonical


def create_followup(data: dict) -> dict:
    user = require_user()
    try:
        booking_id = int(data.get("booking_id"))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Choose the sample booking this follows.", "booking_id") from exc
    booking = owned_booking(booking_id, user["id"])
    if not bool_value(data, "approved"):
        raise ValidationError("Review and approve the summary before saving it.", "approved")
    summary = text_value(data, "summary", maximum=1200)
    raw_actions = data.get("actions", [])
    if isinstance(raw_actions, str):
        raw_actions = [item.strip() for item in raw_actions.replace("\r", "").split("\n") if item.strip()]
    if not isinstance(raw_actions, list):
        raise ValidationError("Actions must be a list.", "actions")
    actions = [str(item).strip() for item in raw_actions if str(item).strip()]
    if not 1 <= len(actions) <= 3 or any(len(item) > 240 for item in actions):
        raise ValidationError("Add one to three concise follow-up actions.", "actions")
    date_key = "checkin_date" if "checkin_date" in data else "scheduled_checkin"
    scheduled = text_value(data, date_key, maximum=10)
    try:
        scheduled_date = date.fromisoformat(scheduled)
    except ValueError as exc:
        raise ValidationError("Choose a valid follow-up date.", date_key) from exc
    if scheduled_date < date.today():
        raise ValidationError("The follow-up date cannot be in the past.", date_key)
    helpfulness = data.get("helpfulness")
    if helpfulness in (None, ""):
        helpfulness_canonical = booking_helpfulness(user["id"], booking["id"])
        helpfulness_value = (
            CONSULTATION_HELPFULNESS[helpfulness_canonical]
            if helpfulness_canonical else None
        )
    else:
        helpfulness_canonical, helpfulness_value = _canonical_helpfulness(helpfulness)
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """UPDATE followup_actions SET active = 0
               WHERE user_id = ? AND followup_id IN (
                   SELECT id FROM followups WHERE user_id = ? AND booking_id = ?
               )""",
            (user["id"], user["id"], booking["id"]),
        )
        cursor = db.execute(
            """INSERT INTO followups
               (user_id, booking_id, summary, actions_json, scheduled_checkin, helpfulness)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                user["id"], booking["id"], summary, json.dumps(actions), scheduled,
                helpfulness_value,
            ),
        )
        followup_id = cursor.lastrowid
        action_rows: list[dict] = []
        for action in actions:
            action_cursor = db.execute(
                """INSERT INTO followup_actions
                   (followup_id, user_id, action_text, active) VALUES (?, ?, ?, 1)""",
                (followup_id, user["id"], action),
            )
            action_rows.append({
                "id": action_cursor.lastrowid,
                "text": action,
                "completed": False,
                "active": True,
            })
        if helpfulness_canonical is not None:
            _write_booking_helpfulness(
                user["id"], booking["id"], helpfulness_canonical, helpfulness_value
            )
        _record_event(
            user["id"], "followup", "Guidance carried forward",
            f"{len(actions)} user-approved follow-up action(s) saved.", followup_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    result = dict(query_one("SELECT * FROM followups WHERE id = ?", (followup_id,)))
    result["actions"] = json.loads(result.pop("actions_json"))
    result["action_items"] = action_rows
    return result


def latest_followup(user_id: int, booking_id: int) -> dict | None:
    """Return only the latest plan for one explicitly selected owned booking."""

    row = query_one(
        """SELECT * FROM followups WHERE user_id = ? AND booking_id = ?
           ORDER BY created_at DESC, id DESC LIMIT 1""",
        (user_id, booking_id),
    )
    if not row:
        return None
    result = dict(row)
    result["actions"] = json.loads(result.pop("actions_json"))
    result["action_items"] = [dict(item) for item in query_all(
        """SELECT id, action_text AS text, active, completed, completed_at
           FROM followup_actions WHERE followup_id = ? ORDER BY id""",
        (result["id"],),
    )]
    return result


def journey_followup_actions(user_id: int) -> list[dict]:
    """Return user-approved continuity actions for Journey rendering."""

    return [dict(row) for row in query_all(
        """SELECT fa.id, fa.action_text, fa.completed, fa.completed_at, fa.created_at,
                  f.scheduled_checkin, f.id AS followup_id
           FROM followup_actions fa
           JOIN followups f ON f.id = fa.followup_id
           WHERE fa.user_id = ? AND fa.active = 1
           ORDER BY fa.created_at DESC, fa.id DESC""",
        (user_id,),
    )]


def complete_followup_action(action_id: int) -> bool:
    """Complete one owned follow-up action exactly once."""

    user = require_user()
    db = get_db()
    action = query_one(
        """SELECT id, action_text, completed FROM followup_actions
           WHERE id = ? AND user_id = ? AND active = 1""",
        (action_id, user["id"]),
    )
    if not action:
        raise ValidationError("Follow-up action not found.", "action_id")
    if not action["completed"]:
        cursor = db.execute(
            """UPDATE followup_actions SET completed = 1, completed_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ? AND active = 1 AND completed = 0""",
            (action_id, user["id"]),
        )
        if cursor.rowcount == 1:
            _record_event(
                user["id"], "followup_action", "Follow-up action completed",
                str(action["action_text"]), action_id,
            )
        db.commit()
        return cursor.rowcount == 1
    return False
