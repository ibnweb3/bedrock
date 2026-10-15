// Context: retractions recorded in each venue (all years). Public record; not evidence about any one paper.
// WITH barrier: start from the venue, not from all retracted papers (see 21_direct.cypher).
UNWIND $vids AS vid
MATCH (v:Venue {id: vid})
WITH v
MATCH (p:Paper)-[:PUBLISHED_IN]->(v)
WHERE p.retracted_at IS NOT NULL
RETURN v.id, count(p) AS n
