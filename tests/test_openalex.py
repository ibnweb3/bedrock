import json
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bedrock.openalex import (  # noqa: E402
    BudgetExceeded,
    Client,
    OpenAlexError,
    date_int,
    doi_batches,
    doi_filter,
    norm_doi,
    short_id,
    slim_work,
)

SALT = "s" * 40

RAW_WORK = {
    "id": "https://openalex.org/W100",
    "doi": "https://doi.org/10.1234/ABC.5",
    "publication_date": "2020-03-09",
    "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    "authorships": [
        {
            "author": {"id": "https://openalex.org/A111", "display_name": "Jane Q. Researcher",
                       "orcid": "https://orcid.org/0000-0001-2345-6789"},
            "institutions": [{"display_name": "Example University"}],
            "raw_affiliation_strings": ["Dept of Things, Example University"],
        },
        {"author": {"id": "https://openalex.org/A111", "display_name": "Jane Q. Researcher"}},
        {"author": {"id": "https://openalex.org/A222", "display_name": "Sam Other"}},
        {"author": {}},
    ],
    "primary_location": {"source": {"id": "https://openalex.org/S999", "display_name": "J. Things"}},
}


class SlimWorkTests(unittest.TestCase):
    def test_fields(self):
        s = slim_work(RAW_WORK, SALT)
        self.assertEqual(s["id"], "W100")
        self.assertEqual(s["doi"], "10.1234/abc.5")
        self.assertEqual(s["pub_date"], 20200309)
        self.assertEqual(s["venue_id"], "S999")
        self.assertEqual(s["refs"], ["W1", "W2"])
        self.assertEqual(len(s["authors"]), 2)  # deduped, empty author skipped

    def test_no_personal_data_survives(self):
        blob = json.dumps(slim_work(RAW_WORK, SALT))
        for forbidden in ("Jane", "Researcher", "Sam Other", "orcid", "0000-0001", "Example University",
                          "A111", "A222", "display_name", "affiliation"):
            self.assertNotIn(forbidden, blob)

    def test_missing_id_returns_none(self):
        self.assertIsNone(slim_work({"doi": "10.1/x"}, SALT))

    def test_missing_optional_fields(self):
        s = slim_work({"id": "https://openalex.org/W5"}, SALT)
        self.assertEqual((s["refs"], s["authors"], s["venue_id"], s["doi"], s["pub_date"]),
                         ([], [], None, None, None))


class HelperTests(unittest.TestCase):
    def test_short_id(self):
        self.assertEqual(short_id("https://openalex.org/W123"), "W123")
        self.assertIsNone(short_id(None))

    def test_norm_doi(self):
        self.assertEqual(norm_doi("HTTPS://DOI.ORG/10.1/ABC"), "10.1/abc")
        self.assertEqual(norm_doi("http://dx.doi.org/10.1/x"), "10.1/x")
        self.assertIsNone(norm_doi("unavailable"))
        self.assertIsNone(norm_doi(""))

    def test_date_int(self):
        self.assertEqual(date_int("2021-05-03"), 20210503)
        self.assertIsNone(date_int("2021"))
        self.assertIsNone(date_int(None))

    def test_doi_batches_skip_bad_and_split(self):
        dois = [f"10.1/{i}" for i in range(250)] + ["10.1/a,b", "10.1/a|b", "10.1/a b"]
        batches = list(doi_batches(dois, size=100))
        self.assertEqual([len(b) for b in batches], [100, 100, 50])

    def test_doi_filter(self):
        self.assertEqual(doi_filter(["10.1/a", "10.2/b"]),
                         "doi:https://doi.org/10.1/a|https://doi.org/10.2/b")


def _client(handler, **kw):
    return Client("k" * 22, transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


class ClientTests(unittest.TestCase):
    def test_rejects_empty_or_malformed_key(self):
        for bad in ("", "has space"):
            with self.assertRaises(OpenAlexError):
                Client(bad)

    def test_cursor_paging_and_stop(self):
        pages = {"*": ([{"id": "a"}, {"id": "b"}], "c2"), "c2": ([{"id": "c"}], None)}

        def handler(request):
            res, nxt = pages[request.url.params["cursor"]]
            return httpx.Response(200, json={"results": res, "meta": {"next_cursor": nxt}})

        got = [w["id"] for res, _ in _client(handler).iter_pages("f") for w in res]
        self.assertEqual(got, ["a", "b", "c"])

    def test_retries_on_429_then_succeeds(self):
        n = {"i": 0}

        def handler(request):
            n["i"] += 1
            if n["i"] == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(200, json={"results": []})

        c = _client(handler)
        self.assertEqual(c.get("/works"), {"results": []})
        self.assertEqual(c.calls, 2)

    def test_401_raises(self):
        with self.assertRaises(OpenAlexError):
            _client(lambda r: httpx.Response(401, json={"error": "x"})).get("/works")

    def test_call_budget_enforced(self):
        c = _client(lambda r: httpx.Response(200, json={"results": []}), max_calls=2)
        c.get("/works")
        c.get("/works")
        with self.assertRaises(BudgetExceeded):
            c.get("/works")

    def test_works_by_dois_sends_one_filter(self):
        seen = {}

        def handler(request):
            seen["filter"] = request.url.params["filter"]
            return httpx.Response(200, json={"results": [{"id": "https://openalex.org/W1"}]})

        out = _client(handler).works_by_dois(["10.1/a", "10.1/b"])
        self.assertEqual(len(out), 1)
        self.assertEqual(seen["filter"], "doi:https://doi.org/10.1/a|https://doi.org/10.1/b")


if __name__ == "__main__":
    unittest.main()
