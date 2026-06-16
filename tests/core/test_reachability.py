"""Tests for prd_taskmaster.reachability — orphan-module detection.

Each test that exercises WIRED vs ORPHAN builds a genuine tiny git repo with
real commits and real files so that the grep logic is executed against actual
source content.  No mocking of the load-bearing grep/git calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from prd_taskmaster.reachability import (
    find_importers,
    language_for_repo,
    new_modules_for_task,
    reachability_verdict,
    sweep_task,
)


# ─── Git repo fixture helper ──────────────────────────────────────────────────

def _git(repo: Path, *args: str) -> str:
    """Run a git command in *repo* and return stdout (stripped)."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    """Create a bare-minimum git repo in *tmp_path*."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit_all(repo: Path, message: str) -> str:
    """Stage everything under *repo* and commit.  Returns the commit SHA."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _make_py_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Build a two-commit Python repo.

    Commit 1 (start): pyproject.toml + pkg/__init__.py
    Commit 2 (head):  pkg/foo.py + tests/test_foo.py  (the new module + its test)

    Returns (repo, start_sha, head_sha).
    """
    repo = _init_repo(tmp_path)
    (repo / "pyproject.toml").write_text("[project]\nname = 'mypkg'\n")
    pkg = repo / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    start = _commit_all(repo, "initial")

    # Add the new module and its test.
    (pkg / "foo.py").write_text("def hello():\n    return 'hello'\n")
    (tests_dir / "test_foo.py").write_text(
        "from pkg.foo import hello\ndef test_hello():\n    assert hello() == 'hello'\n"
    )
    head = _commit_all(repo, "add foo")
    return repo, start, head


# ─── 1. language_for_repo ─────────────────────────────────────────────────────

class TestLanguageForRepo:
    def test_pyproject_toml_detected_as_py(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname='x'\n")
        assert language_for_repo(repo) == "py"

    def test_setup_py_detected_as_py(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "setup.py").write_text("from setuptools import setup; setup()\n")
        assert language_for_repo(repo) == "py"

    def test_package_json_plus_tsconfig_detected_as_ts(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "package.json").write_text("{}")
        (repo / "tsconfig.json").write_text("{}")
        assert language_for_repo(repo) == "ts"

    def test_package_json_alone_detected_as_js(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "package.json").write_text("{}")
        assert language_for_repo(repo) == "js"

    def test_go_mod_detected_as_go(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "go.mod").write_text("module example.com/m\ngo 1.21\n")
        assert language_for_repo(repo) == "go"

    def test_bare_directory_is_unknown(self, tmp_path):
        repo = tmp_path / "proj"
        repo.mkdir()
        assert language_for_repo(repo) == "unknown"

    def test_pyproject_takes_priority_over_package_json(self, tmp_path):
        """If both pyproject.toml and package.json exist, Python wins."""
        repo = tmp_path / "proj"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\n")
        (repo / "package.json").write_text("{}")
        assert language_for_repo(repo) == "py"


# ─── 2. new_modules_for_task ──────────────────────────────────────────────────

class TestNewModulesForTask:
    def test_returns_source_module_and_excludes_test(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        modules = new_modules_for_task(repo, start, head)
        names = [m.name for m in modules]
        assert "foo.py" in names, "source module must be included"
        assert "test_foo.py" not in names, "test file must be excluded"

    def test_excludes_init_py(self, tmp_path):
        """__init__.py added in a commit should not appear as a 'new module'."""
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        start = _commit_all(repo, "init")
        pkg = repo / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("x = 1\n")
        head = _commit_all(repo, "add pkg")
        modules = new_modules_for_task(repo, start, head)
        names = [m.name for m in modules]
        assert "__init__.py" not in names
        assert "core.py" in names

    def test_excludes_main_py(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        start = _commit_all(repo, "init")
        (repo / "__main__.py").write_text("import sys\n")
        (repo / "util.py").write_text("def f(): pass\n")
        head = _commit_all(repo, "add files")
        modules = new_modules_for_task(repo, start, head)
        names = [m.name for m in modules]
        assert "__main__.py" not in names
        assert "util.py" in names

    def test_empty_range_returns_empty_list(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        # Same commit as start and head — no changes.
        modules = new_modules_for_task(repo, head, head)
        assert modules == []

    def test_excludes_files_under_tests_dir(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        start = _commit_all(repo, "init")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "helper.py").write_text("# helper\n")
        (repo / "real_module.py").write_text("x = 1\n")
        head = _commit_all(repo, "add")
        modules = new_modules_for_task(repo, start, head)
        paths = [m.as_posix() for m in modules]
        assert not any("tests/" in p for p in paths), "tests/ subtree must be excluded"
        assert "real_module.py" in paths


# ─── 3. WIRED: importer exists ────────────────────────────────────────────────

class TestReachabilityWired:
    """pkg/foo.py is imported by pkg/app.py — must be WIRED."""

    def test_wired_when_importer_exists(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        start = _commit_all(repo, "init")

        # New module.
        (pkg / "foo.py").write_text("def hello():\n    return 'hello'\n")
        # An importer — genuinely imports the new module.
        (pkg / "app.py").write_text("from pkg.foo import hello\n\nprint(hello())\n")
        # Co-located test (must NOT make it wired on its own).
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_foo.py").write_text("from pkg.foo import hello\n")
        head = _commit_all(repo, "add foo + app")

        verdict = reachability_verdict(repo, Path("pkg/foo.py"), "py")
        assert verdict["verdict"] == "WIRED"
        assert any("app.py" in imp for imp in verdict["importers"])

    def test_wired_importer_paths_are_repo_relative(self, tmp_path):
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "bar.py").write_text("VALUE = 42\n")
        (pkg / "main.py").write_text("from pkg.bar import VALUE\n")
        _commit_all(repo, "add")

        verdict = reachability_verdict(repo, Path("pkg/bar.py"), "py")
        assert verdict["verdict"] == "WIRED"
        # Paths should be relative (no leading slash or absolute prefix).
        for imp in verdict["importers"]:
            assert not imp.startswith("/"), f"importer path should be relative, got: {imp}"


# ─── 4. ORPHAN: no importers ──────────────────────────────────────────────────

class TestReachabilityOrphan:
    """pkg/foo.py exists with only a test importing it — must be ORPHAN."""

    def test_orphan_when_only_colocated_test_imports(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        # tests/test_foo.py imports pkg.foo, but it's excluded from importers.
        # No other file imports pkg.foo.
        verdict = reachability_verdict(repo, Path("pkg/foo.py"), "py")
        assert verdict["verdict"] == "ORPHAN"
        assert verdict["importers"] == []

    def test_orphan_verdict_fields(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(repo, Path("pkg/foo.py"), "py")
        assert verdict["module"] == "pkg/foo.py"
        assert verdict["lang"] == "py"
        assert verdict["reachable_via"] is None
        assert verdict["exempt_reason"] is None

    def test_orphan_vs_wired_is_not_tautological(self, tmp_path):
        """Confirm the grep genuinely distinguishes ORPHAN from WIRED by adding/removing an importer."""
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "util.py").write_text("def compute(): return 99\n")
        start = _commit_all(repo, "init")

        # --- ORPHAN state: only test imports util ---
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_util.py").write_text("from pkg.util import compute\n")
        _commit_all(repo, "add test only")
        v_orphan = reachability_verdict(repo, Path("pkg/util.py"), "py")
        assert v_orphan["verdict"] == "ORPHAN", "Must be ORPHAN when only test imports"

        # --- WIRED state: add a real importer ---
        (pkg / "service.py").write_text("from pkg.util import compute\nresult = compute()\n")
        _commit_all(repo, "add service importer")
        v_wired = reachability_verdict(repo, Path("pkg/util.py"), "py")
        assert v_wired["verdict"] == "WIRED", "Must be WIRED once a real importer exists"


# ─── 5. EXEMPT (scheme) ───────────────────────────────────────────────────────

class TestReachabilityExempt:
    def test_cli_scheme_exempts_orphan(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        # pkg/foo.py has no real importer, but declared as cli-reachable.
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="cli:foo"
        )
        assert verdict["verdict"] == "EXEMPT"
        assert verdict["exempt_reason"] == "cli"

    def test_route_scheme_exempts(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="route:/api/v1/foo"
        )
        assert verdict["verdict"] == "EXEMPT"
        assert verdict["exempt_reason"] == "route"

    def test_tool_scheme_exempts(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="tool:my_tool"
        )
        assert verdict["verdict"] == "EXEMPT"
        assert verdict["exempt_reason"] == "tool"

    def test_hook_scheme_exempts(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="hook:post_save"
        )
        assert verdict["verdict"] == "EXEMPT"
        assert verdict["exempt_reason"] == "hook"

    def test_plugin_scheme_exempts(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="plugin:my_plugin"
        )
        assert verdict["verdict"] == "EXEMPT"
        assert verdict["exempt_reason"] == "plugin"

    def test_dynamic_scheme_exempts(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="dynamic:importlib"
        )
        assert verdict["verdict"] == "EXEMPT"
        assert verdict["exempt_reason"] == "dynamic"

    def test_no_scheme_does_not_exempt(self, tmp_path):
        """A free-form reachable_via string without a known scheme is NOT exempt."""
        repo, start, head = _make_py_repo(tmp_path)
        verdict = reachability_verdict(
            repo, Path("pkg/foo.py"), "py", reachable_via="just a comment"
        )
        # Should still be ORPHAN (no real importers) — no scheme match.
        assert verdict["verdict"] == "ORPHAN"
        assert verdict["exempt_reason"] is None


# ─── 6. sweep_task ────────────────────────────────────────────────────────────

class TestSweepTask:
    def test_domain_model_tier_is_tier_exempt(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "domain-model"}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "EXEMPT"
        assert result["reason"] == "tier-exempt"
        assert result["modules"] == []

    def test_spike_tier_is_tier_exempt(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "spike"}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "EXEMPT"
        assert result["reason"] == "tier-exempt"

    def test_phase_config_tier_takes_priority(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "wired", "phaseConfig": {"tier": "domain-model"}}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "EXEMPT"
        assert result["reason"] == "tier-exempt"

    def test_entrypoint_task_is_exempt(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "wired", "entrypoint": True}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "EXEMPT"
        assert result["reason"] == "entrypoint"

    def test_wired_tier_with_orphan_module_returns_orphan(self, tmp_path):
        """A 'wired' tier task whose new module has no importer must be ORPHAN."""
        repo, start, head = _make_py_repo(tmp_path)
        # pkg/foo.py was added in head but has no importer (only tests/test_foo.py).
        task = {"tier": "wired"}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "ORPHAN"
        # There should be exactly one module entry.
        assert len(result["modules"]) == 1
        assert result["modules"][0]["verdict"] == "ORPHAN"

    def test_live_tier_with_orphan_module_returns_orphan(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "live"}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "ORPHAN"

    def test_wired_tier_with_wired_module_returns_wired(self, tmp_path):
        """A 'wired' tier task where the new module is imported by an EXISTING file is WIRED.

        The importer (app.py) must exist in the start commit so it is not listed as
        a 'new module' — only feature.py is new.  This ensures the importer is a
        genuine pre-existing wire, not itself an orphan added in the same sweep window.
        """
        repo = _init_repo(tmp_path)
        (repo / "pyproject.toml").write_text("[project]\n")
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        # app.py exists BEFORE the task window — it's the importer, not a new module.
        (pkg / "app.py").write_text("# placeholder — will be updated to import feature\n")
        start = _commit_all(repo, "init")

        # Add the new module.  Update app.py to import it (but app.py is not new — it
        # was already committed, so it won't appear in new_modules_for_task).
        (pkg / "feature.py").write_text("def run(): pass\n")
        (pkg / "app.py").write_text("from pkg.feature import run\nrun()\n")
        head = _commit_all(repo, "add feature + wire app")

        task = {"tier": "wired"}
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "WIRED"

    def test_sweep_result_has_required_fields(self, tmp_path):
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "wired"}
        result = sweep_task(repo, task, start)
        assert "verdict" in result
        assert "tier" in result
        assert "modules" in result
        assert "checked_at" in result
        assert "start_commit" in result
        assert result["start_commit"] == start

    def test_default_tier_is_domain_model_exempt(self, tmp_path):
        """A task with no tier field defaults to domain-model (EXEMPT)."""
        repo, start, head = _make_py_repo(tmp_path)
        task = {}  # no tier key
        result = sweep_task(repo, task, start)
        assert result["verdict"] == "EXEMPT"
        assert result["reason"] == "tier-exempt"

    def test_reachable_via_scheme_exempts_module_in_wired_tier(self, tmp_path):
        """A wired-tier task with an orphan module declared as cli: is task-WIRED (module EXEMPT)."""
        repo, start, head = _make_py_repo(tmp_path)
        task = {"tier": "wired", "reachableVia": "cli:foo"}
        result = sweep_task(repo, task, start)
        # Module verdict is EXEMPT (cli scheme), so task verdict is WIRED (no ORPHAN modules).
        assert result["verdict"] == "WIRED"
        assert result["modules"][0]["verdict"] == "EXEMPT"
