"""Pull OpenAlex works into data/staging/*.jsonl as slim records (authors already hashed).

    python scripts/pull_openalex.py retracted   --max-calls 1500
    python scripts/pull_openalex.py candidates  --source-ids S1,S2 --from 2019-01-01 --to 2021-12-31

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
    ids = [s.strip() for s in args.source_ids.split(",") if s.strip()]
    if not ids or len(ids) > 100:
        print("--source-ids needs 1-100 OpenAlex source IDs (e.g. S137773608)")
        return 2
    filt = (
        "primary_location.source.id:" + "|".join(ids)
        + f",from_publication_date:{args.date_from},to_publication_date:{args.date_to}"
    )
    out_path = STAGING / "candidates.jsonl"
    state_path = STAGING / "candidates.state.json"
    STAGING.mkdir(parents=True, exist_ok=True)

    state = {"filter": filt, "cursor": "*", "written": 0}
    if state_path.exists() and not args.restart:
        prev = json.loads(state_path.read_text(encoding="utf-8"))
        if prev["filter"] != filt:
            print("state file belongs to a different filter; use --restart to discard it")
            return 2
        state = prev
    elif args.restart and out_path.exists():
        out_path.unlink()

    client, salt = _client(args.max_calls)
    try:
        with open(out_path, "a", encoding="utf-8") as out:
            for results, nxt in client.iter_pages(filt, cursor=state["cursor"]):
                for w in results:
                    rec = slim_work(w, salt)
                    if rec:
                        out.write(json.dumps(rec) + "\n")
                        state["written"] += 1
                out.flush()
                state["cursor"] = nxt
                state_path.write_text(json.dumps(state), encoding="utf-8")
                if state["written"] % 1000 < 100:
                    print(f"  written {state['written']}, calls {client.calls}")
                if state["written"] >= args.max_works or not nxt:
                    break
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
    c.add_argument("--source-ids", required=True)
    c.add_argument("--from", dest="date_from", required=True)
    c.add_argument("--to", dest="date_to", required=True)
    c.add_argument("--max-works", type=int, default=20000)
    c.add_argument("--max-calls", type=int, default=1000)
    c.add_argument("--restart", action="store_true")
    c.set_defaults(fn=pull_candidates)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
