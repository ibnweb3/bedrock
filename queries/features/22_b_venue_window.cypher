// Baseline b_venue_rate inputs: per venue, papers published in ($lo, $t0] and how many were retracted by $t0.
MATCH (p:Paper)-[:PUBLISHED_IN]->(v:Venue)
WHERE p.pub_date > $lo AND p.pub_date <= $t0
RETURN v.id AS venue, count(p) AS n,
       sum(CASE WHEN p.retracted_at <= $t0 THEN 1 ELSE 0 END) AS retracted
