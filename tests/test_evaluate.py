import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evaluate import pct_rank, weighted_metrics  # noqa: E402


class MetricTests(unittest.TestCase):
    def test_pct_rank_ties_share_average_rank(self):
        self.assertEqual(pct_rank([1, 1, 3]), [0.5, 0.5, 1.0])

    def test_average_precision_known_example(self):
        # ranking labels 1,0,1,0 -> AP = (1/1 + 2/3) / 2
        ap, r1, r5 = weighted_metrics([0, 0, 0, 0], [1, 0, 1, 0], [1], 4, 2)
        self.assertAlmostEqual(ap, (1 + 2 / 3) / 2)
        self.assertAlmostEqual(r1, 0.5)   # top 1% of 4 items = 1 item, holds 1 of 2 positives

    def test_oracle_gets_perfect_ap(self):
        ap, r1, r5 = weighted_metrics([0] * 6, [1, 1, 0, 0, 0, 0], [1], 6, 2)
        self.assertEqual(ap, 1.0)

    def test_weights_duplicate_items(self):
        # venue 0 (a positive) drawn twice, venue 1 (a negative) once, positive ranked first
        ap, _, _ = weighted_metrics([0, 1], [1, 0], [2, 1], 3, 2)
        self.assertEqual(ap, 1.0)

    def test_zero_weight_venue_is_dropped(self):
        ap, _, _ = weighted_metrics([0, 1, 0], [0, 1, 1], [1, 0], 2, 1)
        # venue 1 removed: ranking is neg, pos -> AP 1/2
        self.assertAlmostEqual(ap, 0.5)


if __name__ == "__main__":
    unittest.main()
