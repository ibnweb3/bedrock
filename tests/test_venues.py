import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bedrock.venues import add_months, post_counts, pre_counts, seeded_pick, window_works  # noqa: E402

RETR = [
    {"doi": "10.1/a", "nature": "Retraction", "retraction_date": 20200601},
    {"doi": "10.1/b", "nature": "Retraction", "retraction_date": 20210301},
    {"doi": "10.1/c", "nature": "Retraction", "retraction_date": 20231001},   # outside 24m window
    {"doi": "10.1/d", "nature": "Correction", "retraction_date": 20210301},   # not a retraction
    {"doi": "10.1/a", "nature": "Retraction", "retraction_date": 20200601},   # duplicate row
    {"doi": "10.1/e", "nature": "Retraction", "retraction_date": None},       # no date
    {"doi": "10.1/f", "nature": "Retraction", "retraction_date": 20210101},   # venue unknown
]
VENUES = {"10.1/a": "S1", "10.1/b": "S1", "10.1/c": "S2", "10.1/d": "S2", "10.1/e": "S2"}


class VenueTests(unittest.TestCase):
    def test_pre_counts_only_up_to_cutoff_and_dedupes(self):
        self.assertEqual(pre_counts(RETR, VENUES, 20201231), {"S1": 1})

    def test_pre_counts_excludes_non_retractions_and_unknown_venues(self):
        c = pre_counts(RETR, VENUES, 20991231)
        self.assertEqual(c, {"S1": 2, "S2": 1})

    def test_post_counts_window(self):
        self.assertEqual(post_counts(RETR, VENUES, 20201231, 24), {"S1": 1})
        self.assertEqual(post_counts(RETR, VENUES, 20201231, 36), {"S1": 1, "S2": 1})

    def test_add_months(self):
        self.assertEqual(add_months(20201231, 24), 20221231)
        self.assertEqual(add_months(20210831, 6), 20220228)
        self.assertEqual(add_months(20211115, 3), 20220215)

    def test_seeded_pick_deterministic_and_order_independent(self):
        ids = [f"S{i}" for i in range(100)]
        a = seeded_pick(ids, 10, 42)
        self.assertEqual(a, seeded_pick(list(reversed(ids)), 10, 42))
        self.assertNotEqual(a, seeded_pick(ids, 10, 43))
        self.assertEqual(len(seeded_pick(ids[:3], 10, 1)), 3)

    def test_window_works(self):
        cby = [{"year": 2016, "works_count": 5}, {"year": 2017, "works_count": 7},
               {"year": 2022, "works_count": 11}, {"year": 2023, "works_count": 99}]
        self.assertEqual(window_works(cby, 2017, 2022), 18)
        self.assertEqual(window_works(None, 2017, 2022), 0)


if __name__ == "__main__":
    unittest.main()
