import json
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _fixture import build, connect_or_skip  # noqa: E402
from bedrock.agent import MAX_STEPS, TOOL_NAMES, TOOLS, AuditAgent, compact_audit, deterministic_summary  # noqa: E402
from bedrock.audit import Auditor  # noqa: E402
from bedrock.llm import GroqClient, LLMError  # noqa: E402

TEXT = "Refs:\n[1] https://doi.org/10.1000/r1\n[2] doi:10.1000/a\n[3] 10.1000/b\n[4] 10.1000/c\n"


def call(name, args=None, cid="c1", raw=None):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function",
                            "function": {"name": name, "arguments": raw if raw is not None else json.dumps(args or {})}}]}


def final(text):
    return {"role": "assistant", "content": text}


class FakeLLM:
    model = "fake-model"
    script_default = None

    def __init__(self, script):
        self.script, self.seen, self.usage = list(script), [], {"calls": 0}

    def chat(self, messages, tools=None, **kw):
        self.seen.append([dict(m) for m in messages])
        self.usage["calls"] += 1
        nxt = self.script.pop(0) if self.script else self.script_default
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, _ = connect_or_skip("bedrock_agent_test")
        cls.g = build(cls.db, "bedrock_agent_test")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.g.delete()
        except Exception:  # noqa: BLE001
            pass

    def test_tools_are_read_only(self):
        self.assertEqual(TOOL_NAMES, {"audit_bibliography", "explain_finding", "find_dois"})
        for name in TOOL_NAMES:
            for word in ("apply", "edit", "delete", "write", "remove", "update"):
                self.assertNotIn(word, name)
        self.assertEqual(len(TOOLS), 3)

    def test_happy_path_and_grounding(self):
        llm = FakeLLM([call("audit_bibliography"), call("explain_finding", {"doi": "10.1000/b"}, "c2"),
                       final("Summary. 10.1000/b -> 10.1000/x -> 10.1000/r1 is a two-hop path; 10.1000/r1 was retracted.")])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertEqual(out["source"], "agent")
        self.assertTrue(out["verification"]["ok"])
        self.assertEqual([t["tool"] for t in out["trace"]], ["audit_bibliography", "explain_finding"])
        self.assertTrue(all(t["ok"] for t in out["trace"]))
        last = llm.seen[-1]
        self.assertEqual(last[0]["role"], "system")
        tool_msgs = [m for m in last if m["role"] == "tool"]
        self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["c1", "c2"])
        # the structured audit is independent of the model
        self.assertEqual(out["audit"]["summary"]["input"], 4)
        self.assertTrue(any(p["kind"] == "REMOVE_OR_REPLACE" for p in out["proposals"]))

    def test_doi_returned_only_by_a_tool_is_grounded(self):
        # the user pastes only 10.1000/a; 10.1000/r1 and 10.1000/alt appear solely in tool results
        llm = FakeLLM([call("audit_bibliography"), call("explain_finding", {"doi": "10.1000/a"}, "c2"),
                       final("**10.1000/a** cites the retracted **10.1000/r1**.")])
        out = AuditAgent(self.g, llm).run("only 10.1000/a here")
        self.assertTrue(out["verification"]["ok"], out["verification"])

    def test_empty_dois_argument_audits_the_pasted_list(self):
        llm = FakeLLM([call("audit_bibliography", {"dois": []}), final("done")])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertTrue(out["trace"][0]["ok"])
        self.assertIn("4 DOIs", out["trace"][0]["result"])

    def test_model_cannot_audit_dois_it_made_up_or_mistyped(self):
        llm = FakeLLM([call("audit_bibliography", {"dois": ["10.1000/a", "10.1000/zzz-mistyped"]}), final("done")])
        AuditAgent(self.g, llm).run(TEXT)
        tool_msg = [m for m in llm.seen[-1] if m["role"] == "tool"][0]
        result = json.loads(tool_msg["content"])
        self.assertEqual(result["summary"]["input"], 1)                 # only the real DOI was audited
        self.assertEqual(result["ignored_dois_not_in_user_text"], ["10.1000/zzz-mistyped"])

    def test_explain_rejects_unknown_doi(self):
        out = AuditAgent(self.g, FakeLLM([call("explain_finding", {"doi": "10.1000/zzz"}), final("done")])).run(TEXT)
        self.assertFalse(out["trace"][0]["ok"])

    def test_truncated_answer_is_reported(self):
        llm = FakeLLM([call("audit_bibliography"), {"role": "assistant", "content": "cut o", "_finish_reason": "length"}])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertIn("cut off", out["error"])
        self.assertEqual(out["audit"]["summary"]["input"], 4)

    def test_invented_doi_is_flagged(self):
        llm = FakeLLM([call("audit_bibliography"), final("See 10.1000/r1 and also 10.5555/invented.")])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertFalse(out["verification"]["ok"])
        self.assertEqual(out["verification"]["ungrounded"], ["10.5555/invented"])

    def _flagged(self):
        from bedrock.audit import extract_dois
        res = Auditor(self.g).audit(extract_dois(TEXT))
        return [it["doi"] for it in res["items"] if it["status"] in ("RETRACTED", "CITES_RETRACTED", "TWO_HOP")]

    def test_incomplete_summary_gets_one_retry_that_covers_everything(self):
        flagged = self._flagged()
        self.assertGreaterEqual(len(flagged), 2)
        llm = FakeLLM([call("audit_bibliography"), final(f"Only {flagged[0]} matters."), final("All flagged: " + ", ".join(flagged))])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertTrue(out["verification"]["completeness_retry"])
        self.assertEqual(out["verification"]["appended_missing"], [])
        self.assertTrue(all(d in out["answer"] for d in flagged))
        retry_prompt = llm.seen[-1][-1]["content"]
        self.assertIn(flagged[1], retry_prompt)                      # tells the model exactly what it left out

    def test_still_incomplete_after_retry_appends_the_missing_papers_in_plain_words(self):
        flagged = self._flagged()
        llm = FakeLLM([call("audit_bibliography"), final(f"Only {flagged[0]} matters."), final(f"Still only {flagged[0]}.")])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertEqual(out["verification"]["appended_missing"], flagged[1:])
        self.assertIn("Also flagged by the audit", out["answer"])
        self.assertTrue(all(d in out["answer"] for d in flagged))
        self.assertTrue(out["verification"]["ok"])                    # appended DOIs come from the audit, so they are grounded

    def test_opening_counts_come_from_the_audit_not_the_model(self):
        flagged = self._flagged()
        llm = FakeLLM([call("audit_bibliography"), final("Exactly 99 papers were retracted.\n\nDetails: " + ", ".join(flagged))])
        out = AuditAgent(self.g, llm).run(TEXT)
        first = out["answer"].splitlines()[0]
        self.assertTrue(first.startswith("Checked 4 DOIs:"), first)
        self.assertNotIn("99", out["answer"])
        self.assertTrue(all(d in out["answer"] for d in flagged))

    def test_unknown_tool_and_bad_json_do_not_crash(self):
        llm = FakeLLM([call("delete_everything", {}), call("audit_bibliography", raw="{not json", cid="c2"),
                       final("Could not audit.")])
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertEqual([t["ok"] for t in out["trace"]], [False, False])
        self.assertIn("unknown tool", out["trace"][0]["result"])
        self.assertIn("not valid JSON", out["trace"][1]["result"])
        self.assertEqual(out["source"], "agent")

    def test_explain_limit_is_enforced(self):
        script = [call("explain_finding", {"doi": "10.1000/a"}, "c%d" % i) for i in range(4)] + [final("done")]
        out = AuditAgent(self.g, FakeLLM(script)).run(TEXT)
        self.assertEqual([t["ok"] for t in out["trace"]], [True, True, True, False])

    def test_step_cap_falls_back_to_plain_summary(self):
        llm = FakeLLM([])
        llm.script_default = call("find_dois", {"text": "10.1000/a"})
        out = AuditAgent(self.g, llm).run(TEXT)
        self.assertEqual(out["source"], "fallback")
        self.assertEqual(len(out["trace"]), MAX_STEPS)
        self.assertIn("Checked 4 DOIs", out["answer"])
        self.assertIn("error", out)

    def test_llm_error_falls_back_but_keeps_audit(self):
        out = AuditAgent(self.g, FakeLLM([LLMError("rate limited")])).run(TEXT)
        self.assertEqual(out["source"], "fallback")
        self.assertIn("rate limited", out["error"])
        self.assertEqual(out["audit"]["summary"]["RETRACTED"], 1)

    def test_no_llm_configured(self):
        out = AuditAgent(self.g, None).run(TEXT)
        self.assertIn("not configured", out["error"])
        self.assertIn("Checked 4 DOIs", out["answer"])

    def test_compact_audit_limits_flagged(self):
        res = Auditor(self.g).audit(["10.1000/r1", "10.1000/a", "10.1000/b", "10.1000/c"])
        c = compact_audit(res, max_items=2)
        self.assertEqual(len(c["flagged"]), 2)
        self.assertEqual(c["more_flagged_not_shown"], 1)
        self.assertNotIn("10.1000/c", json.dumps(c["flagged"]))  # clean papers are not sent to the model
        self.assertIn("not certified clean", c["note"])
        self.assertTrue(deterministic_summary(res).startswith("Checked 4 DOIs"))


def groq(handler, **kw):
    return GroqClient("k" * 20, "m", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


OK = {"choices": [{"message": {"role": "assistant", "content": "hi"}}],
      "usage": {"prompt_tokens": 10, "completion_tokens": 3}}


class GroqClientTests(unittest.TestCase):
    def test_requires_key(self):
        with self.assertRaises(LLMError):
            GroqClient("", "m")

    def test_success_sends_tools_and_counts_usage(self):
        seen = {}

        def h(req):
            seen["body"] = json.loads(req.content)
            seen["auth"] = req.headers["authorization"]
            return httpx.Response(200, json=OK)

        c = groq(h)
        msg = c.chat([{"role": "user", "content": "x"}], TOOLS)
        self.assertEqual(msg["content"], "hi")
        self.assertEqual(seen["body"]["tool_choice"], "auto")
        self.assertEqual(len(seen["body"]["tools"]), 3)
        self.assertTrue(seen["auth"].startswith("Bearer "))
        self.assertEqual(c.usage, {"prompt_tokens": 10, "completion_tokens": 3, "calls": 1})

    def test_retries_429_with_retry_after_then_succeeds(self):
        n = {"i": 0}

        def h(req):
            n["i"] += 1
            return httpx.Response(429, headers={"retry-after": "3"}) if n["i"] == 1 else httpx.Response(200, json=OK)

        self.assertEqual(groq(h).chat([{"role": "user", "content": "x"}])["content"], "hi")
        self.assertEqual(n["i"], 2)

    def test_gives_up_after_repeated_429(self):
        with self.assertRaises(LLMError):
            groq(lambda r: httpx.Response(429), max_retries=2).chat([{"role": "user", "content": "x"}])

    def test_reasoning_effort_only_for_gpt_oss_and_finish_reason_returned(self):
        bodies = []

        def h(req):
            bodies.append(json.loads(req.content))
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "x"}, "finish_reason": "length"}]})

        msg = GroqClient("k" * 20, "openai/gpt-oss-120b", transport=httpx.MockTransport(h)).chat([{"role": "user", "content": "x"}])
        GroqClient("k" * 20, "qwen/qwen3.8-27b", transport=httpx.MockTransport(h)).chat([{"role": "user", "content": "x"}])
        self.assertEqual(bodies[0]["reasoning_effort"], "low")
        self.assertNotIn("reasoning_effort", bodies[1])
        self.assertEqual(msg["_finish_reason"], "length")

    def test_401_is_a_clear_error(self):
        with self.assertRaises(LLMError) as cm:
            groq(lambda r: httpx.Response(401, text="bad key")).chat([{"role": "user", "content": "x"}])
        self.assertIn("rejected", str(cm.exception))

    def test_malformed_tool_call_retries_at_temperature_zero(self):
        temps = []

        def h(req):
            temps.append(json.loads(req.content)["temperature"])
            if len(temps) == 1:
                return httpx.Response(400, text='{"error":{"code":"tool_use_failed"}}')
            return httpx.Response(200, json=OK)

        groq(h).chat([{"role": "user", "content": "x"}], TOOLS)
        self.assertEqual(temps, [0.1, 0.0])


if __name__ == "__main__":
    unittest.main()
