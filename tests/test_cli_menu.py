from __future__ import annotations

import unittest
from datetime import datetime, timezone

from nostradamus_cli import _bar, is_paper_window


class InteractiveMenuTests(unittest.TestCase):
    def test_probability_bar_clamps_values(self) -> None:
        self.assertEqual(_bar(-1.0, width=4), "░░░░")
        self.assertEqual(_bar(0.5, width=4), "██░░")
        self.assertEqual(_bar(2.0, width=4), "████")

    def test_paper_window_is_evaluated_in_colombia_time(self) -> None:
        self.assertTrue(
            is_paper_window(datetime(2026, 9, 22, 0, 5, tzinfo=timezone.utc))
        )
        self.assertFalse(
            is_paper_window(datetime(2026, 9, 21, 19, 48, tzinfo=timezone.utc))
        )

    def test_naive_datetime_uses_local_timezone_without_crashing(self) -> None:
        result = is_paper_window(datetime(2026, 9, 21, 19, 5))
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
