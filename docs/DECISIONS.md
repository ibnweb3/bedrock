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
