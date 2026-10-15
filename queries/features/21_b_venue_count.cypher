// Baseline b_venue_count: retractions dated <= $t0 per venue (all publication years).
MATCH (r:Paper)-[:PUBLISHED_IN]->(v:Venue)
WHERE r.retracted_at <= $t0
RETURN v.id AS venue, count(r) AS n
