# UX-FLOW-AUDIT.md — prd-taskmaster (Atlas) engine, developer/agent journey

**Auditor focus:** the *flow* / *UX* of the engine for a NEW human user and for an UNATTENDED
autonomous agent — the command + skill journey, not the web UI (there is none) and not the
provider-config / parse-expand mechanics already covered in `AUDIT.md` + `defect-register.json`.

**Repo:** `/home/anombyte/Shade_Gen/Projects/prd-taskmaster-public` @ branch `v5-final`, version `5.2.0`
**Scope walked:** `README.md`, root `SKILL.md`, `skills/{setup,discover,generate,handoff,execute-task,execute-fleet,go,expand-tasks,customise-workflow}/SKILL.md`, `commands/`, `.claude-plugin/{plugin,marketplace}.json`, `.mcp.json`, `docs/product/MODEL-ECONOMY.md`.

**Out of scope (already known — NOT re-reported):** the P0-1/P0-2/P0-3 provider-config + parse/expand
chain, the credential-presence gate, the structural-fallback gap, packaging/`.gitignore`/postinstall,
`tm_parse_prd`/`tm_analyze_complexity`/`update_pipeline_task_status` unregistered-tool refs (P1-5/P1-6),
the `handoff-gate`/`append-workflow`/`debrief` CLI-subcommand gaps (P2-5). Where a flow finding *touches*
one of those, it is cross-referenced, not duplicated.

---

## Executive summary

The deterministic core is strong, but the **journey around it has three first-contact breakages that a
new user or autonomous agent hits before they ever reach the provider bugs**:

1. **The documented first command does not exist.** README's very first instruction is `/atlas`. There
   is **no `commands/` directory in the repo at all** and no `atlas` skill — `/atlas` resolves to
   nothing. First action → dead end. (UX-P0-1)
2. **Every phase gate is documented as a deadlock with a "just ignore it" workaround.** `setup`,
   `discover`, `generate`, `handoff` all open with a `check_gate(...)` entry call whose own SKILL text
   says it WILL fail on first entry and instructs the agent to "proceed past this gate." A literal
   autonomous agent halts on its first instruction in every phase. (UX-P0-2)
3. **The one advertised knob can't be set by the tool that exists to set it.** The README's headline
   token-economy setting lives in `.atlas-ai/fleet.json`; the `customise-workflow` skill writes a
   *different* file (`.atlas-ai/config/atlas.json`) with a schema that has **no `token_economy` key**.
   The discoverable config UX and the documented config knob are two disconnected systems. (UX-P0-3)

Below these sit a cluster of P1 journey hazards: a naming maze (`atlas` / `prd` / `prd-taskmaster` /
`go` / `taskmaster` all used for the same thing), unresolved shell variables baked into copy-paste
commands (`$SKILL_DIR`, `$VALIDATION_GRADE`), a ship-check path that diverges between solo and fleet
execution, and an autonomous path that silently assumes human-only / harness-only primitives
(`AskUserQuestion`, `CronCreate`, `/goal`, `/sync`, `/doubt`, `/validate`).

Counts: **3 P0 · 6 P1 · 5 P2 · 3 P3.**

---

## P0 — flow-breaking (the journey dead-ends or self-contradicts at first contact)

### UX-P0-1 · The README's first command (`/atlas`) does not exist; the `commands/` directory is empty/absent

**Files:** `README.md:86`; repo root `commands/` (does not exist — `find commands -type f` → 0 files,
`ls commands/` → "No such file or directory"); `.claude-plugin/plugin.json` (no `commands` key);
no skill is `name: atlas` (`grep '^name: atlas$'` across all SKILL.md → none).

**User impact (concrete):** The README "First run" section is the single most-read instruction after
install. It says, verbatim: ``/atlas      (or /prd:go, or just say: "I want to build …")``. A new user
types `/atlas` → nothing resolves. `/prd:go` *may* resolve because the `go` skill is `user-invocable:
true` (plugin `prd` + skill `go`), but `/atlas` — listed **first**, as the canonical command, also the
brand the whole product is sold under — has zero backing. The autonomous fallback ("just say I want to
build…") relies on skill auto-activation, which is non-deterministic. So the *recommended* first action
fails, and the engine's whole value prop ("90 seconds to your first run", README:60) is gated behind the
user guessing that the second alternative is the real one. This is the worst possible place for a 509-star
relaunch to break — the first 30 seconds.

**Why it's flow-breaking, not polish:** the README sells `/atlas` as THE invocation (README:30 in root
SKILL.md repeats "`/atlas` is the canonical invocation"), `plugin.json` ships zero commands, and Claude
Code plugins surface `/`-commands from `commands/*.md` files. There are none.

**Fix:**
- Create `commands/atlas.md` (and `commands/go.md` if you want `/prd:go` to be a first-class command
  rather than relying on skill-name resolution). The command body should just dispatch to the `go`
  orchestrator skill (e.g. `Invoke the prd-taskmaster `go` skill with the user's goal as argument.`).
- If `/atlas` is intended to resolve via a skill named `atlas`, add that skill (or an alias) — but a
  thin command file is the lower-risk fix.
- Verify post-fix with a clean `/plugin install prd` that `/atlas` and `/prd:go` both appear in the
  command list and both reach `go`. Until verified, change README:86 to lead with the invocation that
  actually works.

---

### UX-P0-2 · Every phase skill opens with a gate it documents as a guaranteed first-entry failure, then tells the agent to ignore it

**Files:** `skills/setup/SKILL.md:28-41`; `skills/discover/SKILL.md:33-45`;
`skills/generate/SKILL.md:33-45` (labeled "Mum dogfood feedback [10] — WORST");
`skills/handoff/SKILL.md:35-46`.

**User impact (concrete):** Each phase's **Entry gate, step 1** is "Call `check_gate(phase=..., evidence={})`.
If it returns `gate_passed: false`, report the violations and **stop**." Immediately below, a "Known issue"
note says the gate is wired backwards (it is structurally an EXIT gate checking the phase's OWN outputs as
entry preconditions), so on first entry `evidence={}` **will** fail, and the agent should "proceed past
this gate on first entry." This is a documented contradiction inside a single instruction block:

- A **compliant autonomous agent** reads step 1, calls the gate, gets `gate_passed: false`, and does
  exactly what the imperative says — **report and stop**. The "Known issue" prose is an *exception* the
  agent must notice and weigh against a hard STOP rule it was just given. Half the time it stops; the
  other half it proceeds and feels like it's violating the contract. Either way the flow is fragile at
  every single phase boundary — four times per run.
- A **human watching** sees a wall of "gate failed, but actually proceed anyway, semantic fix in flight,
  see morning brief" at the top of every phase. "See morning brief" is an internal artifact the user
  doesn't have. This reads as a half-finished product on the most safety-critical surface (the gates the
  README sells as "unfakable").

**Why P0:** the engine's headline trust claim is "completion is a deterministic gated state." The gates
are the product. Shipping them in a state where the first instruction at every phase is "the gate is
broken, ignore it" undermines the core promise and creates a real autonomous-halt risk. The
`generate` note even self-labels this "WORST."

**Fix:** land the semantic gate fix (entry-gate checks entry preconditions: legal transition + prior
phase's evidence present; exit-gate checks the phase's outputs). Until then, **invert the instruction**:
the entry step should be "verify the transition is legal via `current_phase` (the state machine already
enforces `None→SETUP→DISCOVER→...`); the `check_gate` call here is advisory and a `false` on first entry
is expected — do NOT stop on it." Right now the *default* reading is STOP and the override is buried.
Remove "see morning brief" from shipped skills.

---

### UX-P0-3 · The advertised token-economy knob (`.atlas-ai/fleet.json`) and the customisation skill (`.atlas-ai/config/atlas.json`) are two disconnected config systems

**Files:** `README.md:133-136` (`// .atlas-ai/fleet.json { "token_economy": "conservative" ... }`);
`docs/product/MODEL-ECONOMY.md:7,66,71` (token_economy lives in `fleet.json`);
`skills/customise-workflow/SKILL.md:6,68,117,145-181` (writes `.atlas-ai/config/atlas.json`, 6-key schema:
`provider/validation/execution/template/autonomous/gates` — **no `token_economy` key anywhere**).

**User impact (concrete):** The README's most prominent configuration example — the "built for the
token-shortage era" section, the one differentiator it leads with — tells the user to set
`token_economy` in `.atlas-ai/fleet.json`. The product *also* ships a dedicated `/customise-workflow`
skill whose entire job is "the user never edits JSON; the skill asks questions and writes the config."
But that skill writes a **different file** with a **different schema that cannot express
`token_economy` at all**. So:

- A user who runs `/customise-workflow` to "tune the skill" can set provider, validation strictness,
  execution mode, template — but **not** the one setting the README told them mattered most. The
  discoverable path silently omits the advertised knob.
- A user who hand-edits `.atlas-ai/fleet.json` per the README has their setting living in a file the
  customisation skill never reads or reconciles, so a later `/customise-workflow` run can't show or
  preserve it.

The two halves of the configuration UX don't know about each other. This is a discoverability +
correctness break in the feature the relaunch leads with.

**Fix:** unify. Either (a) add a `token_economy` curated question to `customise-workflow` and have it
write through to `fleet.json` (or fold `fleet.json` into `atlas.json` under an `economy` key and migrate
the README + MODEL-ECONOMY references), or (b) at minimum, have `customise-workflow` read and surface the
existing `fleet.json` value and document the split loudly. Pick one config root. Then make the README's
config example and the skill's schema reference the same file.

---

## P1 — major friction (the journey works but is confusing, self-contradictory, or human-only where it claims autonomy)

### UX-P1-1 · Naming maze: `atlas` / `prd` / `prd-taskmaster` / `go` / `taskmaster` all name the same thing

**Files (representative):** product = "Atlas" (README:1-5); npm package = `prd-taskmaster` (README:3);
plugin `name: prd` (`plugin.json`); marketplace `name: atlas-prd-taskmaster` (`marketplace.json`);
MCP server `name: go` (`.mcp.json`); command `/atlas` and `/prd:go` (README:86); orchestrator skill
`name: go`; root skill `name: prd-taskmaster`; MCP prefixes `mcp__atlas-engine__` AND
`mcp__plugin_prd_go__` both live in every skill's `allowed-tools`; and `taskmaster` is BOTH a vendor
dependency AND a backend name.

**User impact:** the user cannot form a stable mental model of "what is this thing called and how do I
invoke it." Is the command `/atlas` or `/prd:go`? Is the config in `.atlas-ai/` or `.taskmaster/`? When
the MCP errors, is the server `atlas-engine`, `plugin_prd_go`, or `go`? Every doc and skill uses a
different subset. For an autonomous agent, the ambiguity is worse: the root SKILL Phase 0 has to run a
`ToolSearch` dance across `mcp__atlas-engine__`, `mcp__plugin_prd_go__`, `mcp__plugin_prd-taskmaster_go`,
and `mcp__plugin_atlas-go_go` (root `SKILL.md:8-22`) just to find which prefix is live this session — a
4-way guess encoded because the naming was never settled.

**Fix:** publish a one-paragraph "names" glossary at the top of the README ("The product is **Atlas**.
The npm package and repo are `prd-taskmaster`. The Claude Code plugin is `prd`, so commands are
`/prd:...` and `/atlas` is an alias. State lives in `.atlas-ai/`; the optional TaskMaster backend lives
in `.taskmaster/`.") and make the skills converge on ONE canonical MCP prefix in prose, keeping the
others only as `ToolSearch` fallbacks. The 4-prefix `allowed-tools` list can stay; the *documentation*
should name one.

### UX-P1-2 · Copy-paste commands contain unresolved shell variables that are only defined in the CLI installer, never in plugin context

**Files:** `skills/handoff/SKILL.md:223` (`python3 $SKILL_DIR/script.py append-workflow ...`),
`:361-363` (`python3 "$SKILL_DIR/script.py" debrief ... --grade "$VALIDATION_GRADE"`);
`$SKILL_DIR` is defined ONLY in `install.sh:24`, never exported into a plugin/MCP session.

**User impact:** In plugin mode (the README's Path 2, and the mode most relaunch users will use),
`$SKILL_DIR` is unset, so the handoff skill's append-workflow and debrief commands run as
`python3 /script.py ...` → file-not-found. `$VALIDATION_GRADE` is likewise never assigned anywhere in
the skill — it's a placeholder the agent is implicitly expected to substitute, but it's written as a
literal shell var in a copy-paste block. An agent that runs the block verbatim fails the CLAUDE.md
append (Step 3) and the debrief scaffold (Step 6). (Step 6 is `|| true`-tolerant, so it fails silently;
Step 3 is not, so it fails loudly mid-handoff.) This compounds P2-5 in `AUDIT.md` (the subcommands don't
exist as CLI either) — but even where the MCP path works, the CLI-fallback blocks are un-runnable as
written.

**Fix:** replace `$SKILL_DIR` with `${CLAUDE_PLUGIN_ROOT}` (which IS defined in plugin context, and is
already used correctly in `setup/SKILL.md:87,106`) or with the documented script path
`~/.claude/skills/prd-taskmaster/script.py` for CLI mode; show both. Make `$VALIDATION_GRADE` an explicit
"substitute the grade from Step 4" instruction, not a bare shell variable in a runnable block.

### UX-P1-3 · The autonomous-agent path silently depends on human-only or harness-only primitives with no documented fallback

**Files:** `skills/handoff/SKILL.md:261-265` ("You **MUST** invoke `AskUserQuestion`"),
`:307-317` (Mode C dispatches `/goal` + `/sync`); `skills/execute-task/SKILL.md:67`
(`CronCreate(...)` for the heartbeat, "abort the iteration if the timer cannot be created"),
`:187-188` (`/doubt`, `/validate` skills), `:250,277` (`/sync`); `skills/discover/SKILL.md:46-52`
(Autonomous Mode detection).

**User impact:** The product repeatedly claims the autonomous path is "first-class, not degraded"
(discover:107, execute-task header). But:
- `handoff` *hard-requires* `AskUserQuestion` (a human-facing modal). It documents a hook-blocked prose
  fallback (good), but the *default* contract is "MUST invoke" — an unattended agent in a harness without
  the hook will either block or improvise.
- `execute-task` step 1 **aborts the whole iteration** if `CronCreate` fails. `CronCreate` is not a
  primitive that exists in plain `codex`/`gemini` CLIs or many automated harnesses (it's a
  Claude-Code/orchestrator-specific affordance — no definition exists in `skel/` or `mcp-server/`). So
  the documented "autonomous by design" loop **hard-stops on its first step** in any harness lacking that
  tool, with no fallback.
- Mode C handoff hard-codes `/goal` and `/sync`, and triple-verify hard-codes `/doubt` and `/validate`.
  These are Claude-Code-ecosystem skills. The README sells "model-agnostic: Claude / Codex / Gemini" and
  the root SKILL says "Other harnesses (codex, gemini) ... CLI-mode is fully supported and not a degraded
  experience" (`SKILL.md:80-82`) — but the execution + handoff skills assume Claude-Code-only commands
  with no codex/gemini equivalent named.

**Fix:** for each harness-specific primitive, document the fallback inline: heartbeat → "if `CronCreate`
is unavailable, skip the heartbeat and rely on the parent orchestrator's liveness check; do NOT abort the
iteration"; `/doubt` `/validate` `/goal` `/sync` → name the model-agnostic equivalent or mark the step
"Claude Code only; on other harnesses, [explicit alternative]." Reconcile the "autonomous is first-class"
claim with the actual hard dependencies.

### UX-P1-4 · `execute-fleet` and `execute-task` disagree on the ship-check path — fleet runs a path that won't exist in the user's project

**Files:** `skills/execute-fleet/SKILL.md:163` (`python3 skel/ship-check.py`);
`skills/execute-task/SKILL.md:85,172,247,262` (`.atlas-ai/ship-check.py`, with `skel/ship-check.py`
named only as the *source* copied to `.atlas-ai/` at setup).

**User impact:** `execute-task` correctly runs the project-local copy `.atlas-ai/ship-check.py` (created
by `setup` Step 2.5). `execute-fleet` runs `python3 skel/ship-check.py` — a path **relative to the
user's project cwd**, where `skel/` does not exist (it's inside the plugin install dir, referenced
elsewhere as `${CLAUDE_PLUGIN_ROOT}/skel/`). The premium Fleet termination step therefore fails to find
its ship-check, so the final `SHIP_CHECK_OK` gate — the entire point of the walk-away-come-back-to-proof
pitch — can't run as written. (Fleet is pilot-stage per README, lowering blast radius, but this is the
*flow* terminus of the paid path.)

**Fix:** make `execute-fleet` use `.atlas-ai/ship-check.py` (the project-local copy, consistent with
`execute-task`) or `${CLAUDE_PLUGIN_ROOT}/skel/ship-check.py` (absolute plugin path) — not the cwd-relative
`skel/ship-check.py`. Also confirm fleet runs `setup` Step 2.5 (which scaffolds `.atlas-ai/ship-check.py`)
before the first wave, or scaffold it in the fleet hard-gates.

### UX-P1-5 · `expand-tasks` (`/expand-tasks`) overlaps `generate` Step 6 with no clear "which do I run?" guidance, and its provider error UX contradicts the engine's free-provider promise

**Files:** `skills/expand-tasks/SKILL.md` (whole skill, esp. `:73-74,175`) vs
`skills/generate/SKILL.md:242-343` (Step 6 "Expand tasks into subtasks (MANDATORY)").

**User impact:** `generate` Step 6 already expands every task into subtasks via backend op `expand` and
calls it MANDATORY before HANDOFF. `expand-tasks` is a *separately user-invocable* skill that ALSO
expands tasks, "fits between Step 8 and Step 11" (expand-tasks:194), and is recommended in HANDOFF-less
prose. A user reading both can't tell whether `/expand-tasks` is required, redundant with GENERATE, or
additive (research enrichment vs structural expansion). The decision point has no guidance. Worse, its
error table (`:175`) says: research provider unreachable/rate-limited → **"Exit skill, tell user to
verify `task-master models` research role is set and reachable"** and its prerequisite (`:73-74`) tells
the user to run `task-master models --set-research <model> --<provider>` — i.e. it dead-ends the user
into TaskMaster provider config, directly contradicting the engine's "no paid API key, uses the CLIs you
already have, free local proxy" promise (README:89,210) and saying nothing about the free proxy or a
structural fallback (the P0-3 theme). For a new user whose research provider is down, this skill is a
wall, not a next step.

**Fix:** (1) State the relationship explicitly at the top of `expand-tasks`: "GENERATE already produces
structural subtasks; `/expand-tasks` ADDS deep research notes — optional, run it only if you want
research-grounded subtasks." (2) Rewrite the error row to degrade to structural/agent expansion and to
mention the free proxy, consistent with the engine's provider story, instead of dead-ending into
`task-master models`.

### UX-P1-6 · `execute-task` entry conditions can be unsatisfiable for the documented free path (Mode A / Mode C), creating a halt

**Files:** `skills/execute-task/SKILL.md:50-59` (entry requires
`.atlas-ai/customizations/system-prompt-template.md` present AND `pipeline.json` records
`phase: EXECUTE`), `:31` (plan at `docs/superpowers/plans/*.md`), step 4 `:90-110` (plan lookup);
`skills/handoff/SKILL.md:302-309` (Mode A → `superpowers:writing-plans`; Mode C → `/goal`).

**User impact:** execute-task hard-requires a plan file and the customisations file, and halts ("report
the gap and halt ... do NOT bootstrap from inside this loop") if absent. `setup` Step 2.5 scaffolds the
customisations file — good — but it is REQUIRED setup that exists precisely because a prior run
hard-halted without it (codified 2026-06-04, setup:112). The plan file dependency is more fragile: Mode A
relies on `superpowers:writing-plans` having run and written to `docs/superpowers/plans/*.md`, but a user
who picked Mode A and didn't complete the plan step, or whose superpowers plugin isn't installed, lands
execute-task with no plan → every task hits the step-4 "invented downstream of the plan" → `blocked` path
→ nothing executes. The handoff → execute transition assumes artifacts that the chosen mode may not have
produced, with a halt rather than a recover-or-guide response.

**Fix:** in execute-task entry, if the plan file is missing, emit an actionable next step ("no plan
found at `docs/superpowers/plans/*.md` or `.taskmaster/docs/plan.md` — run `superpowers:writing-plans`
against `.taskmaster/docs/prd.md` first, or re-run `/prd:handoff` and pick a mode that generates a
plan") rather than silently blocking every task. Confirm `setup` (Step 2.5) always runs before
execute-task on the EXECUTE re-entry path, not only on the first SETUP pass.

---

## P2 — moderate (degraded clarity / fragile guidance)

### UX-P2-1 · `setup` Step 3 provider table still says SKIP for "all populated with a supported provider" — the documented DETECT-FIRST flow contradicts the P0-1 fix
**File:** `skills/setup/SKILL.md:124-130`. The flow-level symptom of `AUDIT.md` P0-1: the *skill journey*
still instructs SKIP on populated roles and never calls `configure-providers` (0 grep hits in the skill).
Listed here because it's the *flow/UX* face of an already-registered code defect — when P0-1 is fixed in
code, this table must change in lockstep or the skill text will re-document the broken behavior. Cross-ref
`AUDIT.md` P0-1 fix ("change setup Step 3 to ALWAYS run configure-providers").

### UX-P2-2 · `setup` default provider stack (Gemini) contradicts root SKILL's default (claude-code/codex) and `customise-workflow`'s ordering
**Files:** `skills/setup/SKILL.md:135-145` (fresh-install default = `gemini-3-pro-preview --gemini-cli`,
"Why Gemini CLI: ~113× more token-efficient"); root `SKILL.md:138-149` (Provider Defaults =
`claude-code` first, then `codex-cli`, Gemini not mentioned); `customise-workflow` Q1 lists Gemini first
(`:77-78`). Three documents, three different "default provider" stories. A user (or agent) reading setup
expects Gemini; reading the root skill expects Claude Code. The recommendation the engine actually
enforces is ambiguous. **Fix:** pick one default-stack policy and state it identically in all three.

### UX-P2-3 · "90 seconds / first run" promise omits the actual step count and the pre-alpha provider HOLD
**Files:** `README.md:60` ("90 seconds to your first run"), `:82-92` (First run). The journey to a first
working task graph is: install → `/atlas` (broken, UX-P0-1) → SETUP (provider config, currently the
HOLD'd P0-1 path) → DISCOVER interview (multi-question) → GENERATE (spec + validate + parse + expand,
minutes under rate-limited CLIs per generate:288) → HANDOFF (AskUserQuestion) → EXECUTE. Calling this
"90 seconds" sets an expectation the flow can't meet, especially while `AUDIT.md` says HOLD on the
first-run provider path. **Fix:** reframe as "90 seconds to kick off your first run" or give an honest
"first run takes a few minutes (discovery interview + spec generation)"; don't imply a finished build in
90s.

### UX-P2-4 · `handoff` mode IDs leak internal A/B/C/D and the user-facing names are inconsistent across the skill
**Files:** `skills/handoff/SKILL.md:109-188` (Mode A/B/C/D + E–J) vs `:287-292` (user-facing names: Plan
& Drive / Auto-Execute / Verified Loop / Atlas Fleet). The skill says "internal IDs in parentheses are
for this skill only — never shown to the user" (:286) but then the Mode-D locked-teaser block, the
red-flags, and the evidence-gate status line all surface raw `A|B|C|D` to the rendered output
(`:397` `user choice: <A|B|C|D-teased>`). A user sees both "Verified Loop" and "Mode C" for the same
thing. **Fix:** map every user-visible string to the friendly name; keep A/B/C only in non-rendered
internal reasoning.

### UX-P2-5 · `customise-workflow` Q3 offers "C (Atlas Fleet)" as a selectable default execution mode on free tier
**File:** `skills/customise-workflow/SKILL.md:85-88` (Q3 options "A (Plan Mode), B (Ralph loop),
C (Atlas Fleet)") — note this also mislabels the mode letters vs `handoff` (where C = Verified Loop/Ralph
and D = Atlas Fleet). A free-tier user can set their *default* execution mode to a premium-locked mode
they can never run, and the letters don't even match the handoff skill's mapping. **Fix:** align the
mode letters/names with `handoff`, and either hide Atlas Fleet from free-tier customisation or mark it
locked the same way handoff does.

---

## P3 — polish

### UX-P3-1 · `discover` autonomous-mode reads `session-context/CLAUDE-soul-purpose.md` / `CLAUDE-activeContext.md` — Shade-internal conventions leaked into the public engine
**File:** `skills/discover/SKILL.md:89-92`. These paths are a private orchestration convention, not
something a public user has. In Autonomous Mode the skill will look for files that don't exist for any
external user. **Fix:** make the autonomous goal source the skill args / a generic `GOAL` env var first,
and treat `session-context/*` as an optional internal fallback, documented as such.

### UX-P3-2 · "see morning brief" and dated dogfood codification notes ship inside public skills
**Files:** every phase skill's "Known issue" note ("Semantic fix in flight (see morning brief)"); setup
`:112`, discover, generate, handoff, execute-task `:108-110,179-181,204-215,253-256,312-315` ("Codified
2026-06-04 ...", "yesterday's run ..."). These are valuable internal provenance but read as
unfinished/in-house to a public user browsing the skill ("Read every line" — README:196 invites exactly
that). **Fix:** move provenance to a `CHANGELOG`/comments and keep shipped skills declarative.

### UX-P3-3 · README config example uses a JSON file with `//` comments (invalid JSON)
**File:** `README.md:133-136` (` ```json ... // .atlas-ai/fleet.json ... { "token_economy": "conservative" } // or ... ``` `). A user who copies the block into `fleet.json` writes invalid JSON (comments). **Fix:** show valid JSON and put the explanatory text outside the code fence, or note the file is JSONC if the loader truly tolerates comments.

---

## The journey, mapped (for reference)

```
INSTALL ──► /atlas  ✗ (UX-P0-1: command doesn't exist; /prd:go may work)
            │
            ▼
        go (orchestrator) ─► reads current_phase, routes via Skill tool
            │
   ┌────────┼─────────────────────────────────────────────────────────┐
   ▼        ▼            ▼            ▼            ▼                     ▼
 SETUP   DISCOVER     GENERATE      HANDOFF      EXECUTE            (EXECUTE-FLEET, premium)
   │        │            │            │            │                     │
 each phase: Entry gate step 1 = check_gate(evidence={}) → documented to FAIL
            → "proceed past on first entry"  ✗ (UX-P0-2: halt risk x4)
   │                                  │            │                     │
 provider                       AskUserQuestion  CronCreate/CronCreate   skel/ship-check.py
 SKIP table                     MUST (human)     /goal /sync /doubt      (wrong path)
 (P0-1 face)                    (UX-P1-3)        /validate (UX-P1-3)     (UX-P1-4)
                                $SKILL_DIR unset (UX-P1-2)
                                                              plan-file halt (UX-P1-6)

 CONFIG UX:  README → .atlas-ai/fleet.json (token_economy)
             /customise-workflow → .atlas-ai/config/atlas.json (no token_economy)  ✗ (UX-P0-3)
```

## Top fixes to unblock the journey (ordered)

1. **UX-P0-1** — ship `commands/atlas.md` (+ `commands/go.md`) dispatching to the `go` skill; verify
   `/atlas` resolves on a clean install. Until then, fix README:86 to lead with the working invocation.
2. **UX-P0-2** — invert the phase entry-gate instruction so first-entry `false` is expected and does NOT
   stop the agent; land the semantic gate fix; strip "see morning brief."
3. **UX-P0-3** — unify the config root so `/customise-workflow` can set the README's `token_economy`.
4. **UX-P1-2 / UX-P1-4** — replace `$SKILL_DIR` with `${CLAUDE_PLUGIN_ROOT}`; fix the fleet ship-check path.
5. **UX-P1-1 / UX-P2-2 / UX-P2-5** — settle the naming + default-provider + mode-letter story and state it
   identically across README, root SKILL, setup, handoff, customise-workflow.
6. **UX-P1-3 / UX-P1-6** — give every harness-specific primitive a documented fallback and replace
   execute-task's silent halts with actionable next steps.
```
```
```
```
```
```

