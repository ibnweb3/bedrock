# Bedrock

> What is this research standing on, and what is likely to fall next?

Bedrock is an agent for the **Graph Hacks: Context for AI Agents** hackathon
(WeMakeDevs × FalkorDB), entered in **Track 01 — Agents That Act on Connected Data**.

Given a paper or a bibliography, it traces the multi-hop foundation of the work using a
citation / co-authorship graph in FalkorDB, scores retraction risk from graph signals, and
proposes (never auto-applies) an audit with the exact graph path behind every flag.

**Status: scaffold only.** Nothing below marked *planned* is built yet, and there are **no
results yet**. Every number that ends up in this README will come from a script in this
repo that you can re-run.

## Why a graph

Reference managers flag a paper that directly cites a retracted one. The questions that
matter are multi-hop: does this paper stand on work that stands on retracted work? Is it in
a citation cluster where retractions keep happening? Those are traversals, shortest paths and
community structure — FalkorDB queries, not table lookups.

## Graph data model (planned)

Nodes
- `Paper {id, doi, pub_date, venue_id, retracted_at?, retraction_reasons?}`
- `Author {id}` — **salted hash only**, never a name, email or ORCID
- `Venue {id}`

Edges
- `(:Author)-[:WROTE]->(:Paper)`
- `(:Paper)-[:CITES]->(:Paper)`
- `(:Paper)-[:PUBLISHED_IN]->(:Venue)`
- derived, built inside FalkorDB: `(:Author)-[:COAUTHOR]->(:Author)`, `(:Paper)-[:BIB_COUPLED {shared}]->(:Paper)`

Dates are stored as integers `YYYYMMDD`; the backtest's "as of T0" view is a filter such as
`WHERE p.retracted_at <= $t0`. Retraction is a node property rather than a separate node to
keep the graph small (the free FalkorDB Cloud tier is 100 MB).

## Where the graph logic runs

All graph reasoning — reference traversals, shortest paths to retracted seeds, community
detection, PageRank, the as-of-T0 filter, and every agent tool — is executed as Cypher /
FalkorDB algorithms **inside FalkorDB**. The Cypher lives in [`queries/`](queries/) and the
application imports those exact files, so the README, the repo and the running product
cannot drift apart. Staging files used during ingest are not a graph database and are not
read at query time. A non-graph baseline exists **only** to score the evaluation.

## Quickstart (works today)

```bash
cp .env.example .env              # then fill in values; .env is git-ignored
docker compose up -d              # FalkorDB on 127.0.0.1:6379, Browser on :3000
pip install -r requirements.txt
python scripts/smoke_test.py      # applies schema, runs a 2-hop traversal
python -m unittest discover -s tests
```

## Data pipeline (built, partly run)

```bash
python scripts/openalex_check.py                      # key + field-name check (free)
python scripts/pull_retraction_watch.py --download    # ~67.5 MB CSV -> data/staging/retractions.jsonl
python scripts/pull_openalex.py retracted             # retracted DOIs -> OpenAlex works
python scripts/pull_openalex.py candidates --source-ids S... --from 2019-01-01 --to 2021-12-31
```

Both OpenAlex pulls are resumable and stop at `--max-calls`. Output is JSON Lines in
`data/staging/` (git-ignored). Authors are hashed in memory before anything is written; raw
OpenAlex works are never stored. Staging files are ETL input only — nothing reads them at
query time.

## Evaluation (planned)

Leakage-safe temporal backtest: build the graph from what was known at a cutoff T0, label
papers by whether they were retracted in the following 24 months, rank candidates by graph
signals, and compare against non-graph baselines (venue retraction rate, citation count,
prior-retraction author). Metrics: AUPRC, precision@k, lift over base rate, bootstrap
confidence intervals; plus an ablation of multi-hop signals vs. one-hop joins.

| Method | AUPRC | Precision@1% | Lift |
|---|---|---|---|
| Venue-rate baseline | — | — | — |
| Citation-count baseline | — | — | — |
| Prior-retraction-author baseline | — | — | — |
| Graph signals (1-hop only) | — | — | — |
| Graph signals (multi-hop) | — | — | — |

*Empty on purpose: no run has happened.*

Caveats stated up front: retraction is a lagging, detection-driven label; mass retractions by a
single publisher can dominate it; OpenAlex author-ID disambiguation uses later information
(mild temporal leakage). Output is a statistical risk signal, **not an accusation**.

## Data & attribution

- [Retraction Watch database](https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/),
  distributed by Crossref (public; no license is stated in its repository).
- [OpenAlex](https://openalex.org/) metadata (CC0).

Details and handling in [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).

## Privacy

Author identities are never loaded or displayed: author IDs are replaced by a keyed hash
before ingest; names, emails and ORCIDs are dropped. The demo does not publish a list of
"suspicious papers".

## AI assistance disclosure (hackathon rule 11)

This project is built with **Claude Code** (Anthropic) as a coding assistant. *To be completed
before submission with specifics on which components Claude wrote and which parts the
participant designed, ran and verified.* The participant's design decisions are logged in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Rules compliance

Tracked in [`docs/RULES_CHECKLIST.md`](docs/RULES_CHECKLIST.md).
