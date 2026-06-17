"""Tests for deterministic tier classification (altitude field).

Tier ∈ {spike, domain-model, wired, live}.
- spike        = research / investigation
- domain-model = pure logic (safe default; no reachability required)
- wired        = integration / API / CLI work (reachability required later)
- live         = user-visible / validation (reachability required later)
"""

import json

import pytest

from prd_taskmaster.tasks import _classify_tier, run_enrich_tasks
from prd_taskmaster.backend import TASKS_SCHEMA_HINT


# ─── _classify_tier unit tests ────────────────────────────────────────────────


class TestClassifyTier:
    """Unit tests for the _classify_tier helper."""

    # spike ───────────────────────────────────────────────────────────────────

    def test_research_keyword_in_title_gives_spike(self):
        task = {"title": "Research the best auth framework", "description": ""}
        assert _classify_tier(task) == "spike"

    def test_investigate_keyword_gives_spike(self):
        task = {"title": "Investigate memory leak in parser", "description": ""}
        assert _classify_tier(task) == "spike"

    def test_spike_keyword_gives_spike(self):
        task = {"title": "Spike: evaluate caching strategies", "description": ""}
        assert _classify_tier(task) == "spike"

    def test_evaluate_keyword_in_description_gives_spike(self):
        task = {"title": "Auth options", "description": "Evaluate OAuth vs SAML trade-offs"}
        assert _classify_tier(task) == "spike"

    def test_poc_keyword_gives_spike(self):
        task = {"title": "PoC for streaming responses", "description": ""}
        assert _classify_tier(task) == "spike"

    # live ────────────────────────────────────────────────────────────────────

    def test_user_test_in_combined_gives_live(self):
        task = {"title": "End-to-end user-test pass", "description": ""}
        assert _classify_tier(task) == "live"

    def test_user_validation_checkpoint_in_title_gives_live(self):
        task = {"title": "User Validation Checkpoint: checkout flow", "description": ""}
        assert _classify_tier(task) == "live"

    def test_user_test_in_description_gives_live(self):
        task = {"title": "QA sign-off", "description": "Perform full user-test of the onboarding flow"}
        assert _classify_tier(task) == "live"

    # live takes priority over research keywords
    def test_live_beats_research_when_both_present(self):
        task = {
            "title": "User Validation Checkpoint",
            "description": "Evaluate and review the user flow",
        }
        assert _classify_tier(task) == "live"

    # wired ───────────────────────────────────────────────────────────────────

    def test_wire_keyword_gives_wired(self):
        task = {"title": "Wire authentication into the billing module", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_api_endpoint_gives_wired(self):
        task = {"title": "Add /api/v1/users endpoint", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_connect_to_database_gives_wired(self):
        task = {"title": "Connect the service to the database", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_integration_keyword_gives_wired(self):
        task = {"title": "Integrate Stripe payment gateway", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_webhook_gives_wired(self):
        task = {"title": "Handle incoming webhook from GitHub", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_deploy_gives_wired(self):
        task = {"title": "Deploy service to production", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_mcp_keyword_gives_wired(self):
        task = {"title": "Register new MCP tool in the router", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_cli_keyword_gives_wired(self):
        task = {"title": "Add CLI subcommand for enrich-tasks", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_migration_keyword_gives_wired(self):
        task = {"title": "Write migration for tasks schema", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_route_keyword_gives_wired(self):
        task = {"title": "Add route for user profile page", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_pipeline_keyword_gives_wired(self):
        task = {"title": "Build CI pipeline for staging", "description": ""}
        assert _classify_tier(task) == "wired"

    # domain-model ────────────────────────────────────────────────────────────

    def test_plain_logic_task_gives_domain_model(self):
        task = {"title": "Implement the scoring function", "description": "Pure Python calculation."}
        assert _classify_tier(task) == "domain-model"

    def test_empty_task_gives_domain_model(self):
        task = {}
        assert _classify_tier(task) == "domain-model"

    def test_generic_task_gives_domain_model(self):
        task = {"title": "Add unit tests for the parser", "description": ""}
        assert _classify_tier(task) == "domain-model"

    def test_name_field_used_as_fallback_for_title(self):
        task = {"name": "Implement token counter", "description": ""}
        assert _classify_tier(task) == "domain-model"

    # ── Negative regression tests: keyword over-matching ─────────────────────
    # Each of these MUST classify as domain-model, not wired or spike.
    # They fail against the pre-fix regexes (cli/auth/wire stem collisions,
    # review/assess in _TIER_RESEARCH_RE).

    def test_client_side_does_not_give_wired(self):
        """'client' must not match the 'cli' wired stem."""
        task = {"title": "Build a client-side validation rules module", "description": ""}
        assert _classify_tier(task) == "domain-model"

    def test_client_validation_does_not_give_wired(self):
        """'client' (standalone) must not match the 'cli' wired stem."""
        task = {"title": "Client validation module", "description": ""}
        assert _classify_tier(task) == "domain-model"

    def test_wireframe_does_not_give_wired(self):
        """'wireframe' must not match the 'wire' wired stem."""
        task = {"title": "Create wireframes for the dashboard", "description": ""}
        assert _classify_tier(task) == "domain-model"

    def test_author_does_not_give_wired(self):
        """'author' must not match the 'auth' wired stem."""
        task = {"title": "Author bio component", "description": ""}
        assert _classify_tier(task) == "domain-model"

    def test_authority_does_not_give_wired(self):
        """'authority' must not match the 'auth' wired stem."""
        task = {"title": "Model the authority hierarchy", "description": ""}
        assert _classify_tier(task) == "domain-model"

    def test_code_review_does_not_give_spike(self):
        """'review' in a task title must not trigger the spike tier."""
        task = {"title": "Code review the scoring PR", "description": ""}
        assert _classify_tier(task) != "spike"

    def test_assess_alone_does_not_give_spike(self):
        """'assess' alone must not trigger the spike tier (dropped from _TIER_RESEARCH_RE)."""
        task = {"title": "Assess the risk level of the change", "description": ""}
        assert _classify_tier(task) != "spike"

    # Confirm genuine wired / spike cases still classify correctly (no over-correction)

    def test_wire_scorer_into_cli_still_gives_wired(self):
        """'Wire … CLI' — both 'wire' and 'cli' must still match as wired."""
        task = {"title": "Wire the scorer into the CLI", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_cli_entrypoint_still_gives_wired(self):
        """'cli' as a bare token (not followed by ent/mat/nic) must still match."""
        task = {"title": "Set up the cli entrypoint", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_authenticate_via_oauth_still_gives_wired(self):
        """'authenticate' must still match as a wired integration signal."""
        task = {"title": "Authenticate users via OAuth", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_auth_token_still_gives_wired(self):
        """'\bauth\b' (bare word) must still fire as wired."""
        task = {"title": "Rotate the auth token on each request", "description": ""}
        assert _classify_tier(task) == "wired"

    def test_investigate_still_gives_spike(self):
        """'investigate' must remain a spike trigger despite 'review'/'assess' removal."""
        task = {"title": "Investigate caching options for the feed", "description": ""}
        assert _classify_tier(task) == "spike"

    # wired beats domain-model when integration keyword appears in details
    def test_integration_signal_in_details_gives_wired(self):
        task = {
            "title": "Implement task storage",
            "description": "Store tasks.",
            "details": "Must connect to the database via SQLAlchemy.",
        }
        assert _classify_tier(task) == "wired"

    # research notes appended by parallel pass should NOT influence tier
    def test_research_notes_section_ignored_for_tier(self):
        task = {
            "title": "Implement scoring function",
            "description": "Pure calculation.",
            "details": (
                "Standard implementation.\n"
                "RESEARCH NOTES (parallel pass):\n"
                "Integrate with the API endpoint via database migration."
            ),
        }
        # The wired keywords appear only in the stripped RESEARCH NOTES section
        assert _classify_tier(task) == "domain-model"


# ─── run_enrich_tasks integration tests ──────────────────────────────────────


class TestEnrichTasksTier:
    """Integration tests for tier injection via run_enrich_tasks."""

    def _make_tasks_file(self, tmp_path, tasks: list) -> str:
        p = tmp_path / "tasks.json"
        p.write_text(json.dumps({"tasks": tasks}))
        return str(p)

    def _read_tasks(self, path: str) -> list:
        return json.loads(open(path).read())["tasks"]

    def test_enrich_sets_tier_for_every_task(self, tmp_path):
        tasks = [
            {"id": 1, "title": "Research auth options", "description": "", "subtasks": []},
            {"id": 2, "title": "Implement scoring function", "description": "", "subtasks": []},
            {"id": 3, "title": "Wire the API endpoint", "description": "", "subtasks": []},
        ]
        path = self._make_tasks_file(tmp_path, tasks)
        result = run_enrich_tasks(path)
        assert result["ok"] is True

        written = self._read_tasks(path)
        for task in written:
            assert "phaseConfig" in task
            assert "tier" in task["phaseConfig"], f"missing tier on task {task.get('id')}"

    def test_enrich_tier_matches_classifier_per_task(self, tmp_path):
        tasks = [
            {"id": 1, "title": "Research auth options", "description": "", "subtasks": []},
            {"id": 2, "title": "Implement scoring function", "description": "", "subtasks": []},
            {"id": 3, "title": "Wire the API endpoint", "description": "", "subtasks": []},
            {"id": 4, "title": "User Validation Checkpoint", "description": "", "subtasks": []},
        ]
        path = self._make_tasks_file(tmp_path, tasks)
        run_enrich_tasks(path)
        written = self._read_tasks(path)

        by_id = {t["id"]: t for t in written}
        assert by_id[1]["phaseConfig"]["tier"] == "spike"
        assert by_id[2]["phaseConfig"]["tier"] == "domain-model"
        assert by_id[3]["phaseConfig"]["tier"] == "wired"
        assert by_id[4]["phaseConfig"]["tier"] == "live"

    def test_enrich_is_idempotent_same_tiers_on_second_run(self, tmp_path):
        tasks = [
            {"id": 1, "title": "Research auth options", "description": "", "subtasks": []},
            {"id": 2, "title": "Wire the API endpoint", "description": "", "subtasks": []},
        ]
        path = self._make_tasks_file(tmp_path, tasks)
        run_enrich_tasks(path)
        tiers_after_first = {
            t["id"]: t["phaseConfig"]["tier"]
            for t in self._read_tasks(path)
        }

        run_enrich_tasks(path)
        tiers_after_second = {
            t["id"]: t["phaseConfig"]["tier"]
            for t in self._read_tasks(path)
        }

        assert tiers_after_first == tiers_after_second

    def test_plain_task_defaults_to_domain_model(self, tmp_path):
        tasks = [{"id": 1, "title": "Implement the parser", "description": "", "subtasks": []}]
        path = self._make_tasks_file(tmp_path, tasks)
        run_enrich_tasks(path)
        written = self._read_tasks(path)
        assert written[0]["phaseConfig"]["tier"] == "domain-model"

    def test_pre_existing_phaseconfig_without_tier_gets_backfilled(self, tmp_path):
        """Tasks enriched before the tier feature get tier added on re-run."""
        tasks = [
            {
                "id": 1,
                "title": "Wire auth to billing",
                "description": "",
                "subtasks": [],
                "phaseConfig": {
                    "complexity": "COMPLEX",
                    "requiresCDD": True,
                    "requiresResearch": True,
                    "lifecycle": ["planning", "implementation", "testing", "review"],
                    "cddCardId": None,
                    "acceptanceCriteria": [],
                    # no "tier" key — simulates pre-feature enrichment
                },
            }
        ]
        path = self._make_tasks_file(tmp_path, tasks)
        result = run_enrich_tasks(path)
        assert result["ok"] is True
        written = self._read_tasks(path)
        assert written[0]["phaseConfig"]["tier"] == "wired"

    def test_pre_existing_explicit_tier_not_overwritten(self, tmp_path):
        """An already-present non-empty tier is preserved (honours LLM or manual value)."""
        tasks = [
            {
                "id": 1,
                "title": "Wire auth to billing",
                "description": "",
                "subtasks": [],
                "phaseConfig": {
                    "complexity": "COMPLEX",
                    "tier": "live",  # explicitly set (e.g. by LLM)
                    "requiresCDD": True,
                    "requiresResearch": True,
                    "lifecycle": [],
                    "cddCardId": None,
                    "acceptanceCriteria": [],
                },
            }
        ]
        path = self._make_tasks_file(tmp_path, tasks)
        run_enrich_tasks(path)
        written = self._read_tasks(path)
        # "live" is kept even though the keywords would normally give "wired"
        assert written[0]["phaseConfig"]["tier"] == "live"


# ─── Schema hint test ─────────────────────────────────────────────────────────


def test_tasks_schema_hint_contains_tier():
    assert '"tier"' in TASKS_SCHEMA_HINT or "'tier'" in TASKS_SCHEMA_HINT
    # Also confirm the four valid values are documented
    assert "domain-model" in TASKS_SCHEMA_HINT
