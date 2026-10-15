// How many of each paper's references are indexed in the graph (coverage), vs p.ref_total in the source.
UNWIND $ids AS i
MATCH (p:Paper {id: i})
OPTIONAL MATCH (p)-[c:CITES]->()
RETURN i, count(c) AS indexed
