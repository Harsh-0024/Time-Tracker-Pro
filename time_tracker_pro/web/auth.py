from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..core.admins import is_admin_email
from ..core.rows import display_name, row_value
from ..db import get_db_connection
from ..repositories.auth import create_user
from ..repositories.bootstrap import adopt_orphan_logs
from ..repositories.login_throttle import clear_failures, is_locked_out, record_failure
from ..repositories.users import (
    get_user_by_email,
    get_user_by_id,
    get_user_by_public_id,
    get_user_by_username_or_id_or_email,
    get_user_count,
)
from ..repositories.settings import get_user_settings
from ..services.verification import (
    VERIFICATION_CODE_TTL_MINUTES,
    consume_verification,
    has_active_verification,
    seconds_until_resend_allowed,
    send_verification_email,
    verify_email_code,
)
from ..services.welcome_email import send_welcome_email
from .decorators import login_required
from .utils import mask_email, safe_next_url


bp = Blueprint("auth", __name__)

logger = logging.getLogger(__name__)

_PROFILE_OTP_PURPOSES = {"change_password", "change_username"}
MIN_PASSWORD_LENGTH = 8
# Hashing is deliberately slow; a multi-MB "password" would burn CPU on every attempt.
MAX_PASSWORD_LENGTH = 1024
MAX_NAME_LENGTH = 80
MAX_EMAIL_LENGTH = 254
# Login accepts a username, user ID or email in one box, so IDs must never look like an email
# (an ID of "someone@x.com" would shadow that person's email login).
USER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
USER_ID_RULE = "User ID must be 3-32 letters, numbers, dots, dashes or underscores."
RECENT_CODE_MESSAGE = "We sent you a code less than a minute ago. Check your inbox (and spam)."
SEND_FAILED_MESSAGE = "We couldn't send the email right now. Please try again in a few minutes."
REGISTER_SEND_FAILED_MESSAGE = "Your account was created, but we couldn't send the code. Tap Resend code to try again."


def _ua_hash(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


@bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    if session.get("user_id") is not None:
        return redirect(url_for("main.dashboard"))

    db_name = current_app.config["DB_NAME"]
    next_url = safe_next_url(request.args.get("next"))
    error: Optional[str] = None
    show_verify = False
    identifier_value = ""

    if request.method == "POST":
        identifier = (request.form.get("identifier") or request.form.get("username") or "").strip()
        identifier_value = identifier
        password = request.form.get("password") or ""
        remember = bool(request.form.get("remember"))
        next_url = safe_next_url(request.form.get("next")) or next_url
        action = (request.form.get("action") or "").strip().lower()

        if action == "login_otp":
            if not identifier:
                error = "Please enter your username, email, or user ID."
            else:
                user = get_user_by_username_or_id_or_email(db_name, identifier)
                if not user:
                    error = "No account found with that identifier."
                else:
                    session.clear()
                    session["pending_user_id"] = int(row_value(user, "id"))
                    session["pending_remember"] = remember
                    session["pending_verification_purpose"] = "login_otp"
                    if seconds_until_resend_allowed(db_name, int(row_value(user, "id")), "login_otp"):
                        session["verification_success"] = RECENT_CODE_MESSAGE
                    elif send_verification_email(db_name, user, purpose="login_otp"):
                        target_email = mask_email(row_value(user, "email"))
                        session["verification_success"] = (
                            f"Verification code sent to {target_email}." if target_email else "Verification code sent."
                        )
                    else:
                        session["verification_error"] = SEND_FAILED_MESSAGE
                    return redirect(url_for("auth.verify_email", next=next_url or ""))
        elif not identifier or not password:
            error = "Username, email, or user ID and password are required."
        elif is_locked_out(db_name, identifier):
            error = "Too many failed attempts. Try again in a few minutes, or log in with an email code."
        else:
            user = get_user_by_username_or_id_or_email(db_name, identifier)
            if not user:
                record_failure(db_name, identifier)
                error = "Invalid credentials."
            else:
                pw_hash = row_value(user, "password_hash") or ""
                if len(password) > MAX_PASSWORD_LENGTH or not check_password_hash(pw_hash, password):
                    record_failure(db_name, identifier)
                    error = "Invalid credentials."
                elif not int(row_value(user, "is_verified") or 0):
                    session.clear()
                    session["pending_user_id"] = int(row_value(user, "id"))
                    session["pending_remember"] = remember

                    if send_verification_email(db_name, user):
                        session["verification_success"] = "Verification code sent."
                    else:
                        session["verification_error"] = SEND_FAILED_MESSAGE

                    return redirect(url_for("auth.verify_email", next=next_url or ""))
                else:
                    clear_failures(db_name, identifier)
                    session.clear()
                    session["user_id"] = int(row_value(user, "id"))
                    session.permanent = remember
                    session["ua_hash"] = _ua_hash(request.headers.get("User-Agent") or "")

                    return redirect(next_url or url_for("main.dashboard"))

    if request.args.get("verify"):
        show_verify = True

    return render_template(
        "login.html",
        error=error,
        next=next_url or "",
        show_verify=show_verify,
        identifier=identifier_value,
    )


@bp.route("/forgot-password", methods=["GET", "POST"], endpoint="forgot_password")
def forgot_password():
    if session.get("user_id") is not None:
        return redirect(url_for("main.dashboard"))

    db_name = current_app.config["DB_NAME"]
    error: Optional[str] = session.pop("forgot_error", None)
    success: Optional[str] = None

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        if not identifier:
            error = "Please enter your email or user ID."
        else:
            if "@" in identifier:
                user = get_user_by_email(db_name, identifier)
            else:
                user = get_user_by_public_id(db_name, identifier)
            if not user:
                error = "No account found with that email or user ID."
            else:
                session.clear()
                session["pending_user_id"] = int(row_value(user, "id"))
                session["pending_verification_purpose"] = "forgot_password"
                if seconds_until_resend_allowed(db_name, int(row_value(user, "id")), "forgot_password"):
                    session["verification_success"] = RECENT_CODE_MESSAGE
                    return redirect(url_for("auth.verify_email"))
                if send_verification_email(db_name, user, purpose="forgot_password"):
                    target_email = mask_email(row_value(user, "email"))
                    session["verification_success"] = (
                        f"Verification code sent to {target_email}." if target_email else "Verification code sent."
                    )
                    return redirect(url_for("auth.verify_email"))
                error = SEND_FAILED_MESSAGE

    return render_template(
        "forgot_password.html",
        error=error,
        success=success,
        identifier=(request.form.get("identifier") or "").strip()[:254] if request.method == "POST" else "",
    )


@bp.route("/register", methods=["GET", "POST"], endpoint="register")
def register():
    if session.get("user_id") is not None:
        return redirect(url_for("main.dashboard"))

    db_name = current_app.config["DB_NAME"]
    error: Optional[str] = None

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        public_user_id = (request.form.get("user_id") or "").strip()
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        remember = bool(request.form.get("remember"))

        if not name or not email or not public_user_id or not password:
            error = "Name, email, user ID, and password are required."
        elif password != confirm_password:
            error = "Passwords do not match."
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        elif len(password) > MAX_PASSWORD_LENGTH:
            error = f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
        elif len(name) > MAX_NAME_LENGTH:
            error = f"Name must be at most {MAX_NAME_LENGTH} characters."
        elif len(email) > MAX_EMAIL_LENGTH or "@" not in email or "." not in email:
            error = "Please provide a valid email address."
        elif not USER_ID_RE.match(public_user_id):
            error = USER_ID_RULE
        elif get_user_by_public_id(db_name, public_user_id) or get_user_by_username_or_id_or_email(db_name, public_user_id):
            error = "That user ID is already taken."
        elif get_user_by_email(db_name, email) or get_user_by_username_or_id_or_email(db_name, email):
            error = "An account with that email already exists."
        else:
            created_at = datetime.now(timezone.utc).isoformat()
            password_hash = generate_password_hash(password)
            role = "admin" if is_admin_email(email) else "user"
            existing_users = get_user_count(db_name)

            new_user_id = create_user(
                db_name,
                username=public_user_id,
                user_id=public_user_id,
                name=name,
                email=email,
                password_hash=password_hash,
                role=role,
                is_verified=0,
                created_at=created_at,
            )

            if int(existing_users) == 0:
                adopt_orphan_logs(db_name, new_user_id)

            user = get_user_by_id(db_name, new_user_id)
            sent = bool(user) and send_verification_email(db_name, user)

            session.clear()
            session["pending_user_id"] = new_user_id
            session["pending_remember"] = remember
            if not sent:
                session["verification_error"] = REGISTER_SEND_FAILED_MESSAGE
            return redirect(url_for("auth.verify_email"))

    # Keep what was typed (never the passwords) so one bad field doesn't wipe the form.
    form = {k: (request.form.get(k) or "").strip()[:254] for k in ("name", "email", "user_id")} if request.method == "POST" else {}
    return render_template("register.html", error=error, form=form)


@bp.route("/logout", endpoint="logout")
def logout():
    session.clear()
    resp = redirect(url_for("auth.login"))
    try:
        resp.set_cookie("tt_token", "", expires=0)
    except Exception as exc:
        logger.warning("Failed to clear tt_token cookie error=%s", exc)
    return resp


@bp.route("/verify-email", methods=["GET", "POST"], endpoint="verify_email")
def verify_email():
    db_name = current_app.config["DB_NAME"]
    pending_id = session.get("pending_user_id")
    if not pending_id:
        return redirect(url_for("auth.login"))

    user = get_user_by_id(db_name, int(pending_id))
    if not user:
        session.pop("pending_user_id", None)
        return redirect(url_for("auth.register"))

    error: Optional[str] = session.pop("verification_error", None)
    success: Optional[str] = session.pop("verification_success", None)
    purpose = session.get("pending_verification_purpose") or "verify_email"
    next_url = safe_next_url(request.args.get("next"))
    title = "Verify your email"
    subtitle = "We sent a 6-digit code to"
    if purpose == "forgot_password":
        title = "Reset your password"
        subtitle = "We sent a 6-digit code to"
    if purpose == "login_otp":
        title = "Log in with OTP"
        subtitle = "We sent a 6-digit code to"

    if request.method == "POST":
        if request.form.get("action") == "resend":
            wait = seconds_until_resend_allowed(db_name, int(user["id"]), purpose)
            if wait:
                error = f"Please wait {wait} seconds before requesting another code."
            elif send_verification_email(db_name, user, purpose=purpose):
                success = "Verification code resent."
            else:
                error = SEND_FAILED_MESSAGE
        else:
            code = (request.form.get("code") or "").strip()
            if not code:
                error = "Please enter the verification code."
            else:
                ok, message = verify_email_code(
                    db_name,
                    int(user["id"]),
                    code,
                    purpose=purpose,
                    mark_verified=(purpose == "verify_email"),
                )
                if ok:
                    session.pop("pending_user_id", None)
                    session.pop("pending_verification_purpose", None)
                    if purpose == "verify_email":
                        send_welcome_email(user)
                        remember = bool(session.pop("pending_remember", False))
                        session["user_id"] = int(user["id"])
                        session.permanent = remember
                        session["ua_hash"] = _ua_hash(request.headers.get("User-Agent") or "")
                        return redirect(url_for("main.dashboard"))
                    if purpose == "login_otp":
                        remember = bool(session.pop("pending_remember", False))
                        session["user_id"] = int(user["id"])
                        session.permanent = remember
                        session["ua_hash"] = _ua_hash(request.headers.get("User-Agent") or "")
                        return redirect(next_url or url_for("main.dashboard"))
                    if purpose == "forgot_password":
                        session["otp_authenticated"] = True
                    session["password_reset_user_id"] = int(user["id"])
                    session["password_reset_started"] = int(time.time())
                    return redirect(url_for("auth.reset_password"))
                error = message
    elif not has_active_verification(db_name, int(user["id"]), purpose=purpose):
        if send_verification_email(db_name, user, purpose=purpose):
            success = "Verification code sent."
        else:
            error = SEND_FAILED_MESSAGE

    return render_template(
        "verify_email.html",
        error=error,
        success=success,
        email=row_value(user, "email") if purpose == "verify_email" else mask_email(row_value(user, "email")),
        name=display_name(user),
        title=title,
        subtitle=subtitle,
        # Don't claim "We sent a code" (with an expiry) when the email just failed.
        send_failed=error in (SEND_FAILED_MESSAGE, REGISTER_SEND_FAILED_MESSAGE),
        purpose=purpose,
        resend_wait=seconds_until_resend_allowed(db_name, int(user["id"]), purpose),
        ttl_minutes=VERIFICATION_CODE_TTL_MINUTES,
    )


@bp.route("/reset-password", methods=["GET", "POST"], endpoint="reset_password")
def reset_password():
    db_name = current_app.config["DB_NAME"]
    reset_user_id = session.get("password_reset_user_id")
    if not reset_user_id:
        return redirect(url_for("auth.login"))
    # The page promises the window closes after the code TTL; without this a verified-but-abandoned
    # browser session could set a new password at any later time.
    started = int(session.get("password_reset_started") or 0)
    if time.time() - started > VERIFICATION_CODE_TTL_MINUTES * 60:
        session.pop("password_reset_user_id", None)
        session.pop("password_reset_started", None)
        session.pop("otp_authenticated", None)
        session["forgot_error"] = "That reset session expired. Request a new code to continue."
        return redirect(url_for("auth.forgot_password"))

    user = get_user_by_id(db_name, int(reset_user_id))
    if not user:
        session.pop("password_reset_user_id", None)
        return redirect(url_for("auth.login"))

    error: Optional[str] = None
    success: Optional[str] = None
    if request.method == "POST":
        new_password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
            error = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        elif len(new_password) > MAX_PASSWORD_LENGTH:
            error = f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
        elif new_password != confirm_password:
            error = "Passwords do not match."
        else:
            conn = get_db_connection(db_name)
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(new_password), int(user["id"])),
            )
            conn.commit()
            conn.close()
            # The old failures were against the old password; don't leave them locked out.
            for ident in {row_value(user, "username"), row_value(user, "user_id"), row_value(user, "email")}:
                if ident:
                    clear_failures(db_name, ident)
            session.pop("password_reset_user_id", None)
            session.pop("password_reset_started", None)
            session.pop("otp_authenticated", None)
            session["user_id"] = int(user["id"])
            session.permanent = True
            session["ua_hash"] = _ua_hash(request.headers.get("User-Agent") or "")
            success = "Password updated."
            return redirect(url_for("main.dashboard"))

    return render_template(
        "reset_password.html", error=error, success=success, ttl_minutes=VERIFICATION_CODE_TTL_MINUTES
    )


@bp.route("/profile/request-otp", methods=["POST"], endpoint="profile_request_otp")
@login_required
def profile_request_otp():
    db_name = current_app.config["DB_NAME"]
    user_id = int(session.get("user_id") or 0)
    user = get_user_by_id(db_name, user_id)
    if not user:
        session["profile_error"] = "Unable to load your profile."
        return redirect(url_for("main.settings"))

    purpose = (request.form.get("purpose") or "").strip()
    if purpose == "change_email":
        new_email = (request.form.get("new_email") or "").strip().lower()
        if not new_email or "@" not in new_email or len(new_email) > MAX_EMAIL_LENGTH:
            session["profile_error"] = "Please provide a valid new email address."
            return redirect(url_for("main.settings"))
        if (row_value(user, "email") or "").strip().lower() == new_email:
            session["profile_error"] = "New email matches your current email."
            return redirect(url_for("main.settings"))
        existing = get_user_by_email(db_name, new_email) or get_user_by_username_or_id_or_email(db_name, new_email)
        if existing and int(existing["id"]) != int(user["id"]):
            session["profile_error"] = "That email is already in use."
            return redirect(url_for("main.settings"))

        session["pending_email_new"] = new_email
        sent_old = send_verification_email(db_name, user, purpose="change_email_old")
        sent_new = send_verification_email(
            db_name,
            user,
            purpose="change_email_new",
            email_override=new_email,
        )
        if sent_old and sent_new:
            session["profile_success"] = "Verification codes sent to both emails."
        else:
            session["profile_error"] = "We couldn't send the verification emails right now. Please try again in a few minutes."
        return redirect(url_for("main.settings"))

    if purpose not in _PROFILE_OTP_PURPOSES:
        session["profile_error"] = "Invalid verification request."
        return redirect(url_for("main.settings"))

    if send_verification_email(db_name, user, purpose=purpose):
        session["profile_success"] = "Verification code sent."
    else:
        session["profile_error"] = SEND_FAILED_MESSAGE
    return redirect(url_for("main.settings"))


@bp.route("/profile/update", methods=["POST"], endpoint="update_profile")
@login_required
def update_profile():
    db_name = current_app.config["DB_NAME"]
    user_id = int(session.get("user_id") or 0)
    user = get_user_by_id(db_name, user_id)
    if not user:
        session["profile_error"] = "Unable to load your profile."
        return redirect(url_for("main.settings"))

    action = (request.form.get("action") or "").strip()
    current_password = request.form.get("current_password") or ""
    otp_code = (request.form.get("otp_code") or "").strip()

    # Wrong current-password guesses are throttled like logins (a hijacked session must not
    # be able to brute-force the password). The key has a space, which user IDs can't contain.
    throttle_key = f"profile #{int(user['id'])}"

    def confirm_with_password_or_otp(purpose: str) -> Tuple[bool, str]:
        password_locked = False
        if current_password:
            password_locked = is_locked_out(db_name, throttle_key)
            pw_hash = row_value(user, "password_hash") or ""
            if (
                not password_locked
                and len(current_password) <= MAX_PASSWORD_LENGTH
                and check_password_hash(pw_hash, current_password)
            ):
                clear_failures(db_name, throttle_key)
                return True, ""
            if not password_locked:
                record_failure(db_name, throttle_key)
        if otp_code:
            return verify_email_code(db_name, int(user["id"]), otp_code, purpose=purpose)
        if password_locked:
            return False, "Too many incorrect password attempts. Try again later or use a verification code."
        if current_password:
            return False, "Current password is incorrect."
        return False, "Provide your current password or a verification code."

    if action == "update_username":
        new_user_id = (request.form.get("new_user_id") or "").strip()
        new_name = (request.form.get("new_name") or "").strip()
        if not new_user_id and not new_name:
            session["profile_error"] = "Please enter a new user ID or name."
            return redirect(url_for("main.settings"))
        if len(new_name) > MAX_NAME_LENGTH:
            session["profile_error"] = f"Name must be at most {MAX_NAME_LENGTH} characters."
            return redirect(url_for("main.settings"))
        if new_user_id and not USER_ID_RE.match(new_user_id):
            session["profile_error"] = USER_ID_RULE
            return redirect(url_for("main.settings"))
        existing = (
            get_user_by_public_id(db_name, new_user_id) or get_user_by_username_or_id_or_email(db_name, new_user_id)
            if new_user_id
            else None
        )
        if new_user_id and existing and int(existing["id"]) != int(user["id"]):
            session["profile_error"] = "That user ID is already taken."
            return redirect(url_for("main.settings"))
        ok, message = confirm_with_password_or_otp("change_username")
        if not ok:
            session["profile_error"] = message
            return redirect(url_for("main.settings"))
        conn = get_db_connection(db_name)
        if new_user_id and new_name:
            conn.execute(
                "UPDATE users SET username = ?, user_id = ?, name = ? WHERE id = ?",
                (new_user_id, new_user_id, new_name, int(user["id"])),
            )
        elif new_user_id:
            conn.execute(
                "UPDATE users SET username = ?, user_id = ? WHERE id = ?",
                (new_user_id, new_user_id, int(user["id"])),
            )
        else:
            conn.execute(
                "UPDATE users SET name = ? WHERE id = ?",
                (new_name, int(user["id"])),
            )
        conn.commit()
        conn.close()
        session["profile_success"] = "Profile updated."
        return redirect(url_for("main.settings"))

    if action == "update_password":
        new_password = request.form.get("new_password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        if not new_password or len(new_password) < MIN_PASSWORD_LENGTH:
            session["profile_error"] = f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            return redirect(url_for("main.settings"))
        if len(new_password) > MAX_PASSWORD_LENGTH:
            session["profile_error"] = f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
            return redirect(url_for("main.settings"))
        if new_password != confirm_password:
            session["profile_error"] = "Passwords do not match."
            return redirect(url_for("main.settings"))
        ok = False
        message = ""
        if session.get("otp_authenticated"):
            ok = True
        else:
            ok, message = confirm_with_password_or_otp("change_password")
        if not ok:
            session["profile_error"] = message
            return redirect(url_for("main.settings"))
        conn = get_db_connection(db_name)
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), int(user["id"])),
        )
        conn.commit()
        conn.close()
        session.pop("otp_authenticated", None)
        session["profile_success"] = "Password updated."
        return redirect(url_for("main.settings"))

    if action == "update_email":
        new_email = (request.form.get("new_email") or "").strip().lower()
        old_code = (request.form.get("old_email_code") or "").strip()
        new_code = (request.form.get("new_email_code") or "").strip()
        pending_email = (session.get("pending_email_new") or "").strip().lower()
        if not new_email or "@" not in new_email or len(new_email) > MAX_EMAIL_LENGTH:
            session["profile_error"] = "Please provide a valid new email address."
            return redirect(url_for("main.settings"))
        if not pending_email or pending_email != new_email:
            session["profile_error"] = "Request a new verification code for this email first."
            return redirect(url_for("main.settings"))
        if not old_code or not new_code:
            session["profile_error"] = "Enter both verification codes."
            return redirect(url_for("main.settings"))
        existing = get_user_by_email(db_name, new_email) or get_user_by_username_or_id_or_email(db_name, new_email)
        if existing and int(existing["id"]) != int(user["id"]):
            session["profile_error"] = "That email is already in use."
            return redirect(url_for("main.settings"))

        ok_old, message_old = verify_email_code(
            db_name,
            int(user["id"]),
            old_code,
            purpose="change_email_old",
            consume=False,
        )
        if not ok_old:
            session["profile_error"] = message_old
            return redirect(url_for("main.settings"))
        ok_new, message_new = verify_email_code(
            db_name,
            int(user["id"]),
            new_code,
            purpose="change_email_new",
            consume=False,
        )
        if not ok_new:
            session["profile_error"] = message_new
            return redirect(url_for("main.settings"))
        consume_verification(db_name, int(user["id"]), "change_email_old")
        consume_verification(db_name, int(user["id"]), "change_email_new")

        conn = get_db_connection(db_name)
        conn.execute(
            "UPDATE users SET email = ? WHERE id = ?",
            (new_email, int(user["id"])),
        )
        conn.commit()
        conn.close()
        session.pop("pending_email_new", None)
        session["profile_success"] = "Email updated."
        return redirect(url_for("main.settings"))

    session["profile_error"] = "Unknown profile update action."
    return redirect(url_for("main.settings"))
