"""Contract tests: SKILL.md ↔ script.py ↔ install.sh ↔ templates consistency.

These tests catch the #1 class of user-facing breakage: when SKILL.md tells
the AI to run commands that script.py doesn't support, or when paths/names
don't match across files.

A Claude Code skill is a CONTRACT: SKILL.md is the spec, script.py is the impl.
If the spec says "run X" and X doesn't exist, every user is broken.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPT_PY, EXPAND_SCRIPT_PY, PROJECT_ROOT, TEMPLATE_DIR, run_script


# ═══════════════════════════════════════════════════════════════════════════════
# SKILL.MD ↔ SCRIPT.PY CONTRACT
# ═══════════════════════════════════════════════════════════════════════════════


class TestSkillMdContract:
    """Every command in SKILL.md must be accepted by script.py's argparse."""

    @pytest.fixture(autouse=True)
    def _load_skill_md(self):
        self.skill_md = (PROJECT_ROOT / "SKILL.md").read_text()

    def _extract_subcommands_from_skill(self):
        """Extract all script.py subcommand invocations from SKILL.md."""
        # Pattern: script.py <subcommand> — capture word+hyphen combos
        pattern = r'script\.py\s+([a-z][a-z0-9-]*)'
        matches = re.findall(pattern, self.skill_md)
        # Filter out paths and non-subcommand matches
        subcommands = set()
        for m in matches:
            if '/' in m or '.' in m or m.startswith('-'):
                continue
            subcommands.add(m)
        return subcommands

    def test_all_skill_subcommands_exist_in_script(self):
        """Every subcommand referenced in SKILL.md exists in script.py's argparse."""
        skill_subcommands = self._extract_subcommands_from_skill()

        # Get actual subcommands from script.py
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PY), "--help"],
            capture_output=True, text=True,
        )
        help_text = result.stdout + result.stderr

        for subcmd in skill_subcommands:
            assert subcmd in help_text, \
                f"SKILL.md references 'script.py {subcmd}' but script.py doesn't have that subcommand"

    def test_preflight_subcommand_matches(self):
        """SKILL.md Step 1 'preflight' works as documented."""
        # SKILL.md line 47: python3 script.py preflight
        rc, out = run_script(SCRIPT_PY, ["preflight"], cwd="/tmp")
        assert rc == 0
        assert out["ok"] is True
        # SKILL.md says it returns these fields:
        expected_fields = ["has_taskmaster", "prd_path", "task_count",
                          "tasks_completed", "tasks_pending", "taskmaster_method",
                          "has_claude_md", "has_crash_state", "crash_state"]
        for field in expected_fields:
            assert field in out, f"SKILL.md says preflight returns '{field}' but it's missing"

    def test_validate_prd_accepts_input_flag(self):
        """SKILL.md Step 7 uses '--input' flag which must exist."""
        # SKILL.md line 152: script.py validate-prd --input .taskmaster/docs/prd.md
        # Test that --input is accepted (even with nonexistent file, argparse should parse)
        rc, out = run_script(SCRIPT_PY, ["validate-prd", "--input", "/nonexistent/prd.md"])
        assert rc == 1  # file not found, but argparse accepted the flag
        assert "not found" in out.get("error", "").lower()

    def test_load_template_types_match_skill_md(self):
        """SKILL.md Step 6 documents 'comprehensive|minimal' types."""
        # SKILL.md line 135: script.py load-template --type <comprehensive|minimal>
        for template_type in ["comprehensive", "minimal"]:
            rc, out = run_script(SCRIPT_PY, ["load-template", "--type", template_type])
            assert rc == 0, f"Template type '{template_type}' from SKILL.md not accepted"

    def test_calc_tasks_accepts_requirements_flag(self):
        """SKILL.md Step 8 uses '--requirements' flag."""
        # SKILL.md line 172: script.py calc-tasks --requirements <count>
        rc, out = run_script(SCRIPT_PY, ["calc-tasks", "--requirements", "10"])
        assert rc == 0

    def test_gen_test_tasks_accepts_total_flag(self):
        """SKILL.md Step 9 uses '--total' flag."""
        # SKILL.md line 194: script.py gen-test-tasks --total <task_count>
        rc, out = run_script(SCRIPT_PY, ["gen-test-tasks", "--total", "10"])
        assert rc == 0

    def test_gen_scripts_accepts_output_dir_flag(self):
        """SKILL.md Step 10 uses '--output-dir' flag."""
        # SKILL.md line 208: script.py gen-scripts --output-dir .taskmaster/scripts
        rc, out = run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", "/tmp/test-scripts"])
        assert rc == 0

    def test_init_taskmaster_accepts_method_flag(self):
        """SKILL.md Step 5 uses '--method' flag with cli|mcp."""
        # SKILL.md line 123: script.py init-taskmaster --method <cli|mcp>
        rc, out = run_script(SCRIPT_PY, ["init-taskmaster", "--method", "mcp"])
        assert rc == 0

    def test_backup_prd_accepts_input_flag(self):
        """SKILL.md Step 2 references backup-prd with --input."""
        # SKILL.md line 69: script.py backup-prd --input <path>
        rc, out = run_script(SCRIPT_PY, ["backup-prd", "--input", "/nonexistent.md"])
        assert rc == 1  # file not found but argparse accepted
        assert out["ok"] is False

    def test_log_progress_accepts_all_documented_flags(self):
        """SKILL.md Step 12 documents all log-progress flags."""
        # SKILL.md line 264: --task-id --title --duration --subtasks --tests --issues
        rc, out = run_script(SCRIPT_PY, [
            "log-progress",
            "--task-id", "1",
            "--title", "Test",
            "--duration", "1h",
            "--subtasks", "2/3",
            "--tests", "5 passed",
            "--issues", "none",
        ], cwd="/tmp")
        assert rc == 0

    def test_detect_taskmaster_subcommand_exists(self):
        """SKILL.md Step 3 references detect-taskmaster."""
        # SKILL.md line 83: script.py detect-taskmaster
        rc, out = run_script(SCRIPT_PY, ["detect-taskmaster"])
        assert rc == 0

    def test_read_state_subcommand_exists(self):
        """SKILL.md Step 1 crash recovery uses read-state."""
        rc, out = run_script(SCRIPT_PY, ["read-state"], cwd="/tmp")
        assert rc == 0


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE PLACEHOLDERS
# ═══════════════════════════════════════════════════════════════════════════════


class TestTemplateContract:
    """CLAUDE.md.template placeholders must match SKILL.md Step 10.5 documentation."""

    @pytest.fixture(autouse=True)
    def _load_files(self):
        self.template = (TEMPLATE_DIR / "CLAUDE.md.template").read_text()
        self.skill_md = (PROJECT_ROOT / "SKILL.md").read_text()

    def test_template_file_exists(self):
        """CLAUDE.md.template must exist in templates/."""
        assert (TEMPLATE_DIR / "CLAUDE.md.template").exists()

    def test_all_placeholders_are_double_braced(self):
        """All placeholders use {{NAME}} format."""
        placeholders = re.findall(r'\{\{(\w+)\}\}', self.template)
        assert len(placeholders) >= 5, "Template should have at least 5 placeholders"

    def test_documented_placeholders_exist_in_template(self):
        """Placeholders documented in SKILL.md Step 10.5 exist in template."""
        # SKILL.md line 222-223 documents these placeholders:
        documented = [
            "PROJECT_NAME",
            "TECH_STACK",
            "ARCHITECTURE_OVERVIEW",
            "KEY_DEPENDENCIES",
            "TESTING_FRAMEWORK",
            "DEV_ENVIRONMENT",
            "TEST_COMMAND",
        ]
        template_placeholders = set(re.findall(r'\{\{(\w+)\}\}', self.template))
        for placeholder in documented:
            assert placeholder in template_placeholders, \
                f"SKILL.md documents placeholder '{{{{{placeholder}}}}}' but it's missing from template"

    def test_no_undocumented_placeholders(self):
        """Template doesn't have placeholders that SKILL.md doesn't mention."""
        documented = {
            "PROJECT_NAME", "TECH_STACK", "ARCHITECTURE_OVERVIEW",
            "KEY_DEPENDENCIES", "TESTING_FRAMEWORK", "DEV_ENVIRONMENT",
            "TEST_COMMAND",
        }
        template_placeholders = set(re.findall(r'\{\{(\w+)\}\}', self.template))
        undocumented = template_placeholders - documented
        assert len(undocumented) == 0, \
            f"Template has undocumented placeholders: {undocumented}"

    def test_template_is_valid_markdown(self):
        """Template is valid markdown (no unclosed code blocks)."""
        # Count ``` pairs — should be even
        triple_backticks = self.template.count('```')
        assert triple_backticks % 2 == 0, \
            f"Template has {triple_backticks} ``` markers (odd = unclosed code block)"

    def test_template_has_taskmaster_references(self):
        """Template references taskmaster workflow correctly."""
        assert ".taskmaster" in self.template
        assert "taskmaster" in self.template.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-FILE CONSISTENCY
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossFileConsistency:
    """Version numbers, paths, and names must match across all files."""

    @pytest.fixture(autouse=True)
    def _load_files(self):
        self.skill_md = (PROJECT_ROOT / "SKILL.md").read_text()
        self.install_sh = (PROJECT_ROOT / "install.sh").read_text()
        self.readme = (PROJECT_ROOT / "README.md").read_text()
        self.script_py = (PROJECT_ROOT / "script.py").read_text()

    def test_install_sh_version_matches_readme(self):
        """Version in install.sh should be referenced in README version history."""
        # install.sh: VERSION="3.0.0"
        install_version = re.search(r'VERSION="([^"]+)"', self.install_sh)
        assert install_version, "VERSION not found in install.sh"
        version = install_version.group(1)
        # README may use "v3.0" or "3.0.0" or "v3.0.0" format
        major_minor = ".".join(version.split(".")[:2])  # "3.0"
        assert version in self.readme or \
               "v" + version in self.readme or \
               "v" + major_minor in self.readme or \
               major_minor in self.readme, \
            f"install.sh version {version} (or {major_minor}) not found in README.md"

    def test_skill_name_consistency(self):
        """Skill name in SKILL.md frontmatter matches install.sh."""
        # SKILL.md: name: prd-taskmaster
        skill_name_match = re.search(r'^name:\s*(\S+)', self.skill_md, re.MULTILINE)
        assert skill_name_match
        skill_name = skill_name_match.group(1)

        # install.sh: SKILL_NAME="prd-taskmaster"
        install_name_match = re.search(r'SKILL_NAME="([^"]+)"', self.install_sh)
        assert install_name_match
        install_name = install_name_match.group(1)

        assert skill_name == install_name, \
            f"SKILL.md name '{skill_name}' != install.sh SKILL_NAME '{install_name}'"

    def test_script_py_subcommands_match_dispatch_table(self):
        """All subcommands in argparse are in the DISPATCH dict, and vice versa."""
        # Extract subparser names from add_parser calls
        parser_names = set(re.findall(r'sub\.add_parser\("([^"]+)"', self.script_py))
        # Extract DISPATCH keys
        dispatch_keys = set(re.findall(r'"([^"]+)":\s*cmd_', self.script_py))

        assert parser_names == dispatch_keys, \
            f"Parser/dispatch mismatch. In parser only: {parser_names - dispatch_keys}. In dispatch only: {dispatch_keys - parser_names}"

    def test_readme_subcommands_match_script(self):
        """README's subcommand table matches script.py's actual commands."""
        # README has a table with | Command | Purpose |
        readme_commands = set(re.findall(r'\|\s*`(\S+)`\s*\|', self.readme))
        # Filter to just subcommand names
        readme_subcmds = {c for c in readme_commands if not c.startswith('-')}

        # script.py dispatch
        script_subcmds = set(re.findall(r'"([^"]+)":\s*cmd_', self.script_py))

        # README may not list all, but everything it lists should exist
        for cmd in readme_subcmds:
            assert cmd in script_subcmds, \
                f"README documents command '{cmd}' but it doesn't exist in script.py"

    def test_install_sh_repo_url_is_valid(self):
        """Install.sh's CLONE_URL should reference a valid-looking GitHub URL."""
        clone_url_match = re.search(r'CLONE_URL="([^"]+)"', self.install_sh)
        assert clone_url_match
        url = clone_url_match.group(1)
        assert "github.com" in url
        assert url.endswith(".git")

    def test_skill_md_references_correct_template_types(self):
        """SKILL.md's template types match what load-template accepts."""
        # SKILL.md: --type <comprehensive|minimal>
        skill_types = re.findall(r'--type\s+(?:<)?(\w+(?:\|\w+)*)', self.skill_md)
        if skill_types:
            types_str = skill_types[0]
            documented_types = set(types_str.split('|'))
        else:
            documented_types = set()

        # script.py: choices=["comprehensive", "minimal"]
        script_types = set(re.findall(r'choices=\["([^"]+)",\s*"([^"]+)"\]', self.script_py)[0])

        assert documented_types == script_types, \
            f"SKILL.md types {documented_types} != script.py types {script_types}"


# ═══════════════════════════════════════════════════════════════════════════════
# GENERATED SCRIPTS EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeneratedScriptsExecution:
    """Every generated script must actually run without import/syntax errors."""

    @pytest.fixture
    def scripts_dir(self, tmp_path):
        """Generate all 5 scripts into a temp dir."""
        run_script(SCRIPT_PY, ["gen-scripts", "--output-dir", str(tmp_path / "scripts")])
        return tmp_path / "scripts"

    def test_security_audit_runs_on_real_code(self, scripts_dir, tmp_path):
        """security-audit.py runs and finds patterns in realistic code."""
        # Create files with known security-relevant patterns
        (tmp_path / "auth.py").write_text(
            "import bcrypt\n"
            "password_hash = bcrypt.hashpw(password, bcrypt.gensalt())\n"
            "session_token = jwt.encode(payload, secret)\n"
        )
        (tmp_path / "db.py").write_text(
            "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))\n"
            "result = db.query('INSERT INTO logs VALUES (?)', (msg,))\n"
        )
        (tmp_path / "api.py").write_text(
            "app = flask.Flask(__name__)\n"
            "@app.route('/api/users', methods=['POST'])\n"
            "def create_user():\n"
            "    return jsonify(user)\n"
        )
        (tmp_path / "config.py").write_text(
            "DB_URL = os.environ['DATABASE_URL']\n"
            "SECRET = process.env.SECRET_KEY\n"
        )

        result = subprocess.run(
            [sys.executable, str(scripts_dir / "security-audit.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"security-audit.py crashed: {result.stderr}"
        out = json.loads(result.stdout)
        assert out["ok"] is True
        # Should detect multiple categories
        assert len(out["categories_detected"]) >= 3
        assert "authentication" in out["categories_detected"]
        assert "database" in out["categories_detected"]
        assert "api" in out["categories_detected"]
        # Should generate relevant checklist items
        assert len(out["checklist"]) >= 5
        # Always-included items should be present
        checklist_text = " ".join(out["checklist"]).lower()
        assert "dependencies" in checklist_text
        assert "error messages" in checklist_text

    def test_learn_accuracy_with_real_data(self, scripts_dir, tmp_path):
        """learn-accuracy.py produces meaningful analysis with completed tasks."""
        # Create time tracking data with completed tasks
        state_dir = tmp_path / ".taskmaster" / "state"
        state_dir.mkdir(parents=True)
        tracking_data = {
            "tasks": {
                "1": {"started": "2026-04-10T08:00:00+00:00", "completed": "2026-04-10T10:30:00+00:00", "status": "done", "duration_minutes": 150.0},
                "2": {"started": "2026-04-10T11:00:00+00:00", "completed": "2026-04-10T13:00:00+00:00", "status": "done", "duration_minutes": 120.0},
                "3": {"started": "2026-04-10T14:00:00+00:00", "status": "in_progress"},
            }
        }
        (state_dir / "time-tracking.json").write_text(json.dumps(tracking_data))

        result = subprocess.run(
            [sys.executable, str(scripts_dir / "learn-accuracy.py")],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"learn-accuracy.py crashed: {result.stderr}"
        out = json.loads(result.stdout)
        assert out["ok"] is True
        assert out["tasks_analyzed"] == 2  # only completed tasks with duration
        assert out["average_duration_minutes"] == 135.0  # (150 + 120) / 2
        assert out["total_minutes"] == 270.0

    def test_rollback_sh_with_real_git_repo(self, scripts_dir, tmp_path):
        """rollback.sh works with a real git repo and checkpoint tags."""
        # Init git repo
        env = {**os.environ, "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t.com",
               "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t.com"}
        subprocess.run(["git", "init"], capture_output=True, cwd=str(tmp_path), env=env)

        # Create initial commit
        (tmp_path / "file1.txt").write_text("version 1")
        subprocess.run(["git", "add", "."], capture_output=True, cwd=str(tmp_path))
        subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, cwd=str(tmp_path), env=env)

        # Create checkpoint tag
        subprocess.run(["git", "tag", "checkpoint-task-001"], capture_output=True, cwd=str(tmp_path))

        # Make changes AFTER the checkpoint
        (tmp_path / "file2.txt").write_text("version 2 - after checkpoint")
        subprocess.run(["git", "add", "."], capture_output=True, cwd=str(tmp_path))
        subprocess.run(["git", "commit", "-m", "post-checkpoint"], capture_output=True, cwd=str(tmp_path), env=env)

        # Verify file2 exists before rollback
        assert (tmp_path / "file2.txt").exists()

        # Run rollback
        result = subprocess.run(
            ["bash", str(scripts_dir / "rollback.sh"), "1"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        assert result.returncode == 0, f"rollback.sh failed: {result.stdout}\n{result.stderr}"
        assert "Rollback complete" in result.stdout

        # Verify rollback worked — file2 should be gone
        assert not (tmp_path / "file2.txt").exists(), "Rollback didn't remove post-checkpoint file"
        assert (tmp_path / "file1.txt").exists(), "Rollback removed pre-checkpoint file"

    def test_all_generated_scripts_parse_without_error(self, scripts_dir):
        """Every generated Python script can be imported without errors."""
        for script_name in ["track-time.py", "learn-accuracy.py", "security-audit.py", "execution-state.py"]:
            result = subprocess.run(
                [sys.executable, "-c", f"import py_compile; py_compile.compile('{scripts_dir / script_name}', doraise=True)"],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"{script_name} has syntax error: {result.stderr}"

    def test_rollback_sh_syntax_valid(self, scripts_dir):
        """rollback.sh passes bash syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(scripts_dir / "rollback.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"rollback.sh syntax error: {result.stderr}"
