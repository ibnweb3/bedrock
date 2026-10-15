// g_contam2: distinct retracted-by-$t0 papers reached in exactly 2 citation hops, through an
// intermediate paper that is itself not retracted by $t0, and not cited directly by the candidate.
MATCH (r:Paper) WHERE r.retracted_at <= $t0
MATCH (x:Paper)-[:CITES]->(r)
WHERE x.pub_date <= $t0 AND (x.retracted_at IS NULL OR x.retracted_at > $t0)
MATCH (c:Paper {candidate:true})-[:CITES]->(x)
WHERE c.pub_date > $lo AND c.pub_date <= $t0 AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
  AND NOT (c)-[:CITES]->(r)
RETURN c.id AS id, count(DISTINCT r) AS n
