**I tried to predict retracted papers. I failed, and built something better.**

*Originally published at [bedrock-audit.ibnweb3lab.workers.dev/blog](https://bedrock-audit.ibnweb3lab.workers.dev/blog/). Built for the Graph Hacks hackathon (WeMakeDevs x FalkorDB), Track 01.*

Imagine you've spent a year on a literature review. Every source on your list checks out, because your reference manager flags nothing. But two steps back, one of those sources leans on a paper that was retracted years ago, and no tool you use was ever going to tell you.

That gap is what **Bedrock** is for. You paste a list of DOIs, and it follows every citation path, up to two steps, from your papers to retracted research. For each finding it shows the exact chain, the retraction date and the reasons on record. An AI agent explains the results and proposes edits. It can never apply them.

This is the story of building it in three days: the parts that went well, the part that went badly, and the part where my own agent miscounted.

{% embed https://youtu.be/bqgNoxluHjw %}

- **Code (MIT):** https://github.com/ibnweb3/bedrock
- **Try it:** https://bedrock-audit.ibnweb3lab.workers.dev

## The idea: a question about paths, not rows

Tools that flag retractions typically check the papers you cite. They don't ask what those papers cite. That second question is a graph question: start at a paper, follow `CITES` edges, stop when you reach a retracted node, and report the path.

Here is a real path from the corpus:

```
your reference ──cites──▶ not flagged ──cites──▶ RETRACTED 2014-10-01
10.1016/j.neubiorev       10.1111/ejn.13603      10.1016/j.jpsychires
.2019.09.040                                     .2014.06.018
```

The middle paper isn't retracted, which is exactly why nothing warns you.

Two rules shaped everything. First, **Bedrock states facts about a fixed corpus, it doesn't guess.** A paper with "no exposure found" is never called safe, only not found within two hops. Second, **the person decides.** The agent proposes, a human approves.

## The data: public, and kept that way

The retractions come from the Retraction Watch database, distributed by Crossref. The citations come from OpenAlex, which is CC0. I pulled works from 213 journals, 251,645 articles in all, and joined them to 61,299 retracted works. The hackathon rules ask for public data only, so authors were hashed with a secret salt in memory before anything touched disk, and names, emails and ORCIDs were dropped. The graph I publish has **no author data at all**.

```
Retraction Watch ─┐
                  ├─▶ FalkorDB (Cypher) ─▶ audit queries ─▶ read-only agent ─▶ you approve
OpenAlex (CC0) ───┘
```

The graph produces every finding. The model only writes the summary, and a person approves any change.

## The graph: a small model, sharp queries

The model is deliberately plain: `Paper` nodes carrying `doi`, `retracted_at` and `retraction_reasons`, `Venue` nodes, and two relationships, `CITES` and `PUBLISHED_IN`. A retraction is a property, not its own node, which keeps the graph small and makes "as of this date" filters trivial. The two-hop question is one query:

```cypher
UNWIND $ids AS i
MATCH (p:Paper {id: i})
WITH p
MATCH (p)-[:CITES]->(x:Paper)
WHERE x.retracted_at IS NULL
WITH p, x
MATCH (x)-[:CITES]->(r:Paper)
WHERE r.retracted_at IS NOT NULL AND NOT (p)-[:CITES]->(r)
RETURN p.id, x.id, x.doi, r.id, r.doi, r.retracted_at, r.retraction_reasons
LIMIT $limit
```

Read it aloud: the paper cites `x`, `x` isn't retracted, `x` cites a retracted `r`, and the paper doesn't already cite `r` directly. Everything Bedrock shows, the direct hits, the two-hop paths and the "papers cited alongside it" suggestions for replacements, is a query of this size, run by FalkorDB.

## The 59-second query: the planner started in the wrong place

My first audit of nine papers took **59 seconds**. The data was small and the question was simple, so something was off. The cause: FalkorDB's planner began at the 61,299 retracted papers and worked back toward my input, instead of starting at the few papers I'd asked about. The fix was the humble `WITH p` you can see above. It forces the traversal to start from the input papers and expand their handful of references.

Re-timed after the fix: 0.05 to 0.4 seconds for nine papers, and 0.15 to 0.4 seconds for 150.

> **What I took from it:** a graph database makes the shape of the query matter more than the size of the data. When an indexed lookup can anchor a traversal, say so in the query. It's the difference between a demo and a product.

## The test that failed: I tried to predict retractions

Bedrock's first idea was ambitious: use graph signals, like who a paper cites, who it shares authors with and which community it sits in, to predict which papers will be retracted. Before looking at any result I wrote down the pass mark: the graph method had to beat the best simple baseline, and the gap had to survive removing the largest journal. Then I ran it on 134,798 articles from journals with a retraction history, 140 of which were retracted within the next two years (cutoff 2020-12-31).

| Method | Average precision |
|---|---|
| Random ranking | 0.0012 |
| Journal's past retraction rate | 0.0066 |
| Cites a retracted work (one hop) | 0.0066 |
| Two citation hops | 0.0021 |
| All graph signals combined | 0.0041 |
| Journal history plus graph | 0.0074 |

**The verdict: no reliable improvement.** The best combination beat the journal baseline by less than the uncertainty. The 140 retractions were concentrated in 20 to 27 journals, so the study has low power, and the multi-hop signals did not beat their one-hop versions. The single signal that stood out, "this paper already cites a retracted one", made a paper 5 to 12 times more likely than average to be retracted later, depending on the cutoff. That is a lookup, not a forecast.

I could have shipped a "retraction risk score" anyway. It would have looked impressive and been unearned. Instead I changed the product: Bedrock stopped predicting and started proving. Exact provenance, with the failed test on the front page. That decision, more than any query, is what I'd defend in front of anyone.

## The agent: useful, on a short leash

The agent runs on Groq's free tier with `openai/gpt-oss-120b`. It has three tools, `audit_bibliography`, `explain_finding` and `find_dois`, and every one only reads. There's no edit tool, and a test makes sure it stays that way. The guardrails came from watching it misbehave:

- **Grounding.** Every DOI in the answer must come from your text or a tool result. Models retyped DOIs and corrupted some, so an invented one now raises a visible warning.
- **Completeness.** It once skipped a flagged paper. If the summary omits one, the agent gets a single retry; anything still missing is appended in plain words.
- **Counts.** The same run opened with "one retracted paper" when the audit had found two. Models miscount, so the opening line, "Checked 9 DOIs: 2 retracted, 2 cite a retracted work directly...", is written by code from the audit, never by the model.
- **Fallback.** The findings are computed independently of the model. If the key is missing or Groq is rate-limited, you still get the full audit.

Then the approval step: the server re-runs the audit itself and only applies proposal ids it generated. The browser can't hand it a result to trust.

## Shipping it: 2.5 million nodes down to 318,942

The research graph, with authors and two derived edge types for the backtest (1.69M `COAUTHOR` and 2.68M `BIB_COUPLED`, both built in Cypher inside FalkorDB), reaches about 2.5 million nodes. Too big to hand to anyone. But an exposure path can only follow `CITES` between papers I hold, so for the audit most of it is dead weight.

So I built a slim graph with just papers, venues and the citations between held papers: **318,942 nodes and 530,894 edges.** Then I tested the claim, not just made it. A script audited 2,501 DOIs on both graphs and compared the complete results: statuses, paths, reasons, coverage and alternatives. **Zero differences.** (That test also caught a real bug: self-citations had inflated a reference count by exactly one in 37 papers.)

The slim graph ships as a 17 MB `DUMP` snapshot in the repo. In a container limited to 512 MB and a tenth of a CPU, it restores in about a minute and sits at roughly 300 MB. A judge can run the whole thing with:

```bash
git clone https://github.com/ibnweb3/bedrock && cd bedrock
docker compose --profile demo up --build app
# open http://127.0.0.1:8765
```

I checked that from a fresh clone with no keys: a no-cache build took just over two minutes and the app answered five seconds after starting.

## Honest limits

- It knows only its corpus: 213 journals, 251,645 articles and the papers they cite, with a Retraction Watch snapshot from Oct 15, 2026.
- It looks two hops back. "No exposure found" means nothing was found within that, not that a paper is sound.
- Reasons and dates come from Retraction Watch. A flag is a prompt for a person to read, never a finding about an author.
- The live demo runs on one small AWS server, so it can be slow if many people try it at once. The one-command setup above always works.

## What I learned

- Write the pass mark before you run the test. It's the only reason a failure was a result instead of an argument.
- In a graph database, anchor your traversals. Query shape beats data size.
- Let code state the facts and let the model write the prose. Check its numbers anyway.
- Prove your shortcuts. "The slim graph is equivalent" became a claim I could stand behind only after the 2,501-DOI test.

## How this was built

I built it solo in three days, with Claude Code writing most of the code and docs from my instructions. I chose the idea, set the rules, approved the experiment's size, decided the pivot from prediction to provenance, picked Groq for the agent, and signed off every publication and deployment. The decision log is in the repo at `docs/DECISIONS.md`. The code is MIT licensed; the data keeps its own terms (Retraction Watch via Crossref, OpenAlex CC0).

Photo: sedimentary rock layers at Zabriskie Point, Death Valley, by Brigitte Werner, CC0 ([Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Sedimentary_Rock_Layers_Zabriskie_Point_Death_Valley_USA.jpg)).
