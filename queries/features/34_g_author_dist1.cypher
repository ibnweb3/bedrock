// g_coauth1: authors of the candidate at co-author distance exactly 1 from an author of a paper
// retracted by $t0 (COAUTHOR edge existing by $t0; the author is not themselves at distance 0).
MATCH (a0:RetAuth)-[k:COAUTHOR]-(a1:Author)
WHERE k.first <= $t0 AND NOT a1:RetAuth
WITH DISTINCT a1
MATCH (a1)-[:WROTE]->(c:Paper {candidate:true})
WHERE c.pub_date > $lo AND c.pub_date <= $t0 AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
RETURN c.id AS id, count(DISTINCT a1) AS n
