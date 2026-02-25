import unittest
from datetime import datetime
from itertools import product

import pandas as pd

from time_tracker_pro.services.parser import TimeLogParser


class LogEntryParserRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = TimeLogParser()
        self.now = datetime(2026, 1, 21, 10, 0)
        self.now_str = "2026-01-21 10:00"

    def parse(self, entry: str, previous_end: datetime | None = None) -> dict:
        return self.parser.parse_row(entry, self.now_str, previous_end)

    def parse_with_now(self, entry: str, now_str: str, previous_end: datetime | None = None) -> dict:
        return self.parser.parse_row(entry, now_str, previous_end)

    def parse_rows_like_sync(self, rows: list[tuple[str, str]]) -> list[dict]:
        parser = TimeLogParser()
        max_sort_dt = datetime(9999, 12, 31, 23, 59, 59)

        def to_naive(value: object) -> datetime | None:
            if isinstance(value, pd.Timestamp):
                if pd.isna(value):
                    return None
                value = value.to_pydatetime()
            if isinstance(value, datetime):
                if value.tzinfo is not None:
                    return value.replace(tzinfo=None)
                return value
            return None

        def parse_logged_datetime(value: object) -> datetime | None:
            parsed_direct = to_naive(value)
            if parsed_direct is not None:
                return parsed_direct

            text = str(value or "").strip()
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

            parsed_default = to_naive(pd.to_datetime(text, errors="coerce"))
            if parsed_default is not None:
                return parsed_default

            return to_naive(pd.to_datetime(text, errors="coerce", dayfirst=True))

        row_order: list[tuple[datetime, datetime, int]] = []
        for idx, (client_now, log_entry) in enumerate(rows):
            logged_dt_probe = parse_logged_datetime(client_now)
            logged_sort_dt = logged_dt_probe or max_sort_dt
            inferred_sort_dt = logged_sort_dt
            client_now_probe = client_now
            if logged_dt_probe is not None:
                client_now_probe = logged_dt_probe.strftime("%Y-%m-%d %H:%M:%S")
            try:
                probe_parsed = parser.parse_row(log_entry, client_now_probe, None)
                inferred_candidate = to_naive(probe_parsed.get("start_dt"))
                if inferred_candidate is not None:
                    inferred_sort_dt = inferred_candidate
            except Exception:
                pass
            inferred_sort_key = inferred_sort_dt.replace(second=0, microsecond=0)
            row_order.append((inferred_sort_key, logged_sort_dt, idx))

        ordered_indices = [idx for _, _, idx in sorted(row_order, key=lambda item: (item[0], item[1], item[2]))]
        ordered_rows = [rows[idx] for idx in ordered_indices]

        parsed_rows: list[dict] = []
        previous_end: datetime | None = None
        for client_now, log_entry in ordered_rows:
            logged_dt_current = parse_logged_datetime(client_now)
            client_now_for_parse = client_now
            if logged_dt_current is not None:
                client_now_for_parse = logged_dt_current.strftime("%Y-%m-%d %H:%M:%S")
            parsed = parser.parse_row(log_entry, client_now_for_parse, previous_end)
            parsed_rows.append(parsed)
            if previous_end is None or parsed["end_dt"] > previous_end:
                previous_end = parsed["end_dt"]
        return parsed_rows

    def test_zero_elements_uses_previous_end(self) -> None:
        previous_end = datetime(2026, 1, 21, 8, 0)
        parsed = self.parse("Task only", previous_end)
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], self.now)

    def test_one_time_with_dot(self) -> None:
        parsed = self.parse("9:00. Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 9, 0))
        self.assertEqual(parsed["end_dt"], self.now)

    def test_one_time_with_separate_pm_token(self) -> None:
        parsed = self.parse_with_now("7:50 pm sleep", "2026-01-20 19:58")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 19, 50))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 20, 19, 50))

    def test_one_time_without_dot_uses_previous_end(self) -> None:
        previous_end = datetime(2026, 1, 21, 8, 0)
        parsed = self.parse("9:00 Task", previous_end)
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 9, 0))

    def test_first_row_without_previous_end_sets_start_date(self) -> None:
        parsed = self.parse("9:00 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 9, 0))

    def test_two_elements_time_date_with_dot(self) -> None:
        previous_end = datetime(2026, 1, 20, 8, 0)
        parsed = self.parse("9:00 20/01. Task", previous_end)
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 9, 0))
        self.assertEqual(parsed["end_dt"], self.now)

    def test_two_elements_time_date_without_dot(self) -> None:
        previous_end = datetime(2026, 1, 20, 7, 0)
        parsed = self.parse("9:00 20/01 Task", previous_end)
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 20, 9, 0))

    def test_two_elements_two_times_wraps_day(self) -> None:
        parsed = self.parse("23:00 1:00 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 23, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 1, 0))

    def test_two_elements_two_times_same_day(self) -> None:
        parsed = self.parse("9:00 10:00 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 10, 0))

    def test_one_time_midnight_crossing_uses_previous_day(self) -> None:
        previous_end = datetime(2026, 1, 13, 21, 51)
        parsed = self.parse_with_now(
            "11:30 pm friends time",
            "2026-01-14 01:02",
            previous_end=previous_end,
        )
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 13, 23, 30))

    def test_three_elements_date_times_with_dot_after_date(self) -> None:
        parsed = self.parse("20/01. 9:00 10:00 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 10, 0))

    def test_three_elements_date_times_wraps_day(self) -> None:
        parsed = self.parse("20/01 23:00 1:00 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 23, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 1, 0))

    def test_four_elements_dates_and_times(self) -> None:
        parsed = self.parse("20/01 9:00 21/01 10:00 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 10, 0))

    def test_screenshot_scenario_sleep_then_instagram(self) -> None:
        first = self.parse_with_now(
            "7:50 pm sleep . Necessity Urgent",
            "2026-01-20 19:58",
            previous_end=datetime(2026, 1, 20, 19, 0),
        )
        self.assertEqual(first["start_dt"], datetime(2026, 1, 20, 19, 0))
        self.assertEqual(first["end_dt"], datetime(2026, 1, 20, 19, 50))

        second = self.parse_with_now(
            "Instagram .",
            "2026-01-20 20:27",
            previous_end=first["end_dt"],
        )
        self.assertEqual(second["start_dt"], datetime(2026, 1, 20, 19, 50))
        self.assertEqual(second["end_dt"], datetime(2026, 1, 20, 20, 27))

    def test_ambiguous_hhmm_infers_pm_from_client_now(self) -> None:
        parsed = self.parse_with_now(
            "10:10 workout . Soul Important",
            "2026-01-21 22:29",
            previous_end=datetime(2026, 1, 21, 21, 0),
        )
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 21, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 22, 10))

    def test_split_date_tokens_then_time(self) -> None:
        previous_end = datetime(2026, 2, 3, 22, 17)
        parsed = self.parse_with_now(
            "3 feb 11 pm restfully laid before sleep . Rest",
            "2026-02-04 07:04:09",
            previous_end=previous_end,
        )
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 2, 3, 23, 0))

    def test_followup_row_uses_previous_end(self) -> None:
        previous_end = datetime(2026, 2, 3, 23, 0)
        parsed = self.parse_with_now(
            "Sleep . Necessity Urgent",
            "2026-02-04 07:04:19",
            previous_end=previous_end,
        )
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 2, 4, 7, 4, 19))

    def test_task_name_with_tag_like_words_without_meta(self) -> None:
        parsed = self.parse("Morning Urgentencies")
        self.assertEqual(parsed["task"], "Morning Urgentencies")
        self.assertFalse(parsed["urg"])
        self.assertFalse(parsed["imp"])
        self.assertEqual(parsed["tag"], "Waste")

        parsed = self.parse("Work meeting")
        self.assertEqual(parsed["task"], "Work meeting")
        self.assertFalse(parsed["urg"])
        self.assertFalse(parsed["imp"])
        self.assertEqual(parsed["tag"], "Waste")

    def test_meta_parsed_only_after_dot(self) -> None:
        parsed = self.parse("9:00 Project v2.0 . Work Urgent")
        self.assertEqual(parsed["task"], "Project v2.0")
        self.assertTrue(parsed["urg"])
        self.assertFalse(parsed["imp"])
        self.assertEqual(parsed["tag"], "Work")

    def test_bare_hour_time_tokens_are_rejected(self) -> None:
        previous_end = datetime(2026, 1, 21, 8, 0)
        for entry in ("11 Task", "23 Task", "3 Task"):
            with self.subTest(entry=entry):
                parsed = self.parse(entry, previous_end)
                self.assertEqual(parsed["start_dt"], previous_end)
                self.assertEqual(parsed["end_dt"], self.now)

    def test_leading_dotted_day_with_two_times_uses_date_then_cross_date_end(self) -> None:
        previous_end = datetime(2026, 2, 21, 13, 53)
        parsed = self.parse_with_now(
            "21. 1:53 pm 1:40 travelling for ujjain, Instagram, games and family time . Soul",
            "2026-02-22 01:50:49",
            previous_end=previous_end,
        )
        self.assertEqual(parsed["start_dt"], datetime(2026, 2, 21, 13, 53))
        self.assertEqual(parsed["end_dt"], datetime(2026, 2, 22, 1, 40))

    def test_leading_day_plus_explicit_time_prefers_date_not_hour(self) -> None:
        previous_end = datetime(2026, 2, 22, 23, 59)
        family = self.parse_with_now(
            "22 11:59 In ujjain with family . Soul Urgent",
            "2026-02-23 00:00:33",
            previous_end=previous_end,
        )
        self.assertEqual(family["start_dt"], previous_end)
        self.assertEqual(family["end_dt"], datetime(2026, 2, 22, 23, 59))

        sleep = self.parse_with_now(
            "9:30 am sleep . Necessity",
            "2026-02-23 19:07:59",
            previous_end=family["end_dt"],
        )
        self.assertEqual(sleep["start_dt"], datetime(2026, 2, 22, 23, 59))
        self.assertEqual(sleep["end_dt"], datetime(2026, 2, 23, 9, 30))

    def test_explicit_month_date_with_two_times_parses_absolute_range(self) -> None:
        previous_end = datetime(2026, 2, 23, 0, 0)
        parsed = self.parse_with_now(
            "22 feb 9:30 am 12:30 pm ujjain pooja . Important Urgent",
            "2026-02-25 19:01:25",
            previous_end=previous_end,
        )
        self.assertEqual(parsed["start_dt"], datetime(2026, 2, 22, 9, 30))
        self.assertEqual(parsed["end_dt"], datetime(2026, 2, 22, 12, 30))
        self.assertEqual(parsed["task"], "ujjain pooja")
        self.assertTrue(parsed["urg"])
        self.assertTrue(parsed["imp"])

    def test_sync_order_keeps_plain_row_between_project_and_explicit_interval(self) -> None:
        parsed_rows = self.parse_rows_like_sync(
            [
                ("2026-02-17 12:13:45", "sleep . necessity"),
                ("2026-02-17 15:00:00", "Project time tracker . Work Important"),
                ("2026-02-17 15:42:45", "prepared and ate food . necessity"),
                (
                    "2026-02-17 15:56:18",
                    "17/02/2026 3:42pm 3:56pm After food walk and returned Priyanshi charger. waste urgent",
                ),
            ]
        )
        self.assertTrue(
            any(
                row["task"] == "prepared and ate food"
                and row["start_dt"] == datetime(2026, 2, 17, 15, 0)
                and row["end_dt"] == datetime(2026, 2, 17, 15, 42, 45)
                for row in parsed_rows
            )
        )

    def test_sync_order_keeps_bus_row_between_sleep_and_backfilled_travel(self) -> None:
        parsed_rows = self.parse_rows_like_sync(
            [
                ("2026-02-21 01:21:59", "Review today’s day . Soul Important"),
                ("2026-02-21 10:39:56", "10:30 sleep . Necessity Urgent"),
                ("2026-02-21 13:53:44", "Got ready and Got in bus for Jaipur . Urgent"),
                (
                    "2026-02-22 01:50:49",
                    "21. 1:53 pm 1:40 travelling for ujjain, Instagram, games and family time . Soul",
                ),
            ]
        )
        self.assertTrue(
            any(
                row["task"] == "Got ready and Got in bus for Jaipur"
                and row["start_dt"] == datetime(2026, 2, 21, 10, 30)
                and row["end_dt"] == datetime(2026, 2, 21, 13, 53, 44)
                for row in parsed_rows
            )
        )

    def test_sync_order_keeps_iso_logged_dates_in_same_month(self) -> None:
        parsed_rows = self.parse_rows_like_sync(
            [
                ("2026-02-10 23:19:40", "After food walk and om singing . Soul Important"),
                ("2026-02-11 00:31:37", "Project workout logger . Work Important"),
            ]
        )
        self.assertTrue(
            any(
                row["task"] == "Project workout logger"
                and row["start_dt"] == datetime(2026, 2, 10, 23, 19, 40)
                and row["end_dt"] == datetime(2026, 2, 11, 0, 31, 37)
                for row in parsed_rows
            )
        )

    def test_generated_permutations_do_not_crash(self) -> None:
        time_seqs = [
            ("9",),
            ("09",),
            ("9:00",),
            ("11:15",),
            ("9am",),
            ("9", "am"),
            ("7:50", "pm"),
            ("12", "am"),
            ("12", "pm"),
            ("23",),
        ]
        date_tokens = [
            "20/01",
            "20-01",
            "20.01",
            "20/01/26",
            "2026-01-20",
            "Jan",
        ]

        def as_text(tokens: tuple[str, ...]) -> str:
            return " ".join(tokens)

        def with_trailing_dot(tokens: tuple[str, ...]) -> tuple[str, ...]:
            if not tokens:
                return tokens
            return (*tokens[:-1], f"{tokens[-1]}.")

        def with_trailing_comma(tokens: tuple[str, ...]) -> tuple[str, ...]:
            if not tokens:
                return tokens
            return (*tokens[:-1], f"{tokens[-1]},")

        base_text = ("Task", ".", "Work", "Urgent", "Important")

        cases: list[str] = []

        cases.append(as_text(base_text))

        for t in time_seqs:
            cases.append(as_text((*t, *base_text)))
            cases.append(as_text((*with_trailing_dot(t), *base_text)))
            cases.append(as_text((*t, ".", *base_text)))
            cases.append(as_text((*with_trailing_comma(t), *base_text)))

        for t, d in product(time_seqs, date_tokens):
            td = (*t, d)
            cases.append(as_text((*td, *base_text)))
            cases.append(as_text((*with_trailing_dot(td), *base_text)))
            cases.append(as_text((*td, ".", *base_text)))

        for t1, t2 in product(time_seqs, time_seqs):
            cases.append(as_text((*t1, *t2, *base_text)))

        for d, t1, t2 in product(date_tokens, time_seqs, time_seqs):
            cases.append(as_text((d + ".", *t1, *t2, *base_text)))
            cases.append(as_text((d, ".", *t1, *t2, *base_text)))
            cases.append(as_text((d, *t1, *t2, *base_text)))

        for d1, t1, d2, t2 in product(date_tokens, time_seqs, date_tokens, time_seqs):
            cases.append(as_text((d1, *t1, d2, *t2, *base_text)))

        max_cases = 5000
        tested = 0
        for entry in cases:
            if tested >= max_cases:
                break
            with self.subTest(entry=entry):
                parsed = self.parse(entry)
                self.assertIn("start_dt", parsed)
                self.assertIn("end_dt", parsed)
                self.assertIsInstance(parsed["start_dt"], datetime)
                self.assertIsInstance(parsed["end_dt"], datetime)
            tested += 1


if __name__ == "__main__":
    unittest.main()
