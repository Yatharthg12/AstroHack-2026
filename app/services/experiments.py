"""Reproducible Monte Carlo scenario simulator (not a business forecast)."""

from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from threading import Lock

import numpy as np
from flask import current_app, request, session

from app.db import get_db

from .journey import current_user
from .validation import ValidationError


DEFAULTS = {
    "eligible_users": 10000,
    "pulse_adoption": 0.22,
    "baseline_retention": 0.24,
    "retention_uplift": 0.10,
    "share_rate": 0.08,
    "invites_per_sharer": 1.4,
    "invite_conversion": 0.18,
    "baseline_consultation_conversion": 0.055,
    "consultation_conversion": 0.072,
    "repeat_consultation_uplift": 0.08,
    "average_consultation_revenue": 0.0,
    "trials": 10000,
    "seed": 2026,
}

BOUNDS = {
    "eligible_users": (100, 10_000_000),
    "pulse_adoption": (0.0, 1.0),
    "baseline_retention": (0.0, 1.0),
    "retention_uplift": (-0.5, 1.0),
    "share_rate": (0.0, 1.0),
    "invites_per_sharer": (0.0, 20.0),
    "invite_conversion": (0.0, 1.0),
    "baseline_consultation_conversion": (0.0, 1.0),
    "consultation_conversion": (0.0, 1.0),
    "repeat_consultation_uplift": (-0.5, 1.0),
    "average_consultation_revenue": (0.0, 1_000_000.0),
    "trials": (10000, 100000),
    "seed": (0, 2**32 - 1),
}

_experiment_hits: dict[str, deque[datetime]] = defaultdict(deque)
_experiment_guard_lock = Lock()
_active_experiments = 0


def session_owner_key(*, create: bool = True) -> str | None:
    """Return the stable random capability that owns this session's runs."""

    value = session.get("experiment_owner_key")
    if isinstance(value, str) and 32 <= len(value) <= 80:
        return value
    if not create:
        return None
    csrf_seed = session.get("csrf_token")
    value = (
        hashlib.sha256(f"orbit-experiment:{csrf_seed}".encode()).hexdigest()
        if isinstance(csrf_seed, str) and csrf_seed
        else secrets.token_urlsafe(32)
    )
    session["experiment_owner_key"] = value
    return value


@contextmanager
def experiment_request_guard():
    """Bound per-IP starts and concurrent CPU-heavy simulator work."""

    global _active_experiments
    now = datetime.now(timezone.utc)
    key = request.remote_addr or "local"
    per_minute = int(current_app.config.get("EXPERIMENT_RATE_LIMIT_PER_MINUTE", 6))
    max_concurrency = int(current_app.config.get("EXPERIMENT_MAX_CONCURRENCY", 2))
    with _experiment_guard_lock:
        queue = _experiment_hits[key]
        cutoff = now - timedelta(minutes=1)
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= per_minute:
            raise ValidationError("Too many simulator runs. Wait a minute and try again.", "rate_limit")
        if _active_experiments >= max_concurrency:
            raise ValidationError("The simulator is busy. Try again shortly.", "rate_limit")
        queue.append(now)
        _active_experiments += 1
    try:
        yield
    finally:
        with _experiment_guard_lock:
            _active_experiments -= 1


def _parse_inputs(data: dict) -> dict:
    values = DEFAULTS.copy()
    aliases = {"consultation_conversion": "consultation_conversion", "avg_revenue": "average_consultation_revenue"}
    for raw_key, raw_value in data.items():
        key = aliases.get(raw_key, raw_key)
        if key not in values or raw_value in (None, ""):
            continue
        try:
            value = int(raw_value) if key in {"eligible_users", "trials", "seed"} else float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{key.replace('_', ' ').title()} must be numeric.", key) from exc
        low, high = BOUNDS[key]
        if not low <= value <= high:
            raise ValidationError(f"{key.replace('_', ' ').title()} must be between {low:g} and {high:g}.", key)
        values[key] = value
    return values


def _uncertain_rate(rng: np.random.Generator, mean: float, trials: int, relative_sd: float = 0.12) -> np.ndarray:
    if mean <= 0:
        return np.zeros(trials)
    sd = max(0.005, min(0.15, abs(mean) * relative_sd))
    return np.clip(rng.normal(mean, sd, trials), 0, 1)


def _summary(values: np.ndarray) -> dict:
    return {
        "p05": round(float(np.percentile(values, 5)), 2),
        "median": round(float(np.median(values)), 2),
        "expected": round(float(np.mean(values)), 2),
        "p95": round(float(np.percentile(values, 95)), 2),
    }


def simulate(data: dict, persist: bool = True) -> dict:
    p = _parse_inputs(data)
    n = int(p["trials"])
    rng = np.random.default_rng(int(p["seed"]))

    eligible = np.full(n, int(p["eligible_users"]), dtype=float)
    adoption = _uncertain_rate(rng, p["pulse_adoption"], n)
    baseline_retention = _uncertain_rate(rng, p["baseline_retention"], n)
    uplift = rng.normal(p["retention_uplift"], max(0.01, abs(p["retention_uplift"]) * 0.18), n)
    scenario_retention = np.clip(baseline_retention * (1 + adoption * uplift), 0, 1)
    baseline_retained = rng.binomial(eligible.astype(int), baseline_retention)
    scenario_retained = rng.binomial(eligible.astype(int), scenario_retention)

    share = _uncertain_rate(rng, p["share_rate"], n)
    invites = np.maximum(0, rng.normal(p["invites_per_sharer"], max(0.08, p["invites_per_sharer"] * 0.12), n))
    invite_conversion = _uncertain_rate(rng, p["invite_conversion"], n)
    organic = eligible * adoption * share * invites * invite_conversion

    baseline_consult_rate = _uncertain_rate(rng, p["baseline_consultation_conversion"], n)
    scenario_consult_rate = _uncertain_rate(rng, p["consultation_conversion"], n)
    baseline_consults = rng.binomial(eligible.astype(int), baseline_consult_rate)
    scenario_base = rng.binomial((eligible + organic).astype(int), scenario_consult_rate)
    repeat_factor = np.clip(rng.normal(p["repeat_consultation_uplift"], 0.02, n), -0.5, 1)
    scenario_consults = scenario_base * (1 + repeat_factor)

    incremental_retained = scenario_retained - baseline_retained
    incremental_consults = scenario_consults - baseline_consults
    metrics = {
        "baseline_retained_users": _summary(baseline_retained),
        "scenario_retained_users": _summary(scenario_retained),
        "incremental_retained_users": _summary(incremental_retained),
        "baseline_consultations": _summary(baseline_consults),
        "scenario_consultations": _summary(scenario_consults),
        "incremental_consultations": _summary(incremental_consults),
        "incremental_organic_users": _summary(organic),
    }
    revenue_supported = p["average_consultation_revenue"] > 0
    if revenue_supported:
        metrics["incremental_revenue"] = _summary(incremental_consults * p["average_consultation_revenue"])

    drivers = {
        "Pulse adoption": adoption,
        "Retention uplift": uplift,
        "Share rate": share,
        "Invites per sharer": invites,
        "Invite conversion": invite_conversion,
        "Consultation conversion": scenario_consult_rate,
        "Repeat-consultation uplift": repeat_factor,
    }
    sensitivities = []
    outcome = incremental_retained + organic + incremental_consults
    for label, values in drivers.items():
        corr = float(np.corrcoef(values, outcome)[0, 1]) if np.std(values) and np.std(outcome) else 0.0
        sensitivities.append({"factor": label, "correlation": round(corr, 3), "absolute_influence": round(abs(corr), 3)})
    sensitivities.sort(key=lambda item: item["absolute_influence"], reverse=True)

    result = {
        "label": "Scenario estimate — not measured business impact",
        "inputs": p,
        "metrics": metrics,
        "sensitivity": sensitivities,
        "revenue_supported": revenue_supported,
        "method": "Monte Carlo with bounded normal uncertainty around editable assumptions",
    }
    if persist:
        user = current_user()
        owner_key = session_owner_key()
        db = get_db()
        db.execute(
            "DELETE FROM experiment_runs WHERE created_at < datetime('now', '-24 hours')"
        )
        db.execute(
            """DELETE FROM experiment_runs
               WHERE owner_key = ? AND id NOT IN (
                   SELECT id FROM experiment_runs WHERE owner_key = ?
                   ORDER BY id DESC LIMIT 24
               )""",
            (owner_key, owner_key),
        )
        cursor = db.execute(
            """INSERT INTO experiment_runs (user_id, owner_key, inputs_json, results_json)
               VALUES (?, ?, ?, ?)""",
            (
                user["id"] if user else None,
                owner_key,
                json.dumps(p),
                json.dumps(result),
            ),
        )
        db.commit()
        result["run_id"] = cursor.lastrowid
    return result
