"""Add Paper.ref_total (the number of references in the source record) to the loaded graph.

The loader keeps only some references (pruned stubs), so an audit must say how much of a paper's
bibliography is actually indexed. ref_total is read from the staging files; nothing else changes.

    python scripts/add_ref_totals.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from falkordb import FalkorDB  # noqa: E402

from bedrock.config import load_settings  # noqa: E402
from bedrock.graph import read_query, run_statements  # noqa: E402


def main() -> int:
    s = load_settings()
    g = FalkorDB(host=s.falkordb_host, port=s.falkordb_port).select_graph(s.graph_name)
    run_statements(g, read_query("00_schema.cypher"))  # idempotent; adds the DOI index
    totals: dict[str, int] = {}
    for name in ("candidates.jsonl", "retracted_works.jsonl"):
        with open(ROOT / "data" / "staging" / name, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                totals.setdefault(r["id"], len(set(r["refs"])))
    rows = [{"id": k, "n": v} for k, v in totals.items()]
    t = time.time()
    for i in range(0, len(rows), 5000):
        g.query("UNWIND $rows AS r MATCH (p:Paper {id:r.id}) SET p.ref_total = r.n", {"rows": rows[i : i + 5000]}, timeout=600000)
        if (i // 5000) % 10 == 0:
            print(f"  {i + 5000:,}/{len(rows):,}  [{time.time()-t:.0f}s]", flush=True)
    n = g.ro_query("MATCH (p:Paper) WHERE p.ref_total IS NOT NULL RETURN count(p)", timeout=120000).result_set[0][0]
    print("papers with ref_total:", n)
    print("indexes:", sorted(x[0] for x in g.ro_query("CALL db.indexes() YIELD label, properties RETURN label + ':' + properties[0]").result_set))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
