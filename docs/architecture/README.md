# Atlas engine — architecture diagram suite (INTERNAL)

A multi-level map of the `prd-taskmaster` engine: the whole system, each component, the code
flow, and — the point of the suite — **what is deterministic Python script vs what is an LLM /
agent step**, per phase. Not linked from the public README; this is for understanding/maintaining
the engine.

> The engine is **function-heavy**: 28 modules · 78 imports · **309 functions vs only 8 classes**,
> and **no import cycles**. So UML class diagrams are thin; the load-bearing views are the
> **import graph, the call graph, and the per-phase script-vs-LLM swimlanes**.

## Legend (used in every hand-authored diagram)

Okabe-Ito colorblind-safe palette + shape redundancy (survives grayscale):

| kind | color | shape |
|---|---|---|
| **LLM / agent** (output varies run-to-run) | orange `#E69F00` | hexagon |
| **deterministic engine code** (Python) | sky blue `#56B4E9` | rectangle |
| **interface boundary** (MCP / CLI, fail-closed) | blue `#0072B2` | rectangle |
| **external model execution** | green `#009E73` | oval / stadium |
| **gate** (deterministic checkpoint) | yellow `#F0E442` | diamond |
| **human** | purple `#CC79A7` | person |

Edges: **solid** = deterministic control flow · **dashed** = LLM-routed choice / bounce-back.

## Toolchain

- **D2** (`*.d2`) — system overview + component breakouts (drill-down architecture).
- **Mermaid** (`*.mmd`) — per-phase script-vs-LLM swimlanes + the parse-PRD sequence (GitHub-native, diffable).
- **pyreverse / code2flow / pydeps** — auto-derived import / class / call graphs + cycle check (regenerated from source → never drift).
- AST `gen-fnmap.py` — the per-module function-signature map (the real "down to methods" artifact).

## The suite

| # | file | level | how | shows |
|---|---|---|---|---|
| 00 | `src/00-system-overview.d2` | system | D2 (hand) | the whole engine in 4 layers: LLM prompts → fail-closed interface (MCP/CLI) → deterministic core → external models |
| 10 | `src/10-component-deterministic-core.d2` | component | D2 (hand) | phase state-machine + gates: pipeline, shipcheck, validation, tasks, task_state, fleet, parallel, lib |
| 11 | `src/11-component-backend-provider-engine.d2` | component | D2 (hand) | the GENERATE engine: backend → resolve_provider (cli/api/plan) → cli_agent / llm_client / plan-floor, wrapped by economy |
| 12 | `src/12-component-detect-setup-mode.d2` | component | D2 (hand) | detection/SETUP: batch → preflight, validate_setup, detect_capabilities, providers, setup_wizard |
| 20 | `generated/20-module-function-map.md` + `generated/classes_AtlasEngine.mmd` | class/fn | auto | every module's functions (signatures) + the 8 real classes |
| 30 | `generated/packages_AtlasEngine.mmd/.svg` + `generated/30-import-cycles.txt` | code-flow | auto | the 28-module / 78-import dependency graph (cycle check: none) |
| 31 | `generated/callflow-core.dot/.svg` | code-flow | auto | function-level call graph across the deterministic spine (13 modules) |
| 40 | `src/40-runflow-script-vs-llm.d2` | code-flow | D2 (hand) | end-to-end `/atlas` run, every step colored script vs LLM, to `SHIP_CHECK_OK` |
| 50 | `src/50-swimlane-setup.mmd` | swimlane | Mermaid (hand) | SETUP — deterministic-dominant |
| 51 | `src/51-swimlane-discover.mmd` | swimlane | Mermaid (hand) | DISCOVER — LLM-dominant |
| 52 | `src/52-swimlane-generate.mmd` | swimlane | Mermaid (hand) | GENERATE — the hybrid crux |
| 53 | `src/53-swimlane-handoff.mmd` | swimlane | Mermaid (hand) | HANDOFF — split (mode pick + routing) |
| 54 | `src/54-swimlane-execute.mmd` | swimlane | Mermaid (hand) | EXECUTE — deterministic-gated, LLM-executed (anti-fake ship gate) |
| 60 | `src/60-sequence-generate-parse-prd.mmd` | sequence | Mermaid (hand) | one parse-PRD call across the three provider tiers |

Rendered images are in `rendered/`. The `.d2`/`.mmd`/`.md` sources are the source of truth;
`generated/` is regenerate-on-demand (do not hand-edit).

## Regenerate

```bash
./docs/architecture/gen.sh
```

Needs on PATH: `python3`, `d2`, `mmdc` (`@mermaid-js/mermaid-cli`), `dot` (graphviz),
`rsvg-convert` (librsvg), `chromium`. Analyzers (pylint/pydeps/code2flow) install into a
throwaway `/tmp` venv.

## Per-phase script-vs-LLM split (summary)

- **SETUP** — deterministic-dominant: `batch.run_engine_preflight` → `preflight`, `validate_setup` (6 checks), `providers.*`, `setup_wizard` (+ `_live_probe`), `check_gate('SETUP')`. LLM only reads panels + decides.
- **DISCOVER** — LLM-dominant: `superpowers:brainstorming`, adaptive Q&A, constraint extraction, AskUserQuestion. Code = only `check_gate('DISCOVER')`.
- **GENERATE** — hybrid: LLM writes PRD + task JSON; code = `validate_prd` (placeholder HARD FAIL), `resolve_provider`, `backend.parse_prd/expand`, `economy.shift_tier`, `parallel.apply_results`, `validate_tasks`, `check_gate('GENERATE')`.
- **HANDOFF** — split: code = `detect_capabilities`, `fleet.compute_waves/route_task`, `check_gate('HANDOFF')`; LLM recommends one mode + writes the workflow block.
- **EXECUTE** — deterministic-gated: code = `task_state.*` (flock), `shipcheck.py` 5 gates → `SHIP_CHECK_OK` (Gate 5 `EXIT_STATUS_RE` = the anti-fake gate); LLM does the coding + CDD evidence. The model cannot self-declare shipped.
