# prd-taskmaster-mcp

A thin FastMCP server that exposes every `script.py` subcommand of the
`prd-taskmaster-v2` Claude Code skill as a first-class MCP tool. Instead of
shelling out to `python3 script.py validate-prd --input .taskmaster/docs/prd.md`
and parsing JSON from stdout, Claude Code can call
`mcp__prd_taskmaster__validate_prd(input_path=...)` directly.

This server is a wrapper, not a rewrite. It spawns `script.py` as a subprocess
and returns the parsed JSON — preserving the canonical "every subcommand emits
JSON on stdout" contract documented in the repo's `CLAUDE.md`. If `script.py`
changes, the MCP server automatically picks up the new behavior.

## Install

```bash
# 1. Install the Python MCP framework
pip install --user mcp

# 2. Register the server in ~/.claude.json (or ~/.claude/settings/mcp.json):
```

Add the following under `mcpServers`:

```json
{
  "mcpServers": {
    "prd-taskmaster": {
      "command": "python3",
      "args": [
        "./mcp_server/server.py"
      ]
    }
  }
}
```

Replace the path with wherever you cloned the skill. If you installed the
skill via `install.sh`, the path will be
`~/.claude/skills/prd-taskmaster-v2/mcp_server/server.py`.

Restart Claude Code. The tools will appear as `mcp__prd-taskmaster__<name>`.

## Tools

| Tool | Description |
|---|---|
| `preflight(cwd?)` | Detect `.taskmaster` dir, PRD file, task counts, taskmaster method, crash state |
| `detect_taskmaster(cwd?)` | Detect whether TaskMaster is available via MCP, CLI, or neither |
| `detect_capabilities(cwd?)` | Scan for skills/tools/plugins used by HANDOFF's execution mode recommender |
| `load_template(type)` | Load a PRD template ("comprehensive" or "minimal") — returns full text |
| `validate_prd(input_path, cwd?)` | Run the 13 quality checks on a PRD file |
| `calc_tasks(requirements_count)` | Recommended task count for a given number of REQ-NNN entries |
| `gen_test_tasks(total)` | Generate USER-TEST checkpoint task specs spaced across `total` tasks |
| `gen_scripts(output_dir, cwd?)` | Create the five tracking scripts (progress/status/etc.) |
| `backup_prd(input_path, cwd?)` | Timestamped backup copy of a PRD file |
| `read_state(cwd?)` | Read `.taskmaster/state/execution-state.json` for crash recovery |
| `log_progress(task_id, title, duration?, subtasks?, tests?, issues?, cwd?)` | Append an entry to `.taskmaster/notes/progress.md` |
| `init_taskmaster(method, cwd?)` | Initialize a TaskMaster project via `cli` or `mcp` |

Every tool that operates on files accepts an optional `cwd` parameter. If
omitted, the subprocess runs in the MCP server's current working directory —
which is fine for one-shot calls but not what you want in multi-project setups.
Pass `cwd` explicitly to target a specific project.

## How it works

```
Claude Code ──MCP──▶ mcp_server/server.py ──subprocess──▶ script.py
                              │                                │
                              │◀─ parsed dict ─── JSON stdout ──┘
                              │
                              ▼
                      Claude Code receives dict
```

The shim lives in `mcp_server/lib.py` (`run_script`). Both `ok: true` success
payloads and `ok: false` failure payloads are returned as dicts — the server
does **not** raise exceptions across the MCP boundary, it surfaces them as
error dicts so agents can react programmatically.

## Test

```bash
cd /path/to/prd-taskmaster
python3 mcp_server/test_server.py
```

The test imports the server module and calls three tools directly
(`preflight`, `detect_capabilities`, `validate_prd` against a known-good PRD),
verifying each returns a dict with `ok: true`. It does not spin up the full
stdio MCP transport — that's the job of Claude Code itself.

## Design notes

- **One file per concern.** `server.py` is the tool surface, `lib.py` is the
  subprocess shim, `__init__.py` marks the package. No clever tricks.
- **Reuses `script.py` as-is.** We could import `cmd_*` functions, but they
  call `sys.exit()` internally (via `emit()`/`fail()`). Subprocess is the
  cleaner boundary and future-proofs against script.py refactors.
- **Zero new dependencies.** Just the `mcp` framework. Everything else ships
  with Python 3.11+.
- **Error discipline.** Tool functions return dicts with `ok: false` on
  failure rather than raising. This keeps the MCP serialization clean and
  lets agents distinguish "script said no" from "server crashed".
