import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _fixture import build, connect_or_skip  # noqa: E402
from bedrock import server  # noqa: E402


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, _ = connect_or_skip("bedrock_server_test")
        server._graph = build(cls.db, "bedrock_server_test")
        server._meta.clear()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        server._graph = None
        server._meta.clear()
        try:
            cls.db.select_graph("bedrock_server_test").delete()
        except Exception:  # noqa: BLE001
            pass

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_index_served_with_security_headers(self):
        code, h, body = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Bedrock", body)
        self.assertIn("default-src 'self'", h["Content-Security-Policy"])
        self.assertEqual(h["X-Content-Type-Options"], "nosniff")

    def test_unknown_path_and_traversal_are_404(self):
        self.assertEqual(self.call("/nope")[0], 404)
        self.assertEqual(self.call("/../README.md")[0], 404)

    def test_health_reports_corpus(self):
        code, _, body = self.call("/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_audit_returns_findings_and_proposals(self):
        code, _, body = self.call("/api/audit", {"text": "refs: 10.1000/r1 and https://doi.org/10.1000/b"})
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual([i["status"] for i in data["audit"]["items"]], ["RETRACTED", "TWO_HOP"])
        self.assertTrue(any(p["kind"] == "REMOVE_OR_REPLACE" for p in data["proposals"]))

    def test_no_dois_is_400_with_message(self):
        code, _, body = self.call("/api/audit", {"text": "just words"})
        self.assertEqual(code, 400)
        self.assertIn("No DOIs found", json.loads(body)["error"])

    def test_bad_json_is_400(self):
        req = urllib.request.Request(self.base + "/api/audit", data=b"{not json")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)

    def test_oversized_body_is_413(self):
        req = urllib.request.Request(self.base + "/api/audit", data=b"x" * (server.MAX_BODY + 1))
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 413)

    def test_apply_only_applies_approved_ids_server_side(self):
        text = "10.1000/r1"
        _, _, none = self.call("/api/apply", {"text": text, "approved": []})
        self.assertEqual(json.loads(none)["applied"], [])
        self.assertIn("10.1000/r1", json.loads(none)["revised_dois"])
        # an id the server did not propose is ignored, however it is phrased
        _, _, fake = self.call("/api/apply", {"text": text, "approved": ["remove:10.9000/evil"]})
        self.assertEqual(json.loads(fake)["applied"], [])
        _, _, ok = self.call("/api/apply", {"text": text, "approved": ["remove:10.1000/r1"]})
        self.assertNotIn("10.1000/r1", json.loads(ok)["revised_dois"])


    def test_agent_endpoint_returns_answer_trace_and_independent_audit(self):
        from bedrock.agent import AuditAgent
        from test_agent import FakeLLM, call, final

        llm = FakeLLM([call("audit_bibliography"), final("10.1000/r1 was retracted; 10.1000/b depends on it.")])
        original = server.make_agent
        server.make_agent = lambda: AuditAgent(server.graph(), llm)
        try:
            code, _, body = self.call("/api/agent", {"text": "10.1000/r1 10.1000/b", "question": "what is wrong?"})
        finally:
            server.make_agent = original
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(data["source"], "agent")
        self.assertTrue(data["verification"]["ok"])
        self.assertEqual(data["trace"][0]["tool"], "audit_bibliography")
        self.assertEqual(data["audit"]["summary"]["RETRACTED"], 1)
        self.assertIn("what is wrong?", json.dumps(llm.seen[0]))

    def test_agent_endpoint_without_key_falls_back_to_plain_audit(self):
        from bedrock.agent import AuditAgent

        original = server.make_agent
        server.make_agent = lambda: AuditAgent(server.graph(), None)
        try:
            code, _, body = self.call("/api/agent", {"text": "10.1000/r1"})
        finally:
            server.make_agent = original
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertEqual(data["source"], "fallback")
        self.assertIn("not configured", data["error"])
        self.assertEqual(data["audit"]["items"][0]["status"], "RETRACTED")

    def test_public_mode_agent_budget_exhausted_gives_plain_audit_without_calling_model(self):
        from bedrock.ratelimit import Limits, SlidingWindow

        original_limits, original_make = server.LIMITS, server.make_agent
        lim = Limits(public=True)
        lim.agent_ip = SlidingWindow(0, 3600)   # budget already used up
        server.LIMITS = lim

        def boom():
            raise AssertionError("the model agent must not be built when the budget is used up")

        server.make_agent = boom
        try:
            code, _, body = self.call("/api/agent", {"text": "10.1000/r1"})
        finally:
            server.LIMITS, server.make_agent = original_limits, original_make
        data = json.loads(body)
        self.assertEqual(code, 200)
        self.assertTrue(data["rate_limited"])
        self.assertEqual(data["source"], "fallback")
        self.assertEqual(data["audit"]["items"][0]["status"], "RETRACTED")

    def test_public_mode_audit_limit_returns_429(self):
        from bedrock.ratelimit import Limits, SlidingWindow

        original = server.LIMITS
        lim = Limits(public=True)
        lim.audit_ip = SlidingWindow(0, 3600)
        server.LIMITS = lim
        try:
            code, _, _ = self.call("/api/audit", {"text": "10.1000/r1"})
        finally:
            server.LIMITS = original
        self.assertEqual(code, 429)

    def test_agent_endpoint_rejects_text_without_dois(self):
        self.assertEqual(self.call("/api/agent", {"text": "nothing here"})[0], 400)


if __name__ == "__main__":
    unittest.main()
