import os
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _make_fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "fake-repo"
    (repo / "prd_taskmaster").mkdir(parents=True)
    (repo / "SKILL.md").write_text("# fake skill\n")
    (repo / "script.py").write_text("print('atlas')\n")
    (repo / "prd_taskmaster" / "__init__.py").write_text("")
    (repo / "prd_taskmaster" / "telemetry.py").write_text("def send_event(event):\n    pass\n")
    (repo / "install.sh").write_text("#!/usr/bin/env bash\n")
    return repo


def _make_fake_bin(tmp_path: Path, fake_repo: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm_log = tmp_path / "npm.log"
    npm_log.write_text("")
    bash_path = shutil.which("bash") or "/bin/bash"
    for cmd in ("cat", "chmod", "cp", "date", "dirname", "head", "mkdir", "mktemp", "rm"):
        resolved = shutil.which(cmd)
        if resolved:
            (bin_dir / cmd).symlink_to(resolved)
    _write_executable(
        bin_dir / "git",
        f"#!{bash_path}\n"
        "set -euo pipefail\n"
        "if [[ \"${1:-}\" == \"clone\" ]]; then\n"
        "  dest=\"${@: -1}\"\n"
        "  mkdir -p \"$dest\"\n"
        f"  cp -R {fake_repo}/. \"$dest/\"\n"
        "  exit 0\n"
        "fi\n"
        "echo unexpected git invocation: $* >&2\n"
        "exit 1\n",
    )
    _write_executable(
        bin_dir / "npm",
        f"#!{bash_path}\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"$NPM_LOG\"\n"
        "if [[ \"$*\" == \"install -g task-master-ai\" ]]; then\n"
        "  cat > \"$(dirname \"$0\")/task-master-ai\" <<'TMEOF'\n"
        f"#!{bash_path}\n"
        "if [[ \"${1:-}\" == \"--version\" ]]; then echo task-master-ai 1.2.3; else echo task-master-ai ok; fi\n"
        "TMEOF\n"
        "  chmod +x \"$(dirname \"$0\")/task-master-ai\"\n"
        "fi\n",
    )
    return bin_dir, npm_log


def test_install_sh_installs_taskmaster_peer_and_prints_first_run_box(tmp_path):
    fake_repo = _make_fake_repo(tmp_path)
    bin_dir, npm_log = _make_fake_bin(tmp_path, fake_repo)
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "ATLAS_TELEMETRY": "0",
            "CI": "1",
            "HOME": str(home),
            "NPM_LOG": str(npm_log),
            "PATH": str(bin_dir),
            "SKILL_DIR": str(home / "skill"),
        }
    )

    result = subprocess.run(
        [shutil.which("bash") or "/bin/bash", str(REPO_ROOT / "install.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "install -g task-master-ai" in npm_log.read_text()
    assert "✓ Peer dependency: task-master-ai" in result.stdout
    assert "✓ Self-test: task-master-ai --version" in result.stdout
    assert "Done in " in result.stdout
    assert 'Try: /atlas or say "I want to build..."' in result.stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required for walkthrough")
def test_quickstart_walkthrough_script_runs_deterministic_path():
    script = REPO_ROOT / "tests" / "scripts" / "quickstart-walkthrough.sh"

    result = subprocess.run(
        [shutil.which("bash") or "/bin/bash", str(script)],
        cwd=REPO_ROOT,
        env={**os.environ, "QUICKSTART_LIVE": "0"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "quickstart deterministic path ok" in result.stdout


def test_readme_quickstart_matches_installer_claims():
    readme = (REPO_ROOT / "README.md").read_text()
    install = (REPO_ROOT / "install.sh").read_text()

    assert 'Try: /atlas or say "I want to build..."' in readme
    assert "sets up the task-master-ai peer" in readme
    assert "✓ Peer dependency: task-master-ai" in install
    for flag in ("--check-update", "--no-telemetry", "--version", "--help"):
        assert flag in install
