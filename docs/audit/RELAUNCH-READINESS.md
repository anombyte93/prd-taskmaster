# Relaunch Readiness — prd-taskmaster (Atlas) v5.2.0

**Audited:** 2026-06-14 · HEAD `d506b93` · published to npm as `prd-taskmaster`
**Lens:** go-to-market / first-impression readiness for a FREE viral relaunch (Reddit + npm, 509 GitHub stars). The bar is **"does a brand-new user's first run succeed, and do the README's headline promises hold on a clean machine?"** — not "can I charge."
**Method:** read the actual repo (README, install.sh, package.json, root SKILL.md, skills/setup/SKILL.md, prd_taskmaster/), ran the engine on a clean dir, probed the live `atlas-ai.au/install` endpoint, npm-packed the tarball. Cross-checked against the engineering `defect-register.json` (21 confirmed defects, 3 P0).

---

## Verdict

**Relaunch readiness: 41 / 100 — NO-GO as written.**

The deterministic core is genuinely good and the npm tarball is clean. But the **single most-traveled first-run path — the one the README actively steers viral users onto — ends in zero tasks with a green "ready" status and no actionable error.** That is the worst possible outcome for a goodwill-driven launch: it doesn't error loudly (which a user forgives), it silently produces nothing (which a user screenshots and posts as "this is broken").

**Two of the three relaunch-killers are go-to-market issues the engineering register under-weights:**
1. The README's own quickstart *funnels users into the broken backend* (not just "a bug exists somewhere").
2. The headline "no paid API key, uses the CLIs you already have" is **literally false on the default auto-selected path** once a user does what the README tells them to.

One focused day of work flips this to GO.

---

## 1. The install → first-success funnel (step count + drop-offs)

There are **two install paths and two run paths**, and they don't behave the same — confusion vector #1.

### Path A — one-liner (`curl -fsSL https://atlas-ai.au/install | bash`)
Live and correct: endpoint returns HTTP 200, served `VERSION="5.2.0"` matches the repo. But it is **CLI-only** — `install.sh` does NOT pip-install the MCP deps and does NOT register the MCP server (verified: zero `pip`/`requirements`/`claude mcp`/`server.py` references in install.sh). So the "32 MCP tools" surface is dark after the one-liner; the skills fall back to CLI mode, which works.

### Path B — Claude Code plugin (`/plugin install prd`)
The MCP server (`mcp-server/server.py:22` → `from mcp.server.fastmcp import FastMCP`) is **silently dead** unless the user already has `mcp`/`fastmcp` in their Python env. No `npm postinstall` runs for a `/plugin` install, and **nothing in the plugin quickstart tells plugin users to pip-install the deps.** Not fatal (CLI fallback works) but the headline MCP feature is invisible with no remediation documented. (Not in the defect register — a pure GTM gap.)

### The run funnel (5 phases)
`SETUP → DISCOVER → GENERATE → HANDOFF → EXECUTE`, driven by `/atlas` (root `SKILL.md`, runs inline) or `/prd:go` (`skills/go/SKILL.md`, routes to per-phase skills). User-prompt count to first `tasks.json`: **0 (setup) → N adaptive interview questions + 1 approval (discover) → ~0 (generate) → 1 mode pick (handoff).** Reasonable on paper.

**Drop-off points, in order of likelihood:**
1. **The TaskMaster zero-tasks trap (see §3) — the dominant bounce.** Highest probability, worst symptom: silent zero, green status.
2. **Phase-0 gate "known issue."** Every phase skill (`setup/SKILL.md:36-44`, and discover/generate/handoff) documents that `check_gate` is wired as an entry gate but is structurally an exit gate, so on first entry `evidence={}` **fails by design**, and the skill instructs the agent to "proceed past this gate on first entry." A literal-minded model stops here. Fragile and model-dependent.
3. **Plugin MCP silently dead (Path B).** Feature appears broken; user doesn't know to pip-install.
4. **Python 3.11+ hard requirement** (`README.md:89`) — older-python boxes bounce at import.

**Time-to-first-task on the happy native path:** plausibly the advertised ~90s. **On the README-recommended path (TaskMaster installed): never — 0 tasks.**

---

## 2. README honesty — which specific claims are false on a fresh box

> **`README.md:89-91` / `:210-211`:** "The free engine needs **no paid API key** — it uses the model CLIs you already have."
> **`README.md:78`, `:138-142`, `:216`:** repeatedly encourages `npm install -g task-master-ai` "to unlock the TaskMaster backend."

These two claims are jointly false in the most common configuration, because of the backend auto-selector:

```python
# prd_taskmaster/backend.py:820-833  get_backend()
backend = config.get("backend", "auto")          # default is "auto"
...
taskmaster_backend = TaskMasterBackend(_FACTORY_TOKEN)
if taskmaster_backend.detect().get("available"):  # TaskMaster on PATH? it WINS.
    return taskmaster_backend
return NativeBackend()
```

Verified live on a clean dir with `task-master-ai` present:
```
backend-detect → "selected": "taskmaster", "source": "auto"
```

So: the README tells the user to install `task-master-ai`; the moment they do, **auto-selection abandons the native (genuinely-keyless) path and routes them onto TaskMaster's stock paid Anthropic/Perplexity defaults** — which need keys the user was told they don't need. The "no paid API key" promise holds *only* on the native backend, which the README's own advice causes the user to leave.

> **`README.md:50`:** "Preflight … configures it. **Zero setup questions.**"

Technically true, materially misleading: it configures it *into a non-working state* on the TaskMaster path (§3) and then reports success.

> **`README.md:33` / `:106-112`:** the `Grade: GOOD … 14 tasks parsed` and the GENERATE panel mockups.

These are aspirational mockups, not captured output. Fine for marketing, but they set an expectation ("14 tasks parsed") that the broken path directly contradicts ("0 tasks parsed, ok:true").

**Honest claims that DO hold:** MIT/free-forever; the deterministic PRD grader + placeholder scan; vendor-neutral `tasks.json`; the `SHIP_CHECK_OK` gate; Python/POSIX platform requirements; the pre-alpha framing (the README is admirably candid about "not battle-tested," which buys real goodwill).

---

## 3. The relaunch-killer, end to end (the bug a viral visitor will hit)

A confirmed chain, each link verified in code and reproduced in the defect register:

1. User reads README → installs `task-master-ai` as encouraged (`README.md:78`).
2. `get_backend()` auto-selects **taskmaster** (`backend.py:820-833`, reproduced above).
3. `task-master init` writes **populated** stock paid roles (keyless `anthropic` main / paid `perplexity` research).
4. `configure-providers` is a **no-op** on those: every role write is gated on `_role_empty` (`providers.py:55` → `not isinstance(value, dict) or not value`) at `:176/:190/:207`. Non-empty stock dicts ⇒ "not empty" ⇒ never migrated to the keyless `claude-code`/`codex-cli` providers the engine prefers. (`defect-register.json` P0-1, live-reproduced: `changed=['.env:…']`; main/research/fallback ALL unchanged.)
5. The SETUP gate green-lights it: `validate_setup` does `provider_ok = bool(main_model)` (`mode_recommend.py:459`) — **string presence, zero credential check.** Reports `ready=True` for the exact config that yields nothing. (P0-2)
6. `parse-prd` returns `ok:false / task_count:0`, `tasks.json` never created — and the CLI **exits 0** anyway (P1-1, `backend.py:718-722`), so even a scripting user sees "success."

**Net first-run experience:** green "Setup ready" panel → adaptive interview → "0 tasks parsed" with no error the user can act on. This is the screenshot that torches a Reddit launch.

(The *native* keyless path actually works: `NativeBackend.parse_prd` returns a structured `agent_action_required` with a schema hint and steps for the agent to parse inline — `backend.py:344-349`, `_agent_parse_action:249`. The tragedy is that auto-selection + the README's advice steer users away from the one path that honors the headline.)

---

## 4. The npm package as a first impression

The tarball itself is **clean and professional** — `npm pack --dry-run`: **151.7 kB packed / 515.4 kB unpacked / 64 files.** No leaks: `AUDIT.md`, `defect-register.json`, `.env`, `docs/`, `tests/`, `__pycache__` are all correctly excluded by the `files` allowlist. All `files`-array entries exist.

But the **registry page metadata is degraded** (verified against current `package.json`):
- `author` — **MISSING** (`.claude-plugin/plugin.json` has "Atlas AI"; root package.json doesn't).
- `bugs` — **MISSING** → no "Report issues" link on the npm page.
- `homepage` — **MISSING** → no homepage link (plugin.json has the GitHub URL; package.json doesn't).

For a project trying to look credible to 509 stars' worth of inbound traffic, an npm page with **no author byline, no homepage, no issues link** reads as anonymous/abandoned. (P3-2.) Trivial to fix; high first-impression leverage.

Secondary npm-page risk — **`postinstall` (`package.json:26`)**: it `pip install`s into the user's active Python env and swallows failure with `2>/dev/null`. Verified the **PEP-668 `EXTERNALLY-MANAGED` marker is present on a standard Arch box**, so this install **fails on every modern Debian/Ubuntu/Arch/Fedora distro** — silently. Good news (verified): the **core CLI path is stdlib-only** (`prd_taskmaster/` has zero `mcp`/`fastmcp` imports; `from prd_taskmaster.cli import main` imports clean with no deps). So the postinstall failure is **cosmetic to first-run, fatal only to MCP mode.** But a swallowed-error postinstall during `npm install` still looks broken and erodes trust on the very first command.

---

## 5. The ONE fix that most increases viral-success odds

**Make the backend default keyless-correct, not the README.** Specifically: change `configure-providers` from *fill-empty* to *repair*, so that when TaskMaster's stock keyless `anthropic`/`perplexity` defaults are present and unusable in-env, they are **migrated to `claude-code`/`codex-cli`** (which the code already prefers — see `_desired_main_model`, providers.py:64). This is exactly `defect-register.json` P0-1's fix.

Why this one: it is the root of the entire zero-tasks chain (§3), it makes the README's headline promise *true* instead of requiring a README walk-back, and it's the difference between "0 tasks, green status" and "14 tasks parsed" on the path real users will take. Pair it with the P0-2 credential-usability check in `validate_setup` so the gate can never again green-light a zero-yield config. Together these two are < 1 day and flip the dominant first-run from failure to success.

If only **one line** could change before launch and nothing else: in `get_backend()` (backend.py:822) **default to `native` unless the user explicitly opted into taskmaster** — the native path honors the keyless promise today and sidesteps the entire P0 chain. (Less complete than fixing configure-providers, but the cheapest possible de-risk.)

---

## 6. Relaunch go / no-go and the fastest path to "just works"

**Decision: NO-GO as written. One day of work → GO.**

Do not post to Reddit/npm-announce until the dominant first-run produces > 0 tasks on a keyless box. The fastest credible path (priority-ordered by first-run impact, not engineering elegance):

| # | Fix | File / evidence | Why it gates launch | Effort |
|---|-----|-----------------|---------------------|--------|
| 1 | `configure-providers`: repair stock keyless defaults → claude-code/codex-cli (don't just fill-empty) | `providers.py:55,176,190,207`; P0-1 | Root of the zero-tasks chain; makes "no paid key" true | ~4h |
| 2 | `validate_setup`: add credential-usability checks (CLI on PATH / key present / proxy 200), fail loudly | `mode_recommend.py:459`; P0-2 | Stops the gate green-lighting a 0-yield config | ~2h |
| 3 | `parse-prd`: treat `task_count==0` on rc 0 as `ok:false` with an actionable error | `backend.py:718-722`, `cli.py:87`; P1-1 | Turns silent-zero into a fixable error | ~1h |
| 4 | README: stop steering keyless users to `task-master-ai`; make clear native is the default and keyless; or default `get_backend()` to native | `README.md:78,138-142`; `backend.py:822` | Aligns the funnel with the working path | ~1h |
| 5 | `package.json`: add `author`, `bugs`, `homepage` (mirror plugin.json) | `package.json`; P3-2 | The npm page 509 stars land on | ~10m |
| 6 | `postinstall`: drop `2>/dev/null`, detect PEP-668, print the exact pipx/venv command instead of auto-pip | `package.json:26`; P2-2 | Stops a silent-fail first command on every modern distro | ~30m |
| 7 | Plugin path: document the pip-install step for MCP deps (or lazy-import + graceful CLI fallback message) | `.mcp.json`, `server.py:22` | Plugin users' headline MCP feature isn't silently dark | ~1h |

**Items 1–4 are the launch gate.** 5–7 are same-day polish that materially improve the first impression.

**Acceptance proof before GO:** on a clean box with `ANTHROPIC_API_KEY` unset, `task-master-ai` installed, and only `claude` on PATH — run `/atlas` end to end and observe `tasks.json` with **> 0 tasks** and a status panel that reports the *real* keyless provider. Capture that run. If it still shows 0 tasks or a false-green, it is still NO-GO.

---

## Self-check
- Every claim above cites a file:line or a reproduced command. Verified live: backend auto-selects taskmaster; CLI imports without mcp/fastmcp; PEP-668 marker present; author/bugs/homepage missing; `atlas-ai.au/install` HTTP 200 serving v5.2.0; npm tarball clean at 151.7 kB.
- Score (41) is consistent with the NO-GO call: a confirmed P0 chain that breaks the headline promise on the dominant path caps relaunch readiness regardless of how good the core is.
- Nothing scored "works" that is actually mocked: the native keyless path is real (`agent_action_required`); the failure is that auto-selection + README route users off it.
- Explorer pane killed.
