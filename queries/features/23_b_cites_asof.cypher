// Baseline b_cites_asof: citations from held papers published <= $t0 (dataset-internal control).
MATCH (x:Paper)-[:CITES]->(c:Paper {candidate:true})
WHERE x.pub_date <= $t0 AND c.pub_date > $lo AND c.pub_date <= $t0
  AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
RETURN c.id AS id, count(x) AS n
