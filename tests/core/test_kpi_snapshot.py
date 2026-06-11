import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "kpi-snapshot.sh"


def _run_snapshot(env_updates=None):
    env = os.environ.copy()
    for key in (
        "CF_ACCOUNT_ID",
        "CF_API_TOKEN",
        "ATLAS_D1_DB",
        "KPI_QUERY_CMD",
        "KPI_FIXTURE_JSON",
        "LICENSE_TELEMETRY_DEPLOYED",
    ):
        env.pop(key, None)
    if env_updates:
        env.update(env_updates)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_kpi_snapshot_outputs_table_from_fixture_json():
    fixture = {
        "A1": {"last_7d": 7, "last_30d": 30, "all_time": 300},
        "A3": {"last_7d": 4, "last_30d": 12, "all_time": 80},
        "AC1": {"last_7d": 3, "last_30d": 10, "all_time": 60},
        "AC2": {"last_7d": 2, "last_30d": 8, "all_time": 40},
        "C1": {"last_7d": "5%", "last_30d": "7%", "all_time": "9%"},
    }

    result = _run_snapshot({"KPI_FIXTURE_JSON": json.dumps(fixture), "LICENSE_TELEMETRY_DEPLOYED": "1"})

    assert result.returncode == 0, result.stderr
    assert "Metric" in result.stdout
    assert "last-7d" in result.stdout
    assert "last-30d" in result.stdout
    assert "all-time" in result.stdout
    for label in ("A1 installs", "A3 weekly actives", "AC1 reach_execute", "AC2 ship_check_ok", "C1 conversion"):
        assert label in result.stdout
    assert "300" in result.stdout
    assert "9%" in result.stdout


def test_kpi_snapshot_unconfigured_exits_zero_with_not_configured_rows():
    result = _run_snapshot()

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("not configured") >= 4
    assert "C1 conversion" in result.stdout
    assert "n/a (license telemetry not deployed)" in result.stdout
