from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from dateutil import parser as date_parser


class TimeLogParser:
    def __init__(self) -> None:
        self.time_pattern = re.compile(
            r"^(\d{1,2})(?:[:\s]?(\d{2}))?\s*([ap]m)?\s*",
            re.IGNORECASE,
        )
        self.time_token_pattern = re.compile(
            r"^(\d{1,2})(?:[:\s]?(\d{2}))?\s*([ap]m)?$",
            re.IGNORECASE,
        )
        self.date_token_pattern = re.compile(r"^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?$")

    def _infer_12h_time(self, hour: int, minute: int, ref_date: datetime) -> Tuple[int, int]:
        ref_minutes = ref_date.hour * 60 + ref_date.minute
        if hour == 12:
            candidates = [(0, minute), (12, minute)]
        else:
            candidates = [(hour, minute), (hour + 12, minute)]

        best = candidates[0]
        best_delta = 24 * 60
        for h, m in candidates:
            cand_minutes = h * 60 + m
            delta = ref_minutes - cand_minutes
            if delta < 0:
                delta += 24 * 60
            if delta < best_delta:
                best_delta = delta
                best = (h, m)
        return best

    def _month_from_token(self, token: str) -> Optional[int]:
        normalized = (token or "").strip().lower().strip(".,")
        if not normalized:
            return None
        months = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "sept": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        return months.get(normalized)

    def _parse_split_date(self, tokens: list[str], idx: int, ref_date: datetime) -> tuple[Optional[datetime.date], int]:
        if idx >= len(tokens) or idx + 1 >= len(tokens):
            return None, 0
        day_token = (tokens[idx] or "").strip().strip(".,")
        if not re.fullmatch(r"\d{1,2}", day_token):
            return None, 0
        day = int(day_token)
        if not (1 <= day <= 31):
            return None, 0
        month_token = (tokens[idx + 1] or "").strip()
        if not re.search(r"[A-Za-z]", month_token):
            return None, 0
        month = self._month_from_token(month_token)
        if month is None:
            return None, 0

        consumed = 2
        year = ref_date.year
        if idx + 2 < len(tokens):
            year_token = (tokens[idx + 2] or "").strip().strip(".,")
            if re.fullmatch(r"\d{2,4}", year_token):
                if (
                    len(year_token) == 2
                    and idx + 3 < len(tokens)
                    and (tokens[idx + 3] or "").strip().lower().strip(".,") in {"am", "pm", "a", "p", "a.m", "p.m", "a.m.", "p.m."}
                ):
                    return datetime(year, month, day).date(), consumed
                year = int(year_token)
                if len(year_token) == 2:
                    year += 2000
                consumed = 3
        if consumed == 2 and month > ref_date.month + 1:
            year -= 1
        try:
            return datetime(year, month, day).date(), consumed
        except ValueError:
            return None, 0

    def parse_time_string(self, text_str: str, ref_date: datetime) -> Tuple[Optional[datetime], str]:
        if not isinstance(text_str, str) or not text_str:
            return None, text_str
        match = self.time_pattern.match(text_str)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2) or 0)
            ampm = match.group(3).lower() if match.group(3) else None
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            dt = ref_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            return dt, text_str[match.end() :].strip()
        return None, text_str

    def _parse_time_token(self, token: str, ref_date: datetime) -> Optional[Tuple[int, int]]:
        raw = (token or "").strip().lower().strip(".,")
        if not raw:
            return None

        if re.fullmatch(r"\d{3,4}", raw):
            if len(raw) == 3:
                hour = int(raw[0])
                minute = int(raw[1:])
            else:
                hour = int(raw[:2])
                minute = int(raw[2:])
            if hour > 23 or minute > 59:
                return None
            return hour, minute

        if re.fullmatch(r"\d{1,2}\.\d{2}([ap]m)?", raw, re.IGNORECASE):
            raw = raw.replace(".", ":", 1)

        m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?([ap]m)?", raw)
        if not m:
            return None

        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = (m.group(3) or "").lower() or None

        if minute > 59:
            return None

        if ampm:
            if not (1 <= hour <= 12):
                return None
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return hour, minute

        if hour > 23:
            return None

        if m.group(2) is None:
            return hour, minute

        if hour >= 13:
            return hour, minute
        inferred_hour, inferred_minute = self._infer_12h_time(hour, minute, ref_date)
        return inferred_hour, inferred_minute

    def _parse_date_token(self, token: str, ref_date: datetime) -> Optional[datetime.date]:
        match = self.date_token_pattern.match(token)
        if not match:
            if re.search(r"[ap]m", token, re.IGNORECASE) or ":" in token:
                return None
            if re.search(r"\d", token) or re.search(r"[./-]", token) or re.fullmatch(r"\d{4}", token):
                try:
                    parsed = date_parser.parse(token, default=ref_date, dayfirst=True, fuzzy=False)
                    return parsed.date()
                except Exception:
                    return None
            return None
        day = int(match.group(1))
        month = int(match.group(2))
        year_str = match.group(3)
        if year_str:
            year = int(year_str)
            if len(year_str) == 2:
                year += 2000
        else:
            year = ref_date.year
            if month > ref_date.month + 1:
                year -= 1
        try:
            return datetime(year, month, day).date()
        except ValueError:
            return None

    def _combine_dt(self, date_value: datetime.date, time_value: Tuple[int, int]) -> datetime:
        base = datetime.combine(date_value, datetime.min.time())
        return base.replace(hour=time_value[0], minute=time_value[1], second=0, microsecond=0)

    def _is_time_after(self, t1: Tuple[int, int], t2: Tuple[int, int]) -> bool:
        return (t1[0], t1[1]) > (t2[0], t2[1])

    def parse_row(
        self,
        log_entry: str,
        client_now_str: str,
        previous_end_dt: Optional[datetime],
    ) -> Dict[str, Any]:
        client_now: datetime
        if client_now_str:
            try:
                client_now = datetime.strptime(str(client_now_str).strip(), "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    client_now = pd.to_datetime(client_now_str)
                    if pd.isna(client_now):
                        raise ValueError
                except Exception:
                    client_now = datetime.now()
        else:
            client_now = datetime.now()

        if log_entry is None or (isinstance(log_entry, float) and pd.isna(log_entry)):
            raw_entry = ""
        else:
            raw_entry = str(log_entry)

        tokens = raw_entry.strip().split()
        elements = []
        dot_positions = []
        consumed = 0

        def _ampm_normalized(token: str) -> Optional[str]:
            normalized = token.strip().lower().strip(".,")
            if normalized in {"am", "a.m", "a.m.", "a"}:
                return "am"
            if normalized in {"pm", "p.m", "p.m.", "p"}:
                return "pm"
            return None

        def _is_explicit_time_like(token: str) -> bool:
            raw = (token or "").strip().lower().strip(".,")
            if not raw:
                return False
            if _ampm_normalized(raw):
                return True
            if re.fullmatch(r"\d{1,2}([ap]m)", raw, re.IGNORECASE):
                return True
            if re.fullmatch(r"\d{1,2}[:.]\d{1,2}([ap]m)?", raw, re.IGNORECASE):
                return True
            if re.fullmatch(r"\d{3,4}", raw):
                return True
            return False

        leading_date_has_comma = False
        i = 0
        while i < len(tokens):
            token = tokens[i]
            trailing_dot = token.endswith(".")
            cleaned = token.rstrip(".").rstrip(",")

            split_date, split_consumed = self._parse_split_date(tokens, i, client_now)
            if split_date is not None and split_consumed:
                trailing_dot = trailing_dot or any(
                    (tokens[i + j] or "").strip().endswith(".") for j in range(split_consumed)
                )
                if i == 0 and any((tokens[i + j] or "").strip().endswith(",") for j in range(split_consumed)):
                    leading_date_has_comma = True
                elements.append(("date", split_date))
                dot_positions.append(trailing_dot)
                consumed += split_consumed
                i += split_consumed
                if len(elements) >= 4:
                    break
                continue

            # Disambiguate leading numeric day tokens like:
            # - "21. 1:53 pm 1:40 ..." (dot means date marker)
            # - "22 11:59 ..." (day + explicit time)
            if i == 0 and re.fullmatch(r"\d{1,2}", cleaned):
                day_num = int(cleaned)
                next_token = tokens[i + 1] if i + 1 < len(tokens) else ""
                next_next_token = tokens[i + 2] if i + 2 < len(tokens) else ""
                next_is_split_minute_ampm = (
                    re.fullmatch(r"\d{2}", (next_token or "").strip().strip(".,"))
                    is not None
                    and _ampm_normalized(next_next_token) is not None
                )
                has_explicit_following_time = _is_explicit_time_like(next_token) or next_is_split_minute_ampm
                should_prefer_date = (trailing_dot and has_explicit_following_time) or (
                    day_num >= 13 and has_explicit_following_time
                )
                if should_prefer_date:
                    forced_date = self._parse_date_token(cleaned, client_now)
                    if forced_date is not None:
                        elements.append(("date", forced_date))
                        dot_positions.append(trailing_dot)
                        consumed += 1
                        i += 1
                        if len(elements) >= 4:
                            break
                        continue

            time_val = None
            consumed_extra = 0

            # Support split 12-hour forms like "12 14 pm".
            if i + 2 < len(tokens) and re.fullmatch(r"\d{1,2}", cleaned):
                minute_token = tokens[i + 1].strip().strip(".,")
                ampm2 = _ampm_normalized(tokens[i + 2])
                if re.fullmatch(r"\d{2}", minute_token) and ampm2:
                    merged = f"{cleaned}:{minute_token}{ampm2}"
                    merged_time = self._parse_time_token(merged, client_now)
                    if merged_time is not None:
                        time_val = merged_time
                        consumed_extra = 2
                        trailing_dot = (
                            trailing_dot
                            or tokens[i + 1].endswith(".")
                            or tokens[i + 2].endswith(".")
                        )

            # Support split 12-hour forms like "5 pm".
            if time_val is None and i + 1 < len(tokens) and re.fullmatch(r"\d{1,2}", cleaned):
                ampm = _ampm_normalized(tokens[i + 1])
                if ampm:
                    merged = f"{cleaned}{ampm}"
                    merged_time = self._parse_time_token(merged, client_now)
                    if merged_time is not None:
                        time_val = merged_time
                        consumed_extra = 1
                        trailing_dot = trailing_dot or tokens[i + 1].endswith(".")

            if time_val is None:
                time_val = self._parse_time_token(cleaned, client_now)

            if time_val is not None and i + 1 < len(tokens):
                ampm = _ampm_normalized(tokens[i + 1])
                if ampm and not re.search(r"[ap]m\.?$", cleaned, re.IGNORECASE):
                    merged = f"{cleaned}{ampm}"
                    merged_time = self._parse_time_token(merged, client_now)
                    if merged_time is not None:
                        time_val = merged_time
                        if consumed_extra == 0:
                            consumed_extra = 1
                        trailing_dot = trailing_dot or tokens[i + 1].endswith(".")

            date_val = self._parse_date_token(cleaned, client_now)
            if i == 0 and date_val and token.endswith(","):
                leading_date_has_comma = True
            if time_val:
                elements.append(("time", time_val))
                dot_positions.append(trailing_dot)
            elif date_val:
                elements.append(("date", date_val))
                dot_positions.append(trailing_dot)
            else:
                break
            consumed += 1 + consumed_extra
            i += 1 + consumed_extra
            if len(elements) >= 4:
                break

        if i == 0:
            i = consumed

        remaining_tokens = tokens[consumed:]
        explicit_logged_dt = None
        if (
            leading_date_has_comma
            and len(elements) >= 2
            and elements[0][0] == "date"
            and elements[1][0] == "time"
            and not any(kind == "date" for kind, _ in elements[2:])
        ):
            explicit_logged_dt = self._combine_dt(elements[0][1], elements[1][1])
            client_now = explicit_logged_dt
            elements = elements[2:]
            dot_positions = dot_positions[2:]

        dot_after_first = dot_positions[0] if dot_positions else False
        dot_after_last = dot_positions[-1] if dot_positions else False
        if remaining_tokens and remaining_tokens[0].startswith("."):
            dot_after_last = True
            remaining_tokens[0] = remaining_tokens[0].lstrip(".")
            if not remaining_tokens[0]:
                remaining_tokens = remaining_tokens[1:]

        raw_text = " ".join(remaining_tokens).strip() or "Unspecified"
        task_name, tag = raw_text.strip(), ""
        is_urg, is_imp = False, False

        tags = []

        def apply_token(raw_token: str) -> None:
            nonlocal is_urg, is_imp
            token = re.sub(r"[^A-Za-z]+", "", raw_token).lower()
            if not token:
                return
            if token in {"urg", "urgent"}:
                is_urg = True
                return
            if token in {"imp", "important"}:
                is_imp = True
                return
            if token in {"work", "necessity", "soul", "rest", "waste"}:
                canonical = token.title()
                if canonical not in tags:
                    tags.append(canonical)
                return

        def is_meta_token(raw_token: str) -> bool:
            token = re.sub(r"[^A-Za-z]+", "", raw_token).lower()
            return token in {"urg", "urgent", "imp", "important", "work", "necessity", "soul", "rest", "waste"}

        def has_meta_tokens(tokens: list[str]) -> bool:
            return any(is_meta_token(tok) for tok in tokens)

        task_tokens = None
        meta_tokens = None
        for idx, token in enumerate(remaining_tokens):
            candidate_task = None
            candidate_meta = None
            if token == ".":
                candidate_task = remaining_tokens[:idx]
                candidate_meta = remaining_tokens[idx + 1 :]
            elif token.endswith(".") and token != ".":
                candidate_task = remaining_tokens[:idx] + [token[:-1]]
                candidate_meta = remaining_tokens[idx + 1 :]
            elif token.startswith(".") and token != ".":
                candidate_task = remaining_tokens[:idx]
                candidate_meta = [token[1:]] + remaining_tokens[idx + 1 :]

            if candidate_meta and has_meta_tokens(candidate_meta):
                task_tokens = candidate_task
                meta_tokens = candidate_meta
                break

        if meta_tokens is not None:
            task_name = " ".join(task_tokens).strip() or task_name
            for tok in meta_tokens:
                for part in re.split(r"[\s,]+", tok):
                    apply_token(part)

        tag = ", ".join(tags) if tags else "Waste"

        def fallback_start(end_dt: datetime) -> datetime:
            return previous_end_dt or end_dt

        current_date = client_now.date()
        start_dt = previous_end_dt or client_now
        end_dt = client_now
        has_explicit_logged_time = explicit_logged_dt is not None

        if len(elements) == 0:
            start_dt = previous_end_dt or client_now
            end_dt = client_now
        elif len(elements) == 1 and elements[0][0] == "time":
            t1 = elements[0][1]
            if has_explicit_logged_time:
                start_dt = self._combine_dt(current_date, t1)
                if start_dt > client_now:
                    start_dt = start_dt - timedelta(days=1)
                end_dt = client_now
            elif dot_after_last:
                start_dt = self._combine_dt(current_date, t1)
                if start_dt > client_now:
                    start_dt = start_dt - timedelta(days=1)
                end_dt = client_now
            else:
                candidate_dt = self._combine_dt(current_date, t1)
                if candidate_dt > client_now:
                    candidate_dt = candidate_dt - timedelta(days=1)
                if previous_end_dt is None:
                    start_dt = candidate_dt
                    end_dt = candidate_dt
                elif candidate_dt < previous_end_dt:
                    start_dt = candidate_dt
                    end_dt = client_now
                else:
                    end_dt = candidate_dt
                    start_dt = fallback_start(end_dt)
        elif len(elements) == 2:
            times = [val for kind, val in elements if kind == "time"]
            dates = [val for kind, val in elements if kind == "date"]
            if len(times) == 1 and len(dates) == 1:
                t1 = times[0]
                d1 = dates[0]
                if dot_after_last:
                    start_dt = self._combine_dt(d1, t1)
                    end_dt = client_now
                else:
                    end_dt = self._combine_dt(d1, t1)
                    start_dt = fallback_start(end_dt)
            elif len(times) == 2:
                t1, t2 = times[0], times[1]
                start_date = current_date - timedelta(days=1) if self._is_time_after(t1, t2) else current_date
                start_dt = self._combine_dt(start_date, t1)
                end_dt = self._combine_dt(current_date, t2)
        elif len(elements) == 3:
            if elements[0][0] == "date" and sum(1 for kind, _ in elements if kind == "time") == 2:
                d1 = elements[0][1]
                times = [val for kind, val in elements if kind == "time"]
                t1, t2 = times[0], times[1]
                if dot_after_first:
                    start_dt = self._combine_dt(d1, t1)
                    end_dt = self._combine_dt(current_date, t2)
                else:
                    end_date = d1 + timedelta(days=1) if self._is_time_after(t1, t2) else d1
                    start_dt = self._combine_dt(d1, t1)
                    end_dt = self._combine_dt(end_date, t2)
        elif len(elements) == 4:
            if (
                elements[0][0] == "date"
                and elements[1][0] == "time"
                and elements[2][0] == "date"
                and elements[3][0] == "time"
            ):
                start_dt = self._combine_dt(elements[0][1], elements[1][1])
                end_dt = self._combine_dt(elements[2][1], elements[3][1])

        if previous_end_dt is None and start_dt == client_now and end_dt != client_now:
            start_dt = end_dt

        return {
            "start_dt": start_dt,
            "end_dt": end_dt,
            "task": task_name,
            "tag": tag,
            "urg": is_urg,
            "imp": is_imp,
        }
