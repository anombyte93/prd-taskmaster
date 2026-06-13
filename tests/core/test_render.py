"""Pure-renderer tests: bar math, box width/alignment, glyph + ASCII fallback,
and the UX-SPEC honesty rules (every state = symbol + word; bars carry numerals)."""

import unicodedata

from prd_taskmaster import render


def _dw(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def test_bar_fills_proportionally():
    assert render.bar(49, 57) == "▰▰▰▰▰▰▰▰▱▱"   # 49/57 → 8.6 → 9? round(8.59)=9
    # be exact about the rounding contract:
    assert render.bar(57, 57) == "▰" * 10
    assert render.bar(0, 57) == "▱" * 10
    assert render.bar(0, 0) == "▱" * 10          # no div-by-zero


def test_bar_ascii_fallback():
    assert render.bar(57, 57, ascii_mode=True) == "#" * 10


def test_grade_word_thresholds():
    assert render.grade_word(95) == "EXCELLENT"
    assert render.grade_word(86) == "GOOD"
    assert render.grade_word(78) == "ACCEPTABLE"
    assert render.grade_word(40) == "NEEDS_WORK"


def test_box_borders_align_in_display_width():
    panel = render.box("TEST", ["plain line", "with glyph ✓ and emoji 🔒 inline"])
    lines = panel.splitlines()
    widths = {_dw(ln) for ln in lines}
    assert len(widths) == 1, f"misaligned box rows: {widths}"


def test_box_ascii_mode_has_no_unicode_box_chars():
    panel = render.box("TEST", ["x"], ascii_mode=True)
    assert "┌" not in panel and "│" not in panel and "─" not in panel
    assert panel.startswith("+-")


def test_validation_scorecard_shows_grade_bar_and_numerals():
    val = {
        "grade": "GOOD", "score": 49, "max_score": 57, "percentage": 86,
        "checks_passed": 11, "warnings": [{"term": "fast", "lines": [7]}],
        "placeholders_found": 0,
    }
    out = render.validation_scorecard(val, {"total": 14, "subtasks": 52})
    assert "Grade: GOOD" in out
    assert "49/57 (86%)" in out               # bar carries numerals
    assert "11 checks passed" in out
    assert "W1  fast (line 7)" in out          # warnings quoted + located
    assert "0 placeholders" in out
    assert "14 parsed" in out and "52 subtasks" in out


def test_every_state_pairs_symbol_with_word():
    # preflight panel: each status glyph must be followed by a word, not bare
    out = render.preflight_panel({"ok": True, "has_taskmaster": True, "backend": "native"})
    for line in out.splitlines():
        if "✓" in line or "○" in line or "✗" in line:
            # there is alphabetic text after the glyph
            assert any(c.isalpha() for c in line.split("✓")[-1] + line.split("○")[-1])


def test_handoff_panel_has_no_price_and_marks_fleet_pilot():
    out = render.handoff_panel({"grade": "GOOD", "percentage": 86}, {"total": 14})
    assert "$29" not in out and "/mo" not in out
    assert "private pilot" in out and "🔒" in out


def test_shipcheck_panel_renders_five_gates_and_token():
    out = render.shipcheck_panel({"passed": True, "failures": []})
    for i in range(1, 6):
        assert f"Gate {i}" in out
    assert "SHIP_CHECK_OK" in out
