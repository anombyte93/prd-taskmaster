from prd_taskmaster.render import (
    SYMBOLS,
    USER_PHASES,
    render_gate,
    render_phase_header,
    render_status_block,
)


def test_render_phase_header_uses_atlas_phase_bar():
    header = render_phase_header(1, "PREFLIGHT")

    assert header.startswith("┌─ atlas ── PHASE 1/4: PREFLIGHT ")
    assert header.endswith("┐")
    assert len(header) <= 64


def test_render_phase_header_maps_internal_pipeline_phases():
    assert USER_PHASES["SETUP"] == ("PREFLIGHT", 1)
    assert USER_PHASES["DISCOVER"] == ("DISCOVERY", 2)
    assert USER_PHASES["GENERATE"] == ("GENERATE", 3)
    assert USER_PHASES["HANDOFF"] == ("HANDOFF", 4)
    assert USER_PHASES["EXECUTE"] is None

    assert "PHASE 2/4: DISCOVERY" in render_phase_header("DISCOVER")
    assert render_phase_header("EXECUTE") == ""


def test_render_gate_passed_has_summary_and_no_raw_json():
    output = render_gate({
        "gate_passed": True,
        "phase": "GENERATE",
        "summary": "GOOD score with 12 parsed tasks",
        "violations": [],
    })

    assert output == "✓ Gate passed: GOOD score with 12 parsed tasks"
    assert "{" not in output
    assert "}" not in output
    assert '"gate_passed"' not in output


def test_render_gate_blocked_lists_violation_and_one_fix_without_raw_json():
    output = render_gate({
        "gate_passed": False,
        "phase": "SETUP",
        "violations": ["validate_setup must report ready=true with 0 critical failures"],
    })

    assert output.splitlines()[0] == (
        "✗ Gate blocked: validate_setup must report ready=true with 0 critical failures"
    )
    assert output.splitlines()[1].startswith("Fix: ")
    assert "{" not in output
    assert "}" not in output


def test_render_status_block_orders_what_evidence_next_step():
    output = render_status_block(
        "SETUP",
        what_happened="Preflight checked local tools.",
        evidence=["✓ Python 3 available", "○ TaskMaster not installed"],
        next_step="Install task-master-ai, then run /atlas again.",
    )

    lines = output.splitlines()
    assert lines[0].startswith("┌─ atlas ── PHASE 1/4: PREFLIGHT ")
    assert lines[1] == "What happened: Preflight checked local tools."
    assert lines[2] == "Evidence:"
    assert lines[3] == "  ✓ Python 3 available"
    assert lines[4] == "  ○ TaskMaster not installed"
    assert lines[5] == "Next: Install task-master-ai, then run /atlas again."


def test_symbols_include_unicode_and_ascii_fallbacks():
    assert SYMBOLS["pass"] == ("✓", "PASS")
    assert SYMBOLS["blocked"] == ("✗", "BLOCKED")
    assert SYMBOLS["warn"] == ("⚠", "WARN")
    assert SYMBOLS["pending"] == ("○", "PENDING")
    assert SYMBOLS["next"] == ("▶", "NEXT")
