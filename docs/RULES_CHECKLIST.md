# Graph Hacks rules checklist

Source: https://www.wemakedevs.org/hackathons/falkordb/rules (re-read 2026-10-17; **read it once more on the morning of Oct 18 before submitting**).
Window: Oct 15 12:01 AM IST to Oct 18 11:59 PM IST (= 7:29 PM Nigeria time on Oct 18). Numbering follows the page (18 rules).
Legend: [x] true in the repo today, [ ] still to do at submission, n/a not a requirement on us.

| # | Rule (short) | Evidence in this repo | Status |
|---|---|---|---|
| 1 | Solo or up to 4, one team each | Solo entry | [x] |
| 2 | FalkorDB is the primary graph DB and central to the product | Every audit question is a Cypher query in `queries/audit/`, run by FalkorDB (`src/bedrock/graph.py`, `src/bedrock/audit.py`); no other graph engine | [x] |
| 3 | The graph does real work; the product depends on it | Direct and two-hop exposure, path finding, co-citation alternatives are graph traversals. Without the graph the product returns nothing | [x] |
| 4 | Any way of running FalkorDB | Docker: `docker-compose.yml` and the `Dockerfile` (base image pinned by digest) | [x] |
| 5 | Name every track entered, at submission | Track 01 only: Agents That Act on Connected Data | [ ] at submission |
| 6 | Only public, synthetic or own data; nothing private, login-protected, paywalled, personal or restricted | Retraction Watch (public CSV via Crossref) and OpenAlex (CC0). The published snapshot holds no author data at all (0 author nodes); in the research graph authors were hashed in memory and names, emails and ORCIDs were never stored. See "Data caveat" below | [x] |
| 7 | Submit before Oct 18 11:59 PM IST | Plan: submit by midday Oct 18 (Nigeria time) | [ ] at submission |
| 8 | Main work starts after the start | Repo created 2026-10-15 15:49 UTC; first commit 2026-10-15 16:47 (UTC+1), after the 12:01 AM IST start (= 2026-10-14 18:31 UTC). History is the evidence | [x] |
| 9 | Libraries, public APIs and datasets are allowed; original work is judged | Dependencies: `falkordb`, `httpx`, `python-dotenv`. Sources cited in the README | [x] |
| 10 | Public repo; README with setup and graph data model; the Cypher/algorithms the product depends on; demo video; live deployment or complete local setup; track | See the deliverables list below | [x] except the track field |
| 11 | Disclose AI coding assistants | README section "AI assistance disclosure"; also the product page footer and the video description | [x] |
| 12 | Participant understands the code and can explain the graph model, queries, architecture and decisions | `docs/WALKTHROUGH.md` (read it before submitting), `docs/DECISIONS.md` | [ ] read the walkthrough |
| 13 | Not entirely AI-generated; meaningful contribution, verification, understanding | Participant chose the idea, set the rules, approved the backtest design, decided the pivot from prediction to audit, chose the LLM provider, approved each deployment step; log in `docs/DECISIONS.md` | [x] |
| 14 | Prize pool | iPhone 18 Pro goes to the best Track 01 project | n/a |
| 15 | IP belongs to the participant | n/a; the code is released under MIT (`LICENSE`) | n/a |
| 16-18 | Respect, no harassment or plagiarism or manipulation, no rule-breaking | Honest numbers only (a failed prediction test is reported as failed); sources cited; no named researchers; findings are prompts for review, never accusations | [x] |

## Rule 10 deliverables

- [x] Public source repository: https://github.com/ibnweb3/bedrock (visibility PUBLIC; no `.env` or key files tracked)
- [x] README with setup instructions and the graph data model
- [x] The Cypher the product depends on: `queries/audit/*.cypher` (plus `queries/00_schema.cypher` and the derived-edge queries)
- [x] Demo video: https://youtu.be/bqgNoxluHjw (2:15, unlisted)
- [x] Live deployment (served from the author's PC through a tunnel, address on the product page) and complete local setup: `docker compose --profile demo up --build app` (`docs/DEPLOY.md`)
- [ ] Track named in the submission form: Track 01

## Things to know before submitting

- **Data caveat.** The Retraction Watch database is public but its repository states no licence. The published snapshot (`deploy/`) contains retracted DOIs, dates and reasons from it, with attribution in the README. If the organisers or Retraction Watch object, the snapshot can be removed and rebuilt locally from the pipeline.
- **Licence.** The code is MIT (`LICENSE`, copyright "2026 ibnweb3"; change the name there if you want your real name). The data keeps its own terms (see the README "License" section).
- **Live demo availability.** The live address points at the author's PC through a Cloudflare quick tunnel; it only works while the PC and Docker are running. The one-command local setup is the fallback.
- **Rule changes.** The page says rules may be updated. Re-read it on Oct 18 before submitting.
