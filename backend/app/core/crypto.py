"""Cryptographic and canonical JSON utilities for event integrity (RFC 8785 & SHA-256)."""

import hashlib
import json
from typing import Any

GENESIS_PREV_HASH: str = "0" * 64


def canonicalize_json(data: Any) -> str:
    """Serialize data into canonical JSON according to RFC 8785 (JCS).

    - Lexicographically sort dictionary keys
    - Remove superfluous whitespace between separators (',' and ':')
    - Uniform UTF-8 character encoding with ensure_ascii=False
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hex(data: str | bytes) -> str:
    """Compute the SHA-256 hex digest of a string or byte sequence."""
    if isinstance(data, str):
        payload_bytes = data.encode("utf-8")
    else:
        payload_bytes = data
    return hashlib.sha256(payload_bytes).hexdigest()


def compute_event_hash(prev_hash: str, content: dict[str, Any]) -> str:
    """Compute the immutable hash of an event chained to prev_hash.

    Formula: Hash_n = SHA256(prev_hash || ":" || CanonicalJSON(content_n))
    """
    canonical_content = canonicalize_json(content)
    combined = f"{prev_hash}:{canonical_content}"
    return sha256_hex(combined)
