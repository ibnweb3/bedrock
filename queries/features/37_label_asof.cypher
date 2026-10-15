// Scratch label AsOf on held papers published <= $t0: the population the community detection may see.
MATCH (p:Paper {full:true}) WHERE p.pub_date <= $t0
SET p:AsOf
RETURN count(p) AS n
