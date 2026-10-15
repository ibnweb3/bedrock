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

from .audit import Auditor, apply_approved, build_proposals, extract_dois
from .config import load_settings
from .graph import connect

WEB = Path(__file__).resolve().parent / "web"
STATIC = {"/": "index.html", "/index.html": "index.html", "/style.css": "style.css", "/app.js": "app.js",
          "/favicon.svg": "favicon.svg", "/examples.json": "examples.json"}
MAX_BODY = 1_000_000
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

_graph = None
_graph_lock = threading.Lock()
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
        meta_file = Path(__file__).resolve().parents[2] / "data" / "raw" / "retraction_watch.meta.json"
        if meta_file.exists():
            _meta["retraction_snapshot_downloaded_utc"] = json.loads(meta_file.read_text(encoding="utf-8")).get("downloaded_at_utc")
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

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/health":
            try:
                return self._json(200, {"ok": True, **corpus_meta()})
            except Exception:  # noqa: BLE001
                return self._json(503, {"ok": False, "error": "The graph database is not reachable. Start it with: docker compose up -d"})
        name = STATIC.get(path)
        if not name:
            return self._json(404, {"error": "not found"})
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._send(200, (WEB / name).read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("json") else ""))

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/api/audit", "/api/apply"):
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
        try:
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
