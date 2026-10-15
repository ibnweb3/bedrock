// Suggested replacements for a retracted work: non-retracted papers most often cited together with it
// by indexed papers (co-citation). A heuristic suggestion only - topical fit is NOT verified.
// WITH barriers keep the traversal anchored at the retracted paper (see 21_direct.cypher).
MATCH (r:Paper {id: $rid})
WITH r
MATCH (c:Paper)-[:CITES]->(r)
WITH r, c
MATCH (c)-[:CITES]->(alt:Paper)
WHERE alt.retracted_at IS NULL AND alt.id <> $rid AND alt.doi IS NOT NULL
WITH alt, count(DISTINCT c) AS co
ORDER BY co DESC
LIMIT $limit
RETURN alt.id, alt.doi, alt.pub_date, co
