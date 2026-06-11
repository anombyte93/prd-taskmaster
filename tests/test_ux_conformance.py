import ast
import re
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_extract_md_user_strings_reads_frontmatter_description_and_body(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text(
        "---\n"
        "name: sample\n"
        "description: >-\n"
        "  Frontmatter description text.\n"
        "---\n"
        "# Body Heading\n\n"
        "Body text here.\n"
    )

    extracted = extract_md_user_strings(path)

    assert "Frontmatter description text." in extracted
    assert "# Body Heading" in extracted
    assert "Body text here." in extracted


def test_extract_py_string_literals_collects_constants(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(
        "MESSAGE = 'Atlas Fleet is part of Atlas Pro ($29/mo)'\n"
        "def reason():\n"
        "    return f'Unlock: {\"https://atlas-ai.au/pro\"}'\n"
    )

    extracted = extract_py_string_literals(path)

    assert "Atlas Fleet is part of Atlas Pro ($29/mo)" in extracted
    assert "Unlock: " in extracted
    assert "https://atlas-ai.au/pro" in extracted


def test_banned_vocab_rule_catches_primary_labels():
    text = "phoenix CDD ralph-loop Mode D"

    violations = check_banned_vocab(text, path=Path("fixture.md"))

    assert [violation.term for violation in violations] == [
        "phoenix",
        "CDD",
        "ralph-loop",
        "Mode D",
    ]


def test_banned_vocab_rule_allows_canonical_text_and_identifiers():
    text = (
        "worker verified execution evidence-gated loop fleet mode Atlas Fleet\n"
        ".atlas-ai/cdd/task-1.json\n"
        "'ralph-loop' capability key\n"
        '"requiresCDD": true\n'
    )

    assert check_banned_vocab(text, path=Path("fixture.md")) == []


def test_repo_user_facing_vocab_lint_has_no_violations():
    violations: list[Violation] = []
    for path in iter_user_facing_files():
        text = path.read_text()
        violations.extend(check_banned_vocab(text, path=path.relative_to(REPO_ROOT)))

    assert violations == []


def test_paywall_surfaces_inline_price_pro_url_and_free_default():
    handoff = (REPO_ROOT / "skills" / "handoff" / "SKILL.md").read_text()

    locked_index = handoff.index("Atlas Fleet is a locked teaser")
    locked_context = handoff[locked_index : locked_index + 1200]
    assert "$29/mo" in locked_context
    assert "https://atlas-ai.au/pro" in locked_context
    assert "Fleet is never default while locked" in handoff
    assert "recommended free mode as the default" in handoff
    assert "estimate from your dependency graph" in handoff
    assert "actual time varies" in handoff

    all_text = "\n".join(path.read_text() for path in iter_user_facing_files())
    assert "waitlist" not in all_text.lower()
    assert "atlas-ai.au/waitlist" not in all_text

    upgrade_urls = sorted(set(re.findall(r"https://atlas-ai\.au/[A-Za-z0-9_./-]+", all_text)))
    assert all(url == "https://atlas-ai.au/pro" for url in upgrade_urls if "/pro" in url or "waitlist" in url)


def iter_user_facing_files() -> list[Path]:
    files: list[Path] = []
    files.extend(sorted((REPO_ROOT / "skills").glob("*/SKILL.md")))
    files.extend(sorted((REPO_ROOT / "phases").glob("*.md")))
    files.extend(sorted((REPO_ROOT / "templates").glob("*.md")))
    files.extend(
        REPO_ROOT / path
        for path in (
            "README.md",
            "install.sh",
            "hooks/mode_d_blocker.py",
            "prd_taskmaster/mode_recommend.py",
            "prd_taskmaster/capabilities.py",
            "mcp-server/server.py",
        )
    )
    return files


class Violation:
    def __init__(self, path: Path, line: int, term: str):
        self.path = path
        self.line = line
        self.term = term

    def __eq__(self, other):
        return (
            isinstance(other, Violation)
            and self.path == other.path
            and self.line == other.line
            and self.term == other.term
        )

    def __repr__(self):
        return f"{self.path}:{self.line}:{self.term}"


def check_banned_vocab(text: str, *, path: Path) -> list[Violation]:
    patterns = [
        ("phoenix", re.compile(r"\bphoenix\b", re.IGNORECASE)),
        ("CDD", re.compile(r"\bCDD\b", re.IGNORECASE)),
        ("ralph-loop", re.compile(r"\bralph-loop\b", re.IGNORECASE)),
        ("Mode D", re.compile(r"\bMode\s+D\b", re.IGNORECASE)),
    ]
    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _is_identifier_exception(line):
            continue
        for term, pattern in patterns:
            if pattern.search(line):
                violations.append(Violation(path, line_number, term))
    return violations


def _is_identifier_exception(line: str) -> bool:
    identifier_fragments = (
        ".atlas-ai/cdd/",
        '"requiresCDD"',
        '"cddCardId"',
        "'ralph-loop' capability key",
        "`ralph-loop` capability key",
        '"ralph-loop"',
        "'ralph-loop'",
        "mcp__atlas-cdd__",
        "atlas-cdd",
        "WORKER_CONTRACT_CDD_CARD",
        ".claude/ralph-loop.local.md",
        "/ralph-loop",
    )
    return any(fragment in line for fragment in identifier_fragments)


def extract_md_user_strings(path: Path) -> str:
    text = path.read_text()
    parts: list[str] = []
    if text.startswith("---\n"):
        _start, frontmatter, body = text.split("---", 2)
        metadata = yaml.safe_load(frontmatter) or {}
        description = metadata.get("description")
        if description:
            parts.append(str(description))
        parts.append(body.lstrip())
    else:
        parts.append(text)
    return "\n".join(parts)


def extract_py_string_literals(path: Path) -> str:
    tree = ast.parse(path.read_text())
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
    return "\n".join(values)
