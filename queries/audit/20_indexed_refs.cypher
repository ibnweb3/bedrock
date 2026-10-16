// How many of each paper's references are indexed in the graph (coverage), vs p.ref_total in the source.
// Slim (audit-only) graphs store the figure as p.refs_indexed because they drop edges to cited-only works;
// the full graph has no such property, so the edge count is used.
UNWIND $ids AS i
MATCH (p:Paper {id: i})
OPTIONAL MATCH (p)-[c:CITES]->()
WITH p, count(c) AS n
RETURN p.id, coalesce(p.refs_indexed, n)
