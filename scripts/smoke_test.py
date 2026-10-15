"""Verify the stack end to end: connect, apply schema, write and read back a tiny graph
(including a 2-hop traversal), then clean up. Run after `docker compose up -d`.

    python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bedrock.config import load_settings  # noqa: E402
from bedrock.graph import connect, read_query, run_statements  # noqa: E402


def main() -> int:
    settings = load_settings()
    graph = connect(settings)
    run_statements(graph, read_query("00_schema.cypher"))

    graph.query(
        "CREATE (:Paper {id:'T1', pub_date:20200101}),"
        " (:Paper {id:'T2', pub_date:20210101, retracted_at:20220101}),"
        " (:Paper {id:'T3', pub_date:20220601})"
    )
    graph.query("MATCH (a:Paper {id:'T3'}), (b:Paper {id:'T1'}) CREATE (a)-[:CITES]->(b)")
    graph.query("MATCH (a:Paper {id:'T1'}), (b:Paper {id:'T2'}) CREATE (a)-[:CITES]->(b)")

    res = graph.query(
        "MATCH (p:Paper {id:'T3'})-[:CITES*1..2]->(r:Paper) "
        "WHERE r.retracted_at IS NOT NULL RETURN r.id"
    )
    found = [row[0] for row in res.result_set]
    graph.query("MATCH (n:Paper) WHERE n.id IN ['T1','T2','T3'] DETACH DELETE n")

    ok = found == ["T2"]
    print("2-hop retracted-reference traversal:", "PASS" if ok else f"FAIL (got {found})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
