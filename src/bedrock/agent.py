"""Tool-calling audit agent: an LLM that decides which graph tools to call and explains the result.

Design rules (hackathon rules 11-13 and the project's honesty requirements):
- The agent has READ-ONLY tools. There is deliberately no tool that changes anything: edits are
  applied only by a person approving proposals in the UI.
- Every DOI in the agent's final answer is checked against the tool results; an invented or
  mistyped DOI is reported in `verification.ungrounded` and shown as a warning.
- The structured audit shown to the user is computed directly from FalkorDB, independently of the
  model, so the findings never depend on what the LLM said. If the LLM is unavailable the user
  still gets the audit plus a deterministic summary.
All graph questions are Cypher in queries/audit/, run by FalkorDB through bedrock.audit.
"""
from __future__ import annotations

import json
import time
from typing import Protocol

from .audit import CLEAN, DIRECT, RETRACTED, TWO_HOP, UNKNOWN, Auditor, build_proposals, extract_dois
from .llm import LLMError

MAX_STEPS = 6
MAX_EXPLAIN = 3
MAX_FLAGGED_IN_TOOL_RESULT = 25

SYSTEM = (
    "You are Bedrock, an assistant that checks a bibliography for dependence on retracted research. "
    "You have read-only tools that query a citation graph (retractions: Retraction Watch; citations: OpenAlex). "
    "Workflow: call audit_bibliography; if anything is flagged, call explain_finding on the most important "
    f"DOIs (at most {MAX_EXPLAIN}); then write the answer.\n"
    "Rules: state only facts found in tool results and quote DOIs exactly as given. 'No exposure found' means "
    "nothing was found in the indexed corpus within 2 hops - never say a paper is safe or clean. Never speculate "
    "about authors or intent. You cannot edit anything: suggestions are applied only when a human approves them "
    "in the app. Answer in under 250 words. Begin with a plain one-sentence summary (no label), then mention EVERY flagged DOI from audit_bibliography "
    "(retracted ones first, with their retraction date; then the others, one short line each with the path), "
    "then say what the user should review. Do not omit flagged DOIs."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "audit_bibliography",
        "description": "Audit DOIs for retracted works they are, cite, or reach within 2 citation hops. "
                       "Call it WITHOUT arguments to audit every DOI in the user's pasted text (preferred: do not retype DOIs).",
        "parameters": {"type": "object", "properties": {"dois": {"type": "array", "items": {"type": "string"},
                       "description": "Optional list of DOIs; omit to use all DOIs in the pasted text."}}}}},
    {"type": "function", "function": {
        "name": "explain_finding",
        "description": "Full citation paths, retraction reasons, coverage and suggested alternatives for one DOI.",
        "parameters": {"type": "object", "properties": {"doi": {"type": "string"}}, "required": ["doi"]}}},
    {"type": "function", "function": {
        "name": "find_dois",
        "description": "List the DOIs detected in a piece of text.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
]
TOOL_NAMES = {t["function"]["name"] for t in TOOLS}


class ChatLike(Protocol):
    model: str
    usage: dict

    def chat(self, messages: list[dict], tools: list[dict] | None = None, **kw) -> dict: ...


def compact_audit(result: dict, max_items: int = MAX_FLAGGED_IN_TOOL_RESULT) -> dict:
    """Token-frugal view of an audit for the model: counts + only the flagged items."""
    flagged = [it for it in result["items"] if it["status"] in (RETRACTED, DIRECT, TWO_HOP)]
    out: dict = {"summary": result["summary"], "flagged": []}
    for it in flagged[:max_items]:
        d: dict = {"doi": it["doi"], "status": it["status"]}
        if it["status"] == RETRACTED:
            r = it["retraction"]
            d.update(retracted=r["date"], reasons=r["reasons"][:4], cited_by_indexed_papers=r["indexed_papers_citing_it"],
                     suggested_alternatives=[a["doi"] for a in it.get("alternatives", [])])
        if it.get("direct"):
            d["cites_retracted"] = [{"doi": x["doi"] or x["id"], "retracted": x["retracted_at"]} for x in it["direct"][:3]]
        if it.get("two_hop"):
            d["two_hop_paths"] = [f"{it['doi']} -> {t['via']['doi'] or t['via']['id']} -> "
                                  f"{t['retracted']['doi'] or t['retracted']['id']} (retracted {t['retracted']['retracted_at']})"
                                  for t in it["two_hop"][:3]]
        out["flagged"].append(d)
    out["more_flagged_not_shown"] = max(0, len(flagged) - max_items)
    out["not_in_corpus_count"] = result["summary"][UNKNOWN]
    out["note"] = result["caveats"][1]
    return out


def deterministic_summary(result: dict) -> str:
    """Plain summary used when the LLM is unavailable (no model involved)."""
    s = result["summary"]
    lines = [f"Checked {s['input']} DOIs: {s[RETRACTED]} retracted, {s[DIRECT]} cite a retracted work directly, "
             f"{s[TWO_HOP]} reach one through an intermediate paper, {s[CLEAN]} with no exposure found, "
             f"{s[UNKNOWN]} not in the corpus."]
    for it in result["items"]:
        if it["status"] == RETRACTED:
            lines.append(f"- {it['doi']} was retracted on {it['retraction']['date']}.")
        elif it["status"] == DIRECT:
            lines.append(f"- {it['doi']} cites retracted {it['direct'][0]['doi'] or it['direct'][0]['id']}.")
        elif it["status"] == TWO_HOP:
            t = it["two_hop"][0]
            lines.append(f"- {it['doi']} -> {t['via']['doi'] or t['via']['id']} -> {t['retracted']['doi'] or t['retracted']['id']}.")
    lines.append("No exposure found does not mean a paper is safe; see the caveats.")
    return "\n".join(lines[:14])


class AuditAgent:
    def __init__(self, graph, llm: ChatLike | None):
        self.auditor, self.llm = Auditor(graph), llm
        self.pasted_dois: list[str] = []
        self.seen: set[str] = set()
        self.trace: list[dict] = []
        self.explained = 0

    # ---- tools (all read-only) -------------------------------------------------
    def _allowed(self) -> set[str]:
        """DOIs the model may ask about: those in the pasted text or already returned by a tool.
        This stops a model that retypes or invents a DOI from steering the audit."""
        return set(self.pasted_dois) | self.seen

    def _tool_audit(self, args: dict):
        dois = args.get("dois")
        if not dois:                      # omitted or empty -> audit everything that was pasted
            dois = self.pasted_dois
        if not isinstance(dois, list) or not all(isinstance(d, str) for d in dois):
            return {"error": "'dois' must be a list of strings"}
        asked = extract_dois(" ".join(dois))[:300]
        allowed = self._allowed()
        dois = [d for d in asked if d in allowed]
        ignored = [d for d in asked if d not in allowed]
        if not dois:
            return {"error": "none of those DOIs appear in the user's text; call audit_bibliography without arguments",
                    "ignored_dois": ignored[:10]}
        self.seen.update(dois)
        result = compact_audit(self.auditor.audit(dois))
        if ignored:
            result["ignored_dois_not_in_user_text"] = ignored[:10]
        return result

    def _tool_explain(self, args: dict):
        doi = args.get("doi")
        found = extract_dois(doi) if isinstance(doi, str) else []
        if not found:
            return {"error": "'doi' must be one DOI string"}
        if found[0] not in self._allowed():
            return {"error": "that DOI does not appear in the user's text or earlier tool results"}
        if self.explained >= MAX_EXPLAIN:
            return {"error": f"explain_finding limit reached ({MAX_EXPLAIN}); write the answer now"}
        self.explained += 1
        item = self.auditor.audit([found[0]], max_two_hop=3, max_alternatives=3)["items"][0]
        out = {"doi": item["doi"], "status": item["status"]}
        if "retraction" in item:
            r = item["retraction"]
            out.update(retracted=r["date"], reasons=r["reasons"][:5], cited_by_indexed_papers=r["indexed_papers_citing_it"],
                       suggested_alternatives=[a["doi"] for a in item.get("alternatives", [])])
        if item.get("direct"):
            out["cites_retracted"] = [{"doi": d["doi"] or d["id"], "retracted": d["retracted_at"]} for d in item["direct"][:3]]
        if item.get("two_hop"):
            out["two_hop_paths"] = [f"{item['doi']} -> {t['via']['doi'] or t['via']['id']} -> {t['retracted']['doi'] or t['retracted']['id']}"
                                    for t in item["two_hop"][:3]]
        if item.get("coverage"):
            out["references_checked"] = f"{item['coverage']['refs_indexed']} of {item['coverage']['refs_total'] or '?'} indexed"
        return out

    def _tool_find(self, args: dict):
        text = args.get("text")
        return {"dois": extract_dois(text)[:300]} if isinstance(text, str) else {"error": "'text' must be a string"}

    def _run_tool(self, name: str, raw_args: str):
        try:
            args = json.loads(raw_args) if raw_args else {}
            if not isinstance(args, dict):
                raise ValueError
        except ValueError:
            return {"error": "tool arguments were not valid JSON"}
        if name == "audit_bibliography":
            result = self._tool_audit(args)
        elif name == "explain_finding":
            result = self._tool_explain(args)
        elif name == "find_dois":
            result = self._tool_find(args)
        else:
            return {"error": f"unknown tool '{name}'"}
        self.seen.update(extract_dois(json.dumps(result)))  # DOIs the model may quote = DOIs a tool returned
        return result

    # ---- main loop -------------------------------------------------------------
    def run(self, text: str, question: str = "") -> dict:
        self.pasted_dois = extract_dois(text)
        full = self.auditor.audit(self.pasted_dois)          # independent of the model
        out: dict = {"audit": full, "proposals": build_proposals(full), "trace": self.trace,
                     "model": getattr(self.llm, "model", None), "answer": "", "source": "fallback",
                     "verification": {"ok": True, "ungrounded": []}}
        if self.llm is None:
            out["answer"] = deterministic_summary(full)
            out["error"] = "The agent is not configured (set GROQ_API_KEY in .env); showing the plain audit summary."
            return out

        task = (question.strip() or "Audit this bibliography and tell me what to fix.")[:500]
        preview = text.strip()[:1000]
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"The user pasted a reference list ({len(text)} characters, "
                                                f"{len(self.pasted_dois)} DOIs detected). Start of the text:\n{preview}\n\nTask: {task}"}]
        final = None
        try:
            for step in range(MAX_STEPS):
                msg = self.llm.chat(messages, TOOLS)
                calls = msg.get("tool_calls") or []
                messages.append({"role": "assistant", "content": msg.get("content") or "", **({"tool_calls": calls} if calls else {})})
                if not calls:
                    final = (msg.get("content") or "").strip()
                    if msg.get("_finish_reason") == "length":
                        out["error"] = "The agent's answer was cut off by the token limit; the findings below are complete."
                    break
                for call in calls:
                    fn = (call.get("function") or {})
                    name, raw = fn.get("name", ""), fn.get("arguments", "")
                    t0 = time.time()
                    result = self._run_tool(name, raw)
                    self.trace.append({"step": step + 1, "tool": name, "arguments": raw[:200] or "{}",
                                       "ok": "error" not in result, "seconds": round(time.time() - t0, 3),
                                       "result": _brief(name, result)})
                    messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "name": name,
                                     "content": json.dumps(result)})
        except LLMError as exc:
            out["error"] = f"The agent could not finish ({exc}); showing the plain audit summary."
            out["answer"] = deterministic_summary(full)
            return out

        if not final:
            out["error"] = "The agent did not produce an answer in time; showing the plain audit summary."
            out["answer"] = deterministic_summary(full)
            return out
        allowed = set(self.pasted_dois) | self.seen
        ungrounded = sorted(set(extract_dois(final)) - allowed)
        out.update(answer=final, source="agent", usage=dict(getattr(self.llm, "usage", {})),
                   verification={"ok": not ungrounded, "ungrounded": ungrounded})
        return out


def _brief(name: str, result: dict) -> str:
    if "error" in result:
        return f"error: {result['error']}"
    if name == "audit_bibliography":
        s = result["summary"]
        return f"{s['input']} DOIs: {s[RETRACTED]} retracted, {s[DIRECT]} direct, {s[TWO_HOP]} two-hop, {s[CLEAN]} no exposure found, {s[UNKNOWN]} not in corpus"
    if name == "explain_finding":
        return f"{result['doi']}: {result['status']}"
    return f"{len(result.get('dois', []))} DOIs found"
