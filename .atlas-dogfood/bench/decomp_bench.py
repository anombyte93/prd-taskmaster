"""Decomposition-quality benchmark: how well do cheap/local models turn a PRD into
TaskMaster tasks, scored by /atlas's OWN gate (run_validate_tasks via
backend._validate_task_candidate)? Drives every model through the engine's own
llm_client._http_call + _extract_json so the only variable is the model.

Measures THREE points per model so we can quantify the gap-closing of proposed
prd-taskmaster adjustments:
  raw      = one call, validate as-is (today's behaviour)
  +norm    = + status/priority/think-tag normalization (adjustments #2/#3)
  +repair  = + one validation-aware repair pass (adjustment #1)

Usage: python .atlas-dogfood/bench/decomp_bench.py [num_tasks]
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from prd_taskmaster import backend, llm_client
from prd_taskmaster.lib import CommandError

NUM_TASKS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MAX_TOKENS = 8192
PRD = (Path(__file__).parent / "prd_sample.md").read_text()

PROMPT = (
    f"Parse this PRD into exactly {NUM_TASKS} TaskMaster-compatible tasks.\n"
    "Target tag: master.\n"
    "Return only the tasks JSON object.\n\n"
    f"PRD:\n{PRD}"
    "\n\nReturn ONLY valid JSON matching:\n" + backend.TASKS_SCHEMA_HINT
)
SYSTEM = (
    "You are the prd-taskmaster native backend. Generate strict JSON for the "
    "Native Mode tasks.json path."
)

_ALLOWED_STATUS = {"pending", "in-progress", "review", "done", "deferred", "cancelled"}
_ALLOWED_PRIORITY = {"high", "medium", "low"}


def _norm_status(v):
    s = str(v or "pending").strip().lower().replace(" ", "-").replace("_", "-")
    aliases = {"inprogress": "in-progress", "in-progress": "in-progress",
               "todo": "pending", "open": "pending", "wip": "in-progress",
               "complete": "done", "completed": "done", "closed": "done"}
    s = aliases.get(s, s)
    return s if s in _ALLOWED_STATUS else "pending"


def normalize_candidate(candidate):
    """Adjustments #2/#3: strip reasoning wrappers were handled at extract; here
    coerce status/priority variants so trivial format drift does not fail the gate."""
    if not isinstance(candidate, dict):
        return candidate
    for task in candidate.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        task["status"] = _norm_status(task.get("status"))
        pr = str(task.get("priority", "") or "").strip().lower()
        task["priority"] = pr if pr in _ALLOWED_PRIORITY else "medium"
        for sub in task.get("subtasks") or []:
            if isinstance(sub, dict):
                sub["status"] = _norm_status(sub.get("status"))
    return candidate


def extract(text):
    # adjustment #2: drop reasoning <think>...</think> blocks before parsing
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return llm_client._extract_json(text)


def score(candidate):
    try:
        tasks, _ = backend._validate_task_candidate(candidate)
        return True, len(tasks), [len(t.get("subtasks") or []) for t in tasks], []
    except CommandError as e:
        extra = getattr(e, "extra", {}) or {}
        probs = extra.get("problems") or [getattr(e, "message", str(e))]
        tasks = candidate.get("tasks") if isinstance(candidate, dict) else None
        nt = len(tasks) if isinstance(tasks, list) else 0
        sc = [len(t.get("subtasks") or []) for t in tasks] if isinstance(tasks, list) else []
        return False, nt, sc, probs


def _creds(provider):
    if provider == "google":
        return {"provider": "google", "key": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
                "base_url": "https://generativelanguage.googleapis.com/v1beta"}
    if provider == "openai":
        return {"provider": "openai", "key": os.environ.get("OPENAI_API_KEY"),
                "base_url": "https://api.openai.com/v1"}
    if provider == "ollama":
        return {"provider": "openai-compatible", "key": "ollama",
                "base_url": "http://127.0.0.1:11434/v1"}
    raise ValueError(provider)


MODELS = [
    ("openai:gpt-4.1-mini  (strong API bar)", "openai", "gpt-4.1-mini", 120),
    ("google:gemini-2.5-flash",               "google", "gemini-2.5-flash", 120),
    ("ollama:qwen3:latest  (~8B local)",      "ollama", "qwen3:latest", 300),
    ("ollama:llama3.2:3b   (3B local)",       "ollama", "llama3.2:3b", 240),
    ("ollama:qwen2.5:1.5b  (1.5B local)",     "ollama", "qwen2.5:1.5b", 240),
]

results = []
for label, provider, model, timeout in MODELS:
    row = {"model": label}
    creds = _creds(provider)
    if not creds["key"]:
        row.update(stage="none", note="no key/endpoint"); results.append(row); continue
    t0 = time.monotonic()
    try:
        text, _ = llm_client._http_call(creds, model, SYSTEM, PROMPT, MAX_TOKENS, timeout)
        cand = extract(text)
        if cand is None:
            row.update(raw="no-json", note="no JSON extracted", wall_s=round(time.monotonic() - t0, 1))
            results.append(row); continue
        raw_ok, nt, sc, probs = score(cand)
        row["raw"] = "PASS" if raw_ok else "FAIL"
        # +norm
        cand = normalize_candidate(cand)
        norm_ok, nt, sc, probs = score(cand)
        row["norm"] = "PASS" if norm_ok else "FAIL"
        # +repair (one validation-aware pass) only if still failing
        if not norm_ok:
            repair_prompt = (
                PROMPT
                + "\n\nYour previous JSON had these validation problems:\n- "
                + "\n- ".join(probs[:12])
                + "\nReturn the COMPLETE corrected tasks JSON (every task needs >=2 subtasks, "
                  "non-empty title/description/details/testStrategy, priority high|medium|low)."
            )
            text2, _ = llm_client._http_call(creds, model, SYSTEM, repair_prompt, MAX_TOKENS, timeout)
            cand2 = normalize_candidate(extract(text2) or {})
            rep_ok, nt, sc, probs = score(cand2)
            row["repair"] = "PASS" if rep_ok else "FAIL"
        else:
            row["repair"] = "PASS"
        row.update(wall_s=round(time.monotonic() - t0, 1), n_tasks=nt, subtasks=sc,
                   problems=probs[:5])
    except Exception as e:  # noqa: BLE001
        row.update(note=f"{type(e).__name__}: {str(e)[:120]}", wall_s=round(time.monotonic() - t0, 1))
    results.append(row)

print("\n========= DECOMPOSITION BENCHMARK — gap-closing (gate = run_validate_tasks) =========")
print(f"PRD: per-API-key rate limiter | tasks: {NUM_TASKS} | max_tokens: {MAX_TOKENS}\n")
print(f"{'model':<40} {'raw':>5} {'+norm':>6} {'+repair':>8}   note")
for r in results:
    print(f"{r['model']:<40} {r.get('raw','-'):>5} {r.get('norm','-'):>6} {r.get('repair','-'):>8}   "
          f"{r.get('note','') or ('tasks='+str(r.get('n_tasks'))+' sub='+str(r.get('subtasks')))}")
    for p in r.get("problems", [])[:3]:
        print(f"      · {p}")
print()
(Path(__file__).parent / "decomp_results.json").write_text(json.dumps(results, indent=2, default=str))
print("saved decomp_results.json")
