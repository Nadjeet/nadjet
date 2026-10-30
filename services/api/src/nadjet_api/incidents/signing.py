"""Ed25519 signing of incident chain heads (FR-SEC-003, TD-16)."""

import binascii

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


def generate_seed_hex() -> str:
    return SigningKey.generate().encode().hex()


class ChainSigner:
    def __init__(self, seed_hex: str) -> None:
        self._key = SigningKey(bytes.fromhex(seed_hex))
        self._verify: VerifyKey = self._key.verify_key

    @property
    def public_key_hex(self) -> str:
        return self._verify.encode().hex()

    def sign(self, head_hash: str) -> str:
        return self._key.sign(head_hash.encode()).signature.hex()

    def verify(self, head_hash: str, signature: str | None) -> bool:
        if not signature:
            return False
        try:
            self._verify.verify(head_hash.encode(), bytes.fromhex(signature))
        except (BadSignatureError, binascii.Error, ValueError):
            return False
        return True
