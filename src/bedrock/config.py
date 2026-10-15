"""Environment-driven settings. Secrets come from .env / the process environment only."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional: plain environment variables also work
        return
    # Explicit path: never search parent folders, which may hold other projects' secrets.
    load_dotenv(dotenv_path=REPO_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    falkordb_host: str
    falkordb_port: int
    graph_name: str
    openalex_api_key: str
    author_hash_salt: str


def load_settings() -> Settings:
    _load_dotenv()
    return Settings(
        falkordb_host=os.environ.get("FALKORDB_HOST", "127.0.0.1"),
        falkordb_port=int(os.environ.get("FALKORDB_PORT", "6379")),
        graph_name=os.environ.get("FALKORDB_GRAPH", "bedrock"),
        openalex_api_key=os.environ.get("OPENALEX_API_KEY", ""),
        author_hash_salt=os.environ.get("AUTHOR_HASH_SALT", ""),
    )
