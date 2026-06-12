"""Skill file frontmatter validation (retargeted to merged skills/ layout).

Tool-id prefix updated atlas-go -> prd-taskmaster; routes /atlas-go: -> /prd:.
Paths anchored to REPO_ROOT so the suite is cwd-independent.
"""
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_CONTRACT_PATHS = [
    REPO_ROOT / "SKILL.md",
    *sorted((REPO_ROOT / "phases").glob("*.md")),
    *sorted((REPO_ROOT / "skills").glob("*/SKILL.md")),
]


def _parse_frontmatter(path: str) -> dict:
    content = (REPO_ROOT / path).read_text()
    assert content.startswith("---\n"), f"{path} does not start with YAML frontmatter"
    end = content.find("\n---\n", 4)
    assert end > 0, f"{path} frontmatter not closed with ---"
    return yaml.safe_load(content[4:end])


def test_orchestrator_skill_has_valid_frontmatter():
    fm = _parse_frontmatter("skills/go/SKILL.md")
    assert fm["name"] == "go"
    assert fm["user-invocable"] is True
    assert "Skill" in fm["allowed-tools"]
    assert "Bash" in fm["allowed-tools"]
    assert "Read" in fm["allowed-tools"]


def test_orchestrator_skill_references_phase_skills():
    content = (REPO_ROOT / "skills/go/SKILL.md").read_text()
    for phase in ("setup", "discover", "generate", "handoff", "execute-task"):
        assert f"/prd:{phase}" in content, f"missing route to {phase}"


def test_orchestrator_skill_references_mcp_tools():
    content = (REPO_ROOT / "skills/go/SKILL.md").read_text()
    assert "mcp__plugin_prd_go__preflight" in content
    assert "mcp__plugin_prd_go__current_phase" in content


def test_setup_skill_has_valid_frontmatter():
    fm = _parse_frontmatter("skills/setup/SKILL.md")
    assert fm["name"] == "setup"
    assert fm["user-invocable"] is False
    assert "Read" in fm["allowed-tools"]
    assert "Bash" in fm["allowed-tools"]
    assert "Skill" in fm["allowed-tools"]
    assert "Write" not in fm["allowed-tools"]
    assert "AskUserQuestion" not in fm["allowed-tools"]


def test_setup_skill_references_gate_mcp_tools():
    content = (REPO_ROOT / "skills/setup/SKILL.md").read_text()
    assert "mcp__plugin_prd_go__check_gate" in content
    assert "mcp__plugin_prd_go__advance_phase" in content


def test_setup_skill_ports_detect_first_rule():
    content = (REPO_ROOT / "skills/setup/SKILL.md").read_text()
    assert "DETECT" in content or "detect" in content
    assert "task-master" in content


def test_setup_skill_frames_taskmaster_install_as_backend_unlock():
    content = (REPO_ROOT / "skills/setup/SKILL.md").read_text()
    assert "unlocks the TaskMaster backend" in content
    assert "Then re-run this skill" not in content
    assert "Abort the phase" not in content
    if "npm install -g task-master-ai" in content:
        install_index = content.index("npm install -g task-master-ai")
        window = content[max(0, install_index - 300): install_index + 300]
        assert "unlocks the TaskMaster backend" in window
        assert "prerequisite" not in window.lower()


def test_orchestrator_skill_defines_normative_backend_operations():
    content = (REPO_ROOT / "SKILL.md").read_text()
    assert "## Engine operations" in content
    assert "This table is normative — instruction sites reference operations by name." in content
    assert "| Operation | MCP tool (MCP-mode) | script.py (CLI-mode / fallback) |" in content
    for operation, mcp_tool, script_cmd in (
        ("init", "init_project", "init-project"),
        ("parse-prd", "parse_prd", "parse-prd"),
        ("rate", "rate_tasks", "rate"),
        ("expand", "expand_tasks", "expand"),
        ("next", "next_task", "next-task"),
        ("set-status", "set_task_status", "set-status"),
    ):
        assert f"| `{operation}` | `{mcp_tool}` | `{script_cmd}" in content, (
            f"missing engine op row: {operation}"
        )
    # normalize hard wraps — the sentence spans a line break in the doc
    flat = " ".join(content.split())
    assert "`next`/`set-status` are engine-native under every backend" in flat
    assert "## Script/agent-only operations" in content


def test_orchestrator_skill_documents_feedback_debrief():
    content = (REPO_ROOT / "SKILL.md").read_text()
    assert "## Feedback" in content
    assert "feedback_submit" in content
    assert "script.py feedback-add" in content
    assert ".atlas-ai/feedback.jsonl" in content


def test_bare_taskmaster_lifecycle_commands_are_mode_b_only():
    forbidden = ("task-master next", "task-master set-status")
    failures = []
    for path in DOC_CONTRACT_PATHS:
        rel_path = path.relative_to(REPO_ROOT)
        lines = path.read_text().splitlines()
        for line_no, line in enumerate(lines, start=1):
            if not any(command in line for command in forbidden):
                continue
            context_lines = lines[max(0, line_no - 4): min(len(lines), line_no + 3)]
            context = "\n".join(context_lines)
            if "Mode B" not in context or "TaskMaster backend only" not in context:
                failures.append(f"{rel_path}:{line_no}: {line}")
    assert not failures, "bare task-master lifecycle commands outside Mode B:\n" + "\n".join(failures)


def test_discover_skill_has_valid_frontmatter():
    fm = _parse_frontmatter("skills/discover/SKILL.md")
    assert fm["name"] == "discover"
    assert fm["user-invocable"] is False
    assert "Read" in fm["allowed-tools"]
    assert "Skill" in fm["allowed-tools"]
    assert "AskUserQuestion" in fm["allowed-tools"]
    assert "Write" in fm["allowed-tools"]
    assert "Bash" not in fm["allowed-tools"]


def test_discover_skill_references_gate_mcp_tools():
    content = (REPO_ROOT / "skills/discover/SKILL.md").read_text()
    assert "mcp__plugin_prd_go__check_gate" in content
    assert "mcp__plugin_prd_go__advance_phase" in content
    assert "GENERATE" in content


def test_discover_skill_ports_brainstorming_intercept():
    content = (REPO_ROOT / "skills/discover/SKILL.md").read_text()
    assert "superpowers:brainstorming" in content
    assert "writing-plans" in content
    assert "Interactive Mode" in content or "Interactive mode" in content
    assert "Autonomous Mode" in content or "Autonomous mode" in content
    assert "CONSTRAINTS CAPTURED" in content or "Constraint" in content
    for scale in ("Solo", "Team", "Enterprise"):
        assert scale in content, f"missing scale classification: {scale}"
    assert "session-context/discovery-" in content
    assert "sys.exit" not in content


def test_generate_skill_has_valid_frontmatter():
    fm = _parse_frontmatter("skills/generate/SKILL.md")
    assert fm["name"] == "generate"
    assert fm["user-invocable"] is False
    for t in ("Read", "Write", "Edit", "Bash", "Skill"):
        assert t in fm["allowed-tools"], f"missing tool: {t}"
    assert "AskUserQuestion" not in fm["allowed-tools"]


def test_generate_skill_references_gate_mcp_tools():
    content = (REPO_ROOT / "skills/generate/SKILL.md").read_text()
    assert "mcp__plugin_prd_go__check_gate" in content
    assert "mcp__plugin_prd_go__advance_phase" in content
    assert "HANDOFF" in content


def test_generate_skill_ports_six_steps():
    content = (REPO_ROOT / "skills/generate/SKILL.md").read_text()
    assert ".taskmaster/docs/prd.md" in content
    assert "backend op parse-prd" in content
    assert "script.py parse-prd" in content
    assert "backend op rate" in content
    assert "script.py rate" in content
    assert "backend op expand" in content
    assert "script.py expand" in content
    assert "TaskMaster backend direct methods" in content
    assert ".taskmaster/tasks/tasks.json" in content
    assert ".taskmaster/reports/task-complexity-report.json" in content
    assert "validate-prd" in content or "validate_prd" in content
    assert "calc-tasks" in content or "calc_tasks" in content
    assert "analyze-complexity" in content or "analyze_complexity" in content
    assert "sys.exit" not in content


def test_generate_skill_enforces_anti_parallel_warning():
    content = (REPO_ROOT / "skills/generate/SKILL.md").read_text()
    assert "in parallel" in content
    assert "expand_task" in content
    assert "CONSTRAINT" in content or "Constraint" in content
    assert "SCOPE" in content or "Scope" in content
    assert "reason:" in content
    assert "deferred" in content.lower()
    assert "placeholder" in content.lower()


def test_handoff_skill_has_valid_frontmatter():
    fm = _parse_frontmatter("skills/handoff/SKILL.md")
    assert fm["name"] == "handoff"
    assert fm["user-invocable"] is False
    for t in ("Read", "Skill", "AskUserQuestion"):
        assert t in fm["allowed-tools"], f"missing {t}"
    for t in ("Bash", "Write", "Edit"):
        assert t not in fm["allowed-tools"], f"forbidden tool present: {t}"


def test_handoff_skill_drops_plan_mode():
    content = (REPO_ROOT / "skills/handoff/SKILL.md").read_text()
    assert "EnterPlanMode" not in content, "spec section 13.5 forbids Plan Mode in handoff"
    assert "ExitPlanMode" not in content, "spec section 13.5 forbids Plan Mode in handoff"
    assert "AskUserQuestion" in content
    assert "EXECUTE" in content
    for m in ("Mode A", "Mode B", "Mode C"):
        assert m in content, f"missing mode: {m}"


def test_handoff_skill_references_gate_mcp_tools():
    content = (REPO_ROOT / "skills/handoff/SKILL.md").read_text()
    assert "mcp__plugin_prd_go__check_gate" in content
    assert "mcp__plugin_prd_go__advance_phase" in content
    assert "EXECUTE" in content


def test_handoff_skill_ports_mode_selection_and_teaser():
    content = (REPO_ROOT / "skills/handoff/SKILL.md").read_text()
    assert ".taskmaster/docs/prd.md" in content
    assert "tasks.json" in content
    assert "ralph-loop" in content.lower() or "ralph loop" in content.lower()
    # Mode D is now branded "Atlas Fleet" / "Atlas Pro", shown as a locked
    # teaser (was "Atlas-Auto" / "coming soon" in the plugin).
    assert "Atlas Fleet" in content or "Atlas Pro" in content
    assert "teaser" in content.lower() or "locked" in content.lower()
    assert "sys.exit" not in content


def test_execute_task_skill_uses_standard_taskmaster_root():
    content = (REPO_ROOT / "skills/execute-task/SKILL.md").read_text()
    assert ".taskmaster/tasks/tasks.json" in content
    assert "TASK_MASTER_PROJECT_ROOT=.atlas-ai/taskmaster" not in content
    assert ".atlas-ai/taskmaster/tasks/tasks.json" not in content


def test_expand_tasks_skill_is_user_invocable():
    fm = _parse_frontmatter("skills/expand-tasks/SKILL.md")
    assert fm["name"] == "expand-tasks"
    assert fm["user-invocable"] is True, "expand-tasks is a companion skill, must be user-invocable"
    for t in ("Read", "Write", "Bash", "Task"):
        assert t in fm["allowed-tools"], f"missing tool: {t}"


def test_expand_tasks_skill_references_plugin_mcp_and_agent():
    content = (REPO_ROOT / "skills/expand-tasks/SKILL.md").read_text()
    assert "mcp__plugin_prd_go__" in content
    assert "task-master" in content
    assert "tasks.json" in content
    assert "parallel" in content.lower()
    assert "Wave" in content
    assert "research-expander" in content
    assert "sys.exit" not in content
    assert len(content.splitlines()) >= 80, "expand-tasks SKILL.md too short"


def test_expand_tasks_skill_mentions_backend_op_expand_native_api():
    content = (REPO_ROOT / "skills/expand-tasks/SKILL.md").read_text()
    assert "backend op expand (native api)" in content


def test_research_expander_agent_has_valid_frontmatter():
    fm = _parse_frontmatter("agents/research-expander.md")
    assert fm["name"] == "research-expander"
    assert fm.get("description"), "agent needs description"
    assert fm.get("tools") is not None, "agent needs tools field"


def test_research_expander_agent_body_shape():
    content = (REPO_ROOT / "agents/research-expander.md").read_text()
    assert "sys.exit" not in content
    assert len(content.splitlines()) >= 30, "research-expander agent too short"


def test_customise_workflow_skill_is_user_invocable():
    fm = _parse_frontmatter("skills/customise-workflow/SKILL.md")
    assert fm["name"] == "customise-workflow"
    assert fm["user-invocable"] is True
    for t in ("Read", "Write", "AskUserQuestion"):
        assert t in fm["allowed-tools"], f"missing tool: {t}"


def test_customise_workflow_uses_plugin_atlas_paths():
    content = (REPO_ROOT / "skills/customise-workflow/SKILL.md").read_text()
    assert ".atlas-ai/config/atlas.json" in content, "must write to plugin atlas.json path"
    assert ".atlas-ai/customizations/" in content, "must reference customizations dir"
    assert ".taskmaster/config/user-workflow.json" not in content, "old v4 path must not regress"
    for phase in ("LOAD", "ASK", "VALIDATE", "WRITE", "VERIFY"):
        assert phase in content, f"missing 5-phase marker: {phase}"
    assert "AskUserQuestion" in content
    assert "curated" in content.lower() and "question" in content.lower()
    assert "validate-answer" in content
    assert "show-config" in content
    assert "customization" in content.lower() or "customisation" in content.lower()
    assert "sys.exit" not in content
    assert len(content.splitlines()) >= 60, "customise-workflow SKILL.md too short"


def test_execute_task_skill_has_valid_frontmatter():
    fm = _parse_frontmatter("skills/execute-task/SKILL.md")
    assert fm["name"] == "execute-task"
    assert fm["user-invocable"] is True
    for t in ("Read", "Write", "Edit", "Bash", "Skill", "Agent"):
        assert t in fm["allowed-tools"], f"missing tool: {t}"
    assert "AskUserQuestion" not in fm["allowed-tools"]


def test_execute_task_skill_implements_cdd_loop():
    content = (REPO_ROOT / "skills/execute-task/SKILL.md").read_text()
    for phrase in ("Heartbeat check", "Route by status", "Triple verification", "SHIP_CHECK_OK"):
        assert phrase in content, f"missing loop element: {phrase}"
    for enum in ("DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED"):
        assert enum in content, f"missing route status: {enum}"
    assert "script.py next-task" in content
    assert "script.py set-status" in content
    assert "task-master next --format json" not in content
    assert "sys.exit" not in content
    assert "EnterPlanMode" not in content


def test_execute_fleet_skill_uses_backend_set_status():
    content = (REPO_ROOT / "skills/execute-fleet/SKILL.md").read_text()
    assert "script.py set-status" in content
    assert "task-master set-status" not in content
