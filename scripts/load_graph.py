"""Load staged data into FalkorDB (ETL only; all graph reasoning happens later, in FalkorDB).

    python scripts/load_graph.py --dry-run                      # counts after pruning, no DB writes
    python scripts/load_graph.py --graph bedrock_test --limit 2000 --reset   # throughput test
    python scripts/load_graph.py --reset                         # full load into the configured graph

Pruning (keeps the graph small without losing any signal):
- a cited-only paper becomes a stub node only if it is cited by >= 2 papers we hold in full
  (a work cited once can link nothing) and by no more than --max-cited (default 500);
- an author is kept only if they appear on >= 2 papers (a single-paper author links nothing).

Authors in the staging files are already salted hashes; no names, ORCIDs or affiliations exist
here. Papers are de-duplicated by DOI (OpenAlex sometimes has two works per DOI).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bedrock.config import load_settings  # noqa: E402
from bedrock.graph import read_query, run_statements  # noqa: E402

STAGING = ROOT / "data" / "staging"


def load_jsonl(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_dataset(limit: int = 0, max_cited: int = 500, audit_only: bool = False) -> dict:
    venues_cfg = json.loads((STAGING / "venues.json").read_text(encoding="utf-8"))
    stratum = {v["id"]: s for s, vs in venues_cfg["strata"].items() for v in vs}
    names = {v["id"]: v["name"] for vs in venues_cfg["strata"].values() for v in vs}

    # earliest retraction per DOI (nature == Retraction only)
    ret: dict[str, dict] = {}
    for r in load_jsonl(STAGING / "retractions.jsonl"):
        if r["nature"] != "Retraction" or not r["retraction_date"]:
            continue
        cur = ret.get(r["doi"])
        if cur is None or r["retraction_date"] < cur["date"]:
            ret[r["doi"]] = {"date": r["retraction_date"], "reasons": r["reasons"]}

    papers: dict[str, dict] = {}
    doi_seen: dict[str, str] = {}
    stats = Counter()

    def add(rec: dict, candidate: bool) -> None:
        pid, doi = rec["id"], rec["doi"]
        if pid in papers:
            papers[pid]["candidate"] = papers[pid]["candidate"] or candidate
            return
        if doi and doi in doi_seen:
            stats["duplicate_doi_skipped"] += 1
            return
        if doi:
            doi_seen[doi] = pid
        row = {
            "id": pid, "doi": doi, "pub_date": rec["pub_date"], "venue_id": rec["venue_id"],
            "refs": [x for x in rec["refs"] if x != pid], "authors": rec["authors"],
            "candidate": candidate,
        }
        r = ret.get(doi) if doi else None
        if r:
            row["retracted_at"], row["retraction_reasons"] = r["date"], r["reasons"]
        papers[pid] = row

    n = 0
    for rec in load_jsonl(STAGING / "candidates.jsonl"):
        add(rec, True)
        n += 1
        if limit and n >= limit:
            break
    n_cand = len(papers)
    if not limit:
        for rec in load_jsonl(STAGING / "retracted_works.jsonl"):
            add(rec, False)
    else:  # test mode: keep the sample small but include some retracted papers
        for i, rec in enumerate(load_jsonl(STAGING / "retracted_works.jsonl")):
            add(rec, False)
            if i >= limit // 2:
                break

    # pruning
    cite_n: Counter = Counter()
    author_n: Counter = Counter()
    for p in papers.values():
        cite_n.update(set(p["refs"]))
        author_n.update(set(p["authors"]))
    # stubs: cited by >= 2 held papers, but not by more than max_cited (ubiquitous classics link
    # everything to everything and only bloat the graph). Edges to FULL papers are always kept.
    stub_ids = {r for r, c in cite_n.items() if 2 <= c <= max_cited and r not in papers}
    keep_authors = {a for a, c in author_n.items() if c >= 2}
    cites = [(pid, r) for pid, p in papers.items() for r in set(p["refs"]) if r in papers or r in stub_ids]
    wrote = [(a, pid) for pid, p in papers.items() for a in p["authors"] if a in keep_authors]
    venue_ids = {p["venue_id"] for p in papers.values() if p["venue_id"]}

    # Coverage figures the audit reports. Stored as properties so they survive --audit-only below.
    indexed = Counter(pid for pid, _ in cites)
    for pid, p in papers.items():
        p["ref_total"], p["refs_indexed"] = len(set(p["refs"])), indexed[pid]
    if audit_only:
        # The audit only follows CITES between papers held in full: a cited-only stub has no outgoing
        # edges and is never retracted, so no exposure path can run through one. Authors, co-authorship
        # and coupling are not used by the audit either. Findings are identical; the graph is ~15x smaller.
        stub_ids, keep_authors, wrote = set(), set(), []
        cites = [(a, b) for a, b in cites if b in papers]

    stats.update({
        "papers_full": len(papers), "papers_candidate": sum(p["candidate"] for p in papers.values()),
        "papers_retracted": sum("retracted_at" in p for p in papers.values()),
        "papers_in_candidates_file": n_cand,
        "stubs": len(stub_ids), "refs_dropped_too_popular": sum(1 for r, c in cite_n.items() if c > max_cited and r not in papers), "authors_kept": len(keep_authors), "authors_total": len(author_n),
        "venues": len(venue_ids), "cites_edges": len(cites), "cites_edges_before_prune": sum(len(set(p["refs"])) for p in papers.values()),
        "wrote_edges": len(wrote), "wrote_edges_before_prune": sum(len(p["authors"]) for p in papers.values()),
    })
    return {"papers": papers, "stubs": sorted(stub_ids), "authors": sorted(keep_authors), "cites": cites,
            "wrote": wrote, "venues": sorted(venue_ids), "stratum": stratum, "names": names, "stats": stats}


def batches(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def timed(label: str, total: int, fn, items, size: int) -> None:
    t0 = time.time()
    done = 0
    for b in batches(items, size):
        fn(b)
        done += len(b)
        if (done // size) % 25 == 0 or done == len(items):
            rate = done / max(time.time() - t0, 1e-6)
            eta = (total - done) / rate if rate else 0
            print(f"  {label}: {done}/{total}  {rate:,.0f}/s  eta {eta/60:.1f} min", flush=True)


def load(ds: dict, graph) -> None:
    run_statements(graph, read_query("00_schema.cypher"))
    P = ds["papers"]

    vrows = [{"id": v, "name": ds["names"].get(v), "stratum": ds["stratum"].get(v), "in_pool": v in ds["stratum"]}
             for v in ds["venues"]]
    timed("venues", len(vrows), lambda b: graph.query(
        "UNWIND $rows AS r CREATE (:Venue {id:r.id, name:r.name, stratum:r.stratum, in_pool:r.in_pool})",
        {"rows": b}), vrows, 2000)

    prows = [{k: v for k, v in p.items() if k not in ("refs", "authors")} | {"full": True} for p in P.values()]
    timed("papers", len(prows), lambda b: graph.query(
        "UNWIND $rows AS r CREATE (:Paper {id:r.id, doi:r.doi, pub_date:r.pub_date, venue_id:r.venue_id, "
        "candidate:r.candidate, full:r.full, retracted_at:r.retracted_at, retraction_reasons:r.retraction_reasons, "
        "ref_total:r.ref_total, refs_indexed:r.refs_indexed})",
        {"rows": b}), prows, 2000)

    timed("stubs", len(ds["stubs"]), lambda b: graph.query(
        "UNWIND $ids AS i CREATE (:Paper {id:i, full:false})", {"ids": b}), ds["stubs"], 5000)
    timed("authors", len(ds["authors"]), lambda b: graph.query(
        "UNWIND $ids AS i CREATE (:Author {id:i})", {"ids": b}), ds["authors"], 5000)

    pv = [{"p": pid, "v": p["venue_id"]} for pid, p in P.items() if p["venue_id"]]
    timed("PUBLISHED_IN", len(pv), lambda b: graph.query(
        "UNWIND $rows AS r MATCH (p:Paper {id:r.p}), (v:Venue {id:r.v}) CREATE (p)-[:PUBLISHED_IN]->(v)",
        {"rows": b}), pv, 2000)
    wr = [{"a": a, "p": p} for a, p in ds["wrote"]]
    timed("WROTE", len(wr), lambda b: graph.query(
        "UNWIND $rows AS r MATCH (a:Author {id:r.a}), (p:Paper {id:r.p}) CREATE (a)-[:WROTE]->(p)",
        {"rows": b}), wr, 2000)
    ct = [{"a": a, "b": b} for a, b in ds["cites"]]
    timed("CITES", len(ct), lambda b: graph.query(
        "UNWIND $rows AS r MATCH (a:Paper {id:r.a}), (b:Paper {id:r.b}) CREATE (a)-[:CITES]->(b)",
        {"rows": b}), ct, 2000)


def verify(graph) -> None:
    q = lambda s: graph.query(s).result_set  # noqa: E731
    print("\nverification (counts read back from FalkorDB):")
    for label in ("Paper", "Author", "Venue"):
        print(f"  (:{label})", q(f"MATCH (n:{label}) RETURN count(n)")[0][0])
    for rel in ("CITES", "WROTE", "PUBLISHED_IN"):
        print(f"  [:{rel}]", q(f"MATCH ()-[r:{rel}]->() RETURN count(r)")[0][0])
    print("  full papers", q("MATCH (p:Paper {full:true}) RETURN count(p)")[0][0],
          "| candidates", q("MATCH (p:Paper {candidate:true}) RETURN count(p)")[0][0],
          "| with retracted_at", q("MATCH (p:Paper) WHERE p.retracted_at IS NOT NULL RETURN count(p)")[0][0])
    # Start from the retracted papers and walk INCOMING citations: starting from all candidates
    # scans every outgoing edge and exceeds FalkorDB's default 1 s query timeout.
    row = graph.ro_query(
        "MATCH (r:Paper) WHERE r.retracted_at IS NOT NULL "
        "MATCH (c:Paper {candidate:true})-[:CITES]->(r) RETURN count(DISTINCT c), count(*)",
        timeout=120000,
    ).result_set[0]
    print(f"  candidates citing a retracted paper directly (any retraction date): {row[0]} papers via {row[1]} citations")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true", help="delete the target graph first")
    ap.add_argument("--graph", default="", help="graph name (default FALKORDB_GRAPH)")
    ap.add_argument("--limit", type=int, default=0, help="test mode: only the first N candidates")
    ap.add_argument("--max-cited", type=int, default=500, help="drop stub refs cited by more papers than this")
    ap.add_argument("--audit-only", action="store_true",
                    help="slim graph for the audit app: papers + CITES between held papers + venues only")
    args = ap.parse_args()

    t0 = time.time()
    ds = build_dataset(args.limit, args.max_cited, args.audit_only)
    print("dataset built in %.0fs" % (time.time() - t0))
    for k, v in ds["stats"].items():
        print(f"  {k:<28}{v:>12,}")
    if args.dry_run:
        return 0

    from falkordb import FalkorDB  # noqa: E402

    s = load_settings()
    name = args.graph or s.graph_name
    db = FalkorDB(host=s.falkordb_host, port=s.falkordb_port)
    graph = db.select_graph(name)
    if args.reset:
        try:
            graph.delete()
            print(f"deleted existing graph '{name}'")
        except Exception:  # noqa: BLE001 - graph may not exist yet
            pass
        graph = db.select_graph(name)
    load(ds, graph)
    verify(graph)
    print(f"\nloaded into graph '{name}' in {(time.time() - t0)/60:.1f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
