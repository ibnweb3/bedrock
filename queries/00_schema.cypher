// Schema / indexes. Statements are separated by ';' and run one at a time by
// src/bedrock/graph.py (creating an index twice errors; the loader tolerates that).
// Syntax is unverified until scripts/smoke_test.py has run against a live FalkorDB.
CREATE INDEX FOR (p:Paper) ON (p.id);
CREATE INDEX FOR (a:Author) ON (a.id);
CREATE INDEX FOR (v:Venue) ON (v.id);
CREATE INDEX FOR (p:Paper) ON (p.pub_date);
CREATE INDEX FOR (p:Paper) ON (p.retracted_at);
CREATE INDEX FOR (p:Paper) ON (p.candidate);
