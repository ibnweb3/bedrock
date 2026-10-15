"""Validate the OpenAlex key and confirm the field names the pull scripts rely on.

Uses one free singleton lookup. Prints only structure and counts - never author identities.

    python scripts/openalex_check.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bedrock.config import load_settings  # noqa: E402
from bedrock.openalex import SELECT_FIELDS, Client, OpenAlexError, slim_work  # noqa: E402

# A well-known work id used in OpenAlex's own documentation examples.
SAMPLE_WORK = "W2741809807"


def main() -> int:
    s = load_settings()
    if len(s.author_hash_salt) < 32:
        print("AUTHOR_HASH_SALT missing or short; see .env.example")
        return 1
    try:
        client = Client(s.openalex_api_key)
        limits = client.rate_limit()
    except OpenAlexError as exc:
        print("KEY CHECK FAILED:", exc)
        return 1
    print("key accepted. rate-limit response (numbers/keys only):")
    print(json.dumps(_redact(limits), indent=1)[:900])

    raw = client.get(f"/works/{SAMPLE_WORK}", {"select": SELECT_FIELDS})
    print("\nraw work top-level fields:", sorted(raw.keys()))
    expected = SELECT_FIELDS.split(",")
    absent = [f for f in expected if f not in raw]
    print("missing expected fields:", absent or "none")
    slim = slim_work(raw, s.author_hash_salt)
    print(
        "slim record:",
        {
            "id": slim["id"],
            "doi": slim["doi"],
            "pub_date": slim["pub_date"],
            "venue_id": slim["venue_id"],
            "n_refs": len(slim["refs"]),
            "n_authors(hashed)": len(slim["authors"]),
        },
    )
    return 0 if not absent and slim else 1


def _redact(o):
    if isinstance(o, dict):
        return {k: _redact(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_redact(v) for v in o]
    return o if isinstance(o, (int, float, bool)) or o is None else "<str>"


if __name__ == "__main__":
    raise SystemExit(main())
