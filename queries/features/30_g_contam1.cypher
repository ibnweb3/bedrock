// g_contam1: distinct retracted-by-$t0 papers cited directly. Start from the retracted papers and
// walk incoming CITES (starting from all candidates exceeds FalkorDB's scan budget).
MATCH (r:Paper) WHERE r.retracted_at <= $t0
MATCH (c:Paper {candidate:true})-[:CITES]->(r)
WHERE c.pub_date > $lo AND c.pub_date <= $t0 AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
RETURN c.id AS id, count(DISTINCT r) AS n
