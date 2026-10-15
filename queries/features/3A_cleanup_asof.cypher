// Remove the scratch label and property written by 37/38.
MATCH (p:AsOf) REMOVE p:AsOf, p.comm
RETURN count(p) AS n
