// g_coupled_n / g_coupled_w: BIB_COUPLED neighbours retracted by $t0 - how many, and total shared references.
MATCH (r:Paper) WHERE r.retracted_at <= $t0
MATCH (c:Paper {candidate:true})-[b:BIB_COUPLED]-(r)
WHERE c.pub_date > $lo AND c.pub_date <= $t0 AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
RETURN c.id AS id, count(DISTINCT r) AS n, sum(b.shared) AS w
