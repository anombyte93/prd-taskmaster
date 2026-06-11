"""Tests for the license-activate CLI command."""

import json
from argparse import Namespace
from pathlib import Path

import pytest

from prd_taskmaster.cli import DISPATCH, build_parser
from prd_taskmaster import license
from prd_taskmaster.license_activate import cmd_license_activate


REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS = json.loads((REPO_ROOT / "tests" / "license" / "test_vectors.json").read_text())
GRACE_SECONDS = 14 * 24 * 60 * 60


class TestLicenseActivateParser:
    def test_parser_accepts_license_activate_key(self):
        parser = build_parser()

        args = parser.parse_args(["license-activate", "ATLAS-example.signature"])

        assert args.command == "license-activate"
        assert args.license_key == "ATLAS-example.signature"
        assert args.json is False

    def test_parser_accepts_json_escape_hatch(self):
        parser = build_parser()

        args = parser.parse_args(["license-activate", "--json", "ATLAS-example.signature"])

        assert args.command == "license-activate"
        assert args.license_key == "ATLAS-example.signature"
        assert args.json is True

    def test_parser_requires_license_key(self):
        parser = build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["license-activate"])

    def test_dispatch_registers_license_activate_handler(self):
        assert "license-activate" in DISPATCH
        assert DISPATCH["license-activate"].__name__ == "cmd_license_activate"


class TestLicenseActivateCommand:
    def test_valid_key_persists_and_renders_status_block(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = VECTORS["vectors"][0]
        now = vector["payload"]["exp"] - GRACE_SECONDS
        monkeypatch.setattr(license._time, "time", lambda: now)

        cmd_license_activate(Namespace(license_key=vector["key"], json=False))

        out = capsys.readouterr().out
        assert "┌─ atlas ── license-activate ─┐" in out
        assert "What happened: Atlas Pro license activated." in out
        assert "Evidence:" in out
        assert "plan pro-monthly" in out
        assert "status active" in out
        assert "Next: run `prd-taskmaster detect-capabilities` to confirm premium tier." in out
        assert not out.lstrip().startswith("{")
        assert license.load_license()["key"] == vector["key"]

    def test_grace_key_json_escape_hatch(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        vector = VECTORS["vectors"][0]
        now = vector["payload"]["exp"] - (7 * 24 * 60 * 60)
        monkeypatch.setattr(license._time, "time", lambda: now)

        with pytest.raises(SystemExit) as exc:
            cmd_license_activate(Namespace(license_key=vector["key"], json=True))

        assert exc.value.code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["ok"] is True
        assert data["status"] == "grace"
        assert data["days_remaining"] == 7

    def test_invalid_key_renders_status_block_and_exits_nonzero(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(license, "PUBLIC_KEY", bytes.fromhex(VECTORS["public_key_hex"]))
        bad = next(v for v in VECTORS["vectors"] if v["name"] == "signature-mismatch")

        with pytest.raises(SystemExit) as exc:
            cmd_license_activate(Namespace(license_key=bad["key"], json=False))

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "┌─ atlas ── license-activate ─┐" in out
        assert "What happened: Atlas Pro license was not activated." in out
        assert "status invalid" in out
        assert "signature mismatch" in out
        assert not (tmp_path / ".atlas-ai" / "license.json").exists()
