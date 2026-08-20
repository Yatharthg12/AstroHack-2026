"""AstroLive Orbit Flask application factory."""

from __future__ import annotations

import logging
import re
import secrets
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session

from .config import Config
from .db import close_db, init_db


_TOKEN_PATH = re.compile(r"(/(?:api/referrals|circle)/)[A-Za-z0-9_-]{32,80}")
class _ReferralTokenLogFilter(logging.Filter):
    """Prevent bearer-style referral tokens from appearing in app access logs."""

    @staticmethod
    def _clean(value):
        return _TOKEN_PATH.sub(r"\1[redacted]", value) if isinstance(value, str) else value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._clean(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(self._clean(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: self._clean(value) for key, value in record.args.items()}
        return True


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    if app.config.get("SECRET_KEY_IS_FALLBACK"):
        app.logger.warning(
            "ORBIT_SECRET_KEY is not configured; using an ephemeral development key. "
            "Set it before production deployment."
        )

    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()

    from .routes.api import api_bp
    from .routes.web import web_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.context_processor
    def inject_globals() -> dict:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(24)
        if "journey_owner_key" not in session:
            session["journey_owner_key"] = secrets.token_urlsafe(32)
        return {
            "csrf_token": session["csrf_token"],
            "product_name": "AstroLive Orbit",
            "is_demo": True,
        }

    @app.before_request
    def validate_csrf():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        expected = session.get("csrf_token")
        supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            message = "Refresh the page and try again."
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": {"code": "csrf_failed", "message": message}}), 403
            return render_template(
                "onboarding.html",
                user=None,
                form=request.form.to_dict(),
                errors={"csrf_token": message},
                error=message,
            ), 403
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; base-uri 'self'; form-action 'self'",
        )
        if not app.debug:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/circle/") or request.path.startswith("/api/referrals/"):
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        # Every rendered page receives per-session CSRF and owner state from
        # the context processor, including otherwise-public pages and errors.
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.errorhandler(405)
    def method_not_allowed(error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": {"code": "method_not_allowed", "message": "Method not allowed."}}), 405
        return error

    @app.errorhandler(413)
    def request_too_large(error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": {"code": "request_too_large", "message": "Request body is too large."}}), 413
        return error

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": {"code": "not_found", "message": "Resource not found."}}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("Unhandled application error: %s", error)
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": {"code": "server_error", "message": "Something went wrong."}}), 500
        return render_template("errors/500.html"), 500

    token_filter = _ReferralTokenLogFilter()
    for logger_name in ("werkzeug", "gunicorn.access"):
        target_logger = logging.getLogger(logger_name)
        target_logger.addFilter(token_filter)
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    return app


__all__ = ["create_app"]
