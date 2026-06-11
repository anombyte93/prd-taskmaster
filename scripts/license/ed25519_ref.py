"""Small stdlib-only Ed25519 reference implementation.

This module implements PureEdDSA Ed25519 from RFC 8032 for license-key test
fixtures and local signing tools. It is intentionally minimal: private keys are
32-byte seeds, public keys are 32 bytes, and signatures are 64 bytes.
"""

from __future__ import annotations

import hashlib
import os


P = 2**255 - 19
Q = 2**252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, P - 2, P)) % P
SQRT_M1 = pow(2, (P - 1) // 4, P)


def _inv(x: int) -> int:
    return pow(x, P - 2, P)


def _recover_x(y: int, sign: int) -> int | None:
    if y >= P:
        return None
    x2 = ((y * y - 1) * _inv(D * y * y + 1)) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = (x * SQRT_M1) % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


BASE_Y = (4 * _inv(5)) % P
BASE_X = _recover_x(BASE_Y, 0)
if BASE_X is None:  # pragma: no cover - impossible for the Ed25519 base point.
    raise RuntimeError("failed to recover Ed25519 base point")
BASE = (BASE_X, BASE_Y, 1, (BASE_X * BASE_Y) % P)
IDENTITY = (0, 1, 1, 0)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _sha512_modq(data: bytes) -> int:
    return int.from_bytes(_sha512(data), "little") % Q


def _point_add(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % P
    b = ((y1 + x1) * (y2 + x2)) % P
    c = (2 * D * t1 * t2) % P
    d = (2 * z1 * z2) % P
    e = b - a
    f = d - c
    g = d + c
    h = b + a
    return ((e * f) % P, (g * h) % P, (f * g) % P, (e * h) % P)


def _point_mul(scalar: int, point: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    result = IDENTITY
    addend = point
    while scalar:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _point_equal(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> bool:
    return (
        (p1[0] * p2[2] - p2[0] * p1[2]) % P == 0
        and (p1[1] * p2[2] - p2[1] * p1[2]) % P == 0
    )


def _point_compress(point: tuple[int, int, int, int]) -> bytes:
    z_inv = _inv(point[2])
    x = (point[0] * z_inv) % P
    y = (point[1] * z_inv) % P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _point_decompress(encoded: bytes) -> tuple[int, int, int, int] | None:
    if len(encoded) != 32:
        return None
    y = int.from_bytes(encoded, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, (x * y) % P)


def _secret_expand(secret: bytes) -> tuple[int, bytes]:
    if len(secret) != 32:
        raise ValueError("Ed25519 private seed must be 32 bytes")
    digest = bytearray(_sha512(secret))
    digest[0] &= 248
    digest[31] &= 63
    digest[31] |= 64
    return int.from_bytes(digest[:32], "little"), bytes(digest[32:])


def secret_to_public(secret: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key from a 32-byte private seed."""
    scalar, _prefix = _secret_expand(secret)
    return _point_compress(_point_mul(scalar, BASE))


def sign(secret: bytes, message: bytes) -> bytes:
    """Return a deterministic 64-byte PureEdDSA Ed25519 signature."""
    scalar, prefix = _secret_expand(secret)
    public = _point_compress(_point_mul(scalar, BASE))
    r = _sha512_modq(prefix + message)
    encoded_r = _point_compress(_point_mul(r, BASE))
    h = _sha512_modq(encoded_r + public + message)
    s = (r + h * scalar) % Q
    return encoded_r + int.to_bytes(s, 32, "little")


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """Return True when signature is valid for message under public."""
    if len(public) != 32 or len(signature) != 64:
        return False
    point_a = _point_decompress(public)
    if point_a is None:
        return False
    encoded_r = signature[:32]
    point_r = _point_decompress(encoded_r)
    if point_r is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= Q:
        return False
    h = _sha512_modq(encoded_r + public + message)
    return _point_equal(_point_mul(s, BASE), _point_add(point_r, _point_mul(h, point_a)))


def generate_private_key() -> bytes:
    """Generate a 32-byte Ed25519 private seed."""
    return os.urandom(32)


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate and return (private_seed, public_key)."""
    private_seed = generate_private_key()
    return private_seed, secret_to_public(private_seed)
