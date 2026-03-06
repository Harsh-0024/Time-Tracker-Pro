from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from threading import Lock, Thread
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

from ..db import get_db_connection
from ..core.tags import filter_special_tags, normalize_tag
from ..repositories.logs import replace_logs_for_user
from ..repositories.sheety_snapshots import create_sheety_sync_snapshot, fetch_sheety_sync_snapshot_rows
from ..repositories.settings import get_user_settings
from ..repositories.sheety_accounts import get_user_api_accounts
from ..repositories.sheety_outbox import (
    end_rewrite,
    fetch_pending_outbox,
    is_rewrite_in_progress,
    mark_outbox_done,
    mark_outbox_failed,
    try_begin_rewrite,
    update_local_sheety_id_for_created,
)
from ..repositories.users import get_user_count
from .parser import TimeLogParser


logger = logging.getLogger(__name__)

SHEETY_ENDPOINT_ENV = "SHEETY_ENDPOINT"
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))
SYNC_FAIL_COOLDOWN_SECONDS = int(os.getenv("SYNC_FAIL_COOLDOWN_SECONDS", "1800"))
DELETE_DUPLICATE_SHEET_ROWS = (os.getenv("SYNC_DELETE_DUPLICATE_SHEET_ROWS") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
REWRITE_SORTED_SHEET_ROWS = (os.getenv("SYNC_REWRITE_SORTED_SHEET_ROWS") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
DISABLE_SHEET_REWRITE = (os.getenv("DISABLE_SHEET_REWRITE") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
REWRITE_MIN_KEEP_RATIO = float(os.getenv("SYNC_REWRITE_MIN_KEEP_RATIO", "0.90"))
READ_ONLY_SYNC_NO_SHEETY_WRITES = (os.getenv("SYNC_READ_ONLY_NO_SHEETY_WRITES", "true") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}

MAX_FULL_REWRITE_ROWS = int(os.getenv("SYNC_MAX_FULL_REWRITE_ROWS", "200"))
MAX_SHEETY_WRITE_BUDGET = int(os.getenv("SYNC_MAX_SHEETY_WRITE_BUDGET", "50"))
MAX_DUPLICATE_DELETE_BATCH = int(os.getenv("SYNC_MAX_DUPLICATE_DELETE_BATCH", "20"))
SCOPED_DUPLICATE_LOOKBACK_ROWS = int(os.getenv("SYNC_SCOPED_DUPLICATE_LOOKBACK_ROWS", "300"))
SHEETY_FLAG_COLUMN = (os.getenv("SYNC_SHEETY_FLAG_COLUMN") or "").strip()
SHEETY_FLAG_VALUE = (os.getenv("SYNC_SHEETY_FLAG_VALUE") or "1").strip() or "1"
ENABLE_SHEETY_FLAGGING = (os.getenv("SYNC_ENABLE_SHEETY_FLAGGING") or "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
MAX_FLAG_UPDATE_BATCH = int(os.getenv("SYNC_MAX_FLAG_UPDATE_BATCH", "20"))

_LAST_SYNC_TS_BY_USER: Dict[int, datetime] = {}
_LAST_SYNC_FAIL_TS_BY_USER: Dict[int, datetime] = {}
_LAST_SYNC_STATS_BY_USER: Dict[int, Dict[str, Any]] = {}
_REWRITE_LOCKS_BY_USER: Dict[int, Lock] = {}
_REWRITE_JOB_SCHEDULED_BY_USER: Dict[int, bool] = {}
_DUPLICATE_CLEANUP_JOB_SCHEDULED_BY_USER: Dict[int, bool] = {}


def should_sync(user_id: int, now: Optional[datetime] = None) -> bool:
    current = now or datetime.now(timezone.utc)
    last_fail = _LAST_SYNC_FAIL_TS_BY_USER.get(int(user_id))
    if last_fail and (current - last_fail).total_seconds() < SYNC_FAIL_COOLDOWN_SECONDS:
        return False
    last_ok = _LAST_SYNC_TS_BY_USER.get(int(user_id))
    if last_ok is None:
        return True
    return (current - last_ok).total_seconds() > SYNC_INTERVAL_SECONDS


def sync_cloud_data(db_name: str, user_id: int, force: bool = False) -> Optional[Dict[str, str]]:
    if os.getenv("DISABLE_CLOUD_SYNC") and not force:
        logger.info("Cloud sync disabled by env; skipping (force=%s)", force)
        return None

    now = datetime.now(timezone.utc)
    if not force and not should_sync(int(user_id), now):
        return None

    failover_notice: Optional[Dict[str, str]] = None
    _LAST_SYNC_STATS_BY_USER[int(user_id)] = {
        "status": "started",
        "source_rows": 0,
        "parsed_rows": 0,
        "deduped_rows": 0,
        "merged_rows": 0,
        "inserted_rows": 0,
        "deleted_duplicates": 0,
        "flagged_rows": 0,
        "duplicate_candidates": 0,
        "duplicate_preview": [],
        "sheet_rewrite": "skipped",
        "skipped_reason": "",
        "sheety_quota_exhausted": False,
        "sheety_error": "",
    }

    if is_rewrite_in_progress(db_name, int(user_id)):
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "skipped"
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "in_progress"
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "sheet_rewrite_in_progress"
        return None

    def _is_sheety_quota_error(error: Optional[str]) -> bool:
        if not error:
            return False
        lower = error.lower()
        return "http 402" in lower or "quota" in lower or "payment required" in lower

    def _record_sync_failure(reason: str, error: Optional[str] = None, quota: bool = False) -> None:
        if quota:
            _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now - timedelta(hours=23)
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheety_quota_exhausted"] = True
        else:
            _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "failed"
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = reason
        if error:
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheety_error"] = str(error)

    try:
        payload: Optional[Dict[str, Any]] = None
        cleanup_service = None
        cleanup_url: Optional[str] = None
        cleanup_headers: Dict[str, str] = {}
        service = None
        try:
            from .sheety_failover import SheetyFailoverService

            service = SheetyFailoverService(db_name, int(user_id))
            if not service.has_available_accounts():
                service = None
        except Exception:
            service = None

        if service is not None:
            success, data, error = service.make_request("GET")
            failover_notice = service.get_failover_notification()
            used_fallback = False
            if not success:
                logger.warning("Sheety sync failed user_id=%s error=%s", int(user_id), error)
                fallback_url, fallback_headers = _get_sheety_endpoint(db_name, int(user_id))
                if fallback_url:
                    try:
                        response = requests.get(fallback_url, headers=fallback_headers, timeout=15)
                        if response.status_code == 402:
                            _record_sync_failure(
                                "sheety_subscription_required",
                                error="HTTP 402",
                                quota=True,
                            )
                            return failover_notice
                        response.raise_for_status()
                        payload = response.json()
                        cleanup_url = fallback_url
                        cleanup_headers = fallback_headers
                        used_fallback = True
                    except requests.RequestException as exc:
                        quota_error = _is_sheety_quota_error(error or str(exc))
                        _record_sync_failure(error or str(exc), error=error or str(exc), quota=quota_error)
                        return failover_notice
                else:
                    quota_error = _is_sheety_quota_error(error)
                    _record_sync_failure(error or "sheety_request_failed", error=error, quota=quota_error)
                    return failover_notice
            if isinstance(data, dict):
                payload = data
            if not used_fallback:
                cleanup_service = service
        else:
            url, headers = _get_sheety_endpoint(db_name, int(user_id))
            if not url:
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "skipped"
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "missing_sheety_endpoint"
                return failover_notice
            cleanup_url = url
            cleanup_headers = headers

            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 402:
                _record_sync_failure("sheety_subscription_required", error="HTTP 402", quota=True)
                return failover_notice
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict) or not payload:
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "skipped"
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "empty_payload"
            return failover_notice

        sheet_key = "sheet1" if "sheet1" in payload else next(iter(payload.keys()), None)
        if not sheet_key:
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "skipped"
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "missing_sheet_key"
            return failover_notice

        cloud_df = pd.DataFrame(payload.get(sheet_key) or [])
        original_row_ids: Optional[List[Optional[int]]] = None
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["source_rows"] = len(cloud_df)
        if "id" in cloud_df.columns:
            cloud_df = cloud_df.sort_values("id")
            original_row_ids = []
            for value in cloud_df["id"].tolist():
                if isinstance(value, float) and pd.isna(value):
                    original_row_ids.append(None)
                elif value is None:
                    original_row_ids.append(None)
                else:
                    try:
                        original_row_ids.append(int(value))
                    except (TypeError, ValueError):
                        original_row_ids.append(None)

        logged_col = None
        for candidate in ("loggedTime", "logged_time", "logged time"):
            if candidate in cloud_df.columns:
                logged_col = candidate
                break

        def parse_logged_datetime(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, pd.Timestamp):
                if pd.isna(value):
                    return None
                value = value.to_pydatetime()
            if isinstance(value, datetime):
                if value.tzinfo is not None:
                    return value.replace(tzinfo=None)
                return value

            text = str(value).strip()
            if not text or text.lower() == "nan":
                return None

            iso_text = text
            if iso_text.endswith("Z"):
                iso_text = f"{iso_text[:-1]}+00:00"
            try:
                parsed_iso = datetime.fromisoformat(iso_text)
                if parsed_iso.tzinfo is not None:
                    return parsed_iso.replace(tzinfo=None)
                return parsed_iso
            except Exception:
                pass

            parsed_default = pd.to_datetime(text, errors="coerce")
            if not pd.isna(parsed_default):
                if isinstance(parsed_default, pd.Timestamp):
                    parsed_default = parsed_default.to_pydatetime()
                if isinstance(parsed_default, datetime):
                    if parsed_default.tzinfo is not None:
                        return parsed_default.replace(tzinfo=None)
                    return parsed_default

            parsed_dayfirst = pd.to_datetime(text, errors="coerce", dayfirst=True)
            if pd.isna(parsed_dayfirst):
                return None
            if isinstance(parsed_dayfirst, pd.Timestamp):
                parsed_dayfirst = parsed_dayfirst.to_pydatetime()
            if isinstance(parsed_dayfirst, datetime):
                if parsed_dayfirst.tzinfo is not None:
                    return parsed_dayfirst.replace(tzinfo=None)
                return parsed_dayfirst
            return None

        if logged_col:
            try:
                cloud_df["__logged_dt"] = cloud_df[logged_col].apply(parse_logged_datetime)
                cloud_df["__logged_dt"] = pd.to_datetime(cloud_df["__logged_dt"], errors="coerce")
                sort_cols = ["__logged_dt"]
                ascending = [True]
                if "id" in cloud_df.columns:
                    sort_cols.append("id")
                    ascending.append(True)
                cloud_df = cloud_df.sort_values(
                    sort_cols,
                    ascending=ascending,
                    kind="mergesort",
                    na_position="last",
                )
            except Exception:
                pass

        def row_text(row: pd.Series, keys: Iterable[str]) -> str:
            for key in keys:
                value = row.get(key)
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    continue
                text = str(value).strip()
                if text and text.lower() != "nan":
                    return text
            return ""

        def dict_text(raw_row: Dict[str, Any], keys: Iterable[str]) -> str:
            for key in keys:
                value = raw_row.get(key)
                if value is None:
                    continue
                if isinstance(value, float) and pd.isna(value):
                    continue
                text = str(value).strip()
                if text and text.lower() != "nan":
                    return text
            return ""

        def normalize_task_name(raw: Any) -> str:
            s = re.sub(r"\s+", " ", str(raw or "").strip())
            if not s:
                return "Unspecified"
            return s.title()

        def normalize_log_entry(raw: Any) -> str:
            s = re.sub(r"\s+", " ", str(raw or "").strip())
            if not s:
                return ""
            s = re.sub(r"[\s\.,;:]+$", "", s)
            return s.lower()

        def dedupe_log_entry_key(raw: Any) -> str:
            return str(raw or "").strip()

        def canonical_logged_key(row: pd.Series, client_now: str) -> str:
            logged_key = str(client_now or "").strip()
            logged_dt_value = row.get("__logged_dt")
            if logged_dt_value is not None and not pd.isna(logged_dt_value):
                try:
                    if isinstance(logged_dt_value, pd.Timestamp):
                        logged_key = logged_dt_value.isoformat()
                    else:
                        parsed_logged_dt = parse_logged_datetime(logged_dt_value)
                        if parsed_logged_dt is not None:
                            logged_key = parsed_logged_dt.isoformat()
                except Exception:
                    pass
            return logged_key

        parser = TimeLogParser()
        parsed_rows: List[Dict[str, Any]] = []
        previous_end: Optional[datetime] = None
        seen_source_rows: Dict[tuple[str, str], Dict[str, Any]] = {}
        duplicate_sheety_ids: List[int] = []
        duplicate_groups: Dict[tuple[str, str], Dict[str, Any]] = {}
        row_payloads: List[Dict[str, Any]] = []

        def is_row_flagged(value: Any) -> bool:
            if not SHEETY_FLAG_COLUMN:
                return False
            raw = str(value or "").strip().lower()
            if not raw:
                return False
            if raw == str(SHEETY_FLAG_VALUE).strip().lower():
                return True
            return raw in {"1", "true", "yes", "y", "on"}

        for _, row in cloud_df.iterrows():
            sheety_id = row.get("id")
            if isinstance(sheety_id, float) and pd.isna(sheety_id):
                sheety_id = None
            elif sheety_id is not None:
                try:
                    sheety_id = int(sheety_id)
                except (TypeError, ValueError):
                    sheety_id = None
            log_entry = row_text(
                row,
                (
                    "logEntry",
                    "log_entry",
                    "log entry",
                    "entry",
                    "taskDetails",
                    "task",
                    "task_details",
                    "task details",
                    "rawTask",
                    "raw_task",
                    "colB",
                ),
            )
            client_now = row_text(
                row,
                (
                    "loggedTime",
                    "logged_time",
                    "logged time",
                ),
            )
            logged_key = canonical_logged_key(row, client_now)
            entry_key = dedupe_log_entry_key(log_entry)

            flag_value = None
            is_flagged = False
            if SHEETY_FLAG_COLUMN and SHEETY_FLAG_COLUMN in row.index:
                flag_value = row.get(SHEETY_FLAG_COLUMN)
                is_flagged = is_row_flagged(flag_value)
            row_payloads.append(
                {
                    "row": row,
                    "row_dict": row.to_dict(),
                    "sheety_id": sheety_id,
                    "log_entry": log_entry,
                    "client_now": client_now,
                    "logged_key": logged_key,
                    "entry_key": entry_key,
                    "is_flagged": bool(is_flagged),
                }
            )

        sorted_row_ids: Optional[List[Optional[int]]] = None
        if original_row_ids is not None:
            sorted_row_ids = [payload.get("sheety_id") for payload in row_payloads]

        existing_row_ids_for_rewrite: List[int] = []
        for payload in row_payloads:
            sid = payload.get("sheety_id")
            if sid is None:
                continue
            try:
                existing_row_ids_for_rewrite.append(int(sid))
            except Exception:
                continue
        if existing_row_ids_for_rewrite:
            existing_row_ids_for_rewrite = sorted(set(existing_row_ids_for_rewrite))

        rows_for_parse: List[Dict[str, Any]] = []
        for payload in row_payloads:
            if not str(payload.get("logged_key") or "").strip():
                rows_for_parse.append(payload)
                continue
            source_key = (payload["entry_key"], payload["logged_key"])
            if source_key in seen_source_rows:
                first = seen_source_rows.get(source_key) or {}
                group = duplicate_groups.get(source_key)
                if group is None:
                    group = {
                        "logged_time": source_key[1],
                        "normalized_log_entry": normalize_log_entry(payload["log_entry"]),
                        "sample_log_entry": first.get("log_entry") or "",
                        "row_ids": [],
                    }
                    if first.get("sheety_id") is not None:
                        group["row_ids"].append(int(first["sheety_id"]))
                    duplicate_groups[source_key] = group
                if payload.get("sheety_id") is not None:
                    group["row_ids"].append(int(payload["sheety_id"]))
                    duplicate_sheety_ids.append(int(payload["sheety_id"]))
                continue
            seen_source_rows[source_key] = {
                "sheety_id": payload.get("sheety_id"),
                "log_entry": payload["log_entry"],
            }
            rows_for_parse.append(payload)

        order_changed = bool(
            original_row_ids is not None
            and sorted_row_ids is not None
            and original_row_ids != sorted_row_ids
        )
        duplicates_removed = len(rows_for_parse) != len(row_payloads)

        rewrite_requested = False
        force_duplicate_cleanup = False
        if DISABLE_SHEET_REWRITE:
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "disabled"
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "sheet_rewrite_disabled"
        if REWRITE_SORTED_SHEET_ROWS and not DISABLE_SHEET_REWRITE and not order_changed and not duplicates_removed:
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "not_needed"
        keep_ratio = (len(rows_for_parse) / len(row_payloads)) if row_payloads else 1.0
        rewrite_drop_too_large = duplicates_removed and keep_ratio < REWRITE_MIN_KEEP_RATIO
        if rewrite_drop_too_large:
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "skipped_safety"
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "rewrite_safety_keep_ratio"
            logger.warning(
                "Skipping sheet rewrite for safety user_id=%s keep_ratio=%.3f min_keep_ratio=%.3f source_rows=%s deduped_rows=%s",
                int(user_id),
                keep_ratio,
                REWRITE_MIN_KEEP_RATIO,
                len(row_payloads),
                len(rows_for_parse),
            )
            if duplicate_sheety_ids and keep_ratio <= 0.70:
                force_duplicate_cleanup = True

        if (
            REWRITE_SORTED_SHEET_ROWS
            and not DISABLE_SHEET_REWRITE
            and (order_changed or duplicates_removed)
            and not rewrite_drop_too_large
            and bool(existing_row_ids_for_rewrite)
        ):
            estimated_writes = int(len(existing_row_ids_for_rewrite))
            if len(existing_row_ids_for_rewrite) > MAX_FULL_REWRITE_ROWS:
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "skipped_budget"
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "rewrite_too_many_rows"
            elif MAX_SHEETY_WRITE_BUDGET > 0 and estimated_writes > MAX_SHEETY_WRITE_BUDGET:
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "skipped_budget"
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "rewrite_write_budget"
            elif MAX_SHEETY_WRITE_BUDGET <= 0:
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "skipped_budget"
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "rewrite_budget_disabled"
            else:
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "scheduled"
                rewrite_requested = True

        if (
            REWRITE_SORTED_SHEET_ROWS
            and not DISABLE_SHEET_REWRITE
            and (order_changed or duplicates_removed)
            and not rewrite_drop_too_large
            and not existing_row_ids_for_rewrite
        ):
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "skipped_missing_ids"
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "rewrite_missing_row_ids"

        if READ_ONLY_SYNC_NO_SHEETY_WRITES:
            rewrite_requested = False
            force_duplicate_cleanup = False
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["sheet_rewrite"] = "disabled_read_only"
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "sync_read_only_no_sheet_writes"

        snapshot_rows: List[Dict[str, Any]] = []
        for payload in rows_for_parse:
            row_dict = dict(payload.get("row_dict") or {})
            row_dict.pop("__logged_dt", None)
            snapshot_rows.append(row_dict)

        snapshot_id: Optional[int] = None
        if snapshot_rows:
            try:
                snapshot_id = int(
                    create_sheety_sync_snapshot(
                        db_name,
                        int(user_id),
                        str(sheet_key),
                        snapshot_rows,
                    )
                )
                _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["snapshot_id"] = int(snapshot_id)
            except Exception as exc:
                logger.warning("Failed to store Sheety snapshot user_id=%s error=%s", int(user_id), exc)

        parse_source_rows: List[Dict[str, Any]] = snapshot_rows
        if snapshot_id is not None:
            try:
                parse_source_rows = fetch_sheety_sync_snapshot_rows(db_name, int(snapshot_id))
            except Exception:
                parse_source_rows = snapshot_rows

        def _to_naive_datetime(value: Any) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, pd.Timestamp):
                if pd.isna(value):
                    return None
                value = value.to_pydatetime()
            if isinstance(value, datetime):
                if value.tzinfo is not None:
                    return value.replace(tzinfo=None)
                return value
            return None

        if parse_source_rows:
            max_sort_dt = datetime(9999, 12, 31, 23, 59, 59)
            row_order: List[Tuple[datetime, int, datetime, int]] = []

            def _minute_floor(dt_value: datetime) -> datetime:
                return dt_value.replace(second=0, microsecond=0)

            for idx, row_dict in enumerate(parse_source_rows):
                log_entry = dict_text(
                    row_dict,
                    (
                        "logEntry",
                        "log_entry",
                        "log entry",
                        "entry",
                        "taskDetails",
                        "task",
                        "task_details",
                        "task details",
                        "rawTask",
                        "raw_task",
                        "colB",
                    ),
                )
                client_now = dict_text(
                    row_dict,
                    (
                        "loggedTime",
                        "logged_time",
                        "logged time",
                    ),
                )

                logged_dt_probe = parse_logged_datetime(client_now)
                logged_sort_dt = logged_dt_probe or max_sort_dt
                inferred_sort_dt = logged_sort_dt
                inferred_is_range = 0
                client_now_probe = client_now
                if logged_dt_probe is not None:
                    client_now_probe = logged_dt_probe.strftime("%Y-%m-%d %H:%M:%S")

                if client_now:
                    try:
                        probe_parsed = parser.parse_row(log_entry, client_now_probe, None)
                        inferred_candidate = _to_naive_datetime(probe_parsed.get("start_dt"))
                        inferred_end = _to_naive_datetime(probe_parsed.get("end_dt"))
                        if inferred_candidate is not None:
                            inferred_sort_dt = inferred_candidate
                        if (
                            inferred_candidate is not None
                            and inferred_end is not None
                            and inferred_end != inferred_candidate
                        ):
                            inferred_is_range = 1
                    except Exception:
                        pass

                row_order.append((_minute_floor(inferred_sort_dt), inferred_is_range, logged_sort_dt, idx))

            ordered_indices = [idx for _, _, _, idx in sorted(row_order, key=lambda item: (item[0], item[1], item[2], item[3]))]
            parse_source_rows = [parse_source_rows[idx] for idx in ordered_indices]

        for row_dict in parse_source_rows:
            raw_sheety_id = row_dict.get("id")
            sheety_id = None
            if isinstance(raw_sheety_id, float) and pd.isna(raw_sheety_id):
                sheety_id = None
            elif raw_sheety_id is not None:
                try:
                    sheety_id = int(raw_sheety_id)
                except (TypeError, ValueError):
                    sheety_id = None

            log_entry = dict_text(
                row_dict,
                (
                    "logEntry",
                    "log_entry",
                    "log entry",
                    "entry",
                    "taskDetails",
                    "task",
                    "task_details",
                    "task details",
                    "rawTask",
                    "raw_task",
                    "colB",
                ),
            )
            client_now = dict_text(
                row_dict,
                (
                    "loggedTime",
                    "logged_time",
                    "logged time",
                ),
            )
            logged_dt_current = parse_logged_datetime(client_now)
            client_now_for_parse = client_now
            if logged_dt_current is not None:
                client_now_for_parse = logged_dt_current.strftime("%Y-%m-%d %H:%M:%S")

            try:
                parsed = parser.parse_row(log_entry, client_now_for_parse, previous_end)
            except Exception as exc:
                logger.warning(
                    "Skipping invalid row during cloud sync user_id=%s logged_time=%s log_entry=%r error=%s",
                    int(user_id),
                    client_now,
                    log_entry,
                    exc,
                )
                continue

            if sheety_id is not None:
                parsed["sheety_id"] = sheety_id

            parsed["task"] = normalize_task_name(parsed.get("task"))
            parsed["tag"] = normalize_tag(parsed.get("tag")) or "Waste"
            parsed_rows.append(parsed)
            if previous_end is None:
                previous_end = parsed["end_dt"]
            elif parsed.get("end_dt") is not None:
                try:
                    if parsed["end_dt"] > previous_end:
                        previous_end = parsed["end_dt"]
                except Exception:
                    pass

        _LAST_SYNC_STATS_BY_USER[int(user_id)]["parsed_rows"] = len(parsed_rows)
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["duplicate_candidates"] = len(duplicate_sheety_ids)
        if duplicate_groups:
            preview: List[Dict[str, Any]] = []
            for group in duplicate_groups.values():
                ids = [int(x) for x in (group.get("row_ids") or []) if x is not None]
                ids = sorted(set(ids))
                if len(ids) < 2:
                    continue
                preview.append(
                    {
                        "logged_time": group.get("logged_time") or "",
                        "normalized_log_entry": group.get("normalized_log_entry") or "",
                        "sample_log_entry": group.get("sample_log_entry") or "",
                        "row_ids": ids[:10],
                    }
                )
            preview.sort(key=lambda item: (item.get("logged_time") or "", item.get("normalized_log_entry") or ""))
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["duplicate_preview"] = preview[:15]

        _LAST_SYNC_STATS_BY_USER[int(user_id)]["deduped_rows"] = len(parsed_rows)
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["merged_rows"] = len(parsed_rows)

        final_rows: List[Dict[str, Any]] = []
        for p in parsed_rows:
            if p["start_dt"].date() < p["end_dt"].date():
                midnight = datetime.combine(p["end_dt"].date(), datetime.min.time())
                part1 = p.copy()
                part1["end_dt"] = midnight
                part2 = p.copy()
                part2["start_dt"] = midnight
                final_rows.append(part1)
                final_rows.append(part2)
            else:
                final_rows.append(p)

        inserted_count = replace_logs_for_user(db_name, int(user_id), final_rows)
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["inserted_rows"] = inserted_count
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "success"

        if rewrite_requested and snapshot_id is not None:
            _schedule_sheet_rewrite_job(
                db_name,
                int(user_id),
                sheet_key,
                int(snapshot_id),
                existing_row_ids_for_rewrite,
            )
        if rewrite_requested and snapshot_id is None:
            _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "skipped_snapshot_failed"

        if (
            duplicate_sheety_ids
            and (DELETE_DUPLICATE_SHEET_ROWS or force_duplicate_cleanup)
            and not rewrite_requested
            and not READ_ONLY_SYNC_NO_SHEETY_WRITES
        ):
            scoped_duplicate_ids = [int(x) for x in duplicate_sheety_ids if x is not None]
            scoped_duplicate_ids = sorted(set(scoped_duplicate_ids))
            if scoped_duplicate_ids and SCOPED_DUPLICATE_LOOKBACK_ROWS > 0:
                max_existing_id = max(scoped_duplicate_ids)
                for sid in existing_row_ids_for_rewrite:
                    if sid is not None and sid > max_existing_id:
                        max_existing_id = int(sid)

                max_flagged_id: Optional[int] = None
                if SHEETY_FLAG_COLUMN:
                    for payload in row_payloads:
                        if not payload.get("is_flagged"):
                            continue
                        sid = payload.get("sheety_id")
                        if sid is None:
                            continue
                        try:
                            sid_int = int(sid)
                        except Exception:
                            continue
                        if max_flagged_id is None or sid_int > max_flagged_id:
                            max_flagged_id = int(sid_int)

                threshold = int(max_flagged_id) if max_flagged_id is not None else int(max(0, max_existing_id - SCOPED_DUPLICATE_LOOKBACK_ROWS))
                scoped_duplicate_ids = [int(x) for x in scoped_duplicate_ids if int(x) > threshold]
                _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["duplicate_scope_threshold_id"] = int(threshold)
                _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["duplicate_candidates_scoped"] = int(len(scoped_duplicate_ids))
            if MAX_DUPLICATE_DELETE_BATCH > 0 and len(scoped_duplicate_ids) > MAX_DUPLICATE_DELETE_BATCH:
                scoped_duplicate_ids = scoped_duplicate_ids[: int(MAX_DUPLICATE_DELETE_BATCH)]
            _schedule_duplicate_cleanup_job(
                db_name,
                int(user_id),
                sheet_key,
                scoped_duplicate_ids,
            )

        if ENABLE_SHEETY_FLAGGING and SHEETY_FLAG_COLUMN and not rewrite_requested and not READ_ONLY_SYNC_NO_SHEETY_WRITES:
            flag_ids: List[int] = []
            for payload in rows_for_parse:
                if payload.get("is_flagged"):
                    continue
                sid = payload.get("sheety_id")
                if sid is None:
                    continue
                try:
                    flag_ids.append(int(sid))
                except Exception:
                    continue
            if MAX_FLAG_UPDATE_BATCH > 0 and len(flag_ids) > MAX_FLAG_UPDATE_BATCH:
                flag_ids = flag_ids[: int(MAX_FLAG_UPDATE_BATCH)]
            if flag_ids:
                _schedule_flag_rows_job(db_name, int(user_id), str(sheet_key), flag_ids)
        _LAST_SYNC_TS_BY_USER[int(user_id)] = now
        return failover_notice
    except requests.RequestException as exc:
        quota_error = False
        if hasattr(exc, "response") and exc.response is not None and exc.response.status_code == 402:
            quota_error = True
        _record_sync_failure(
            "sheety_subscription_required" if quota_error else str(exc),
            error=str(exc),
            quota=quota_error,
        )
        logger.error("Network error during cloud sync: %s", exc)
    except Exception as exc:
        _record_sync_failure(str(exc), error=str(exc), quota=False)
        logger.exception("Unexpected sync error: %s", exc)
    return failover_notice


def sync_status_payload(db_name: str, user_id: Optional[int]) -> Dict[str, Any]:
    allow_env_fallback = get_user_count(db_name) <= 1
    if user_id is not None:
        settings = get_user_settings(db_name, int(user_id))
        accounts = get_user_api_accounts(db_name, int(user_id))
        configured = bool(
            accounts
            or (settings.get("sheety_endpoint") or "").strip()
            or ((os.getenv(SHEETY_ENDPOINT_ENV) or "").strip() if allow_env_fallback else "")
        )
        return {
            "sheety_configured": configured,
            "disable_cloud_sync": bool(os.getenv("DISABLE_CLOUD_SYNC")),
            "last_sync": _LAST_SYNC_TS_BY_USER.get(int(user_id)).isoformat() if _LAST_SYNC_TS_BY_USER.get(int(user_id)) else None,
            "last_sync_fail": _LAST_SYNC_FAIL_TS_BY_USER.get(int(user_id)).isoformat() if _LAST_SYNC_FAIL_TS_BY_USER.get(int(user_id)) else None,
            "sync_interval_seconds": SYNC_INTERVAL_SECONDS,
            "fail_cooldown_seconds": SYNC_FAIL_COOLDOWN_SECONDS,
            "db_exists": os.path.exists(db_name),
        }

    return {
        "sheety_configured": bool(os.getenv(SHEETY_ENDPOINT_ENV)),
        "disable_cloud_sync": bool(os.getenv("DISABLE_CLOUD_SYNC")),
        "last_sync": None,
        "last_sync_fail": None,
        "sync_interval_seconds": SYNC_INTERVAL_SECONDS,
        "fail_cooldown_seconds": SYNC_FAIL_COOLDOWN_SECONDS,
        "db_exists": os.path.exists(db_name),
    }


def _schedule_sheet_rewrite_job(
    db_name: str,
    user_id: int,
    sheet_key: str,
    snapshot_id: int,
    existing_row_ids: List[Optional[int]],
) -> None:
    if not snapshot_id:
        return

    if _REWRITE_JOB_SCHEDULED_BY_USER.get(int(user_id)):
        return
    _REWRITE_JOB_SCHEDULED_BY_USER[int(user_id)] = True

    def _worker() -> None:
        try:
            _run_sheet_rewrite_job(
                db_name,
                int(user_id),
                str(sheet_key),
                int(snapshot_id),
                existing_row_ids,
            )
        finally:
            _REWRITE_JOB_SCHEDULED_BY_USER[int(user_id)] = False

    Thread(target=_worker, daemon=True, name=f"sheet-rewrite-{int(user_id)}").start()


def _schedule_duplicate_cleanup_job(
    db_name: str,
    user_id: int,
    sheet_key: str,
    duplicate_ids: List[int],
) -> None:
    if not duplicate_ids:
        return
    if _DUPLICATE_CLEANUP_JOB_SCHEDULED_BY_USER.get(int(user_id)):
        return
    _DUPLICATE_CLEANUP_JOB_SCHEDULED_BY_USER[int(user_id)] = True

    ids_copy = [int(x) for x in duplicate_ids if x is not None]

    def _worker() -> None:
        cleanup_service = None
        cleanup_url: Optional[str] = None
        cleanup_headers: Dict[str, str] = {}
        try:
            accounts = get_user_api_accounts(db_name, int(user_id))
            if accounts:
                try:
                    from .sheety_failover import SheetyFailoverService

                    cleanup_service = SheetyFailoverService(db_name, int(user_id))
                except Exception:
                    cleanup_service = None
            if cleanup_service is None:
                url, headers = _get_sheety_endpoint(db_name, int(user_id))
                cleanup_url = url or None
                cleanup_headers = headers

            deleted_count = _delete_duplicate_sheet_rows(
                ids_copy,
                sheet_key,
                cleanup_service,
                cleanup_url,
                cleanup_headers,
            )
            _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["deleted_duplicates"] = deleted_count
        finally:
            _DUPLICATE_CLEANUP_JOB_SCHEDULED_BY_USER[int(user_id)] = False

    Thread(target=_worker, daemon=True, name=f"sheet-duplicate-cleanup-{int(user_id)}").start()


def _schedule_flag_rows_job(db_name: str, user_id: int, sheet_key: str, row_ids: List[int]) -> None:
    if not row_ids or not SHEETY_FLAG_COLUMN:
        return

    ids_copy = [int(x) for x in row_ids if x is not None]
    if not ids_copy:
        return

    def _worker() -> None:
        service = None
        url: Optional[str] = None
        headers: Dict[str, str] = {}
        flagged = 0
        try:
            accounts = get_user_api_accounts(db_name, int(user_id))
            if accounts:
                try:
                    from .sheety_failover import SheetyFailoverService

                    service = SheetyFailoverService(db_name, int(user_id))
                except Exception:
                    service = None
            if service is None:
                endpoint, h = _get_sheety_endpoint(db_name, int(user_id))
                url = endpoint or None
                headers = h

            for row_id in ids_copy:
                payload = {sheet_key: {SHEETY_FLAG_COLUMN: SHEETY_FLAG_VALUE}}
                if service is not None:
                    success, _, error = service.make_request("PUT", str(int(row_id)), payload)
                    if not success:
                        if error and (error.startswith("HTTP 402") or "quota" in error.lower()):
                            break
                        if error and ("put has been disabled" in error.lower()):
                            break
                        continue
                elif url:
                    try:
                        response = requests.put(
                            f"{url.rstrip('/')}/{int(row_id)}",
                            headers=headers,
                            json=payload,
                            timeout=15,
                        )
                        if response.status_code == 402:
                            break
                        if response.status_code not in (200, 201, 204):
                            if response.status_code == 403 and "put has been disabled" in (response.text or "").lower():
                                break
                            continue
                    except Exception:
                        continue
                flagged += 1
        finally:
            _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["flagged_rows"] = int(flagged)

    Thread(target=_worker, daemon=True, name=f"sheet-flag-rows-{int(user_id)}").start()


def _run_sheet_rewrite_job(
    db_name: str,
    user_id: int,
    sheet_key: str,
    snapshot_id: int,
    existing_row_ids: List[Optional[int]],
) -> None:
    rewrite_lock = _REWRITE_LOCKS_BY_USER.setdefault(int(user_id), Lock())
    if not rewrite_lock.acquire(blocking=False):
        _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "in_progress"
        return

    cleanup_service = None
    cleanup_url: Optional[str] = None
    cleanup_headers: Dict[str, str] = {}
    try:
        if not try_begin_rewrite(db_name, int(user_id)):
            _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "in_progress"
            return

        _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "started"

        accounts = get_user_api_accounts(db_name, int(user_id))
        if accounts:
            try:
                from .sheety_failover import SheetyFailoverService

                cleanup_service = SheetyFailoverService(db_name, int(user_id))
            except Exception:
                cleanup_service = None

        if cleanup_service is None:
            url, headers = _get_sheety_endpoint(db_name, int(user_id))
            cleanup_url = url or None
            cleanup_headers = headers

        snapshot_rows = fetch_sheety_sync_snapshot_rows(db_name, int(snapshot_id))
        if not snapshot_rows:
            logger.warning("Sheet rewrite skipped: empty snapshot user_id=%s snapshot_id=%s", int(user_id), int(snapshot_id))
            _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "skipped_empty_snapshot"
            return

        rows_for_rewrite: List[Dict[str, Any]] = []
        for row_dict in snapshot_rows:
            raw_id = row_dict.get("id") if isinstance(row_dict, dict) else None
            sheety_id = None
            if isinstance(raw_id, float) and pd.isna(raw_id):
                sheety_id = None
            elif raw_id is not None:
                try:
                    sheety_id = int(raw_id)
                except (TypeError, ValueError):
                    sheety_id = None
            rows_for_rewrite.append(
                {
                    "row_dict": dict(row_dict) if isinstance(row_dict, dict) else {},
                    "sheety_id": sheety_id,
                }
            )

        updated_rows = _rewrite_sheet_rows(
            rows_for_rewrite,
            existing_row_ids,
            sheet_key,
            cleanup_service,
            cleanup_url,
            cleanup_headers,
        )
        if updated_rows is None:
            _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "failed"
            return

        rewrite_id_map: Dict[int, int] = {}
        for payload in updated_rows:
            prev_id = payload.get("previous_sheety_id")
            new_id = payload.get("sheety_id")
            if prev_id is None or new_id is None:
                continue
            try:
                rewrite_id_map[int(prev_id)] = int(new_id)
            except Exception:
                continue

        if rewrite_id_map:
            conn = get_db_connection(db_name)
            try:
                for old_id, new_id in rewrite_id_map.items():
                    conn.execute(
                        "UPDATE logs SET sheety_id = ? WHERE user_id = ? AND sheety_id = ?",
                        (int(new_id), int(user_id), int(old_id)),
                    )
                    conn.execute(
                        """
                        UPDATE sheety_outbox
                        SET endpoint = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ? AND status = 'pending' AND endpoint = ?
                        """,
                        (str(int(new_id)), int(user_id), str(int(old_id))),
                    )
                conn.commit()
            finally:
                conn.close()

        try:
            end_rewrite(db_name, int(user_id))
        except Exception:
            pass

        _replay_outbox(db_name, int(user_id), sheet_key, cleanup_service, rewrite_id_map)
        _LAST_SYNC_STATS_BY_USER.setdefault(int(user_id), {})["sheet_rewrite"] = "success"
    finally:
        try:
            if is_rewrite_in_progress(db_name, int(user_id)):
                end_rewrite(db_name, int(user_id))
        except Exception:
            pass
        rewrite_lock.release()


def _replay_outbox(
    db_name: str,
    user_id: int,
    default_sheet_key: str,
    replay_service: Optional["SheetyFailoverService"],
    rewrite_id_map: Dict[int, int],
) -> None:
    try:
        pending = fetch_pending_outbox(db_name, int(user_id), limit=200)
    except Exception:
        pending = []
    if not pending:
        return

    if replay_service is None:
        from .sheety_failover import SheetyFailoverService

        replay_service = SheetyFailoverService(db_name, int(user_id))

    for op in pending:
        outbox_id = int(op.get("id") or 0)
        method = str(op.get("method") or "").upper()
        endpoint = str(op.get("endpoint") or "")
        raw_json = op.get("json_data") or "{}"
        try:
            json_obj = json.loads(raw_json)
        except Exception:
            json_obj = {}

        resolved_endpoint = endpoint
        if endpoint.isdigit():
            try:
                old_id = int(endpoint)
                if old_id in rewrite_id_map:
                    resolved_endpoint = str(int(rewrite_id_map[old_id]))
            except Exception:
                pass

        sheet_name = str(op.get("sheet_key") or "").strip() or None
        if sheet_name is None and isinstance(json_obj, dict):
            for key in json_obj.keys():
                if key in {"__ttpro_meta", "__ttpro_bypass_outbox"}:
                    continue
                sheet_name = str(key)
                break
        if sheet_name is None:
            sheet_name = default_sheet_key

        meta = json_obj.get("__ttpro_meta") if isinstance(json_obj, dict) else None
        try:
            success, data, error = replay_service.make_request_bypass_outbox(
                method,
                resolved_endpoint,
                (json_obj if isinstance(json_obj, dict) else None),
            )
        except Exception as exc:
            success, data, error = False, None, str(exc)

        if success:
            mark_outbox_done(db_name, outbox_id)
        else:
            mark_outbox_failed(db_name, outbox_id, error or "sheety_request_failed")
            continue

        if method == "POST" and isinstance(meta, dict):
            new_id = _extract_sheety_row_id(data or {}, sheet_name)
            if new_id is not None:
                try:
                    update_local_sheety_id_for_created(
                        db_name,
                        int(user_id),
                        meta,
                        int(new_id),
                    )
                except Exception:
                    pass


def _get_sheety_endpoint(db_name: str, user_id: int) -> tuple[str, Dict[str, str]]:
    settings = get_user_settings(db_name, int(user_id))
    user_url = (settings.get("sheety_endpoint") or "").strip()
    env_url = (os.getenv(SHEETY_ENDPOINT_ENV) or "").strip()
    allow_env_fallback = get_user_count(db_name) <= 1
    url = user_url or (env_url if allow_env_fallback else "")
    if not url:
        return "", {}

    headers: Dict[str, str] = {}
    token = (settings.get("sheety_token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return url, headers


def _delete_duplicate_sheet_rows(
    duplicate_ids: List[int],
    sheet_key: str,
    cleanup_service: Optional["SheetyFailoverService"],
    cleanup_url: Optional[str],
    cleanup_headers: Dict[str, str],
) -> int:
    if not duplicate_ids:
        return 0
    deleted_count = 0
    for row_id in duplicate_ids:
        try:
            if cleanup_service is not None:
                success, _, error = cleanup_service.make_request_bypass_outbox("DELETE", str(row_id), None)
                if not success and error and error.startswith("HTTP 404"):
                    success = True
                if not success:
                    logger.warning("Failed to delete duplicate sheet row id=%s error=%s", row_id, error)
                    continue
            elif cleanup_url:
                url = f"{cleanup_url.rstrip('/')}/{row_id}"
                response = requests.delete(url, headers=cleanup_headers, timeout=15)
                if response.status_code not in (200, 204, 404):
                    logger.warning(
                        "Failed to delete duplicate sheet row id=%s status=%s",
                        row_id,
                        response.status_code,
                    )
                    continue
            else:
                logger.warning("No cleanup client available to delete duplicate row id=%s", row_id)
                continue
            deleted_count += 1
        except Exception as exc:
            logger.warning("Error deleting duplicate sheet row id=%s error=%s", row_id, exc)
    return deleted_count


def _extract_sheety_row_id(response_data: Any, sheet_key: str) -> Optional[int]:
    if not isinstance(response_data, dict):
        return None
    candidate = response_data.get(sheet_key)
    if isinstance(candidate, dict) and candidate.get("id") is not None:
        try:
            return int(candidate.get("id"))
        except (TypeError, ValueError):
            return None
    if response_data.get("id") is not None:
        try:
            return int(response_data.get("id"))
        except (TypeError, ValueError):
            return None
    for value in response_data.values():
        if isinstance(value, dict) and value.get("id") is not None:
            try:
                return int(value.get("id"))
            except (TypeError, ValueError):
                return None
    return None


def _clean_sheet_row_payload(raw_row: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for key, value in raw_row.items():
        if key in {"id", "__logged_dt"}:
            continue
        if isinstance(value, float) and pd.isna(value):
            continue
        payload[key] = value
    return payload


def _rewrite_sheet_rows(
    rows: List[Dict[str, Any]],
    existing_row_ids: List[Optional[int]],
    sheet_key: str,
    cleanup_service: Optional["SheetyFailoverService"],
    cleanup_url: Optional[str],
    cleanup_headers: Dict[str, str],
) -> Optional[List[Dict[str, Any]]]:
    if not cleanup_service and not cleanup_url:
        logger.warning("Skipping sheet rewrite: no cleanup client available.")
        return None

    baseline_ids: List[int] = []
    for row_id in existing_row_ids:
        if row_id is None:
            continue
        try:
            baseline_ids.append(int(row_id))
        except Exception:
            continue
    baseline_set = set(baseline_ids)

    current_rows: List[Dict[str, Any]] = []
    try:
        if cleanup_service is not None:
            success, data, error = cleanup_service.make_request_bypass_outbox("GET", "", None)
            if not success:
                logger.warning("Failed to fetch current sheet rows before rewrite error=%s", error)
            elif isinstance(data, dict):
                current_rows = list(data.get(sheet_key) or [])
        elif cleanup_url:
            response = requests.get(cleanup_url, headers=cleanup_headers, timeout=15)
            if response.status_code == 200:
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                if isinstance(payload, dict):
                    current_rows = list(payload.get(sheet_key) or [])
    except Exception as exc:
        logger.warning("Error fetching current sheet rows before rewrite error=%s", exc)

    baseline_rows: List[Dict[str, Any]] = []
    tail_rows: List[Dict[str, Any]] = []
    violates_tail_assumption = False
    if current_rows and baseline_set:
        seen_tail = False
        for raw in current_rows:
            if not isinstance(raw, dict):
                continue
            raw_id = raw.get("id")
            rid = None
            if isinstance(raw_id, float) and pd.isna(raw_id):
                rid = None
            elif raw_id is not None:
                try:
                    rid = int(raw_id)
                except (TypeError, ValueError):
                    rid = None
            if rid is None:
                continue
            in_baseline = rid in baseline_set
            if not in_baseline:
                seen_tail = True
            elif seen_tail:
                violates_tail_assumption = True

            if in_baseline:
                baseline_rows.append(raw)
            else:
                tail_rows.append(raw)

    if tail_rows and violates_tail_assumption:
        logger.warning(
            "Tail-safe rewrite skipped: detected baseline rows after tail; sheet was edited in the middle during rewrite.",
        )
        return None

    if tail_rows and not baseline_rows:
        logger.warning(
            "Tail-safe rewrite skipped: could not identify baseline rows while tail rows exist.",
        )
        return None

    if tail_rows and baseline_rows:
        ordered_baseline_ids: List[int] = []
        original_by_id: Dict[int, Dict[str, Any]] = {}
        for raw in baseline_rows:
            rid = raw.get("id")
            try:
                rid_int = int(rid)
            except Exception:
                continue
            ordered_baseline_ids.append(int(rid_int))
            original_by_id[int(rid_int)] = dict(raw)

        if len(ordered_baseline_ids) < len(rows):
            logger.warning(
                "Tail-safe rewrite skipped: baseline rows smaller than snapshot user_id=%s baseline=%s snapshot=%s tail=%s",
                int(getattr(cleanup_service, "user_id", 0) or 0),
                len(ordered_baseline_ids),
                len(rows),
                len(tail_rows),
            )
            return None

        def _put_row(row_id: int, row_payload: Dict[str, Any]) -> bool:
            try:
                if cleanup_service is not None:
                    success, _, error = cleanup_service.make_request_bypass_outbox(
                        "PUT",
                        str(int(row_id)),
                        {sheet_key: row_payload},
                    )
                    if not success:
                        logger.warning("Failed to update sheet row id=%s error=%s", int(row_id), error)
                        return False
                    return True
                if cleanup_url:
                    url = f"{cleanup_url.rstrip('/')}/{int(row_id)}"
                    response = requests.put(
                        url,
                        headers=cleanup_headers,
                        json={sheet_key: row_payload},
                        timeout=15,
                    )
                    if response.status_code in (200, 201, 204):
                        return True
                    logger.warning(
                        "Failed to update sheet row id=%s status=%s",
                        int(row_id),
                        response.status_code,
                    )
                    return False
            except Exception as exc:
                logger.warning("Error updating sheet row id=%s error=%s", int(row_id), exc)
                return False
            return False

        updated_rows: List[Dict[str, Any]] = []
        updated_target_ids: List[int] = []
        for idx, payload in enumerate(rows):
            payload["previous_sheety_id"] = payload.get("sheety_id")
            target_id = int(ordered_baseline_ids[idx])
            cleaned = _clean_sheet_row_payload(dict(payload.get("row_dict") or {}))
            if not _put_row(target_id, cleaned):
                for rollback_id in updated_target_ids:
                    original = original_by_id.get(int(rollback_id))
                    if not original:
                        continue
                    original_cleaned = _clean_sheet_row_payload(original)
                    _put_row(int(rollback_id), original_cleaned)
                return None
            payload["sheety_id"] = int(target_id)
            updated_rows.append(payload)
            updated_target_ids.append(int(target_id))

        delete_ids = [int(x) for x in ordered_baseline_ids[len(rows) :] if x is not None]
        pending_delete = list(delete_ids)
        for attempt in range(3):
            if not pending_delete:
                break
            failed: List[int] = []
            for row_id in pending_delete:
                if not _delete_row(int(row_id)):
                    failed.append(int(row_id))
            pending_delete = failed
            if pending_delete and attempt < 2:
                time.sleep(0.25)

        if pending_delete:
            logger.warning(
                "Tail-safe rewrite could not delete %s/%s old baseline rows; leaving them in place.",
                len(pending_delete),
                len(delete_ids),
            )

        return updated_rows

    def _delete_row(row_id: int) -> bool:
        try:
            if cleanup_service is not None:
                success, _, error = cleanup_service.make_request_bypass_outbox("DELETE", str(row_id), None)
                if not success and error and error.startswith("HTTP 404"):
                    return True
                if not success:
                    logger.warning("Failed to delete sheet row id=%s error=%s", row_id, error)
                    return False
                return True
            if cleanup_url:
                url = f"{cleanup_url.rstrip('/')}/{row_id}"
                response = requests.delete(url, headers=cleanup_headers, timeout=15)
                if response.status_code in (200, 204, 404):
                    return True
                if response.status_code not in (200, 204, 404):
                    logger.warning(
                        "Failed to delete sheet row id=%s status=%s",
                        row_id,
                        response.status_code,
                    )
                    return False
        except Exception as exc:
            logger.warning("Error deleting sheet row id=%s error=%s", row_id, exc)
            return False
        return False

    updated_rows: List[Dict[str, Any]] = []
    created_row_ids: List[int] = []

    for payload in rows:
        payload["previous_sheety_id"] = payload.get("sheety_id")
        row_dict = payload.get("row_dict") or {}
        cleaned = _clean_sheet_row_payload(row_dict)
        data: Any = None
        try:
            if cleanup_service is not None:
                success, data, error = cleanup_service.make_request_bypass_outbox(
                    "POST",
                    "",
                    {sheet_key: cleaned},
                )
                if not success:
                    logger.warning("Failed to create sorted sheet row error=%s", error)
                    for created_id in created_row_ids:
                        _delete_row(created_id)
                    return None
            elif cleanup_url:
                response = requests.post(
                    cleanup_url,
                    headers=cleanup_headers,
                    json={sheet_key: cleaned},
                    timeout=15,
                )
                if response.status_code not in (200, 201):
                    logger.warning(
                        "Failed to create sorted sheet row status=%s",
                        response.status_code,
                    )
                    for created_id in created_row_ids:
                        _delete_row(created_id)
                    return None
                try:
                    data = response.json()
                except ValueError:
                    data = None
            else:
                for created_id in created_row_ids:
                    _delete_row(created_id)
                return None
        except Exception as exc:
            logger.warning("Error creating sorted sheet row error=%s", exc)
            for created_id in created_row_ids:
                _delete_row(created_id)
            return None

        new_id = _extract_sheety_row_id(data or {}, sheet_key)
        if new_id is None:
            logger.warning("Failed to capture new Sheety row id while rewriting sorted sheet rows")
            for created_id in created_row_ids:
                _delete_row(created_id)
            return None

        payload["sheety_id"] = int(new_id)
        created_row_ids.append(int(new_id))
        updated_rows.append(payload)

    row_ids = sorted(set(baseline_ids))

    pending_delete = list(row_ids)
    for attempt in range(3):
        if not pending_delete:
            break
        failed: List[int] = []
        for row_id in pending_delete:
            if not _delete_row(int(row_id)):
                failed.append(int(row_id))
        pending_delete = failed
        if pending_delete and attempt < 2:
            time.sleep(0.25)

    if pending_delete:
        logger.warning(
            "Sheet rewrite failed to delete %s/%s old rows; rolling back newly created rows.",
            len(pending_delete),
            len(row_ids),
        )
        rollback_pending = list(created_row_ids)
        for attempt in range(4):
            if not rollback_pending:
                break
            failed: List[int] = []
            for row_id in rollback_pending:
                if not _delete_row(int(row_id)):
                    failed.append(int(row_id))
            rollback_pending = failed
            if rollback_pending and attempt < 3:
                time.sleep(0.5)

        if rollback_pending:
            logger.warning(
                "Rollback left %s/%s newly created rows in place after failed rewrite.",
                len(rollback_pending),
                len(created_row_ids),
            )
        return None

    return updated_rows


def get_last_sync_stats(user_id: int) -> Dict[str, Any]:
    return _LAST_SYNC_STATS_BY_USER.get(int(user_id), {})
