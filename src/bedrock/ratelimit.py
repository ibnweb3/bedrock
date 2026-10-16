"""Small in-memory rate limiter for the public demo (stdlib only).

Active only when BEDROCK_PUBLIC=1. It protects the free Groq quota behind /api/agent and keeps one visitor
from hogging the database. Limits reset on restart; that is acceptable for a demo, and the plain audit
(no model) stays available when the agent budget is used up.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque


class SlidingWindow:
    def __init__(self, limit: int, window_s: float, *, max_keys: int = 5000, clock=time.monotonic):
        self.limit, self.window, self.max_keys, self.clock = limit, window_s, max_keys, clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            if key not in self._hits and len(self._hits) >= self.max_keys:
                for k in [k for k, q in self._hits.items() if not q or now - q[-1] > self.window]:
                    del self._hits[k]
                if len(self._hits) >= self.max_keys:   # still full: refuse new keys rather than grow without bound
                    return False
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


class Limits:
    """Per-IP and global budgets. `public=False` (local use) allows everything."""

    def __init__(self, public: bool | None = None, clock=time.monotonic):
        self.public = os.environ.get("BEDROCK_PUBLIC") == "1" if public is None else public
        self.audit_ip = SlidingWindow(_env_int("BEDROCK_AUDIT_PER_IP_HOUR", 120), 3600, clock=clock)
        self.agent_ip = SlidingWindow(_env_int("BEDROCK_AGENT_PER_IP_HOUR", 6), 3600, clock=clock)
        self.agent_day = SlidingWindow(_env_int("BEDROCK_AGENT_PER_DAY", 100), 86400, clock=clock)

    def allow_audit(self, ip: str) -> bool:
        return not self.public or self.audit_ip.allow(ip)

    def allow_agent_model(self, ip: str) -> bool:
        """True if this request may spend model tokens. Checks the per-IP budget first so one visitor
        cannot drain the global daily budget."""
        if not self.public:
            return True
        return self.agent_ip.allow(ip) and self.agent_day.allow("all")
