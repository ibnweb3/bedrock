"""Author-ID pseudonymisation (hackathon rule 6: no personal data in the graph).

Only the keyed hash of an OpenAlex author ID is ever stored or displayed.
Co-authorship structure is preserved because the hash is deterministic per salt.
Names, emails and ORCIDs must never reach this module's callers' output.
"""
from __future__ import annotations

import hashlib
import hmac

MIN_SALT_LEN = 32


def hash_author_id(openalex_author_id: str, salt: str) -> str:
    if len(salt) < MIN_SALT_LEN:
        raise ValueError(
            f"AUTHOR_HASH_SALT must be at least {MIN_SALT_LEN} characters; see .env.example"
        )
    if not openalex_author_id:
        raise ValueError("empty author id")
    digest = hmac.new(salt.encode(), openalex_author_id.encode(), hashlib.sha256).hexdigest()
    return digest[:16]
