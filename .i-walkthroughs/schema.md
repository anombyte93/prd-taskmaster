# `.i-walkthroughs/` schema (v1)

> **Skill template.** This is the canonical copy the `interactive-walkthrough` skill carries.
> On first use in a repo that has no `.i-walkthroughs/`, copy this file to
> `<repo>/.i-walkthroughs/schema.md` (then create `README.md`, an empty `index.jsonl`,
> `entries/`, and `evidence/`) and commit, so the Runlog gate's "per `.i-walkthroughs/schema.md`"
> always resolves against a repo-local source of truth.

Canonical field dictionary for walkthrough runlog entries. A future repo-wide RAG ingester
reads THIS file. Stable contract: glob `**/.i-walkthroughs/entries/*.md`, parse YAML
frontmatter as the metadata record, treat each `##` body heading as a chunk boundary, upsert
keyed on `id` (== filename stem), gate migrations on `schema_version`.

## Folder layout

```
.i-walkthroughs/
  README.md              # what this is + RAG-forward note
  schema.md              # THIS file — single source of truth
  index.jsonl            # append-only machine index, one JSON object per entry
  entries/
    <id>.md              # one self-contained learning unit per file
  evidence/
    <id>/                # per-entry assets (id == entry id)
      before-<vp>.png    # pre-fix VIEWPORT screenshot
      after-<vp>.png     # post-fix (second-check) VIEWPORT screenshot
      dom-measure.json   # {"before":{...},"after":{...}} authoritative numbers
```

**File strategy:** one file per `(screen, issue)` learning unit (NOT an append-to-one-log),
because a RAG hit must return a complete, single-issue document with correct metadata so
filters like `verdict:resolved AND severity:P1` select exactly the right unit. `index.jsonl`
is the fast non-vector path to enumerate/pre-filter the corpus without parsing markdown.

**`<id>` == filename stem == frontmatter `id` == `index.jsonl` row key.** Never reused, never changed.

## Slug / id rules

`<id>` = `<YYYY-MM-DD>-<route-slug>-<issue-slug>`
- `route-slug`: route with `/` → `-`, leading `-` stripped; root `/` → `root`.
- `issue-slug`: 2–4 word kebab summary of the defect.
- lowercase ASCII, no spaces. Same-day collision → append `-2`, `-3`.

## Frontmatter fields

| key | type | purpose |
|---|---|---|
| `id` | string (== filename stem) | Primary key for RAG upsert/dedup + `index.jsonl` join + git anchor. Immutable. |
| `schema_version` | int (start 1) | Migration gate for field renames. |
| `repo` | string `owner/name` | Repo-wide RAG filter dimension (this repo's `owner/name`, e.g. `anombyte93/atlas-ai-website`). |
| `branch` | string | Branch the fix landed on. |
| `commit` | git SHA \| `pending` | Hard link to the resolving diff; `pending` until committed. |
| `date` | ISO date `YYYY-MM-DD` | Day the second check passed; filename prefix + index sort key. |
| `route` | string app route | Primary filter: "everything learned about `/calculator`". Leading slash; root `/`. |
| `screen_purpose` | string (one sentence) | The screen soul purpose; anchors the embedding to intended behavior. |
| `mode` | enum `interactive` \| `auto` \| `mobile` | Which walkthrough mode produced this. |
| `viewport` | string `WxH` or `WxH@dpr` | Reproduction context (e.g. `390x844`). |
| `device_class` | enum `mobile` \| `tablet` \| `desktop` | Coarse class for filtering + regression arm. |
| `severity` | enum `P0` \| `P1` \| `P2` \| `P3` | Reuses `reference/auto-report-schema.md` labels verbatim. |
| `category` | enum `layout` \| `copy` \| `a11y` \| `perf` \| `security` \| `interaction` \| `data` \| `trust` \| `role-boundary` | Defect taxonomy for clustering. |
| `root_cause` | string (one line) | The why (NOT the symptom). High-value learn-from-mistakes field. |
| `assumption_trap` | string \| null | The false belief made/nearly made (e.g. "desktop pass == mobile pass"). Drives `reusable_rule`. |
| `reusable_rule` | string (one line, imperative) | Portable rule a future agent applies to avoid repeating this. Highest-signal retrieval target. |
| `evidence_method` | list[enum `dom-measure` \| `viewport-screenshot` \| `console` \| `network` \| `axe` \| `lighthouse` \| `code`] | How proof was gathered, ordered by authority (`dom-measure` first). |
| `files_changed` | list[string] repo-relative | Source files the fix touched. |
| `first_check` | object `{result: fail\|pass, metric, evidence_ref}` | Pre-fix proof the issue was real. Required for P0/P1. |
| `second_check` | object `{result: pass\|fail, metric, evidence_ref, regression_scan: pass\|fail}` | MANDATORY post-fix re-verification. `result=pass` ONLY if same metric now passes AND `regression_scan=pass`. `metric` must be the SAME numeric assertion as `first_check.metric`. |
| `regression_checks` | list[string] | The specific adjacent things re-verified (other viewport class, overflow, focus, console/CSP). Backs `second_check.regression_scan`. |
| `verdict` | enum `resolved` \| `partial` \| `regressed` \| `reverted` | Headline outcome. `resolved`=gone + no regression; `partial`=residual remains; `regressed`=fix broke something; `reverted`=rolled back. |
| `status` | enum `open` \| `verified` \| `shipped` | Lifecycle, orthogonal to verdict. `open`=no passing second check yet; `verified`=second check passed; `shipped`=committed/merged. |
| `approval` | string \| `pending` | Who approved the mutating action (owner handle + when + channel). In `--mobile` this is the Discord reply. |
| `evidence_dir` | string repo-relative | `evidence/<id>/` — keeps binaries out of embedded text but linkable. |
| `tags` | list[string] kebab | Free-form RAG facets beyond the fixed enums. |
| `related` | list[string] entry ids | Graph edges (recurrence → prior resolved entry, supersedes, caused-by). |
| `title` | string (short headline) | Display + embedding-friendly summary; also `index.jsonl` `title`. |

## Body sections (in order; each `##` is a chunk boundary)

1. **Lesson (TL;DR)** — standalone 2–4 sentences; restates `root_cause` + `reusable_rule` in prose. Lead chunk.
2. **Screen & Purpose** — route, role/context, viewport, soul purpose.
3. **Issue (first check)** — observable QUANTITATIVE symptom; DOM numbers first, then screenshot ref. Never an opinion.
4. **Root Cause** — underlying cause + the `assumption_trap` narrative.
5. **Fix** — smallest coherent change, `files_changed`, load-bearing snippet, commit.
6. **Second Check (re-verification, MANDATORY)** — fresh same-screen/same-viewport evidence: (a) same-defect proof via the same metric, (b) explicit regression scan, then the verdict.
7. **Reusable Rule** — the portable rule, imperative.
8. **Decision Trail** — owner decision + channel, rejected alternatives, deferred items, open questions.
9. **Revisions** — append-only log of in-turn updates (e.g. a regressed second check → re-fix). Keeps the full mistake arc in one unit.

## Re-touch rule

- In-turn correction (a fix regresses on its own second check this turn) → **update the same entry** (Revisions section; verdict flips).
- A separate later walkthrough re-touching the same screen → **new dated entry** with `related` linking back. The corpus accumulates `mistake → fix → second-check` triples over time.

## `index.jsonl` row shape

One JSON object per line, append-only (never rewrite prior lines):

```json
{"id":"...","repo":"owner/name","branch":"...","route":"/...","date":"YYYY-MM-DD","severity":"P0|P1|P2|P3","category":"...","verdict":"resolved|partial|regressed|reverted","status":"open|verified|shipped","title":"...","file":"entries/<id>.md"}
```
