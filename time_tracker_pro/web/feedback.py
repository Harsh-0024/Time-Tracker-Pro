from __future__ import annotations

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from ..core.rows import display_name
from ..repositories.feedback import (
    FEEDBACK_KINDS,
    add_feedback,
    clean_feedback,
    delete_feedback,
    feedback_counts,
    list_all_feedback,
    mark_feedback_seen,
    set_feedback_status,
)
from ..repositories.users import get_user_by_id
from .decorators import admin_required, login_required
from .utils import get_current_user_id


bp = Blueprint("feedback", __name__)


@bp.route("/settings/feedback", methods=["POST"], endpoint="send")
@login_required
def send():
    db_name = current_app.config["DB_NAME"]
    user_id = int(get_current_user_id() or 0)
    try:
        kind, message = clean_feedback(request.form.get("kind"), request.form.get("message"))
    except ValueError as exc:
        session["feedback_error"] = str(exc)
        # Keep what they wrote so it isn't lost.
        session["feedback_form"] = {
            "kind": (request.form.get("kind") or "")[:16],
            "message": (request.form.get("message") or "")[:4000],
        }
        return redirect(url_for("main.settings") + "#feedback-settings")
    add_feedback(db_name, user_id, kind, message)
    session["feedback_success"] = "Thank you. Your feedback went straight to the developer."
    return redirect(url_for("main.settings") + "#feedback-settings")


@bp.route("/admin/feedback", endpoint="admin_feedback")
@admin_required
def admin_feedback():
    db_name = current_app.config["DB_NAME"]
    admin_row = get_user_by_id(db_name, int(get_current_user_id() or 0))
    items = list_all_feedback(db_name)
    page = render_template(
        "admin_feedback.html",
        items=items,
        counts=feedback_counts(db_name),
        kinds=FEEDBACK_KINDS,
        current_user={"display_name": display_name(admin_row)},
        error=request.args.get("error"),
        success=request.args.get("success"),
    )
    # Shown once as new; from now on the sender sees it was read.
    mark_feedback_seen(db_name, [item["id"] for item in items if item["status"] == "new"])
    return page


@bp.route("/admin/feedback/<int:feedback_id>/status", methods=["POST"], endpoint="admin_feedback_status")
@admin_required
def admin_feedback_status(feedback_id: int):
    db_name = current_app.config["DB_NAME"]
    try:
        found = set_feedback_status(db_name, feedback_id, (request.form.get("status") or "").strip())
    except ValueError as exc:
        return redirect(url_for("feedback.admin_feedback", error=str(exc)))
    if not found:
        return redirect(url_for("feedback.admin_feedback", error="That feedback no longer exists."))
    return redirect(url_for("feedback.admin_feedback") + f"#fb-{feedback_id}")


@bp.route("/admin/feedback/<int:feedback_id>/delete", methods=["POST"], endpoint="admin_feedback_delete")
@admin_required
def admin_feedback_delete(feedback_id: int):
    db_name = current_app.config["DB_NAME"]
    if not delete_feedback(db_name, feedback_id):
        return redirect(url_for("feedback.admin_feedback", error="That feedback no longer exists."))
    return redirect(url_for("feedback.admin_feedback", success="Feedback deleted."))
