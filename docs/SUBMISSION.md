# Submission answers (draft; paste into the form on Oct 18)

I could not see the form's exact fields, so these are written to cover what the rules require (rule 10) and what a form usually asks for.
Edit anything that does not match the real fields. Re-read https://www.wemakedevs.org/hackathons/falkordb/rules first.

**Project name:** Bedrock

**Track (rule 5, name every track entered):** Track 01, Agents That Act on Connected Data. (Only this one.)

**One-line pitch:** Bedrock checks a reference list against retracted research, follows every citation path up to two steps, and shows you the exact chain, with an AI agent that can propose fixes but never apply them.

**Short description (about 100 words):**
Reference managers warn you when a paper you cite was retracted. They do not warn you when a paper you cite cites one, or when it happens two steps back. Bedrock does. Paste a list of DOIs and it queries a FalkorDB citation graph of 312,108 papers and 61,299 retracted works, then shows each finding with the exact citation path, the retraction date and the recorded reasons. A read-only AI agent explains the results and proposes edits, and only a person can approve them. We also tried to predict future retractions, pre-registered the success test, and it failed, so Bedrock reports exact provenance, not forecasts.

**How FalkorDB is used (rules 2 and 3):** The citation graph (`Paper`, `Venue`, `CITES`, `PUBLISHED_IN`) lives in FalkorDB. Every finding is a Cypher traversal in `queries/audit/`: 1-hop and 2-hop paths to retracted papers, coverage counts, and co-citation alternatives. Without the graph the product returns nothing.

**Links**
- Source code (public): https://github.com/ibnweb3/bedrock
- Demo video (2:15): https://youtu.be/bqgNoxluHjw
- Live demo and product page: https://bedrock-audit.ibnweb3lab.workers.dev (the live app link is on that page and is served from the author's PC; if it is offline, run the one-command local setup below)
- X post: https://x.com/ibnWeb3/status/2111400175331672463

**Run it locally (complete setup, rule 10):**
```
git clone https://github.com/ibnweb3/bedrock && cd bedrock
docker compose --profile demo up --build app
# open http://127.0.0.1:8765  (the AI agent needs a free GROQ_API_KEY in .env; the graph audit works without it)
```
Details: `docs/DEPLOY.md`. Tests: `python -m unittest discover tests` (90 tests).

**Tech stack:** FalkorDB (graph), Python (stdlib HTTP server, `falkordb`, `httpx`), plain HTML/CSS/JS front end, Docker, Groq `openai/gpt-oss-120b` for the agent, Cloudflare Workers for the product page.

**Data (rule 6):** Retraction Watch database (public, via Crossref) and OpenAlex (CC0). Author identities are never stored or shown; the published graph contains no author data.

**AI assistance disclosure (rule 11):** The code and docs were written with Claude Code (Anthropic) from the participant's instructions. At run time the optional agent uses Groq's `openai/gpt-oss-120b`; the findings themselves come from graph queries, not from the model. The participant's decisions are in `docs/DECISIONS.md`.

**Honest limits:** Findings cover the indexed corpus only (213 journals, 251,645 articles plus papers they cite), two hops, and the Retraction Watch snapshot of 2026-10-15. "No exposure found" is not a clearance. A flag is a prompt for human review, never an accusation.
