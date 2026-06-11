"""T7: economy-report — telemetry summary per (op_class, model)."""

import json

from prd_taskmaster.economy import summarize_telemetry


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
