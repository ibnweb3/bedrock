// Resolve input DOIs to papers in the corpus (index scan on Paper.doi) with venue context.
// A DOI that is not in the corpus returns a row with null fields and is reported as NOT_IN_CORPUS.
UNWIND $dois AS d
OPTIONAL MATCH (p:Paper {doi: d})
OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)
RETURN d, p.id, p.pub_date, p.retracted_at, p.retraction_reasons, p.ref_total, v.id, v.name, v.stratum
