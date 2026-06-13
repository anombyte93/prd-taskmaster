"""Pure terminal renderer for Atlas progress panels.

Reproduces the boxed status panels specified in docs/product/UX-SPEC.md §1-2
from real pipeline state, honoring the §7 symbol grammar:

    ✓ done   ✗ blocked   ⚠ warning   ○ optional/queued   ▶ running
    ▸ option   ▰▱ progress bar   🔒 pilot-locked

Rules (UX-SPEC §7): every state = symbol + word; progress bars carry numerals;
≤64 cols inside the box; monochrome (NO_COLOR is irrelevant — we emit no color).
An ASCII fallback (ATLAS_ASCII=1, or a non-UTF stdout) swaps every glyph for a
bracket token so the panels survive terminals without UTF-8.

This module is pure: functions take plain dicts and return strings. No file
I/O, no process state — so it is trivially testable and deterministic.
"""

from __future__ import annotations

import os
import sys
import unicodedata

INNER_WIDTH = 60  # columns inside the box borders (≤64 per UX-SPEC)


def _display_width(s: str) -> int:
    """Terminal column width of a string. Wide/Fullwidth code points (e.g. the
    🔒 emoji) count as 2; everything else (including ambiguous box/bar glyphs,
    which terminals render at 1) counts as 1."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _clip(s: str, width: int) -> str:
    """Clip a string to a display width of `width` columns."""
    out, w = [], 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        if w + cw > width:
            break
        out.append(c)
        w += cw
    return "".join(out)

# UX-SPEC §7 symbol grammar → (unicode, ascii-fallback)
_GLYPHS = {
    "done": ("✓", "[ok]"),
    "blocked": ("✗", "[x]"),
    "warn": ("⚠", "[!]"),
    "optional": ("○", "[ ]"),
    "running": ("▶", "[>]"),
    "option": ("▸", ">"),
    "lock": ("🔒", "[PILOT]"),
    "star": ("★", "*"),
    "dot": ("·", "-"),
    "bar_full": ("▰", "#"),
    "bar_empty": ("▱", "-"),
}
_BOX = {
    "tl": ("┌", "+"), "tr": ("┐", "+"), "bl": ("└", "+"), "br": ("┘", "+"),
    "h": ("─", "-"), "v": ("│", "|"),
}


def _ascii_mode() -> bool:
    if os.environ.get("ATLAS_ASCII"):
        return True
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" not in enc if enc else False


def _g(name: str, ascii_mode: bool) -> str:
    return _GLYPHS[name][1 if ascii_mode else 0]


def _b(name: str, ascii_mode: bool) -> str:
    return _BOX[name][1 if ascii_mode else 0]


def grade_word(percentage: float) -> str:
    """Letter grade from a percentage (matches validation.py thresholds)."""
    if percentage >= 91:
        return "EXCELLENT"
    if percentage >= 83:
        return "GOOD"
    if percentage >= 75:
        return "ACCEPTABLE"
    return "NEEDS_WORK"


def bar(score: float, maximum: float, segments: int = 10, *, ascii_mode: bool = False) -> str:
    """A segmented progress bar. The caller is responsible for appending the
    numerals (UX-SPEC: bars carry numerals) — this returns only the segments."""
    if maximum <= 0:
        filled = 0
    else:
        # floor, not round — never inflate a grade bar; matches the UX-SPEC /
        # README mockup (49/57 = 86% → 8/10 filled, not 9).
        filled = max(0, min(segments, int((score / maximum) * segments)))
    full, empty = _g("bar_full", ascii_mode), _g("bar_empty", ascii_mode)
    return full * filled + empty * (segments - filled)


def box(title: str, lines: list[str], *, ascii_mode: bool = False, width: int = INNER_WIDTH) -> str:
    """Render a titled box. `title` goes in the top border:
    ┌─ atlas ── <TITLE> ─…─┐. Body lines are padded to `width`."""
    h, v = _b("h", ascii_mode), _b("v", ascii_mode)
    tl, tr, bl, br = _b("tl", ascii_mode), _b("tr", ascii_mode), _b("bl", ascii_mode), _b("br", ascii_mode)
    label = f"{h} atlas {h}{h} {title} "
    # body/bottom span (width + 2) cells between the corners (content width plus
    # the two margin spaces); the top border must match exactly.
    fill = (width + 2) - _display_width(label)
    if fill < 1:
        label = _clip(label, (width + 2) - 1)
        fill = 1
    top = f"{tl}{label}{h * fill}{tr}"
    out = [top]
    for ln in lines:
        clipped = _clip(ln, width)
        out.append(f"{v} {clipped}{' ' * (width - _display_width(clipped))} {v}")
    out.append(f"{bl}{h * (width + 2)}{br}")
    return "\n".join(out)


# ─── one-line summary ─────────────────────────────────────────────────────────


def oneline_summary(validation: dict | None, task_counts: dict | None, *, ascii_mode: bool = False) -> str:
    """`Grade: GOOD ▰▰▰▰▰▰▰▰▱▱ 49/57 (86%) · 0 placeholders · 14 tasks parsed`"""
    dot = f" {_g('dot', ascii_mode)} "
    if not validation:
        return "No PRD validated yet."
    pct = validation.get("percentage", 0)
    g = bar(validation.get("score", 0), validation.get("max_score", 0) or 1, ascii_mode=ascii_mode)
    parts = [
        f"Grade: {validation.get('grade', grade_word(pct))}  {g}  "
        f"{validation.get('score', 0)}/{validation.get('max_score', 0)} ({round(pct)}%)",
        f"{validation.get('placeholders_found', 0)} placeholders",
    ]
    if task_counts:
        parts.append(f"{task_counts.get('total', 0)} tasks parsed")
    return dot.join(parts)


# ─── phase tracker ────────────────────────────────────────────────────────────

# UX-SPEC numbers the pre-execution phases 1/4..4/4; EXECUTE is "the run".
_PHASE_DISPLAY = {
    "SETUP": ("PREFLIGHT", 1),
    "DISCOVER": ("DISCOVERY", 2),
    "GENERATE": ("GENERATE", 3),
    "HANDOFF": ("HANDOFF", 4),
    "EXECUTE": ("EXECUTE", None),
}


def phase_header_title(phase: str | None) -> str:
    if not phase:
        return "PHASE 0/4: NOT STARTED"
    name, num = _PHASE_DISPLAY.get(phase, (phase, None))
    return f"PHASE {num}/4: {name}" if num else "EXECUTE — the run"


def phase_tracker(state: dict, *, ascii_mode: bool = False) -> str:
    cur = state.get("current_phase")
    done = set(state.get("phases_completed", []))
    lines = []
    for key in ("SETUP", "DISCOVER", "GENERATE", "HANDOFF", "EXECUTE"):
        name, num = _PHASE_DISPLAY[key]
        if key in done:
            sym, word = _g("done", ascii_mode), "done"
        elif key == cur:
            sym, word = _g("running", ascii_mode), "in progress"
        else:
            sym, word = _g("optional", ascii_mode), "pending"
        label = f"{num}/4" if num else " run"
        lines.append(f"{sym} {label}  {name:<10} {word}")
    return box("PIPELINE", lines, ascii_mode=ascii_mode)


# ─── validation scorecard (the headline GENERATE panel) ───────────────────────


def validation_scorecard(validation: dict | None, task_counts: dict | None, *, ascii_mode: bool = False) -> str:
    if not validation:
        return box("PHASE 3/4: GENERATE", ["Spec not generated yet."], ascii_mode=ascii_mode)
    pct = validation.get("percentage", 0)
    g = bar(validation.get("score", 0), validation.get("max_score", 0) or 1, ascii_mode=ascii_mode)
    checks_passed = validation.get("checks_passed", 0)
    warnings = validation.get("warnings", [])
    placeholders = validation.get("placeholders_found", 0)
    ok, warn = _g("done", ascii_mode), _g("warn", ascii_mode)
    lines = [
        f"Grade: {validation.get('grade', grade_word(pct))}  {g}  "
        f"{validation.get('score', 0)}/{validation.get('max_score', 0)} ({round(pct)}%)",
        "",
        f"{ok} {checks_passed} checks passed",
    ]
    if warnings:
        lines.append(f"{warn} {len(warnings)} warnings")
        for i, w in enumerate(warnings[:4], 1):
            loc = ""
            if w.get("lines"):
                loc = f" (line {', '.join(str(n) for n in w['lines'])})"
            elif w.get("line"):
                loc = f" (line {w['line']})"
            term = w.get("term") or w.get("item") or w.get("type", "")
            lines.append(f"   W{i}  {term}{loc}")
    else:
        lines.append(f"{ok} 0 warnings")
    ph_sym = ok if placeholders == 0 else warn
    lines.append(f"{ph_sym} {placeholders} placeholders   (TBD/TODO/{{...}} scan)")
    if validation.get("hard_fail"):
        lines.append(f"{_g('blocked', ascii_mode)} hard fail: placeholders must be removed")
    if task_counts:
        subs = task_counts.get("subtasks")
        tasks_line = f"Tasks: {task_counts.get('total', 0)} parsed"
        if subs is not None:
            tasks_line += f" {_g('dot', ascii_mode)} {subs} subtasks"
        lines += ["", tasks_line]
    return box("PHASE 3/4: GENERATE", lines, ascii_mode=ascii_mode)


# ─── preflight capability panel ───────────────────────────────────────────────


def preflight_panel(preflight: dict, *, ascii_mode: bool = False) -> str:
    ok, opt, blocked = _g("done", ascii_mode), _g("optional", ascii_mode), _g("blocked", ascii_mode)
    tm = preflight.get("has_taskmaster")
    backend = (preflight.get("backend") or {})
    sel = backend.get("selected") if isinstance(backend, dict) else preflight.get("backend")
    lines = [
        f"{ok if tm else opt} TaskMaster     {'available' if tm else 'optional — native backend in use'}",
        f"{ok} Backend        {sel or 'native'}",
        f"{ok if preflight.get('ok') else blocked} Pipeline       {'verified' if preflight.get('ok') else 'not ready'}",
        "",
        f"Gate: environment ready." if preflight.get("ok") else "Gate: blocked — see above.",
    ]
    return box("PHASE 1/4: PREFLIGHT", lines, ascii_mode=ascii_mode)


# ─── ship-check gates panel ───────────────────────────────────────────────────

_GATE_NAMES = [
    "Pipeline phase = EXECUTE",
    "All tasks done",
    "CDD evidence per task",
    "Plan file present",
    "No non-zero exit codes",
]


def shipcheck_panel(shipcheck: dict, *, ascii_mode: bool = False) -> str:
    ok, blocked = _g("done", ascii_mode), _g("blocked", ascii_mode)
    failures = " ".join(shipcheck.get("failures", []))
    lines = []
    for i, name in enumerate(_GATE_NAMES, 1):
        # a gate is failed if its hint appears in the failures blob
        hit = any(tok in failures.lower() for tok in _gate_tokens(i))
        sym, word = (blocked, "blocked") if hit else (ok, "passed")
        lines.append(f"{sym} Gate {i}  {name:<26} {word}")
    lines.append("")
    if shipcheck.get("passed"):
        token = "SHIP_CHECK_OK" + (" [OVERRIDE]" if shipcheck.get("override_active") else "")
        lines.append(f"{ok} {token}")
    else:
        lines.append(f"{blocked} not shippable — {len(shipcheck.get('failures', []))} gate(s) failed")
    return box("SHIP CHECK", lines, ascii_mode=ascii_mode)


def _gate_tokens(i: int) -> list[str]:
    return {
        1: ["phase", "pipeline"],
        2: ["task", "done", "status"],
        3: ["cdd", "evidence"],
        4: ["plan"],
        5: ["exit"],
    }[i]


# ─── execute progress panel ───────────────────────────────────────────────────


def execute_panel(task_counts: dict, *, ascii_mode: bool = False) -> str:
    total = task_counts.get("total", 0)
    done = task_counts.get("done", 0)
    g = bar(done, total or 1, ascii_mode=ascii_mode)
    running = _g("running", ascii_mode)
    lines = [
        f"Progress  {g}  {done}/{total} tasks done",
        "",
        f"{running} executing — evidence required before a task counts done.",
    ]
    return box("EXECUTE — the run", lines, ascii_mode=ascii_mode)


# ─── handoff panel (modes; Fleet = private pilot, NO price) ────────────────────


def handoff_panel(validation: dict | None, task_counts: dict | None, *, ascii_mode: bool = False) -> str:
    opt, star, lock = _g("option", ascii_mode), _g("star", ascii_mode), _g("lock", ascii_mode)
    summary = "Spec ready"
    if validation:
        summary = f"Spec: {validation.get('grade', '')} ({round(validation.get('percentage', 0))}%)"
    if task_counts:
        summary += f" {_g('dot', ascii_mode)} {task_counts.get('total', 0)} tasks"
    lines = [
        summary,
        "",
        "How should these tasks get executed?",
        f"{opt} Verified Loop        {star} recommended — evidence per task",
        f"{opt} Auto-Execute         native loop, lighter verification",
        f"{opt} Plan & Drive         get the plan, implement it yourself",
        "",
        f"{lock} Atlas Fleet          private pilot — request access",
    ]
    return box("PHASE 4/4: HANDOFF", lines, ascii_mode=ascii_mode)
