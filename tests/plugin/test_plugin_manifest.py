import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_plugin_manifest_exists():
    p = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert p.exists(), "plugin.json must exist at .claude-plugin/plugin.json"


def _package_version() -> str:
    import re
    text = (REPO_ROOT / "prd_taskmaster" / "__init__.py").read_text()
    return re.search(r'__version__\s*=\s*["\']([^"\']+)', text).group(1)


def test_plugin_manifest_has_required_fields():
    data = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert data["name"] == "prd"
    # version must agree with the package source of truth (no magic constants;
    # the CI version-agreement job checks the full quintet)
    assert data["version"] == _package_version()
    assert "description" in data
    assert "author" in data


def test_mcp_json_exists_and_references_plugin_root():
    data = json.loads((REPO_ROOT / ".mcp.json").read_text())
    assert "go" in data
    server = data["go"]
    assert server["command"] == "python3"
    assert any("${CLAUDE_PLUGIN_ROOT}" in arg for arg in server["args"])
    assert "mcp-server/server.py" in server["args"][-1]


def test_package_json_peer_dep_and_postinstall():
    data = json.loads((REPO_ROOT / "package.json").read_text())
    assert data["name"] == "prd-taskmaster"
    assert data["version"] == _package_version()
    assert data["peerDependencies"]["task-master-ai"].startswith(">=")
    assert "postinstall" in data["scripts"]
    assert "pip install" in data["scripts"]["postinstall"]
    assert "test" in data["scripts"]


def test_templates_and_reference_present():
    assert (REPO_ROOT / "templates" / "taskmaster-prd-comprehensive.md").exists()
    assert (REPO_ROOT / "templates" / "taskmaster-prd-minimal.md").exists()
    assert (REPO_ROOT / "reference" / "validation-checklist.md").exists()
    assert (REPO_ROOT / "reference" / "taskmaster-integration-guide.md").exists()
