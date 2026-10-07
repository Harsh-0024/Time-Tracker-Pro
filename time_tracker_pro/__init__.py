from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, url_for

from .core.time_utils import human_hours
from .db import init_db
from .repositories.app_settings import get_app_setting


_ENV_NAME = (os.getenv("FLASK_ENV") or os.getenv("ENV") or "").strip().lower()
_IS_LOCAL_ENV = _ENV_NAME in {"dev", "development", "local"}
LOCAL_AUTH_BYPASS = _IS_LOCAL_ENV and (os.getenv("LOCAL_AUTH_BYPASS") == "1")
_raw_auth_user_id = (os.getenv("LOCAL_AUTH_USER_ID") or "").strip()
LOCAL_AUTH_USER_ID: Optional[int] = int(_raw_auth_user_id) if _raw_auth_user_id.isdigit() else None


def create_app(config_overrides: Optional[Dict[str, Any]] = None) -> Flask:
    load_dotenv()

    root = Path(__file__).resolve().parents[1]
    template_folder = str(root / "templates")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    static_folder = str(root / "static")
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

    secret = os.getenv("SECRET_KEY")
    if not secret or secret == "dev-secret-change-me":
        env = (os.getenv("FLASK_ENV") or os.getenv("ENV") or "").strip().lower()
        allow_insecure = env in {"dev", "development"} or os.getenv("ALLOW_INSECURE_SECRET") == "1"
        if not allow_insecure:
            raise RuntimeError(
                "SECRET_KEY is missing or insecure. Set a strong random SECRET_KEY in the environment before running in production."
            )
        secret = secret or "dev-secret-change-me"
    app.secret_key = secret
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if os.getenv("SESSION_COOKIE_SECURE"):
        app.config["SESSION_COOKIE_SECURE"] = True
    app.permanent_session_lifetime = timedelta(days=int(os.getenv("SESSION_LIFETIME_DAYS", "30")))

    # Largest legitimate body is the 5MB icon upload / a CSV import; reject anything bigger up front.
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH_MB", "16")) * 1024 * 1024
    app.config["DB_NAME"] = (os.getenv("DB_PATH") or "productivity.db").strip() or "productivity.db"
    app.config["LOCAL_AUTH_BYPASS"] = LOCAL_AUTH_BYPASS
    app.config["LOCAL_AUTH_USER_ID"] = LOCAL_AUTH_USER_ID

    if config_overrides:
        app.config.update(config_overrides)

    init_db(app.config["DB_NAME"])

    app.jinja_env.filters["human_hours"] = human_hours

    def _short_date(value: Any) -> str:
        """ISO timestamp -> 'Jan 18, 2026' (blank if missing/unparseable)."""
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)[:10]
        return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"

    app.jinja_env.filters["short_date"] = _short_date

    from .web.admin import bp as admin_bp
    from .web.api import bp as api_bp
    from .web.auth import bp as auth_bp
    from .web.main import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(main_bp)

    def _icon_version() -> str:
        try:
            return get_app_setting(app.config["DB_NAME"], "app_icon_version") or "1"
        except Exception:
            return "1"

    @app.before_request
    def _reject_oversized_body():
        # Werkzeug only enforces MAX_CONTENT_LENGTH when the body is read, and some routes read it
        # inside a broad try/except (turning the 413 into a 500), so check the declared length first.
        limit = app.config.get("MAX_CONTENT_LENGTH")
        if limit and request.content_length is not None and request.content_length > limit:
            abort(413)

    @app.after_request
    def _security_headers(response):
        # Cheap hardening that doesn't interfere with the inline scripts/CDN assets.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    _ERROR_COPY = {
        403: ("Not allowed", "You don't have access to this page."),
        404: ("Page not found", "That page doesn't exist or has moved."),
        405: ("Not allowed", "That action isn't available here."),
        413: ("Upload too large", "That file or request is too large to process."),
        500: ("Something went wrong", "An unexpected error occurred. Please try again in a moment."),
    }

    def _error_response(status: int):
        title, message = _ERROR_COPY.get(status, ("Error", "Something went wrong."))
        # API callers (fetch) expect JSON, not an HTML page.
        if request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json":
            return jsonify({"error": message}), status
        try:
            return render_template("error.html", status=status, title=title, message=message), status
        except Exception:  # never let the error page itself fail
            return f"{status} {title}", status

    for _status in (403, 404, 405, 413, 500):
        app.register_error_handler(_status, lambda exc, _s=_status: _error_response(_s))

    @app.context_processor
    def inject_pwa_assets():
        version = _icon_version()
        return {
            "pwa_manifest_url": url_for("main.manifest"),
            "pwa_icon_url": url_for("main.app_icon", v=version),
            "pwa_icon_version": version,
        }

    enable_weekly = (os.getenv("ENABLE_WEEKLY_MAINTENANCE_REWRITE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    if enable_weekly and not app.config.get("_WEEKLY_MAINTENANCE_THREAD_STARTED"):
        should_start = (os.environ.get("WERKZEUG_RUN_MAIN") == "true") or not app.debug
        if should_start:
            from .repositories.sheety_outbox import claim_weekly_run, sunday_week_key
            from .repositories.users import list_user_ids
            from .services.sync import sync_cloud_data

            poll_seconds = int(os.getenv("WEEKLY_MAINTENANCE_POLL_SECONDS", "3600"))

            def _weekly_maintenance_loop() -> None:
                while True:
                    try:
                        if os.getenv("DISABLE_CLOUD_SYNC"):
                            time.sleep(max(60, poll_seconds))
                            continue
                        db_name = app.config.get("DB_NAME")
                        if not db_name:
                            time.sleep(max(60, poll_seconds))
                            continue
                        now = datetime.now(timezone.utc)
                        week_key = sunday_week_key(now)
                        for uid in list_user_ids(str(db_name)):
                            try:
                                if claim_weekly_run(str(db_name), int(uid), str(week_key)):
                                    sync_cloud_data(str(db_name), int(uid), force=True)
                            except Exception as exc:
                                logging.getLogger(__name__).warning(
                                    "Weekly maintenance sync failed user_id=%s error=%s",
                                    int(uid),
                                    exc,
                                )
                    except Exception as exc:
                        logging.getLogger(__name__).warning("Weekly maintenance loop error=%s", exc)
                    time.sleep(max(60, poll_seconds))

            t = threading.Thread(target=_weekly_maintenance_loop, daemon=True, name="weekly-maintenance")
            t.start()
            app.config["_WEEKLY_MAINTENANCE_THREAD_STARTED"] = True

    return app
