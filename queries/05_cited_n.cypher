// In-degree of CITES per paper, used to ignore ubiquitous references when coupling papers.
// Runs inside FalkorDB. Idempotent (overwrites the property).
MATCH (r:Paper)<-[c:CITES]-()
WITH r, count(c) AS n
SET r.cited_n = n
