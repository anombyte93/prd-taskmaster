"""Reachability gate — detect orphan modules (code with passing tests but imported by nothing).

This module is READ-ONLY at runtime: it uses git and grep (via subprocess) to inspect
the repository; it never writes files.

Verdict contract
----------------
- WIRED  : at least one non-test file outside the module's own co-located test imports it.
           This is a PASS verdict.
- EXEMPT : ``reachable_via`` starts with a known scheme prefix
           (cli:|route:|tool:|hook:|plugin:|dynamic:).  In v1 we accept the declared scheme
           on trust; scheme-registration verification is a TODO.
           This is a PASS verdict.
- ORPHAN : no non-test importer found AND no exempt scheme declared.
           This is a BLOCKING verdict.
- ERROR  : git or grep encountered a real failure (exit code != 0 for git;
           exit code >= 2 for grep).  The sweep cannot be trusted.
           This is a BLOCKING verdict.

CRITICAL: ERROR must NEVER be mis-reported as WIRED or EXEMPT.
Only WIRED and EXEMPT are passing verdicts.  ORPHAN and ERROR both block.

Design notes
------------
- new_modules_for_task raises ReachabilityError on git failure so callers can never
  silently swallow a broken-environment result and pass an orphan sweep.
- find_importers / _grep_patterns raise ReachabilityError on grep exit code >= 2
  (a real error, not "no matches").  grep exit code 1 ("no matches") is NORMAL and
  causes ORPHAN, not an error.
- reachability_verdict and sweep_task catch ReachabilityError and return
  {"verdict": "ERROR", ...} so the gate is blocked.
- Test files are excluded from importers whether co-located, under tests/, tests/core/,
  or any __tests__/ subtree.

Known v1 limitations (not fixed here; deferred to future iterations)
-----------------------------------------------------------------------
- Python commented-out imports (# import bar) can produce a false-WIRED via grep.
  A future AST-based scan would eliminate this.
- Migration-filename exclusion in new_modules_for_task covers filename patterns but not
  content (e.g. a migration that also defines a domain model).  Low-risk in practice.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Sentinel exception ───────────────────────────────────────────────────────

class ReachabilityError(Exception):
    """Raised when a git or grep subprocess fails with a real error.

    Distinct from 'no matches' (grep rc=1), which is a normal, expected result
    that produces an ORPHAN verdict rather than an error.
    """


# ─── Exempt scheme prefixes ───────────────────────────────────────────────────

_EXEMPT_SCHEMES = ("cli:", "route:", "tool:", "hook:", "plugin:", "dynamic:")

# ─── Exclusion patterns ───────────────────────────────────────────────────────

# Files excluded from "new module" lists even if git says they're added.
_EXCLUDE_NAMES = {
    "__init__.py",
    "__main__.py",
    "conftest.py",
    "setup.py",
}

_EXCLUDE_NAME_RE = re.compile(
    r"(^|/)("
    r"test_[^/]+\.(py|ts|js|go)"  # test_*.py / test_*.ts …
    r"|[^/]+_test\.(py|ts|js|go)"  # *_test.py …
    r"|[^/]+\.test\.(py|ts|js|go)"  # *.test.py / *.test.ts …
    r"|index\.[^/]+"               # index.* barrels
    r"|[^/]+migration[^/]*\.(py|ts|js|go)"  # migration files
    r")$"
)

# Directories whose children are always excluded.
_EXCLUDE_DIRS_RE = re.compile(r"(^|/)(__tests__|tests)/")

# Language source extensions.
_LANG_EXTS: dict[str, set[str]] = {
    "py":  {".py"},
    "ts":  {".ts", ".tsx"},
    "js":  {".js", ".jsx", ".mjs", ".cjs"},
    "go":  {".go"},
}


# ─── Public API ───────────────────────────────────────────────────────────────

def language_for_repo(repo_root: Path) -> str:
    """Detect the primary language of a repository from marker files.

    Priority order:
      1. pyproject.toml or setup.py  -> 'py'
      2. package.json + tsconfig.json -> 'ts'
      3. package.json alone           -> 'js'
      4. go.mod                       -> 'go'
      5. none of the above            -> 'unknown'
    """
    root = Path(repo_root)
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "py"
    has_pkg = (root / "package.json").exists()
    if has_pkg and (root / "tsconfig.json").exists():
        return "ts"
    if has_pkg:
        return "js"
    if (root / "go.mod").exists():
        return "go"
    return "unknown"


def new_modules_for_task(
    repo_root: Path,
    start_commit: str,
    head: str = "HEAD",
) -> list[Path]:
    """Return repo-relative Paths of source files added between *start_commit* and *head*.

    Files are filtered to:
    - Only source extensions for the repo language (as detected by language_for_repo).
    - Exclude tests, __init__.py, __main__.py, index.* barrels, conftest.py,
      setup.py, and migration files (see module-level patterns).

    Raises ReachabilityError if git exits with a non-zero return code (real git failure).
    An empty diff (git succeeds but no files were added) returns [] normally — this is
    NOT an error.

    Contract: callers must handle ReachabilityError to avoid silently passing a sweep
    on a broken git environment.
    """
    repo_root = Path(repo_root)
    lang = language_for_repo(repo_root)
    exts = _LANG_EXTS.get(lang, set())

    result = subprocess.run(
        ["git", "-C", str(repo_root), "diff",
         f"{start_commit}..{head}",
         "--diff-filter=A", "--name-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        msg = (
            f"new_modules_for_task: git diff failed (rc={result.returncode}): "
            f"{result.stderr.strip()}"
        )
        logger.warning(msg)
        raise ReachabilityError(msg)

    modules: list[Path] = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        p = Path(path)
        # Must be a recognised source extension for this language.
        if p.suffix not in exts:
            continue
        # Excluded by filename.
        if p.name in _EXCLUDE_NAMES:
            continue
        # Excluded by path pattern (tests/, __tests__/, test_*.py, etc.).
        if _EXCLUDE_NAME_RE.search(path) or _EXCLUDE_DIRS_RE.search(path):
            continue
        modules.append(p)

    return modules


def find_importers(repo_root: Path, module: Path, lang: str) -> list[Path]:
    """Return repo-relative Paths of files that import *module*, excluding the module itself
    and all test files (co-located, under tests/, tests/core/, __tests__/, or any
    path matching the test-file patterns).

    Python (lang='py'):
      Given foo/bar.py the pkg dotted path is foo.bar and the bare name is bar.
      Grep for any of:
        import foo.bar
        from foo.bar import
        from foo import bar
        import bar  (word boundary)
      across *.py files.

    TypeScript/JavaScript (lang='ts'|'js'):
      Grep for ``from '...{stem}'`` / ``require('...{stem}')`` referencing the module's
      basename (without extension), anchored at a path-component boundary (/, ./, or start
      of path segment) so that stem='bar' does NOT match './foobar'.

    Go (lang='go'):
      Grep for the module's directory path (package) in import blocks.

    Error policy (fail CLOSED):
      - grep exit code 1 = "no matches" → NORMAL, returns [] → caller produces ORPHAN.
      - grep exit code >= 2 = real error → RAISES ReachabilityError.
      Test-file importers are excluded from the result.

    Returns repo-relative Paths.
    """
    repo_root = Path(repo_root)
    module = Path(module)
    module_str = module.as_posix()

    # Build the set of paths to exclude (the module itself + its co-located test).
    exclude_paths: set[str] = {module_str}
    stem = module.stem
    parent = module.parent
    for candidate in [
        parent / f"test_{stem}{module.suffix}",
        parent / f"{stem}_test{module.suffix}",
        parent / f"{stem}.test{module.suffix}",
    ]:
        exclude_paths.add(candidate.as_posix())
    # Also check tests/ sibling directory.
    exclude_paths.add((parent.parent / "tests" / f"test_{stem}{module.suffix}").as_posix())

    if lang == "py":
        patterns = _py_import_patterns(module)
        raw = _grep_patterns(repo_root, patterns, "*.py")
    elif lang in ("ts", "js"):
        patterns = _ts_import_patterns(module)
        globs = ["*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs"]
        raw = []
        for g in globs:
            raw.extend(_grep_patterns(repo_root, patterns, g))
    elif lang == "go":
        patterns = _go_import_patterns(repo_root, module)
        raw = _grep_patterns(repo_root, patterns, "*.go")
    else:
        return []

    importers: list[Path] = []
    seen: set[str] = set()
    for p in raw:
        rel = p.as_posix()
        if rel in seen or rel in exclude_paths:
            continue
        # Exclude ALL test files — co-located, nested under tests/, __tests__/, or any
        # path matching the test-file or test-directory patterns.
        if _EXCLUDE_NAME_RE.search(rel) or _EXCLUDE_DIRS_RE.search(rel):
            continue
        seen.add(rel)
        importers.append(p)

    return importers


def reachability_verdict(
    repo_root: Path,
    module: Path,
    lang: str,
    reachable_via: str | None = None,
    tier: str = "domain-model",
) -> dict:
    """Compute the reachability verdict for a single *module*.

    Steps:
    1. EXEMPT if *reachable_via* starts with a known scheme prefix (cli:|route:|tool:|hook:|plugin:|dynamic:).
       (v1: scheme accepted on trust; verification is a TODO.)
    2. Call find_importers.  WIRED if any found, else ORPHAN.
       On ReachabilityError (real grep/subprocess failure): return ERROR verdict.

    Verdict contract (fail CLOSED):
      WIRED  → PASS (imported by at least one non-test file)
      EXEMPT → PASS (declared reachable via scheme)
      ORPHAN → BLOCKING (no non-test importer found)
      ERROR  → BLOCKING (subprocess failure; sweep result is untrustworthy)

    Returns a dict::

        {
            "verdict":      "WIRED" | "ORPHAN" | "EXEMPT" | "ERROR",
            "module":       str,
            "importers":    [str, ...],
            "reachable_via": str | None,
            "exempt_reason": str | None,   # scheme name if EXEMPT
            "lang":         str,
            "error":        str | None,    # only present for ERROR verdict
        }
    """
    module = Path(module)
    module_str = module.as_posix()

    # Step 1: scheme exemption.
    if reachable_via:
        for scheme in _EXEMPT_SCHEMES:
            if reachable_via.startswith(scheme):
                return {
                    "verdict": "EXEMPT",
                    "module": module_str,
                    "importers": [],
                    "reachable_via": reachable_via,
                    "exempt_reason": scheme.rstrip(":"),
                    "lang": lang,
                }

    # Step 2: importer sweep.
    try:
        importers = find_importers(repo_root, module, lang)
    except ReachabilityError as exc:
        logger.warning(
            "reachability_verdict: find_importers raised ReachabilityError for %s: %s — returning ERROR",
            module_str,
            exc,
        )
        return {
            "verdict": "ERROR",
            "module": module_str,
            "importers": [],
            "reachable_via": reachable_via,
            "exempt_reason": None,
            "lang": lang,
            "error": str(exc),
        }

    verdict = "WIRED" if importers else "ORPHAN"
    return {
        "verdict": verdict,
        "module": module_str,
        "importers": [p.as_posix() for p in importers],
        "reachable_via": reachable_via,
        "exempt_reason": None,
        "lang": lang,
    }


def sweep_task(
    repo_root: Path,
    task: dict,
    start_commit: str,
) -> dict:
    """Run the reachability sweep for a task.

    Used by execute-task and ship-check Gate 6.

    Logic:
    - tier = task.phaseConfig.tier or task.tier or "domain-model".
    - If tier in {spike, domain-model}: EXEMPT (not swept; reachability not required at this phase).
    - If task.entrypoint is truthy: EXEMPT (entrypoints are by definition reachable via the outside world).
    - Else (tier in {wired, live}): sweep new modules and compute per-module verdicts.
      Task verdict = ORPHAN if ANY module is ORPHAN.
      Task verdict = ERROR  if ANY module is ERROR (or if new_modules_for_task raises).
      Else WIRED (EXEMPT modules don't make the task orphan).

    Verdict contract (fail CLOSED):
      WIRED  → PASS
      EXEMPT → PASS
      ORPHAN → BLOCKING
      ERROR  → BLOCKING (never silently pass on a broken environment)

    Returns::

        {
            "verdict":      "WIRED" | "ORPHAN" | "EXEMPT" | "ERROR",
            "tier":         str,
            "modules":      [<per-module verdict dicts>],
            "reason":       str | None,        # only for EXEMPT
            "checked_at":   str (ISO-8601),
            "start_commit": str,
            "error":        str | None,        # only for ERROR
        }
    """
    repo_root = Path(repo_root)
    tier = (
        (task.get("phaseConfig") or {}).get("tier")
        or task.get("tier")
        or "domain-model"
    )
    checked_at = datetime.now(timezone.utc).isoformat()

    # Tier-exempt (spike / domain-model): do not sweep.
    if tier in ("spike", "domain-model"):
        return {
            "verdict": "EXEMPT",
            "reason": "tier-exempt",
            "tier": tier,
            "modules": [],
            "checked_at": checked_at,
            "start_commit": start_commit,
        }

    # Entrypoint tasks are by definition wired to an external caller.
    if task.get("entrypoint"):
        return {
            "verdict": "EXEMPT",
            "reason": "entrypoint",
            "tier": tier,
            "modules": [],
            "checked_at": checked_at,
            "start_commit": start_commit,
        }

    # Sweep (tier in {wired, live}).
    lang = language_for_repo(repo_root)
    try:
        new_modules = new_modules_for_task(repo_root, start_commit)
    except ReachabilityError as exc:
        logger.warning("sweep_task: new_modules_for_task raised ReachabilityError: %s — returning ERROR", exc)
        return {
            "verdict": "ERROR",
            "tier": tier,
            "modules": [],
            "checked_at": checked_at,
            "start_commit": start_commit,
            "error": str(exc),
        }

    reachable_via = task.get("reachableVia")
    module_verdicts: list[dict] = []

    for mod in new_modules:
        v = reachability_verdict(
            repo_root=repo_root,
            module=mod,
            lang=lang,
            reachable_via=reachable_via,
            tier=tier,
        )
        module_verdicts.append(v)

    # Task is ORPHAN if ANY module is ORPHAN; ERROR if ANY module is ERROR.
    # Only WIRED if no module is ORPHAN or ERROR (EXEMPT modules don't contribute).
    task_verdict = "WIRED"
    task_error: str | None = None
    for v in module_verdicts:
        if v["verdict"] == "ORPHAN":
            task_verdict = "ORPHAN"
            break
        if v["verdict"] == "ERROR":
            task_verdict = "ERROR"
            task_error = v.get("error")
            break

    result: dict = {
        "verdict": task_verdict,
        "tier": tier,
        "modules": module_verdicts,
        "checked_at": checked_at,
        "start_commit": start_commit,
    }
    if task_error is not None:
        result["error"] = task_error
    return result


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _py_import_patterns(module: Path) -> list[str]:
    """Build grep -E patterns that match Python import statements for *module*."""
    # Convert path to dotted module name: foo/bar.py -> foo.bar
    parts = list(module.with_suffix("").parts)
    dotted = ".".join(parts)          # e.g. "pkg.foo"
    name = module.stem                # e.g. "foo"
    parent_pkg = ".".join(parts[:-1]) # e.g. "pkg"  (may be empty for top-level)

    patterns = [
        rf"import {re.escape(dotted)}(\s|$|;|,)",
        rf"from {re.escape(dotted)} import",
    ]
    if parent_pkg:
        patterns.append(rf"from {re.escape(parent_pkg)} import {re.escape(name)}(\s|$|;|,)")
    # Bare "import name" — less precise but catches flat imports.
    patterns.append(rf"import {re.escape(name)}(\s|$|;|,)")
    return patterns


def _ts_import_patterns(module: Path) -> list[str]:
    """Build grep -E patterns that match TS/JS import/require for *module*.

    The stem is anchored at a path-component boundary so that stem='bar' does NOT
    match './foobar'.  The pattern requires that the character immediately before
    the stem (within the quoted path) is a '/' — ensuring 'bar' is the last path
    segment, not a suffix of a longer name.

    Examples (stem='bar'):
      from './bar'          ✓   '/' immediately before stem
      from '../pkg/bar'     ✓   '/' immediately before stem
      from './foobar'       ✗   no '/' immediately before 'bar' (preceded by 'o')
      require('./bar')      ✓
      require('./foobar')   ✗

    Correctness note: [^'"]*/{stem}['"] applied to './foobar' — the only '/' in
    the quoted string is at position 1 (between '.' and 'f'), and '/foobar' does
    not contain '/bar' as an anchored suffix starting after a '/'.  grep backtracks
    through all positions and finds no valid split, so './foobar' correctly does
    NOT match.
    """
    stem = re.escape(module.stem)
    return [
        rf"""from ['"][^'"]*/{stem}['"]""",
        rf"""require\(['"][^'"]*/{stem}['"]\)""",
    ]


def _go_import_patterns(repo_root: Path, module: Path) -> list[str]:
    """Build grep patterns for Go package imports."""
    # Use the directory containing the module file as the package path fragment.
    pkg_dir = module.parent.as_posix()  # e.g. "pkg/foo"
    return [rf'"{re.escape(pkg_dir)}"']


def _grep_patterns(repo_root: Path, patterns: list[str], glob: str) -> list[Path]:
    """Run grep -rEl for each pattern across files matching *glob* under *repo_root*.

    Returns a deduplicated list of repo-relative Paths of matching files.

    Error policy (fail CLOSED):
      - grep exit code 0 = matches found → normal.
      - grep exit code 1 = no matches → normal, returns [] for this pattern.
      - grep exit code >= 2 = real error (e.g. invalid regex, I/O error) →
        RAISES ReachabilityError.  The caller must propagate this upward so that
        the sweep returns ERROR rather than a false WIRED/ORPHAN.
    """
    found: set[str] = set()
    for pattern in patterns:
        result = subprocess.run(
            ["grep", "-rEl", "--include", glob,
             "--exclude-dir=tests", "--exclude-dir=__tests__",
             pattern, "."],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Matches found.
            pass
        elif result.returncode == 1:
            # No matches — completely normal, not an error.
            continue
        else:
            # rc >= 2: real grep error.
            msg = (
                f"_grep_patterns: grep returned rc={result.returncode} "
                f"for pattern {pattern!r}: {result.stderr.strip()}"
            )
            logger.warning(msg)
            raise ReachabilityError(msg)

        for line in result.stdout.splitlines():
            line = line.strip()
            if line:
                # Strip leading "./" from grep output.
                if line.startswith("./"):
                    line = line[2:]
                found.add(line)

    return [Path(p) for p in sorted(found)]
