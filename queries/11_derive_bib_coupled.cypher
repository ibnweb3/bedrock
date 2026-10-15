// BIB_COUPLED: two held papers that cite >= $min_shared of the same works.
//   shared = number of shared references (ignoring references cited by more than $max_cited papers)
// Computed in slices ($m slices, slice $k) by internal node id so that every pair is created exactly
// once (the slice is decided by node `a`, and a.id < b.id). Query it undirected.
// As-of-T0 views filter on the endpoint papers' pub_date / retracted_at, not on the edge.
MATCH (a:Paper)-[:CITES]->(r:Paper)<-[:CITES]-(b:Paper)
WHERE id(a) % $m = $k AND a.id < b.id AND r.cited_n <= $max_cited
WITH a, b, count(r) AS shared
WHERE shared >= $min_shared
CREATE (a)-[:BIB_COUPLED {shared: shared}]->(b)
RETURN count(*)
