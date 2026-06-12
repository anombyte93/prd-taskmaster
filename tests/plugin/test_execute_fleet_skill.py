"""Structural coverage for the execute-fleet phase skill.

The skill is an orchestration contract, so these tests intentionally assert
grep-able markers and tool ids rather than trying to execute Atlas Fleet.
"""
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = REPO_ROOT / "skills" / "execute-fleet" / "SKILL.md"


def _content() -> str:
    assert SKILL_PATH.exists(), "skills/execute-fleet/SKILL.md must exist"
    return SKILL_PATH.read_text()


def _frontmatter() -> dict:
    content = _content()
    assert content.startswith("---\n"), "execute-fleet skill must start with YAML frontmatter"
    end = content.find("\n---\n", 4)
    assert end > 0, "execute-fleet frontmatter must be closed with ---"
    return yaml.safe_load(content[4:end])


def test_execute_fleet_skill_has_valid_frontmatter():
    fm = _frontmatter()
    assert fm["name"] == "execute-fleet"
    assert fm["user-invocable"] is False
    assert "Read" in fm["allowed-tools"]
    assert "Bash" in fm["allowed-tools"]
    assert "Skill" in fm["allowed-tools"]


def test_execute_fleet_skill_references_required_mcp_tools():
    content = _content()
    for tool_id in (
        "mcp__plugin_prd_go__compute_fleet_waves",
        "mcp__atlas-launcher__session_spawn",
        "mcp__atlas-launcher__session_send",
        "mcp__atlas-launcher__inbox_read",
        "mcp__atlas-launcher__inbox_send",
    ):
        assert tool_id in content, f"missing tool id: {tool_id}"


def test_execute_fleet_worker_prompt_has_contract_fields():
    content = _content()
    for marker in (
        "WORKER_CONTRACT_ORCHESTRATOR_REPORT_TO",
        "WORKER_CONTRACT_FULL_TASK_JSON_INLINE",
        "WORKER_CONTRACT_WORKTREE_BRANCH",
        "WORKER_CONTRACT_CDD_CARD",
        "WORKER_CONTRACT_TERMINAL_STATUS",
        "WORKER_CONTRACT_HARD_RULES",
        "WORKER_CONTRACT_QUESTIONS_INBOX",
    ):
        assert content.count(marker) == 1, f"{marker} must appear exactly once"


def test_execute_fleet_skill_states_hard_gates():
    content = _content()
    assert "SOLE-WRITER RULE" in content
    assert ".taskmaster/tasks/tasks.json" in content
    assert ".atlas-ai/state/pipeline.json" in content
    assert "Never mark a task done without the CDD card" in content
    assert "re-queue the task ONCE" in content
    assert "second failure" in content and "BLOCKED" in content
    assert "Merge conflict" in content and "do not force" in content


def test_execute_fleet_skill_states_worker_status_vocabulary():
    content = _content()
    for status in ("DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"):
        assert status in content, f"missing worker status: {status}"


def test_execute_fleet_skill_renders_status_and_terminates_safely():
    content = _content()
    assert "atlas fleet" in content
    assert "wave 2 of 3" in content
    assert "claude-1" in content
    assert "codex-1" in content
    assert "Gate: a wave merges only after the checker approves it" in content
    assert "python3 skel/ship-check.py" in content
    assert "SHIP_CHECK_OK" in content
    assert "main is never auto-touched" in content
