"""README telemetry disclosure accuracy tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_readme_telemetry_section_is_complete_and_positioned():
    readme = (ROOT / "README.md").read_text()

    quickstart = readme.index("## Quickstart")
    telemetry = readme.index("## Telemetry")
    faq = readme.index("## FAQ")

    assert quickstart < telemetry < faq
    for field in ("install_id", "event", "version", "os"):
        assert field in readme
    for event_name in ("install", "atlas_invoked", "reach_execute", "ship_check_ok"):
        assert event_name in readme
    for opt_out in ("ATLAS_TELEMETRY=0", "config.json", "--no-telemetry"):
        assert opt_out in readme
    for forbidden in ("PII", "goal text", "code", "paths"):
        assert forbidden in readme
