from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

from ..core.tags import filter_special_tags, normalize_tag
from ..repositories.logs import replace_logs_for_user
from ..repositories.settings import get_user_settings
from ..repositories.sheety_accounts import get_user_api_accounts
from ..repositories.users import get_user_count
from .parser import TimeLogParser


logger = logging.getLogger(__name__)

SHEETY_ENDPOINT_ENV = "SHEETY_ENDPOINT"
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "300"))
SYNC_FAIL_COOLDOWN_SECONDS = int(os.getenv("SYNC_FAIL_COOLDOWN_SECONDS", "1800"))

_LAST_SYNC_TS_BY_USER: Dict[int, datetime] = {}
_LAST_SYNC_FAIL_TS_BY_USER: Dict[int, datetime] = {}
_LAST_SYNC_STATS_BY_USER: Dict[int, Dict[str, Any]] = {}


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
        "duplicate_candidates": 0,
        "duplicate_preview": [],
        "skipped_reason": "",
    }

    try:
        payload: Optional[Dict[str, Any]] = None
        cleanup_service = None
        cleanup_url: Optional[str] = None
        cleanup_headers: Dict[str, str] = {}
        accounts = get_user_api_accounts(db_name, int(user_id))
        if accounts:
            from .sheety_failover import SheetyFailoverService

            service = SheetyFailoverService(db_name, int(user_id))
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
                            _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now - timedelta(hours=23)
                            _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "failed"
                            _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "sheety_subscription_required"
                            return failover_notice
                        response.raise_for_status()
                        payload = response.json()
                        cleanup_url = fallback_url
                        cleanup_headers = fallback_headers
                        used_fallback = True
                    except requests.RequestException as exc:
                        _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now
                        _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "failed"
                        _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = error or str(exc)
                        return failover_notice
                else:
                    _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now
                    _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "failed"
                    _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = error or "sheety_request_failed"
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
                _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now - timedelta(hours=23)
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["status"] = "failed"
                _LAST_SYNC_STATS_BY_USER[int(user_id)]["skipped_reason"] = "sheety_subscription_required"
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
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["source_rows"] = len(cloud_df)
        if "id" in cloud_df.columns:
            cloud_df = cloud_df.sort_values("id")

        logged_col = None
        for candidate in ("loggedTime", "logged_time", "logged time"):
            if candidate in cloud_df.columns:
                logged_col = candidate
                break
        if logged_col:
            try:
                cloud_df["__logged_dt"] = pd.to_datetime(cloud_df[logged_col], errors="coerce")
                sort_cols = ["__logged_dt"]
                if "id" in cloud_df.columns:
                    sort_cols.append("id")
                cloud_df = cloud_df.sort_values(sort_cols)
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

        parser = TimeLogParser()
        parsed_rows: List[Dict[str, Any]] = []
        previous_end: Optional[datetime] = None
        seen_source_rows: Dict[tuple[str, str], Dict[str, Any]] = {}
        duplicate_sheety_ids: List[int] = []
        duplicate_groups: Dict[tuple[str, str], Dict[str, Any]] = {}

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

            source_key = (normalize_log_entry(log_entry), str(client_now or "").strip())
            if source_key in seen_source_rows:
                first = seen_source_rows.get(source_key) or {}
                group = duplicate_groups.get(source_key)
                if group is None:
                    group = {
                        "logged_time": source_key[1],
                        "normalized_log_entry": source_key[0],
                        "sample_log_entry": first.get("log_entry") or "",
                        "row_ids": [],
                    }
                    if first.get("sheety_id") is not None:
                        group["row_ids"].append(int(first["sheety_id"]))
                    duplicate_groups[source_key] = group
                if sheety_id is not None:
                    group["row_ids"].append(int(sheety_id))
                    duplicate_sheety_ids.append(int(sheety_id))
                continue
            seen_source_rows[source_key] = {"sheety_id": sheety_id, "log_entry": log_entry}

            try:
                parsed = parser.parse_row(log_entry, client_now, previous_end)
            except Exception as exc:
                logger.warning(
                    "Skipping invalid row during cloud sync user_id=%s logged_time=%s log_entry=%r error=%s",
                    int(user_id),
                    client_now,
                    log_entry,
                    exc,
                )
                continue

            if parsed.get("end_dt") is not None and parsed.get("start_dt") is not None and parsed["end_dt"] <= parsed["start_dt"]:
                target_end = parsed["end_dt"]
                candidate_start: Optional[datetime] = None
                for prior in reversed(parsed_rows):
                    prior_end = prior.get("end_dt")
                    if prior_end is None:
                        continue
                    if prior_end <= target_end:
                        candidate_start = prior_end
                        break
                if candidate_start is not None and candidate_start < target_end:
                    parsed["start_dt"] = candidate_start

            if sheety_id is not None:
                parsed["sheety_id"] = sheety_id

            parsed["task"] = normalize_task_name(parsed.get("task"))
            parsed["tag"] = normalize_tag(parsed.get("tag")) or "Waste"
            parsed_rows.append(parsed)
            if previous_end is None:
                previous_end = parsed["end_dt"]
            elif parsed.get("end_dt") is not None:
                previous_end = max(previous_end, parsed["end_dt"])

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

        parsed_rows.sort(
            key=lambda row: (
                row["start_dt"],
                row["end_dt"],
                row.get("task") or "",
                row.get("tag") or "",
                bool(row.get("urg")),
                bool(row.get("imp")),
            )
        )
        deduped_rows: List[Dict[str, Any]] = []
        seen_rows = set()
        for row in parsed_rows:
            key = (
                row["start_dt"],
                row["end_dt"],
                row.get("task") or "",
                row.get("tag") or "",
                bool(row.get("urg")),
                bool(row.get("imp")),
            )
            if key in seen_rows:
                continue
            seen_rows.add(key)
            deduped_rows.append(row)
        parsed_rows = deduped_rows
        _LAST_SYNC_STATS_BY_USER[int(user_id)]["deduped_rows"] = len(parsed_rows)

        for i in range(1, len(parsed_rows)):
            current = parsed_rows[i]
            prev = parsed_rows[i - 1]
            if current["start_dt"] < prev["end_dt"]:
                parsed_rows[i - 1]["end_dt"] = current["start_dt"]

        merged_rows: List[Dict[str, Any]] = []
        for row in parsed_rows:
            if (
                merged_rows
                and row.get("task") == merged_rows[-1].get("task")
                and row.get("tag") == merged_rows[-1].get("tag")
                and bool(row.get("urg")) == bool(merged_rows[-1].get("urg"))
                and bool(row.get("imp")) == bool(merged_rows[-1].get("imp"))
                and row["start_dt"] == merged_rows[-1]["end_dt"]
            ):
                if row["end_dt"] > merged_rows[-1]["end_dt"]:
                    merged_rows[-1]["end_dt"] = row["end_dt"]
                if merged_rows[-1].get("sheety_id") is None and row.get("sheety_id") is not None:
                    merged_rows[-1]["sheety_id"] = row.get("sheety_id")
                continue
            merged_rows.append(row)
        parsed_rows = merged_rows
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

        if duplicate_sheety_ids:
            deleted_count = _delete_duplicate_sheet_rows(
                duplicate_sheety_ids,
                sheet_key,
                cleanup_service,
                cleanup_url,
                cleanup_headers,
            )
            _LAST_SYNC_STATS_BY_USER[int(user_id)]["deleted_duplicates"] = deleted_count
        _LAST_SYNC_TS_BY_USER[int(user_id)] = now
        return failover_notice
    except requests.RequestException as exc:
        _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now
        if hasattr(exc, "response") and exc.response is not None and exc.response.status_code == 402:
            _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now - timedelta(hours=23)
            return failover_notice
        logger.error("Network error during cloud sync: %s", exc)
    except Exception as exc:
        _LAST_SYNC_FAIL_TS_BY_USER[int(user_id)] = now
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
                success, _, error = cleanup_service.make_request("DELETE", str(row_id), None)
                if not success:
                    logger.warning("Failed to delete duplicate sheet row id=%s error=%s", row_id, error)
                    continue
            elif cleanup_url:
                url = f"{cleanup_url.rstrip('/')}/{row_id}"
                response = requests.delete(url, headers=cleanup_headers, timeout=15)
                if response.status_code not in (200, 204):
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


def get_last_sync_stats(user_id: int) -> Dict[str, Any]:
    return _LAST_SYNC_STATS_BY_USER.get(int(user_id), {})
