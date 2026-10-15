// COAUTHOR: one edge per author pair that appears together on >= 1 paper in the graph.
//   n     = number of joint papers
//   first = earliest joint publication date (YYYYMMDD) -> use "c.first <= $t0" for as-of-T0 views
// Direction is arbitrary (a.id < b.id); query it undirected: (a)-[:COAUTHOR]-(b).
MATCH (a:Author)-[:WROTE]->(p:Paper)<-[:WROTE]-(b:Author)
WHERE a.id < b.id
WITH a, b, count(p) AS n, min(p.pub_date) AS first
CREATE (a)-[:COAUTHOR {n: n, first: first}]->(b)
RETURN count(*)
