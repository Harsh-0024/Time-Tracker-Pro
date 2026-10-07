from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from flask import Blueprint, current_app, make_response, redirect, render_template, request, send_file, session, url_for

from ..core.admins import is_admin_email
from ..core.dates import get_period_range, parse_period_param
from ..core.rows import display_name, row_value
from ..core.tags import primary_special_tag
from ..repositories.app_settings import get_app_setting, upsert_app_setting
from ..repositories.goals import get_user_goals, parse_goal_hours, upsert_user_goals
from ..repositories.logs import fetch_local_data, get_first_log_date
from ..repositories.settings import get_user_settings, upsert_user_settings
from ..repositories.users import get_user_by_id, get_user_count
from ..services.insights import (
    build_daily_breakdown,
    build_day_timeline,
    build_goal_progress,
    build_insights,
    goal_streaks,
    task_name_suggestions,
)
from ..core.numbers import round_half_up
from ..services.matrix import get_matrix_stats
from ..services.sync import get_last_sync_stats, sync_cloud_data, sync_status_payload
from .decorators import admin_required, login_required
from .utils import get_current_user_id, request_date_param


bp = Blueprint("main", __name__)

logger = logging.getLogger(__name__)

_DEFAULT_ICON_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIW2P8z8BQDwAF/wJ+q9QKJwAAAABJRU5ErkJggg=="
)


def _icon_storage_path() -> Path:
    icon_dir = Path(current_app.instance_path) / "pwa"
    icon_dir.mkdir(parents=True, exist_ok=True)
    return icon_dir / "app-icon.png"


def _is_admin(user_row) -> bool:
    return bool(
        user_row
        and (
            (row_value(user_row, "role") or "user") == "admin"
            or is_admin_email(row_value(user_row, "email"))
        )
    )


@bp.route("/settings", methods=["GET", "POST"], endpoint="settings")
@login_required
def settings():
    from ..repositories.sheety_accounts import get_user_api_accounts
    
    db_name = current_app.config["DB_NAME"]
    user_id = int(get_current_user_id() or 0)
    current = get_user_settings(db_name, user_id)

    if request.method == "POST":
        from .api import _api_url_error

        sheety_endpoint = request.form.get("sheety_endpoint")
        sheety_token = request.form.get("sheety_token")
        if (sheety_endpoint or "").strip() and _api_url_error(sheety_endpoint.strip()):
            return redirect(url_for("main.settings"))
        upsert_user_settings(db_name, user_id, sheety_endpoint, sheety_token)
        return redirect(url_for("main.dashboard"))

    user_row = get_user_by_id(db_name, user_id)
    is_admin = _is_admin(user_row)

    allow_env_fallback = get_user_count(db_name) <= 1
    env_sheety = (os.getenv("SHEETY_ENDPOINT") or "").strip() if allow_env_fallback else ""

    current_user = {
        "id": user_id,
        "display_name": display_name(user_row),
        "role": (row_value(user_row, "role") if user_row else "user"),
    }
    profile_info = {
        "username": row_value(user_row, "username") if user_row else "",
        "email": row_value(user_row, "email") if user_row else "",
        "user_id": row_value(user_row, "user_id") if user_row else "",
        "name": row_value(user_row, "name") if user_row else "",
    }
    
    # Get API accounts for this user
    api_accounts = get_user_api_accounts(db_name, user_id)

    return render_template(
        "settings.html",
        settings=current,
        current_user=current_user,
        profile_info=profile_info,
        env_sheety=env_sheety,
        is_admin=is_admin,
        api_accounts=api_accounts,
        icon_error=request.args.get("icon_error"),
        icon_success=request.args.get("icon_success"),
        profile_error=session.pop("profile_error", None),
        profile_success=session.pop("profile_success", None),
        pending_email=session.get("pending_email_new"),
        goals=get_user_goals(db_name, user_id),
        goals_error=session.pop("goals_error", None),
        goals_form=session.pop("goals_form", None),
        goals_success=session.pop("goals_success", None),
    )


@bp.route("/settings/goals", methods=["POST"], endpoint="update_goals")
@login_required
def update_goals():
    db_name = current_app.config["DB_NAME"]
    user_id = int(get_current_user_id() or 0)
    try:
        growth = parse_goal_hours(request.form.get("growth_hours"))
        waste = parse_goal_hours(request.form.get("waste_limit_hours"))
    except ValueError:
        session["goals_error"] = "Goals must be numbers of hours between 0 and 24."
        # Re-show what was typed so it can be corrected rather than retyped.
        session["goals_form"] = {
            "growth_hours": (request.form.get("growth_hours") or "")[:20],
            "waste_limit_hours": (request.form.get("waste_limit_hours") or "")[:20],
        }
        return redirect(url_for("main.settings") + "#goals-settings")
    upsert_user_goals(db_name, user_id, growth, waste)
    session["goals_success"] = "Goals saved." if (growth is not None or waste is not None) else "Goals cleared."
    return redirect(url_for("main.settings") + "#goals-settings")


@bp.route("/admin/app-icon", methods=["POST"], endpoint="update_app_icon")
@admin_required
def update_app_icon():
    db_name = current_app.config["DB_NAME"]
    file = request.files.get("icon")
    if not file or not file.filename:
        return redirect(url_for("admin.admin_users", error="Please choose a PNG icon to upload."))
    if file.mimetype not in {"image/png", "image/x-png"}:
        return redirect(url_for("admin.admin_users", error="Icon must be a PNG file."))
    data = file.read()
    if not data:
        return redirect(url_for("admin.admin_users", error="Uploaded icon file was empty."))
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        # The mimetype comes from the browser; check the bytes (a renamed JPEG breaks PWA installs).
        return redirect(url_for("admin.admin_users", error="Icon must be a PNG file."))
    if len(data) > 5 * 1024 * 1024:
        return redirect(url_for("admin.admin_users", error="Icon is too large (max 5MB)."))
    icon_path = _icon_storage_path()
    icon_path.write_bytes(data)
    upsert_app_setting(db_name, "app_icon_version", str(int(time.time())))
    return redirect(url_for("admin.admin_users", success="App icon updated. Re-add the app to refresh."))


_MATRIX_KEYS = ("q1", "q2", "q3", "q4", "important", "not_important", "urgent", "not_urgent")
_DELTA_LABELS = {"day": "vs prev day", "week": "vs prev week", "month": "vs prev month"}


def _logged_coverage(total_hours: float, start_date, end_date, today=None) -> float:
    """Logged hours as a % of the 24h days that have started in the period."""
    today = today or datetime.now().date()
    last_day = min(end_date, today)
    elapsed_days = (last_day - start_date).days + 1
    if elapsed_days <= 0:
        # A future period: compare against its full length so the number stays meaningful.
        elapsed_days = (end_date - start_date).days + 1
    expected = max(1, elapsed_days) * 24.0
    return round_half_up(min(100.0, total_hours / expected * 100.0), 1)


def _previous_period_range(selected_date, period: str):
    if period == "week":
        return get_period_range(selected_date - timedelta(days=7), "week")
    if period == "month":
        return get_period_range(selected_date.replace(day=1) - timedelta(days=1), "month")
    return get_period_range(selected_date - timedelta(days=1), "day")


def _matrix_share_deltas(df: pd.DataFrame, matrix: Dict[str, Any], selected_date, period: str) -> Dict[str, float]:
    """Change in each quadrant's share of logged time (percentage points) vs the
    previous period. Shares, not hours, so a half-logged today compares fairly
    with a complete yesterday. Empty when either period has no data."""
    if df.empty or not matrix.get("total_hours"):
        return {}
    prev_start, prev_end = _previous_period_range(selected_date, period)
    prev_df = df[(df["date"] >= prev_start) & (df["date"] <= prev_end)]
    if prev_df.empty:
        return {}
    prev = get_matrix_stats(prev_df)
    if not prev.get("total_hours"):
        return {}
    return {key: round_half_up(float(matrix[key]["pct"]) - float(prev[key]["pct"]), 1) for key in _MATRIX_KEYS}


@bp.route("/", endpoint="dashboard")
@login_required
def dashboard():
    db_name = current_app.config["DB_NAME"]
    user_id = int(get_current_user_id() or 0)

    sync_cloud_data(db_name, user_id)
    sync_stats = get_last_sync_stats(user_id)

    raw_period = request.args.get("period", "day")
    period = parse_period_param(raw_period)
    selected_date = request_date_param("date")

    df = fetch_local_data(db_name, user_id)
    if df.empty:
        try:
            sync_cloud_data(db_name, user_id, force=True)
            sync_stats = get_last_sync_stats(user_id)
            df = fetch_local_data(db_name, user_id)
        except Exception as exc:
            logger.warning(
                "Dashboard sync fallback failed user_id=%s error=%s",
                int(user_id),
                exc,
            )

    start_date, end_date = get_period_range(selected_date, period)
    period_df = df[(df["date"] >= start_date) & (df["date"] <= end_date)] if not df.empty else pd.DataFrame()
    avg_start_date = start_date
    avg_end_date = end_date
    if not period_df.empty:
        try:
            parsed_dates = pd.to_datetime(period_df["date"])
            first_date = parsed_dates.min()
            last_date = parsed_dates.max()
            if not pd.isna(first_date):
                first_date = first_date.date()
            if not pd.isna(last_date):
                last_date = last_date.date()
        except Exception:
            first_date = None
            last_date = None
        if first_date and first_date > avg_start_date:
            avg_start_date = first_date
        if last_date and last_date < avg_end_date:
            avg_end_date = last_date
    if avg_end_date < avg_start_date:
        avg_end_date = avg_start_date

    matrix = get_matrix_stats(period_df)
    matrix_deltas = _matrix_share_deltas(df, matrix, selected_date, period)
    insights = build_insights(
        df, period_df, period, start_date, end_date,
        previous=_previous_period_range(selected_date, period) if period != "day" else None,
    )
    day_timeline = build_day_timeline(df, selected_date) if period == "day" else None
    daily_breakdown = build_daily_breakdown(period_df, start_date, end_date) if period != "day" and not df.empty else None
    logged_coverage = _logged_coverage(float(matrix.get("total_hours") or 0.0), start_date, end_date)
    goals = get_user_goals(db_name, user_id)
    onboarding = None
    if df.empty:
        try:
            sheet_connected = bool(sync_status_payload(db_name, user_id).get("sheety_configured"))
        except Exception:
            sheet_connected = False
        onboarding = {"sheet_connected": sheet_connected}
    empty_period = None
    if not df.empty and period_df.empty:
        earlier = df[df["date"] < start_date]["date"]
        later = df[df["date"] > end_date]["date"]
        empty_period = {
            "previous": earlier.max() if not earlier.empty else None,
            "next": later.min() if not later.empty else None,
        }
    goal_progress = build_goal_progress(period_df, period, start_date, end_date, goals)
    if goal_progress is not None and period == "day":
        goal_progress["streaks"] = goal_streaks(df, selected_date, goals)
    task_count = int(len(period_df)) if not period_df.empty else 0

    idx = (selected_date.weekday() + 1) % 7
    start_of_week = selected_date - timedelta(days=idx)
    week_days: List[Dict[str, Any]] = []
    today = datetime.now().date()
    for i in range(7):
        day = start_of_week + timedelta(days=i)
        day_data = df[df["date"] == day] if not df.empty else pd.DataFrame()
        day_hours = round_half_up(day_data["duration"].sum() / 60.0, 1) if not day_data.empty else 0.0
        week_days.append(
            {
                "date_obj": day,
                "day_name": day.strftime("%a")[0],
                "day_num": day.day,
                "full_str": day.strftime("%Y-%m-%d"),
                "hours": day_hours,
                "is_selected": day == selected_date,
                "is_today": day == today,
            }
        )

    week_total = sum(day["hours"] for day in week_days)

    tag_labels: List[str] = []
    tag_data: List[float] = []
    tag_pct: List[float] = []
    if not period_df.empty:
        tag_df = period_df.copy()
        if "primary_tag" not in tag_df.columns:
            tag_df["primary_tag"] = tag_df["tag"].apply(primary_special_tag)
        tag_counts = tag_df.groupby("primary_tag")["duration"].sum().sort_values(ascending=False)
        tag_labels = list(tag_counts.index)
        tag_data = [round_half_up(float(x) / 60.0, 1) for x in tag_counts.values]
        # Shares from raw minutes: rounding each tag's hours first skews them
        # (4.5h of 10.25h read 43.3% here vs 43.9% on the quadrant card).
        tag_total = float(tag_counts.sum())
        tag_pct = [round_half_up(float(x) * 100.0 / tag_total, 1) if tag_total else 0.0 for x in tag_counts.values]

    if period == "day":
        period_label = selected_date.strftime("%B %Y")
    elif period == "week":
        week_end = start_of_week + timedelta(days=6)
        if start_of_week.year != week_end.year:
            period_label = f"{start_of_week.strftime('%b')} {start_of_week.day}, {start_of_week.year} – {week_end.strftime('%b')} {week_end.day}, {week_end.year}"
        elif start_of_week.month == week_end.month:
            period_label = f"{start_of_week.strftime('%b')} {start_of_week.day} – {week_end.day}, {week_end.year}"
        else:
            period_label = f"{start_of_week.strftime('%b')} {start_of_week.day} – {week_end.strftime('%b')} {week_end.day}, {week_end.year}"
    else:
        period_label = selected_date.strftime("%B %Y")

    user_row = get_user_by_id(db_name, user_id)
    is_admin = _is_admin(user_row)
    current_user = {
        "id": user_id,
        "display_name": display_name(user_row),
        "role": (row_value(user_row, "role") if user_row else "user"),
        "is_admin": is_admin,
    }

    resp = make_response(
        render_template(
            "dashboard.html",
            matrix=matrix,
            tags={"labels": tag_labels, "data": tag_data, "pct": tag_pct},
            task_count=task_count,
            week_days=week_days,
            week_total=round_half_up(week_total, 1),
            current_month=period_label,
            selected_date=selected_date,
            period=period,
            start_date=start_date,
            end_date=end_date,
            current_user=current_user,
            is_admin=is_admin,
            avg_start_date=avg_start_date,
            avg_end_date=avg_end_date,
            sync_stats=sync_stats or {},
            matrix_deltas=matrix_deltas,
            insights=insights,
            task_suggestions=task_name_suggestions(df),
            day_timeline=day_timeline,
            daily_breakdown=daily_breakdown,
            logged_coverage=logged_coverage,
            goal_progress=goal_progress,
            onboarding=onboarding,
            empty_period=empty_period,
            delta_label=_DELTA_LABELS.get(period, "vs previous"),
            is_today=(period == "day" and selected_date == datetime.now().date()),
        )
    )
    return resp


@bp.route("/manifest.webmanifest", endpoint="manifest")
def manifest():
    db_name = current_app.config["DB_NAME"]
    version = get_app_setting(db_name, "app_icon_version") or "1"
    icon_url = url_for("main.app_icon", v=version)
    payload = {
        "name": "Time Tracker Pro",
        "short_name": "Time Tracker",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#F7F1E6",
        "theme_color": "#F7CF6B",
        "icons": [
            {
                "src": icon_url,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            }
        ],
        # Long-press / right-click menu on the installed app's icon.
        "shortcuts": [
            {"name": "Add task", "short_name": "Add", "url": "/#add-task"},
            {"name": "This week", "short_name": "Week", "url": "/?period=week"},
            {"name": "Graphs", "short_name": "Graphs", "url": "/graphs"},
        ],
    }
    return current_app.response_class(
        json.dumps(payload),
        mimetype="application/manifest+json",
    )


def _sniff_image_mimetype(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            head = fh.read(12)
    except OSError:
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


@bp.route("/app-icon.png", endpoint="app_icon")
def app_icon():
    icon_path = _icon_storage_path()
    if icon_path.exists():
        return send_file(icon_path, mimetype=_sniff_image_mimetype(icon_path))
    default_icon = Path(current_app.static_folder or "") / "img" / "app-icon-default.png"
    if default_icon.exists():
        return send_file(default_icon, mimetype="image/png")
    return send_file(BytesIO(_DEFAULT_ICON_BYTES), mimetype="image/png")


@bp.route("/favicon.ico", endpoint="favicon")
def favicon():
    # Browsers request this regardless of <link rel="icon">; avoid a 404 on every page.
    return redirect(url_for("main.app_icon", v=get_app_setting(current_app.config["DB_NAME"], "app_icon_version") or "1"))


@bp.route("/graphs", endpoint="graphs")
@login_required
def graphs():
    db_name = current_app.config["DB_NAME"]
    user_id = int(get_current_user_id() or 0)
    user_row = get_user_by_id(db_name, user_id)
    first_log_date = get_first_log_date(db_name, user_id)
    current_user = {
        "id": user_id,
        "display_name": display_name(user_row),
        "role": (row_value(user_row, "role") if user_row else "user"),
    }
    is_admin = _is_admin(user_row)
    return render_template(
        "graphs.html",
        current_user=current_user,
        is_admin=is_admin,
        first_log_date=(first_log_date.strftime("%Y-%m-%d") if first_log_date else ""),
        goals=get_user_goals(db_name, user_id),
    )
