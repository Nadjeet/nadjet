"""3-character base32 short codes for SMS (unique among open incidents). Deterministic, pure."""

import hashlib
import uuid

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
LENGTH = 3
MAX_ATTEMPTS = 256


def short_code(incident_id: uuid.UUID, attempt: int = 0) -> str:
    """Code for ``incident_id``; a higher ``attempt`` yields a different code (collisions)."""
    digest = hashlib.sha256(incident_id.bytes + attempt.to_bytes(4, "big")).digest()
    value = int.from_bytes(digest[:4], "big")
    chars = []
    for _ in range(LENGTH):
        value, index = divmod(value, len(ALPHABET))
        chars.append(ALPHABET[index])
    return "".join(chars)


def pick_short_code(incident_id: uuid.UUID, taken: set[str]) -> str:
    """First free code for ``incident_id`` given the codes of open incidents."""
    for attempt in range(MAX_ATTEMPTS):
        code = short_code(incident_id, attempt)
        if code not in taken:
            return code
    raise RuntimeError("no free short code")
