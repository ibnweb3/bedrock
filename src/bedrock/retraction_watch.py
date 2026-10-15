"""Retraction Watch CSV (distributed by Crossref): download, parse, minimise.

Source: https://gitlab.com/crossref/retraction-watch-data (file retraction_watch.csv).
Privacy (hackathon rule 6): only the columns in USED_COLUMNS are read into records. The
Author, Institution, Title, URLS and Notes columns are never copied anywhere.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import httpx

from .openalex import norm_doi

CSV_URL = "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"

USED_COLUMNS = (
    "Record ID",
    "Journal",
    "Publisher",
    "RetractionDate",
    "OriginalPaperDate",
    "OriginalPaperDOI",
    "RetractionNature",
    "Reason",
)

# Formats are tried in order. The README documents "the date of the published retraction"
# but not its format, so the pull script reports how many values parse and lists the unparsed
# ones; confirm against real data before trusting the day/month order.
_DATE_FORMATS = ("%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def parse_date(value: str | None) -> int | None:
    """Return YYYYMMDD as int, or None if blank/unparseable."""
    v = (value or "").strip()
    if not v:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return int(datetime.strptime(v, fmt).strftime("%Y%m%d"))
        except ValueError:
            continue
    return None


def clean_reasons(value: str | None) -> list[str]:
    return [p.strip() for p in (value or "").split(";") if p.strip()]


def iter_records(path: Path, stats: Counter | None = None) -> Iterator[dict]:
    """Yield minimised records. Rows without a usable original-paper DOI are counted and skipped."""
    stats = stats if stats is not None else Counter()
    csv.field_size_limit(10_000_000)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in USED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV is missing expected columns: {missing}")
        for row in reader:
            stats["rows"] += 1
            nature = (row["RetractionNature"] or "").strip()
            stats[f"nature:{nature or '<blank>'}"] += 1
            doi = norm_doi(row["OriginalPaperDOI"])
            if not doi:
                stats["skipped:no_original_doi"] += 1
                continue
            r_date = parse_date(row["RetractionDate"])
            if r_date is None:
                stats["unparsed_retraction_date"] += 1
                if row["RetractionDate"].strip():
                    stats[f"unparsed_sample:{row['RetractionDate'].strip()[:25]}"] += 1
            yield {
                "record_id": (row["Record ID"] or "").strip(),
                "doi": doi,
                "nature": nature,
                "retraction_date": r_date,
                "original_date": parse_date(row["OriginalPaperDate"]),
                "journal": (row["Journal"] or "").strip(),
                "publisher": (row["Publisher"] or "").strip(),
                "reasons": clean_reasons(row["Reason"]),
            }


def download(dest: Path, url: str = CSV_URL, *, timeout: float = 60.0) -> dict:
    """Download with resume support (flaky connections). Returns provenance metadata."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    with httpx.Client(timeout=timeout, follow_redirects=True) as http:
        total = int(http.head(url).headers.get("content-length", "0"))
        for _ in range(20):  # resume loop
            have = part.stat().st_size if part.exists() else 0
            if total and have >= total:
                break
            headers = {"Range": f"bytes={have}-"} if have else {}
            try:
                with http.stream("GET", url, headers=headers) as r:
                    if r.status_code == 416:
                        break
                    r.raise_for_status()
                    mode = "ab" if (have and r.status_code == 206) else "wb"
                    with open(part, mode) as out:
                        for chunk in r.iter_bytes(1 << 16):
                            out.write(chunk)
            except httpx.TransportError:
                continue
        size = part.stat().st_size if part.exists() else 0
        if total and size != total:
            raise RuntimeError(f"incomplete download: {size} of {total} bytes; rerun to resume")
    part.replace(dest)
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    meta = {
        "url": url,
        "bytes": dest.stat().st_size,
        "sha256": sha,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
