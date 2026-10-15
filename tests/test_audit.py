import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bedrock.audit import (  # noqa: E402
    CLEAN, DIRECT, RETRACTED, TWO_HOP, UNKNOWN, Auditor, apply_approved, build_proposals, extract_dois, fmt_date,
)


class PureTests(unittest.TestCase):
    def test_extract_dois_from_messy_text(self):
        text = ("1. Smith et al. https://doi.org/10.1234/ABC.5. 2. doi:10.5555/xyz-9; "
                "3. (10.1234/abc.5) duplicate. 4. not a doi 10.12/short")
        self.assertEqual(extract_dois(text), ["10.1234/abc.5", "10.5555/xyz-9"])

    def test_fmt_date(self):
        self.assertEqual(fmt_date(20210601), "2021-06-01")
        self.assertIsNone(fmt_date(None))


from _fixture import build, connect_or_skip  # noqa: E402


class AuditGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, _ = connect_or_skip("bedrock_audit_test")
        cls.g = build(cls.db, "bedrock_audit_test")
        cls.res = Auditor(cls.g).audit(["10.1000/r1", "10.1000/a", "10.1000/b", "10.1000/c", "10.1000/zzz"])
        cls.by = {it["doi"]: it for it in cls.res["items"]}

    @classmethod
    def tearDownClass(cls):
        try:
            cls.g.delete()
        except Exception:  # noqa: BLE001
            pass

    def test_statuses(self):
        self.assertEqual({d: it["status"] for d, it in self.by.items()},
                         {"10.1000/r1": RETRACTED, "10.1000/a": DIRECT, "10.1000/b": TWO_HOP, "10.1000/c": CLEAN, "10.1000/zzz": UNKNOWN})

    def test_summary_counts_and_order(self):
        s = self.res["summary"]
        self.assertEqual((s["input"], s[RETRACTED], s[DIRECT], s[TWO_HOP], s[CLEAN], s[UNKNOWN]), (5, 1, 1, 1, 1, 1))
        self.assertEqual([it["status"] for it in self.res["items"]], [RETRACTED, DIRECT, TWO_HOP, CLEAN, UNKNOWN])

    def test_retraction_details(self):
        r = self.by["10.1000/r1"]["retraction"]
        self.assertEqual((r["date"], r["reasons"], r["indexed_papers_citing_it"]), ("2021-06-01", ["Plagiarism"], 4))

    def test_direct_and_two_hop_paths(self):
        self.assertEqual(self.by["10.1000/a"]["direct"][0]["doi"], "10.1000/r1")
        t = self.by["10.1000/b"]["two_hop"][0]
        self.assertEqual((t["via"]["doi"], t["retracted"]["doi"]), ("10.1000/x", "10.1000/r1"))

    def test_two_hop_excludes_papers_already_citing_directly(self):
        res = Auditor(self.g).audit(["10.1000/d"])
        self.assertEqual(res["items"][0]["status"], DIRECT)
        self.assertNotIn("two_hop", res["items"][0])

    def test_alternatives_are_cocited_non_retracted(self):
        alts = self.by["10.1000/r1"]["alternatives"]
        self.assertEqual([(a["doi"], a["co_cited_by"]) for a in alts], [("10.1000/alt", 2)])

    def test_coverage_and_venue(self):
        self.assertEqual(self.by["10.1000/a"]["coverage"], {"refs_indexed": 1, "refs_total": 3})
        self.assertEqual(self.by["10.1000/a"]["venue"]["name"], "Journal One")
        self.assertEqual(self.by["10.1000/a"]["venue"]["retractions_recorded"], 2)

    def test_clean_does_not_claim_safety(self):
        self.assertTrue(any("not certified clean" in c for c in self.res["caveats"]))

    def test_proposals_and_approval_gate(self):
        props = build_proposals(self.res)
        kinds = {p["id"]: p["kind"] for p in props}
        self.assertEqual(kinds["remove:10.1000/r1"], "REMOVE_OR_REPLACE")
        self.assertEqual(kinds["alt:10.1000/r1:10.1000/alt"], "SUGGEST_ALTERNATIVE")
        self.assertEqual(kinds["review:10.1000/a"], "REVIEW")
        # nothing approved -> nothing changes
        none = apply_approved(self.res, props, set())
        self.assertIn("10.1000/r1", none["revised_dois"])
        self.assertEqual(none["applied"], [])
        # approving only the removal drops the retracted DOI and adds no replacement
        some = apply_approved(self.res, props, {"remove:10.1000/r1"})
        self.assertNotIn("10.1000/r1", some["revised_dois"])
        self.assertNotIn("10.1000/alt", some["revised_dois"])
        # approving both removal and the alternative swaps it in
        both = apply_approved(self.res, props, {"remove:10.1000/r1", "alt:10.1000/r1:10.1000/alt"})
        self.assertIn("10.1000/alt", both["revised_dois"])
        self.assertNotIn("10.1000/r1", both["revised_dois"])
        self.assertIn("## Caveats", both["report_markdown"])


if __name__ == "__main__":
    unittest.main()
