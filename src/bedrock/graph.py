"""FalkorDB access. All graph reasoning in this project goes through here (rules 2 and 3):
no other graph engine, and no graph logic in pandas/NetworkX.
"""
from __future__ import annotations

from pathlib import Path

from .config import Settings, load_settings

QUERIES_DIR = Path(__file__).resolve().parents[2] / "queries"


def connect(settings: Settings | None = None):
    """Return a FalkorDB graph handle. Requires `pip install -r requirements.txt`."""
    from falkordb import FalkorDB  # imported lazily so unit tests need no install

    s = settings or load_settings()
    db = FalkorDB(host=s.falkordb_host, port=s.falkordb_port)
    return db.select_graph(s.graph_name)


def read_query(name: str) -> str:
    """Load a Cypher file from queries/. The app runs exactly what the README lists."""
    return (QUERIES_DIR / name).read_text(encoding="utf-8")


def run_statements(graph, cypher_text: str) -> None:
    """Run ';'-separated statements one by one, skipping comment-only chunks.
    'already indexed' errors are tolerated so schema setup is re-runnable."""
    # Drop comment lines BEFORE splitting: a ';' inside a comment must not split a statement.
    code = "\n".join(
        ln for ln in cypher_text.splitlines() if not ln.strip().startswith("//")
    )
    for chunk in code.split(";"):
        stmt = chunk.strip()
        if not stmt:
            continue
        try:
            graph.query(stmt)
        except Exception as exc:  # noqa: BLE001
            if "already indexed" in str(exc).lower():
                continue
            raise
