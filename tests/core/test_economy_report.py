"""T7: economy-report — telemetry summary per (op_class, model)."""

import json
from pathlib import Path

import pytest

from prd_taskmaster.economy import PRICES_PER_MTOK, append_telemetry, summarize_telemetry

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rows():
    return [
        {"ts": "t1", "op_class": "structured_gen", "task_id": 1, "model": "claude-haiku-4-5-20251001",
         "backend": "taskmaster-api", "exit": 0, "wall_ms": 1200, "escalated": False},
        {"ts": "t2", "op_class": "structured_gen", "task_id": 2, "model": "claude-haiku-4-5-20251001",
         "backend": "taskmaster-api", "exit": 1, "wall_ms": 900, "escalated": False},
        {"ts": "t3", "op_class": "structured_gen", "task_id": 2, "model": "claude-sonnet-4-6",
         "backend": "taskmaster-api", "exit": 0, "wall_ms": 2400, "escalated": True},
    ]


def test_summarize_groups_and_rates(tmp_path):
    f = tmp_path / "telemetry.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in _rows()) + "\n")
    rep = summarize_telemetry(f)
    assert rep["ok"] is True
    groups = {(g["op_class"], g["model"]): g for g in rep["groups"]}
    haiku = groups[("structured_gen", "claude-haiku-4-5-20251001")]
    assert haiku["calls"] == 2 and haiku["success_rate"] == 0.5
    sonnet = groups[("structured_gen", "claude-sonnet-4-6")]
    assert sonnet["calls"] == 1 and sonnet["success_rate"] == 1.0
    assert sonnet["p50_wall_ms"] == 2400
    assert rep["escalations"] == 1


def test_summarize_missing_file(tmp_path):
    rep = summarize_telemetry(tmp_path / "nope.jsonl")
    assert rep["ok"] is True and rep["groups"] == [] and rep["total_calls"] == 0


def test_summarize_skips_malformed_lines(tmp_path):
    f = tmp_path / "telemetry.jsonl"
    f.write_text('{"op_class":"x","model":"m","exit":0,"wall_ms":10}\nnot json\n')
    rep = summarize_telemetry(f)
    assert rep["total_calls"] == 1 and rep["skipped_lines"] == 1


def test_model_economy_docs_include_verified_openai_price_rows():
    content = (REPO_ROOT / "docs" / "product" / "MODEL-ECONOMY.md").read_text()

    assert "| gpt-4.1 | $2 / $8 | live-verified 2026-06-12 |" in content
    assert "| gpt-4.1-mini | $0.40 / $1.60 | live-verified 2026-06-12 |" in content


def test_summarize_costs_priced_unpriced_unknown_and_corrupt(tmp_path):
    rows = [
        {
            "op_class": "structured_gen",
            "model": "claude-haiku-4-5-20251001",
            "exit": 0,
            "wall_ms": 100,
            "tokens_in": 1_000_000,
            "tokens_out": 500_000,
            "escalated": False,
        },
        {
            "op_class": "structured_gen",
            "model": "claude-sonnet-4-6",
            "exit": 0,
            "wall_ms": 200,
            "tokens_in": 2_000_000,
            "tokens_out": 1_000_000,
            "escalated": True,
        },
        {
            "op_class": "structured_gen",
            "model": "claude-opus-4-8",
            "exit": 1,
            "wall_ms": 300,
            "escalated": False,
        },
        {
            "op_class": "structured_gen",
            "model": "unknown-model",
            "exit": 0,
            "wall_ms": 400,
            "tokens_in": 1_000,
            "tokens_out": 1_000,
            "escalated": False,
        },
    ]
    f = tmp_path / "telemetry.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")

    rep = summarize_telemetry(f)

    assert rep["ok"] is True
    assert rep["total_calls"] == 4
    assert rep["skipped_lines"] == 1
    assert rep["escalations"] == 1
    groups = {(g["op_class"], g["model"]): g for g in rep["groups"]}
    assert groups[("structured_gen", "claude-haiku-4-5-20251001")]["calls"] == 1
    assert groups[("structured_gen", "unknown-model")]["success_rate"] == 1.0

    costs = rep["costs"]
    assert costs["naive_baseline_model"] == "claude-fable-5"
    assert costs["est_cost_usd"] == pytest.approx(24.5)
    assert costs["naive_cost_usd"] == pytest.approx(105.0)
    assert costs["est_saved_usd"] == pytest.approx(80.5)
    assert costs["priced_calls"] == 2
    assert costs["unpriced_calls"] == 2
    assert costs["token_coverage"] == pytest.approx(0.75)
    assert costs["priced_coverage"] == pytest.approx(0.5)


def test_verified_openai_price_math_from_prd(tmp_path):
    f = tmp_path / "telemetry.jsonl"
    f.write_text(json.dumps({
        "op_class": "structured_gen",
        "model": "gpt-4.1-mini",
        "exit": 0,
        "wall_ms": 100,
        "tokens_in": 384,
        "tokens_out": 1240,
        "escalated": False,
    }) + "\n")

    rep = summarize_telemetry(f)

    assert PRICES_PER_MTOK["gpt-4.1"] == (2.0, 8.0)
    assert PRICES_PER_MTOK["gpt-4.1-mini"] == (0.4, 1.6)
    costs = rep["costs"]
    assert costs["est_cost_usd"] == pytest.approx(0.0021376)
    assert costs["naive_cost_usd"] == pytest.approx(0.06584)
    assert costs["est_saved_usd"] == pytest.approx(0.0637024)
    assert costs["priced_calls"] == 1
    assert costs["unpriced_calls"] == 0
    assert costs["priced_coverage"] == pytest.approx(1.0)


def test_versioned_openai_model_id_prices_by_most_specific_prefix(tmp_path):
    f = tmp_path / "telemetry.jsonl"
    f.write_text(json.dumps({
        "op_class": "structured_gen",
        "model": "gpt-4.1-mini-2025-04-14",
        "exit": 0,
        "wall_ms": 100,
        "tokens_in": 384,
        "tokens_out": 1240,
        "escalated": False,
    }) + "\n")

    costs = summarize_telemetry(f)["costs"]

    assert costs["est_cost_usd"] == pytest.approx(0.0021376)
    assert costs["priced_calls"] == 1
    assert costs["unpriced_calls"] == 0


def test_append_telemetry_returns_row_reference(tmp_path):
    f = tmp_path / "telemetry.jsonl"
    first = {
        "ts": "2026-06-12T00:00:00+00:00",
        "op_class": "structured_gen",
        "model": "claude-haiku-4-5-20251001",
        "backend": "native-api",
        "exit": 0,
    }
    second = {
        "ts": "2026-06-12T00:00:01+00:00",
        "op_class": "structured_gen",
        "model": "claude-sonnet-4-6",
        "backend": "native-api",
        "exit": 1,
    }

    ref1 = append_telemetry(first, f)
    ref2 = append_telemetry(second, f)

    assert ref1 == {
        "path": str(f),
        "line": 1,
        "ts": first["ts"],
        "op_class": first["op_class"],
        "model": first["model"],
        "backend": first["backend"],
        "exit": first["exit"],
    }
    assert ref2 == {
        "path": str(f),
        "line": 2,
        "ts": second["ts"],
        "op_class": second["op_class"],
        "model": second["model"],
        "backend": second["backend"],
        "exit": second["exit"],
    }
    assert [json.loads(line) for line in f.read_text().splitlines()] == [first, second]
