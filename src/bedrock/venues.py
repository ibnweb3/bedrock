"""Venue-pool selection helpers for the temporal backtest.

Leakage rule: venues are SELECTED using only information available at the selection cutoff
(``retraction_date <= t_sel``). Counts after the cutoff (``post_counts``) are computed for
diagnostics/reporting only and must never feed selection.
"""
from __future__ import annotations

import random
from collections import Counter
from datetime import date
from typing import Iterable, Mapping, Sequence


def add_months(yyyymmdd: int, months: int) -> int:
    d = date(yyyymmdd // 10000, yyyymmdd // 100 % 100, yyyymmdd % 100)
    m0 = d.month - 1 + months
    y, m = d.year + m0 // 12, m0 % 12 + 1
    # clamp day to month length (e.g. Aug 31 + 6 months -> Feb 28/29)
    for day in (d.day, 30, 29, 28):
        try:
            return int(date(y, m, day).strftime("%Y%m%d"))
        except ValueError:
            continue
    raise ValueError("unreachable")


def _retraction_venues(
    retractions: Iterable[Mapping], doi_to_venue: Mapping[str, str]
) -> Iterable[tuple[str, int]]:
    """(venue_id, retraction_date) for 'Retraction' records whose DOI resolved to a venue."""
    seen: set[str] = set()
    for r in retractions:
        if r.get("nature") != "Retraction" or not r.get("retraction_date"):
            continue
        doi = r["doi"]
        if doi in seen:  # a DOI can appear in several RW rows; count it once
            continue
        venue = doi_to_venue.get(doi)
        if venue:
            seen.add(doi)
            yield venue, r["retraction_date"]


def pre_counts(retractions, doi_to_venue, t0: int) -> Counter:
    """Retractions per venue with retraction_date <= t0 (safe for selection)."""
    return Counter(v for v, d in _retraction_venues(retractions, doi_to_venue) if d <= t0)


def post_counts(retractions, doi_to_venue, t0: int, months: int = 24) -> Counter:
    """Retractions per venue in (t0, t0+months]. DIAGNOSTIC ONLY - never use for selection."""
    end = add_months(t0, months)
    return Counter(v for v, d in _retraction_venues(retractions, doi_to_venue) if t0 < d <= end)


def seeded_pick(ids: Iterable[str], k: int, seed: int) -> list[str]:
    """Deterministic random pick: sort first so input order cannot change the result."""
    pool = sorted(set(ids))
    return sorted(random.Random(seed).sample(pool, min(k, len(pool))))


def window_works(counts_by_year: Sequence[Mapping], year_from: int, year_to: int) -> int:
    """Works published in [year_from, year_to] from an OpenAlex source's counts_by_year."""
    return sum(c.get("works_count", 0) for c in counts_by_year or [] if year_from <= c.get("year", 0) <= year_to)
