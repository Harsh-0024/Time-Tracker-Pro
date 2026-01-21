import unittest
from datetime import datetime

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

    def test_zero_elements_uses_previous_end(self) -> None:
        previous_end = datetime(2026, 1, 21, 8, 0)
        parsed = self.parse("Task only", previous_end)
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], self.now)

    def test_one_time_with_dot(self) -> None:
        parsed = self.parse("9. Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 9, 0))
        self.assertEqual(parsed["end_dt"], self.now)

    def test_one_time_with_separate_pm_token(self) -> None:
        parsed = self.parse_with_now("7:50 pm sleep", "2026-01-20 19:58")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 19, 50))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 20, 19, 50))

    def test_one_time_without_dot_uses_previous_end(self) -> None:
        previous_end = datetime(2026, 1, 21, 8, 0)
        parsed = self.parse("9 Task", previous_end)
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 9, 0))

    def test_first_row_without_previous_end_sets_start_date(self) -> None:
        parsed = self.parse("9 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 9, 0))

    def test_two_elements_time_date_with_dot(self) -> None:
        previous_end = datetime(2026, 1, 20, 8, 0)
        parsed = self.parse("9 20/01. Task", previous_end)
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 9, 0))
        self.assertEqual(parsed["end_dt"], self.now)

    def test_two_elements_time_date_without_dot(self) -> None:
        previous_end = datetime(2026, 1, 20, 7, 0)
        parsed = self.parse("9 20/01 Task", previous_end)
        self.assertEqual(parsed["start_dt"], previous_end)
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 20, 9, 0))

    def test_two_elements_two_times_wraps_day(self) -> None:
        parsed = self.parse("23 1 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 23, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 1, 0))

    def test_two_elements_two_times_same_day(self) -> None:
        parsed = self.parse("9 11 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 21, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 11, 0))

    def test_three_elements_date_times_with_dot_after_date(self) -> None:
        parsed = self.parse("20/01. 9 11 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 9, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 11, 0))

    def test_three_elements_date_times_wraps_day(self) -> None:
        parsed = self.parse("20/01 23 1 Task")
        self.assertEqual(parsed["start_dt"], datetime(2026, 1, 20, 23, 0))
        self.assertEqual(parsed["end_dt"], datetime(2026, 1, 21, 1, 0))

    def test_four_elements_dates_and_times(self) -> None:
        parsed = self.parse("20/01 9 21/01 10 Task")
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


if __name__ == "__main__":
    unittest.main()
