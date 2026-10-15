// 2 hops: the paper cites X (not itself retracted) and X cites a retracted work R that the paper does not cite directly.
// WITH barriers keep the traversal anchored at the paper (see 21_direct.cypher).
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
