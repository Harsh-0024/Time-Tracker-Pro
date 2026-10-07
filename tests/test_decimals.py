import unittest
from time_tracker_pro.core.time_utils import human_hours

class DecimalHandlingTests(unittest.TestCase):
    def test_human_hours_simple(self):
        self.assertEqual(human_hours(0.5), "30 minutes")
        self.assertEqual(human_hours(1.0), "1 hours")
        self.assertEqual(human_hours(1.25), "1 hours 15 minutes")

    def test_human_hours_rounding(self):
        # Avoid float drift like 31.5099999999 by rounding minutes first
        self.assertEqual(human_hours(31.51), "31 hours 31 minutes")
        self.assertEqual(human_hours(5.26), "5 hours 16 minutes")


class HalfUpRoundingTests(unittest.TestCase):
    def test_quarter_hours_round_like_javascript_tofixed(self):
        from time_tracker_pro.core.numbers import round_half_up
        # Python's round() gives 3.2 / 0.2 here (half to even); the JS views show 3.3 / 0.3.
        self.assertEqual(round_half_up(3.25, 1), 3.3)
        self.assertEqual(round_half_up(0.25, 1), 0.3)
        self.assertEqual(round_half_up(6.75, 1), 6.8)
        self.assertEqual(round_half_up(-3.25, 1), -3.3)
        self.assertEqual(round_half_up(195 / 60.0, 1), 3.3)
        self.assertEqual(round_half_up(1 / 3, 1), 0.3)

    def test_matrix_hours_use_half_up(self):
        import pandas as pd
        from time_tracker_pro.services.matrix import get_matrix_stats
        df = pd.DataFrame([{"duration": 195, "urgent": False, "important": True}])
        self.assertEqual(get_matrix_stats(df)["q2"]["hours"], 3.3)


if __name__ == "__main__":
    unittest.main()
