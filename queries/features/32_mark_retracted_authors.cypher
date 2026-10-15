// Scratch label RetAuth on authors (hashed ids) of papers retracted by $t0. Removed by 35_unmark.
MATCH (r:Paper) WHERE r.retracted_at <= $t0
MATCH (a:Author)-[:WROTE]->(r)
SET a:RetAuth
RETURN count(DISTINCT a) AS n
