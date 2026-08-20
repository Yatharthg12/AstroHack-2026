"""Consent-gated, privacy-safe Orbit Circle referral loop."""

from __future__ import annotations

import json
import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from flask import current_app, request

from app.db import get_db, query_one

from .journey import _record_event, current_user, require_user
from .validation import ValidationError, bool_value


_hits: dict[str, deque[datetime]] = defaultdict(deque)
_hits_lock = Lock()


def check_rate_limit(scope: str) -> None:
    now = datetime.now(timezone.utc)
    key = f"{scope}:{request.remote_addr or 'local'}"
    limit = int(current_app.config.get("RATE_LIMIT_PER_MINUTE", 30))
    with _hits_lock:
        queue = _hits[key]
        cutoff = now - timedelta(minutes=1)
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= limit:
            raise ValidationError("Too many requests. Wait a minute and try again.", "rate_limit")
        queue.append(now)


def _event(referral_id: int, event_type: str, metadata: dict | None = None) -> None:
    get_db().execute(
        "INSERT INTO referral_events (referral_id, event_type, metadata_json) VALUES (?, ?, ?)",
        (referral_id, event_type, json.dumps(metadata or {}, separators=(",", ":"))),
    )


def create_referral() -> dict:
    check_rate_limit("create_referral")
    user = require_user()
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=int(current_app.config["REFERRAL_TTL_HOURS"]))
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        consent = query_one(
            "SELECT granted FROM consents WHERE user_id = ? AND consent_type = 'circle_sharing'",
            (user["id"],),
        )
        if not consent or not consent["granted"]:
            raise ValidationError(
                "Enable optional Circle sharing consent before creating an invitation.",
                "circle_consent",
            )
        active_ids = [
            row["id"]
            for row in db.execute(
                """SELECT id FROM referrals
                   WHERE inviter_user_id = ?
                     AND inviter_consent = 1
                     AND status IN ('created', 'opened')
                     AND expires_at > ?""",
                (user["id"], datetime.now(timezone.utc).isoformat()),
            ).fetchall()
        ]
        if active_ids:
            placeholders = ",".join("?" for _ in active_ids)
            db.execute(
                f"""UPDATE referrals
                    SET inviter_consent = 0, status = 'revoked'
                    WHERE id IN ({placeholders})""",
                tuple(active_ids),
            )
            db.executemany(
                """INSERT INTO referral_events
                       (referral_id, event_type, metadata_json)
                   VALUES (?, 'revoked', '{\"reason\":\"replaced\"}')""",
                [(referral_id,) for referral_id in active_ids],
            )
        cursor = db.execute(
            "INSERT INTO referrals (token, inviter_user_id, inviter_consent, expires_at) VALUES (?, ?, 1, ?)",
            (token, user["id"], expires.isoformat()),
        )
        referral_id = cursor.lastrowid
        _event(referral_id, "created")
        _record_event(user["id"], "referral", "Private Circle invitation created", "A time-limited link was created without birth details or concerns.", referral_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Relative URL avoids reflecting an untrusted Host header. The same-origin
    # browser converts it to an absolute share URL from the origin it loaded.
    return {"token": token, "url": f"/circle/{token}", "expires_at": expires.isoformat(), "status": "created"}


def _load_referral(token: str) -> dict:
    if len(token) < 32 or len(token) > 80:
        raise ValidationError("This invitation link is invalid.", "token")
    row = query_one(
        """SELECT r.*, u.display_name AS inviter_name,
                  COALESCE(c.granted, 0) AS current_circle_consent
           FROM referrals r
           JOIN demo_users u ON u.id = r.inviter_user_id
           LEFT JOIN consents c ON c.user_id = r.inviter_user_id
             AND c.consent_type = 'circle_sharing'
           WHERE r.token = ?""",
        (token,),
    )
    if not row:
        raise ValidationError("This invitation link is invalid.", "token")
    result = dict(row)
    if (
        result["status"] == "revoked"
        or not result["inviter_consent"]
        or not result["current_circle_consent"]
    ):
        raise ValidationError("This invitation was withdrawn and is no longer available.", "token")
    expires = datetime.fromisoformat(result["expires_at"])
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        if result["status"] != "expired":
            get_db().execute("UPDATE referrals SET status = 'expired' WHERE id = ?", (result["id"],))
            get_db().commit()
        raise ValidationError("This invitation has expired. Ask for a new link.", "token")
    return result


def open_referral(token: str) -> dict:
    check_rate_limit("open_referral")
    referral = _load_referral(token)
    if referral["status"] == "created":
        db = get_db()
        cursor = db.execute(
            "UPDATE referrals SET status = 'opened' WHERE id = ? AND status = 'created'",
            (referral["id"],),
        )
        if cursor.rowcount == 1:
            _event(referral["id"], "opened")
            referral["status"] = "opened"
        db.commit()
        if cursor.rowcount != 1:
            # Another request transitioned or revoked the token first. Reload
            # the authoritative state rather than returning the stale read.
            referral = _load_referral(token)
    return safe_referral_view(referral)


def complete_referral(token: str, data: dict) -> dict:
    check_rate_limit("complete_referral")
    referral = _load_referral(token)
    viewer = current_user()
    if viewer and viewer["id"] == referral["inviter_user_id"]:
        raise ValidationError(
            "The inviter cannot complete their own Circle invitation. "
            "Open it in an independent guest session.",
            "invitee",
        )
    if referral["status"] == "completed":
        # A repeated POST must be idempotent without becoming a read endpoint
        # for the original invitee's name or the consent-gated insight.
        return safe_referral_view(referral)
    if not bool_value(data, "consent"):
        raise ValidationError("Consent is required to complete this independent Circle check-in.", "consent")
    conversation_style = str(data.get("conversation_style", "")).strip().lower()
    insights = {
        "listen": "Both people consented. The invited person selected listening as their preferred support. Consider asking whether quiet listening, without immediate advice, would feel supportive.",
        "ideas": "Both people consented. The invited person selected practical ideas as their preferred support. Consider exchanging one small idea each while leaving the final choice with its owner.",
        "space": "Both people consented. The invited person selected space and time as their preferred support. Consider agreeing on a gentle time to check in again.",
    }
    if conversation_style not in insights:
        raise ValidationError("Choose a valid conversation preference.", "conversation_style")
    insight = insights[conversation_style]
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        cursor = db.execute(
            """UPDATE referrals
               SET invitee_name = NULL, invitee_focus = NULL, invitee_state = NULL,
                   invitee_consent = 1, mutual_insight = ?, status = 'completed', completed_at = ?
               WHERE id = ?
                 AND status IN ('created', 'opened')
                 AND inviter_consent = 1
                 AND expires_at > ?
                 AND EXISTS (
                     SELECT 1 FROM consents c
                     WHERE c.user_id = referrals.inviter_user_id
                       AND c.consent_type = 'circle_sharing' AND c.granted = 1
                 )""",
            (insight, now, referral["id"], now),
        )
        if cursor.rowcount != 1:
            db.rollback()
            consumed = _load_referral(token)
            return safe_referral_view(consumed)
        _event(referral["id"], "consented_completion", {"shareable": True})
        _record_event(referral["inviter_user_id"], "circle", "Circle connection completed", "A trusted person consented and unlocked a mutual, non-sensitive insight.", referral["id"])
        db.commit()
    except Exception:
        db.rollback()
        raise
    completed = {
        **referral,
        "status": "completed",
        "invitee_consent": 1,
        "mutual_insight": insight,
        "completed_at": now,
    }
    return safe_referral_view(completed, include_insight=True)


def set_circle_consent(granted: bool) -> dict:
    """Atomically update Circle consent and revoke every active invitation."""

    user = require_user()
    db = get_db()
    revoked_ids: list[int] = []
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """INSERT INTO consents (user_id, consent_type, granted)
               VALUES (?, 'circle_sharing', ?)
               ON CONFLICT(user_id, consent_type) DO UPDATE
               SET granted = excluded.granted, recorded_at = CURRENT_TIMESTAMP""",
            (user["id"], int(granted)),
        )
        if not granted:
            revoked_ids = [
                row["id"]
                for row in db.execute(
                    """SELECT id FROM referrals
                       WHERE inviter_user_id = ? AND status NOT IN ('expired', 'revoked')""",
                    (user["id"],),
                ).fetchall()
            ]
            if revoked_ids:
                placeholders = ",".join("?" for _ in revoked_ids)
                db.execute(
                    f"UPDATE referrals SET inviter_consent = 0, status = 'revoked' WHERE id IN ({placeholders})",
                    tuple(revoked_ids),
                )
                db.executemany(
                    "INSERT INTO referral_events (referral_id, event_type, metadata_json) VALUES (?, 'revoked', '{}')",
                    [(referral_id,) for referral_id in revoked_ids],
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"granted": granted, "revoked": len(revoked_ids)}


def safe_referral_view(referral: dict, include_insight: bool = False) -> dict:
    result = {
        "token": referral["token"],
        "inviter_name": referral["inviter_name"],
        "status": referral["status"],
        "expires_at": referral["expires_at"],
        "completed": referral["status"] == "completed",
    }
    if include_insight and referral.get("inviter_consent") and referral.get("invitee_consent"):
        result["mutual_insight"] = referral.get("mutual_insight")
    return result


def latest_referral(user_id: int) -> dict | None:
    row = query_one(
        """SELECT r.*, u.display_name AS inviter_name FROM referrals r
           JOIN demo_users u ON u.id = r.inviter_user_id
           JOIN consents c ON c.user_id = r.inviter_user_id
             AND c.consent_type = 'circle_sharing' AND c.granted = 1
           WHERE r.inviter_user_id = ?
             AND r.status NOT IN ('expired', 'revoked')
             AND r.inviter_consent = 1
             AND r.expires_at > ?
           ORDER BY r.created_at DESC, r.id DESC LIMIT 1""",
        (user_id, datetime.now(timezone.utc).isoformat()),
    )
    return safe_referral_view(dict(row), include_insight=True) if row else None
