"""Tests for offline Atlas license parsing, verification, and persistence."""

import base64
import ast
import json
import os
from pathlib import Path

from prd_taskmaster import _ed25519
from prd_taskmaster import license


REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((REPO_ROOT / "tests" / "license" / "test_vectors.json").read_text())
GRACE_SECONDS = 14 * 24 * 60 * 60


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class TestEd25519Verify:
    def test_accepts_rfc8032_section_7_1_vector_1(self):
        public = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        message = b""
        signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        )

        assert _ed25519.verify(public, message, signature) is True

    def test_rejects_tampered_rfc8032_signature(self):
        public = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        signature = bytearray.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        )
        signature[0] ^= 1

        assert _ed25519.verify(public, b"", bytes(signature)) is False

    def test_rejects_malformed_lengths(self):
        public = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        )

        assert _ed25519.verify(public[:-1], b"", signature) is False
        assert _ed25519.verify(public, b"", signature[:-1]) is False


class TestParseKey:
    def test_valid_key_returns_payload_bytes_and_signature(self):
        vector = VECTORS["vectors"][0]

        parsed = license.parse_key(vector["key"])

        assert parsed["ok"] is True
        assert parsed["payload"] == vector["payload"]
        assert parsed["payload_bytes"] == json.dumps(
            vector["payload"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        assert isinstance(parsed["signature"], bytes)
        assert len(parsed["signature"]) == 64

    def test_malformed_keys_return_invalid_result(self):
        payload = {
            "exp": 1717286400,
            "iat": 1717196400,
            "lid": "lic_bad",
            "plan": "pro-monthly",
            "sub": "0" * 64,
            "v": 1,
        }
        payload_segment = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        signature_segment = _b64url(b"x" * 64)
        cases = [
            "BAD-" + payload_segment + "." + signature_segment,
            "ATLAS-not*base64." + signature_segment,
            "ATLAS-" + _b64url(b"not json") + "." + signature_segment,
            "ATLAS-" + _b64url(json.dumps({"v": 1}).encode()) + "." + signature_segment,
            "ATLAS-" + _b64url(json.dumps({**payload, "v": 2}, sort_keys=True, separators=(",", ":")).encode()) + "." + signature_segment,
        ]

        for key in cases:
            parsed = license.parse_key(key)
            assert parsed["ok"] is False
            assert parsed["status"] == "invalid"
            assert parsed["detail"]
            assert parsed["payload"] is None or isinstance(parsed["payload"], dict)


class TestSignatureVerification:
    def test_fixture_signatures_verify_against_fixture_public_key(self, monkeypatch):
        public_key = bytes.fromhex(VECTORS["public_key_hex"])
        monkeypatch.setattr(license, "PUBLIC_KEY", public_key)

        expected_by_name = {
            "valid": True,
            "expired": True,
            "tampered-payload": False,
            "signature-mismatch": False,
        }

        for vector in VECTORS["vectors"]:
            parsed = license.parse_key(vector["key"])
            assert parsed["ok"] is True
            assert license.verify_signature(
                parsed["payload_bytes"],
                parsed["signature"],
                license.PUBLIC_KEY,
            ) is expected_by_name[vector["name"]]

    def test_verify_signature_returns_false_for_wrong_public_key(self):
        parsed = license.parse_key(VECTORS["vectors"][0]["key"])

        assert license.verify_signature(
            parsed["payload_bytes"],
            parsed["signature"],
            b"\x00" * 32,
        ) is False


class TestLicenseStatus:
    def test_active_before_grace_window(self, monkeypatch):
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = VECTORS["vectors"][0]
        now = vector["payload"]["exp"] - GRACE_SECONDS

        status = license.get_status(vector["key"], now=now)

        assert status["status"] == "active"
        assert status["days_remaining"] is None
        assert status["detail"] == "license active"

    def test_grace_after_period_end_and_before_expiry(self, monkeypatch):
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = VECTORS["vectors"][0]
        now = vector["payload"]["exp"] - (7 * 24 * 60 * 60)

        status = license.get_status(vector["key"], now=now)

        assert status["status"] == "grace"
        assert status["days_remaining"] == 7
        assert "grace" in status["detail"]

    def test_exp_is_end_of_grace_not_start_of_second_grace(self, monkeypatch):
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = VECTORS["vectors"][0]

        status = license.get_status(vector["key"], now=vector["payload"]["exp"] + 1)

        assert status["status"] == "expired"
        assert status["days_remaining"] == 0
        assert "expired" in status["detail"]

    def test_invalid_signature_returns_invalid_status(self, monkeypatch):
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = next(v for v in VECTORS["vectors"] if v["name"] == "signature-mismatch")

        status = license.get_status(vector["key"], now=VECTORS["now"])

        assert status["status"] == "invalid"
        assert status["days_remaining"] is None
        assert "signature" in status["detail"]

    def test_malformed_key_returns_invalid_status(self):
        status = license.get_status("not-a-license-key", now=VECTORS["now"])

        assert status["status"] == "invalid"
        assert status["days_remaining"] is None
        assert status["detail"]


class TestLicensePersistence:
    def test_save_license_creates_private_license_file_and_loads_it(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = VECTORS["vectors"][0]
        now = vector["payload"]["exp"] - GRACE_SECONDS

        result = license.save_license(vector["key"], now=now)

        assert result["ok"] is True
        license_dir = tmp_path / ".atlas-ai"
        license_file = license_dir / "license.json"
        assert license_file.is_file()
        if os.name == "posix":
            assert (license_dir.stat().st_mode & 0o777) == 0o700
            assert (license_file.stat().st_mode & 0o777) == 0o600

        loaded = license.load_license()
        assert loaded is not None
        assert loaded["ok"] is True
        assert loaded["payload"] == vector["payload"]
        assert loaded["key"] == vector["key"]

    def test_save_license_rejects_signature_mismatch(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        bad = next(v for v in VECTORS["vectors"] if v["name"] == "signature-mismatch")

        result = license.save_license(bad["key"], now=VECTORS["now"])

        assert result["ok"] is False
        assert result["status"] == "invalid"
        assert not (tmp_path / ".atlas-ai" / "license.json").exists()

    def test_load_license_returns_none_for_missing_or_corrupt_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        assert license.load_license() is None

        license_dir = tmp_path / ".atlas-ai"
        license_dir.mkdir()
        (license_dir / "license.json").write_text("{not json")

        assert license.load_license() is None


class TestLicenseModuleSurface:
    def test_license_modules_import_only_stdlib_and_package_modules(self):
        allowed = {
            "base64",
            "hashlib",
            "json",
            "math",
            "os",
            "pathlib",
            "re",
            "time",
            "typing",
            "prd_taskmaster",
        }
        for relpath in ("prd_taskmaster/license.py", "prd_taskmaster/_ed25519.py"):
            tree = ast.parse((REPO_ROOT / relpath).read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])

            assert imported <= allowed

    def test_license_public_api_surface_is_explicit(self):
        public = {name for name in vars(license) if not name.startswith("_")}

        assert public == {
            "PUBLIC_KEY",
            "parse_key",
            "verify_signature",
            "get_status",
            "save_license",
            "load_license",
        }
