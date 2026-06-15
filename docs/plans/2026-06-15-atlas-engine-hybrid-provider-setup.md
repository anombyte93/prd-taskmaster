# Atlas Engine — Hybrid Provider + Setup Layer — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the native Atlas engine generate tasks in parallel with zero API key by adding a keyless CLI-agent provider (`claude -p`/`codex`/`gemini`), a 3-tier hybrid resolver, an `engine` config block, and a setup wizard — the foundation for removing the `task-master` dependency.

**Architecture:** A single `resolve_provider(role)` (new `provider_resolver.py`) chooses per role between three tiers — keyless CLI-agent (new `cli_agent.py`, the net-new piece), raw-key HTTP API (existing `llm_client`), and the agent-plan floor (existing `_agent_*_action`). `NativeBackend` dispatches on the returned `ProviderHandle`; the CLI path drops into the existing `ThreadPoolExecutor` so parallelism is inherited for free. A setup wizard recommends a working keyless default and live-validates it.

**Tech Stack:** Python 3 (stdlib only — `subprocess`, `urllib`, `concurrent.futures`), pytest, argparse CLI, the local `claude`/`codex`/`gemini` CLIs.

**Spec:** `docs/design/2026-06-15-atlas-engine-hybrid-provider-setup.md` (reviewer-approved).

---

## Execution order & prerequisites

Build the chunks **in order**. Dependencies:

| Chunk | Builds | Depends on |
|------|--------|-----------|
| 1 | `engine` config block + `fleet.engine_config()` | — |
| 2 | `cli_agent.py` keyless provider | (telemetry/extractor reuse only) |
| 3 | probe cache + `provider_resolver.py` | 1 |
| 4 | wire resolver into `NativeBackend` | 1, 2, 3 (hard prerequisite) |
| 5 | setup wizard + `validate_setup` refactor | 1, 3 |
| 6 | flip `auto`→native + golden-parity gate → delete task-master | 1–5 (deletion gated on parity GREEN) |

**Process:** fresh subagent per Task, TDD red→green→commit, two-stage review. Chunk 6's physical deletion of `TaskMasterBackend`/`tm_parallel.py` must NOT run until the golden-parity task in Chunk 6 passes.

---


## Chunk 1: engine config block

This chunk adds the `engine` block to the `fleet.json` schema and an `engine_config(cfg=None)` accessor. It is pure parsing/defaults — no provider behavior. The accessor returns the fully-defaulted engine block; `load_fleet_config` merges the engine block into its returned config so downstream chunks can read `cfg["engine"]`. Malformed values fall back silently, matching the rest of the loader.

### Task 1: `engine_config(cfg=None)` accessor with all defaults

The accessor is the single source of truth for engine defaults. Given `None` it returns the pure defaults; given a raw config dict it merges any valid `engine` sub-keys over the defaults, ignoring malformed values (exactly like `load_fleet_config`'s field-by-field validation). `engine_config` accepts *either* a raw loaded JSON dict (`{"engine": {...}}`) *or* a top-level dict that already carries an `engine` key — it reads `cfg.get("engine")` in both cases, so it is safe to call on the output of `load_fleet_config`.

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/fleet.py` — add `DEFAULT_ENGINE_CONFIG`, `PROVIDER_MODE_CHOICES`, `STRUCTURED_JSON_CHOICES` constants after `BACKEND_CHOICES` (line 51); add `engine_config()` function after `_atlas_config_economy()` (after line 72, before `load_fleet_config` at line 75).
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_engine_config.py` (new file).

- [ ] **Step 1: Write the failing test**

Create `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_engine_config.py`:

```python
"""Atlas hybrid provider: engine config block defaults + merge (Chunk 1)."""

import json

import pytest

from prd_taskmaster.fleet import engine_config, load_fleet_config


# ─── engine_config() pure defaults ───────────────────────────────────────────

def test_engine_config_none_returns_full_defaults():
    eng = engine_config(None)
    assert eng["provider_mode"] == "hybrid"
    assert eng["keyless_default"] is None
    assert eng["cli_agent"]["structured_json"] == "auto"
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900
    assert eng["cli_agent"]["per_call_timeout_s"] == 180
    assert eng["cli_agent"]["max_inflight"] is None
    assert eng["concurrency"]["structured_gen"] is None
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_no_arg_returns_full_defaults():
    # Called with no argument at all (cfg defaults to None).
    eng = engine_config()
    assert eng["provider_mode"] == "hybrid"
    assert eng["keyless_default"] is None
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_returns_fresh_copy_not_shared_mutable():
    a = engine_config(None)
    a["provider_mode"] = "MUTATED"
    a["cli_agent"]["probe_cache_ttl_s"] = -999
    b = engine_config(None)
    assert b["provider_mode"] == "hybrid"
    assert b["cli_agent"]["probe_cache_ttl_s"] == 900


# ─── engine_config() merges valid overrides ──────────────────────────────────

def test_engine_config_merges_valid_top_level_values():
    raw = {"engine": {"provider_mode": "cli_only", "keyless_default": True}}
    eng = engine_config(raw)
    assert eng["provider_mode"] == "cli_only"
    assert eng["keyless_default"] is True
    # untouched keys keep defaults
    assert eng["cli_agent"]["structured_json"] == "auto"
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_keyless_default_false_is_honored():
    eng = engine_config({"engine": {"keyless_default": False}})
    assert eng["keyless_default"] is False


def test_engine_config_merges_valid_cli_agent_values():
    raw = {"engine": {"cli_agent": {
        "structured_json": "schema",
        "probe_cache_ttl_s": 60,
        "per_call_timeout_s": 30,
        "max_inflight": 4,
    }}}
    eng = engine_config(raw)
    assert eng["cli_agent"]["structured_json"] == "schema"
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 60
    assert eng["cli_agent"]["per_call_timeout_s"] == 30
    assert eng["cli_agent"]["max_inflight"] == 4


def test_engine_config_merges_valid_concurrency_values():
    raw = {"engine": {"concurrency": {"structured_gen": 8, "ram_aware": True}}}
    eng = engine_config(raw)
    assert eng["concurrency"]["structured_gen"] == 8
    assert eng["concurrency"]["ram_aware"] is True


# ─── engine_config() ignores malformed values (silent fallback) ──────────────

def test_engine_config_malformed_provider_mode_falls_back():
    eng = engine_config({"engine": {"provider_mode": "warp_drive"}})
    assert eng["provider_mode"] == "hybrid"


def test_engine_config_malformed_keyless_default_falls_back():
    # Only true/false/None are valid; a string is malformed -> default None.
    eng = engine_config({"engine": {"keyless_default": "yes"}})
    assert eng["keyless_default"] is None


def test_engine_config_malformed_structured_json_falls_back():
    eng = engine_config({"engine": {"cli_agent": {"structured_json": "telepathy"}}})
    assert eng["cli_agent"]["structured_json"] == "auto"


def test_engine_config_malformed_ints_fall_back():
    raw = {"engine": {"cli_agent": {
        "probe_cache_ttl_s": "soon",     # not an int
        "per_call_timeout_s": 0,          # < 1, invalid
        "max_inflight": -3,               # < 1, invalid (None stays valid via default)
    }}}
    eng = engine_config(raw)
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900
    assert eng["cli_agent"]["per_call_timeout_s"] == 180
    assert eng["cli_agent"]["max_inflight"] is None


def test_engine_config_bool_is_not_accepted_as_int():
    # bool is a subclass of int in Python; ttl must reject True/False.
    eng = engine_config({"engine": {"cli_agent": {"probe_cache_ttl_s": True}}})
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900


def test_engine_config_malformed_ram_aware_falls_back():
    eng = engine_config({"engine": {"concurrency": {"ram_aware": "true"}}})
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_malformed_structured_gen_falls_back():
    eng = engine_config({"engine": {"concurrency": {"structured_gen": "lots"}}})
    assert eng["concurrency"]["structured_gen"] is None


def test_engine_config_non_dict_engine_block_falls_back():
    assert engine_config({"engine": "broken"})["provider_mode"] == "hybrid"
    assert engine_config({"engine": ["not", "a", "dict"]})["provider_mode"] == "hybrid"
    assert engine_config({"engine": 42})["provider_mode"] == "hybrid"


def test_engine_config_non_dict_cli_agent_falls_back():
    eng = engine_config({"engine": {"cli_agent": "nope"}})
    assert eng["cli_agent"]["probe_cache_ttl_s"] == 900


def test_engine_config_non_dict_concurrency_falls_back():
    eng = engine_config({"engine": {"concurrency": 5}})
    assert eng["concurrency"]["ram_aware"] is False


def test_engine_config_missing_engine_key_returns_defaults():
    eng = engine_config({"max_concurrency": 7})
    assert eng["provider_mode"] == "hybrid"


def test_engine_config_non_dict_cfg_returns_defaults():
    assert engine_config("garbage")["provider_mode"] == "hybrid"
    assert engine_config(42)["provider_mode"] == "hybrid"
    assert engine_config([])["provider_mode"] == "hybrid"
```

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_engine_config.py -v
```

Expected: collection or every test errors with `ImportError: cannot import name 'engine_config' from 'prd_taskmaster.fleet'`. (Run from `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public`.)

- [ ] **Step 3: Minimal implementation**

In `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/fleet.py`, add the constants immediately after `BACKEND_CHOICES = {"auto", "taskmaster", "native"}` (line 51):

```python
# ─── Atlas hybrid provider: engine config block (Chunk 1) ─────────────────────
PROVIDER_MODE_CHOICES = {"hybrid", "api_only", "cli_only", "plan_only"}
STRUCTURED_JSON_CHOICES = {"auto", "schema", "prompt"}

DEFAULT_ENGINE_CONFIG = {
    "provider_mode": "hybrid",        # hybrid | api_only | cli_only | plan_only
    "keyless_default": None,          # null until wizard asks; True=CLI-first, False=key-first
    "cli_agent": {
        "structured_json": "auto",    # auto | schema | prompt
        "probe_cache_ttl_s": 900,
        "per_call_timeout_s": 180,
        "max_inflight": None,         # null -> inherit max_concurrency
    },
    "concurrency": {
        "structured_gen": None,       # null -> inherit max_concurrency
        "ram_aware": False,           # reserved for sub-project #2
    },
}
```

Then add the accessor function immediately after `_atlas_config_economy()` (after line 72, the `return val if isinstance(val, str) else None` line, before `def load_fleet_config`):

```python
def _is_pos_int(value):
    """True for a real positive int, excluding bool (bool subclasses int)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def engine_config(cfg=None):
    """Merged `engine` block with all defaults applied (Chunk 1).

    Accepts a raw fleet.json dict OR the output of `load_fleet_config` (both
    carry an `engine` key after this change). Returns a fresh dict every call.
    Malformed values fall back silently, exactly like `load_fleet_config`.
    """
    eng = {
        "provider_mode": DEFAULT_ENGINE_CONFIG["provider_mode"],
        "keyless_default": DEFAULT_ENGINE_CONFIG["keyless_default"],
        "cli_agent": dict(DEFAULT_ENGINE_CONFIG["cli_agent"]),
        "concurrency": dict(DEFAULT_ENGINE_CONFIG["concurrency"]),
    }
    if not isinstance(cfg, dict):
        return eng
    raw = cfg.get("engine")
    if not isinstance(raw, dict):
        return eng

    mode = raw.get("provider_mode")
    if mode in PROVIDER_MODE_CHOICES:
        eng["provider_mode"] = mode

    keyless = raw.get("keyless_default")
    # Only an explicit bool is persisted; None means "wizard hasn't asked".
    if isinstance(keyless, bool):
        eng["keyless_default"] = keyless

    cli = raw.get("cli_agent")
    if isinstance(cli, dict):
        sj = cli.get("structured_json")
        if sj in STRUCTURED_JSON_CHOICES:
            eng["cli_agent"]["structured_json"] = sj
        ttl = cli.get("probe_cache_ttl_s")
        if _is_pos_int(ttl):
            eng["cli_agent"]["probe_cache_ttl_s"] = ttl
        timeout = cli.get("per_call_timeout_s")
        if _is_pos_int(timeout):
            eng["cli_agent"]["per_call_timeout_s"] = timeout
        inflight = cli.get("max_inflight")
        if _is_pos_int(inflight):
            eng["cli_agent"]["max_inflight"] = inflight

    conc = raw.get("concurrency")
    if isinstance(conc, dict):
        sg = conc.get("structured_gen")
        if _is_pos_int(sg):
            eng["concurrency"]["structured_gen"] = sg
        if isinstance(conc.get("ram_aware"), bool):
            eng["concurrency"]["ram_aware"] = conc["ram_aware"]

    return eng
```

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_engine_config.py -v
```

Expected: all 19 tests in the file pass (`19 passed`). No other test files touched.

- [ ] **Step 5: Commit**

```
git add prd_taskmaster/fleet.py tests/core/test_engine_config.py
git commit -m "$(cat <<'EOF'
feat(engine): add engine_config accessor with hybrid-provider defaults

Chunk 1 of the Atlas hybrid provider + setup layer. Pure parsing/defaults:
engine.provider_mode / keyless_default / cli_agent / concurrency, all
defaulted, malformed values fall back silently like load_fleet_config.
No behavior yet — resolver/cli_agent land in later chunks.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

### Task 2: `load_fleet_config` merges the `engine` block into its returned config

Downstream chunks read `cfg["engine"]` off the loaded config. This task makes `load_fleet_config` always include a fully-defaulted `engine` key, populated from the raw file via `engine_config`. Reuses the accessor — no duplicate validation logic (DRY).

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/fleet.py` — in `load_fleet_config` (lines 75-135): seed `cfg["engine"]` with pure defaults at the initial-dict (lines 83-89), and re-merge from the parsed raw file just before `return cfg` (line 135).
- Test: append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_engine_config.py`.

- [ ] **Step 1: Write the failing test**

Append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_engine_config.py`:

```python
# ─── load_fleet_config merges the engine block ───────────────────────────────

def test_load_fleet_config_has_engine_defaults_without_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_fleet_config()
    assert cfg["engine"]["provider_mode"] == "hybrid"
    assert cfg["engine"]["keyless_default"] is None
    assert cfg["engine"]["cli_agent"]["probe_cache_ttl_s"] == 900
    assert cfg["engine"]["concurrency"]["ram_aware"] is False


def test_load_fleet_config_merges_engine_from_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "max_concurrency": 5,
        "engine": {
            "provider_mode": "cli_only",
            "keyless_default": True,
            "cli_agent": {"per_call_timeout_s": 45},
            "concurrency": {"ram_aware": True},
        },
    }))
    cfg = load_fleet_config()
    # legacy keys still work
    assert cfg["max_concurrency"] == 5
    # engine merged
    assert cfg["engine"]["provider_mode"] == "cli_only"
    assert cfg["engine"]["keyless_default"] is True
    assert cfg["engine"]["cli_agent"]["per_call_timeout_s"] == 45
    # untouched engine sub-keys keep defaults
    assert cfg["engine"]["cli_agent"]["probe_cache_ttl_s"] == 900
    assert cfg["engine"]["concurrency"]["ram_aware"] is True


def test_load_fleet_config_engine_malformed_file_falls_back(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text("{not json")
    cfg = load_fleet_config()
    assert cfg["engine"]["provider_mode"] == "hybrid"
    assert cfg["engine"]["keyless_default"] is None


def test_load_fleet_config_engine_invalid_values_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "engine": {
            "provider_mode": "warp_drive",          # invalid -> hybrid
            "keyless_default": "yes",                # invalid -> None
            "cli_agent": {"probe_cache_ttl_s": 0},   # invalid -> 900
            "concurrency": {"structured_gen": -1},   # invalid -> None
        },
    }))
    cfg = load_fleet_config()
    assert cfg["engine"]["provider_mode"] == "hybrid"
    assert cfg["engine"]["keyless_default"] is None
    assert cfg["engine"]["cli_agent"]["probe_cache_ttl_s"] == 900
    assert cfg["engine"]["concurrency"]["structured_gen"] is None


def test_load_fleet_config_engine_block_independent_per_call(tmp_path, monkeypatch):
    # Mutating one returned engine block must not bleed into the next call.
    monkeypatch.chdir(tmp_path)
    a = load_fleet_config()
    a["engine"]["cli_agent"]["probe_cache_ttl_s"] = -1
    b = load_fleet_config()
    assert b["engine"]["cli_agent"]["probe_cache_ttl_s"] == 900


def test_engine_config_accepts_loaded_config(tmp_path, monkeypatch):
    # engine_config() called on load_fleet_config() output is idempotent.
    monkeypatch.chdir(tmp_path)
    d = tmp_path / ".atlas-ai"
    d.mkdir()
    (d / "fleet.json").write_text(json.dumps({
        "engine": {"provider_mode": "api_only"},
    }))
    cfg = load_fleet_config()
    eng = engine_config(cfg)
    assert eng["provider_mode"] == "api_only"
    assert eng["cli_agent"]["structured_json"] == "auto"
```

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_engine_config.py -v -k "load_fleet_config or accepts_loaded_config"
```

Expected: the 6 new `load_fleet_config`/`accepts_loaded_config` tests FAIL with `KeyError: 'engine'` (the loaded config has no `engine` key yet). Task-1 tests still pass.

- [ ] **Step 3: Minimal implementation**

In `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/fleet.py`, seed the engine defaults in the initial `cfg` dict inside `load_fleet_config`. Change the block at lines 83-89:

```python
    cfg = {
        "max_concurrency": DEFAULT_FLEET_CONFIG["max_concurrency"],
        "routing": dict(DEFAULT_ROUTING),
        "experimental_backends": DEFAULT_FLEET_CONFIG["experimental_backends"],
        "token_economy": _atlas_config_economy() or DEFAULT_FLEET_CONFIG["token_economy"],
        "backend": DEFAULT_FLEET_CONFIG["backend"],
    }
```

to:

```python
    cfg = {
        "max_concurrency": DEFAULT_FLEET_CONFIG["max_concurrency"],
        "routing": dict(DEFAULT_ROUTING),
        "experimental_backends": DEFAULT_FLEET_CONFIG["experimental_backends"],
        "token_economy": _atlas_config_economy() or DEFAULT_FLEET_CONFIG["token_economy"],
        "backend": DEFAULT_FLEET_CONFIG["backend"],
        "engine": engine_config(None),
    }
```

Then, at the end of `load_fleet_config`, replace the final `return cfg` (line 135) with a re-merge from the parsed `raw` file:

```python
    cfg["engine"] = engine_config(raw)

    return cfg
```

Note: `raw` is the parsed JSON dict that is in scope at the point of the final return (the function only reaches there after the `isinstance(raw, dict)` guard at lines 97-98). The `engine_config(None)` seed at the top covers the early-return paths (no file / unreadable / not-a-dict), so every return path now carries a valid `engine` key.

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_engine_config.py -v
```

Expected: all tests pass (`25 passed`). Then confirm no regression in the existing loader suite:

```
python3 -m pytest tests/core/test_fleet_config.py -v
```

Expected: `8 passed` (unchanged — the existing tests assert specific keys, none of which is `engine`, so the additive key does not break them).

- [ ] **Step 5: Commit**

```
git add prd_taskmaster/fleet.py tests/core/test_engine_config.py
git commit -m "$(cat <<'EOF'
feat(engine): merge engine block into load_fleet_config output

load_fleet_config now always returns a fully-defaulted cfg["engine"], merged
from .atlas-ai/fleet.json via engine_config(). Every return path (no file,
malformed, valid) carries a valid engine key so downstream chunks can read
cfg["engine"] unconditionally. Existing fleet-config tests unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
```

---

**Chunk 1 done.** Exports added to `prd_taskmaster/fleet.py`: `PROVIDER_MODE_CHOICES`, `STRUCTURED_JSON_CHOICES`, `DEFAULT_ENGINE_CONFIG`, `engine_config(cfg=None)`, and `load_fleet_config(...)["engine"]`. These are the interface later chunks consume — `provider_resolver.resolve_provider` reads `fleet_config["engine"]["provider_mode"]` / `["keyless_default"]`, and `cli_agent` reads `["cli_agent"]["probe_cache_ttl_s"]` / `["per_call_timeout_s"]` / `["structured_json"]`. No provider behavior is introduced here.


---


## Chunk 2: cli_agent keyless provider

**Goal:** New module `prd_taskmaster/cli_agent.py` exposing `generate_json_via_cli(provider, prompt, ...)` — the structured-JSON twin of `llm_client.generate_json()` that shells out to a host model CLI (`claude` / `codex` / `gemini`) using its own session auth (no API key). It reuses `llm_client._extract_json`, applies one parse-retry, emits one `backend="native-cli"` telemetry row per attempt, and raises `CliAgentError(kind, message)` with `kind ∈ {no_cli, spawn_refused, timeout, invalid_json, nonzero_exit}`.

**Contract (shared interface §3):**
```python
def generate_json_via_cli(provider, prompt, *, system="", schema_hint="", model=None,
                          op_class="structured_gen", task_id=None, timeout=180,
                          structured_json="auto") -> dict
```
- `claude`: `claude -p <prompt> --output-format json [--json-schema <schema>]` → stdout is a JSON envelope; `.result` is the model output. When `structured_json="prompt"` or `"auto"` and no schema is supplied, schema flag is omitted and the envelope `.result` is run through `_extract_json`.
- `codex`: `codex exec --skip-git-repo-check -` with prompt on **stdin**; `_extract_json` on stdout.
- `gemini`: `gemini -p <prompt>`; `_extract_json` on stdout.
- All `subprocess.run` calls are **mocked** in tests (capture argv/stdin, feed canned stdout/returncode). No real CLI is ever spawned; no network.

**Design notes baked into the implementation (read before writing code):**
- The `claude --output-format json` envelope is a JSON object whose `result` field carries the model's textual answer. We parse the envelope first; if `--json-schema` was passed, `result` should already be a JSON string/object — we still funnel it through `_extract_json` so a stringified-JSON `result` is normalized uniformly. If the envelope itself is unparseable, that is an `invalid_json` (subject to the one parse-retry).
- "Schema path vs prompt+extract path" (acceptance): schema path = claude WITH `--json-schema`; prompt+extract = codex/gemini (always) and claude when `structured_json != "schema"` or no schema given.
- One parse-retry mirrors `generate_json` (`llm_client.py:246-252`): on first `_extract_json` → `None`, append the corrective instruction to the prompt and respawn **once**; a second failure raises `CliAgentError("invalid_json", ...)`.
- `subprocess.run(..., timeout=timeout)` raising `TimeoutExpired` → `CliAgentError("timeout", ...)`. A non-zero `returncode` → `CliAgentError("nonzero_exit", ...)`. `which(cli)` missing → `CliAgentError("no_cli", ...)`. `OSError`/`FileNotFoundError` on spawn → `CliAgentError("spawn_refused", ...)`.
- Telemetry: one row per spawn attempt via `economy.append_telemetry({...})` with `backend="native-cli"`, fields mirroring `llm_client._telemetry` shape (`ts, op_class, task_id, model, backend, exit, wall_ms, escalated:False, parse_retry, http_status:None`). `exit=0` on parse success, `exit=1` otherwise. Token counts are unavailable from the CLIs so are omitted (matches the no-usage telemetry case in `test_telemetry_rows_written`).

---

### Task 1: Module skeleton — `CliAgentError`, argv builder, telemetry helper

**Files:**
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli_agent.py` (lines 1–80)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py`

- [ ] **Step 1: Write the failing test**

Create `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py`:

```python
"""Chunk 2: cli_agent — keyless CLI-agent structured-JSON provider.

Hermetic: every subprocess.run is monkeypatched (no real claude/codex/gemini),
no network. Telemetry asserted by chdir-ing into tmp_path and reading the
.atlas-ai/telemetry.jsonl the module appends to.
"""

import json
import subprocess

import pytest

from prd_taskmaster import cli_agent as C


# ── A reusable fake for subprocess.run ───────────────────────────────────────
class FakeCompleted:
    """Mimics subprocess.CompletedProcess just enough for cli_agent."""
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_runner(scripted):
    """Return a fake subprocess.run that records calls and replays `scripted`
    (a list of FakeCompleted or Exception instances), one per invocation."""
    calls = []
    seq = list(scripted)

    def fake_run(argv, *args, **kwargs):
        calls.append({"argv": argv, "kwargs": kwargs})
        item = seq.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    fake_run.calls = calls
    return fake_run


# ── Task 1: error shape + argv builders ──────────────────────────────────────

def test_cli_agent_error_has_kind():
    err = C.CliAgentError("timeout", "boom")
    assert err.kind == "timeout"
    assert "boom" in str(err)
    assert isinstance(err, Exception)


def test_build_argv_claude_schema_path():
    argv, stdin = C._build_argv(
        "claude-code", "/bin/claude", "PROMPT", schema_hint='{"type":"object"}',
        structured_json="auto",
    )
    assert argv == ["/bin/claude", "-p", "PROMPT", "--output-format", "json",
                    "--json-schema", '{"type":"object"}']
    assert stdin is None


def test_build_argv_claude_prompt_path_when_no_schema():
    argv, stdin = C._build_argv(
        "claude-code", "/bin/claude", "PROMPT", schema_hint="",
        structured_json="auto",
    )
    assert argv == ["/bin/claude", "-p", "PROMPT", "--output-format", "json"]
    assert stdin is None


def test_build_argv_claude_prompt_mode_forces_no_schema():
    argv, _ = C._build_argv(
        "claude-code", "/bin/claude", "PROMPT", schema_hint='{"x":1}',
        structured_json="prompt",
    )
    assert "--json-schema" not in argv


def test_build_argv_codex_uses_stdin():
    argv, stdin = C._build_argv(
        "codex-cli", "/bin/codex", "PROMPT", schema_hint="", structured_json="auto",
    )
    assert argv == ["/bin/codex", "exec", "--skip-git-repo-check", "-"]
    assert stdin == "PROMPT"


def test_build_argv_gemini():
    argv, stdin = C._build_argv(
        "gemini-cli", "/bin/gemini", "PROMPT", schema_hint="", structured_json="auto",
    )
    assert argv == ["/bin/gemini", "-p", "PROMPT"]
    assert stdin is None


def test_build_argv_unknown_provider_raises_no_cli():
    with pytest.raises(C.CliAgentError) as ei:
        C._build_argv("openrouter", "/bin/x", "P", schema_hint="", structured_json="auto")
    assert ei.value.kind == "no_cli"
```

- [ ] **Step 2: Run it, expect FAIL**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v
```
Expected: collection error / `ModuleNotFoundError: No module named 'prd_taskmaster.cli_agent'` (or, once the file exists but is empty, `AttributeError: module 'prd_taskmaster.cli_agent' has no attribute 'CliAgentError'`).

- [ ] **Step 3: Minimal implementation**

Create `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli_agent.py`:

```python
"""Keyless CLI-agent structured-JSON provider (sub-project #1, Chunk 2).

The structured-JSON twin of llm_client.generate_json(): instead of an HTTP call
against a raw API key, it shells out to a host model CLI (claude / codex / gemini)
using that CLI's own session auth — free, no API key, runs N-parallel inside the
existing NativeBackend ThreadPoolExecutor exactly like N concurrent HTTP calls.

Reuses llm_client._extract_json verbatim and mirrors generate_json's ONE
parse-retry. Emits one telemetry row per spawn attempt with backend="native-cli".
"""

import shutil
import subprocess
import time

from prd_taskmaster.economy import append_telemetry
from prd_taskmaster.llm_client import _extract_json

# provider -> CLI binary name (mirrors providers._SPAWN_PROBE_CLI; kept local to
# avoid a hard import cycle and because cli_agent must run even if probe is stubbed).
_CLI_FOR_PROVIDER = {"claude-code": "claude", "codex-cli": "codex", "gemini-cli": "gemini"}

_RETRY_INSTRUCTION = (
    "\nYour previous output failed json.loads. Return ONLY the JSON, no prose, no fences."
)


class CliAgentError(Exception):
    """kind in {"no_cli", "spawn_refused", "timeout", "invalid_json", "nonzero_exit"}."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def _build_argv(provider, binary, prompt, *, schema_hint, structured_json):
    """Return (argv, stdin_text). stdin_text is None unless the CLI takes the
    prompt on stdin (codex). Raises CliAgentError('no_cli') for unknown providers."""
    p = str(provider or "").lower()
    if p == "claude-code":
        argv = [binary, "-p", prompt, "--output-format", "json"]
        # Schema path: only when a schema is supplied AND prompt-mode not forced.
        if schema_hint and structured_json != "prompt":
            argv += ["--json-schema", schema_hint]
        return argv, None
    if p == "codex-cli":
        return [binary, "exec", "--skip-git-repo-check", "-"], prompt
    if p == "gemini-cli":
        return [binary, "-p", prompt], None
    raise CliAgentError("no_cli", f"provider {provider!r} is not a spawning CLI agent")


def _telemetry(op_class, task_id, model, exit_code, start, parse_retry):
    """One native-cli telemetry row. Mirrors llm_client._telemetry minus usage
    tokens (the CLIs do not surface token counts) and http_status (None)."""
    from datetime import datetime, timezone

    return append_telemetry({
        "ts": datetime.now(timezone.utc).isoformat(),
        "op_class": op_class,
        "task_id": task_id,
        "model": model,
        "backend": "native-cli",
        "exit": exit_code,
        "wall_ms": int((time.monotonic() - start) * 1000),
        "escalated": False,
        "parse_retry": parse_retry,
        "http_status": None,
    })
```

- [ ] **Step 4: Run, expect PASS**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v
```
Expected: `7 passed` (the Task-1 tests). No subprocess is touched yet.

- [ ] **Step 5: Commit**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
git add prd_taskmaster/cli_agent.py tests/core/test_cli_agent.py
git commit -m "feat(cli-agent): CliAgentError + per-provider argv builder

New keyless CLI-agent module skeleton: error shape with .kind, argv/stdin
builder for claude/codex/gemini, native-cli telemetry helper. Schema path
(claude --json-schema) vs prompt path selection. subprocess fully mocked.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `_run_once` — spawn one attempt, parse stdout, classify failures

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli_agent.py` (append `_parse_claude_envelope`, `_run_once`; ~lines 81–150)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py`:

```python
# ── Task 2: _run_once spawn + parse + failure classification ──────────────────

def test_run_once_claude_envelope_result_is_json_string(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    envelope = json.dumps({"type": "result", "result": '{"tasks": [1, 2]}'})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "claude-code", "/bin/claude", "PROMPT", schema_hint="", structured_json="auto",
        model="sonnet", op_class="structured_gen", task_id=3, timeout=180,
    )
    assert out == {"tasks": [1, 2]}
    # captured argv is the claude prompt path
    assert fake.calls[0]["argv"][:2] == ["/bin/claude", "-p"]


def test_run_once_claude_envelope_result_is_object(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    envelope = json.dumps({"result": {"tasks": []}})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
        model="sonnet", op_class="structured_gen", task_id=None, timeout=180,
    )
    assert out == {"tasks": []}


def test_run_once_codex_extract_from_fenced_stdout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    stdout = "Here you go:\n```json\n{\"ok\": true}\n```\n"
    fake = make_runner([FakeCompleted(returncode=0, stdout=stdout)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "codex-cli", "/bin/codex", "P", schema_hint="", structured_json="auto",
        model="gpt-5.2-codex", op_class="structured_gen", task_id=None, timeout=180,
    )
    assert out == {"ok": True}
    # codex carries the prompt on stdin, not argv
    assert fake.calls[0]["kwargs"].get("input") == "P"


def test_run_once_invalid_json_returns_none(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([FakeCompleted(returncode=0, stdout="totally not json")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C._run_once(
        "gemini-cli", "/bin/gemini", "P", schema_hint="", structured_json="auto",
        model=None, op_class="structured_gen", task_id=None, timeout=180,
    )
    assert out is None  # signals the caller to do its one parse-retry


def test_run_once_nonzero_exit_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([FakeCompleted(returncode=2, stdout="", stderr="bad flag")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C._run_once(
            "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
            model=None, op_class="structured_gen", task_id=None, timeout=180,
        )
    assert ei.value.kind == "nonzero_exit"
    assert "bad flag" in str(ei.value)


def test_run_once_timeout_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([subprocess.TimeoutExpired(cmd="claude", timeout=180)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C._run_once(
            "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
            model=None, op_class="structured_gen", task_id=None, timeout=180,
        )
    assert ei.value.kind == "timeout"


def test_run_once_oserror_raises_spawn_refused(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([OSError("nested spawn refused")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C._run_once(
            "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
            model=None, op_class="structured_gen", task_id=None, timeout=180,
        )
    assert ei.value.kind == "spawn_refused"


def test_run_once_emits_one_native_cli_telemetry_row(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    envelope = json.dumps({"result": '{"ok": true}'})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C._run_once(
        "claude-code", "/bin/claude", "P", schema_hint="", structured_json="auto",
        model="sonnet", op_class="structured_gen", task_id=9, timeout=180,
    )
    rows = [json.loads(l) for l in
            (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["backend"] == "native-cli"
    assert rows[0]["exit"] == 0
    assert rows[0]["task_id"] == 9
    assert rows[0]["http_status"] is None
    assert "tokens_in" not in rows[0]


def test_run_once_invalid_json_telemetry_exit_1(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = make_runner([FakeCompleted(returncode=0, stdout="nope")])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C._run_once(
        "gemini-cli", "/bin/gemini", "P", schema_hint="", structured_json="auto",
        model=None, op_class="structured_gen", task_id=None, timeout=180,
    )
    rows = [json.loads(l) for l in
            (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert rows[0]["exit"] == 1
    assert rows[0]["parse_retry"] is False
```

- [ ] **Step 2: Run it, expect FAIL**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v -k "run_once"
```
Expected: `AttributeError: module 'prd_taskmaster.cli_agent' has no attribute '_run_once'` for all `run_once` tests.

- [ ] **Step 3: Minimal implementation**

Append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli_agent.py`:

```python
def _parse_claude_envelope(stdout):
    """claude --output-format json prints a JSON envelope; the model answer is in
    `.result` (a JSON string when --json-schema was used, else free text). Funnel
    `.result` through _extract_json so a stringified-JSON result is normalized.
    Return parsed JSON, or None to signal a parse failure (one retry upstream)."""
    envelope = _extract_json(stdout)
    if isinstance(envelope, dict) and "result" in envelope:
        result = envelope["result"]
        if isinstance(result, (dict, list)):
            return result
        if isinstance(result, str):
            return _extract_json(result)
        return None
    # No envelope (or non-dict): treat the whole stdout as the payload.
    return envelope


def _run_once(provider, binary, prompt, *, schema_hint, structured_json,
              model, op_class, task_id, timeout, parse_retry=False):
    """Spawn the CLI once, parse stdout into JSON. Returns the parsed dict/list,
    or None on a parse failure (caller decides whether to retry). Raises
    CliAgentError for timeout / nonzero_exit / spawn_refused. Emits exactly one
    native-cli telemetry row for this attempt."""
    argv, stdin_text = _build_argv(
        provider, binary, prompt, schema_hint=schema_hint, structured_json=structured_json,
    )
    start = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _telemetry(op_class, task_id, model, 1, start, parse_retry)
        raise CliAgentError("timeout", f"{binary} exceeded {timeout}s timeout")
    except OSError as exc:
        _telemetry(op_class, task_id, model, 1, start, parse_retry)
        raise CliAgentError("spawn_refused", f"{binary} could not spawn: {exc}")

    if completed.returncode != 0:
        _telemetry(op_class, task_id, model, 1, start, parse_retry)
        detail = (completed.stderr or completed.stdout or "").strip()[:400]
        raise CliAgentError("nonzero_exit", f"{binary} exit {completed.returncode}: {detail}")

    if str(provider).lower() == "claude-code":
        result = _parse_claude_envelope(completed.stdout)
    else:
        result = _extract_json(completed.stdout)

    _telemetry(op_class, task_id, model, 0 if result is not None else 1, start, parse_retry)
    return result
```

- [ ] **Step 4: Run, expect PASS**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v
```
Expected: all Task-1 + Task-2 tests pass (16 passed).

- [ ] **Step 5: Commit**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
git add prd_taskmaster/cli_agent.py tests/core/test_cli_agent.py
git commit -m "feat(cli-agent): _run_once spawn + claude envelope parse + failure kinds

One spawn attempt: claude .result envelope unwrap (reuses _extract_json),
codex/gemini direct extract. Classifies TimeoutExpired->timeout,
OSError->spawn_refused, nonzero rc->nonzero_exit. Emits one native-cli
telemetry row (exit 0/1) per attempt. All subprocess mocked.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `generate_json_via_cli` — public entry, no-cli gate, one parse-retry

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli_agent.py` (append public fn; ~lines 151–210)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py`:

```python
# ── Task 3: generate_json_via_cli public entry ───────────────────────────────

def test_generate_json_via_cli_happy_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    envelope = json.dumps({"result": '{"tasks": [{"id": 1}]}'})
    fake = make_runner([FakeCompleted(returncode=0, stdout=envelope)])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C.generate_json_via_cli("claude-code", "Make tasks", task_id=1)
    assert out == {"tasks": [{"id": 1}]}
    assert len(fake.calls) == 1  # one spawn, no retry needed


def test_generate_json_via_cli_no_cli_when_binary_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: None)
    with pytest.raises(C.CliAgentError) as ei:
        C.generate_json_via_cli("claude-code", "P")
    assert ei.value.kind == "no_cli"


def test_generate_json_via_cli_parse_retry_succeeds(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    # First spawn: garbage; second spawn (the one retry): valid.
    fake = make_runner([
        FakeCompleted(returncode=0, stdout="garbage no json"),
        FakeCompleted(returncode=0, stdout='{"ok": true}'),
    ])
    monkeypatch.setattr(C.subprocess, "run", fake)
    out = C.generate_json_via_cli("gemini-cli", "P")
    assert out == {"ok": True}
    assert len(fake.calls) == 2
    # The retry prompt must carry the corrective instruction.
    retry_prompt = fake.calls[1]["argv"][2]  # gemini -p <prompt>
    assert "ONLY the JSON" in retry_prompt


def test_generate_json_via_cli_invalid_json_after_retry_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([
        FakeCompleted(returncode=0, stdout="nope"),
        FakeCompleted(returncode=0, stdout="still nope"),
    ])
    monkeypatch.setattr(C.subprocess, "run", fake)
    with pytest.raises(C.CliAgentError) as ei:
        C.generate_json_via_cli("gemini-cli", "P")
    assert ei.value.kind == "invalid_json"
    assert len(fake.calls) == 2  # exactly one retry, no third spawn


def test_generate_json_via_cli_schema_hint_appended_to_prompt_when_no_schema_flag(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([FakeCompleted(returncode=0, stdout='{"ok": 1}')])
    monkeypatch.setattr(C.subprocess, "run", fake)
    # gemini has no schema flag -> schema_hint must be folded into the prompt text.
    C.generate_json_via_cli("gemini-cli", "Base", schema_hint='{"type":"object"}')
    sent_prompt = fake.calls[0]["argv"][2]
    assert "Base" in sent_prompt
    assert '{"type":"object"}' in sent_prompt


def test_generate_json_via_cli_claude_schema_uses_flag_not_prompt(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([FakeCompleted(returncode=0, stdout=json.dumps({"result": "{}"}))])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C.generate_json_via_cli("claude-code", "Base", schema_hint='{"type":"object"}',
                            structured_json="schema")
    argv = fake.calls[0]["argv"]
    assert "--json-schema" in argv
    # schema goes via the flag, so the prompt slot stays the bare prompt
    assert argv[2] == "Base"


def test_generate_json_via_cli_two_telemetry_rows_on_retry(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([
        FakeCompleted(returncode=0, stdout="bad"),
        FakeCompleted(returncode=0, stdout='{"ok": true}'),
    ])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C.generate_json_via_cli("gemini-cli", "P", task_id=5)
    rows = [json.loads(l) for l in
            (tmp_path / ".atlas-ai" / "telemetry.jsonl").read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["exit"] == 1 and rows[0]["parse_retry"] is False
    assert rows[1]["exit"] == 0 and rows[1]["parse_retry"] is True
    assert all(r["backend"] == "native-cli" for r in rows)
```

- [ ] **Step 2: Run it, expect FAIL**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v -k "generate_json_via_cli"
```
Expected: `AttributeError: module 'prd_taskmaster.cli_agent' has no attribute 'generate_json_via_cli'`.

- [ ] **Step 3: Minimal implementation**

Append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli_agent.py`:

```python
def _has_schema_flag(provider):
    """Only claude exposes a native --json-schema flag today; codex/gemini fold
    the schema into the prompt text."""
    return str(provider or "").lower() == "claude-code"


def generate_json_via_cli(provider, prompt, *, system="", schema_hint="", model=None,
                          op_class="structured_gen", task_id=None, timeout=180,
                          structured_json="auto"):
    """Structured-JSON generation by shelling out to a keyless host CLI.

    Mirrors llm_client.generate_json: builds the full prompt (system + schema for
    CLIs without a schema flag), spawns once, and on a parse failure respawns ONCE
    with the corrective instruction. Raises CliAgentError(kind, message) with
    kind in {no_cli, spawn_refused, timeout, invalid_json, nonzero_exit}. One
    telemetry row (backend=native-cli) per spawn attempt.
    """
    cli = _CLI_FOR_PROVIDER.get(str(provider or "").lower())
    if not cli:
        raise CliAgentError("no_cli", f"provider {provider!r} is not a spawning CLI agent")
    binary = shutil.which(cli)
    if not binary:
        raise CliAgentError("no_cli", f"{cli} binary not on PATH")

    # Assemble the prompt the model sees. The CLI takes no separate system slot,
    # so prepend system. Fold the schema into the prompt only when the CLI has no
    # native schema flag (codex/gemini) or prompt-mode is forced for claude.
    base_prompt = prompt
    if system:
        base_prompt = system + "\n\n" + base_prompt
    use_schema_flag = _has_schema_flag(provider) and structured_json != "prompt"
    if schema_hint and not use_schema_flag:
        base_prompt += "\n\nReturn ONLY valid JSON matching:\n" + schema_hint

    flag_schema = schema_hint if use_schema_flag else ""

    attempt_prompt = base_prompt
    parse_retry = False
    while True:
        result = _run_once(
            provider, binary, attempt_prompt,
            schema_hint=flag_schema, structured_json=structured_json,
            model=model, op_class=op_class, task_id=task_id, timeout=timeout,
            parse_retry=parse_retry,
        )
        if result is not None:
            return result
        if parse_retry:
            raise CliAgentError("invalid_json", "CLI output failed JSON parsing after one retry")
        parse_retry = True
        attempt_prompt = base_prompt + _RETRY_INSTRUCTION
```

- [ ] **Step 4: Run, expect PASS**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v
```
Expected: all tests pass (~23 passed). Then confirm no regression in the reused modules:
```
python3 -m pytest tests/core/test_llm_client.py tests/core/test_economy.py -q
```
Expected: existing suites still green (the new module only imports `_extract_json` + `append_telemetry`, no behavior change).

- [ ] **Step 5: Commit**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
git add prd_taskmaster/cli_agent.py tests/core/test_cli_agent.py
git commit -m "feat(cli-agent): generate_json_via_cli public entry with one parse-retry

Resolves binary via shutil.which (no_cli when absent), folds system+schema into
the prompt for codex/gemini, uses claude --json-schema flag in schema mode, and
mirrors generate_json's single parse-retry (corrective instruction fed back).
Two telemetry rows on a retried call. Closes the keyless structured-JSON gap.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Full-suite guard + idempotency sweep

**Files:**
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py` (no new code — verification gate only)

- [ ] **Step 1: Write the failing test** — N/A (gate task; the contract is already covered). Add one belt-and-braces test that the module never touches the network and never spawns when the provider is plan/api-only-shaped:

Append to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_cli_agent.py`:

```python
# ── Task 4: guardrails ───────────────────────────────────────────────────────

def test_generate_json_via_cli_api_provider_is_no_cli(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # an API/plan provider name must never reach a spawn — it is no_cli.
    monkeypatch.setattr(C.subprocess, "run",
                        lambda *a, **k: pytest.fail("must not spawn for api provider"))
    for provider in ("anthropic", "openai", "perplexity", ""):
        with pytest.raises(C.CliAgentError) as ei:
            C.generate_json_via_cli(provider, "P")
        assert ei.value.kind == "no_cli"


def test_codex_prompt_carried_on_stdin_not_argv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(C.shutil, "which", lambda c: "/bin/" + c)
    fake = make_runner([FakeCompleted(returncode=0, stdout='{"ok": true}')])
    monkeypatch.setattr(C.subprocess, "run", fake)
    C.generate_json_via_cli("codex-cli", "SECRET PROMPT", schema_hint='{"x":1}')
    argv = fake.calls[0]["argv"]
    assert "SECRET PROMPT" not in " ".join(argv)        # never on the command line
    assert "SECRET PROMPT" in fake.calls[0]["kwargs"]["input"]  # on stdin
    assert '{"x":1}' in fake.calls[0]["kwargs"]["input"]        # schema folded into stdin
```

- [ ] **Step 2: Run it, expect FAIL/PASS** — these tests should PASS immediately if Task 1–3 are correct (they assert already-implemented behavior). Run to confirm:

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py -v -k "no_cli or stdin"
```
Expected: 2 passed. (If `test_codex_prompt_carried_on_stdin_not_argv` fails, the schema-fold or stdin wiring from Task 3 regressed — fix there, not here.)

- [ ] **Step 3: Minimal implementation** — none required; this task is a guard. If the stdin test fails, the bug is that `codex` schema folding must go through `base_prompt` (already does), so re-verify Task 3's `base_prompt` assembly.

- [ ] **Step 4: Run, expect PASS** — full module + the reused-module regression set + the native-backend suite (which Chunk 6 will wire into, so it must stay green now):

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
python3 -m pytest tests/core/test_cli_agent.py tests/core/test_llm_client.py tests/core/test_economy.py tests/core/test_native_backend.py -q
```
Expected: all green. The cli_agent module is standalone (only `_extract_json` + `append_telemetry` imports), so the other suites are unaffected.

- [ ] **Step 5: Commit**

```
cd /home/anombyte/Shade_Gen/Projects/prd-taskmaster-public
git add tests/core/test_cli_agent.py
git commit -m "test(cli-agent): guardrails — api providers never spawn; codex prompt on stdin

Locks two safety invariants: api/plan provider names short-circuit to no_cli
before any subprocess.run, and the codex prompt+schema travel on stdin (never
on the argv command line). Completes Chunk 2 — keyless CLI-agent provider.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

**Chunk 2 done-when:** `generate_json_via_cli` returns parsed JSON for claude (schema + envelope path), codex (stdin + extract), and gemini (prompt + extract); raises `CliAgentError` with the correct `kind` for `no_cli`/`spawn_refused`/`timeout`/`nonzero_exit`/`invalid_json`; does exactly one parse-retry; writes one `backend="native-cli"` telemetry row per spawn; and every test mocks `subprocess.run` (no real CLI, no network). Downstream chunks consume it as `cli_agent.generate_json_via_cli(handle.provider, prompt, system=..., schema_hint=..., model=handle.model, op_class=op_class, task_id=..., timeout=engine_cfg["cli_agent"]["per_call_timeout_s"], structured_json=engine_cfg["cli_agent"]["structured_json"])` — the shared-interface §3 signature.


---


## Chunk 3: probe cache + provider_resolver

This chunk adds the per-process spawn-probe cache to `providers.py` and builds the net-new `provider_resolver.py` module — the single decision point that picks CLI vs API vs plan-floor per role, honoring `provider_mode` and `keyless_default` exactly as the contract specifies. No subprocess or network is ever touched in these tests: every external fact (`discover_key`, `_probe_spawn_cached`, `_read_taskmaster_model`, `_provider_usable` inputs) is monkeypatched.

**Dependencies:** Chunk 1 must have landed `fleet.engine_config(cfg=None) -> dict` (the merged `engine` block). This chunk imports and calls it. If running this chunk before chunk 1, the resolver tests that pass an explicit `fleet_config` dict will still pass because `engine_config` accepts a pre-loaded cfg; the no-arg path is covered by chunk 1's tests.

---

### Task 1: `providers._probe_spawn_cached(provider, ttl_s)` — per-process TTL cache with failure invalidation

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/providers.py` (add a module-level `_PROBE_CACHE` dict + `_probe_spawn_cached` after `_probe_spawn`, ends at line 146; insert at line 147)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_providers_probe_cache.py` (new)

The cache must: (a) call `_probe_spawn` at most once per provider within `ttl_s`; (b) re-probe after the TTL elapses; (c) **invalidate immediately on a `False` result** regardless of TTL, so a transient spawn refusal never sticks for 900s. Time is read via `time.monotonic()` so the tests control the clock by monkeypatching `time.monotonic`.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_providers_probe_cache.py
"""Per-process spawn-probe cache: _probe_spawn at most once per provider per TTL,
invalidated on the first False result. No real subprocess is ever spawned —
_probe_spawn itself is monkeypatched and time.monotonic is driven by the test."""

import prd_taskmaster.providers as providers


def _reset_cache():
    providers._PROBE_CACHE.clear()


def test_cached_hit_calls_probe_once_within_ttl(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def fake_probe(provider):
        calls["n"] += 1
        return True

    clock = {"t": 1000.0}
    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["t"])

    assert providers._probe_spawn_cached("claude-code", 900) is True
    clock["t"] = 1500.0  # 500s later, still inside the 900s TTL
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert calls["n"] == 1  # second call served from cache


def test_reprobes_after_ttl_expires(monkeypatch):
    _reset_cache()
    calls = {"n": 0}

    def fake_probe(provider):
        calls["n"] += 1
        return True

    clock = {"t": 1000.0}
    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["t"])

    assert providers._probe_spawn_cached("claude-code", 900) is True
    clock["t"] = 1000.0 + 901.0  # just past TTL
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert calls["n"] == 2  # TTL expired -> re-probed


def test_false_result_is_not_cached(monkeypatch):
    _reset_cache()
    calls = {"n": 0}
    results = iter([False, True])  # first probe refuses, second succeeds

    def fake_probe(provider):
        calls["n"] += 1
        return next(results)

    clock = {"t": 1000.0}
    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: clock["t"])

    assert providers._probe_spawn_cached("claude-code", 900) is False
    # Same instant, well inside TTL — a cached False would skip the probe.
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert calls["n"] == 2  # the False was never cached


def test_distinct_providers_are_cached_independently(monkeypatch):
    _reset_cache()
    seen = []

    def fake_probe(provider):
        seen.append(provider)
        return True

    monkeypatch.setattr(providers, "_probe_spawn", fake_probe)
    monkeypatch.setattr(providers.time, "monotonic", lambda: 1000.0)

    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert providers._probe_spawn_cached("codex-cli", 900) is True
    assert providers._probe_spawn_cached("claude-code", 900) is True
    assert seen == ["claude-code", "codex-cli"]  # claude-code second call cached
```

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_providers_probe_cache.py -v
```

Expected: collection/attribute errors — `AttributeError: module 'prd_taskmaster.providers' has no attribute '_PROBE_CACHE'` (and `_probe_spawn_cached`). All four tests FAIL/ERROR.

- [ ] **Step 3: Minimal implementation**

First add the `time` import. The top of `providers.py` currently imports `argparse, os, shutil, subprocess` (lines 3-6). Add `time` alongside them:

```python
import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path
```

Then insert the cache + accessor immediately after `_probe_spawn` (after line 146, before `_resolve_configure_profile`):

```python
# Per-process spawn-probe cache. Keyed by provider -> (monotonic_ts, result).
# Dedupes the 60s probe across the in-process ThreadPoolExecutor fan-out (the
# acceptance-criteria case). Cross-process dedup is out of scope (#1). A False
# result is NEVER stored: a transient nested-spawn refusal must not pin the
# provider off the free path for the whole TTL.
_PROBE_CACHE: dict[str, tuple[float, bool]] = {}


def _probe_spawn_cached(provider: object, ttl_s: int) -> bool:
    """Cached _probe_spawn: at most one real probe per provider per ttl_s.
    True results are cached for ttl_s; False results invalidate the entry so
    the next call re-probes (empirical demote, not a sticky failure)."""
    key = str(provider or "").lower()
    now = time.monotonic()
    entry = _PROBE_CACHE.get(key)
    if entry is not None:
        ts, result = entry
        if now - ts < ttl_s:
            return result
    result = _probe_spawn(provider)
    if result:
        _PROBE_CACHE[key] = (now, result)
    else:
        _PROBE_CACHE.pop(key, None)
    return result
```

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_providers_probe_cache.py -v
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add prd_taskmaster/providers.py tests/core/test_providers_probe_cache.py
git commit -m "feat(providers): per-process spawn-probe cache with failure invalidation

_probe_spawn_cached(provider, ttl_s): module-level dict keyed by provider,
time.monotonic TTL, True cached for ttl_s, False never cached so a transient
nested-spawn refusal re-probes instead of pinning off the free path.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `provider_resolver.ProviderHandle` + plan-floor resolution (the always-true tier)

**Files:**
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/provider_resolver.py` (new)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_provider_resolver.py` (new)

Start with the dataclass and the universal floor: when nothing else is usable, `resolve_provider` returns a `plan` handle. This pins the contract's `ProviderHandle` shape and the "plan floor always" invariant before any tier logic exists.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_provider_resolver.py
"""resolve_provider precedence. Every external fact is monkeypatched — no
subprocess, no network, no real config file is read.

Knobs under test (all default-applied by fleet.engine_config):
  provider_mode   : hybrid | api_only | cli_only | plan_only
  keyless_default : True/null -> CLI-first ; False -> key-first ; floor always
"""

import prd_taskmaster.provider_resolver as pr
from prd_taskmaster.provider_resolver import ProviderHandle


def _engine(provider_mode="hybrid", keyless_default=None, ttl_s=900):
    """A fleet_config dict whose engine block is what the resolver reads."""
    return {
        "engine": {
            "provider_mode": provider_mode,
            "keyless_default": keyless_default,
            "cli_agent": {"probe_cache_ttl_s": ttl_s},
        }
    }


def _patch(monkeypatch, *, role_provider="claude-code", role_model="sonnet",
           usable=True, probe=True, key=None):
    """Wire the four facts resolve_provider consults."""
    monkeypatch.setattr(
        pr, "_read_taskmaster_model",
        lambda role: {"provider": role_provider, "modelId": role_model},
    )
    monkeypatch.setattr(pr, "_provider_usable", lambda *a, **k: usable)
    monkeypatch.setattr(pr, "_probe_spawn_cached", lambda provider, ttl_s: probe)
    monkeypatch.setattr(pr, "discover_key", lambda: key)


def test_handle_is_frozen_dataclass():
    h = ProviderHandle(kind="plan", provider="", role="main", model=None, reason="x")
    assert (h.kind, h.provider, h.role, h.model, h.reason) == ("plan", "", "main", None, "x")
    try:
        h.kind = "cli"
        assert False, "ProviderHandle must be frozen"
    except Exception:
        pass


def test_no_cli_no_key_falls_to_plan_floor(monkeypatch):
    # claude-code role, but spawn probe refuses AND no API key -> plan floor.
    _patch(monkeypatch, usable=True, probe=False, key=None)
    h = pr.resolve_provider("main", fleet_config=_engine())
    assert h.kind == "plan"
    assert h.provider == ""
    assert h.role == "main"


def test_plan_only_mode_always_returns_plan(monkeypatch):
    # Even with a perfectly usable CLI and a key, plan_only forces the floor.
    _patch(monkeypatch, usable=True, probe=True, key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(provider_mode="plan_only"))
    assert h.kind == "plan"
```

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_provider_resolver.py -v
```

Expected: `ModuleNotFoundError: No module named 'prd_taskmaster.provider_resolver'`. All tests ERROR at import.

- [ ] **Step 3: Minimal implementation**

Create the module with the full final resolver (it is small; writing the complete precedence now avoids churn, and Task 3/4 only add tests against it). Note the imports are bound at module scope so tests `monkeypatch.setattr(pr, "<name>", ...)` over them.

```python
# prd_taskmaster/provider_resolver.py
"""Single decision point: pick the provider TIER for one role at gen time.

Three kinds, in contract precedence (keyless_default truthy/null):
  1. cli  — provider_mode in {hybrid, cli_only} AND role provider is a spawning
            CLI AND usable (_provider_usable) AND _probe_spawn_cached() true.
  2. api  — provider_mode in {hybrid, api_only} AND discover_key() returns creds.
  3. plan — always the floor; returned when nothing above is usable.
keyless_default=False swaps tiers 1 and 2. provider_mode=plan_only short-circuits
to plan; cli_only never falls through to api; api_only never tries the CLI.

Nothing here spawns a process or hits the network: it consults
  - _read_taskmaster_model(role)      -> the role's configured provider
  - _provider_usable(...)             -> credential/CLI presence
  - _probe_spawn_cached(provider,ttl) -> empirical nested-spawn check (cached)
  - discover_key()                    -> raw-key API creds
The cli_agent / llm_client actually run the chosen tier downstream.
"""

import os
import shutil
from dataclasses import dataclass

from prd_taskmaster.fleet import engine_config
from prd_taskmaster.lib import _read_taskmaster_model
from prd_taskmaster.llm_client import discover_key
from prd_taskmaster.providers import (
    _SPAWNING_PROVIDERS,
    _provider_usable,
    _probe_spawn_cached,
)


@dataclass(frozen=True)
class ProviderHandle:
    kind: str          # "cli" | "api" | "plan"
    provider: str      # e.g. "claude-code", "anthropic", ""
    role: str          # "main" | "fallback" | "research"
    model: str | None
    reason: str        # human-readable why this tier (telemetry/logs)


def _usability_facts() -> dict:
    """The keyword args _provider_usable expects. discover_key is consulted
    separately for the api tier; here we only need CLI/key presence flags."""
    return {
        "has_claude": shutil.which("claude") is not None,
        "has_codex": shutil.which("codex") is not None,
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "has_perplexity_key": bool(os.environ.get("PERPLEXITY_API_KEY")),
    }


def _try_cli(role: str, provider: str, model, ttl_s: int) -> ProviderHandle | None:
    """CLI tier: spawning provider, usable, and spawn probe passes (cached)."""
    if provider not in _SPAWNING_PROVIDERS:
        return None
    if not _provider_usable(provider, **_usability_facts()):
        return None
    if not _probe_spawn_cached(provider, ttl_s):
        return None
    return ProviderHandle(
        kind="cli", provider=provider, role=role, model=model,
        reason=f"keyless CLI-agent ({provider}) usable + spawn-probe ok",
    )


def _try_api(role: str, model) -> ProviderHandle | None:
    """Raw-key API tier: discover_key found credentials."""
    creds = discover_key()
    if not creds:
        return None
    return ProviderHandle(
        kind="api", provider=creds.get("provider", ""), role=role, model=model,
        reason=f"raw-key API ({creds.get('provider', '')}) via discover_key",
    )


def _plan_floor(role: str, model, reason: str) -> ProviderHandle:
    return ProviderHandle(kind="plan", provider="", role=role, model=model, reason=reason)


def resolve_provider(role, op_class="structured_gen", *, fleet_config=None) -> ProviderHandle:
    """Resolve the provider tier for one role. See module docstring for precedence."""
    engine = engine_config(fleet_config)
    mode = engine.get("provider_mode", "hybrid")
    keyless = engine.get("keyless_default")  # True | False | None
    ttl_s = (engine.get("cli_agent") or {}).get("probe_cache_ttl_s", 900)

    role_cfg = _read_taskmaster_model(role) or {}
    provider = str(role_cfg.get("provider", "")).lower()
    model = role_cfg.get("modelId")

    if mode == "plan_only":
        return _plan_floor(role, model, "provider_mode=plan_only")

    cli_allowed = mode in {"hybrid", "cli_only"}
    api_allowed = mode in {"hybrid", "api_only"}

    # keyless_default False -> key-first; True/None -> CLI-first.
    cli_first = keyless is not False

    if cli_first:
        order = [
            ("cli", lambda: _try_cli(role, provider, model, ttl_s) if cli_allowed else None),
            ("api", lambda: _try_api(role, model) if api_allowed else None),
        ]
    else:
        order = [
            ("api", lambda: _try_api(role, model) if api_allowed else None),
            ("cli", lambda: _try_cli(role, provider, model, ttl_s) if cli_allowed else None),
        ]

    for _name, attempt in order:
        handle = attempt()
        if handle is not None:
            return handle

    return _plan_floor(role, model, f"no usable CLI/API tier (mode={mode})")
```

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_provider_resolver.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```
git add prd_taskmaster/provider_resolver.py tests/core/test_provider_resolver.py
git commit -m "feat(resolver): ProviderHandle + resolve_provider 3-tier precedence

New prd_taskmaster/provider_resolver.py. frozen ProviderHandle(kind/provider/
role/model/reason). resolve_provider consults engine_config + _read_taskmaster_
model + _provider_usable + _probe_spawn_cached + discover_key; plan floor always.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CLI-first and key-first precedence (`keyless_default` truthy/null vs false)

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_provider_resolver.py` (append tests; resolver already complete)
- Test: same file

Locks the contract's core swap: with a spawning CLI usable AND a key present, the tier chosen depends entirely on `keyless_default`.

- [ ] **Step 1: Write the failing test** (append to `test_provider_resolver.py`)

```python
def test_cli_first_when_keyless_default_null(monkeypatch):
    # Both a usable CLI and a key exist; keyless_default unset (None) -> CLI wins.
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(keyless_default=None))
    assert h.kind == "cli"
    assert h.provider == "claude-code"
    assert h.model == "sonnet"


def test_cli_first_when_keyless_default_true(monkeypatch):
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(keyless_default=True))
    assert h.kind == "cli"


def test_key_first_when_keyless_default_false(monkeypatch):
    # Same facts, keyless_default False -> API wins despite the usable CLI.
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(keyless_default=False))
    assert h.kind == "api"
    assert h.provider == "anthropic"


def test_key_first_demotes_to_cli_when_no_key(monkeypatch):
    # keyless_default False but no key present -> still falls to the usable CLI,
    # not the plan floor (api tier missing -> next tier in order).
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True, key=None)
    h = pr.resolve_provider("main", fleet_config=_engine(keyless_default=False))
    assert h.kind == "cli"
```

- [ ] **Step 2: Run it, expect FAIL... or PASS**

```
python3 -m pytest tests/core/test_provider_resolver.py -v -k "keyless or key_first"
```

Because the resolver was written complete in Task 2, these four assertions should already pass. If any FAIL, that is a real precedence bug in Task 2's code — fix the `cli_first`/`order` logic before proceeding. Expected after a correct Task 2: `4 passed`.

- [ ] **Step 3: Minimal implementation** — none required (resolver complete). If Task 2 had a precedence bug, the fix lives in the `cli_first = keyless is not False` line and the `order` lists.

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_provider_resolver.py -v
```

Expected: `7 passed`.

- [ ] **Step 5: Commit**

```
git add tests/core/test_provider_resolver.py
git commit -m "test(resolver): keyless_default flips CLI-first <-> key-first tier order

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: mode gating (`api_only`, `cli_only`) + spawn-refused demote

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_provider_resolver.py` (append)
- Test: same file

Locks the remaining contract branches: `api_only` never touches the CLI, `cli_only` never falls to API, and a usable-but-spawn-refused CLI demotes correctly to the next allowed tier.

- [ ] **Step 1: Write the failing test** (append)

```python
def test_api_only_ignores_usable_cli(monkeypatch):
    # CLI is usable, but api_only must use the key and never the CLI.
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(provider_mode="api_only"))
    assert h.kind == "api"


def test_api_only_with_no_key_falls_to_plan(monkeypatch):
    # api_only + no key -> CLI tier is not allowed, so plan floor (not cli).
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True, key=None)
    h = pr.resolve_provider("main", fleet_config=_engine(provider_mode="api_only"))
    assert h.kind == "plan"


def test_cli_only_ignores_key(monkeypatch):
    # cli_only with a usable CLI uses it even though a key exists.
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=True,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(provider_mode="cli_only"))
    assert h.kind == "cli"


def test_cli_only_with_refused_spawn_falls_to_plan(monkeypatch):
    # cli_only + spawn refused -> api tier not allowed, so plan floor (not api),
    # even with a key present.
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=False,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine(provider_mode="cli_only"))
    assert h.kind == "plan"


def test_spawn_refused_demotes_to_api_in_hybrid(monkeypatch):
    # hybrid, CLI usable per config but _probe_spawn_cached refuses -> demote to
    # the key API tier (the nested-claude gh#11 case). This is the core demote.
    _patch(monkeypatch, role_provider="claude-code", usable=True, probe=False,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine())  # hybrid, keyless null
    assert h.kind == "api"
    assert h.provider == "anthropic"
    assert "spawn" not in h.reason or h.kind == "api"  # reason reflects api tier


def test_non_spawning_role_provider_skips_cli_tier(monkeypatch):
    # Role provider is a raw-key provider (anthropic), not a spawning CLI. The
    # CLI tier is skipped on provider identity; with a key it resolves to api.
    _patch(monkeypatch, role_provider="anthropic", role_model="claude-sonnet-4-20250514",
           usable=True, probe=True, key={"provider": "anthropic"})
    h = pr.resolve_provider("main", fleet_config=_engine())
    assert h.kind == "api"


def test_unusable_cli_demotes_to_api(monkeypatch):
    # Spawning provider in config, probe would pass, but _provider_usable is
    # False (e.g. binary absent) -> demote to api.
    _patch(monkeypatch, role_provider="codex-cli", usable=False, probe=True,
           key={"provider": "anthropic"})
    h = pr.resolve_provider("fallback", fleet_config=_engine())
    assert h.kind == "api"
    assert h.role == "fallback"
```

- [ ] **Step 2: Run it, expect PASS** (resolver complete; these exercise existing branches)

```
python3 -m pytest tests/core/test_provider_resolver.py -v -k "only or refused or non_spawning or unusable"
```

Expected: all pass. If `test_spawn_refused_demotes_to_api_in_hybrid` or `test_api_only_with_no_key_falls_to_plan` FAIL, the demote/mode-gating logic in Task 2 is wrong — the bug is in the per-tier `if cli_allowed`/`if api_allowed` guards inside `order`, not the tests.

- [ ] **Step 3: Minimal implementation** — none expected. If a mode-gating test fails, confirm `_try_cli`/`_try_api` are only invoked when `cli_allowed`/`api_allowed` (the `lambda: ... if <allowed> else None` wrappers in `order`).

- [ ] **Step 4: Run the full module, expect PASS**

```
python3 -m pytest tests/core/test_provider_resolver.py -v
```

Expected: `14 passed`.

- [ ] **Step 5: Commit**

```
git add tests/core/test_provider_resolver.py
git commit -m "test(resolver): mode gating (api_only/cli_only) + spawn-refused demote

Covers: api_only ignores usable CLI; api_only+no-key -> plan; cli_only ignores
key; cli_only+refused -> plan; hybrid spawn-refused demotes to api (gh#11);
non-spawning role provider skips CLI tier; unusable CLI demotes to api.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Full-suite regression gate (no real spawn / network leaked)

**Files:**
- Test: both new test files + the existing core suite

Confirms the probe cache and resolver did not regress sibling modules and — critically — that no test in this chunk spawns a real `claude`/`codex` child or opens a socket.

- [ ] **Step 1: Write the failing test** — none new. This is a verification gate, not a TDD step.

- [ ] **Step 2: Run the two new files + a sanity grep**

```
python3 -m pytest tests/core/test_providers_probe_cache.py tests/core/test_provider_resolver.py -v
```

Expected: `18 passed` (4 + 14).

- [ ] **Step 3: Run the full core suite**

```
python3 -m pytest tests/core/ -q
```

Expected: all prior tests still pass plus the 18 new ones; no errors importing `provider_resolver` (catches a broken chunk-1 `engine_config` contract early).

- [ ] **Step 4: Prove no real subprocess/network was used**

```
python3 -m pytest tests/core/test_providers_probe_cache.py tests/core/test_provider_resolver.py -v -p no:cacheprovider 2>&1 | grep -iE "real|spawn|connect|timeout" || echo "NO REAL EXTERNAL CALLS"
```

Expected: `NO REAL EXTERNAL CALLS` (every external fact was monkeypatched; `_probe_spawn` itself is patched in the cache tests, and the resolver never calls subprocess directly).

- [ ] **Step 5: Commit (only if any incidental fix was needed; otherwise skip)**

```
git add -A
git commit -m "test(chunk3): green full core suite with probe cache + resolver

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

**Chunk 3 done.** Net new: `_PROBE_CACHE` + `_probe_spawn_cached` in `providers.py`; `prd_taskmaster/provider_resolver.py` (`ProviderHandle` + `resolve_provider`). Consumes chunk 1's `fleet.engine_config`. Produces the `ProviderHandle` that chunk's NativeBackend wiring (contract §6) branches on. Total ~330 lines incl. tests.


---


## Chunk 4: wire resolver into NativeBackend

> **PREREQUISITE: Chunks 1, 2 and 3 MUST be merged before any step in this chunk runs.** Step 3 of Task 4.1 adds the imports at `backend.py:15` (`from prd_taskmaster import cli_agent …` and `from prd_taskmaster.provider_resolver import resolve_provider`), so the module will not import until those modules exist. The red/green TDD steps below are **NOT** standalone-runnable without chunks 1/2/3 on the branch — the "expect FAIL" step fails on a missing attribute, not on an ImportError, only because those imports are already present.

**Dependencies (built by sibling chunks):**
- **Chunk 1:** `fleet.engine_config(config)` (the contract accessor the new `_cli_timeout` / `_cli_structured_mode` helpers call) **and** the defaulted `engine.cli_agent` block it returns (`["cli_agent"]["per_call_timeout_s"]`, `["cli_agent"]["structured_json"]`). These helpers are dead without Chunk 1 supplying `fleet.engine_config` + the defaulted `engine.cli_agent` config.
- **Chunk 2:** `cli_agent.generate_json_via_cli(provider, prompt, *, system, schema_hint, model, op_class, task_id, timeout, structured_json) -> dict` and `cli_agent.CliAgentError(kind, message)` — the CLI generation path every `cli`-kind branch dispatches to.
- **Chunk 3:** `from prd_taskmaster.provider_resolver import resolve_provider, ProviderHandle` — `resolve_provider(role)` returns a frozen `ProviderHandle` (`.kind/.provider/.role/.model/.reason`); `kind` is one of `api`/`cli`/`plan`.

**Goal:** Replace the three `if not llm_client.discover_key(): return {…agent_action_required…}` gates in `NativeBackend.parse_prd` / `expand` / `rate` (`backend.py:344-665`) with a single `resolve_provider(role)` dispatch. Three outcomes per handle:

- `handle.kind == "api"` → the existing `llm_client.generate_json` path, unchanged.
- `handle.kind == "cli"` → `cli_agent.generate_json_via_cli(handle.provider, …)` (chunk 1 module).
- `handle.kind == "plan"` → the existing `_agent_*_action(...)` floor packet, never deleted.

The `ThreadPoolExecutor` fan-out (`backend.py:444`) **stays exactly as it is**; the CLI path is only a new branch *inside the per-packet worker* `_expand_packet`. The resolved handle is computed once in `expand()` and threaded into each worker so all N `claude -p` children run concurrently like N HTTP calls.

**Dependencies (already built by sibling chunks — assume importable):**
- Chunk 3: `from prd_taskmaster.provider_resolver import resolve_provider, ProviderHandle` (frozen dataclass with `.kind/.provider/.role/.model/.reason`).
- Chunk 1: `from prd_taskmaster import cli_agent` exposing `generate_json_via_cli(provider, prompt, *, system, schema_hint, model, op_class, task_id, timeout, structured_json) -> dict` and `cli_agent.CliAgentError(kind, message)`.

> **Conventions:** tests in `tests/core/test_native_backend.py`; import `from prd_taskmaster import …`; run `python3 -m pytest tests/core/test_native_backend.py -v`; never spawn a real `claude`/`codex` — monkeypatch `resolve_provider` and `cli_agent.generate_json_via_cli`. Every existing test in that file must still pass (they monkeypatch `discover_key` → truthy, which must keep routing to the `api` branch).

---

### Task 4.1: Thread a resolved handle into parse_prd

Make `parse_prd` resolve the provider for role `"main"` and dispatch. `api` keeps the current behaviour; `cli` calls `cli_agent`; `plan` returns the existing parse floor.

**Files:**
- Modify: `prd_taskmaster/backend.py` — imports (L15), `parse_prd` (L344-419)
- Test: `tests/core/test_native_backend.py`

Steps:

- [ ] **Step 1: Write the failing tests** — append to `tests/core/test_native_backend.py`:

```python
def _stub_handle(kind, provider="", role="main", model=None, reason="test"):
    from prd_taskmaster.provider_resolver import ProviderHandle
    return ProviderHandle(kind=kind, provider=provider, role=role, model=model, reason=reason)


def test_parse_prd_cli_kind_drives_cli_agent(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend, TASKS_SCHEMA_HINT

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n\nREQ-001: Build native backend.")
    # Even if a key existed, cli kind must win — prove the resolver, not discover_key, decides.
    monkeypatch.setattr(llm_client, "discover_key", lambda: {"provider": "anthropic", "key": "k"})
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )

    cli_calls = []

    def fake_cli(provider, prompt, **kwargs):
        cli_calls.append({"provider": provider, "prompt": prompt, **kwargs})
        return _valid_tasks(2)

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)
    # If the api path were taken this would blow up the test.
    monkeypatch.setattr(
        llm_client, "generate_json", lambda *a, **k: pytest.fail("api path taken on cli kind")
    )

    result = NativeBackend().parse_prd(prd, 2, tag="native-tag")

    assert result["ok"] is True
    assert result["task_count"] == 2
    assert result["backend"] == "native"
    assert result["ai"] == "cli"
    assert len(cli_calls) == 1
    assert cli_calls[0]["provider"] == "claude-code"
    assert cli_calls[0]["model"] is None  # plan-kind handle has model=None; contract must thread it through
    assert cli_calls[0]["schema_hint"] == TASKS_SCHEMA_HINT
    assert cli_calls[0]["op_class"] == "structured_gen"
    written = json.loads((tmp_path / ".taskmaster" / "tasks" / "tasks.json").read_text())
    assert [task["id"] for task in written["native-tag"]["tasks"]] == [1, 2]


def test_parse_prd_plan_kind_returns_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend, TASKS_SCHEMA_HINT

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
    monkeypatch.setattr(
        backend_mod.cli_agent,
        "generate_json_via_cli",
        lambda *a, **k: pytest.fail("cli path taken on plan kind"),
    )

    result = NativeBackend().parse_prd(prd, 1, tag="master")

    assert result["ok"] is False
    assert result["agent_action_required"]["op"] == "parse_prd"
    assert result["agent_action_required"]["schema_hint"] == TASKS_SCHEMA_HINT


def test_parse_prd_cli_agent_error_falls_back_to_plan(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    prd = tmp_path / "prd.md"
    prd.write_text("# PRD\n")
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )

    def boom(provider, prompt, **kwargs):
        raise backend_mod.cli_agent.CliAgentError("spawn_refused", "nested claude refused")

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", boom)

    result = NativeBackend().parse_prd(prd, 1, tag="master")

    assert result["ok"] is False
    # CLI failure must demote to the plan floor, not hard-error.
    assert result["agent_action_required"]["op"] == "parse_prd"
```

- [ ] **Step 2: Run it, expect FAIL** —
  `python3 -m pytest tests/core/test_native_backend.py -v -k "parse_prd_cli_kind or parse_prd_plan_kind or parse_prd_cli_agent_error"`
  Expected: collection error or failures — `AttributeError: module 'prd_taskmaster.backend' has no attribute 'resolve_provider'` (and `cli_agent`). The existing dispatch still keys off `discover_key`, so the new branches don't exist yet.

- [ ] **Step 3: Minimal implementation** — wire the imports and refactor `parse_prd`.

  In `backend.py` extend the import block (L15) so `resolve_provider` and `cli_agent` are module attributes (monkeypatch-able):

```python
from prd_taskmaster import cli_agent, fleet, llm_client, parallel, taskmaster, tm_parallel
from prd_taskmaster.provider_resolver import resolve_provider
```

  Replace the head of `parse_prd` (current L344-350, the `if not llm_client.discover_key(): return {…}` block) with a resolve-and-dispatch that reads the PRD first, then routes. Replace **L344-419** with:

```python
    def parse_prd(self, prd_path, num_tasks, tag=None) -> dict:
        handle = resolve_provider("main")
        if handle.kind == "plan":
            return {
                "ok": False,
                "agent_action_required": _agent_parse_action(prd_path, num_tasks, tag),
            }

        path = Path(prd_path)
        try:
            prd_text = path.read_text()
        except OSError as exc:
            return {"ok": False, "error": f"failed to read PRD: {exc}", "prd_path": str(path)}

        config = fleet.load_fleet_config()
        profile = economy_profile(config)
        tier = profile.get("structured_gen_start", "standard")
        prompt = (
            f"Parse this PRD into exactly {num_tasks} TaskMaster-compatible tasks.\n"
            f"Target tag: {tag or parallel.current_tag(None)}.\n"
            "Return only the tasks JSON object.\n\n"
            f"PRD PATH: {path}\n"
            f"PRD:\n{prd_text}"
        )
        system = (
            "You are the prd-taskmaster native backend. Generate strict JSON for "
            "the Native Mode tasks.json path."
        )

        telemetry_ref = None
        if handle.kind == "cli":
            try:
                candidate = cli_agent.generate_json_via_cli(
                    handle.provider,
                    prompt,
                    system=system,
                    schema_hint=TASKS_SCHEMA_HINT,
                    model=handle.model,
                    op_class="structured_gen",
                    timeout=_cli_timeout(config),
                    structured_json=_cli_structured_mode(config),
                )
            except cli_agent.CliAgentError:
                return {
                    "ok": False,
                    "agent_action_required": _agent_parse_action(prd_path, num_tasks, tag),
                }
            ai_label = "cli"
        else:
            try:
                generated = llm_client.generate_json(
                    prompt,
                    system=system,
                    schema_hint=TASKS_SCHEMA_HINT,
                    tier=tier,
                    op_class="structured_gen",
                    return_telemetry_ref=True,
                )
            except llm_client.LLMError as exc:
                if exc.kind == "no_key":
                    return {
                        "ok": False,
                        "agent_action_required": _agent_parse_action(prd_path, num_tasks, tag),
                    }
                return {"ok": False, "error": str(exc), "kind": exc.kind, "backend": "native"}
            if isinstance(generated, tuple) and len(generated) == 2:
                candidate, telemetry_ref = generated
            else:
                candidate = generated
            ai_label = "api"

        try:
            tasks, validation = _validate_task_candidate(candidate)
        except CommandError as exc:
            result = {"ok": False, "error": exc.message, "backend": "native"}
            result.update(exc.extra)
            return result
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "native"}

        try:
            resolved = _write_tasks_into_tag(tasks, tag)
        except Exception as exc:
            return {"ok": False, "error": f"failed to write tasks: {exc}", "backend": "native"}

        result = {
            "ok": True,
            "task_count": len(tasks),
            "tag": resolved,
            "backend": "native",
            "ai": ai_label,
            "validation": validation,
        }
        if telemetry_ref is not None:
            result["telemetry_ref"] = telemetry_ref
        return result
```

  Add two small config helpers near the top of the module body (just after `_report_candidates`, ~L301), reading the shared `engine` block via the contract accessor `fleet.engine_config`:

```python
def _cli_timeout(config: dict | None = None) -> int:
    return int(fleet.engine_config(config)["cli_agent"]["per_call_timeout_s"])


def _cli_structured_mode(config: dict | None = None) -> str:
    return str(fleet.engine_config(config)["cli_agent"]["structured_json"])
```

- [ ] **Step 4: Run, expect PASS** —
  `python3 -m pytest tests/core/test_native_backend.py -v -k "parse_prd"`
  Expected: all `parse_prd*` pass, **including** the pre-existing `test_parse_prd_validates_and_writes_tagged_tasks`, `test_parse_prd_success_echoes_telemetry_reference`, and `test_parse_prd_invalid_candidate_returns_error_without_overwrite` — those monkeypatch `discover_key` truthy, and the real `resolve_provider` must return an `api` handle for them (chunk 3 returns `api` when `discover_key()` is truthy and no usable CLI). If chunk 3 isn't merged yet, those three will route through `resolve_provider`; ensure chunk 3 is on the branch first.

- [ ] **Step 5: Commit** —
  `git add prd_taskmaster/backend.py tests/core/test_native_backend.py`
  `git commit -m "feat(backend): route parse_prd through resolve_provider (api/cli/plan)"` (append the Co-Authored-By trailer)

---

### Task 4.2: Branch _expand_packet on the resolved handle (preserve fan-out)

`expand()` resolves the handle **once** for role `"main"`, decides plan-vs-generate, then fans every packet over the unchanged `ThreadPoolExecutor`. The per-packet worker `_expand_packet` gains a `handle` arg and routes to `cli_agent` when `handle.kind == "cli"`. Parallelism is preserved because each worker independently shells out.

**Files:**
- Modify: `prd_taskmaster/backend.py` — `expand` (L421-479), `_expand_packet` (L481-559)
- Test: `tests/core/test_native_backend.py`

Steps:

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_expand_cli_kind_drives_cli_agent_and_produces_graph(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    tasks_path = _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )
    monkeypatch.setattr(
        llm_client, "generate_json", lambda *a, **k: pytest.fail("api path taken on cli kind")
    )

    cli_calls = []

    def fake_cli(provider, prompt, **kwargs):
        cli_calls.append({"provider": provider, **kwargs})
        return {
            "id": 1,
            "complexityScore": 8,
            "recommendedSubtasks": 2,
            "reasoning": "Needs careful backend integration.",
            "researchNotes": "Reuse parallel.apply_results for the merge.",
            "subtasks": [
                {"title": "Write expansion test", "description": "Cover merge.",
                 "details": "Assert once.", "dependencies": []},
                {"title": "Implement expansion", "description": "Apply packet.",
                 "details": "CLI path.", "dependencies": [1]},
            ],
        }

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is True
    assert result["applied"] == [1]
    assert result["failed"] == []
    assert result["ai"] == "cli"
    assert len(cli_calls) == 1
    assert cli_calls[0]["provider"] == "claude-code"
    merged = json.loads(tasks_path.read_text())
    titles = [s["title"] for s in merged["master"]["tasks"][0]["subtasks"]]
    assert titles == ["Write expansion test", "Implement expansion"]


def test_expand_plan_kind_returns_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
    monkeypatch.setattr(
        backend_mod.cli_agent,
        "generate_json_via_cli",
        lambda *a, **k: pytest.fail("cli path taken on plan kind"),
    )

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is False
    assert result["agent_action_required"]["op"] == "expand"
    assert result["agent_action_required"]["packets"]


def test_expand_cli_kind_fans_out_in_parallel(tmp_path, monkeypatch):
    """Three packets must be in flight concurrently on the cli path."""
    import threading
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task(1), _pending_task(2), _pending_task(3)])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )
    # Force >=3 workers regardless of profile defaults.
    monkeypatch.setattr(backend_mod, "_native_concurrency", lambda n, c, p: max(n, 3))

    barrier = threading.Barrier(3, timeout=5)

    def fake_cli(provider, prompt, **kwargs):
        # If fan-out were serial, the 2nd/3rd never arrive and this times out.
        barrier.wait()
        tid = kwargs["task_id"]
        return {
            "id": tid,
            "complexityScore": 5,
            "recommendedSubtasks": 2,
            "reasoning": "parallel proof",
            "researchNotes": "n/a",
            "subtasks": [
                {"title": "a", "description": "x", "details": "y", "dependencies": []},
                {"title": "b", "description": "x", "details": "y", "dependencies": [1]},
            ],
        }

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)

    result = NativeBackend().expand(tag="master")

    assert result["ok"] is True
    assert sorted(result["applied"]) == [1, 2, 3]
    assert result["ai"] == "cli"
```

- [ ] **Step 2: Run it, expect FAIL** —
  `python3 -m pytest tests/core/test_native_backend.py -v -k "expand_cli or expand_plan"`
  Expected: `AttributeError: module 'prd_taskmaster.backend' has no attribute 'resolve_provider'`, and the parallel test would hang/timeout on the barrier under the unmodified serial-via-api code (it never calls `cli_agent`). All three fail.

- [ ] **Step 3: Minimal implementation** — replace the `discover_key` gate in `expand` and add the `handle` plumb-through + cli branch in `_expand_packet`.

  In `expand` (L421-479), replace the gate block (current L430-435) and the future-submission line (L446) and the trailing `ai` (L478). The full replacement for **L421-479**:

```python
    def expand(self, task_ids=None, research=True, tag=None) -> dict:
        try:
            resolved, pending = _pending_tasks(tag, task_ids)
            packets = parallel.build_packets(pending, missing_only=True)
        except SystemExit as exc:
            return {"ok": False, "error": f"failed to load tasks: {exc}", "backend": "native"}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "native"}

        handle = resolve_provider("main")
        if handle.kind == "plan":
            return {
                "ok": False,
                "tag": resolved,
                "agent_action_required": _agent_expand_action(resolved, task_ids, packets),
            }
        if not packets:
            return {"ok": True, "tag": resolved, "applied": [], "failed": [], "results": []}

        config = fleet.load_fleet_config()
        profile = economy_profile(config)
        workers = _native_concurrency(len(packets), config, profile)
        outcomes = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._expand_packet, packet, profile, research, handle, config)
                for packet in packets
            ]
            for future in as_completed(futures):
                outcomes.append(future.result())

        outcomes.sort(key=lambda item: str(item.get("task_id")))
        results = [item["result"] for item in outcomes if item.get("ok")]
        failed = [item["task_id"] for item in outcomes if not item.get("ok")]

        if results:
            try:
                applied = parallel.apply_results(results, tag=resolved)
            except SystemExit as exc:
                return {"ok": False, "error": f"failed to apply results: {exc}", "backend": "native"}
            except Exception as exc:
                return {"ok": False, "error": str(exc), "backend": "native"}
        else:
            applied = {
                "ok": False,
                "tag": resolved,
                "applied": [],
                "report": None,
                "needs_more_subtasks": [],
            }

        return {
            **applied,
            "ok": bool(applied.get("ok")) and not failed,
            "failed": failed,
            "results": outcomes,
            "backend": "native",
            "ai": handle.kind,
        }
```

  Then update `_expand_packet` to accept the `handle` and `config`, and add a `cli` short-circuit at the top of the generate logic. The CLI path does **not** run the api tier-escalation ladder (escalation = swap to a more capable API tier, which is meaningless for a single CLI); on `cli` it does one call and emits its own telemetry inside `generate_json_via_cli` (chunk 1 contract item 3). Replace the signature and the first generate block of **L481-510**:

```python
    def _expand_packet(
        self, packet: dict, profile: dict, research: bool, handle: Any, config: dict | None = None
    ) -> dict:
        task_id = packet.get("id")
        start_tier = profile.get("structured_gen_start", "standard")
        prompt = packet.get("prompt", "")
        if not research:
            prompt += "\n\nDo not perform external research; decompose structurally from the task text."
        system = (
            "You are the prd-taskmaster native backend expansion engine. Return "
            "one strict JSON result object for parallel.apply_results."
        )

        if handle.kind == "cli":
            try:
                result = cli_agent.generate_json_via_cli(
                    handle.provider,
                    prompt,
                    system=system,
                    schema_hint=PARALLEL_RESULT_SCHEMA_HINT,
                    model=handle.model,
                    op_class="structured_gen",
                    task_id=task_id,
                    timeout=_cli_timeout(config),
                    structured_json=_cli_structured_mode(config),
                )
            except cli_agent.CliAgentError as exc:
                return {
                    "ok": False,
                    "task_id": task_id,
                    "error": str(exc),
                    "kind": exc.kind,
                    "escalated": False,
                }
            return self._packet_success(packet, result, escalated=False)

        try:
            result = llm_client.generate_json(
                prompt,
                system=system,
                schema_hint=PARALLEL_RESULT_SCHEMA_HINT,
                tier=start_tier,
                op_class="structured_gen",
                task_id=task_id,
            )
            return self._packet_success(packet, result, escalated=False)
        except llm_client.LLMError as exc:
            if exc.kind != "invalid_json":
                return {
                    "ok": False,
                    "task_id": task_id,
                    "error": str(exc),
                    "kind": exc.kind,
                    "escalated": False,
                }
```

  Everything below that (the escalation block L512-559) is unchanged — it is only reached on the `api` path now, since the `cli` branch returns first.

- [ ] **Step 4: Run, expect PASS** —
  `python3 -m pytest tests/core/test_native_backend.py -v -k "expand"`
  Expected: new `expand_cli_*` / `expand_plan_*` pass AND the pre-existing `test_expand_builds_packets_escalates_invalid_json_and_merges_once` passes (it monkeypatches `discover_key` truthy → real `resolve_provider` returns `api` → escalation ladder still exercised, `tier` calls still `["standard", "capable"]`).

- [ ] **Step 5: Commit** —
  `git add prd_taskmaster/backend.py tests/core/test_native_backend.py`
  `git commit -m "feat(backend): cli-kind expansion worker inside the ThreadPoolExecutor fan-out"` (Co-Authored-By trailer)

---

### Task 4.3: Route rate through resolve_provider

`rate` is single-shot like `parse_prd`. Resolve role `"main"`, dispatch api/cli/plan.

**Files:**
- Modify: `prd_taskmaster/backend.py` — `rate` (L580-665)
- Test: `tests/core/test_native_backend.py`

Steps:

- [ ] **Step 1: Write the failing tests** — append:

```python
def _complexity_payload():
    return {
        "complexityAnalysis": [
            {
                "taskId": 1,
                "taskTitle": "Task 1",
                "complexityScore": 5,
                "recommendedSubtasks": 3,
                "expansionPrompt": "Expand Task 1",
                "reasoning": "Moderate implementation work.",
            }
        ]
    }


def test_rate_cli_kind_drives_cli_agent(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("cli", "claude-code", role)
    )
    monkeypatch.setattr(
        llm_client, "generate_json", lambda *a, **k: pytest.fail("api path taken on cli kind")
    )

    cli_calls = []

    def fake_cli(provider, prompt, **kwargs):
        cli_calls.append({"provider": provider, **kwargs})
        return _complexity_payload()

    monkeypatch.setattr(backend_mod.cli_agent, "generate_json_via_cli", fake_cli)

    result = NativeBackend().rate(tag="master")

    assert result["ok"] is True
    assert result["ai"] == "cli"
    assert result["complexityAnalysis"][0]["taskId"] == 1
    assert len(cli_calls) == 1
    assert cli_calls[0]["provider"] == "claude-code"
    report = tmp_path / ".taskmaster" / "reports" / "task-complexity-report.json"
    assert report.is_file()


def test_rate_plan_kind_returns_agent_action_required(tmp_path, monkeypatch):
    from prd_taskmaster import backend as backend_mod
    from prd_taskmaster.backend import NativeBackend

    monkeypatch.chdir(tmp_path)
    _seed_project(tmp_path, [_pending_task()])
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
    monkeypatch.setattr(
        backend_mod.cli_agent,
        "generate_json_via_cli",
        lambda *a, **k: pytest.fail("cli path taken on plan kind"),
    )

    result = NativeBackend().rate(tag="master")

    assert result["ok"] is False
    assert result["agent_action_required"]["op"] == "rate"
    assert "scoring_rubric" in result["agent_action_required"]
```

- [ ] **Step 2: Run it, expect FAIL** —
  `python3 -m pytest tests/core/test_native_backend.py -v -k "rate_cli or rate_plan"`
  Expected: `AttributeError: module 'prd_taskmaster.backend' has no attribute 'resolve_provider'` — the `rate` gate still keys off `discover_key`; both fail.

- [ ] **Step 3: Minimal implementation** — replace the gate in `rate`. Replace **L580-625** (from the `def rate` head through the `except llm_client.LLMError` block):

```python
    def rate(self, tag=None, research=True) -> dict:
        try:
            resolved, tasks = _load_tasks(tag)
        except SystemExit as exc:
            return {"ok": False, "error": f"failed to load tasks: {exc}", "backend": "native"}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "backend": "native"}

        summaries = _task_summaries(tasks)
        handle = resolve_provider("main")
        if handle.kind == "plan":
            return {
                "ok": False,
                "tag": resolved,
                "agent_action_required": _agent_rate_action(resolved, summaries),
            }

        config = fleet.load_fleet_config()
        profile = economy_profile(config)
        tier = profile.get("structured_gen_start", "standard")
        prompt = (
            "Score these TaskMaster tasks and return a TaskMaster-compatible "
            "complexity report.\n"
            f"Research enabled: {bool(research)}\n"
            f"Scoring rubric: {COMPLEXITY_SCORING_RUBRIC}\n\n"
            f"TASK SUMMARIES:\n{json.dumps(summaries, indent=2, default=str)}"
        )
        system = (
            "You are the prd-taskmaster native backend complexity engine. Return "
            "strict JSON in TaskMaster complexity report format."
        )
        if handle.kind == "cli":
            try:
                candidate = cli_agent.generate_json_via_cli(
                    handle.provider,
                    prompt,
                    system=system,
                    schema_hint=COMPLEXITY_REPORT_SCHEMA_HINT,
                    model=handle.model,
                    op_class="structured_gen",
                    timeout=_cli_timeout(config),
                    structured_json=_cli_structured_mode(config),
                )
            except cli_agent.CliAgentError:
                return {
                    "ok": False,
                    "tag": resolved,
                    "agent_action_required": _agent_rate_action(resolved, summaries),
                }
            ai_label = "cli"
        else:
            try:
                candidate = llm_client.generate_json(
                    prompt,
                    system=system,
                    schema_hint=COMPLEXITY_REPORT_SCHEMA_HINT,
                    tier=tier,
                    op_class="structured_gen",
                )
            except llm_client.LLMError as exc:
                if exc.kind == "no_key":
                    return {
                        "ok": False,
                        "tag": resolved,
                        "agent_action_required": _agent_rate_action(resolved, summaries),
                    }
                return {"ok": False, "error": str(exc), "kind": exc.kind, "backend": "native"}
            ai_label = "api"
```

  Then update the success return at the **end of `rate`** (current L657-665) to emit the resolved label — change `"ai": "api"` to `"ai": ai_label`:

```python
        return {
            "ok": True,
            "tag": resolved,
            "report": str(report_path),
            "complexityAnalysis": analysis,
            "raw": report,
            "backend": "native",
            "ai": ai_label,
        }
```

  (The `analysis` extraction, `report` build, and `write_atomic` block at L627-656 are unchanged.)

- [ ] **Step 4: Run, expect PASS** —
  `python3 -m pytest tests/core/test_native_backend.py -v -k "rate"`
  Expected: new `rate_cli_*` / `rate_plan_*` pass AND pre-existing `test_rate_writes_taskmaster_report_from_batched_generation` passes (discover_key truthy → api handle → unchanged behaviour, `ai == "api"`).

- [ ] **Step 5: Commit** —
  `git add prd_taskmaster/backend.py tests/core/test_native_backend.py`
  `git commit -m "feat(backend): route rate through resolve_provider (api/cli/plan)"` (Co-Authored-By trailer)

---

### Task 4.4: Reconcile the legacy no-key test + full backend regression

The pre-existing `test_no_key_operations_return_agent_action_required` (test_native_backend.py:298-323) monkeypatches `discover_key → None` and asserts all three ops return the plan floor. With chunk 3 merged, `resolve_provider` returns a `plan` handle when no key AND no usable CLI — so the test passes unchanged in a CI box with no `claude` on PATH. To make it deterministic regardless of the host (a dev box may have `claude` installed → resolver would pick `cli`), pin the resolver to `plan` explicitly.

**Files:**
- Modify: `tests/core/test_native_backend.py` — `test_no_key_operations_return_agent_action_required` (L298-323)
- Test: same file + full suite

Steps:

- [ ] **Step 1: Make the legacy test host-independent** — add a resolver pin at the top of `test_no_key_operations_return_agent_action_required`, right after the `discover_key` monkeypatch (L305):

```python
    from prd_taskmaster import backend as backend_mod
    monkeypatch.setattr(
        backend_mod, "resolve_provider", lambda role, *a, **k: _stub_handle("plan", role=role)
    )
```

  This guarantees the plan floor is exercised whether or not a CLI is on PATH, matching the test's intent (no-key → plan).

- [ ] **Step 2: Run the whole native-backend file, expect PASS** —
  `python3 -m pytest tests/core/test_native_backend.py -v`
  Expected: every test green — the 8 original tests plus the 8 new dispatch tests (parse cli/plan/error, expand cli/plan/parallel, rate cli/plan).

- [ ] **Step 3: Run the adjacent backend regression, expect PASS** —
  `python3 -m pytest tests/core/test_backend.py tests/core/test_native_backend.py -v`
  Expected: no regressions in the `TaskMasterBackend`/`get_backend` seam — Chunk 4 only touched `NativeBackend` methods and added two module-level helpers + two imports.

- [ ] **Step 4: Full suite sanity, expect PASS** —
  `python3 -m pytest tests/ -q`
  Expected: `passed` with no new failures attributable to backend wiring. (If `provider_resolver` or `cli_agent` aren't yet merged from chunks 1/3, this surfaces an ImportError at `backend.py` import time — that is the integration gate; rebase chunks 1+3 first.)

- [ ] **Step 5: Commit** —
  `git add tests/core/test_native_backend.py`
  `git commit -m "test(backend): pin resolver to plan in legacy no-key test for host independence"` (Co-Authored-By trailer)

---

**Chunk 4 invariants verified by these tests:**
- (a) `cli` kind drives `cli_agent.generate_json_via_cli` and produces a valid graph — `test_parse_prd_cli_kind_drives_cli_agent`, `test_expand_cli_kind_drives_cli_agent_and_produces_graph`, `test_rate_cli_kind_drives_cli_agent`.
- (b) `plan` kind still returns `agent_action_required` — the three `*_plan_kind_*` tests + the pinned legacy test.
- (c) parallel fan-out still occurs for `cli` kind — `test_expand_cli_kind_fans_out_in_parallel` (a 3-way `threading.Barrier` deadlocks unless all three CLI workers run concurrently inside the unchanged `ThreadPoolExecutor`).
- All existing backend tests preserved: untouched assertions still hold because a truthy `discover_key` resolves to an `api` handle (chunk 3), keeping the api branch byte-identical to today.


---


## Chunk 5: setup wizard

Builds `prd_taskmaster/setup_wizard.py` (`run_setup`, `cmd_setup`), wires an `atlas setup`
CLI verb with `--yes` / `--validate`, and refactors `mode_recommend.validate_setup` so its
task-master binary/version checks (checks 1–2) go advisory when `provider_mode != "plan_only"`
(contract item 8). Depends on chunk 1's `fleet.engine_config()` accessor and a
`fleet.save_engine_config()` persister; depends on chunk 4's `resolve_provider`/`ProviderHandle`
ONLY transitively — the wizard never imports the resolver, it reads/writes config + runs a
live probe, so this chunk is independently testable with the other chunks stubbed.

> **Contract dependency:** this chunk calls `fleet.engine_config(cfg=None) -> dict` (returns the
> merged engine block with all defaults) and `fleet.save_engine_config(updates: dict) -> dict`
> (deep-merges `updates` into `fleet.json["engine"]`, writes atomically, returns the new merged
> block). Both are delivered by Chunk 1. If Chunk 1 is not yet merged when you start, add the two
> shims below to `fleet.py` first (they match Chunk 1's contract exactly and Chunk 1 will replace
> them — coordinate on the merge):
>
> ```python
> # fleet.py — Chunk-1 contract shims (remove once Chunk 1 lands the real versions)
> _ENGINE_DEFAULTS = {
>     "provider_mode": "hybrid",
>     "keyless_default": None,
>     "cli_agent": {"structured_json": "auto", "probe_cache_ttl_s": 900,
>                   "per_call_timeout_s": 180, "max_inflight": None},
>     "concurrency": {"structured_gen": None, "ram_aware": False},
> }
>
> def engine_config(cfg=None) -> dict:
>     import copy
>     merged = copy.deepcopy(_ENGINE_DEFAULTS)
>     raw = (cfg or load_fleet_config()).get("engine") if isinstance(cfg, dict) else None
>     if raw is None and FLEET_CONFIG_PATH.is_file():
>         try:
>             raw = json.loads(FLEET_CONFIG_PATH.read_text()).get("engine")
>         except (json.JSONDecodeError, OSError):
>             raw = None
>     if isinstance(raw, dict):
>         for k, v in raw.items():
>             if isinstance(v, dict) and isinstance(merged.get(k), dict):
>                 merged[k].update(v)
>             elif k in merged:
>                 merged[k] = v
>     return merged
>
> def save_engine_config(updates: dict) -> dict:
>     path = FLEET_CONFIG_PATH
>     path.parent.mkdir(parents=True, exist_ok=True)
>     try:
>         doc = json.loads(path.read_text()) if path.is_file() else {}
>     except (json.JSONDecodeError, OSError):
>         doc = {}
>     if not isinstance(doc, dict):
>         doc = {}
>     engine = doc.get("engine") if isinstance(doc.get("engine"), dict) else {}
>     for k, v in updates.items():
>         if isinstance(v, dict) and isinstance(engine.get(k), dict):
>             engine[k].update(v)
>         else:
>             engine[k] = v
>     doc["engine"] = engine
>     tmp = path.with_suffix(".json.tmp")
>     tmp.write_text(json.dumps(doc, indent=2))
>     tmp.replace(path)
>     return engine_config(doc)
> ```

---

### Task 1: Refactor `validate_setup` — task-master checks go advisory in non-plan_only mode

The keyless engine must not fail its own validator on the `task-master` binary it is removing.
Checks 1 (`binary`) and 2 (`version`) become `severity: "advisory"` (excluded from
`critical_failures`) when `provider_mode != "plan_only"`. In `plan_only` mode they keep current
behavior. `validate_setup` gains a `provider_mode` parameter (default read from
`fleet.engine_config()`) so tests inject it without a config file.

**Files:**
- Modify: `prd_taskmaster/mode_recommend.py` (signature at line 367; check 1 at lines 404–413; check 2 at lines 417–428; aggregation at lines 563–582; add import)
- Test: `tests/core/test_mode_recommend_validate.py` (Create)

- [ ] **Step 1: Write the failing test**

  Create `tests/core/test_mode_recommend_validate.py`:
  ```python
  """validate_setup: task-master binary/version checks are advisory in hybrid mode."""
  import json

  import pytest

  from prd_taskmaster import mode_recommend


  def _no_taskmaster(monkeypatch):
      """No task-master binary on PATH, no claude/codex either."""
      monkeypatch.setattr(mode_recommend.shutil, "which", lambda name: None)

  def _seed_config(tmp_path, main_provider="claude-code"):
      tm = tmp_path / ".taskmaster"
      tm.mkdir(parents=True, exist_ok=True)
      (tm / "config.json").write_text(json.dumps({
          "models": {
              "main": {"provider": main_provider, "modelId": "sonnet"},
              "research": {"provider": "perplexity", "modelId": "sonar"},
              "fallback": {"provider": "codex-cli", "modelId": "gpt-5.2-codex"},
          }
      }))


  def test_hybrid_mode_does_not_hard_fail_on_missing_taskmaster(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _seed_config(tmp_path)
      _no_taskmaster(monkeypatch)
      # claude usable so provider_main passes; only the task-master checks would fail.
      monkeypatch.setattr(mode_recommend.shutil, "which",
                          lambda name: "/usr/bin/claude" if name == "claude" else None)

      result = mode_recommend.validate_setup(provider_mode="hybrid")

      binary = next(c for c in result["checks"] if c["id"] == "binary")
      version = next(c for c in result["checks"] if c["id"] == "version")
      assert binary["severity"] == "advisory"
      assert version["severity"] == "advisory"
      # binary/version are NOT in critical_failures even though they "failed"
      assert not binary["passed"]
      assert result["critical_failures"] == 0
      assert result["ready"] is True


  def test_plan_only_mode_still_hard_fails_on_missing_taskmaster(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _seed_config(tmp_path)
      _no_taskmaster(monkeypatch)

      result = mode_recommend.validate_setup(provider_mode="plan_only")

      binary = next(c for c in result["checks"] if c["id"] == "binary")
      assert binary.get("severity") != "advisory"
      assert not binary["passed"]
      assert result["critical_failures"] >= 1
      assert result["ready"] is False


  def test_default_provider_mode_reads_engine_config_hybrid(tmp_path, monkeypatch):
      """No explicit provider_mode → engine_config() default 'hybrid' → advisory."""
      monkeypatch.chdir(tmp_path)
      _seed_config(tmp_path)
      monkeypatch.setattr(mode_recommend.shutil, "which",
                          lambda name: "/usr/bin/claude" if name == "claude" else None)

      result = mode_recommend.validate_setup()  # no arg → engine_config default

      binary = next(c for c in result["checks"] if c["id"] == "binary")
      assert binary["severity"] == "advisory"
      assert result["ready"] is True
  ```

- [ ] **Step 2: Run it, expect FAIL**
  ```
  python3 -m pytest tests/core/test_mode_recommend_validate.py -v
  ```
  Expected: `TypeError: validate_setup() got an unexpected keyword argument 'provider_mode'`
  for all three tests (the parameter does not exist yet).

- [ ] **Step 3: Minimal implementation**

  In `prd_taskmaster/mode_recommend.py`, add the engine_config import after the existing
  `from prd_taskmaster.providers import (...)` block (around line 25):
  ```python
  from prd_taskmaster.fleet import engine_config
  ```

  Change the signature (line 367) from:
  ```python
  def validate_setup() -> dict:
  ```
  to:
  ```python
  def validate_setup(provider_mode: str | None = None) -> dict:
  ```

  Immediately inside the function (just before `checks = []` at line 384) add:
  ```python
      if provider_mode is None:
          provider_mode = engine_config().get("provider_mode", "hybrid")
      # When the engine is NOT plan_only it no longer depends on the task-master
      # binary (sub-project #1 removes it), so its presence/version is advisory,
      # not a critical gate. plan_only keeps the binary as a hard requirement.
      taskmaster_advisory = provider_mode != "plan_only"
  ```

  Replace check 1 (the `binary` check, lines 404–413) with:
  ```python
      checks.append({
          "id": "binary",
          "name": "task-master CLI installed",
          "passed": bool(cli_path),
          "detail": (
              f"Found at {cli_path} (version {cli_version})" if cli_path
              else (
                  "Not found in PATH (advisory: engine no longer requires it)"
                  if taskmaster_advisory else "Not found in PATH"
              )
          ),
          "fix": (
              None if cli_path or taskmaster_advisory
              else "npm install -g task-master-ai"
          ),
          **({"severity": "advisory"} if taskmaster_advisory else {}),
      })
  ```

  Replace check 2 (the `version` check, lines 417–428) with:
  ```python
      version_info = _check_taskmaster_version(cli_path)
      checks.append({
          "id": "version",
          "name": f"task-master version >= {TASKMASTER_MIN_VERSION}",
          "passed": version_info["supported"],
          "detail": (
              f"detected {version_info['detected_version']} (min {TASKMASTER_MIN_VERSION})"
              if version_info.get("detected_version")
              else "version not detectable"
          ),
          "fix": (
              None if version_info["supported"] or taskmaster_advisory
              else "npm install -g task-master-ai@latest"
          ),
          "severity": "advisory" if taskmaster_advisory else "warning",
      })
  ```

  Update the aggregation (lines 563–567). The `critical_failures` filter already excludes
  `severity == "warning"`; extend it to exclude `"advisory"` too:
  ```python
      # Aggregate — neither "warning" nor "advisory" failures are "critical"
      _non_critical = {"warning", "advisory"}
      critical_failures = [
          c for c in checks
          if not c["passed"] and c.get("severity") not in _non_critical
      ]
      all_passed = len(critical_failures) == 0
  ```

- [ ] **Step 4: Run, expect PASS**
  ```
  python3 -m pytest tests/core/test_mode_recommend_validate.py -v
  ```
  Expected: `3 passed`. Then guard the existing suite:
  ```
  python3 -m pytest tests/core/ -q -k "validate or capabilit or prerelaunch"
  ```
  Expected: all pass (the `provider_mode=None` default + `engine_config()` "hybrid" is the new
  behavior; if a legacy test asserted `ready is False` on missing task-master it must pass
  `provider_mode="plan_only"` — update it in this commit).

- [ ] **Step 5: Commit**
  ```
  git add prd_taskmaster/mode_recommend.py tests/core/test_mode_recommend_validate.py
  git commit -m "$(cat <<'EOF'
  refactor(validate): task-master binary/version checks advisory off plan_only

  Contract item 8: the keyless hybrid engine no longer depends on the task-master
  binary, so its presence/version is advisory (excluded from critical_failures)
  when provider_mode != plan_only. plan_only keeps the hard gate.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 2: `setup_wizard.run_setup` — Detect&Recommend + the recommendation panel

`run_setup(accept_default=False, validate_only=False)` first builds a recommendation by reusing
`run_detect_providers()` + `detect_capabilities()`, renders a human panel into `result["panel"]`
(list of lines), and returns it. This task delivers ONLY the detect/recommend slice and the
panel; accept/customise/add-key/validate land in Tasks 3–4. `run_setup` is non-interactive in
this task (no `input()`), driven by flags — interactivity is layered behind a guarded `_prompt`
in Task 3.

**Files:**
- Create: `prd_taskmaster/setup_wizard.py`
- Test: `tests/core/test_setup_wizard.py` (Create)

- [ ] **Step 1: Write the failing test**

  Create `tests/core/test_setup_wizard.py`:
  ```python
  """Setup wizard: detect+recommend panel, accept, add-key, validate."""
  import json

  import pytest

  from prd_taskmaster import setup_wizard


  def _stub_detectors(monkeypatch, *, claude=True, codex=True, gemini=False,
                      anthropic_key=False, perplexity_proxy=True):
      """Stub run_detect_providers + detect_capabilities so the panel is deterministic."""
      providers = {
          "main": {"provider": "claude-code" if claude else "anthropic",
                   "status": "detected", "source": "claude CLI"},
          "fallback": {"provider": "codex-cli" if codex else "claude-code",
                       "status": "detected", "source": "codex CLI"},
          "research": {"provider": "perplexity-api-free" if perplexity_proxy else "claude-code",
                       "status": "detected", "source": "proxy"},
      }
      monkeypatch.setattr(setup_wizard, "run_detect_providers",
                          lambda: {"ok": True, "providers": providers})
      caps = {
          "ok": True, "tier": "free",
          "recommended_mode": "C", "recommended_reason": "Plan + Ralph Loop",
          "capabilities": {"codex-cli": codex, "gemini-cli": gemini},
          "has_external_ai_tools": codex or gemini,
      }
      monkeypatch.setattr(setup_wizard, "detect_capabilities", lambda: caps)
      # PATH-based presence flags used by the env-detection line.
      def fake_which(name):
          return {
              "claude": "/usr/bin/claude" if claude else None,
              "codex": "/usr/bin/codex" if codex else None,
              "gemini": "/usr/bin/gemini" if gemini else None,
          }.get(name)
      monkeypatch.setattr(setup_wizard.shutil, "which", fake_which)
      if anthropic_key:
          monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
      else:
          monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


  def test_recommend_panel_lists_each_role_with_reason(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch)
      monkeypatch.setattr(setup_wizard, "_validate", lambda mode: {"ok": True, "ready": True, "checks": []})

      result = setup_wizard.run_setup(accept_default=True)

      panel = "\n".join(result["panel"])
      assert "Atlas detected" in panel
      assert "claude ✓" in panel
      assert "codex ✓" in panel
      assert "gemini ✗" in panel
      assert "main" in panel and "claude-code" in panel
      assert "fallback" in panel and "codex-cli" in panel
      assert "research" in panel
      assert result["recommendation"]["main"]["provider"] == "claude-code"
      assert result["ok"] is True
  ```

- [ ] **Step 2: Run it, expect FAIL**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v
  ```
  Expected: `ModuleNotFoundError: No module named 'prd_taskmaster.setup_wizard'`.

- [ ] **Step 3: Minimal implementation**

  Create `prd_taskmaster/setup_wizard.py`:
  ```python
  """Setup wizard — `atlas setup`.

  Beats `task-master models --setup`: zero-config recommendation by default, an
  optional guided layer that explains every auto-decision, and a live one-token
  probe per chosen provider BEFORE the pipeline runs (the differentiator).

  Steps: Detect&Recommend → Accept → Customise → Add-key (writes
  engine.keyless_default after asking) → Validate.

  Pure-core `run_setup()` returns a dict (never exits); `cmd_setup` is the CLI
  wrapper. Interactivity is fully guarded behind `accept_default` / `validate_only`
  so the function is non-interactive under --yes and in tests.
  """
  from __future__ import annotations

  import os
  import shutil
  import subprocess

  from prd_taskmaster import fleet
  from prd_taskmaster.lib import _ensure_env_entry  # used in Task 4
  from pathlib import Path  # used in Task 4
  from prd_taskmaster.mode_recommend import detect_capabilities, validate_setup
  from prd_taskmaster.providers import run_configure_providers, run_detect_providers

  # one-token live-probe commands per provider kind (Task 5)
  _PROBE_CMD = {
      "claude-code": ["claude", "-p", "ok"],
      "codex-cli": ["codex", "--version"],
      "gemini-cli": ["gemini", "--version"],
  }
  _PROBE_TIMEOUT = 60


  def _env_flag(name: str) -> bool:
      return bool(os.environ.get(name))


  def _detect_line() -> str:
      """`Atlas detected:  claude ✓  codex ✓  gemini ✗  ANTHROPIC_API_KEY ✗ ...`"""
      def mark(ok: bool) -> str:
          return "✓" if ok else "✗"
      claude = shutil.which("claude") is not None
      codex = shutil.which("codex") is not None
      gemini = shutil.which("gemini") is not None
      akey = _env_flag("ANTHROPIC_API_KEY")
      pkey = _env_flag("PERPLEXITY_API_KEY") or _env_flag("PERPLEXITY_API_BASE_URL")
      return (
          f"Atlas detected:  claude {mark(claude)}   codex {mark(codex)}   "
          f"gemini {mark(gemini)}   ANTHROPIC_API_KEY {mark(akey)}   "
          f"PERPLEXITY {mark(pkey)}"
      )


  _ROLE_REASON = {
      "claude-code": "free via your Claude session, no API key",
      "codex-cli": "separate quota pool, runs in parallel",
      "gemini-cli": "separate quota pool",
      "anthropic": "paid Anthropic API key",
      "perplexity-api-free": "local proxy on :8765",
      "perplexity": "Perplexity API key",
  }


  def _recommend() -> dict:
      """Reuse the zero-config detectors and shape a per-role recommendation."""
      detected = run_detect_providers().get("providers", {})
      caps = detect_capabilities()
      recommendation = {}
      for role in ("main", "fallback", "research"):
          entry = detected.get(role, {})
          provider = entry.get("provider", "")
          recommendation[role] = {
              "provider": provider,
              "modelId": entry.get("modelId"),
              "source": entry.get("source", "-"),
              "reason": _ROLE_REASON.get(provider, entry.get("source", "")),
          }
      return {"recommendation": recommendation, "capabilities": caps}


  def _panel(recommendation: dict, caps: dict) -> list[str]:
      lines = [_detect_line(), ""]
      lines.append("Recommended (zero-config, keyless):")
      for role in ("main", "fallback", "research"):
          rec = recommendation[role]
          model = rec.get("modelId") or ""
          label = f"{rec['provider']}/{model}".rstrip("/")
          lines.append(f"  {role:<9} {label:<28} ← {rec['reason']}")
      lines.append(
          f"Tier: {caps.get('tier', 'free')} — {caps.get('recommended_reason', '')}"
      )
      lines.append("[Enter] accept   [c] customise   [k] add an API key   [v] validate only")
      return lines


  def _validate(mode: str | None) -> dict:
      """Indirection so tests can stub the heavy validate path. Calls the
      refactored validate_setup with the resolved provider_mode."""
      return validate_setup(provider_mode=mode)


  def run_setup(accept_default: bool = False, validate_only: bool = False) -> dict:
      """Drive the wizard. Returns a dict; never exits, never raises on the
      happy path. Non-interactive when accept_default or validate_only is set."""
      rec = _recommend()
      recommendation = rec["recommendation"]
      caps = rec["capabilities"]
      panel = _panel(recommendation, caps)

      result = {
          "ok": True,
          "panel": panel,
          "recommendation": recommendation,
          "tier": caps.get("tier", "free"),
      }
      # Accept / customise / add-key / validate are layered in Tasks 3–4.
      return result
  ```

- [ ] **Step 4: Run, expect PASS**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v
  ```
  Expected: `1 passed`.

- [ ] **Step 5: Commit**
  ```
  git add prd_taskmaster/setup_wizard.py tests/core/test_setup_wizard.py
  git commit -m "$(cat <<'EOF'
  feat(setup): wizard detect+recommend panel (step 1)

  run_setup() reuses run_detect_providers + detect_capabilities to render a
  per-role recommendation panel with reasons. Non-interactive scaffold; accept/
  add-key/validate land next.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3: Accept + Validate steps (+ live one-token probe) and `--yes` non-interactivity

`run_setup` now: on `accept_default` runs `run_configure_providers()` (the repair-on-detect
Accept step) and then the Validate step; `validate_only` runs ONLY validate. Validate =
`validate_setup()` + a **live one-token probe** per chosen spawning provider. `--yes` proves
non-interactive: no `input()` is ever called when `accept_default=True`.

**Files:**
- Modify: `prd_taskmaster/setup_wizard.py` (extend `run_setup`; add `_live_probe`, `_run_validate_step`)
- Test: `tests/core/test_setup_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

  Append to `tests/core/test_setup_wizard.py`:
  ```python
  def test_yes_is_non_interactive_and_configures(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch)
      called = {"configure": 0, "input": 0}
      monkeypatch.setattr(setup_wizard, "run_configure_providers",
                          lambda *a, **k: called.__setitem__("configure", called["configure"] + 1) or
                          {"ok": True, "changed": ["main"], "models": {}})
      monkeypatch.setattr(setup_wizard, "_validate",
                          lambda mode: {"ok": True, "ready": True, "checks": []})
      monkeypatch.setattr(setup_wizard, "_live_probe", lambda provider: {"provider": provider, "ok": True})
      # any input() call must blow the test up
      def boom(*a, **k):
          called["input"] += 1
          raise AssertionError("input() called under --yes")
      monkeypatch.setattr("builtins.input", boom)

      result = setup_wizard.run_setup(accept_default=True)

      assert called["configure"] == 1
      assert called["input"] == 0
      assert result["accepted"] is True
      assert result["validation"]["ready"] is True


  def test_validate_surfaces_forced_auth_failure(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch)
      # validate_setup passes, but the LIVE probe of the chosen provider fails (401/ENOENT).
      monkeypatch.setattr(setup_wizard, "_validate",
                          lambda mode: {"ok": True, "ready": True, "checks": []})

      def fake_run(cmd, **kw):
          class R:
              returncode = 1
              stdout = ""
              stderr = "Error: 401 invalid x-api-key"
          return R()
      monkeypatch.setattr(setup_wizard.subprocess, "run", fake_run)

      result = setup_wizard.run_setup(validate_only=True)

      assert result["validation"]["ready"] is False  # live probe demotes readiness
      probes = result["validation"]["live_probes"]
      assert any(p["ok"] is False and "401" in (p.get("error") or "") for p in probes)


  def test_validate_only_does_not_configure(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch)
      monkeypatch.setattr(setup_wizard, "run_configure_providers",
                          lambda *a, **k: (_ for _ in ()).throw(AssertionError("configure under --validate")))
      monkeypatch.setattr(setup_wizard, "_validate", lambda mode: {"ok": True, "ready": True, "checks": []})
      monkeypatch.setattr(setup_wizard, "_live_probe", lambda provider: {"provider": provider, "ok": True})

      result = setup_wizard.run_setup(validate_only=True)
      assert result.get("accepted") is not True
      assert result["validation"]["ready"] is True
  ```

- [ ] **Step 2: Run it, expect FAIL**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v -k "non_interactive or forced_auth or validate_only"
  ```
  Expected: `KeyError: 'accepted'` / `KeyError: 'validation'` — `run_setup` does not yet add
  those keys or run the steps.

- [ ] **Step 3: Minimal implementation**

  In `prd_taskmaster/setup_wizard.py`, add these helpers above `run_setup`:
  ```python
  def _live_probe(provider: str) -> dict:
      """One-token liveness probe for a chosen provider. Surfaces a real
      401/ENOENT BEFORE the pipeline. Spawning CLIs only; API/proxy providers
      are validated by validate_setup's credential checks, so they pass here."""
      cmd = _PROBE_CMD.get(provider)
      if not cmd:
          return {"provider": provider, "ok": True, "skipped": "no live probe for this provider"}
      binary = shutil.which(cmd[0])
      if not binary:
          return {"provider": provider, "ok": False, "error": f"{cmd[0]} not found in PATH"}
      probe = [binary, *cmd[1:]]
      try:
          proc = subprocess.run(probe, capture_output=True, text=True, timeout=_PROBE_TIMEOUT)
      except (subprocess.TimeoutExpired, OSError) as exc:
          return {"provider": provider, "ok": False, "error": f"probe failed: {exc}"}
      if proc.returncode != 0:
          err = (proc.stderr or proc.stdout or "").strip().splitlines()
          return {"provider": provider, "ok": False, "error": err[-1] if err else f"exit {proc.returncode}"}
      return {"provider": provider, "ok": True}


  def _run_validate_step(recommendation: dict, mode: str | None) -> dict:
      """validate_setup (credential-aware checks) PLUS a live one-token probe per
      chosen provider. A failed live probe demotes `ready` to False — that is the
      'surfaces a real 401 before the pipeline' differentiator."""
      base = _validate(mode)
      probed = set()
      live_probes = []
      for role in ("main", "fallback", "research"):
          provider = recommendation.get(role, {}).get("provider", "")
          if provider in _PROBE_CMD and provider not in probed:
              probed.add(provider)
              live_probes.append(_live_probe(provider))
      live_ok = all(p["ok"] for p in live_probes)
      ready = bool(base.get("ready")) and live_ok
      return {**base, "ready": ready, "live_probes": live_probes}
  ```

  Replace the tail of `run_setup` (everything after `result = {...}` … `return result`) with:
  ```python
      mode = fleet.engine_config().get("provider_mode", "hybrid")

      if validate_only:
          result["validation"] = _run_validate_step(recommendation, mode)
          return result

      if accept_default:
          configured = run_configure_providers()
          result["accepted"] = True
          result["configured"] = configured
          result["validation"] = _run_validate_step(recommendation, mode)
          return result

      # Interactive branch is layered in Task 4 (Customise / Add-key prompts).
      result["validation"] = _run_validate_step(recommendation, mode)
      return result
  ```

- [ ] **Step 4: Run, expect PASS**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v
  ```
  Expected: `4 passed`.

- [ ] **Step 5: Commit**
  ```
  git add prd_taskmaster/setup_wizard.py tests/core/test_setup_wizard.py
  git commit -m "$(cat <<'EOF'
  feat(setup): Accept + Validate steps with live one-token probe

  --yes runs configure-providers + validate non-interactively (no input()).
  --validate runs validate_setup PLUS a live claude -p / codex --version probe
  per chosen provider, demoting `ready` on a real 401/ENOENT before the pipeline.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 4: Add-key step writes `engine.keyless_default` (decision #2 question)

The interactive Add-key step prompts for a key, writes it to `.env` via `_ensure_env_entry`,
then — **only when both a key was added AND a spawning CLI exists** — asks the decision-#2
question ("free-but-slower keyless, or paid-but-faster key, as primary?") and persists
`engine.keyless_default` via `fleet.save_engine_config`. Driven by injected callbacks so it is
fully testable without real stdin.

**Files:**
- Modify: `prd_taskmaster/setup_wizard.py` (add `add_key`)
- Test: `tests/core/test_setup_wizard.py` (append)

- [ ] **Step 1: Write the failing test**

  Append to `tests/core/test_setup_wizard.py`:
  ```python
  def test_add_key_writes_env_and_keyless_flag_when_cli_present(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch, claude=True)  # a spawning CLI exists
      # user supplies a key, then answers "paid" (key as primary) -> keyless_default False
      result = setup_wizard.add_key(
          var="ANTHROPIC_API_KEY",
          ask_value=lambda: "sk-newkey",
          ask_keyless=lambda: False,
      )
      env_text = (tmp_path / ".env").read_text()
      assert 'ANTHROPIC_API_KEY="sk-newkey"' in env_text
      engine = setup_wizard.fleet.engine_config()
      assert engine["keyless_default"] is False
      assert result["keyless_default"] is False
      assert result["asked_keyless"] is True


  def test_add_key_keyless_true_when_user_chooses_keyless(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch, claude=True)
      setup_wizard.add_key(
          var="ANTHROPIC_API_KEY",
          ask_value=lambda: "sk-newkey",
          ask_keyless=lambda: True,
      )
      assert setup_wizard.fleet.engine_config()["keyless_default"] is True


  def test_add_key_does_not_ask_keyless_without_cli(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch, claude=False, codex=False, gemini=False)
      def must_not_ask():
          raise AssertionError("asked keyless question with no CLI present")
      result = setup_wizard.add_key(
          var="ANTHROPIC_API_KEY",
          ask_value=lambda: "sk-newkey",
          ask_keyless=must_not_ask,
      )
      assert result["asked_keyless"] is False
      # flag stays null (unset) — no global default imposed
      assert setup_wizard.fleet.engine_config()["keyless_default"] is None


  def test_add_key_blank_value_is_noop(tmp_path, monkeypatch):
      monkeypatch.chdir(tmp_path)
      _stub_detectors(monkeypatch, claude=True)
      result = setup_wizard.add_key(
          var="ANTHROPIC_API_KEY",
          ask_value=lambda: "   ",
          ask_keyless=lambda: True,
      )
      assert result["ok"] is False
      assert not (tmp_path / ".env").exists() or 'ANTHROPIC_API_KEY' not in (tmp_path / ".env").read_text()
      assert result["asked_keyless"] is False
  ```

- [ ] **Step 2: Run it, expect FAIL**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v -k add_key
  ```
  Expected: `AttributeError: module 'prd_taskmaster.setup_wizard' has no attribute 'add_key'`.

- [ ] **Step 3: Minimal implementation**

  Add to `prd_taskmaster/setup_wizard.py`:
  ```python
  def _has_spawning_cli() -> bool:
      return any(shutil.which(b) for b in ("claude", "codex", "gemini"))


  def add_key(var: str, ask_value, ask_keyless) -> dict:
      """Add-key step (decision #2).

      `ask_value()` returns the raw key string (e.g. an input() call).
      `ask_keyless()` returns True if the user wants the FREE keyless CLI as
      primary, False if the PAID key. Both are injected so the step is testable.

      Writes the key to .env (via _ensure_env_entry — non-secret local append),
      then — only when a key was added AND a spawning CLI exists — asks the
      keyless/paid question and persists engine.keyless_default. With no CLI the
      question is meaningless (only one path exists) so the flag stays unset
      (null) — no global default imposed (decision #2)."""
      value = (ask_value() or "").strip()
      if not value:
          return {"ok": False, "reason": "no key entered", "asked_keyless": False,
                  "keyless_default": fleet.engine_config().get("keyless_default")}

      changed = _ensure_env_entry(Path(".env"), var, value)

      asked = False
      keyless_default = fleet.engine_config().get("keyless_default")
      if _has_spawning_cli():
          asked = True
          # True  → keyless CLI primary  → keyless_default True
          # False → paid key primary     → keyless_default False
          keyless_default = bool(ask_keyless())
          fleet.save_engine_config({"keyless_default": keyless_default})

      return {
          "ok": True,
          "env_changed": changed,
          "var": var,
          "asked_keyless": asked,
          "keyless_default": keyless_default,
      }
  ```

  Wire `add_key` into the interactive branch of `run_setup` (replace the
  `# Interactive branch is layered in Task 4` block). Interactivity reads a single choice via
  an injectable `choose` callback (default `input`), so it remains test-safe:
  ```python
      # Interactive: present the panel, read a one-char choice. The default
      # (Enter / 'a') accepts. 'k' adds a key + asks the decision-#2 question.
      choice = (choose() or "").strip().lower()
      if choice in ("", "a", "accept"):
          configured = run_configure_providers()
          result["accepted"] = True
          result["configured"] = configured
      elif choice in ("k", "key"):
          result["add_key"] = add_key(
              var="ANTHROPIC_API_KEY",
              ask_value=lambda: choose("Paste API key: "),
              ask_keyless=lambda: (choose(
                  "Primary provider? [k]eyless (free) / [p]aid key: ").strip().lower()
                  not in ("p", "paid")),
          )
          configured = run_configure_providers()
          result["accepted"] = True
          result["configured"] = configured
      elif choice in ("c", "customise", "customize"):
          # Customise = repair-on-detect for now (task-master-style picker is a
          # later enhancement); run_configure_providers never clobbers user choices.
          result["configured"] = run_configure_providers()
          result["accepted"] = True
      result["validation"] = _run_validate_step(recommendation, mode)
      return result
  ```

  Update the `run_setup` signature to accept the injectable prompt:
  ```python
  def run_setup(accept_default: bool = False, validate_only: bool = False, choose=None) -> dict:
  ```
  and at the top of the function:
  ```python
      if choose is None:
          choose = input
  ```

- [ ] **Step 4: Run, expect PASS**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v
  ```
  Expected: `8 passed`.

- [ ] **Step 5: Commit**
  ```
  git add prd_taskmaster/setup_wizard.py tests/core/test_setup_wizard.py
  git commit -m "$(cat <<'EOF'
  feat(setup): Add-key step asks decision-#2 question, writes keyless_default

  When a key is added AND a spawning CLI exists, the wizard asks once
  (keyless-free vs paid-key as primary) and persists engine.keyless_default via
  save_engine_config. No CLI → no question, flag stays null (no global default).

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 5: `cmd_setup` + the `atlas setup` CLI subcommand (`--yes`, `--validate`)

Add `cmd_setup` to `setup_wizard.py` and wire the `setup` subparser + DISPATCH entry in
`cli.py`, matching the file's conventions (`sub.add_parser`, `DISPATCH[...]`, `emit`-style
output). The command prints the panel lines to stderr-free stdout-readable form and emits the
result JSON; exit code reflects validation readiness so CI can gate on it.

**Files:**
- Modify: `prd_taskmaster/setup_wizard.py` (add `cmd_setup`)
- Modify: `prd_taskmaster/cli.py` (import line 10-area; subparser after line 184; DISPATCH after line 361)
- Test: `tests/core/test_setup_wizard.py` (append a CLI-level test using the `run_cli` shim)

- [ ] **Step 1: Write the failing test**

  Append to `tests/core/test_setup_wizard.py`:
  ```python
  import os
  import subprocess as _sp
  import sys
  from pathlib import Path as _Path

  REPO_ROOT = _Path(__file__).resolve().parents[2]
  SCRIPT = REPO_ROOT / "script.py"


  def _clean_env(tmp_path):
      env = os.environ.copy()
      for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY"):
          env.pop(k, None)
      bin_dir = tmp_path / "bin"
      bin_dir.mkdir(exist_ok=True)
      env["PATH"] = str(bin_dir)
      env["HOME"] = str(tmp_path / "home")
      return env


  def test_cli_setup_validate_runs_and_emits_json(tmp_path):
      """`script.py setup --validate` exits cleanly and emits a validation block.
      No claude/codex on PATH → live probes are skipped/absent, validate runs."""
      env = _clean_env(tmp_path)
      proc = _sp.run(
          [sys.executable, str(SCRIPT), "setup", "--validate"],
          capture_output=True, text=True, cwd=str(tmp_path), env=env,
      )
      # exit code mirrors readiness; with no project it is not ready -> exit 1.
      assert proc.returncode in (0, 1), proc.stderr
      payload = json.loads(proc.stdout)
      assert "validation" in payload
      assert "panel" in payload
      assert isinstance(payload["panel"], list)


  def test_cli_setup_subcommand_registered():
      """`setup` is a real subcommand (argparse help lists it)."""
      proc = _sp.run(
          [sys.executable, str(SCRIPT), "--help"],
          capture_output=True, text=True, cwd=str(REPO_ROOT),
      )
      assert "setup" in proc.stdout
  ```

- [ ] **Step 2: Run it, expect FAIL**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v -k "cli_setup"
  ```
  Expected: `setup` is not a registered subcommand → argparse exits 2 with
  `invalid choice: 'setup'`; `json.loads` raises / assertion fails.

- [ ] **Step 3: Minimal implementation**

  Add `cmd_setup` to the end of `prd_taskmaster/setup_wizard.py`:
  ```python
  import json
  import sys


  def cmd_setup(args) -> None:
      """CLI wrapper for `atlas setup`. Emits the result JSON; exit code mirrors
      validation readiness (0 = ready, 1 = not ready) so CI / dispatch can gate."""
      result = run_setup(
          accept_default=bool(getattr(args, "yes", False)),
          validate_only=bool(getattr(args, "validate", False)),
      )
      print(json.dumps(result, indent=2, default=str))
      validation = result.get("validation") or {}
      ready = validation.get("ready", True)
      sys.exit(0 if result.get("ok") and ready else 1)
  ```

  In `prd_taskmaster/cli.py`, add the import (after line 11,
  `from prd_taskmaster.providers import ...`):
  ```python
  from prd_taskmaster.setup_wizard import cmd_setup
  ```

  Add the subparser (after the `detect-capabilities` parser, line 184):
  ```python
      # setup — guided provider/setup wizard (better than task-master models --setup)
      p = sub.add_parser("setup", help="Guided provider setup wizard (detect, recommend, validate)")
      p.add_argument("--yes", action="store_true", help="Accept the recommendation non-interactively (CI/dispatch)")
      p.add_argument("--validate", action="store_true", help="Dry-run gate: validate_setup + a live one-token probe per provider")
  ```

  Add the DISPATCH entry (in the `DISPATCH` dict, after `"detect-capabilities": cmd_detect_capabilities,`):
  ```python
      "setup": cmd_setup,
  ```

- [ ] **Step 4: Run, expect PASS**
  ```
  python3 -m pytest tests/core/test_setup_wizard.py -v
  ```
  Expected: all setup-wizard tests pass (10 total). Then the full CLI suite:
  ```
  python3 -m pytest tests/core/test_cli.py tests/core/test_setup_wizard.py -q
  ```
  Expected: all pass.

- [ ] **Step 5: Commit**
  ```
  git add prd_taskmaster/setup_wizard.py prd_taskmaster/cli.py tests/core/test_setup_wizard.py
  git commit -m "$(cat <<'EOF'
  feat(cli): wire `atlas setup` verb (--yes, --validate)

  cmd_setup drives run_setup and exits non-zero when validation is not ready so
  CI/dispatch can gate on `atlas setup --validate`. Subparser + DISPATCH follow
  cli.py conventions.

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 6: Full-suite regression guard

Confirm the chunk integrates without breaking sibling chunks or the existing suite.

**Files:** none (verification only).

- [ ] **Step 1:** Run the chunk's tests plus every test that touches providers/validate/CLI:
  ```
  python3 -m pytest tests/core/test_setup_wizard.py tests/core/test_mode_recommend_validate.py \
      tests/core/test_cli.py tests/core/test_dogfood_fixes.py tests/core/test_prerelaunch_p0_fixes.py \
      tests/core/test_fleet_config.py -v
  ```
  Expected: all pass.
- [ ] **Step 2:** Run the entire suite for safety:
  ```
  python3 -m pytest tests/core/ -q
  ```
  Expected: green (any failure here is a Chunk-1 `engine_config`/`save_engine_config`
  integration gap — coordinate with Chunk 1, do NOT paper over it in `setup_wizard.py`).
- [ ] **Step 3: Commit (only if anything was touched to integrate)** — otherwise skip. If a
  legacy `validate_setup()` caller needed `provider_mode="plan_only"`, fix it here:
  ```
  git add -A
  git commit -m "$(cat <<'EOF'
  test(setup): full-suite regression guard for the setup-wizard chunk

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  EOF
  )"
  ```
```

I have written Chunk 5 grounded in the real source. Key load-bearing facts I verified and built against:

- **`validate_setup` (mode_recommend.py:367)** takes no args today; check 1 (`binary`, L404-413), check 2 (`version`, L417-428), aggregation (L563-582) already excludes `severity == "warning"` — so my refactor only needs to add `"advisory"` to the exclusion set and gate it on `provider_mode != "plan_only"`. I added a `provider_mode` param defaulting to `fleet.engine_config()["provider_mode"]`.
- **`run_detect_providers` / `detect_capabilities` / `run_configure_providers`** return the exact dict shapes the panel/accept steps consume (`{"ok", "providers": {main/fallback/research}}`, the caps dict, the configure result).
- **`_ensure_env_entry(env_path, key, value)` (lib.py:275)** returns `True` when changed and appends a quoted entry — the Add-key step uses it verbatim.
- **`emit`/`fail`/`CommandError` (lib.py:33-56)** and the `cli.py` `sub.add_parser(...)` + `DISPATCH` dict + `main()` dispatch pattern (cli.py:142-397) — the `setup` subparser and `cmd_setup` follow them.
- **Contract dependency surfaced explicitly:** `fleet.engine_config()` and `fleet.save_engine_config()` do **not** exist yet (grep returned nothing) — they are Chunk 1's deliverable. I included drop-in contract-matching shims so this chunk is buildable/testable standalone, with a coordination note for the merge.

Plan file to be created by the executing engineer: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/setup_wizard.py` (new), with modifications to `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/mode_recommend.py` and `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli.py`, and tests at `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_setup_wizard.py` and `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_mode_recommend_validate.py`.


---


## Chunk 6: migration: flip default + parity gate

This chunk completes sub-project #1: it flips `get_backend("auto")` to resolve to `NativeBackend` unconditionally (keeping `backend="taskmaster"` working for one deprecation release behind a `DeprecationWarning`), then erects a **golden-parity gate** (a verification TASK referencing the `AI-golden-parity-refactor` skill) that must pass GREEN before the **final** task physically deletes `TaskMasterBackend`, `tm_parallel.py`, and the three TaskMaster MCP tools.

> **Gating rule (read this first):** Tasks 1–3 land independently. **Task 3 (parity) is a hard gate on Task 4 (deletion).** Do NOT start Task 4 — do not delete a single line of `TaskMasterBackend` / `tm_parallel.py` / the MCP tools — until Task 3's parity run is committed GREEN with the diff artifact checked in. The plan marks the exact gate command. This is the migration order from spec §9 (flip → parity gate → delete).

**Dependency on prior chunks:** this chunk assumes Chunks 1–5 have landed (`engine` config block in `fleet.py`, `provider_resolver.resolve_provider`, `cli_agent.generate_json_via_cli`, the `NativeBackend.parse_prd/expand/rate` rewiring to the resolver, and the probe cache). If those are not yet merged, Task 3's "native+cli_agent" leg cannot pass — which is exactly why Task 4's deletion is gated on it.

---

### Task 1: Flip `get_backend("auto")` → `NativeBackend` unconditionally + deprecate `"taskmaster"`

Spec §9.2. Today `get_backend` with `backend="auto"` constructs a `TaskMasterBackend`, calls `.detect()`, and returns it when the `task-master` binary is available — preferring the external binary. We flip the default so `"auto"` always returns `NativeBackend`, and we keep the explicit `backend="taskmaster"` opt-in alive for **one** deprecation release, emitting a `DeprecationWarning`. The `TaskMasterBackend` class is **not** deleted here (that is gated Task 4).

**Files:**
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/backend.py` (`get_backend`, L855-867) — replace the auto-detect body
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/backend.py` (add `import warnings` near top, L3-12 import block)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_backend_migration.py` (new)

Steps:

- [ ] **Step 1: Write the failing test**

Create `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_backend_migration.py`:

```python
"""Migration tests: backend='auto' resolves to NativeBackend unconditionally,
backend='taskmaster' still works for one deprecation release with a warning.

Spec: docs/design/2026-06-15-atlas-engine-hybrid-provider-setup.md §9.2
"""

import warnings

import pytest

from prd_taskmaster import backend as backend_mod
from prd_taskmaster.backend import (
    NativeBackend,
    TaskMasterBackend,
    get_backend,
)


def test_auto_resolves_native_even_when_taskmaster_binary_present(monkeypatch):
    """The migration's core invariant: 'auto' is NativeBackend even when the
    task-master binary is on PATH and detect() reports it available.

    We monkeypatch TaskMasterBackend.detect to claim availability; the old
    code would have returned the TaskMasterBackend in that case. Post-flip it
    must NOT — 'auto' returns NativeBackend unconditionally.
    """
    monkeypatch.setattr(
        TaskMasterBackend,
        "detect",
        lambda self: {"name": "taskmaster", "available": True, "ai_ops": True},
    )
    be = get_backend({"backend": "auto"})
    assert isinstance(be, NativeBackend)
    assert be.name == "native"


def test_auto_resolves_native_when_taskmaster_binary_absent(monkeypatch):
    monkeypatch.setattr(
        TaskMasterBackend,
        "detect",
        lambda self: {"name": "taskmaster", "available": False, "ai_ops": False},
    )
    be = get_backend({"backend": "auto"})
    assert isinstance(be, NativeBackend)


def test_missing_backend_key_defaults_to_native(monkeypatch):
    """An empty/legacy config (no 'backend' key) defaults to 'auto' -> Native."""
    monkeypatch.setattr(
        TaskMasterBackend,
        "detect",
        lambda self: {"name": "taskmaster", "available": True},
    )
    be = get_backend({})
    assert isinstance(be, NativeBackend)


def test_explicit_native_returns_native():
    be = get_backend({"backend": "native"})
    assert isinstance(be, NativeBackend)


def test_explicit_taskmaster_still_works_but_warns():
    """backend='taskmaster' is honored for ONE deprecation release, with a
    DeprecationWarning so dispatch logs surface the impending removal."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        be = get_backend({"backend": "taskmaster"})
    assert isinstance(be, TaskMasterBackend)
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    assert any("taskmaster" in str(w.message).lower() for w in caught)


def test_get_backend_does_not_call_taskmaster_detect_on_auto(monkeypatch):
    """Regression guard: the old auto path constructed a TaskMasterBackend and
    called .detect(). The flip must NOT touch TaskMasterBackend at all on auto —
    no binary probe cost, no import-time spawn."""
    called = {"detect": False}

    def boom(self):
        called["detect"] = True
        return {"available": True}

    monkeypatch.setattr(TaskMasterBackend, "detect", boom)
    get_backend({"backend": "auto"})
    assert called["detect"] is False
```

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_backend_migration.py -v
```

Expected: `test_auto_resolves_native_even_when_taskmaster_binary_present` FAILS with `AssertionError: assert isinstance(<TaskMasterBackend>, NativeBackend)` (old code returns the TaskMasterBackend when detect reports available); `test_explicit_taskmaster_still_works_but_warns` FAILS because no `DeprecationWarning` is emitted; `test_get_backend_does_not_call_taskmaster_detect_on_auto` FAILS (`assert called["detect"] is False` — old code calls detect on auto).

- [ ] **Step 3: Minimal implementation**

In `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/backend.py`, add `import warnings` to the stdlib import block (alphabetical, after `import time` on L8):

```python
import time
import warnings
```

Replace `get_backend` (L855-867) in its entirety with:

```python
def get_backend(cfg=None) -> Backend:
    config = fleet.load_fleet_config() if cfg is None else cfg
    backend = config.get("backend", "auto") if isinstance(config, dict) else "auto"

    if backend == "taskmaster":
        # Deprecated path: kept for ONE release so existing fleet.json files with
        # an explicit "backend": "taskmaster" do not hard-break on upgrade. The
        # TaskMaster binary + this branch are deleted in the gated migration task
        # (spec §9.4) once golden parity is green.
        warnings.warn(
            "backend='taskmaster' is deprecated and will be removed in the next "
            "release; the native engine is now the sole generator. Remove the "
            "'backend' key from .atlas-ai/fleet.json (or set it to 'native') to "
            "silence this warning.",
            DeprecationWarning,
            stacklevel=2,
        )
        return TaskMasterBackend(_FACTORY_TOKEN)

    # backend == "native" OR "auto" (the default): the native engine is the sole
    # generator. 'auto' no longer probes for the task-master binary — it resolves
    # to NativeBackend unconditionally (spec §9.2).
    return NativeBackend()
```

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_backend_migration.py -v
```

Expected: 6 passed. Then run the existing backend suites to catch regressions in callers that relied on the old auto-detect:

```
python3 -m pytest tests/core/test_backend.py tests/core/test_native_backend.py -v
```

Expected: most pass, but **`test_backend_factory_precedence_and_auto_detection` (tests/core/test_backend.py:106-125) WILL FAIL** — it asserts the **old** behavior: after `_write_fake_taskmaster`, `get_backend({"backend":"auto"})` returns a `TaskMasterBackend` (L123-125, `auto = get_backend({"backend": "auto"}); assert isinstance(auto, TaskMasterBackend)`). That assertion encodes the behavior we are intentionally changing. Update that test: change its final two lines so `auto` is expected to be `NativeBackend` even with the fake binary present, and add a one-line comment `# flipped: spec §9.2 — auto is always native`. Concretely, replace L123-125:

```python
    _write_fake_taskmaster(tmp_path / "bin")
    auto = get_backend({"backend": "auto"})
    assert isinstance(auto, TaskMasterBackend)
```
with:
```python
    # flipped: spec §9.2 — auto is always native, even with the task-master binary present
    _write_fake_taskmaster(tmp_path / "bin")
    auto = get_backend({"backend": "auto"})
    assert isinstance(auto, NativeBackend)
```

The rest of `test_backend.py` (the explicit `backend="taskmaster"` / `backend="native"` assertions in that same test, and the other TaskMasterBackend tests) still pass under Task 1 — `"taskmaster"` is still honored. Do not weaken the new `auto→native` invariant to satisfy a stale assertion. (Those `backend="taskmaster"`-coupled tests are dealt with separately in Task 4, once the class is actually deleted.)

- [ ] **Step 5: Commit**

```
git add prd_taskmaster/backend.py tests/core/test_backend_migration.py tests/core/test_backend.py
git commit -m "feat(backend): flip get_backend('auto') to NativeBackend; deprecate backend='taskmaster'

auto no longer probes for the task-master binary — native is the sole
generator (spec §9.2). backend='taskmaster' still works for one release
behind a DeprecationWarning. Updated test_backend_factory_precedence_and_auto_detection
to expect auto->native. TaskMasterBackend class deletion is gated on golden
parity (Task 4).

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Add the golden-parity capture harness (script, no deletion)

Spec §9.3 + the `AI-golden-parity-refactor` skill. This task builds the **reusable harness** that captures task-graph outputs from both backends on 2-3 sample PRDs and diffs them. It captures the TaskMaster-path golden **now** (while `TaskMasterBackend` still exists) so Task 3 can prove the native+cli_agent path produces equivalent graphs. This task writes only the harness + fixtures; the actual pass/fail gate is Task 3.

> **Critical correctness note (the disk-vs-result bug):** `NativeBackend.parse_prd` (backend.py:409-419) and `TaskMasterBackend.parse_prd` (backend.py:735-738) BOTH return `{"ok": ..., "task_count": N, "tag": ..., "backend": ...}` with **no `"tasks"` key and no `"raw"` key** — the generated tasks are written to `.taskmaster/tasks/tasks.json` on disk (the binary writes them; `NativeBackend` calls `_write_tasks_into_tag`). So the harness must **read the task graph from disk** via `parallel.load_tagged` + `parallel.get_tasks` after `parse_prd` returns — it cannot pull tasks out of the result dict. Because both backends write to the SAME `.taskmaster/tasks/tasks.json` path, each backend leg must run in its **own temp cwd + tag** so the two legs don't overwrite each other's `tasks.json`. The unit test below locks this contract so the bug is caught in CI, not only at Task-3 runtime.

**Files:**
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/fixtures/prd_cli_tool.md` (sample PRD 1)
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/fixtures/prd_web_api.md` (sample PRD 2)
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/fixtures/prd_data_pipeline.md` (sample PRD 3)
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/golden_parity.py` (harness: capture + normalize + diff)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_golden_parity_harness.py` (unit tests for the normalizer/differ + the disk-read extraction path — pure, no model calls)

Steps:

- [ ] **Step 1: Write the failing test**

Create the fixtures first (tiny but real PRDs — these are inputs, not asserted output). Example for `tests/parity/fixtures/prd_cli_tool.md`:

```markdown
# PRD: line-count CLI

## Goal
Build `lc`, a CLI that counts lines, words, and bytes in files.

## Requirements
- `lc <file>` prints lines, words, bytes for one file.
- `lc <a> <b>` prints per-file rows plus a total row.
- `--lines-only` flag suppresses word/byte columns.
- Reads stdin when no path is given.

## Acceptance
- Output matches `wc` byte-for-byte on the test corpus.
- Exit 1 with a stderr message on a missing file.
```

(Author `prd_web_api.md` and `prd_data_pipeline.md` similarly — each ~10-15 lines, one clear goal, 4-5 requirements, an acceptance section. These exist to exercise generation, not to be asserted.)

Now create `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_golden_parity_harness.py` — unit tests for the **pure** normalizer/differ AND the disk-read task-extraction path (no model, no subprocess):

```python
"""Unit tests for the golden-parity harness normalizer + differ + extractor.

These are PURE-function tests — they do NOT call any model, backend, or
subprocess. They lock two contracts:
  1. the harness compares the STRUCTURE of two task graphs (parity-relevant
     shape) and not volatile fields;
  2. the harness extracts tasks from DISK (.taskmaster/tasks/tasks.json) after
     parse_prd, NOT from the parse_prd result dict — which carries only
     {ok, task_count, tag, backend} and has NO "tasks" key (backend.py:409-419,
     735-738). Test #2 is the regression guard for the disk-vs-result bug.

Spec: docs/design/2026-06-15-atlas-engine-hybrid-provider-setup.md §9.3
Skill: AI-golden-parity-refactor
"""

import json
from pathlib import Path

from tests.parity.golden_parity import (
    diff_graphs,
    extract_graph_from_disk,
    normalize_graph,
)


def _graph(*titles):
    return {
        "tasks": [
            {
                "id": i + 1,
                "title": t,
                "description": f"desc {t}",
                "details": "volatile per-run details that must be ignored",
                "testStrategy": "volatile too",
                "status": "pending",
                "dependencies": [],
                "priority": "high",
                "subtasks": [],
            }
            for i, t in enumerate(titles)
        ]
    }


def test_normalize_keeps_structural_fields_drops_volatile():
    norm = normalize_graph(_graph("Set up project", "Write tests"))
    assert norm == {
        "task_count": 2,
        "tasks": [
            {"id": 1, "title": "Set up project", "dependencies": [], "subtask_count": 0, "priority": "high"},
            {"id": 2, "title": "Write tests", "dependencies": [], "subtask_count": 0, "priority": "high"},
        ],
    }
    # details / testStrategy / description must NOT appear — they are prose that
    # legitimately differs run-to-run and is not a parity signal.
    assert "details" not in norm["tasks"][0]
    assert "description" not in norm["tasks"][0]


def test_diff_identical_graphs_is_clean():
    a = normalize_graph(_graph("A", "B"))
    b = normalize_graph(_graph("A", "B"))
    result = diff_graphs(a, b)
    assert result["parity"] is True
    assert result["diffs"] == []


def test_diff_reports_task_count_mismatch():
    a = normalize_graph(_graph("A", "B"))
    b = normalize_graph(_graph("A"))
    result = diff_graphs(a, b)
    assert result["parity"] is False
    assert any("task_count" in d for d in result["diffs"])


def test_diff_reports_dependency_shape_change():
    g1 = _graph("A", "B")
    g2 = _graph("A", "B")
    g2["tasks"][1]["dependencies"] = [1]
    result = diff_graphs(normalize_graph(g1), normalize_graph(g2))
    assert result["parity"] is False
    assert any("dependencies" in d for d in result["diffs"])


def test_diff_honors_intended_whitelist():
    """A pre-declared intended diff (e.g. a deliberate title rephrase on task 2)
    is allowed and does NOT fail parity — per the skill, declare the whitelist
    BEFORE running."""
    a = normalize_graph(_graph("A", "B"))
    g2 = _graph("A", "B-renamed")
    b = normalize_graph(g2)
    result = diff_graphs(a, b, intended={"tasks[1].title"})
    assert result["parity"] is True
    assert result["intended_applied"] == ["tasks[1].title"]


def test_extract_reads_tasks_from_disk_not_from_parse_result(tmp_path, monkeypatch):
    """REGRESSION GUARD for the disk-vs-result bug: parse_prd returns a dict with
    {ok, task_count} and NO "tasks"/"raw" key (backend.py:409-419, 735-738).
    extract_graph_from_disk must read the graph from .taskmaster/tasks/tasks.json
    via parallel.load_tagged + parallel.get_tasks — NOT from the result dict.

    We simulate a completed parse: write a realistic parse_prd-shaped result dict
    (no "tasks" key) AND a tasks.json on disk, then assert the extractor returns
    the DISK tasks and would have returned nothing useful from the result dict.
    """
    monkeypatch.chdir(tmp_path)
    tm = tmp_path / ".taskmaster" / "tasks"
    tm.mkdir(parents=True)
    (tmp_path / ".taskmaster" / "state.json").write_text(json.dumps({"currentTag": "master"}))
    disk_tasks = [
        {"id": 1, "title": "From disk A", "dependencies": [], "priority": "high", "subtasks": []},
        {"id": 2, "title": "From disk B", "dependencies": [1], "priority": "medium", "subtasks": []},
    ]
    (tm / "tasks.json").write_text(json.dumps({"master": {"tasks": disk_tasks}}, indent=2))

    # Exactly the shape both backends return — NO "tasks", NO "raw".
    parse_result = {"ok": True, "task_count": 2, "tag": "master", "backend": "native", "ai": "api"}
    assert "tasks" not in parse_result and "raw" not in parse_result  # the trap

    graph = extract_graph_from_disk(parse_result)
    assert [t["title"] for t in graph["tasks"]] == ["From disk A", "From disk B"]
    # And the normalized shape reflects the on-disk dependency edge, proving we
    # did not silently fall back to an empty list from the result dict.
    norm = normalize_graph(graph)
    assert norm["task_count"] == 2
    assert norm["tasks"][1]["dependencies"] == [1]
```

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_golden_parity_harness.py -v
```

Expected: collection error / `ModuleNotFoundError: No module named 'tests.parity.golden_parity'` (the harness does not exist yet). If `tests/` lacks an `__init__.py`, the import `from tests.parity.golden_parity import ...` will fail — create empty `tests/__init__.py` and `tests/parity/__init__.py` so the package import resolves (confirm with `ls tests/__init__.py`; if the repo runs pytest in rootdir-import mode without packages, instead import as `from parity.golden_parity import ...` and add `tests/` to `pythonpath` in `pyproject.toml`/`pytest.ini` — match whatever the existing `tests/core/*` files do).

- [ ] **Step 3: Minimal implementation**

Create `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/__init__.py` (empty) and `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/golden_parity.py`:

```python
"""Golden-parity harness for the TaskMaster -> native+cli_agent migration.

Captures task-graph outputs from each backend on the sample PRDs in
fixtures/, normalizes them to a structural shape (dropping volatile prose),
and diffs them. Only diffs NOT in the pre-declared `intended` whitelist fail
parity.

IMPORTANT: parse_prd does NOT return the task graph in its result dict — both
NativeBackend.parse_prd (backend.py:409-419) and TaskMasterBackend.parse_prd
(backend.py:735-738) return {ok, task_count, tag, backend, ...} with no "tasks"
key; the tasks are written to .taskmaster/tasks/tasks.json. So capture reads the
graph from DISK via parallel.load_tagged + parallel.get_tasks AFTER parse_prd.
Each backend leg runs in its OWN temp cwd + tag so the two legs do not overwrite
each other's tasks.json.

This is the binary acceptance gate referenced by the migration deletion task.
Skill: AI-golden-parity-refactor. Spec: §9.3.

Usage (capture + gate, run from repo root):
    python3 -m tests.parity.golden_parity capture --backend taskmaster --out golden/tm
    python3 -m tests.parity.golden_parity capture --backend native    --out golden/native
    python3 -m tests.parity.golden_parity gate    --gold golden/tm --new golden/native
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PRDS = ["prd_cli_tool.md", "prd_web_api.md", "prd_data_pipeline.md"]

# Pre-declared intended-diff whitelist (skill: declare BEFORE running).
# Each entry is a "tasks[<i>].<field>" path that is allowed to differ between
# the TaskMaster golden and the native+cli_agent output. Start EMPTY — every
# real diff must be consciously promoted here with a one-line justification.
INTENDED_DIFFS: set[str] = set()


def extract_graph_from_disk(parse_result: dict | None = None, tag: str | None = None) -> dict:
    """Read the task graph that parse_prd wrote to .taskmaster/tasks/tasks.json.

    parse_result is accepted (and may be inspected for {ok}) but its body is NOT
    the source of tasks — parse_prd returns only {ok, task_count, tag, ...} with
    no "tasks"/"raw" key. The authoritative graph is the on-disk tasks.json for
    the current (or given) tag, read via parallel.load_tagged + parallel.get_tasks.
    Imported lazily so the pure differ tests do not drag in backend deps.
    """
    from prd_taskmaster import parallel

    resolved = tag if tag is not None else (
        parse_result.get("tag") if isinstance(parse_result, dict) and parse_result.get("tag") else None
    )
    resolved = parallel.current_tag(resolved)
    raw, tag_key = parallel.load_tagged(resolved)
    tasks = parallel.get_tasks(raw, tag_key)
    return {"tasks": tasks}


def normalize_graph(graph: dict) -> dict:
    """Reduce a parse_prd/expand task graph to its parity-relevant structure.

    Keeps: task_count, and per-task {id, title, dependencies, subtask_count,
    priority}. Drops: details/testStrategy/description (volatile prose),
    status (always 'pending' at gen time), and subtask internals (structural
    count is the parity signal, not generated subtask prose).
    """
    tasks = graph.get("tasks", []) or []
    norm_tasks = []
    for t in tasks:
        norm_tasks.append(
            {
                "id": t.get("id"),
                "title": t.get("title", ""),
                "dependencies": sorted(t.get("dependencies", []) or []),
                "subtask_count": len(t.get("subtasks", []) or []),
                "priority": t.get("priority", ""),
            }
        )
    return {"task_count": len(norm_tasks), "tasks": norm_tasks}


def diff_graphs(gold: dict, new: dict, intended: set[str] | None = None) -> dict:
    """Structural diff. Returns {parity: bool, diffs: [str], intended_applied: [str]}.

    A diff path in `intended` is recorded in intended_applied and does NOT
    count against parity (skill: only explicitly-intended diffs allowed).
    """
    intended = intended or set()
    diffs: list[str] = []
    intended_applied: list[str] = []

    if gold.get("task_count") != new.get("task_count"):
        diffs.append(
            f"task_count: gold={gold.get('task_count')} new={new.get('task_count')}"
        )

    g_tasks = gold.get("tasks", [])
    n_tasks = new.get("tasks", [])
    for idx in range(max(len(g_tasks), len(n_tasks))):
        g = g_tasks[idx] if idx < len(g_tasks) else None
        n = n_tasks[idx] if idx < len(n_tasks) else None
        if g is None or n is None:
            diffs.append(f"tasks[{idx}]: present in only one graph")
            continue
        for field in ("title", "dependencies", "subtask_count", "priority"):
            if g.get(field) != n.get(field):
                path = f"tasks[{idx}].{field}"
                if path in intended:
                    intended_applied.append(path)
                else:
                    diffs.append(f"{path}: gold={g.get(field)!r} new={n.get(field)!r}")

    return {
        "parity": not diffs,
        "diffs": diffs,
        "intended_applied": intended_applied,
    }


def _capture(backend_name: str, out_dir: Path) -> int:
    """Run parse_prd on each sample PRD via the named backend; write normalized
    graphs to out_dir/<prd>.json.

    Each PRD runs in its OWN isolated temp cwd + per-PRD tag so the two backend
    legs (which both write the SAME .taskmaster/tasks/tasks.json path) never
    overwrite each other. The graph is read from DISK after parse_prd via
    extract_graph_from_disk — parse_prd's result dict has no "tasks" key.

    Imported lazily so the pure differ tests do not drag in backend/model deps."""
    from prd_taskmaster.backend import NativeBackend, TaskMasterBackend, _FACTORY_TOKEN

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if backend_name == "taskmaster":
        be = TaskMasterBackend(_FACTORY_TOKEN)
    elif backend_name == "native":
        be = NativeBackend()
    else:
        print(f"unknown backend: {backend_name}", file=sys.stderr)
        return 2

    rc = 0
    cwd0 = Path.cwd()
    for prd in SAMPLE_PRDS:
        prd_path = (FIXTURES / prd).resolve()
        stem = Path(prd).stem
        tag = f"parity_{backend_name}_{stem}"
        # Isolated workdir per leg+PRD: parse_prd writes .taskmaster/tasks/tasks.json
        # relative to cwd, so distinct cwds keep the two backend legs from clobbering.
        with tempfile.TemporaryDirectory(prefix=f"parity_{backend_name}_") as work:
            os.chdir(work)
            try:
                be.init_project()
                # point state at this PRD's tag so load_tagged resolves it
                state = Path(".taskmaster") / "state.json"
                state.parent.mkdir(parents=True, exist_ok=True)
                state.write_text(json.dumps({"currentTag": tag}))
                result = be.parse_prd(str(prd_path), num_tasks=8, tag=tag)
                if not result.get("ok"):
                    print(f"CAPTURE FAIL {backend_name}/{prd}: {result}", file=sys.stderr)
                    rc = 1
                    continue
                # Read the graph from DISK (result dict has no "tasks" key).
                graph = extract_graph_from_disk(result, tag=tag)
            finally:
                os.chdir(cwd0)
        norm = normalize_graph(graph)
        (out_dir / f"{stem}.json").write_text(
            json.dumps(norm, indent=2, sort_keys=True)
        )
        print(f"captured {backend_name}/{prd}: {norm['task_count']} tasks")
    return rc


def _gate(gold_dir: Path, new_dir: Path) -> int:
    """Diff every captured PRD graph; print a report; return 0 iff full parity."""
    overall = True
    report = []
    for prd in SAMPLE_PRDS:
        stem = Path(prd).stem
        gold = json.loads((gold_dir / f"{stem}.json").read_text())
        new = json.loads((new_dir / f"{stem}.json").read_text())
        res = diff_graphs(gold, new, intended=INTENDED_DIFFS)
        report.append((stem, res))
        if not res["parity"]:
            overall = False

    print("=== GOLDEN PARITY REPORT ===")
    for stem, res in report:
        status = "PARITY_OK" if res["parity"] else "PARITY_FAIL"
        print(f"[{status}] {stem}")
        for d in res["diffs"]:
            print(f"    DIFF: {d}")
        for i in res["intended_applied"]:
            print(f"    intended (allowed): {i}")
    print("=== %s ===" % ("ALL_PARITY_OK" if overall else "PARITY_FAILED"))
    return 0 if overall else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--backend", required=True, choices=["taskmaster", "native"])
    cap.add_argument("--out", required=True, type=Path)
    gate = sub.add_parser("gate")
    gate.add_argument("--gold", required=True, type=Path)
    gate.add_argument("--new", required=True, type=Path)
    args = p.parse_args(argv)
    if args.cmd == "capture":
        return _capture(args.backend, args.out)
    return _gate(args.gold, args.new)


if __name__ == "__main__":
    raise SystemExit(main())
```

Create empty `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/__init__.py` if it does not already exist.

- [ ] **Step 4: Run, expect PASS**

```
python3 -m pytest tests/core/test_golden_parity_harness.py -v
```

Expected: 6 passed (5 pure normalizer/differ tests + `test_extract_reads_tasks_from_disk_not_from_parse_result`, the disk-vs-result regression guard). The harness's `capture`/`gate` CLI subcommands are exercised live in Task 3 (they need a real backend run); here we prove the pure normalizer/differ contract AND that task extraction reads from disk, not from the result dict.

- [ ] **Step 5: Commit**

```
git add tests/parity/ tests/__init__.py tests/core/test_golden_parity_harness.py
git commit -m "test(parity): golden-parity harness + sample PRD fixtures

Normalizer reduces a task graph to its structural shape (drops volatile
prose); differ gates on a pre-declared intended-diff whitelist (skill:
AI-golden-parity-refactor). Capture reads the graph from DISK
(.taskmaster/tasks/tasks.json via parallel.load_tagged/get_tasks) because
parse_prd returns {ok, task_count} with no 'tasks' key; each backend leg runs
in its own temp cwd+tag. A unit test feeds a realistic parse_prd-shaped result
dict through the extractor to catch the disk-vs-result bug in CI. capture/gate
CLI subcommands feed the deletion gate (Task 3). No production code touched.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Run the golden-parity gate — capture TaskMaster golden, prove native+cli_agent parity

Spec §9.3 + acceptance criterion "Golden-parity: native+cli_agent task graphs match the TaskMaster path on sample PRDs (only intended diffs)." This is the **gate** that unlocks Task 4. It is a verification TASK, not a code change: it runs the Task-2 harness end-to-end against both backends and commits the artifacts (golden capture + native capture + the GREEN gate report). Per the skill, **re-verify the diff yourself — do not trust a `PARITY_OK` string; run the diff.**

> This task requires a runtime where the `task-master` binary AND a `claude`/`codex`/`gemini` CLI (or a raw API key) are present, so both legs of the capture actually generate graphs. Run it in the target dispatch runtime, NOT in a bare unit-test sandbox. Generation calls a real model — this is the ONE place in the chunk that does, and it is a one-time capture, not a unit test.

**Files:**
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/golden/tm/*.json` (TaskMaster-path captures — committed artifact)
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/golden/native/*.json` (native+cli_agent captures — committed artifact)
- Create: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/parity/golden/PARITY_REPORT.txt` (the gate output — committed artifact)
- Test: parity gate is the harness `gate` subcommand (exit 0)

Steps:

- [ ] **Step 1: Write the failing test (the gate invocation itself is the test)**

The gate is the command below. Before running it, **declare the intended-diff whitelist**. With both legs feeding the SAME `normalize_graph` (titles/deps/counts only, prose dropped), the expectation is `INTENDED_DIFFS = set()` (empty) — i.e. byte-identical structure. If a legitimate intended diff exists (e.g. native deliberately emits a different `priority` heuristic), add it to `INTENDED_DIFFS` in `golden_parity.py` **now**, with a one-line `# justification` comment, BEFORE capturing — never after seeing the diff.

- [ ] **Step 2: Capture both legs, run the gate, expect FAIL-or-PASS surfaced**

From repo root, in the runtime that has both backends. Each capture runs each PRD in its own isolated temp cwd+tag and reads the resulting graph from disk (per the Task-2 harness), so the two legs do not collide on `.taskmaster/tasks/tasks.json`:

```
# Golden: capture from the TaskMaster path WHILE IT STILL EXISTS.
python3 -m tests.parity.golden_parity capture --backend taskmaster --out tests/parity/golden/tm

# New: capture from native+cli_agent (Chunks 1-5 must be merged for the keyless leg).
python3 -m tests.parity.golden_parity capture --backend native --out tests/parity/golden/native

# The gate:
python3 -m tests.parity.golden_parity gate \
    --gold tests/parity/golden/tm --new tests/parity/golden/native \
    | tee tests/parity/golden/PARITY_REPORT.txt
echo "GATE_EXIT=$?"
```

Expected on the FIRST run: very possibly `PARITY_FAILED` with `GATE_EXIT=1`, listing concrete `DIFF:` lines (e.g. a task-count delta, a dependency-shape change, a title rephrase). That is the gate doing its job. Per the skill's pitfalls: do not paper over a diff — for each one decide (a) it is an UNINTENDED behavior regression → fix the native/cli_agent path (a Chunk 1-5 bug) and re-capture, or (b) it is a genuinely INTENDED behavior change → add the exact `tasks[i].field` path to `INTENDED_DIFFS` with justification, and re-run the gate.

- [ ] **Step 3: Drive to GREEN, then self-verify the diff by hand**

Iterate Step 2 until the gate prints `=== ALL_PARITY_OK ===` and `GATE_EXIT=0`. Then re-verify the gate **yourself** (skill step 5 — don't trust the string). The committed captures under `tests/parity/golden/{tm,native}/` are the already-normalized graphs that the harness read from disk and wrote out; diff them directly:

```
# Independent re-derivation: diff the committed normalized captures directly.
for f in tests/parity/golden/tm/*.json; do
  base=$(basename "$f")
  diff <(python3 -c "import json,sys;print(json.dumps(json.load(open('$f')),sort_keys=True,indent=2))") \
       <(python3 -c "import json,sys;print(json.dumps(json.load(open('tests/parity/golden/native/$base')),sort_keys=True,indent=2))") \
    && echo "BYTE_IDENTICAL $base" || echo "INSPECT $base (expected only declared intended diffs)"
done
```

Expected: `BYTE_IDENTICAL` for every PRD when `INTENDED_DIFFS` is empty; for any PRD reported as `INSPECT`, eyeball that the ONLY differing fields are exactly the declared whitelist paths — nothing else. Sanity-check the output shape too (the skill's pitfall: an empty diff that tested nothing — which, given the disk-vs-result bug we fixed, is exactly the false-pass to guard against). Confirm each capture file actually has `task_count > 0` and non-empty `tasks` (i.e. the disk read actually found generated tasks, not an empty graph from a result dict that never carried them):

```
python3 -c "import json,glob; [print(p, json.load(open(p))['task_count']) for p in glob.glob('tests/parity/golden/*/*.json')]"
```

Expected: every file reports a non-zero task_count (proves the on-disk graph was actually read and generation actually ran — not an empty-vs-empty false pass arising from reading tasks out of the result dict instead of disk).

- [ ] **Step 4: Confirm the gate is GREEN and reproducible**

Re-run the gate one final time against the committed artifacts to confirm determinism of the gate itself (the normalizer/differ are pure, so re-gating committed captures must be stable):

```
python3 -m tests.parity.golden_parity gate --gold tests/parity/golden/tm --new tests/parity/golden/native; echo "GATE_EXIT=$?"
```

Expected: `=== ALL_PARITY_OK ===`, `GATE_EXIT=0`.

- [ ] **Step 5: Commit the GREEN gate artifact (this commit is the unlock token for Task 4)**

```
git add tests/parity/golden/ tests/parity/golden_parity.py
git commit -m "test(parity): GREEN golden-parity gate — native+cli_agent matches TaskMaster path

Captured task graphs from both backends on 3 sample PRDs (read from disk per
leg, isolated temp cwd+tag); structural diff is clean (intended-diff whitelist:
<empty | list paths + justification>). Gate re-verified by hand (byte-identical
captures, non-empty task_counts). This unlocks the gated deletion task (Task 4):
TaskMaster removal is now safe.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

> If parity CANNOT be reached after fixing genuine regressions (a real capability the native path lacks vs TaskMaster), **STOP** — do NOT proceed to Task 4, do NOT delete TaskMaster. Surface the un-closable gap to the orchestrator. The whole point of the gate is that deletion is conditional on it.

---

### Task 4: GATED DELETION — remove `TaskMasterBackend`, `tm_parallel.py`, the 3 MCP tools, the install step

> **DO NOT START until Task 3 is committed GREEN.** The unlock condition is a literal git check, run as the first sub-step. Spec §9.4. Physical deletion of: `TaskMasterBackend` (backend.py L668-852), `tm_parallel.py` (652 lines) + its `cli.py` command registrations AND argparse subparsers, the `backend_detect`/`init_taskmaster`/`tm_parallel_expand` MCP tools (server.py), the `task-master-ai` install in `skills/setup/SKILL.md`, and `BACKEND_CHOICES` → `{"native"}`. This ALSO requires deleting/rewriting the `TaskMasterBackend`-coupled tests in `tests/core/test_backend.py` (they import `TaskMasterBackend` and exercise `get_backend({"backend":"taskmaster"})`). **Keep** `KNOWN_STOCK_TASKMASTER_DEFAULTS` (still repairs legacy config on read), the `_detect_taskmaster_method` function in `lib.py` (still used by `preflight.py` + `capabilities.py` — verified by grep), `taskmaster.py` itself (still used by `cmd_init_taskmaster` + file-format support per spec §9.5), and the `.taskmaster/config.json` + `tasks.json` file formats (spec §9.5).

**Files:**
- Delete: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/tm_parallel.py`
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/backend.py` (remove `TaskMasterBackend` L668-852; remove `_binary_or_raise` L151-155; remove `tm_parallel` AND `taskmaster` from import L15; remove `_detect_taskmaster_method` from the lib import L17 — all grep-verified orphaned; drop the `"taskmaster"` early-return body in `get_backend`)
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/fleet.py` (`BACKEND_CHOICES` L51; `DEFAULT_FLEET_CONFIG` backend default L48)
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/prd_taskmaster/cli.py` (remove `tm_parallel` import L20; remove the 4 `tm-*` `add_parser` subparser blocks L262-282; remove the 4 `tm-*` COMMANDS entries L374-377)
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/mcp-server/server.py` (remove `init_taskmaster` L93-96, `tm_parallel_expand` L117-123, `backend_detect` L164-172; remove `tm_parallel as TMP` import L33)
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/skills/setup/SKILL.md` (remove the `npm install -g task-master-ai` block L54-55)
- Modify: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_backend.py` (delete/rewrite the TaskMasterBackend-coupled tests — see Step 3.7)
- Test: `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public/tests/core/test_backend_migration.py` (extend — assert the deleted surface is gone)

Steps:

- [ ] **Step 1: Write the failing test (assert the surface is GONE) + verify the gate unlock**

First, the literal unlock check — this MUST pass before any deletion:

```
git log --oneline -50 | grep -q "GREEN golden-parity gate" && echo "GATE_UNLOCKED" || echo "BLOCKED: parity gate not committed green — STOP"
```

Expected: `GATE_UNLOCKED`. If `BLOCKED`, stop and return to Task 3.

Then append to `tests/core/test_backend_migration.py`:

```python
def test_taskmaster_backend_is_removed():
    """Post-deletion: TaskMasterBackend no longer exists in the backend module."""
    from prd_taskmaster import backend as backend_mod

    assert not hasattr(backend_mod, "TaskMasterBackend")


def test_tm_parallel_module_is_removed():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("prd_taskmaster.tm_parallel")


def test_backend_choices_is_native_only():
    from prd_taskmaster import fleet

    assert fleet.BACKEND_CHOICES == {"native"}


def test_taskmaster_backend_request_falls_back_to_native(recwarn):
    """An old fleet.json still pinned to backend='taskmaster' must NOT crash now
    that the class is gone — it resolves to native with a deprecation warning."""
    from prd_taskmaster.backend import NativeBackend, get_backend

    be = get_backend({"backend": "taskmaster"})
    assert isinstance(be, NativeBackend)
    assert any(issubclass(w.category, DeprecationWarning) for w in recwarn.list)
```

Note: `test_explicit_taskmaster_still_works_but_warns` from Task 1 asserted `isinstance(be, TaskMasterBackend)` — that assertion is now intentionally obsolete. **Delete that one test** and rely on `test_taskmaster_backend_request_falls_back_to_native` (the deprecation release is over; the class is gone, the warning + native fallback remains so legacy configs don't hard-crash). Also remove the now-dead `TaskMasterBackend` symbol from the top-of-file import in `test_backend_migration.py` (it is no longer importable) — keep only `NativeBackend` and `get_backend`.

- [ ] **Step 2: Run it, expect FAIL**

```
python3 -m pytest tests/core/test_backend_migration.py -v
```

Expected: the 4 new tests FAIL (`TaskMasterBackend` still present; `tm_parallel` still importable; `BACKEND_CHOICES == {"auto","taskmaster","native"}`).

- [ ] **Step 3: Minimal implementation (the deletions)**

1. Delete the file:
```
git rm prd_taskmaster/tm_parallel.py
```

2. `backend.py` — edit imports. L15 from:
```python
from prd_taskmaster import fleet, llm_client, parallel, taskmaster, tm_parallel
```
to:
```python
from prd_taskmaster import fleet, llm_client, parallel
```
(both `taskmaster` and `tm_parallel` become orphaned in backend.py once `TaskMasterBackend` + `_binary_or_raise` are gone — verified by grep: the only `taskmaster.` refs in backend.py were `taskmaster._find_binary()` at L152 inside `_binary_or_raise` and `taskmaster.init_taskmaster()` at L699 inside the class). And L17 from:
```python
from prd_taskmaster.lib import CommandError, _detect_taskmaster_method, now_iso
```
to:
```python
from prd_taskmaster.lib import CommandError, now_iso
```
(`_detect_taskmaster_method`'s only backend.py use is L676 inside `TaskMasterBackend.detect`; it is still defined in `lib.py` and still imported by `preflight.py` + `capabilities.py` — leave the function in `lib.py`, only drop the now-unused backend.py import).

Delete the entire `class TaskMasterBackend(Backend):` block (L668-852). Delete the now-orphaned `_binary_or_raise()` helper (L151-155 — grep-verified: its only callers were L702/L754/L819, all inside the deleted class). Update `get_backend` — remove the `if backend == "taskmaster": ... return TaskMasterBackend(...)` early-return body but KEEP the deprecation-warning fall-through to native:
```python
def get_backend(cfg=None) -> Backend:
    config = fleet.load_fleet_config() if cfg is None else cfg
    backend = config.get("backend", "auto") if isinstance(config, dict) else "auto"

    if backend == "taskmaster":
        # The taskmaster backend was removed; a legacy fleet.json pinned to it
        # resolves to native (the sole generator) rather than crashing.
        warnings.warn(
            "backend='taskmaster' has been removed; using the native engine. "
            "Remove the 'backend' key from .atlas-ai/fleet.json.",
            DeprecationWarning,
            stacklevel=2,
        )
    return NativeBackend()
```
Then confirm zero remaining references in backend.py before moving on: `grep -n "taskmaster\b\|tm_parallel\|_binary_or_raise\|_detect_taskmaster_method" prd_taskmaster/backend.py` — the only surviving hits should be `prd_taskmaster.__version__` (line ~312, a different module attr, NOT the `taskmaster` submodule) and any `KNOWN_STOCK_TASKMASTER_DEFAULTS`/config-repair string literals. If a real `taskmaster.<x>` submodule call survives, it was missed — handle it before deleting the import.

3. `fleet.py` — L51:
```python
BACKEND_CHOICES = {"native"}
```
And L48 in `DEFAULT_FLEET_CONFIG`, change `"backend": "auto"` to `"backend": "native"` (auto now means native; keep `"auto"` accepted in `get_backend` for back-compat but stop emitting it as the default).

4. `cli.py` — remove `tm_parallel` from the import L20:
```python
from prd_taskmaster import fleet, parallel, task_state
```
Delete the 4 `tm-*` argparse subparser blocks (L262-282: the `tm-parallel`/`tm-plan`/`tm-run`/`tm-harvest` `sub.add_parser(...)` registrations) AND the 4 corresponding `COMMANDS` entries (L374-377: `tm-parallel`/`tm-plan`/`tm-run`/`tm-harvest`). Both halves must go — deleting only the COMMANDS dict entries leaves dangling subparsers that reference `tm_parallel.cmd_*` and break import.

5. `mcp-server/server.py` — delete the `from prd_taskmaster import tm_parallel as TMP` import (L33), and delete the three tool functions: `init_taskmaster` (L93-96), `tm_parallel_expand` (L117-123), `backend_detect` (L164-172). Grep for any remaining `TM.init_taskmaster` / `TMP.` / `CLI.run_backend_detect` references and remove their now-orphaned helper imports if unused.

6. `skills/setup/SKILL.md` — delete L54-55:
```
TaskMaster is optional. Installing task-master-ai unlocks the TaskMaster backend:
  npm install -g task-master-ai
```
Replace with a one-line note that the native engine needs no external binary (and, if a CLI agent is the keyless path, that `claude`/`codex`/`gemini` on PATH is sufficient — cross-ref Chunk 7's setup wizard).

7. `tests/core/test_backend.py` — this file imports `TaskMasterBackend` and exercises `get_backend({"backend":"taskmaster"})` across many tests; with the class deleted, those tests fail to import/collect. Delete or rewrite them:
- **`test_backend_factory_precedence_and_auto_detection` (L106-125):** it imports `TaskMasterBackend` and asserts `get_backend({"backend":"taskmaster"})` is a `TaskMasterBackend` (L111-114) and (after Task 1's edit) `auto→Native`. Rewrite: drop the `TaskMasterBackend` import and the explicit-taskmaster `isinstance(..., TaskMasterBackend)` block; assert `get_backend({"backend":"taskmaster"})` now returns `NativeBackend` (with a `DeprecationWarning`), keep the `native` and `auto→Native` assertions.
- **`test_backend_detect_shape_and_version_gate` (L128-141):** exercises the TaskMaster `detect()` version gate — **delete** (no TaskMaster backend to detect).
- **`test_parse_prd_runs_taskmaster_and_counts_tasks_json` (L144-157):** TaskMaster `parse_prd` — **delete**.
- **`test_expand_delegates_to_tm_parallel_for_more_than_three_pending` (L160-178):** imports `tm_parallel` and patches `run_tm_parallel` — **delete** (module gone).
- **`test_expand_serial_branch_runs_binary_and_appends_telemetry` (L180-204):** TaskMaster serial expand via binary — **delete**.
- **`test_rate_reads_report_file_not_stdout` (L207-227):** TaskMaster `rate()` — **delete**.
- **`test_taskmaster_responses_carry_backend_identity` (L245-266):** TaskMaster backend-identity — **delete**.
- **`test_expand_serial_degrades_to_structural_on_research_failure` (L271-291)** and **`test_parse_prd_zero_tasks_is_failure` (L294-319):** these exercise TaskMaster-binary P0-3 / P1-1 paths — **delete** (the native backend has its own coverage in `test_native_backend.py`; these binary-path behaviors no longer exist).
- **`test_load_fleet_config_backend_key_validates_silently` (L230-242):** does NOT touch `TaskMasterBackend` (only `load_fleet_config`), but L234 asserts `load_fleet_config()["backend"] == "auto"` for an empty config — after the fleet.py default flip to `"native"` (Step 3.3), update that assertion to `== "native"`. Keep the test otherwise; it still validates the `"broken" → default` repair path (update its final assertion to the new default too).
- The fake-binary helpers `_write_fake_taskmaster` / `_isolate(..., with_binary=...)` and the `_seed_tasks` helper become unused once the above are deleted — remove `_write_fake_taskmaster` and the `with_binary` plumbing if nothing else references them (grep first). `_seed_tasks` may still be referenced by surviving/rewritten tests; keep it only if so.

- [ ] **Step 4: Run, expect PASS — and run the FULL suite + parity gate to confirm no orphaned references**

```
python3 -m pytest tests/core/test_backend_migration.py tests/core/test_backend.py -v
python3 -m pytest tests/ -q
```
Expected: migration tests pass; the rewritten `test_backend.py` collects and passes (no `ImportError: cannot import name 'TaskMasterBackend'`, no `ModuleNotFoundError: prd_taskmaster.tm_parallel`); full suite green. Then prove nothing references the deleted symbols:
```
grep -rn "tm_parallel\|TaskMasterBackend\|backend_detect\|init_taskmaster\|tm_parallel_expand\|_binary_or_raise" prd_taskmaster/ mcp-server/ skills/ --include='*.py' --include='*.md' | grep -v "KNOWN_STOCK_TASKMASTER_DEFAULTS\|taskmaster.init_taskmaster\|# " ; echo "EXIT=$?"
```
Expected: no live code references (grep exit 1 / `EXIT=1`). Note `taskmaster.py`'s own `init_taskmaster()` function (called by `cmd_init_taskmaster`) is KEPT — the filter excludes it; if the grep surfaces a hit, confirm it is that kept function, not the deleted MCP tool. Re-confirm the MCP server still imports:
```
python3 -c "import importlib.util,sys; sys.path.insert(0,'mcp-server'); importlib.import_module('server') if importlib.util.find_spec('server') else None" 2>&1 || python3 mcp-server/server.py --help 2>&1 | head -1
```
Expected: no `ImportError`. Finally, re-run the parity gate one more time against the committed captures to confirm deletion did not disturb the native path:
```
python3 -m tests.parity.golden_parity gate --gold tests/parity/golden/tm --new tests/parity/golden/native; echo "GATE_EXIT=$?"
```
Expected: `=== ALL_PARITY_OK ===`, `GATE_EXIT=0` (the committed golden captures still validate; the TaskMaster golden is a frozen artifact, not regenerated — note the `taskmaster` capture leg is no longer runnable post-deletion, which is exactly why the golden is a committed frozen artifact).

- [ ] **Step 5: Commit**

```
git add prd_taskmaster/backend.py prd_taskmaster/fleet.py prd_taskmaster/cli.py mcp-server/server.py skills/setup/SKILL.md tests/core/test_backend_migration.py tests/core/test_backend.py
git commit -m "feat(backend)!: delete TaskMasterBackend + tm_parallel.py + 3 MCP tools (gated on green parity)

Native engine is the sole generator. Removes:
- TaskMasterBackend (backend.py), _binary_or_raise helper, tm_parallel.py (652 lines)
- backend.py imports of taskmaster, tm_parallel, _detect_taskmaster_method (orphaned)
- backend_detect / init_taskmaster / tm_parallel_expand MCP tools
- tm-parallel/tm-plan/tm-run/tm-harvest CLI commands (argparse subparsers + COMMANDS)
- npm install -g task-master-ai from skills/setup
- BACKEND_CHOICES -> {native}
- TaskMasterBackend-coupled tests in tests/core/test_backend.py
Keeps: taskmaster.py (cmd_init_taskmaster + file formats), lib._detect_taskmaster_method
(preflight/capabilities), .taskmaster/config.json + tasks.json formats,
KNOWN_STOCK_TASKMASTER_DEFAULTS config repair. Legacy backend='taskmaster' configs
fall back to native + warn. Unlocked by the committed GREEN golden-parity gate.

BREAKING CHANGE: task-master binary is no longer required or supported.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

**Chunk 6 done when:** `get_backend("auto")` returns `NativeBackend` even with the `task-master` binary present (Task 1, monkeypatched, with `test_backend_factory_precedence_and_auto_detection` updated); the golden-parity harness (reading task graphs from disk, isolated per leg) + GREEN gate artifact are committed (Tasks 2-3); and the gated deletion of `TaskMasterBackend` + `_binary_or_raise` + `tm_parallel.py` + the 3 MCP tools + the `tm-*` CLI surface + the install step + the TaskMasterBackend-coupled `test_backend.py` tests has landed with the full suite + parity gate green (Task 4). Acceptance criteria satisfied: "Golden-parity: native+cli_agent task graphs match the TaskMaster path on sample PRDs" and "`task-master` binary is not required for any generation operation."


---
