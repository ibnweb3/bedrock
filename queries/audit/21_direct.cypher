// 1 hop: retracted works the paper cites directly.
// The WITH barrier forces FalkorDB to start from the paper (index lookup) and expand its few
// references; without it the planner starts from all 61k retracted papers (seconds instead of ms).
UNWIND $ids AS i
MATCH (p:Paper {id: i})
WITH p
MATCH (p)-[:CITES]->(r:Paper)
WHERE r.retracted_at IS NOT NULL
RETURN p.id, r.id, r.doi, r.retracted_at, r.retraction_reasons
ORDER BY p.id, r.retracted_at
