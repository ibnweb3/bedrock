# Decision log

Rules 12 and 13 require the participant to understand and meaningfully contribute to this
project. Record each decision here with who made it and why. Edit freely.

| Date | Decision | Made by | Why / notes |
|---|---|---|---|
| 2026-10-15 | Build "Bedrock" (retraction-contamination graph agent) for Track 01 | Participant | Chosen over PR triage, fraud-ring and microservice ideas after comparing data, evidence, feasibility and rule risk |
| 2026-10-15 | Fallback = PR triage if no lift over the venue baseline by Fri Oct 16 noon | Participant + Claude | Time-boxed risk control |
| 2026-10-15 | Retraction stored as properties on `Paper` (`retracted_at`, `retraction_reasons`), not a separate node | Claude (proposed) — **participant to confirm** | Smaller graph for the 100 MB free tier; simpler as-of-T0 filter |
| 2026-10-15 | Dates as integer `YYYYMMDD` | Claude (proposed) — **participant to confirm** | Simple, verifiable comparisons in Cypher |
| 2026-10-15 | Author IDs stored as HMAC-SHA256(salt, id) truncated to 16 hex chars | Claude (proposed) — **participant to confirm** | Rule 6 hardening; keeps co-authorship structure |
| 2026-10-15 | Staging files allowed for ETL only; all runtime graph logic in FalkorDB | Participant + Claude | Rules 2 and 3 |
| 2026-10-15 | Candidate pool = journals stratified by pre-cutoff retraction history (H / L / Z), selected with pre-cutoff counts only, seeded; two cutoffs 2020-12-31 and 2022-12-31 | Claude (proposed) — **participant to confirm** | See docs/BACKTEST_DESIGN.md. Avoids selecting venues by outcome; pool is a convenience sample, stated as a limitation |
| 2026-10-15 | Sizes: 300-3,000 works per venue over 2017-2022; 40 H / 30 L / 60 Z venues | Claude (proposed) — **participant to confirm** | Keeps the pull near 100-150k works (~1-1.5k credits) and the graph tractable |
| 2026-10-15 | Feasibility check showed the first pool (`venues_v1`) gives 84 / 11 positives at T0 2020 / 2022; propose H=150 venues, T0 2020 (primary) and 2021 (secondary), 2022 as regime check only, within-H primary metrics, venue-clustered bootstrap | Claude (proposed) — **participant to confirm** | Disclosed that k_h was chosen after seeing positive counts; venue choice still uses pre-cutoff history only. See docs/BACKTEST_DESIGN.md |
| 2026-10-15 | H = 150 venues approved; pool built as 150 H / 30 L / 33 Z (213 venues, 251,645 articles) | Participant (approved) + Claude | k_h chosen after seeing positive counts (disclosed in BACKTEST_DESIGN.md) |
| 2026-10-15 | Graph keeps cited-only works as stub `Paper` nodes only if cited by >= 2 held papers (and <= 500); authors kept only if on >= 2 papers; all citations to fully-held papers kept | Claude (proposed) — **participant to confirm** | A work cited once or an author on one paper links nothing; keeps the graph at ~1.2 GiB. Only 39 refs exceeded the 500 cap |
| 2026-10-15 | Report results with a venue-clustered bootstrap, also excluding the largest venue, plus per-venue breakdown | Claude (proposed) — **participant to confirm** | 70-88% of positives sit in 2-3 venues (mass retractions) |

