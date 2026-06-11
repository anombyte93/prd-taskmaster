from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SIGN_KEY_PATH = ROOT / "scripts" / "license" / "sign-key.py"
VECTORS_PATH = ROOT / "tests" / "license" / "test_vectors.json"
SPEC_PATH = ROOT / "docs" / "product" / "LICENSE-KEY-SPEC.md"
TS_SIGN_KEY_PATH = ROOT / "scripts" / "license" / "sign-key.ts"


def load_sign_key():
    assert SIGN_KEY_PATH.exists(), "scripts/license/sign-key.py is required"
    spec = importlib.util.spec_from_file_location("atlas_sign_key", SIGN_KEY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_payload_bytes_are_sorted_compact_json():
    sign_key = load_sign_key()
    payload = {
        "v": 1,
        "sub": "b" * 64,
        "plan": "pro-monthly",
        "iat": 1_717_200_000,
        "lid": "lic_test_001",
        "exp": 1_719_720_000,
    }

    canonical = sign_key.canonical_payload_bytes(payload)

    assert canonical == (
        b'{"exp":1719720000,"iat":1717200000,"lid":"lic_test_001",'
        b'"plan":"pro-monthly","sub":"'
        + b"b" * 64
        + b'","v":1}'
    )
    assert json.loads(canonical.decode("utf-8")) == payload


def test_build_payload_hashes_email_and_preserves_required_fields():
    sign_key = load_sign_key()

    payload = sign_key.build_payload(
        lid="lic_test_001",
        email="buyer@example.com",
        plan="pro-annual",
        iat=1_717_200_000,
        exp=1_719_720_000,
    )

    assert payload == {
        "lid": "lic_test_001",
        "sub": hashlib.sha256(b"buyer@example.com").hexdigest(),
        "plan": "pro-annual",
        "iat": 1_717_200_000,
        "exp": 1_719_720_000,
        "v": 1,
    }


def test_encode_parse_round_trip_uses_atlas_prefix_and_unpadded_base64url():
    sign_key = load_sign_key()
    payload = {
        "lid": "lic_test_001",
        "sub": hashlib.sha256(b"buyer@example.com").hexdigest(),
        "plan": "pro-monthly",
        "iat": 1_717_200_000,
        "exp": 1_719_720_000,
        "v": 1,
    }
    signature = bytes(range(64))

    license_key = sign_key.encode_license_key(payload, signature)
    decoded_payload, decoded_signature = sign_key.decode_license_key(license_key)

    assert re.fullmatch(r"ATLAS-[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", license_key)
    assert "=" not in license_key
    assert decoded_payload == payload
    assert decoded_signature == signature


def test_cli_help_documents_signing_fields():
    assert SIGN_KEY_PATH.exists(), "scripts/license/sign-key.py is required"

    result = subprocess.run(
        [sys.executable, str(SIGN_KEY_PATH), "sign", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    for expected in (
        "--private-key",
        "--lid",
        "--email",
        "--plan",
        "--iat",
        "--exp",
    ):
        assert expected in result.stdout


def test_committed_vectors_verify_expected_verdicts():
    sign_key = load_sign_key()
    assert VECTORS_PATH.exists(), "tests/license/test_vectors.json is required"

    data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

    assert data["format"] == "atlas-license-key-v1"
    assert {case["name"] for case in data["vectors"]} == {
        "valid",
        "expired",
        "tampered-payload",
        "signature-mismatch",
    }
    public_key = bytes.fromhex(data["public_key_hex"])
    for case in data["vectors"]:
        result = sign_key.verify_license_key(case["key"], public_key, now=data["now"])
        assert result["ok"] is case["expected"]["ok"], case["name"]
        assert result["reason"] == case["expected"]["reason"], case["name"]


def test_license_key_spec_mentions_payload_fields_and_interop_rules():
    assert SPEC_PATH.exists(), "docs/product/LICENSE-KEY-SPEC.md is required"

    spec = SPEC_PATH.read_text(encoding="utf-8")
    for required in (
        "lid",
        "sub",
        "plan",
        "iat",
        "exp",
        "v",
        "ATLAS-<base64url(payload)>.<base64url(sig)>",
        "canonical JSON",
        "base64url",
        "14 days",
        "Ed25519",
        "public key",
        "byte-for-byte",
    ):
        assert required in spec


def test_typescript_signer_reproduces_reproducible_vector_keys():
    node = shutil.which("node")
    if node is None:
        import pytest

        pytest.skip("node is unavailable")
    assert TS_SIGN_KEY_PATH.exists(), "scripts/license/sign-key.ts is required"

    data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    for case in data["vectors"]:
        if not case.get("reproducible"):
            continue
        result = subprocess.run(
            [
                node,
                str(TS_SIGN_KEY_PATH),
                "sign-payload",
                "--payload-json",
                json.dumps(case["payload"], sort_keys=True, separators=(",", ":")),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == case["key"], case["name"]


def test_private_key_material_is_ignored_and_not_committed():
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for rule in ("*.key", "*.pem", "license-signing*"):
        assert rule in ignore_text

    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    forbidden = [
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"ATLAS_LICENSE_PRIVATE_KEY_HEX\\s*=\\s*['\"][0-9a-fA-F]{64}['\"]"),
        re.compile(r"private_seed_hex['\"]?\\s*:\\s*['\"][0-9a-fA-F]{64}['\"]"),
    ]

    offenders: list[str] = []
    for relpath in listed.stdout.splitlines():
        path = ROOT / relpath
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in forbidden):
            offenders.append(relpath)

    assert offenders == []
