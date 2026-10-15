// Baseline b_author_prior (author distance 0): authors of the candidate who wrote a paper retracted by $t0.
MATCH (a:RetAuth)-[:WROTE]->(c:Paper {candidate:true})
WHERE c.pub_date > $lo AND c.pub_date <= $t0 AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
RETURN c.id AS id, count(DISTINCT a) AS n
