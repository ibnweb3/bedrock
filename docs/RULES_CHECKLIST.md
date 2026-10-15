# Graph Hacks rules checklist

Source: https://www.wemakedevs.org/hackathons/falkordb/rules (read 2026-10-13; **re-read on the
morning of Oct 18** — the page says rules may be updated). Window: Oct 15 12:01 AM IST to
Oct 18 11:59 PM IST. Tick a box only when it is true in the repo.

| # | Rule (short) | Where / how satisfied | Done |
|---|---|---|---|
| 1 | Solo or ≤4, one team each | Solo; registered 2026-10-15 | [x] |
| 2 | FalkorDB primary, central | All reasoning runs in FalkorDB (`queries/`, `src/bedrock/graph.py`) | [ ] |
| 3 | Graph does real work; product must not work without it | Signals are Cypher/algos in FalkorDB; ablation multi-hop vs 1-hop reported honestly | [ ] |
| 4 | Run FalkorDB any way | Docker (`docker-compose.yml`) | [x] |
| 5 | Name every track at submit | Track 01 only | [ ] |
| 6 | Only public/synthetic/own data; nothing private, login-protected, paywalled, personal, restricted | Public sources only; author IDs hashed; names/emails/ORCIDs dropped | [ ] |
| 7 | Submit before Oct 18 11:59 PM IST (= 7:29 PM Nigeria) | Target: submit by midday Oct 18 | [ ] |
| 8 | Main work starts after start | Fresh repo created 2026-10-15; commit history is the evidence | [ ] |
| 9 | Libraries/public data allowed; original work judged | Sources and libraries cited in README | [ ] |
| 10 | Repo (public), README with setup + data model, Cypher/algos, demo video, live deploy or local setup, track | See sub-list below | [ ] |
| 11 | Disclose AI assistants | README section (needs specifics before submit) | [ ] |
| 12 | Participant can explain graph model, queries, architecture, decisions | Read-through session; `docs/DECISIONS.md` | [ ] |
| 13 | Not entirely AI-generated; meaningful contribution/verification | Participant chose idea, reviews and runs the backtest, verifies numbers | [ ] |
| 14 | Prize: iPhone 18 Pro = Track 01 | n/a | — |
| 15 | IP belongs to participants | n/a | — |
| 16–18 | Respect; no harassment/plagiarism/manipulation; CoC | Honest numbers only; prior work cited; no named researchers | [ ] |

## Rule 10 deliverables

- [ ] Public source repository (create on GitHub — needs the participant's approval; no keys committed)
- [ ] README with setup instructions and the graph data model
- [ ] The Cypher queries / graph algorithms the product depends on (`queries/`)
- [ ] Demo video of the working project
- [ ] Live deployment, or complete local setup instructions
- [ ] Track named in the submission form

## FAQ items worth remembering

- Submission and main FalkorDB implementation must be new work done during the event.
- A live deployment is preferred; otherwise full local setup + working demo video.
- AI assistants allowed, but you must be able to explain what was built and why.
