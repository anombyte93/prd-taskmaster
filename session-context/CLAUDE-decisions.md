## 17:23 AWST 11/04/2026

1. **Keep repo script.py as the clean version** — the repo already had redundant functions removed; the live skill's 41KB script.py was the stale one
2. **Default to claude-code provider** — zero API key for Claude Max users, eliminates #1 setup friction
3. **Add detect-capabilities to repo** — was only in live version, needed by HANDOFF phase
4. **Fix TaskMaster CLI detection** — check both `task-master-ai` and `taskmaster` binaries (the actual binary is task-master-ai)
5. **Use TaskMaster native analyze-complexity** — replaces custom enrich-tasks/classify/acceptance-criteria functions
6. **Phase structure: 5 phases** — SETUP (new) -> Preflight -> DISCOVER -> GENERATE -> HANDOFF
