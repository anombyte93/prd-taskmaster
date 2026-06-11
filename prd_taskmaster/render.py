"""User-facing terminal rendering helpers."""

from __future__ import annotations

from typing import Iterable

HEADER_WIDTH = 64

SYMBOLS = {
    "pass": ("✓", "PASS"),
    "blocked": ("✗", "BLOCKED"),
    "warn": ("⚠", "WARN"),
    "pending": ("○", "PENDING"),
    "next": ("▶", "NEXT"),
}

USER_PHASES: dict[str, tuple[str, int] | None] = {
    "SETUP": ("PREFLIGHT", 1),
    "DISCOVER": ("DISCOVERY", 2),
    "GENERATE": ("GENERATE", 3),
    "HANDOFF": ("HANDOFF", 4),
    "EXECUTE": None,
}

_PHASE_FIXES = {
    "SETUP": "Run /atlas setup again after fixing the failed preflight check.",
    "DISCOVER": "Record user approval or document clear assumptions before continuing.",
    "GENERATE": "Regenerate or repair tasks until the score is GOOD or better.",
    "HANDOFF": "Record the chosen mode and write the plan file before handoff.",
}


def render_phase_header(phase_or_number: str | int, name: str | None = None) -> str:
    """Render the UX-SPEC phase header for user-facing pipeline phases."""
    if isinstance(phase_or_number, str):
        mapped = USER_PHASES.get(phase_or_number.upper())
        if mapped is None:
            return ""
        name, number = mapped
    else:
        number = phase_or_number
        if name is None:
            raise ValueError("name is required when rendering by phase number")

    label = f"┌─ atlas ── PHASE {number}/4: {name.upper()} "
    fill = max(0, HEADER_WIDTH - len(label) - 1)
    return f"{label}{'─' * fill}┐"


def render_gate(result: dict) -> str:
    """Render a pipeline gate result without exposing raw JSON."""
    phase = str(result.get("phase") or "").upper()
    violations = _clean_lines(result.get("violations", []))

    if result.get("gate_passed"):
        summary = str(result.get("summary") or _default_gate_summary(phase))
        return f"{SYMBOLS['pass'][0]} Gate passed: {summary}"

    violation = violations[0] if violations else "required evidence is missing"
    fix = str(result.get("fix") or _PHASE_FIXES.get(phase) or "Add the missing evidence and rerun the gate.")
    return f"{SYMBOLS['blocked'][0]} Gate blocked: {violation}\nFix: {fix}"


def render_status_block(
    phase_or_number: str | int,
    *,
    name: str | None = None,
    what_happened: str,
    evidence: Iterable[str],
    next_step: str,
) -> str:
    """Render a fixed-order status block: what happened, evidence, next step."""
    lines = [render_phase_header(phase_or_number, name)]
    lines.append(f"What happened: {what_happened}")
    lines.append("Evidence:")
    lines.extend(f"  {line}" for line in evidence)
    lines.append(f"Next: {next_step}")
    return "\n".join(line for line in lines if line)


def _clean_lines(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _default_gate_summary(phase: str) -> str:
    if phase in USER_PHASES and USER_PHASES[phase] is not None:
        name, _number = USER_PHASES[phase]
        return f"{name.title()} evidence is ready"
    return "required evidence is ready"
