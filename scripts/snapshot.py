"""Export / restore the slim audit graph as a compressed FalkorDB snapshot (Redis DUMP / RESTORE).

    python scripts/snapshot.py export  --graph bedrock_demo --out deploy/bedrock_slim.rdb.gz
    python scripts/snapshot.py restore --file deploy/bedrock_slim.rdb.gz --graph bedrock [--force]

The snapshot is the slim graph built by `load_graph.py --audit-only` (papers, CITES between held papers,
venues; hashed ids only - no author data). It was proven to give identical audit output to the full graph
(scripts/verify_slim_graph.py). DUMP payloads are tied to the FalkorDB module version, so the version is
recorded in a manifest next to the file; docs/DEPLOY.md says how to rebuild from raw data instead.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import redis  # noqa: E402  (installed with the falkordb client)
import redis.backoff  # noqa: E402
import redis.retry  # noqa: E402

from bedrock.config import load_settings  # noqa: E402


def raw_client(wait_s: int = 0) -> redis.Redis:
    s = load_settings()
    # bytes in/out: DUMP is binary. RESTORE decodes and indexes 300k nodes, which can take minutes on a tiny
    # CPU, so no socket timeout and no automatic retry (a retry would start a second restore).
    r = redis.Redis(host=s.falkordb_host, port=s.falkordb_port, socket_timeout=None,
                    retry=redis.retry.Retry(redis.backoff.NoBackoff(), 0))
    deadline = time.time() + wait_s
    while True:
        try:
            r.ping()
            return r
        except redis.exceptions.ConnectionError:
            if time.time() >= deadline:
                raise
            time.sleep(1)


def graph_counts(r: redis.Redis, graph: str) -> dict:
    nodes = r.execute_command("GRAPH.RO_QUERY", graph, "MATCH (n) RETURN count(n)")[1][0][0]
    edges = r.execute_command("GRAPH.RO_QUERY", graph, "MATCH ()-[e]->() RETURN count(e)")[1][0][0]
    return {"nodes": int(nodes), "edges": int(edges)}


def module_version(r: redis.Redis) -> str:
    def text(v):
        return v.decode() if isinstance(v, bytes) else v

    for m in r.module_list():          # redis-py parses each module into a dict
        d = {text(k): text(v) for k, v in m.items()}
        if d.get("name") == "graph":
            return str(d.get("ver"))
    return "unknown"


def export(a) -> int:
    r = raw_client()
    blob = r.dump(a.graph)
    if blob is None:
        print(f"No graph key named '{a.graph}'.", file=sys.stderr)
        return 1
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.GzipFile(out, "wb", compresslevel=9, mtime=0) as f:  # mtime=0: reproducible bytes
        f.write(blob)
    manifest = {
        "graph_key_at_export": a.graph, "dump_bytes": len(blob), "gzip_bytes": out.stat().st_size,
        "sha256_of_gzip": hashlib.sha256(out.read_bytes()).hexdigest(),
        "falkordb_module_version": module_version(r), **graph_counts(r, a.graph),
    }
    out.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


def restore(a) -> int:
    r = raw_client(wait_s=a.wait)
    if r.exists(a.graph) and not a.force:
        print(f"Graph '{a.graph}' already present ({graph_counts(r, a.graph)}); nothing to do (use --force to replace).")
        return 0
    path = Path(a.file)
    manifest_file = path.with_suffix(".manifest.json")
    blob = gzip.decompress(path.read_bytes())
    if manifest_file.exists():
        want = json.loads(manifest_file.read_text(encoding="utf-8"))
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want["sha256_of_gzip"]:
            print("Snapshot checksum does not match its manifest; refusing to load.", file=sys.stderr)
            return 1
    r.restore(a.graph, 0, blob, replace=True)
    counts = graph_counts(r, a.graph)
    print(f"Restored '{a.graph}': {counts}")
    if manifest_file.exists() and (counts["nodes"], counts["edges"]) != (want["nodes"], want["edges"]):
        print("Restored counts differ from the manifest.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--graph", default="bedrock_demo")
    e.add_argument("--out", default=str(ROOT / "deploy" / "bedrock_slim.rdb.gz"))
    e.set_defaults(fn=export)
    s = sub.add_parser("restore")
    s.add_argument("--file", default=str(ROOT / "deploy" / "bedrock_slim.rdb.gz"))
    s.add_argument("--graph", default=load_settings().graph_name)
    s.add_argument("--force", action="store_true")
    s.add_argument("--wait", type=int, default=0, help="seconds to wait for the database to accept connections")
    s.set_defaults(fn=restore)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
