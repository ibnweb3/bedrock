"""Compute baselines and graph signals for every candidate as of a cutoff T0.

    python scripts/compute_features.py --t0 20201231

All signals are Cypher in queries/features/ executed by FalkorDB; this script only passes the
cutoff parameters, joins the per-candidate results, and writes data/staging/features_<T0>.jsonl.
Scratch labels/properties (RetAuth, AsOf, comm) are always removed afterwards.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from falkordb import FalkorDB  # noqa: E402

from bedrock.config import load_settings  # noqa: E402
from bedrock.graph import read_query  # noqa: E402
from bedrock.venues import add_months  # noqa: E402

TIMEOUT = 900_000


def q(name: str) -> str:
    return "\n".join(l for l in read_query(f"features/{name}.cypher").splitlines() if not l.strip().startswith("//"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t0", type=int, required=True)
    args = ap.parse_args()
    t0 = args.t0
    params = {"t0": t0, "lo": t0 - 40000, "end": add_months(t0, 24)}

    s = load_settings()
    db = FalkorDB(host=s.falkordb_host, port=s.falkordb_port)
    g = db.select_graph(s.graph_name)
    db.connection.execute_command("GRAPH.CONFIG", "SET", "RESULTSET_SIZE", "-1")  # lift the 10k-row cap (local DB)

    def run(name: str, p: dict | None = None):
        t = time.time()
        rows = g.query(q(name), p if p is not None else params, timeout=TIMEOUT).result_set
        print(f"  {name:<32}{len(rows):>9,} rows  [{time.time()-t:5.1f}s]", flush=True)
        return rows

    print(f"T0={t0}  window=({params['lo']}, {t0}]  label window=({t0}, {params['end']}]")
    # make sure no scratch state is left from an earlier crashed run
    g.query(q("35_unmark_retracted_authors"), timeout=TIMEOUT)
    g.query(q("3A_cleanup_asof"), timeout=TIMEOUT)

    try:
        run("37_label_asof")
        run("38_community")
        cand = run("20_candidates")
        comm_stats = {r[0]: (r[1], r[2]) for r in run("39_community_stats")}
        venue_count = {r[0]: r[1] for r in run("21_b_venue_count")}
        venue_win = {r[0]: (r[1], r[2]) for r in run("22_b_venue_window")}
        cites = {r[0]: r[1] for r in run("23_b_cites_asof")}
        c1 = {r[0]: r[1] for r in run("30_g_contam1")}
        c2 = {r[0]: r[1] for r in run("31_g_contam2")}
        run("32_mark_retracted_authors")
        a0 = {r[0]: r[1] for r in run("33_b_author_dist0")}
        a1 = {r[0]: r[1] for r in run("34_g_author_dist1")}
        cp = {r[0]: (r[1], r[2]) for r in run("36_g_coupled")}
    finally:
        g.query(q("35_unmark_retracted_authors"), timeout=TIMEOUT)
        g.query(q("3A_cleanup_asof"), timeout=TIMEOUT)

    out = ROOT / "data" / "staging" / f"features_{t0}.jsonl"
    n_pos = 0
    with open(out, "w", encoding="utf-8") as fh:
        for cid, venue, stratum, y, comm in cand:
            size, ret = comm_stats.get(comm, (1, 0)) if comm is not None else (1, 0)
            wn, wr = venue_win.get(venue, (0, 0))
            row = {
                "id": cid, "venue": venue, "stratum": stratum, "y": y,
                "b_venue_count": venue_count.get(venue, 0),
                "b_venue_rate": (wr / wn) if wn else 0.0,
                "b_cites_asof": cites.get(cid, 0),
                "b_author_prior": a0.get(cid, 0),
                "g_contam1": c1.get(cid, 0),
                "g_contam2": c2.get(cid, 0),
                "g_coauth1": a1.get(cid, 0),
                "g_coupled_n": cp.get(cid, (0, 0))[0],
                "g_coupled_w": cp.get(cid, (0, 0))[1],
                "g_comm_rate": (ret / size) if size else 0.0,
                "g_comm_ret": ret,
            }
            n_pos += y
            fh.write(json.dumps(row) + "\n")
    print(f"\nwrote {len(cand):,} candidates ({n_pos} positives) -> {out}")
    # nonzero coverage so an all-zero (broken) signal is obvious
    cols = [k for k in row if k.startswith(("b_", "g_"))]
    rows = [json.loads(l) for l in open(out, encoding="utf-8")]
    print("share of candidates with a nonzero value:")
    for c in cols:
        print(f"  {c:<16}{sum(1 for r in rows if r[c]) / len(rows):8.2%}")
    left = g.ro_query("MATCH (n) WHERE n:RetAuth OR n:AsOf RETURN count(n)", timeout=TIMEOUT).result_set[0][0]
    print("scratch labels left in graph:", left)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
