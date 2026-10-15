"""Download (optional) and minimise the Retraction Watch CSV into data/staging/retractions.jsonl.

    python scripts/pull_retraction_watch.py --download   # fetches ~67 MB, resumable
    python scripts/pull_retraction_watch.py              # parse an existing download

Only the columns listed in bedrock.retraction_watch.USED_COLUMNS are kept; author names and
institutions are never copied.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bedrock.retraction_watch import download, iter_records  # noqa: E402

RAW = ROOT / "data" / "raw" / "retraction_watch.csv"
OUT = ROOT / "data" / "staging" / "retractions.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="fetch the CSV (resumable)")
    args = ap.parse_args()

    if args.download:
        print("downloading ... (resumes if interrupted; rerun the same command)")
        meta = download(RAW)
        print("downloaded", meta["bytes"], "bytes, sha256", meta["sha256"][:16], "...")
    if not RAW.exists():
        print(f"{RAW} not found; rerun with --download")
        return 2

    stats: Counter = Counter()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    per_year: Counter = Counter()
    kept = 0
    with open(OUT, "w", encoding="utf-8") as out:
        for rec in iter_records(RAW, stats):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            kept += 1
            if rec["nature"] == "Retraction" and rec["retraction_date"]:
                per_year[str(rec["retraction_date"])[:4]] += 1

    print(f"\nrows read: {stats['rows']}  records written (have original DOI): {kept}")
    print("by RetractionNature:")
    for k, v in sorted(stats.items()):
        if k.startswith("nature:"):
            print(f"  {k[7:]:<24}{v}")
    print("skipped, no usable original DOI:", stats["skipped:no_original_doi"])
    print("unparsed RetractionDate:", stats["unparsed_retraction_date"])
    for k, v in stats.most_common():
        if k.startswith("unparsed_sample:"):
            print("   sample:", k[16:], v)
    print("retractions (with DOI) per retraction year:")
    for y in sorted(per_year):
        print(f"  {y}  {per_year[y]}")
    print("\nwrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
