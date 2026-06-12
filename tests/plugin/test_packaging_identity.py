import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_taskmaster_peer_dependency_is_optional_not_hard_dependency():
    data = json.loads((REPO_ROOT / "package.json").read_text())

    assert data["peerDependencies"]["task-master-ai"].startswith(">=")
    assert data["peerDependenciesMeta"]["task-master-ai"] == {"optional": True}
    assert "task-master-ai" not in data.get("dependencies", {})


def test_installer_offers_taskmaster_backend_without_requiring_it():
    content = (REPO_ROOT / "install.sh").read_text()

    assert "--with-taskmaster" in content
    assert "--no-taskmaster" in content
    assert "unlocks the TaskMaster backend" in content
    assert "non-interactive" in content.lower()

    install_cmd = "npm install -g task-master-ai"
    assert content.count(install_cmd) == 1
    offer_start = content.index("install_taskmaster_backend()")
    install_skill_start = content.index("install_skill()")
    assert offer_start < content.index(install_cmd) < install_skill_start


def test_readme_marks_taskmaster_install_optional():
    content = (REPO_ROOT / "README.md").read_text()

    assert "optional — unlocks the TaskMaster backend" in content


def test_readme_leads_with_structural_moats_before_taskmaster_funnel():
    content = (REPO_ROOT / "README.md").read_text()

    markers = [
        "cross-vendor fleet",
        "validate-tasks",
        "persistent vendor-neutral `tasks.json`",
        "token-economy cost ledger",
        "speaks TaskMaster natively",
    ]
    positions = [content.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_product_spec_marks_backend_abstraction_shipped_v41():
    content = (REPO_ROOT / "docs" / "product" / "PRODUCT-SPEC.md").read_text()

    assert "FR-33 [FREE, SHIPPED v4.1]" in content
    assert "auto|taskmaster|native" in content
    assert "detect/init/parse_prd/expand/rate" in content
    assert "agent_action_required" in content
