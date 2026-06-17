"""Shared helpers, path constants, and VAGUE patterns for prd-taskmaster.

emit()/fail() live here (CLI layer). Pure cores raise CommandError instead of
calling fail(), and return dicts instead of calling emit().
"""

import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ─── Path constants ───────────────────────────────────────────────────────────
# Templates live at the REPO ROOT (one level above this package dir).
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
TEMPLATE_DIR = REPO_ROOT / "templates"
TASKMASTER_DIR = Path(".taskmaster")
TASKMASTER_DOCS = TASKMASTER_DIR / "docs"
TASKMASTER_SCRIPTS = TASKMASTER_DIR / "scripts"
TASKMASTER_STATE = TASKMASTER_DIR / "state"
TASKMASTER_TASKS = TASKMASTER_DIR / "tasks"


# ─── CLI emit / fail ──────────────────────────────────────────────────────────

def emit(data: dict) -> None:
    """Print JSON to stdout and exit 0."""
    print(json.dumps(data, indent=2, default=str))
    sys.exit(0)


def fail(message: str, **extra) -> None:
    """Print JSON error to stdout and exit 1."""
    print(json.dumps({"ok": False, "error": message, **extra}, indent=2, default=str))
    sys.exit(1)


class CommandError(Exception):
    """Raised by pure cores to signal a failure path.

    Carries the message and any extra fields so the CLI wrapper can translate
    it into fail(message, **extra) for identical CLI output, while a hosting
    process (e.g. MCP server) can catch it without exiting.
    """

    def __init__(self, message: str, extra: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.extra = extra or {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Stateful-core helpers (atomic / locked writes, JSON IO) ──────────────────
# Ported byte-faithful from the plugin mcp-server/lib.py. All return values are
# dicts/strings — NEVER call sys.exit (per spec §13.3).

def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via tmp + os.replace (atomic on POSIX)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(content)
    os.replace(tmp, path)


def locked_update(path: Path, transform: Callable[[str], str]) -> str:
    """Read-modify-write under flock. transform takes current content, returns new content.
    Returns the new content for convenience.

    The write is skipped when the transform returns the same string as ``current``
    (identity check: ``new is current`` or ``new == current``) to avoid creating
    ghost empty files when the transform signals a no-op / error abort by returning
    the unchanged input.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            current = path.read_text() if path.exists() else ""
            new = transform(current)
            if new is not current and new != current:
                atomic_write(path, new)
            return new
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def emit_json_error(message: str, **extra: Any) -> dict:
    """Format an error response as a dict. DO NOT call sys.exit."""
    return {"ok": False, "error": message, **extra}


def read_json(path: Path) -> dict:
    """Read and parse a JSON file. Returns empty dict if missing."""
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_json(path: Path, data: dict) -> None:
    """Write dict as JSON atomically."""
    atomic_write(path, json.dumps(data, indent=2, default=str))


def word_count(text: str) -> int:
    return len(text.split())


def count_requirements(text: str) -> int:
    """Count REQ-NNN patterns in PRD text."""
    return len(set(re.findall(r'REQ-\d{3}', text)))


def has_section(text: str, heading: str) -> bool:
    """Check if markdown heading exists (case-insensitive)."""
    pattern = r'^#{1,3}\s+.*' + re.escape(heading) + r'.*$'
    return bool(re.search(pattern, text, re.MULTILINE | re.IGNORECASE))


def get_section_content(text: str, heading: str) -> str:
    """Extract content under a markdown heading until next same-level heading."""
    lines = text.split('\n')
    capturing = False
    level = 0
    content = []
    heading_re = re.compile(r'^(#{1,6})\s+(.*)')
    for line in lines:
        heading_match = heading_re.match(line)
        if heading_match and heading.lower() in heading_match.group(2).lower():
            capturing = True
            level = len(heading_match.group(1))
            continue
        if capturing:
            if heading_match and len(heading_match.group(1)) <= level:
                break
            content.append(line)
    return '\n'.join(content).strip()


# ─── VAGUE_PATTERNS for validation ───────────────────────────────────────────

VAGUE_WORDS = [
    "fast", "quick", "slow", "good", "bad", "poor",
    "user-friendly", "easy", "simple", "secure", "safe",
    "scalable", "flexible", "performant", "efficient",
]

VAGUE_PATTERN = re.compile(
    r'\b(?:should\s+be\s+|must\s+be\s+|needs?\s+to\s+be\s+)?'
    r'(' + '|'.join(VAGUE_WORDS) + r')\b',
    re.IGNORECASE
)


# ─── Shared taskmaster detection / config / state helpers ─────────────────────

def _detect_taskmaster_method() -> dict:
    """Detect taskmaster: MCP > CLI > none."""
    # Check CLI
    cli_cmd = None
    cli_path = None
    for candidate in ("taskmaster", "task-master"):
        candidate_path = shutil.which(candidate)
        if candidate_path:
            cli_cmd = candidate
            cli_path = candidate_path
            break
    cli_version = None
    if cli_cmd:
        try:
            result = subprocess.run(
                [cli_cmd, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                # task-master --version can print telemetry notices around the
                # semver — extract just the version number.
                import re as _re
                m = _re.search(r"\d+\.\d+\.\d+", result.stdout)
                cli_version = m.group(0) if m else result.stdout.strip().splitlines()[-1]
            else:
                cli_version = None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # MCP detection: check if mcp__task-master-ai tools are available
    # We can't directly test MCP from a script, so we check for config hints
    mcp_available = False
    for config_path in [
        Path.home() / ".claude.json",
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings" / "mcp.json",
        Path.home() / ".config" / "claude-code" / "mcp.json",
        Path(".mcp.json"),
    ]:
        if config_path.is_file():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                servers = config.get("mcpServers", config.get("servers", {}))
                if any("task-master" in k.lower() for k in servers):
                    mcp_available = True
                    break
            except (json.JSONDecodeError, KeyError):
                pass

    if mcp_available:
        return {"method": "mcp", "version": None, "path": None}
    elif cli_path:
        return {"method": "cli", "version": cli_version, "path": cli_path, "command": cli_cmd}
    else:
        return {"method": "none", "version": None, "path": None}


def _read_taskmaster_model(role: str) -> dict:
    """Read one role from .taskmaster/config.json, if present."""
    config_path = TASKMASTER_DIR / "config.json"
    if not config_path.is_file():
        return {}
    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        return {}
    model = config.get("models", {}).get(role, {})
    return model if isinstance(model, dict) else {}


def _read_taskmaster_config() -> dict:
    """Read .taskmaster/config.json if it exists."""
    config_path = TASKMASTER_DIR / "config.json"
    if not config_path.is_file():
        return {}
    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        return {}
    return config if isinstance(config, dict) else {}


def _write_taskmaster_config(config: dict) -> None:
    """Atomically write .taskmaster/config.json."""
    config_path = TASKMASTER_DIR / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(config, indent=2, default=str) + "\n")
    tmp_path.replace(config_path)


def _local_port_open(host: str = "127.0.0.1", port: int = 8765, timeout: float = 0.25) -> bool:
    """Return whether a local TCP endpoint is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _env_file_has_key(env_path: Path, key: str) -> bool:
    if not env_path.is_file():
        return False
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=", re.MULTILINE)
    return bool(pattern.search(env_path.read_text()))


def _ensure_env_entry(env_path: Path, key: str, value: str, comment: str | None = None) -> bool:
    """Append a missing non-secret local env entry. Returns True when changed."""
    if _env_file_has_key(env_path, key):
        return False
    env_path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "\n" if env_path.is_file() and env_path.read_text() and not env_path.read_text().endswith("\n") else ""
    suffix = f' # {comment}' if comment else ""
    with open(env_path, "a") as f:
        f.write(f'{prefix}{key}="{value}"{suffix}\n')
    return True


def _read_env_file_value(env_path: Path, key: str) -> str | None:
    """Read a simple KEY=value entry from an env file."""
    if not env_path.is_file():
        return None
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*['\"]?([^'\"\n#]+)", re.MULTILINE)
    match = pattern.search(env_path.read_text())
    return match.group(1).strip() if match else None


def _detect_perplexity_mcp() -> str | None:
    """Return the detected Perplexity MCP flavor, if configured."""
    for config_path in [
        Path.home() / ".claude.json",
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings" / "mcp.json",
        Path.home() / ".config" / "claude-code" / "mcp.json",
        Path(".mcp.json"),
    ]:
        if config_path.is_file():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                servers = config.get("mcpServers", config.get("servers", {}))
            except (json.JSONDecodeError, KeyError):
                continue
            names = [str(name).lower() for name in servers]
            if any("perplexity-api-free" in name for name in names):
                return "perplexity-api-free-mcp"
            if any("perplexity" in name for name in names):
                return "perplexity-mcp"
    return None


def _is_local_perplexity_free(model: dict) -> bool:
    """Detect TaskMaster research config pointed at the local free Perplexity proxy."""
    provider = str(model.get("provider", "")).lower()
    base_url = str(
        model.get("baseURL")
        or os.environ.get("PERPLEXITY_API_BASE_URL")
        or os.environ.get("PERPLEXITY_API_FREE_BASE_URL")
        or ""
    ).lower()
    local_proxy = (
        "127.0.0.1:8765" in base_url
        or "localhost:8765" in base_url
        or "perplexity-api-free" in base_url
    )
    return provider in {"openai-compatible", "perplexity"} and local_proxy


def _current_taskmaster_tag() -> str:
    """Read the active TaskMaster tag from .taskmaster/state.json."""
    state_path = TASKMASTER_DIR / "state.json"
    if state_path.is_file():
        try:
            with open(state_path) as f:
                state = json.load(f)
            tag = state.get("currentTag")
            if isinstance(tag, str) and tag:
                return tag
        except json.JSONDecodeError:
            pass
    return "master"


def _resolve_tasks_payload(raw: object, tag: str | None = None) -> tuple[list | None, object]:
    """Return the active task list and write-back wrapper for flat or tagged TaskMaster files.

    Resolution order (tagged structures win over a coexisting legacy flat key):
      1. An explicit ``tag`` argument, if that tag exists as ``raw[tag]["tasks"]``.
      2. ``state.json``'s ``currentTag``, if that tag exists as ``raw[tag]["tasks"]``.
      3. The legacy flat top-level ``raw["tasks"]`` list (backward-compat).
      4. The first tagged ``{... : {"tasks": [...]}}`` block found.

    The critical invariant: when a file holds BOTH a legacy flat ``tasks`` key
    AND a tagged structure, an explicit/currentTag selection must operate on the
    tagged block — not silently fall through to the stale flat tasks. The flat
    key is only honored when no requested tag resolves (true legacy files).
    """
    if isinstance(raw, list):
        return raw, {"tasks": raw}
    if not isinstance(raw, dict):
        return None, raw

    # 1 + 2: a requested tag (explicit arg, else currentTag) that actually exists
    # takes precedence over a coexisting legacy flat ``tasks`` key.
    requested = tag if (isinstance(tag, str) and tag) else _current_taskmaster_tag()
    tagged = raw.get(requested)
    if isinstance(tagged, dict) and isinstance(tagged.get("tasks"), list):
        return tagged["tasks"], raw

    # An EXPLICIT tag that does not exist is an error, not a silent flat fallback —
    # otherwise --tag would be a misleading no-op (the BUG2 failure mode).
    if isinstance(tag, str) and tag:
        raise CommandError(
            f"requested tag {tag!r} not found in tasks.json",
            {"available_tags": sorted(
                k for k, v in raw.items()
                if isinstance(v, dict) and isinstance(v.get("tasks"), list)
            )},
        )

    # 3: legacy flat format (no tagged block matched the active tag).
    if isinstance(raw.get("tasks"), list):
        return raw["tasks"], raw

    # 4: first tagged block as a last resort.
    for value in raw.values():
        if isinstance(value, dict) and isinstance(value.get("tasks"), list):
            return value["tasks"], raw
    return None, raw


def _read_execution_state() -> dict:
    """Read crash recovery state from .taskmaster/state/execution-state.json."""
    state_file = TASKMASTER_STATE / "execution-state.json"
    if not state_file.is_file():
        return {"has_incomplete": False}
    try:
        with open(state_file) as f:
            state = json.load(f)
        return {
            "has_incomplete": state.get("status") == "in_progress",
            "last_task": state.get("current_task"),
            "last_subtask": state.get("current_subtask"),
            "mode": state.get("mode"),
            "last_updated": state.get("last_updated"),
            "checkpoint": state.get("last_checkpoint"),
        }
    except (json.JSONDecodeError, KeyError):
        return {"has_incomplete": False}
