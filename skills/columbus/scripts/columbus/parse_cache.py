"""Private, lossless parse-fact storage; graph responses remain ordinary JSON."""
from __future__ import annotations

import json
import zlib


MAGIC = b"columbus.parse\x00\x01"
MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024


def encode_parse_cache(facts: dict) -> bytes | str:
    """Compress one file's facts, retaining legacy JSON for unusually large facts."""
    serialized = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    raw = serialized.encode("utf-8")
    if len(raw) > MAX_DECOMPRESSED_BYTES:
        # The expansion bound must not reject previously supported source files.
        return serialized
    return MAGIC + zlib.compress(raw, level=3)


def decode_parse_cache(value: str | bytes) -> dict:
    """Read legacy JSON or a versioned blob, rejecting corrupt/oversized streams."""
    if isinstance(value, bytes):
        if not value.startswith(MAGIC):
            raise ValueError("Unsupported parse cache encoding; rebuild the index")
        inflater = zlib.decompressobj()
        try:
            raw = inflater.decompress(value[len(MAGIC):], MAX_DECOMPRESSED_BYTES + 1)
        except zlib.error as exc:
            raise ValueError("Corrupt parse cache stream; rebuild the index") from exc
        if len(raw) > MAX_DECOMPRESSED_BYTES:
            raise ValueError("Compressed parse cache exceeds expansion limit; rebuild the index")
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError("Incomplete or trailing parse cache stream; rebuild the index")
        value = raw
    try:
        facts = json.loads(value)
    except (ValueError, UnicodeError, RecursionError, TypeError) as exc:
        raise ValueError("Invalid parse cache JSON; rebuild the index") from exc
    if not isinstance(facts, dict):
        raise ValueError("Invalid parse cache object; rebuild the index")
    return facts
