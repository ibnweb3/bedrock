"""Minimal OpenAlex client plus record slimming.

Privacy (hackathon rule 6): ``slim_work`` is the ONLY place raw OpenAlex works are
interpreted. It keeps ids, dates and references, and replaces every author ID with a keyed
hash. Author names, ORCIDs, institutions and affiliations are never returned or written.

API facts used here were read from OpenAlex's docs on 2026-10-15:
- auth: ``Authorization: Bearer <key>`` (a free key is required for cursor paging past page 1)
- ``select`` accepts top-level fields only, so ``authorships`` arrives whole and is reduced here
- ``per_page`` max is 100; a ``doi:`` filter accepts up to 100 ``|``-separated values
- list calls cost about $0.0001 each; the free key budget is $1/day (check /rate-limit)
The exact field names inside a work are confirmed live by scripts/openalex_check.py.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Iterable, Iterator

import httpx

from .hashing import hash_author_id

BASE_URL = "https://api.openalex.org"
SELECT_FIELDS = "id,doi,publication_date,referenced_works,authorships,primary_location"

_DOI_PREFIX = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)
_BAD_DOI_CHARS = re.compile(r"[\s,|]")  # would break a comma/pipe-delimited filter


class OpenAlexError(RuntimeError):
    pass


class BudgetExceeded(OpenAlexError):
    pass


def short_id(url: str | None) -> str | None:
    """'https://openalex.org/W123' -> 'W123'."""
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1] or None


def norm_doi(doi: str | None) -> str | None:
    """Lower-case bare DOI ('10.x/y'), or None if it does not look like one."""
    if not doi:
        return None
    d = _DOI_PREFIX.sub("", doi.strip()).lower()
    return d if d.startswith("10.") else None


def date_int(value: str | None) -> int | None:
    """'2021-05-03' -> 20210503. Year-only/invalid values give None."""
    if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    return int(value.replace("-", ""))


def slim_work(work: dict, salt: str) -> dict | None:
    """Reduce a raw OpenAlex work to the fields the graph needs. No personal data survives."""
    wid = short_id(work.get("id"))
    if not wid:
        return None
    seen: set[str] = set()
    authors: list[str] = []
    for authorship in work.get("authorships") or []:
        raw = short_id((authorship.get("author") or {}).get("id"))
        if not raw:
            continue
        h = hash_author_id(raw, salt)
        if h not in seen:
            seen.add(h)
            authors.append(h)
    source = (work.get("primary_location") or {}).get("source") or {}
    refs = [r for r in (short_id(x) for x in work.get("referenced_works") or []) if r]
    return {
        "id": wid,
        "doi": norm_doi(work.get("doi")),
        "pub_date": date_int(work.get("publication_date")),
        "venue_id": short_id(source.get("id")),
        "refs": refs,
        "authors": authors,
    }


def doi_batches(dois: Iterable[str], size: int = 100) -> Iterator[list[str]]:
    """Yield batches of valid DOIs; DOIs containing whitespace, ',' or '|' are skipped."""
    batch: list[str] = []
    for d in dois:
        if not d or _BAD_DOI_CHARS.search(d):
            continue
        batch.append(d)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def doi_filter(dois: list[str]) -> str:
    return "doi:" + "|".join(f"https://doi.org/{d}" for d in dois)


class Client:
    def __init__(
        self,
        api_key: str,
        *,
        max_calls: int | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key or any(c.isspace() for c in api_key):
            raise OpenAlexError(
                "OPENALEX_API_KEY is empty or malformed; put the key in bedrock/.env "
                "(create one at https://openalex.org/settings/api)"
            )
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "bedrock-graphhacks/0.1"},
            timeout=timeout,
            transport=transport,
        )
        self.calls = 0
        self.max_calls = max_calls
        self._sleep = sleep

    def get(self, path: str, params: dict | None = None) -> dict:
        delay = 2.0
        for _ in range(6):
            if self.max_calls is not None and self.calls >= self.max_calls:
                raise BudgetExceeded(f"stopped at --max-calls={self.max_calls}")
            self.calls += 1
            try:
                r = self._http.get(path, params=params)
            except httpx.TransportError:
                self._sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if r.status_code == 401:
                raise OpenAlexError(f"401 from OpenAlex: {r.text[:200]}")
            if r.status_code in (429, 500, 502, 503, 504):
                try:
                    wait = float(r.headers.get("Retry-After", delay))
                except ValueError:
                    wait = delay
                self._sleep(min(wait, 120))
                delay = min(delay * 2, 60)
                continue
            r.raise_for_status()
            return r.json()
        raise OpenAlexError(f"gave up after repeated failures on {path}")

    def rate_limit(self) -> dict:
        return self.get("/rate-limit")

    def iter_pages(
        self,
        filter_str: str,
        *,
        select: str = SELECT_FIELDS,
        per_page: int = 100,
        cursor: str | None = "*",
    ) -> Iterator[tuple[list[dict], str | None]]:
        """Cursor-page /works. Yields (results, next_cursor); stops on an empty page."""
        while cursor:
            data = self.get(
                "/works",
                {"filter": filter_str, "select": select, "per_page": per_page, "cursor": cursor},
            )
            results = data.get("results") or []
            nxt = (data.get("meta") or {}).get("next_cursor")
            yield results, nxt
            if not results:
                return
            cursor = nxt

    def works_by_dois(self, dois: list[str]) -> list[dict]:
        """One list call for up to 100 DOIs (raw works; slim them with slim_work)."""
        data = self.get(
            "/works",
            {"filter": doi_filter(dois), "select": SELECT_FIELDS, "per_page": 100},
        )
        return data.get("results") or []
