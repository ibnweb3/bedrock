// How many indexed papers cite each retracted paper (context for how widely a retracted work propagated).
UNWIND $ids AS i
MATCH (r:Paper {id: i})<-[:CITES]-(c:Paper)
RETURN i, count(c) AS citers
