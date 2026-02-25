from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from flask import Flask, url_for

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

    app.config["DB_NAME"] = (os.getenv("DB_PATH") or "productivity.db").strip() or "productivity.db"
    app.config["LOCAL_AUTH_BYPASS"] = LOCAL_AUTH_BYPASS
    app.config["LOCAL_AUTH_USER_ID"] = LOCAL_AUTH_USER_ID

    if config_overrides:
        app.config.update(config_overrides)

    init_db(app.config["DB_NAME"])

    app.jinja_env.filters["human_hours"] = human_hours

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
