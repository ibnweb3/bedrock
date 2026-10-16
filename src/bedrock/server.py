"""Local web server for the Bedrock provenance audit (Python standard library only).

Binds to 127.0.0.1 by default. JSON in, JSON out; every graph question is answered by
FalkorDB through bedrock.audit. The server never trusts client-supplied audit results: the
approval step re-runs the audit from the submitted text and applies only approved proposal ids.
"""
from __future__ import annotations

import json
import mimetypes
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .agent import AuditAgent
from .audit import Auditor, apply_approved, build_proposals, extract_dois
from .config import load_settings
from .graph import connect
from .llm import GroqClient
from .ratelimit import Limits

WEB = Path(__file__).resolve().parent / "web"
STATIC = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/app.js": "app.js",
          "/favicon.svg": "favicon.svg", "/examples.json": "examples.json"}
MAX_BODY = 1_000_000
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

LIMITS = Limits()  # no-op unless BEDROCK_PUBLIC=1
_graph = None
_graph_lock = threading.Lock()
_agent_lock = threading.Lock()  # one agent run at a time: Groq's free tier has tight token budgets


def make_agent() -> AuditAgent:
    s = load_settings()
    llm = GroqClient(s.groq_api_key, s.groq_model) if s.groq_api_key else None
    return AuditAgent(graph(), llm)
_meta: dict = {}


def graph():
    global _graph
    with _graph_lock:
        if _graph is None:
            _graph = connect()
        return _graph


def corpus_meta() -> dict:
    if not _meta:
        g = graph()
        one = lambda q: g.ro_query(q, timeout=120000).result_set[0][0]  # noqa: E731
        _meta.update(
            papers_indexed=one("MATCH (p:Paper {full:true}) RETURN count(p)"),
            retracted_works=one("MATCH (p:Paper) WHERE p.retracted_at IS NOT NULL RETURN count(p)"),
        )
        root = Path(__file__).resolve().parents[2]
        # data/raw/ exists after running the pipeline; deploy/ carries a copy for the published snapshot.
        for meta_file in (root / "data" / "raw" / "retraction_watch.meta.json", root / "deploy" / "retraction_watch.meta.json"):
            if meta_file.exists():
                _meta["retraction_snapshot_downloaded_utc"] = json.loads(meta_file.read_text(encoding="utf-8")).get("downloaded_at_utc")
                break
    return dict(_meta)


class Handler(BaseHTTPRequestHandler):
    server_version = "Bedrock/0.1"

    def log_message(self, fmt, *args):  # keep the console quiet and free of request bodies
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def _client_ip(self) -> str:
        # Behind the host's proxy (BEDROCK_PUBLIC=1) the real client is the LAST X-Forwarded-For entry,
        # which the proxy appended; earlier entries are client-controlled and are ignored.
        if LIMITS.public:
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd.strip():
                return fwd.split(",")[-1].strip()[:64]
        return self.client_address[0]

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/health":
            try:
                st = load_settings()
                return self._json(200, {"ok": True, **corpus_meta(), "agent_available": bool(st.groq_api_key),
                                        "agent_model": st.groq_model if st.groq_api_key else None})
            except Exception:  # noqa: BLE001
                return self._json(503, {"ok": False, "error": "The graph database is not ready (it may still be loading; wait a few seconds and reload). Running locally? Start it with: docker compose up -d"})
        name = STATIC.get(path)
        if not name:
            return self._json(404, {"error": "not found"})
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._send(200, (WEB / name).read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("json") else ""))

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/api/audit", "/api/apply", "/api/agent"):
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            return self._json(413, {"error": "Request too large (limit 1 MB)."})
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            text = str(data.get("text", ""))
        except (ValueError, AttributeError):
            return self._json(400, {"error": "Send JSON with a 'text' field."})
        dois = extract_dois(text)
        if not dois:
            return self._json(400, {"error": "No DOIs found. Paste DOIs (like 10.1234/abc) or a reference list that contains them."})
        ip = self._client_ip()
        if not LIMITS.allow_audit(ip):
            return self._json(429, {"error": "Too many requests from your address this hour. Please try again later."})
        try:
            if path == "/api/agent":
                with _agent_lock:
                    if LIMITS.allow_agent_model(ip):
                        return self._json(200, make_agent().run(text, str(data.get("question", ""))[:500]))
                    out = AuditAgent(graph(), None).run(text, "")   # plain audit: spends no model tokens
                    out["rate_limited"] = True
                    out["error"] = ("The AI agent's budget for this public demo is used up (per visitor or for today). "
                                    "This is the plain graph audit; the findings are the same. Run the project locally for unlimited agent use.")
                    return self._json(200, out)
            result = Auditor(graph()).audit(dois)
            proposals = build_proposals(result)
            if path == "/api/audit":
                return self._json(200, {"audit": result, "proposals": proposals})
            approved = {str(x) for x in data.get("approved", []) if isinstance(x, str)}
            return self._json(200, apply_approved(result, proposals, approved))
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"audit failed: {type(exc).__name__}: {str(exc)[:200]}\n")
            return self._json(503, {"error": "The graph database did not answer. Is it running (docker compose up -d)?"})


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    load_settings()  # fail early on config problems
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Bedrock audit: http://{host}:{port}   (Ctrl+C to stop)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
