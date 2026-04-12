#!/usr/bin/env python3
"""customise-workflow companion skill — deterministic config operations.

Reads and writes .taskmaster/config/user-workflow.json per project.

Philosophy: the AI asks the questions and validates answers; this script
handles the deterministic file I/O and schema validation. Every subcommand
outputs JSON on stdout so the AI can parse it predictably.

Usage:
    script.py load-config                  # Load current config (or defaults)
    script.py list-questions               # Return curated question set
    script.py validate-answer --key K --value V
    script.py write-config --input <file>  # Write answers dict to config
    script.py show-config                  # Display current config
    script.py reset-config                 # Delete config file
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CONFIG_DIR = Path(".taskmaster") / "config"
CONFIG_FILE = CONFIG_DIR / "user-workflow.json"


# ─── Default config ──────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "schema_version": 1,
    "provider": {
        "main": "gemini-cli",
        "model_main": "gemini-3-pro-preview",
        "research": "gemini-cli",
        "model_research": "gemini-3-pro-preview",
        "fallback": "gemini-cli",
        "model_fallback": "gemini-3-flash-preview",
    },
    "validation": {
        "strictness": "normal",
        "ai_review_default": False,
        "min_passing_grade": "GOOD",
    },
    "execution": {
        "preferred_mode": "C",
        "auto_handoff": False,
        "external_tool": None,
    },
    "template": {
        "default": "comprehensive",
        "custom_template_path": None,
    },
    "autonomous": {
        "allow_self_brainstorm": True,
        "ralph_loop_auto_approve": False,
    },
    "gates": {
        "skip_phase_0_if_validated": False,
        "skip_user_approval_in_discovery": False,
        "require_research_expansion": True,
    },
}


# ─── Allowed values for validation ───────────────────────────────────────────

ALLOWED = {
    "provider.main": [
        "gemini-cli", "claude-code", "anthropic", "openai",
        "openrouter", "ollama", "bedrock", "azure", "vertex",
        "codex-cli", "lmstudio", "openai-compatible", "perplexity",
    ],
    "provider.research": [
        "gemini-cli", "claude-code", "anthropic", "openai",
        "openrouter", "ollama", "perplexity",
    ],
    "provider.fallback": [
        "gemini-cli", "claude-code", "anthropic", "openai",
        "openrouter", "ollama",
    ],
    "validation.strictness": ["strict", "normal", "lenient"],
    "validation.min_passing_grade": [
        "EXCELLENT", "GOOD", "ACCEPTABLE", "NEEDS_WORK",
    ],
    "execution.preferred_mode": list("ABCDEFGHIJ"),
    "execution.external_tool": [
        None, "cursor", "roo-code", "codex-cli", "gemini-cli",
        "coderabbit", "aider", "continue",
    ],
    "template.default": ["comprehensive", "minimal"],
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def emit(data: dict) -> None:
    print(json.dumps(data, indent=2, default=str))
    sys.exit(0)


def fail(message: str, **extra) -> None:
    print(json.dumps({"ok": False, "error": message, **extra}, indent=2, default=str))
    sys.exit(1)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def deep_merge(base: dict, overlay: dict) -> dict:
    """Merge overlay into base recursively. overlay keys win."""
    result = dict(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def get_nested(d: dict, key_path: str):
    """Traverse a.b.c style key path. Returns None if missing."""
    current = d
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_nested(d: dict, key_path: str, value) -> None:
    """Set a.b.c style key path in a dict, creating parents as needed."""
    parts = key_path.split(".")
    current = d
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


# ─── Subcommands ─────────────────────────────────────────────────────────────

def cmd_load_config(args: argparse.Namespace) -> None:
    """Load current config file, merging with defaults for missing keys."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE) as f:
                user_cfg = json.load(f)
            merged = deep_merge(DEFAULT_CONFIG, user_cfg)
            emit({
                "ok": True,
                "source": "user+defaults",
                "path": str(CONFIG_FILE),
                "config": merged,
                "user_customised": True,
            })
        except (json.JSONDecodeError, OSError) as exc:
            fail(f"user-workflow.json unreadable: {exc}", path=str(CONFIG_FILE))
    else:
        emit({
            "ok": True,
            "source": "defaults",
            "path": str(CONFIG_FILE),
            "config": DEFAULT_CONFIG,
            "user_customised": False,
        })


def cmd_list_questions(args: argparse.Namespace) -> None:
    """Return the curated question set as JSON for the AI to iterate through."""
    questions = [
        {
            "id": "q1_provider_main",
            "key": "provider.main",
            "category": "provider",
            "prompt": "Which AI provider do you prefer for main task generation?",
            "explainer": "This is the model used by task-master parse-prd and expand. Gemini is most token-efficient (free via Google account). Claude Code is free for Claude Max users. OpenAI/Anthropic/etc require API keys.",
            "options": ALLOWED["provider.main"],
            "default": "gemini-cli",
        },
        {
            "id": "q2_model_main",
            "key": "provider.model_main",
            "category": "provider",
            "prompt": "Which specific model ID for main? (depends on provider chosen)",
            "explainer": "For gemini-cli use 'gemini-3-pro-preview'. For claude-code use 'sonnet'. For openai use 'gpt-4o'. This gets passed verbatim to `task-master models --set-main`.",
            "options": None,
            "default": "gemini-3-pro-preview",
        },
        {
            "id": "q3_provider_research",
            "key": "provider.research",
            "category": "provider",
            "prompt": "Which provider for research calls? (used by --research flags and validate-prd --ai)",
            "explainer": "Perplexity is web-grounded and best for up-to-date research but requires PERPLEXITY_API_KEY. Gemini is free but uses training-data knowledge only.",
            "options": ALLOWED["provider.research"],
            "default": "perplexity",
        },
        {
            "id": "q4_validation_strictness",
            "key": "validation.strictness",
            "category": "validation",
            "prompt": "How strict should PRD validation be?",
            "explainer": "Strict blocks on NEEDS_WORK grade. Normal warns but allows GOOD+. Lenient accepts ACCEPTABLE+.",
            "options": ALLOWED["validation.strictness"],
            "default": "normal",
        },
        {
            "id": "q5_ai_review_default",
            "key": "validation.ai_review_default",
            "category": "validation",
            "prompt": "Run validate-prd --ai by default? (adds LLM-based quality review on every validation)",
            "explainer": "Costs extra tokens but catches subjective quality issues regex misses.",
            "options": [True, False],
            "default": False,
        },
        {
            "id": "q6_preferred_mode",
            "key": "execution.preferred_mode",
            "category": "execution",
            "prompt": "Which execution mode do you prefer for task handoff?",
            "explainer": "A=plan only, B=taskmaster auto, C=ralph-loop free, D=atlas premium, E=Cursor, F=RooCode, G=Codex CLI, H=Gemini CLI, I=CodeRabbit, J=Aider.",
            "options": ALLOWED["execution.preferred_mode"],
            "default": "C",
        },
        {
            "id": "q7_auto_handoff",
            "key": "execution.auto_handoff",
            "category": "execution",
            "prompt": "Auto-handoff to the chosen mode without asking, or always confirm?",
            "explainer": "Auto-handoff is faster but less reversible. Always-confirm is safer but adds a click.",
            "options": [True, False],
            "default": False,
        },
        {
            "id": "q8_template_default",
            "key": "template.default",
            "category": "template",
            "prompt": "Which template should be the default for new PRDs?",
            "explainer": "Comprehensive is the 12-section full template. Minimal is a quick 6-section template for small features.",
            "options": ALLOWED["template.default"],
            "default": "comprehensive",
        },
        {
            "id": "q9_autonomous_brainstorm",
            "key": "autonomous.allow_self_brainstorm",
            "category": "autonomous",
            "prompt": "Allow the skill to self-brainstorm in autonomous mode (ralph-loop / pentest-wtf / auto-approve)?",
            "explainer": "When enabled, DISCOVER phase writes its own answers instead of blocking for user input. Required for overnight or unattended runs.",
            "options": [True, False],
            "default": True,
        },
        {
            "id": "q10_require_research_expansion",
            "key": "gates.require_research_expansion",
            "category": "gates",
            "prompt": "Require research expansion on every task (uses the research model for each expand_task call)?",
            "explainer": "Better task quality but costs more tokens. Off by default for speed.",
            "options": [True, False],
            "default": True,
        },
    ]
    emit({"ok": True, "count": len(questions), "questions": questions})


def cmd_validate_answer(args: argparse.Namespace) -> None:
    """Validate a single answer against the allowed set for its key."""
    key = args.key
    raw_value = args.value

    # Parse bool strings
    if raw_value.lower() in ("true", "false"):
        value = raw_value.lower() == "true"
    elif raw_value.lower() in ("none", "null"):
        value = None
    else:
        value = raw_value

    allowed = ALLOWED.get(key)
    if allowed is None:
        # Free-text key (e.g. provider.model_main) — accept any non-empty string
        if value is None or (isinstance(value, str) and not value.strip()):
            fail(f"{key}: value must be non-empty", key=key, value=raw_value)
        emit({"ok": True, "key": key, "value": value, "validation": "free-text"})

    if value in allowed:
        emit({"ok": True, "key": key, "value": value, "validation": "exact-match"})
    else:
        fail(
            f"{key}: '{raw_value}' not in allowed set",
            key=key,
            value=raw_value,
            allowed=allowed,
        )


def cmd_write_config(args: argparse.Namespace) -> None:
    """Write validated answers dict to user-workflow.json."""
    input_path = Path(args.input)
    if not input_path.is_file():
        fail(f"Answers file not found: {args.input}")

    try:
        with open(input_path) as f:
            answers = json.load(f)
    except json.JSONDecodeError as exc:
        fail(f"Answers file is not valid JSON: {exc}")

    # Answers are key-path -> value pairs. Build a nested dict.
    overlay = {}
    for key_path, value in answers.items():
        set_nested(overlay, key_path, value)

    # Merge with current config (or defaults)
    if CONFIG_FILE.is_file():
        with open(CONFIG_FILE) as f:
            current = json.load(f)
    else:
        current = {}

    merged = deep_merge(DEFAULT_CONFIG, current)
    merged = deep_merge(merged, overlay)
    merged["_last_updated"] = now_iso()
    merged["schema_version"] = 1

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(merged, indent=2, default=str))

    emit({
        "ok": True,
        "path": str(CONFIG_FILE),
        "keys_updated": list(answers.keys()),
        "config": merged,
    })


def cmd_show_config(args: argparse.Namespace) -> None:
    """Display the merged (defaults + user) config."""
    cmd_load_config(args)


def cmd_reset_config(args: argparse.Namespace) -> None:
    """Delete user-workflow.json."""
    if CONFIG_FILE.is_file():
        CONFIG_FILE.unlink()
        emit({
            "ok": True,
            "action": "deleted",
            "path": str(CONFIG_FILE),
        })
    else:
        emit({
            "ok": True,
            "action": "noop",
            "message": "No user-workflow.json to delete",
        })


# ─── Argument parsing ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="customise-workflow",
        description="Customise prd-taskmaster-v2 workflow via user-workflow.json",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("load-config", help="Load current config (or defaults)")
    sub.add_parser("list-questions", help="Return the curated question set")
    sub.add_parser("show-config", help="Display current config")
    sub.add_parser("reset-config", help="Delete user-workflow.json")

    p = sub.add_parser("validate-answer", help="Validate a single answer")
    p.add_argument("--key", required=True, help="Dotted key path (e.g. provider.main)")
    p.add_argument("--value", required=True, help="The answer value")

    p = sub.add_parser("write-config", help="Write answers dict to config")
    p.add_argument("--input", required=True, help="Path to answers JSON file")

    return parser


DISPATCH = {
    "load-config": cmd_load_config,
    "list-questions": cmd_list_questions,
    "validate-answer": cmd_validate_answer,
    "write-config": cmd_write_config,
    "show-config": cmd_show_config,
    "reset-config": cmd_reset_config,
}


def main():
    parser = build_parser()
    args = parser.parse_args()
    handler = DISPATCH.get(args.command)
    if handler:
        handler(args)
    else:
        fail(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
