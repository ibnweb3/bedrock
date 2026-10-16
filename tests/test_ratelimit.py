import unittest

from bedrock.ratelimit import Limits, SlidingWindow


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class SlidingWindowTests(unittest.TestCase):
    def test_blocks_after_limit_and_recovers_after_window(self):
        c = Clock()
        w = SlidingWindow(2, 60, clock=c)
        self.assertTrue(w.allow("a"))
        self.assertTrue(w.allow("a"))
        self.assertFalse(w.allow("a"))
        self.assertTrue(w.allow("b"))          # other keys are independent
        c.t = 61
        self.assertTrue(w.allow("a"))

    def test_key_table_is_bounded(self):
        c = Clock()
        w = SlidingWindow(1, 60, max_keys=3, clock=c)
        for k in "abc":
            self.assertTrue(w.allow(k))
        self.assertFalse(w.allow("d"))         # full of live keys: refuse rather than grow
        c.t = 100
        self.assertTrue(w.allow("d"))          # expired keys were pruned


class LimitsTests(unittest.TestCase):
    def test_local_mode_allows_everything(self):
        lim = Limits(public=False)
        self.assertTrue(all(lim.allow_audit("x") and lim.allow_agent_model("x") for _ in range(1000)))

    def test_per_ip_budget_does_not_drain_global_budget(self):
        lim = Limits(public=True)
        lim.agent_ip = SlidingWindow(1, 3600)
        lim.agent_day = SlidingWindow(2, 86400)
        self.assertTrue(lim.allow_agent_model("a"))
        self.assertFalse(lim.allow_agent_model("a"))   # refused by the per-IP window, global not charged
        self.assertTrue(lim.allow_agent_model("b"))    # global budget still had room
        self.assertFalse(lim.allow_agent_model("c"))   # global budget (2) now used up


if __name__ == "__main__":
    unittest.main()
