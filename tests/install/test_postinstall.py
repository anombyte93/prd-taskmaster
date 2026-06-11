"""Tests for npm postinstall telemetry behavior."""

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run_postinstall(tmp_path, *, telemetry_env=None):
    package = json.loads((ROOT / "package.json").read_text())
    script = package["scripts"]["postinstall"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "python.log"
    log.write_text("")
    (bin_dir / "pip").write_text("#!/usr/bin/env bash\nexit 0\n")
    (bin_dir / "python3").write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"${PYTHON_LOG}\"\n"
        "exit 0\n"
    )
    (bin_dir / "pip").chmod(0o755)
    (bin_dir / "python3").chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "PYTHON_LOG": str(log),
        }
    )
    if telemetry_env is not None:
        env["ATLAS_TELEMETRY"] = telemetry_env
    result = subprocess.run(
        script,
        cwd=ROOT,
        env=env,
        shell=True,
        executable="/bin/bash",
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text()


def test_package_postinstall_sends_install_event_once(tmp_path):
    result, python_log = _run_postinstall(tmp_path)

    assert result.returncode == 0, result.stderr
    assert python_log.count('send_event("install")') == 1


def test_package_postinstall_respects_env_opt_out(tmp_path):
    result, python_log = _run_postinstall(tmp_path, telemetry_env="0")

    assert result.returncode == 0, result.stderr
    assert 'send_event("install")' not in python_log
