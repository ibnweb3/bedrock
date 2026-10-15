// Candidate set as of $t0 plus the label. Candidates: pool-venue articles published in ($lo, $t0]
// and not retracted on or before $t0. Label y = retracted in ($t0, $end].
// $lo = t0 - 4 years, $end = t0 + 24 months. Also returns the community id (set by 38_community).
MATCH (c:Paper {candidate:true})-[:PUBLISHED_IN]->(v:Venue)
WHERE c.pub_date > $lo AND c.pub_date <= $t0 AND (c.retracted_at IS NULL OR c.retracted_at > $t0)
RETURN c.id AS id, v.id AS venue, v.stratum AS stratum,
       CASE WHEN c.retracted_at IS NOT NULL AND c.retracted_at <= $end THEN 1 ELSE 0 END AS y,
       c.comm AS comm
