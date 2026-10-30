"""VAPID key generation for Web Push (`nadjet-api gen-vapid`)."""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate_vapid() -> tuple[str, str]:
    """``(private, public)``: the private key as a base64url scalar, the public key as the
    uncompressed point the browser passes as ``applicationServerKey``."""
    vapid = Vapid()
    vapid.generate_keys()
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64url(private), _b64url(public)
