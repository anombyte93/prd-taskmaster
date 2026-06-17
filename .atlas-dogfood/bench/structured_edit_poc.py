"""Structured-edit EXECUTION POC (adjustment #5): can a model that cannot drive an
agentic tool-using harness still COMPLETE a coding task by emitting a structured
SEARCH/REPLACE edit that a deterministic harness applies + gates?

Task = T2 (_parse_version -> fixed 3-tuple). The model never touches the filesystem;
it only returns JSON {"find": <exact current snippet>, "replace": <corrected snippet>}.
The harness applies it (str.replace, once), runs gate_t2.sh, then resets.

Usage: python .atlas-dogfood/bench/structured_edit_poc.py
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

from prd_taskmaster import llm_client

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "prd_taskmaster" / "mode_recommend.py"
GATE = REPO / ".atlas-dogfood" / "bench" / "gate_t2.sh"


def current_func(src: str) -> str:
    lines = src.splitlines(keepends=True)
    out, capturing = [], False
    for ln in lines:
        if ln.startswith("def _parse_version"):
            capturing = True
        elif capturing and ln.startswith("def "):
            break
        if capturing:
            out.append(ln)
    return "".join(out).rstrip("\n")


BASELINE = TARGET.read_text()
FUNC = current_func(BASELINE)

TASK = (
    "Fix this Python function so it ALWAYS returns a fixed-length 3-tuple of ints:\n"
    '  "1.2.3"->(1,2,3)  "1.2"->(1,2,0)  "1"->(1,0,0)  "v2.0"->(2,0,0)\n'
    '  "1.2.3-rc1"->(1,2,3)  "1.2.3.4"->(1,2,3)  bad/empty->(0,0,0)\n'
    "Pad missing components with 0, truncate extras to 3, keep the (0,0,0) fallback.\n\n"
    "CURRENT FUNCTION (copy it VERBATIM into \"find\"):\n```python\n" + FUNC + "\n```\n\n"
    'Return ONLY a JSON object: {"find": "<exact current function text>", '
    '"replace": "<corrected function text>"}. "find" MUST match the current text '
    "character-for-character so a literal string replace succeeds."
)
SYSTEM = "You emit a single JSON search/replace edit. No prose, no tool calls."


def _creds(provider):
    if provider == "google":
        return {"provider": "google", "key": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
                "base_url": "https://generativelanguage.googleapis.com/v1beta"}
    return {"provider": "openai-compatible", "key": "ollama", "base_url": "http://127.0.0.1:11434/v1"}


def run_gate():
    r = subprocess.run(["bash", str(GATE)], capture_output=True, text=True, cwd=str(REPO))
    return r.returncode


def reset():
    subprocess.run(["git", "checkout", "--", str(TARGET)], cwd=str(REPO),
                   capture_output=True, text=True)


MODELS = [
    ("google:gemini-2.5-flash (control)", "google", "gemini-2.5-flash", ""),
    ("ollama:qwen3:8b (/no_think)",       "ollama", "qwen3:latest", "\n/no_think"),
    ("ollama:llama3.2:3b",                "ollama", "llama3.2:3b", ""),
    ("ollama:qwen2.5:1.5b",               "ollama", "qwen2.5:1.5b", ""),
]

results = []
for label, provider, model, suffix in MODELS:
    reset()
    row = {"model": label}
    creds = _creds(provider)
    if not creds["key"]:
        row["verdict"] = "skip (no key)"; results.append(row); continue
    t0 = time.monotonic()
    try:
        text, _ = llm_client._http_call(creds, model, SYSTEM, TASK + suffix, 8192, 300)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        edit = llm_client._extract_json(text)
        if not isinstance(edit, dict) or "find" not in edit or "replace" not in edit:
            row.update(verdict="NO-EDIT", note="no valid {find,replace} JSON")
        else:
            find, replace = edit["find"], edit["replace"]
            if find not in BASELINE:
                # tolerant retry: match on stripped whitespace
                row.update(verdict="FIND-MISS", note="`find` did not match source verbatim")
            else:
                TARGET.write_text(BASELINE.replace(find, replace, 1))
                rc = run_gate()
                row.update(verdict="PASS" if rc == 0 else "FAIL-GATE", gate_rc=rc)
        row["wall_s"] = round(time.monotonic() - t0, 1)
    except Exception as e:  # noqa: BLE001
        row.update(verdict="ERR", note=f"{type(e).__name__}: {str(e)[:100]}",
                   wall_s=round(time.monotonic() - t0, 1))
    reset()
    results.append(row)

print("\n===== STRUCTURED-EDIT EXECUTION POC (T2, model emits find/replace, harness applies) =====\n")
print(f"{'model':<36} {'verdict':<12} {'wall':>6}   note")
for r in results:
    print(f"{r['model']:<36} {r.get('verdict','-'):<12} {str(r.get('wall_s','?'))+'s':>6}   {r.get('note','')}")
print()
(Path(__file__).parent / "structured_edit_results.json").write_text(json.dumps(results, indent=2, default=str))
print("saved structured_edit_results.json")
