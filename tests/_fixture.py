"""Tiny graph with known retraction chains, shared by the audit and server tests."""
from __future__ import annotations

import unittest


def connect_or_skip(name: str):
    try:
        from falkordb import FalkorDB
        db = FalkorDB(host="127.0.0.1", port=6379)
        db.connection.ping()
        return db, db.select_graph(name)
    except Exception as exc:  # noqa: BLE001
        raise unittest.SkipTest(f"FalkorDB not reachable: {exc}")


def build(db, name: str):
    try:
        db.select_graph(name).delete()
    except Exception:  # noqa: BLE001
        pass
    g = db.select_graph(name)
    P = lambda i, doi, **kw: {"id": i, "doi": doi, "pub_date": 20200101, "ref_total": kw.pop("rt", 3), **kw}  # noqa: E731
    papers = [
        P("R1", "10.1000/r1", retracted_at=20210601, retraction_reasons=["Plagiarism"]),
        P("R2", "10.1000/r2", retracted_at=20210701, retraction_reasons=["Concerns/Issues about Data"]),
        P("A", "10.1000/a"), P("B", "10.1000/b"), P("X", "10.1000/x"), P("C", "10.1000/c"),
        P("D", "10.1000/d"), P("E", "10.1000/e"), P("ALT", "10.1000/alt"),
        {"id": "S1", "doi": None},
    ]
    g.query("UNWIND $rows AS r CREATE (:Paper {id:r.id, doi:r.doi, pub_date:r.pub_date, retracted_at:r.retracted_at, "
            "retraction_reasons:r.retraction_reasons, ref_total:r.ref_total})", {"rows": papers})
    g.query("CREATE (:Venue {id:'V1', name:'Journal One', stratum:'H'})")
    g.query("MATCH (p:Paper), (v:Venue {id:'V1'}) WHERE p.id IN ['R1','A','R2'] CREATE (p)-[:PUBLISHED_IN]->(v)")
    for a, b in [("A", "R1"), ("B", "X"), ("X", "R1"), ("C", "S1"), ("D", "R1"), ("D", "ALT"),
                 ("E", "R1"), ("E", "ALT"), ("E", "R2")]:
        g.query("MATCH (a:Paper {id:$a}), (b:Paper {id:$b}) CREATE (a)-[:CITES]->(b)", {"a": a, "b": b})
    return g
