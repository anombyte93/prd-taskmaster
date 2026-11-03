"""Pin the tier -> vendor model id ladder, unpriced reporting, and the
cross-process telemetry lock.

Every test here imports prd_taskmaster.economy directly, so a stale ladder or a
regression to an in-process-only lock fails here, not in production telemetry.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from prd_taskmaster import economy
from prd_taskmaster.economy import (
    PRICES_PER_MTOK,
    TIER_MODEL_IDS,
    append_telemetry,
    summarize_telemetry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

EXPECTED_IDS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
    "fable": "claude-fable-5-1",
}

# The 5.5 ids carry no cited price in this repo, so they must stay unpriced.
UNPRICED_5_5_IDS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]

# Stored telemetry rows still carry these ids; their price keys must survive.
LEGACY_PRICE_KEYS = [
    "claude-haiku-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-8",
    "claude-fable-5",
    "gpt-4.1",
    "gpt-4.1-mini",
]


def test_tier_model_ids_are_the_5_5_ladder():
    assert TIER_MODEL_IDS == EXPECTED_IDS


def test_legacy_price_keys_are_kept():
    for key in LEGACY_PRICE_KEYS:
        assert key in PRICES_PER_MTOK, key


@pytest.mark.parametrize("model", UNPRICED_5_5_IDS)
def test_5_5_id_without_price_is_unpriced_never_zero(tmp_path, model):
    assert economy._price_key_for_model(model) is None
    f = tmp_path / "telemetry.jsonl"
    append_telemetry(
        {
            "ts": "2026-11-03T00:00:00+00:00",
            "op_class": "structured_gen",
            "model": model,
            "backend": "native-api",
            "exit": 0,
            "tokens_in": 1000,
            "tokens_out": 500,
        },
        f,
    )
    costs = summarize_telemetry(f)["costs"]
    assert costs["unpriced_calls"] == 1
    assert costs["priced_calls"] == 0
    assert costs["priced_coverage"] == 0.0
    # Not priced at zero: no cost or saving is claimed for an unpriced call.
    assert costs["est_cost_usd"] == 0.0
    assert costs["naive_cost_usd"] == 0.0
    assert costs["est_saved_usd"] == 0.0


_WRITER = """
import sys
from prd_taskmaster.economy import append_telemetry
path, tag, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
for i in range(n):
    append_telemetry({"op_class": "concurrency", "model": tag, "i": i, "exit": 0}, path)
"""


def test_two_processes_append_telemetry_without_losing_rows(tmp_path):
    f = tmp_path / "telemetry.jsonl"
    n = 150
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WRITER, str(f), tag, str(n)],
            cwd=str(REPO_ROOT),
        )
        for tag in ("writer-a", "writer-b")
    ]
    for p in procs:
        assert p.wait(timeout=120) == 0

    rows = [json.loads(line) for line in f.read_text().splitlines()]
    assert len(rows) == 2 * n
    for tag in ("writer-a", "writer-b"):
        assert sorted(r["i"] for r in rows if r["model"] == tag) == list(range(n))
