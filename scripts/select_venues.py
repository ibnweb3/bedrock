"""Choose the candidate venue pool for the backtest (writes data/staging/venues.json).

Design (documented in docs/BACKTEST_DESIGN.md):
- Venues are stratified by retraction history known at the selection cutoff --t-sel:
    H  >=3 retractions before the cutoff,  L  1-2,  Z  none (random journals via a seeded sample).
- Selection uses ONLY pre-cutoff counts. Post-cutoff counts are printed as diagnostics and
  written under "diagnostics"; they never influence which venues are picked.
- All randomness is seeded and the seeds are recorded in the output.

    python scripts/select_venues.py            # needs the full `pull_openalex.py retracted` run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bedrock.config import load_settings  # noqa: E402
from bedrock.openalex import Client, short_id  # noqa: E402
from bedrock.venues import post_counts, pre_counts, seeded_pick, window_works  # noqa: E402

STAGING = ROOT / "data" / "staging"
SRC_SELECT = "id,display_name,works_count,counts_by_year,type"


def load_jsonl(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def fetch_sources(client: Client, ids: list[str], cache: Path) -> dict[str, dict]:
    meta: dict[str, dict] = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    todo = [i for i in ids if i not in meta]
    for k in range(0, len(todo), 100):
        batch = todo[k : k + 100]
        data = client.get(
            "/sources",
            {"filter": "openalex:" + "|".join(batch), "select": SRC_SELECT, "per_page": 100},
        )
        for s in data.get("results") or []:
            meta[short_id(s["id"])] = {
                "name": s.get("display_name"),
                "type": s.get("type"),
                "works_count": s.get("works_count", 0),
                "counts_by_year": s.get("counts_by_year") or [],
            }
        for i in batch:  # remember misses so reruns do not refetch them
            meta.setdefault(i, {"name": None, "type": None, "works_count": 0, "counts_by_year": []})
        cache.write_text(json.dumps(meta), encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t-sel", type=int, default=20201231, help="selection cutoff (YYYYMMDD)")
    ap.add_argument("--t0", type=int, nargs="+", default=[20201231, 20221231], help="backtest cutoffs")
    ap.add_argument("--years", type=int, nargs=2, default=[2017, 2022], help="candidate publication years")
    ap.add_argument("--min-works", type=int, default=300)
    ap.add_argument("--max-works", type=int, default=3000)
    ap.add_argument("--k-h", type=int, default=40)
    ap.add_argument("--k-l", type=int, default=30)
    ap.add_argument("--k-z", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args()

    retractions = list(load_jsonl(STAGING / "retractions.jsonl"))
    resolved = {r["doi"]: r["venue_id"] for r in load_jsonl(STAGING / "retracted_works.jsonl") if r.get("venue_id")}
    miss_path = STAGING / "retracted_works.missing.txt"
    missing = set(miss_path.read_text(encoding="utf-8").split()) if miss_path.exists() else set()
    all_dois = {r["doi"] for r in retractions if r["nature"] == "Retraction"}
    done = {r["doi"] for r in load_jsonl(STAGING / "retracted_works.jsonl")} | missing
    if len(all_dois - done) > 0 and not args.allow_partial:
        print(f"retracted pull incomplete: {len(all_dois - done)} DOIs unresolved; finish it or pass --allow-partial")
        return 2
    print(f"retraction DOIs: {len(all_dois)}  resolved to a venue: {len(resolved)}  not in OpenAlex: {len(missing)}")

    s = load_settings()
    client = Client(s.openalex_api_key, max_calls=args.max_calls)
    y0, y1 = args.years

    pre = pre_counts(retractions, resolved, args.t_sel)
    meta = fetch_sources(client, sorted(v for v, n in pre.items() if n >= 1), STAGING / "sources_meta.json")

    def eligible(vid: str) -> bool:
        m = meta.get(vid)
        if not m or m["type"] != "journal":
            return False
        return args.min_works <= window_works(m["counts_by_year"], y0, y1) <= args.max_works

    h_pool = [v for v, n in pre.items() if n >= 3 and eligible(v)]
    l_pool = [v for v, n in pre.items() if 1 <= n <= 2 and eligible(v)]
    strata = {
        "H": seeded_pick(h_pool, args.k_h, args.seed),
        "L": seeded_pick(l_pool, args.k_l, args.seed + 1),
    }
    print(f"eligible H pool {len(h_pool)} -> picked {len(strata['H'])};  L pool {len(l_pool)} -> picked {len(strata['L'])}")

    # Z stratum: random journals (seeded OpenAlex sample) with no retraction before the cutoff.
    z_meta: dict[str, dict] = {}
    for draw in range(12):
        if len(z_meta) >= args.k_z * 3:
            break
        data = client.get(
            "/sources",
            {"filter": f"type:journal,works_count:>{args.min_works}", "sample": 100,
             "seed": args.seed + 100 + draw, "select": SRC_SELECT, "per_page": 100},
        )
        for src in data.get("results") or []:
            vid = short_id(src["id"])
            if pre.get(vid, 0) == 0 and vid not in z_meta:
                z_meta[vid] = {"name": src.get("display_name"), "type": src.get("type"),
                               "works_count": src.get("works_count", 0),
                               "counts_by_year": src.get("counts_by_year") or []}
    z_ok = [v for v, m in z_meta.items()
            if args.min_works <= window_works(m["counts_by_year"], y0, y1) <= args.max_works]
    strata["Z"] = seeded_pick(z_ok, args.k_z, args.seed + 2)
    meta.update({v: z_meta[v] for v in strata["Z"]})
    print(f"Z draws kept {len(z_meta)} zero-history journals; size-eligible {len(z_ok)} -> picked {len(strata['Z'])}")

    chosen = {v for vs in strata.values() for v in vs}
    diagnostics = {}
    for t0 in args.t0:
        post = post_counts(retractions, resolved, t0, 24)
        pre_t0 = pre_counts(retractions, resolved, t0)
        diagnostics[str(t0)] = {
            name: {
                "venues": len(vs),
                "pre_retractions": sum(pre_t0.get(v, 0) for v in vs),
                "post_24m_retractions_DIAGNOSTIC_ONLY": sum(post.get(v, 0) for v in vs),
            }
            for name, vs in strata.items()
        }

    out = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {k: getattr(args, k) for k in vars(args)},
        "selection_rule": "venues picked using retractions dated <= t_sel only; post counts are diagnostics",
        "strata": {
            name: [{"id": v, "name": meta[v]["name"],
                    "works_in_years": window_works(meta[v]["counts_by_year"], y0, y1),
                    "pre_retractions_t_sel": pre.get(v, 0)} for v in vs]
            for name, vs in strata.items()
        },
        "diagnostics": diagnostics,
        "caveats": [
            "Pool is a stratified convenience sample, not representative of all literature.",
            "Retractions whose original DOI is missing or not in OpenAlex are invisible, so some "
            "'zero-history' venues may have had retractions.",
            "works_in_years counts all work types; the candidate pull filters to type:article.",
        ],
    }
    (STAGING / "venues.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

    print("\nstratum | venues | est. works (all types) | " + " | ".join(f"T0={t}: pre / post24m" for t in args.t0))
    for name, vs in strata.items():
        est = sum(window_works(meta[v]["counts_by_year"], y0, y1) for v in vs)
        cells = [f"{diagnostics[str(t)][name]['pre_retractions']} / {diagnostics[str(t)][name]['post_24m_retractions_DIAGNOSTIC_ONLY']}"
                 for t in args.t0]
        print(f"{name:>7} | {len(vs):>6} | {est:>22} | " + " | ".join(f"{c:>26}" for c in cells))
    print(f"\nchosen venues: {len(chosen)}  API calls: {client.calls}  -> data/staging/venues.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
