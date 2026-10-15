# Data sources and handling (hackathon rule 6)

## Retraction Watch database (via Crossref)

- Where: https://gitlab.com/crossref/retraction-watch-data (CSV; Crossref docs:
  https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/)
- Status checked 2026-10-15: public, no login. The repository README states **no license**
  ("have made it publicly available"); a `LICENSE` file was not found at the raw path.
  Credit Retraction Watch and Crossref.
- Columns used: retraction date, original paper DOI, reason list (semicolon-separated).
- **Dropped at ingest:** author names and any other personal fields.

## OpenAlex

- Where: https://openalex.org/ API (a free key is required; create it at
  https://openalex.org/settings/api; free key = 10× the keyless daily budget, 30 req/s).
- Status checked 2026-10-15: metadata is CC0 per OpenAlex's help centre. The key only
  meters usage; the data itself is open.
- Fields used, **confirmed against the live API on 2026-10-15** (`scripts/openalex_check.py`):
  `id`, `doi`, `publication_date`, `referenced_works`, `authorships[].author.id`,
  `primary_location.source.id`. `select` only accepts top-level fields, so `authorships`
  arrives whole and is reduced in memory (names, ORCIDs, affiliations discarded).
- Budget (from `/rate-limit`): $1/day = 10,000 credits; a list call = 1 credit, a singleton
  lookup = 0. Cursor paging past page 1 requires the key. `per_page` max 100; a `doi:` filter
  takes up to 100 `|`-separated values.
- **Author handling:** only the author ID is read, then replaced by a salted hash
  (`src/bedrock/hashing.py`). No names, emails or ORCIDs are stored or shown.

## Not used

Anything private, login-gated, paywalled or restricted. If a source's terms are unclear, it
is left out rather than assumed.
