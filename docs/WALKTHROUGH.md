# Walkthrough: how Bedrock works (read this before submitting)

Rules 12 and 13 say you must be able to explain the graph model, the queries, the architecture and the decisions. This page is written so you can
do that in your own words. Every claim here can be checked in the files named next to it.

## 1. The idea in one breath
A reference manager warns you if a paper you cite was retracted. It does not warn you if a paper you cite *cites* a retracted paper, or if that
happens one step further back. Bedrock does: you paste a list of DOIs, it walks the citation graph up to two steps and shows the exact path from your
paper to the retracted one, with the retraction date and the recorded reasons. An AI agent explains the findings and proposes edits; only a person
can approve them.

## 2. The graph (rule 10: data model)
Built in FalkorDB. Nodes and edges (`README.md`, `queries/00_schema.cypher`, `scripts/load_graph.py`):
- `Paper` with `id`, `doi`, `pub_date`, `retracted_at`, `retraction_reasons`, `ref_total`, `refs_indexed`. A retraction is a property, not a separate node.
- `Venue` (the journal) and `PUBLISHED_IN` from paper to venue.
- `CITES` from a paper to a paper it cites. This is the edge everything depends on.
- Research graph only (not in the published snapshot): `Author` with a salted hash instead of an identity, `WROTE`, and two derived edges
  (`COAUTHOR`, `BIB_COUPLED`) that we built for the backtest.

Two versions exist on purpose:
- **Research graph:** about 2.5 million nodes, used for the backtest.
- **Published slim graph:** 318,942 nodes and 530,894 edges (312,108 papers, 6,834 venues; 220,696 `CITES` edges plus 310,198 `PUBLISHED_IN` edges).
  An exposure path can only follow `CITES` between papers we hold, so dropping authors and cited-only stubs cannot change an answer.
  We **proved** this: `scripts/verify_slim_graph.py` compared full audit results for 2,501 DOIs on both graphs and found 0 differences.

## 3. The queries (rule 10: the Cypher the product depends on)
All in `queries/audit/`, run by FalkorDB, called from `src/bedrock/audit.py`:
- `10_resolve`: look up each DOI (index on `Paper.doi`) with its venue. A DOI not found is reported `NOT_IN_CORPUS`.
- `21_direct`: papers this paper cites that are retracted (1 hop).
- `22_two_hop`: paper cites X (not retracted) and X cites a retracted paper R that the paper does not already cite (2 hops).
- `31_alternatives`: papers most often cited together with a retracted one (co-citation). A suggestion only; topical fit is never verified.
- `20_indexed_refs`, `30_citers`, `40_venue_retractions`: coverage ("checked 34 of 48 references"), how many papers cite a retracted one, retractions in the venue.

One real engineering decision: the queries use `WITH` barriers so FalkorDB starts from the few input papers instead of all 61,299 retracted papers.
Without them an audit of 9 papers took 59 seconds; with them it takes a fraction of a second (re-timed on 2026-10-17: 0.05 to 0.4 s for 9 papers, 0.15 to 0.4 s for 150; see `docs/DECISIONS.md`).

Five statuses, strongest first: `RETRACTED`, `CITES_RETRACTED` (1 hop), `TWO_HOP`, `NO_EXPOSURE_FOUND`, `NOT_IN_CORPUS`.
`NO_EXPOSURE_FOUND` is never "safe": only indexed references and only two hops were checked, and the app says so.

## 4. The architecture (follow one request)
1. Browser (`src/bedrock/web/`) sends pasted text to `POST /api/audit` or `/api/agent` (`src/bedrock/server.py`).
2. The server pulls DOIs out of the text (`extract_dois`), applies per-visitor rate limits in public mode (`src/bedrock/ratelimit.py`), and calls `Auditor.audit` (`src/bedrock/audit.py`).
3. `Auditor` runs the queries above in FalkorDB and assembles items, paths, coverage and caveats. Results are sorted so the same input always gives the same output.
4. `build_proposals` turns findings into proposed actions (remove, suggest alternative, review). **Nothing is applied here.**
5. `POST /api/apply` re-runs the audit itself and applies only proposal ids the server generated, for the ones the person ticked. The client cannot inject its own results.
6. Everything is rendered with DOM calls and `textContent` (never `innerHTML`), under a strict content security policy.

## 5. The agent (src/bedrock/agent.py, src/bedrock/llm.py)
- Model: Groq `openai/gpt-oss-120b`, tool calling. Groq because the free tier costs nothing (your decision; the Claude API needs a $5 deposit).
- Three tools, all read-only: `audit_bibliography`, `explain_finding`, `find_dois`. There is no edit tool, and a test enforces that.
- **Grounding:** every DOI in the agent's answer must have come from the pasted text or a tool result; otherwise the UI shows a warning.
- **Completeness:** if the summary leaves out a flagged paper, the agent gets one retry; anything still missing is appended in plain words.
- **Counts:** the opening line ("Checked 9 DOIs: 2 retracted, ...") is written by our code from the audit, never by the model, because models miscount.
- **Fallback:** the structured audit is computed independently of the model. Without a key, or if Groq is rate-limited, you still get the full audit and a plain summary.
- The cards on screen come straight from the graph. The model only writes the summary.

## 6. The honest result (docs/RESULTS.md, docs/BACKTEST_DESIGN.md)
We first tried to *predict* which papers will be retracted using graph signals. We wrote the success test before looking (the graph method must beat the
best simple baseline, and survive removing the largest journal), then ran it on 134,798 articles with 140 later retractions. **It failed.** The only
strong signal was "cites an already retracted paper" (5 to 12 times more likely to be retracted later, depending on the cutoff), and that is a lookup,
not a forecast. So the product became an exact provenance audit. You made that call, and the failed test is reported openly on the product page.

## 7. Questions a judge might ask, with the short answer
- **Why a graph?** The question is about paths between papers. A table lookup finds direct citations; two hops and "the exact chain" are traversals.
  FalkorDB runs them in a fraction of a second, and the same graph answers co-citation questions for alternatives.
- **Why not just use OpenAlex's API live?** We need retracted-paper flags joined to citation paths, queried 150 papers at a time in under half a second, with a fixed snapshot so results are reproducible.
- **Is the AI doing the analysis?** No. The graph produces every finding. The model summarises and proposes; our code verifies its numbers and DOIs.
- **What if the model lies or skips something?** Invented DOIs are flagged, counts come from the audit, and omitted papers are appended. Tests cover each case (`tests/test_agent.py`).
- **What are the limits?** Only the indexed corpus (213 journals, 251,645 articles plus their cited papers), two hops, and the Retraction Watch snapshot of 2026-10-15. "No exposure found" is not a clearance.
- **Privacy?** The published graph has no authors. Findings are about papers, never people; a flag is a prompt for human review.
- **What did you do vs the AI?** You chose the idea and the rules, approved the backtest size, decided the pivot, chose Groq, approved each publication and deployment. Claude Code wrote most of the code and docs from your instructions (`README.md` disclosure, `docs/DECISIONS.md`).

## 8. Try these before you submit
- Run `docker compose --profile demo up --build app`, open http://127.0.0.1:8765, press "Try an example", then "Audit with agent". Follow one finding from the card back to `queries/audit/22_two_hop.cypher`.
- Open `docs/DECISIONS.md` and be ready to say why each row happened.
- Run `python -m unittest discover tests` (90 tests).
