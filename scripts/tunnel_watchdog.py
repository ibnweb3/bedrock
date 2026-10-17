"""Keeps the public demo reachable: runs a Cloudflare quick tunnel to the local app, and when the tunnel dies
(quick tunnels are free and can be dropped without warning) starts a new one, writes its address into
site/index.html and redeploys the product page, so the link on the page always works.

    python scripts/tunnel_watchdog.py [--port 8780] [--interval 60]

Needs: cloudflared installed, the app container running on --port (this script also restarts the container
named bedrock-live if the local app stops answering), and `npx wrangler` logged in. The product page itself is
the stable address to give people; it carries the current live link. Log: data/staging/watchdog.log

Start at logon (Windows): see docs/DEPLOY.md, "Keeping the public demo alive".
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "site" / "index.html"
LOG = ROOT / "data" / "staging" / "watchdog.log"
TUNNEL_LOG = ROOT / "data" / "staging" / "tunnel.log"
PIDFILE = ROOT / "data" / "staging" / "tunnel.pid"
CLOUDFLARED = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
DOCKER_DESKTOP = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
LIVE_RE = re.compile(r'(live:\s*")https://[a-z0-9-]+\.trycloudflare\.com(")')


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def healthy(base: str, timeout: float = 15) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/api/health", timeout=timeout) as r:
            return r.status == 200 and json.load(r).get("ok") is True
    except Exception:  # noqa: BLE001
        return False


def docker_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=25).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def ensure_app(local: str) -> None:
    """Docker Desktop is not set to start at login, so start it here if needed, then start the app container."""
    if not docker_up():
        log("Docker is not running; starting Docker Desktop")
        try:
            subprocess.Popen([DOCKER_DESKTOP])
        except OSError as exc:
            log(f"could not start Docker Desktop: {exc}")
            return
        for _ in range(48):          # up to 4 minutes
            time.sleep(5)
            if docker_up():
                break
        else:
            log("Docker did not come up in time; will retry")
            return
    subprocess.run(["docker", "start", "bedrock-live"], capture_output=True)
    for _ in range(40):              # the graph snapshot loads in a few seconds to about a minute
        time.sleep(3)
        if healthy(local, 5):
            log("app container is answering")
            return
    log("app container started but is not answering yet")


def current_url() -> str | None:
    m = LIVE_RE.search(PAGE.read_text(encoding="utf-8"))
    return m.group(0).split('"')[1] if m else None


def kill_our_tunnel() -> None:
    if PIDFILE.exists():
        pid = PIDFILE.read_text().strip()
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)  # only the process this script started
        PIDFILE.unlink(missing_ok=True)


def start_tunnel(port: int) -> str | None:
    kill_our_tunnel()
    TUNNEL_LOG.write_text("", encoding="utf-8")
    out = TUNNEL_LOG.open("a", encoding="utf-8")
    p = subprocess.Popen([CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
                         stdout=out, stderr=subprocess.STDOUT)
    PIDFILE.write_text(str(p.pid))
    for _ in range(40):
        time.sleep(1)
        m = URL_RE.search(TUNNEL_LOG.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(0)
    return None


def publish(url: str) -> bool:
    html = PAGE.read_text(encoding="utf-8")
    if not LIVE_RE.search(html):
        log("could not find the live link in site/index.html")
        return False
    PAGE.write_text(LIVE_RE.sub(lambda m: m.group(1) + url + m.group(2), html), encoding="utf-8", newline="")
    r = subprocess.run("npx --yes wrangler deploy", cwd=ROOT, shell=True, capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0
    log(f"page redeployed with {url}" if ok else f"wrangler deploy FAILED: {(r.stderr or r.stdout)[-300:]}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--interval", type=int, default=60)
    a = ap.parse_args()
    # Single instance: holding this local port is the lock. A second copy (for example the logon task while one is
    # already running) exits at once instead of starting a competing tunnel.
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 47831))
    except OSError:
        log("another watchdog is already running; exiting")
        return 0
    local = f"http://127.0.0.1:{a.port}"
    fails = 0
    log(f"watchdog started (local {local}, every {a.interval}s)")
    while True:
        try:
            if not healthy(local, 5):
                log("local app not answering")
                ensure_app(local)
            url = current_url()
            if url and healthy(url):
                fails = 0
            else:
                fails += 1
                log(f"public link not healthy ({fails}/2): {url}")
                if fails >= 2 or not url:
                    new = start_tunnel(a.port)
                    if new:
                        time.sleep(8)
                        log(f"new tunnel {new}, healthy={healthy(new)}")
                        publish(new)
                        fails = 0
                    else:
                        log("tunnel did not come up; will retry")
        except Exception as exc:  # noqa: BLE001
            log(f"watchdog error: {type(exc).__name__}: {exc}")
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
