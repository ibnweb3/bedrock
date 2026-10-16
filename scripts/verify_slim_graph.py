"""Prove the slim (audit-only) graph gives IDENTICAL audit results to the full graph.

    python scripts/verify_slim_graph.py --full bedrock --slim bedrock_demo [--n 2000]

Samples corpus DOIs and retracted DOIs, audits them on both graphs, and compares the complete result
(statuses, paths, reasons, coverage, venue context, alternatives). Also reports FalkorDB's memory use.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from falkordb import FalkorDB  # noqa: E402

from bedrock.audit import Auditor  # noqa: E402
from bedrock.config import load_settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", default="bedrock")
    ap.add_argument("--slim", default="bedrock_demo")
    ap.add_argument("--n", type=int, default=2000, help="corpus DOIs to sample (plus n/4 retracted)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    s = load_settings()
    db = FalkorDB(host=s.falkordb_host, port=s.falkordb_port)
    gf, gs = db.select_graph(a.full), db.select_graph(a.slim)

    def sample(g, where: str, k: int) -> list[str]:
        rows = g.ro_query(f"MATCH (p:Paper) WHERE {where} AND p.doi IS NOT NULL RETURN p.doi", timeout=300000).result_set
        dois = sorted(r[0] for r in rows)
        return random.Random(a.seed).sample(dois, min(k, len(dois)))

    dois = sample(gf, "p.candidate = true AND p.retracted_at IS NULL", a.n) + sample(gf, "p.retracted_at IS NOT NULL", a.n // 4)
    dois += ["10.0000/not-a-real-doi"]
    mism = 0
    kinds: dict[str, int] = {}
    for i in range(0, len(dois), 100):
        chunk = dois[i : i + 100]
        rf, rs = Auditor(gf).audit(chunk), Auditor(gs).audit(chunk)
        for itf, its in zip(rf["items"], rs["items"]):
            kinds[itf["status"]] = kinds.get(itf["status"], 0) + 1
            if json.dumps(itf, sort_keys=True) != json.dumps(its, sort_keys=True):
                mism += 1
                if mism <= 3:
                    print("MISMATCH", itf["doi"], "\n  full:", json.dumps(itf)[:300], "\n  slim:", json.dumps(its)[:300])
    print(f"audited {len(dois)} DOIs on both graphs; status mix {kinds}")
    print(f"mismatching items: {mism}")
    for name in (a.full, a.slim):
        try:
            u = db.connection.execute_command("GRAPH.MEMORY", "USAGE", name)
            d = dict(zip(u[0::2], u[1::2]))
            print(f"graph '{name}': total {int(d.get('total_graph_sz_mb', 0))} MB "
                  f"(nodes {int(d.get('node_count', 0)):,}, edges {int(d.get('edge_count', 0)):,})")
        except Exception as exc:  # noqa: BLE001
            print(f"graph '{name}': memory usage unavailable ({type(exc).__name__})")
    return 0 if mism == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
