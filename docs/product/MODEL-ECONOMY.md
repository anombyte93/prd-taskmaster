# Model Economy — priors, quota pools, and the measurement plan

> Living doc. Priors below were adversarially verified (3-vote review, live-fetched sources,
> 2026-06-12) by a 105-agent research pass. **Every number here is a starting prior, not a
> constant** — pricing changed twice in April 2026 alone, and routing-threshold transfer across
> model generations was *refuted* in review. Local telemetry (`.atlas-ai/telemetry.jsonl`,
> `economy-report`) is the source of truth that refines this doc and `fleet.json` over time.

## 1. Verified price ladder (per MTok in/out, live 2026-06-12)

| Model | API price | Effective notes |
|---|---|---|
| Claude Haiku 4.5 | $1 / $5 | Batch −50% → $0.50/$2.50; cache reads 0.1× input (~$0.05) — **cheapest first-party path** for bulk non-interactive work |
| Claude Sonnet 4.6 | $3 / $15 | Anthropic's explicit "default for most coding" |
| Claude Opus 4.8 | $5 / $25 | per-TURN cost is "several times" Sonnet (deeper-thinking turns consume more tokens — multiplier unpublished, measure locally) |
| Claude Fable 5 | $10 / $50 | tokenizer emits ~30–35% MORE tokens for the same content → effective per-content cost exceeds the 2× sticker vs Opus. Reserve strictly. |
| Codex GPT-5.5 | 125/12.5/750 credits per MTok | ~5–45 credits per typical task |
| Codex GPT-5.4 | 62.5/6.25/375 credits | Sonnet-analog on the Codex side |
| Codex GPT-5.4-Mini | 18.75/1.875/113 credits | ~6.7× cheaper input than 5.5 — Codex's own haiku-class |
| Perplexity Sonar | $1 / $1 + ~$0.005–0.014 **per-request search fee** | cheapest verified search-grounded API; the request fee DOMINATES short calls → batch questions per call |
| Perplexity Sonar Pro | $3 / $15 + fee | 15× output premium over Sonar — escalation-only |
| Gemini API key (free) | 250 req/day, 10 RPM, Flash only | medium confidence; Pro is paid-only on API free tier since ~Apr 2026 |
| Gemini CLI OAuth | **dynamic per-account** | the popular "1,000/day" figure was REFUTED 0-3; Google stopped publishing static limits — measure your account |
| Groq / OpenRouter / DeepSeek | **unverified** | no claims survived review — open question, do not assume |

Discount stacking (verified): Anthropic Batch −50% applies to input AND output and **stacks with
prompt-cache multipliers** → async Haiku batch + cache ≈ $0.05 input/MTok effective. Batch caveats:
24h turnaround, not ZDR-eligible.

## 2. Quota pools (the fleet-throughput dimension)

| Pool | Cost | Shape |
|---|---|---|
| Claude Max | $100/mo (5×) or $200/mo (20×) | flat-rate, includes Claude Code; per-session caps + TWO weekly caps (all-models + Sonnet-only). Weekly quantities unpublished; temporarily +50% until 2026-07-13 |
| Codex via ChatGPT | subscription credits | per-model credit rates above; OpenAI self-reports ~$100–200/dev/mo typical |
| Gemini | free | dynamic; Flash-only on API key |
| Perplexity | pure pay-per-use | no meaningful free pool |

**Quota-pool doctrine:** the three CLI backends draw on separate pools. Quality picks the model per
task; pool-spreading picks where bulk tiers run when fleet size strains any one subscription.

## 3. Job-class → model prior matrix (synthesis; medium confidence)

| Job class | Start | Escalate to | Basis |
|---|---|---|---|
| Scaffolding / mechanical edits / renames | Haiku 4.5 (or GPT-5.4-Mini) | Sonnet | vendor-endorsed "quick mechanical, high-volume scripted" |
| Bulk non-interactive: decomposition, complexity rating, summarization, structured JSON | Haiku via API (batch+cache when async is OK) | Sonnet | cheapest verified path; single-shot structured calls don't need an agent session |
| Standard feature implementation | Sonnet 4.6 | Opus | Anthropic's explicit default-for-most-coding |
| Complex architecture / hard debugging / cross-cutting refactors | Opus 4.8 | Fable 5 | vendor guidance; "opusplan" pattern (expensive plans, cheap executes) supports plan/execute tier splits |
| Long-running autonomous work | Fable 5 on subscription pool | — (ceiling) | 1M context; run on Max pool, not raw API; gate Stripe-style |
| Research / synthesis | Sonar ($1/$1+fee) | Sonar Pro on validation failure | cheapest search-grounded; batch questions per call |
| Verification / review | Sonnet | Opus | verifier must be ≥ implementer class on hard tasks |

## 4. Escalation doctrine (what the evidence supports)

- **Cascades work and save real money** — FrugalGPT matched best-model accuracy at up to 98% cost
  reduction; only 16.6% of queries escalated to the top model in its case study (cheap models match
  expensive ones on large query subsets). RouteLLM: up to 3.66× savings at 95% quality.
- **The production-grade gate shape** (Stripe "minions", 1,300 merged PRs/week from unattended
  one-shot agents): cheap fast validator first (lint, <5s) → bounded expensive validation (≤2 CI
  rounds) → **hard stop**. This maps directly onto our `escalation.max_steps=2` + ship-check gates.
- **What does NOT transfer:** router thresholds/orderings trained on one model pair were refuted
  for other pairs (0-3). Cascade percentages come from classification benchmarks with 2023–24
  models. Conclusion baked into the engine: thresholds live in `fleet.json`, get recalibrated from
  local telemetry **per model generation**, and are never hard-coded.

## 5. Engine mapping (how priors become behavior)

- `token_economy: conservative | balanced | performance` (`.atlas-ai/fleet.json`, default
  balanced) → start tiers per op class + escalation steps/ceiling + research-provider choice
  (see `prd_taskmaster/economy.py`).
- TaskMaster-native ops (parse/expand/rate/research) run on **API providers** via per-workdir
  config (`tm_parallel`) — single-shot structured calls, the cheap path. CLI agent sessions are
  reserved for file-editing/verification work (workers).
- Routing per task: `route_task()` (complexity tier → ladder → installed-backend check →
  escalation shift per attempt, ceiling-clamped).

## 6. Claims requiring LOCAL measurement (telemetry backlog)

1. Actual Opus/Sonnet/Haiku per-TURN cost multipliers in Claude Code (vendor: "several times", no number).
2. Fable 5 effective cost after tokenizer inflation (~30–35% more tokens — measure per job class).
3. Real Gemini per-account quotas (dynamic; published figures refuted).
4. Per-job token/latency: single-shot API call vs CLI-agent session for decomposition/rating/synthesis
   — **no published benchmark survived verification**; ours may be the first good dataset.
5. Cascade escalation rates + thresholds on OUR job mix (literature numbers are existence proofs only).
6. Whether GPT-5.3-Codex's cheap rate remains available (dropped from the current rate card).
7. Max-plan weekly quantities, especially after the +50% boost expires 2026-07-13.
8. Groq/OpenRouter/DeepSeek bulk pricing vs Haiku-batch (unanswered by research).

## Sources (all live-verified 2026-06-12)

platform.claude.com/docs pricing · support.claude.com Max-plan + Claude Code usage articles ·
help.openai.com Codex rate card + developers.openai.com/codex/pricing · docs.perplexity.ai pricing ·
geminicli.com + google-gemini.github.io quota docs · stripe.dev/blog minions + InfoQ ·
FrugalGPT (TMLR 2024) · RouteLLM (ICLR 2025).
