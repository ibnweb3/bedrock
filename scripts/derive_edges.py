"""Build the derived edges (COAUTHOR, BIB_COUPLED) inside FalkorDB and verify samples.

    python scripts/derive_edges.py                 # build + verify
    python scripts/derive_edges.py --no-verify

All derivation is Cypher in queries/ executed by FalkorDB (hackathon rules 2 and 3). The
verification step re-derives a random sample of edges, and a sample of should-exist edges, from
the raw staging data in Python and compares - that is a check on the edges, not part of the product.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from falkordb import FalkorDB  # noqa: E402

from bedrock.config import load_settings  # noqa: E402
from bedrock.graph import read_query  # noqa: E402

TIMEOUT = 900_000


def cypher(name: str) -> str:
    """File content without // comment lines (FalkorDB parses comments, but keep logs clean)."""
    return "\n".join(l for l in read_query(name).splitlines() if not l.strip().startswith("//"))


def verify(graph, max_cited: int, min_shared: int, n: int, seed: int) -> bool:
    sys.path.insert(0, str(ROOT / "scripts"))
    from load_graph import build_dataset  # noqa: E402  (staging -> same dataset the loader used)

    print("\nverification: rebuilding the loader's dataset from staging files ...", flush=True)
    ds = build_dataset(0, 500)
    P = ds["papers"]
    indeg = defaultdict(int)
    for _, r in ds["cites"]:
        indeg[r] += 1
    refs_in_graph = defaultdict(set)
    for a, r in ds["cites"]:
        refs_in_graph[a].add(r)
    rng = random.Random(seed)
    ok = True

    def shared_count(x: str, y: str) -> int:
        return sum(1 for r in refs_in_graph[x] & refs_in_graph[y] if indeg[r] <= max_cited)

    # 1) edges present in the graph must have the right weight
    rows = graph.ro_query(
        "MATCH (a:Paper)-[b:BIB_COUPLED]->(c:Paper) WITH a, b, c, rand() AS x ORDER BY x LIMIT $n "
        "RETURN a.id, c.id, b.shared", {"n": n}, timeout=TIMEOUT).result_set
    bad = [(a, b, s, shared_count(a, b)) for a, b, s in rows if shared_count(a, b) != s]
    print(f"  BIB_COUPLED weights: {len(rows) - len(bad)}/{len(rows)} sampled edges match recomputation")
    ok &= not bad

    # 2) pairs that SHOULD be coupled (found via a random shared reference) must exist
    by_ref = defaultdict(list)
    for a, r in ds["cites"]:
        if 2 <= indeg[r] <= max_cited:
            by_ref[r].append(a)
    cand_refs = [r for r, v in by_ref.items() if len(v) >= 2]
    missing = checked = 0
    for _ in range(n * 5):
        r = rng.choice(cand_refs)
        x, y = rng.sample(by_ref[r], 2)
        if shared_count(x, y) >= min_shared:
            a, b = (x, y) if x < y else (y, x)
            exists = graph.ro_query(
                "MATCH (a:Paper {id:$a})-[e:BIB_COUPLED]->(b:Paper {id:$b}) RETURN e.shared",
                {"a": a, "b": b}).result_set
            checked += 1
            missing += not exists
            if checked == n:
                break
    print(f"  BIB_COUPLED completeness: {checked - missing}/{checked} should-exist pairs found in the graph")
    ok &= missing == 0

    # 3) COAUTHOR: weight (n) and earliest joint date (first)
    papers_of = defaultdict(set)
    for a, pid in ds["wrote"]:
        papers_of[a].add(pid)
    rows = graph.ro_query(
        "MATCH (a:Author)-[c:COAUTHOR]->(b:Author) WITH a, b, c, rand() AS x ORDER BY x LIMIT $n "
        "RETURN a.id, b.id, c.n, c.first", {"n": n}, timeout=TIMEOUT).result_set
    bad = 0
    for a, b, cn, first in rows:
        joint = papers_of[a] & papers_of[b]
        dates = [P[p]["pub_date"] for p in joint if P[p]["pub_date"]]
        if len(joint) != cn or (min(dates) if dates else None) != first:
            bad += 1
    print(f"  COAUTHOR n/first: {len(rows) - bad}/{len(rows)} sampled edges match recomputation")
    ok &= bad == 0
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-shared", type=int, default=2)
    ap.add_argument("--max-cited", type=int, default=50)
    ap.add_argument("--slices", type=int, default=20)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    s = load_settings()
    graph = FalkorDB(host=s.falkordb_host, port=s.falkordb_port).select_graph(s.graph_name)
    t0 = time.time()

    graph.query(cypher("05_cited_n.cypher"), timeout=TIMEOUT)
    print(f"cited_n set  [{time.time()-t0:.0f}s]", flush=True)

    for rel in ("COAUTHOR", "BIB_COUPLED"):  # idempotent rebuild
        graph.query(f"MATCH ()-[e:{rel}]->() DELETE e", timeout=TIMEOUT)

    t = time.time()
    graph.query(cypher("10_derive_coauthor.cypher"), timeout=TIMEOUT)
    n_co = graph.ro_query("MATCH ()-[e:COAUTHOR]->() RETURN count(e)", timeout=TIMEOUT).result_set[0][0]
    print(f"COAUTHOR edges: {n_co:,}  [{time.time()-t:.0f}s]", flush=True)

    q = cypher("11_derive_bib_coupled.cypher")
    t = time.time()
    total = 0
    for k in range(args.slices):
        total += graph.query(q, {"m": args.slices, "k": k, "max_cited": args.max_cited,
                                 "min_shared": args.min_shared}, timeout=TIMEOUT).result_set[0][0]
        if (k + 1) % 5 == 0 or k + 1 == args.slices:
            print(f"  BIB_COUPLED slice {k+1}/{args.slices}: {total:,} edges so far  [{time.time()-t:.0f}s]", flush=True)
    n_bc = graph.ro_query("MATCH ()-[e:BIB_COUPLED]->() RETURN count(e)", timeout=TIMEOUT).result_set[0][0]
    print(f"BIB_COUPLED edges read back: {n_bc:,} (created {total:,})", flush=True)
    assert n_bc == total, "created and read-back counts differ"

    ok = True
    if not args.no_verify:
        ok = verify(graph, args.max_cited, args.min_shared, args.sample, args.seed)
    print(f"\nderived edges done in {(time.time()-t0)/60:.1f} min; verification {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
