# Bedrock

> What is this research standing on, and what is likely to fall next?

Bedrock is an agent for the **Graph Hacks: Context for AI Agents** hackathon
(WeMakeDevs × FalkorDB), entered in **Track 01 — Agents That Act on Connected Data**.

Given a bibliography (a list of DOIs), it traces which **retracted** works the cited papers stand on,
directly or through one intermediate paper, using a citation graph in FalkorDB. Every finding comes with
the exact citation path, and the agent proposes (never auto-applies) edits that a person approves.
It makes **exact statements about an indexed corpus, not predictions**: a backtest of whether graph
signals predict future retractions found no reliable improvement over journal history
([`docs/RESULTS.md`](docs/RESULTS.md)), so Bedrock does not claim to forecast anything.

**Try it in one command** (needs Docker; details in [`docs/DEPLOY.md`](docs/DEPLOY.md)):

```bash
docker compose --profile demo up --build app      # then open http://127.0.0.1:8765
```

**Status.** Built and working: the data pipeline, the FalkorDB graph, the audit queries, the web app with an
approval step, the tool-calling agent, and a leave-venue-out / venue-clustered temporal backtest. **The backtest
result was negative: graph signals did not reliably beat venue-history baselines at predicting retractions**
(see Evaluation and [`docs/RESULTS.md`](docs/RESULTS.md)), which is why the product is an exact provenance audit and
not a forecaster. The research graph has 2.5M nodes (312k papers held in the corpus plus 2.0M cited-only stubs, 1.7M
co-author and 2.7M coupling edges); the audit only needs the 312k papers and the citations between them, and the
published 17 MB snapshot (`deploy/`) is that slim graph, verified to give identical audit output on 2,501 DOIs.
Every number in this README comes from a script in this repo that you can re-run.

## Why a graph

Reference managers flag a paper that directly cites a retracted one. The question that matters is
multi-hop: does this paper stand on work that itself stands on retracted work, and through which path?
Finding that, and suggesting replacements that the community co-cites with a retracted work, are graph
traversals — FalkorDB queries (`queries/audit/`), not table lookups. Honest scope note: the backtest showed
that one-hop contamination is the strongest signal and multi-hop signals did not beat it for *prediction*;
the value of the graph here is exact, explainable provenance, not forecasting.

## Graph data model

Nodes
- `Paper {id, doi, pub_date, venue_id, retracted_at?, retraction_reasons?}`
- `Author {id}` — **salted hash only**, never a name, email or ORCID
- `Venue {id}`

Edges
- `(:Author)-[:WROTE]->(:Paper)`
- `(:Paper)-[:CITES]->(:Paper)`
- `(:Paper)-[:PUBLISHED_IN]->(:Venue)`
- derived, built inside FalkorDB by `queries/10_*.cypher` and `queries/11_*.cypher`:
  `(:Author)-[:COAUTHOR {n, first}]->(:Author)` (n = joint papers, first = earliest joint date) and
  `(:Paper)-[:BIB_COUPLED {shared}]->(:Paper)` (>= 2 shared references, ignoring references cited by more than 50
  held papers). Both are queried undirected; as-of-T0 views filter on dates, not on the edge.
  Paper nodes also carry `cited_n` (in-degree, `queries/05_cited_n.cypher`).

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

## Run the audit app

```bash
python scripts/serve.py            # http://127.0.0.1:8765  (localhost only; needs the loaded graph)
```

Paste DOIs or a reference list, press *Audit bibliography*, read the findings and citation paths, tick the
proposed actions you accept, and apply them. Nothing is changed without that approval; the server re-runs the
audit and applies only proposal ids it generated itself. Statuses: `RETRACTED`, `CITES_RETRACTED`, `TWO_HOP`,
`NO_EXPOSURE_FOUND` (not a certification), `NOT_IN_CORPUS`.

### The agent (optional, needs a free Groq key)

`python scripts/serve.py` also enables an **Audit with agent** button when `GROQ_API_KEY` is set in `.env`
([free key](https://console.groq.com/keys)). A tool-calling model (default `openai/gpt-oss-120b`) chooses between
three **read-only** tools (`audit_bibliography`, `explain_finding`, `find_dois`), each a thin wrapper over the Cypher in
`queries/audit/`, and writes a short summary. Guard rails: the agent has no tool that changes anything (edits are applied
only after you approve them); every DOI in its answer is checked against what the tools returned and a mismatch is shown
as a warning; the findings cards are computed from the graph independently of the model; and without a key or when the
model is rate-limited you still get the full audit and a plain summary.

## Quickstart for development (full pipeline)

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
python scripts/select_venues.py --k-h 150             # stratified venue pool -> data/staging/venues.json
python scripts/pull_openalex.py candidates --venues-file data/staging/venues.json --from 2017-01-01 --to 2022-12-31
python scripts/load_graph.py --reset                  # staged data -> FalkorDB (~7 min, ~1.2 GiB RAM)
python scripts/derive_edges.py                        # COAUTHOR + BIB_COUPLED in FalkorDB (~4 min) + sample checks
```

Both OpenAlex pulls are resumable and stop at `--max-calls`. Output is JSON Lines in
`data/staging/` (git-ignored). Authors are hashed in memory before anything is written; raw
OpenAlex works are never stored. Staging files are ETL input only — nothing reads them at
query time.

## Evaluation (pre-registered backtest)

Leakage-safe temporal backtest: build the graph from what was known at a cutoff T0, label
papers by whether they were retracted in the following 24 months, rank candidates by graph
signals, and compare against non-graph baselines (venue retraction rate, citation count,
prior-retraction author). Metrics: AUPRC, precision@k, lift over base rate, bootstrap
confidence intervals; plus an ablation of multi-hop signals vs. one-hop joins.

First run (stratum H, T0 = 2020-12-31; 134,798 candidates, 140 positives; full tables in [`docs/RESULTS.md`](docs/RESULTS.md)):

| Method | AP | Recall@1% (lift) | Recall@5% |
|---|---|---|---|
| random control | 0.0012 | 0.016 (1.6x) | 0.054 |
| best baseline (venue retraction rate) | 0.0066 | 0.000 (0x) | 0.550 |
| author prior retraction (one-hop) | 0.0032 | 0.077 (7.7x) | 0.194 |
| cites a retracted paper (one-hop) | 0.0066 | 0.100 (10.0x) | 0.143 |
| 2 citation hops (multi-hop) | 0.0021 | 0.073 (7.3x) | 0.117 |
| graph composite | 0.0041 | 0.071 (7.1x) | 0.286 |
| venue count + graph composite | 0.0074 | 0.157 (15.7x) | 0.379 |

**Result: no reliable improvement.** The pre-registered criterion (paired 95% interval excluding 0, surviving the
removal of the largest venue) was not met at any cutoff, and the multi-hop signals did not beat their one-hop
counterparts. Positives are concentrated in 20-27 venues, so the study has low power.

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

**Coding assistant.** Most of the code in this repository (the pull and load scripts, the Cypher in `queries/`,
the audit module, the agent, the web app, the tests and the docs) was written by **Claude Code** (Anthropic) working
from the participant's instructions in a single long session.

**What the participant did.** Chose the track and the product idea after comparing several candidates; set the
rules to follow (FalkorDB as the central database, hashed authors, no invented numbers, a fresh public repo);
obtained and supplied the API keys; approved the backtest design and its size (150 high-history venues);
reviewed the first backtest result, which failed the pre-registered criterion, and **decided to change the product
from retraction prediction to an exact citation-provenance audit**; decided to use Groq's free tier for the agent;
and approves each commit, push and deployment. The decisions are logged in [`docs/DECISIONS.md`](docs/DECISIONS.md).

**AI inside the product.** At run time the optional agent calls **Groq-hosted `openai/gpt-oss-120b`** (tool
calling). It has three read-only tools, cannot change anything, and its answer is checked against the tool results;
the findings themselves are computed by Cypher queries in FalkorDB, not by the model. Without a Groq key the
product works as a plain graph audit.

## Rules compliance

Tracked in [`docs/RULES_CHECKLIST.md`](docs/RULES_CHECKLIST.md).
