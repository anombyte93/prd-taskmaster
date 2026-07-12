# Known issues

## 2026-07-12 — parse_prd unusable when server cwd ≠ project root; provider drift to paid Perplexity
Verified by source read (this session, atlas-vault fleet run).

### A. parse_prd `[Errno 2] ... '.atlas-ai'` (Severity: HIGH)
- `.atlas-ai` state paths are CWD-relative module constants: economy.py:32, fleet.py:17,76,
  pipeline.py:13-19, feedback.py:10, suggestions.py:20, reputation.py:39-40, task_state.py:401,
  mcp-server/server.py:394. No stateful op takes a project root.
- The long-lived atlas-engine MCP server frequently runs with a DELETED cwd (a removed git
  worktree) → `Path('.atlas-ai').mkdir(...)` at lib.py:88 raises Errno 2 even though the parent
  mkdir exists. Reached via economy.py telemetry (economy.py:115) from NativeBackend.parse_prd
  (backend.py:351); error swallowed at mcp-server/server.py:221-222. preflight() also does
  os.chdir (pipeline.py:192), permanently moving the shared server off-root.
- Telemetry writes AFTER the LLM call, so the failure burns paid tokens then discards the parse.
- validate vs parse inconsistency: validation.py:39-41 resolves a relative prd_path against the
  server cwd (rejects a path valid from project root); parse reads abs fine (backend.py:359-363)
  but then fails on the cwd-relative WRITE.
- FIX: anchor all state to an explicit project root (tool param / ATLAS_PROJECT_ROOT env / MCP
  roots); detect a dead cwd per call and fail self-diagnosing; make append_telemetry best-effort;
  replace preflight os.chdir with a plumbed root; echo the resolved absolute prd_path in errors.

### B. Research role silently uses paid Perplexity (Severity: MEDIUM)
- providers.py:352-358: research_choice "real_api_if_key" + has_perplexity_key →
  _perplexity_research_model("sonar"), which writes NO baseURL → TaskMaster defaults to paid
  api.perplexity.ai even when PERPLEXITY_API_BASE_URL=localhost:8765 is set and the proxy is up.
- Sticky: _correctable (providers.py:297-309) treats the existing paid role as a user choice and
  won't rewrite it.
- FIX: prefer the local proxy when PERPLEXITY_API_BASE_URL is localhost:8765 (or make
  free_proxy_first the default); always include baseURL when writing a perplexity role; treat a
  paid-perplexity role as correctable when the free proxy is reachable.
