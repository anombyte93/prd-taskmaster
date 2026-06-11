#!/usr/bin/env python3
"""Atlas license key signer and verifier.

License keys are encoded as ATLAS-<base64url(payload)>.<base64url(signature)>.
The signature is Ed25519 over the canonical JSON payload bytes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ed25519_ref  # noqa: E402


KEY_PREFIX = "ATLAS-"
PAYLOAD_FIELDS = ("lid", "sub", "plan", "iat", "exp", "v")
PLANS = ("pro-monthly", "pro-annual")
PRIVATE_KEY_ENV = "ATLAS_LICENSE_PRIVATE_KEY_HEX"
VECTOR_NOW = 1_717_200_000
VECTOR_SEED_LABEL = b"atlas-license-test-vector-seed-v1"
VECTOR_MISMATCH_SEED_LABEL = b"atlas-license-test-vector-mismatch-seed-v1"
_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class LicenseKeyError(ValueError):
    """Raised when a license key is malformed or fails structural checks."""


def canonical_payload_bytes(payload: dict[str, Any]) -> bytes:
    """Return sorted-key, compact UTF-8 JSON bytes for a payload."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(value: str) -> bytes:
    if not value or "=" in value or _B64URL_RE.fullmatch(value) is None:
        raise LicenseKeyError("invalid base64url segment")
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except ValueError as exc:
        raise LicenseKeyError("invalid base64url data") from exc


def build_payload(*, lid: str, email: str, plan: str, iat: int, exp: int) -> dict[str, Any]:
    if plan not in PLANS:
        raise LicenseKeyError(f"plan must be one of: {', '.join(PLANS)}")
    return {
        "lid": lid,
        "sub": hashlib.sha256(email.encode("utf-8")).hexdigest(),
        "plan": plan,
        "iat": int(iat),
        "exp": int(exp),
        "v": 1,
    }


def validate_payload(payload: dict[str, Any]) -> None:
    if set(payload) != set(PAYLOAD_FIELDS):
        raise LicenseKeyError("payload fields must be exactly lid, sub, plan, iat, exp, v")
    if not isinstance(payload["lid"], str) or not payload["lid"]:
        raise LicenseKeyError("lid must be a non-empty string")
    if not isinstance(payload["sub"], str) or _HEX64_RE.fullmatch(payload["sub"]) is None:
        raise LicenseKeyError("sub must be a lowercase SHA-256 hex digest")
    if payload["plan"] not in PLANS:
        raise LicenseKeyError(f"plan must be one of: {', '.join(PLANS)}")
    if not isinstance(payload["iat"], int) or not isinstance(payload["exp"], int):
        raise LicenseKeyError("iat and exp must be integer Unix timestamps")
    if payload["exp"] < payload["iat"]:
        raise LicenseKeyError("exp must be greater than or equal to iat")
    if payload["v"] != 1:
        raise LicenseKeyError("v must be 1")


def encode_license_key(payload: dict[str, Any], signature: bytes) -> str:
    validate_payload(payload)
    if len(signature) != 64:
        raise LicenseKeyError("Ed25519 signature must be 64 bytes")
    return f"{KEY_PREFIX}{b64url_encode(canonical_payload_bytes(payload))}.{b64url_encode(signature)}"


def decode_license_key(license_key: str) -> tuple[dict[str, Any], bytes]:
    if not license_key.startswith(KEY_PREFIX):
        raise LicenseKeyError("license key must start with ATLAS-")
    body = license_key[len(KEY_PREFIX) :]
    if body.count(".") != 1:
        raise LicenseKeyError("license key must contain one payload/signature separator")
    payload_segment, signature_segment = body.split(".", 1)
    payload_bytes = b64url_decode(payload_segment)
    signature = b64url_decode(signature_segment)
    if len(signature) != 64:
        raise LicenseKeyError("Ed25519 signature must be 64 bytes")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseKeyError("payload must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise LicenseKeyError("payload must be a JSON object")
    validate_payload(payload)
    if payload_bytes != canonical_payload_bytes(payload):
        raise LicenseKeyError("payload JSON is not canonical")
    return payload, signature


def sign_payload(payload: dict[str, Any], private_seed: bytes) -> str:
    validate_payload(payload)
    signature = ed25519_ref.sign(private_seed, canonical_payload_bytes(payload))
    return encode_license_key(payload, signature)


def verify_license_key(
    license_key: str,
    public_key: bytes,
    *,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        payload, signature = decode_license_key(license_key)
    except LicenseKeyError as exc:
        return {"ok": False, "reason": str(exc), "payload": None}

    if not ed25519_ref.verify(public_key, canonical_payload_bytes(payload), signature):
        return {"ok": False, "reason": "signature mismatch", "payload": payload}
    if now is not None and payload["exp"] < int(now):
        return {"ok": False, "reason": "expired", "payload": payload}
    return {"ok": True, "reason": "valid", "payload": payload}


def deterministic_vector_seed(label: bytes = VECTOR_SEED_LABEL) -> bytes:
    """Return a deterministic non-secret seed for reproducible test vectors."""
    return hashlib.sha256(label).digest()


def _is_under_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
        return True
    except ValueError:
        return False


def _read_private_seed(path: Path | None) -> bytes:
    if path is None:
        value = os.environ.get(PRIVATE_KEY_ENV)
        if not value:
            raise LicenseKeyError(f"provide --private-key or set {PRIVATE_KEY_ENV}")
        return bytes.fromhex(value)
    if _is_under_repo(path):
        raise LicenseKeyError("private-key path must be outside the repository")
    text = path.read_text(encoding="utf-8").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        seed_hex = text
    else:
        seed_hex = data.get("private_seed_hex", "")
    seed = bytes.fromhex(seed_hex)
    if len(seed) != 32:
        raise LicenseKeyError("private key seed must be 32 bytes")
    return seed


def _write_keypair(path: Path, *, force: bool) -> bytes:
    if _is_under_repo(path):
        raise LicenseKeyError("private-key path must be outside the repository")
    if path.exists() and not force:
        raise LicenseKeyError(f"{path} already exists; pass --force to overwrite")
    private_seed, public_key = ed25519_ref.generate_keypair()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "kty": "Ed25519",
                "private_seed_hex": private_seed.hex(),
                "public_key_hex": public_key.hex(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return public_key


def generate_vectors() -> dict[str, Any]:
    private_seed = deterministic_vector_seed()
    mismatch_seed = deterministic_vector_seed(VECTOR_MISMATCH_SEED_LABEL)
    public_key = ed25519_ref.secret_to_public(private_seed)

    valid_payload = build_payload(
        lid="lic_vec_valid",
        email="valid@example.com",
        plan="pro-monthly",
        iat=VECTOR_NOW - 3600,
        exp=VECTOR_NOW + 86400,
    )
    expired_payload = build_payload(
        lid="lic_vec_expired",
        email="expired@example.com",
        plan="pro-annual",
        iat=VECTOR_NOW - 172800,
        exp=VECTOR_NOW - 86400,
    )

    valid_key = sign_payload(valid_payload, private_seed)
    expired_key = sign_payload(expired_payload, private_seed)

    tampered_payload = dict(valid_payload)
    tampered_payload["lid"] = "lic_vec_tampered"
    _original_payload, valid_signature = decode_license_key(valid_key)
    tampered_key = encode_license_key(tampered_payload, valid_signature)

    mismatch_key = sign_payload(valid_payload, mismatch_seed)

    return {
        "format": "atlas-license-key-v1",
        "now": VECTOR_NOW,
        "public_key_hex": public_key.hex(),
        "vectors": [
            {
                "name": "valid",
                "payload": valid_payload,
                "key": valid_key,
                "expected": {"ok": True, "reason": "valid"},
                "reproducible": True,
            },
            {
                "name": "expired",
                "payload": expired_payload,
                "key": expired_key,
                "expected": {"ok": False, "reason": "expired"},
                "reproducible": True,
            },
            {
                "name": "tampered-payload",
                "payload": tampered_payload,
                "key": tampered_key,
                "expected": {"ok": False, "reason": "signature mismatch"},
                "reproducible": False,
            },
            {
                "name": "signature-mismatch",
                "payload": valid_payload,
                "key": mismatch_key,
                "expected": {"ok": False, "reason": "signature mismatch"},
                "reproducible": False,
            },
        ],
    }


def _cmd_keygen(args: argparse.Namespace) -> int:
    public_key = _write_keypair(args.private_key, force=args.force)
    print(public_key.hex())
    return 0


def _cmd_sign(args: argparse.Namespace) -> int:
    private_seed = _read_private_seed(args.private_key)
    payload = build_payload(
        lid=args.lid,
        email=args.email,
        plan=args.plan,
        iat=args.iat,
        exp=args.exp,
    )
    print(sign_payload(payload, private_seed))
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    public_key = bytes.fromhex(args.public_key)
    result = verify_license_key(args.key, public_key, now=args.now)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


def _cmd_vectors(args: argparse.Namespace) -> int:
    data = generate_vectors()
    rendered = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sign and verify Atlas license keys.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    keygen = subcommands.add_parser("keygen", help="generate a local Ed25519 keypair")
    keygen.add_argument(
        "--private-key",
        required=True,
        type=Path,
        help="path outside the repo where the private key JSON will be written",
    )
    keygen.add_argument("--force", action="store_true", help="overwrite an existing private-key file")
    keygen.set_defaults(func=_cmd_keygen)

    sign = subcommands.add_parser("sign", help="sign a license payload")
    sign.add_argument(
        "--private-key",
        type=Path,
        help=f"path outside the repo containing the private seed JSON; defaults to {PRIVATE_KEY_ENV}",
    )
    sign.add_argument("--lid", required=True, help="license id to embed in the payload")
    sign.add_argument("--email", required=True, help="subscriber email to SHA-256 hash into sub")
    sign.add_argument("--plan", required=True, choices=PLANS, help="licensed plan")
    sign.add_argument("--iat", required=True, type=int, help="issued-at Unix timestamp")
    sign.add_argument("--exp", required=True, type=int, help="expiry Unix timestamp including 14-day grace")
    sign.set_defaults(func=_cmd_sign)

    verify = subcommands.add_parser("verify", help="verify an Atlas license key")
    verify.add_argument("--public-key", required=True, help="Ed25519 public key as 64 hex characters")
    verify.add_argument("--key", required=True, help="ATLAS license key string to verify")
    verify.add_argument("--now", type=int, help="Unix timestamp for expiry checks")
    verify.set_defaults(func=_cmd_verify)

    vectors = subcommands.add_parser("vectors", help="generate deterministic license test vectors")
    vectors.add_argument("--out", type=Path, help="optional output path for test_vectors.json")
    vectors.set_defaults(func=_cmd_vectors)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, LicenseKeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
