"""SQLite access and idempotent schema initialisation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS demo_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    journey_owner_key TEXT UNIQUE,
    display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 60),
    birth_date TEXT NOT NULL,
    birth_time TEXT,
    birth_city TEXT,
    focus_area TEXT NOT NULL,
    communication_preference TEXT NOT NULL,
    sun_sign TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    consent_type TEXT NOT NULL,
    granted INTEGER NOT NULL CHECK(granted IN (0, 1)),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, consent_type)
);

CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    emotional_state TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 5),
    concern TEXT NOT NULL,
    reflection TEXT NOT NULL,
    micro_action TEXT NOT NULL,
    reason TEXT NOT NULL,
    relevance TEXT,
    action_completed INTEGER NOT NULL DEFAULT 0 CHECK(action_completed IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS consultation_briefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    context TEXT NOT NULL,
    desired_outcome TEXT NOT NULL,
    questions_json TEXT NOT NULL,
    preferred_language TEXT NOT NULL,
    preferred_mode TEXT NOT NULL,
    urgency TEXT NOT NULL,
    include_checkins INTEGER NOT NULL DEFAULT 0 CHECK(include_checkins IN (0, 1)),
    speciality TEXT NOT NULL,
    explanation TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0 CHECK(approved IN (0, 1)),
    revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brief_checkin_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_id INTEGER NOT NULL REFERENCES consultation_briefs(id) ON DELETE CASCADE,
    checkin_id INTEGER NOT NULL,
    emotional_state TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK(confidence BETWEEN 1 AND 5),
    concern TEXT NOT NULL,
    checkin_created_at TEXT NOT NULL,
    snapshotted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(brief_id, checkin_id)
);

CREATE TABLE IF NOT EXISTS demo_bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    brief_id INTEGER NOT NULL REFERENCES consultation_briefs(id) ON DELETE CASCADE,
    astrologer_name TEXT NOT NULL,
    mode TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    sample_price REAL NOT NULL CHECK(sample_price >= 0),
    status TEXT NOT NULL DEFAULT 'demo_confirmed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    booking_id INTEGER NOT NULL REFERENCES demo_bookings(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    scheduled_checkin TEXT NOT NULL,
    helpfulness INTEGER CHECK(helpfulness BETWEEN 1 AND 5),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS followup_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    followup_id INTEGER NOT NULL REFERENCES followups(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    action_text TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0, 1)),
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL UNIQUE,
    inviter_user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    inviter_consent INTEGER NOT NULL CHECK(inviter_consent IN (0, 1)),
    invitee_name TEXT,
    invitee_focus TEXT,
    invitee_state TEXT,
    invitee_consent INTEGER NOT NULL DEFAULT 0 CHECK(invitee_consent IN (0, 1)),
    mutual_insight TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS referral_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referral_id INTEGER NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journey_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES demo_users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    related_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES demo_users(id) ON DELETE CASCADE,
    feedback_type TEXT NOT NULL,
    value TEXT NOT NULL,
    related_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES demo_users(id) ON DELETE SET NULL,
    owner_key TEXT,
    inputs_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_checkins_user_created ON checkins(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_brief_snapshots_brief ON brief_checkin_snapshots(brief_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_approved_brief_per_user
ON consultation_briefs(user_id) WHERE approved = 1;
CREATE INDEX IF NOT EXISTS idx_followup_actions_user ON followup_actions(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_journey_user_created ON journey_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_referrals_token ON referrals(token);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        database = Path(current_app.config["DATABASE"])
        database.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA)
    experiment_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(experiment_runs)").fetchall()
    }
    if "owner_key" not in experiment_columns:
        db.execute("ALTER TABLE experiment_runs ADD COLUMN owner_key TEXT")
    user_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(demo_users)").fetchall()
    }
    if "journey_owner_key" not in user_columns:
        db.execute("ALTER TABLE demo_users ADD COLUMN journey_owner_key TEXT")
    brief_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(consultation_briefs)").fetchall()
    }
    if "revoked" not in brief_columns:
        db.execute(
            "ALTER TABLE consultation_briefs ADD COLUMN revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0, 1))"
        )
    feedback_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(feedback)").fetchall()
    }
    if "related_id" not in feedback_columns:
        db.execute("ALTER TABLE feedback ADD COLUMN related_id INTEGER")
    followup_action_columns = {
        row["name"] for row in db.execute("PRAGMA table_info(followup_actions)").fetchall()
    }
    if "active" not in followup_action_columns:
        db.execute(
            "ALTER TABLE followup_actions ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))"
        )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_experiment_runs_owner ON experiment_runs(owner_key)"
    )
    db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_demo_users_journey_owner
           ON demo_users(journey_owner_key) WHERE journey_owner_key IS NOT NULL"""
    )
    db.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_related
           ON feedback(user_id, feedback_type, related_id) WHERE related_id IS NOT NULL"""
    )
    db.commit()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()
