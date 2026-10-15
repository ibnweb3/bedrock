// Per community: members, and members retracted by $t0.
MATCH (p:AsOf)
RETURN p.comm AS comm, count(p) AS size,
       sum(CASE WHEN p.retracted_at <= $t0 THEN 1 ELSE 0 END) AS ret
