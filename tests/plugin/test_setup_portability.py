from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_skills_do_not_reference_developer_machine_paths():
    offenders = []
    for path in (REPO_ROOT / "skills").glob("*/SKILL.md"):
        text = path.read_text()
        for forbidden in ("/Shade_Gen/", "$HOME/Shade_Gen"):
            if forbidden in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {forbidden}")

    assert offenders == []


def test_setup_bootstrap_uses_installed_skill_relative_skel():
    text = (REPO_ROOT / "skills" / "setup" / "SKILL.md").read_text()

    assert "$SKILL_DIR/../../skel" in text
    assert ".atlas-ai/customizations/system-prompt-template.md" in text
    assert ": > .atlas-ai/customizations/system-prompt-template.md" in text
