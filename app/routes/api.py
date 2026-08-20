"""JSON APIs powering the interactive prototype."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, jsonify, request

from app.db import get_db, query_one
from app.services.consultations import (
    approve_brief,
    complete_followup_action,
    create_booking,
    create_brief,
    create_followup,
    revoke_brief,
    set_booking_helpfulness,
)
from app.services.experiments import experiment_request_guard, session_owner_key, simulate
from app.services.journey import (
    ValidationError,
    complete_action,
    create_checkin,
    current_user,
    reset_current_user,
    set_checkin_feedback,
)
from app.services.validation import bool_value, text_value
from app.services.referrals import complete_referral, create_referral, set_circle_consent


api_bp = Blueprint("api", __name__)


def _payload() -> dict:
    if request.is_json:
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValidationError("Request body must be a JSON object.", "body")
        return value
    value = request.form.to_dict()
    for key in ("actions", "questions", "checkin_ids"):
        values = request.form.getlist(key)
        if len(values) > 1:
            value[key] = values
    return value


def _ok(data=None, status: int = 200):
    return jsonify({"ok": True, "data": data if data is not None else {}}), status


def _error(error: ValidationError, status: int = 400):
    return jsonify({"ok": False, "error": {"code": "validation_error", "message": str(error), "field": error.field}}), status


@api_bp.errorhandler(ValidationError)
def handle_validation(error):
    status = 401 if error.field == "user" else 429 if error.field == "rate_limit" else 400
    return _error(error, status)


@api_bp.get("/health")
def health():
    from app.analytics.dashboard import model_catalog

    db_ok = query_one("SELECT 1 AS ok")["ok"] == 1
    model_dir = Path(current_app.config["MODEL_DIR"])
    catalog = model_catalog(model_dir)
    model_tasks = {
        task: {
            "available": details["available"],
            "version": details["version"],
        }
        for task, details in catalog["tasks"].items()
    }
    models_ok = bool(catalog["available"])
    return _ok({
        "status": "healthy" if db_ok and models_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "model_integrity": "ok" if models_ok else "degraded",
        "models_available": sorted(
            task for task, details in model_tasks.items() if details["available"]
        ),
        "models": model_tasks,
        "demo_mode": True,
        "version": "1.0.0",
    })


@api_bp.post("/check-ins")
def checkins_create():
    return _ok(create_checkin(_payload()), 201)


@api_bp.post("/check-ins/<int:checkin_id>/feedback")
def checkins_feedback(checkin_id: int):
    data = _payload()
    relevant = data.get("relevant")
    if isinstance(relevant, bool):
        relevant = "yes" if relevant else "no"
    set_checkin_feedback(checkin_id, str(relevant).lower())
    return _ok({"checkin_id": checkin_id, "relevant": relevant})


@api_bp.post("/briefs")
def briefs_create():
    return _ok(create_brief(_payload()), 201)


@api_bp.post("/briefs/<int:brief_id>/approve")
def briefs_approve(brief_id: int):
    if not bool_value(_payload(), "approved"):
        raise ValidationError("Confirm approval of the reviewed brief.", "approved")
    return _ok(approve_brief(brief_id))


@api_bp.post("/briefs/<int:brief_id>/revoke")
def briefs_revoke(brief_id: int):
    if not bool_value(_payload(), "confirm"):
        raise ValidationError("Confirm withdrawal of console access.", "confirm")
    return _ok(revoke_brief(brief_id))


@api_bp.post("/bookings")
def bookings_create():
    return _ok(create_booking(_payload()), 201)


@api_bp.post("/follow-up")
def followup_create():
    return _ok(create_followup(_payload()), 201)


@api_bp.post("/consents/circle")
def circle_consent():
    data = _payload()
    if "granted" not in data:
        raise ValidationError("Choose whether Circle consent is granted or withdrawn.", "granted")
    raw_granted = data["granted"]
    if not isinstance(raw_granted, bool) and str(raw_granted).strip().lower() not in {
        "0", "1", "false", "true", "no", "yes", "off", "on",
    }:
        raise ValidationError("Circle consent must be an explicit true or false value.", "granted")
    granted = bool_value({"granted": raw_granted}, "granted")
    return _ok(set_circle_consent(granted))


@api_bp.post("/referrals")
def referrals_create():
    return _ok(create_referral(), 201)


@api_bp.post("/referrals/<token>/complete")
def referrals_complete(token: str):
    return _ok(complete_referral(token, _payload()))


@api_bp.post("/journey/actions/<int:checkin_id>/complete")
def journey_action_complete(checkin_id: int):
    changed = complete_action(checkin_id)
    return _ok({"checkin_id": checkin_id, "completed": True, "changed": changed})


@api_bp.post("/journey/follow-up-actions/<int:action_id>/complete")
def journey_followup_action_complete(action_id: int):
    changed = complete_followup_action(action_id)
    return _ok({"action_id": action_id, "completed": True, "changed": changed})


@api_bp.post("/reset")
def reset():
    if not bool_value(_payload(), "confirm"):
        raise ValidationError("Confirm deletion before resetting the demo journey.", "confirm")
    reset_current_user()
    return _ok({"reset": True})


@api_bp.post("/feedback")
def feedback_create():
    user = current_user()
    if not user:
        raise ValidationError("Start the Orbit demo before continuing.", "user")
    data = _payload()
    feedback_type = text_value(data, "type", maximum=40)
    value = text_value(data, "value", maximum=80)
    allowed = {
        "consultation": {"helpful", "somewhat", "not_yet"},
        "experience": {"clear", "unclear", "useful", "not_useful"},
    }
    if feedback_type not in allowed or value not in allowed[feedback_type]:
        raise ValidationError("Choose a valid feedback response.", "value")
    if feedback_type == "consultation":
        try:
            booking_id = int(data.get("booking_id"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Choose the sample booking this feedback describes.", "booking_id"
            ) from exc
        value = set_booking_helpfulness(booking_id, value)
        row = query_one(
            """SELECT id FROM feedback
               WHERE user_id = ? AND feedback_type = 'consultation' AND related_id = ?""",
            (user["id"], booking_id),
        )
        return _ok({
            "id": row["id"],
            "type": feedback_type,
            "value": value,
            "related_id": booking_id,
        }, 201)
    cursor = get_db().execute(
        "INSERT INTO feedback (user_id, feedback_type, value) VALUES (?, ?, ?)",
        (user["id"], feedback_type, value),
    )
    get_db().commit()
    return _ok({
        "id": cursor.lastrowid,
        "type": feedback_type,
        "value": value,
        "related_id": None,
    }, 201)


@api_bp.get("/analytics")
def analytics():
    from app.services.growth import growth_snapshot

    return _ok(growth_snapshot(
        period=request.args.get("period", "90d"),
        segment=request.args.get("segment", "all"),
        focus=request.args.get("focus", "all"),
    ))


@api_bp.post("/experiments")
def experiments_create():
    with experiment_request_guard():
        result = simulate(_payload(), persist=True)
    return _ok(result, 201)


@api_bp.get("/experiments/<int:run_id>.<fmt>")
def experiments_download(run_id: int, fmt: str):
    owner_key = session_owner_key(create=False)
    if owner_key is None:
        abort(404)
    row = query_one(
        """SELECT inputs_json, results_json FROM experiment_runs
           WHERE id = ? AND owner_key = ?""",
        (run_id, owner_key),
    )
    if not row:
        abort(404)
    result = json.loads(row["results_json"])
    if fmt == "json":
        return Response(json.dumps(result, indent=2), mimetype="application/json", headers={"Content-Disposition": f"attachment; filename=orbit-scenario-{run_id}.json", "Cache-Control": "private, no-store"})
    if fmt == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow([
            "section", "name", "value", "p05", "median", "expected", "p95",
            "correlation", "absolute_influence",
        ])
        for name, value in result["inputs"].items():
            writer.writerow(["assumption", name, value, "", "", "", "", "", ""])
        for metric, values in result["metrics"].items():
            writer.writerow([
                "result", metric, "", values["p05"], values["median"],
                values["expected"], values["p95"], "", "",
            ])
        for item in result["sensitivity"]:
            writer.writerow([
                "sensitivity", item["factor"], "", "", "", "", "",
                item["correlation"], item["absolute_influence"],
            ])
        return Response(stream.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=orbit-scenario-{run_id}.csv", "Cache-Control": "private, no-store"})
    raise ValidationError("Download format must be json or csv.", "format")
