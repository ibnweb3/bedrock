"""Pull OpenAlex works into data/staging/*.jsonl as slim records (authors already hashed).

    python scripts/pull_openalex.py retracted   --max-calls 1500
    python scripts/pull_openalex.py candidates  --venues-file data/staging/venues.json --from 2017-01-01 --to 2022-12-31
    (only type:article works are pulled)

Both subcommands are resumable and stop at --max-calls (cost is roughly $0.0001 per list call;
the free key budget is about $1/day - run `python scripts/openalex_check.py` to see it).
Raw OpenAlex works are never written to disk: bedrock.openalex.slim_work hashes author IDs and
drops names, ORCIDs and affiliations in memory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bedrock.config import load_settings  # noqa: E402
from bedrock.openalex import (  # noqa: E402
    BudgetExceeded,
    Client,
    OpenAlexError,
    doi_batches,
    norm_doi,
    slim_work,
)

STAGING = ROOT / "data" / "staging"


def _client(max_calls: int) -> tuple[Client, str]:
    s = load_settings()
    if len(s.author_hash_salt) < 32:
        raise SystemExit("AUTHOR_HASH_SALT missing or short; see .env.example")
    return Client(s.openalex_api_key, max_calls=max_calls), s.author_hash_salt


def pull_retracted(args) -> int:
    src = STAGING / "retractions.jsonl"
    if not src.exists():
        print(f"{src} not found; run scripts/pull_retraction_watch.py first")
        return 2
    out_path = STAGING / "retracted_works.jsonl"
    miss_path = STAGING / "retracted_works.missing.txt"

    dois: list[str] = []
    with open(src, encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            if rec["nature"] == "Retraction":
                dois.append(rec["doi"])
    dois = sorted(set(dois))

    done: set[str] = set()
    for p in (out_path, miss_path):
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    done.add(json.loads(line)["doi"] if p == out_path else line)
    todo = [d for d in dois if d not in done]
    if args.limit_dois:
        todo = todo[: args.limit_dois]
    print(f"{len(dois)} retracted DOIs; {len(done)} already resolved; {len(todo)} to do")

    client, salt = _client(args.max_calls)
    found = missing = 0
    try:
        with open(out_path, "a", encoding="utf-8") as out, open(miss_path, "a", encoding="utf-8") as miss:
            for i, batch in enumerate(doi_batches(todo), 1):
                hits: set[str] = set()
                for w in client.works_by_dois(batch):
                    rec = slim_work(w, salt)
                    if rec and rec["doi"] in set(batch):
                        out.write(json.dumps(rec) + "\n")
                        hits.add(rec["doi"])
                for d in batch:
                    if d not in hits:
                        miss.write(d + "\n")
                found += len(hits)
                missing += len(batch) - len(hits)
                out.flush()
                miss.flush()
                if i % 10 == 0:
                    print(f"  batch {i}: found {found}, not found {missing}, calls {client.calls}")
    except BudgetExceeded as exc:
        print("stopped:", exc, "- rerun to continue")
    except OpenAlexError as exc:
        print("OpenAlex error:", exc)
        return 1
    print(f"done this run: found {found}, not found {missing}, API calls {client.calls}")
    return 0


def pull_candidates(args) -> int:
    if args.venues_file:
        v = json.loads(Path(args.venues_file).read_text(encoding="utf-8"))
        ids = sorted({x["id"] for vs in v["strata"].values() for x in vs})
    else:
        ids = [s.strip() for s in (args.source_ids or "").split(",") if s.strip()]
    if not ids:
        print("give --venues-file data/staging/venues.json or --source-ids S1,S2")
        return 2
    # OpenAlex allows <=100 OR-values per filter, so venues go in batches (resumable per batch).
    batches = [ids[i : i + args.venue_batch] for i in range(0, len(ids), args.venue_batch)]
    suffix = f",type:article,from_publication_date:{args.date_from},to_publication_date:{args.date_to}"
    out_path = STAGING / "candidates.jsonl"
    state_path = STAGING / "candidates.state.json"
    STAGING.mkdir(parents=True, exist_ok=True)

    signature = {"venues": ids, "suffix": suffix}
    state = {"signature": signature, "batch": 0, "cursor": "*", "written": 0}
    if state_path.exists() and not args.restart:
        prev = json.loads(state_path.read_text(encoding="utf-8"))
        if prev["signature"] != signature:
            print("state file belongs to a different venue list/filter; use --restart to discard it")
            return 2
        state = prev
    elif args.restart and out_path.exists():
        out_path.unlink()

    client, salt = _client(args.max_calls)
    print(f"{len(ids)} venues in {len(batches)} batches; resuming at batch {state['batch']}, written so far {state['written']}")
    try:
        with open(out_path, "a", encoding="utf-8") as out:
            while state["batch"] < len(batches):
                filt = "primary_location.source.id:" + "|".join(batches[state["batch"]]) + suffix
                for results, nxt in client.iter_pages(filt, cursor=state["cursor"]):
                    for w in results:
                        rec = slim_work(w, salt)
                        if rec:
                            out.write(json.dumps(rec) + "\n")
                            state["written"] += 1
                    out.flush()
                    state["cursor"] = nxt or "*"
                    state_path.write_text(json.dumps(state), encoding="utf-8")
                    if state["written"] % 5000 < 100:
                        print(f"  batch {state['batch'] + 1}/{len(batches)} written {state['written']} calls {client.calls}")
                    if state["written"] >= args.max_works:
                        print("reached --max-works")
                        return 0
                    if not nxt:
                        break
                state["batch"] += 1
                state["cursor"] = "*"
                state_path.write_text(json.dumps(state), encoding="utf-8")
    except BudgetExceeded as exc:
        print("stopped:", exc, "- rerun to continue")
    except OpenAlexError as exc:
        print("OpenAlex error:", exc)
        return 1
    print(f"candidates written in total: {state['written']}, API calls this run: {client.calls}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("retracted", help="resolve retracted DOIs to OpenAlex works")
    r.add_argument("--max-calls", type=int, default=1500)
    r.add_argument("--limit-dois", type=int, default=0, help="test with the first N DOIs")
    r.set_defaults(fn=pull_retracted)

    c = sub.add_parser("candidates", help="pull candidate works from chosen venues")
    c.add_argument("--source-ids", default="", help="comma-separated OpenAlex source IDs")
    c.add_argument("--venues-file", default="", help="data/staging/venues.json from select_venues.py")
    c.add_argument("--venue-batch", type=int, default=50)
    c.add_argument("--from", dest="date_from", required=True)
    c.add_argument("--to", dest="date_to", required=True)
    c.add_argument("--max-works", type=int, default=400000)
    c.add_argument("--max-calls", type=int, default=3500)
    c.add_argument("--restart", action="store_true")
    c.set_defaults(fn=pull_candidates)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
