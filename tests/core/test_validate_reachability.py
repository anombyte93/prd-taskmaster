"""Tests for tier-gated reachableVia + promise>evidence detector + warnings channel.

All tests call run_validate_tasks() directly or _promise_evidence_mismatch() directly.
No subprocess, no mocking of the load-bearing checks.
"""

from __future__ import annotations

import json
import pytest

from prd_taskmaster.lib import CommandError
from prd_taskmaster.validation import run_validate_tasks, _promise_evidence_mismatch


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_task(
    task_id: int = 1,
    title: str = "Implement feature X",
    description: str = "A concrete feature.",
    details: str = "Implementation details here.",
    test_strategy: str = "Run pytest tests/core/ -q",
    tier: str | None = None,
    reachable_via: str | None = None,
    phase_config: dict | None = None,
    priority: str = "medium",
    status: str = "pending",
) -> dict:
    """Build a minimal valid task dict with optional tier/reachableVia overrides."""
    task: dict = {
        "id": task_id,
        "title": title,
        "description": description,
        "details": details,
        "testStrategy": test_strategy,
        "priority": priority,
        "status": status,
        "dependencies": [],
        "subtasks": [
            {"id": 1, "title": "First checkpoint", "description": "First step", "status": "pending", "dependencies": []},
            {"id": 2, "title": "Second checkpoint", "description": "Second step", "status": "pending", "dependencies": [1]},
        ],
    }
    if tier is not None:
        task["tier"] = tier
    if reachable_via is not None:
        task["reachableVia"] = reachable_via
    if phase_config is not None:
        task["phaseConfig"] = phase_config
    return task


def _write_tasks_file(tmp_path, tasks: list[dict]) -> str:
    """Write a flat tasks.json to tmp_path and return the path string."""
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps({"tasks": tasks}))
    return str(tasks_file)


# ─── 1. wired-tier task with empty reachableVia → hard-block ─────────────────


class TestReachableViaHardBlock:
    def test_wired_empty_reachable_via_raises(self, tmp_path):
        """wired-tier task with no reachableVia must raise CommandError (hard-block)."""
        task = _make_task(tier="wired", reachable_via=None)
        path = _write_tasks_file(tmp_path, [task])
        with pytest.raises(CommandError) as exc_info:
            run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        err = exc_info.value
        assert "reachableVia" in " ".join(str(p) for p in err.extra.get("problems", []))

    def test_live_empty_reachable_via_raises(self, tmp_path):
        """live-tier task with no reachableVia must also raise CommandError."""
        task = _make_task(tier="live", reachable_via=None)
        path = _write_tasks_file(tmp_path, [task])
        with pytest.raises(CommandError) as exc_info:
            run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        err = exc_info.value
        problems_text = " ".join(str(p) for p in err.extra.get("problems", []))
        assert "reachableVia" in problems_text
        assert "tier=live" in problems_text

    def test_wired_with_reachable_via_passes(self, tmp_path):
        """wired-tier task with a populated reachableVia must NOT raise."""
        task = _make_task(tier="wired", reachable_via="route:/api/v1/orders")
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True


# ─── 2. domain-model/untiered task with empty reachableVia → warning only ────


class TestReachableViaWarningsOnly:
    def test_domain_model_empty_reachable_via_does_not_raise(self, tmp_path):
        """domain-model task with empty reachableVia must not raise — just warn."""
        task = _make_task(tier="domain-model", reachable_via=None)
        path = _write_tasks_file(tmp_path, [task])
        # Must NOT raise
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True

    def test_domain_model_empty_reachable_via_produces_warning(self, tmp_path):
        """domain-model + empty reachableVia must appear in warnings."""
        task = _make_task(tier="domain-model", reachable_via=None)
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert "warnings" in result
        assert any("reachableVia" in w for w in result["warnings"])

    def test_untiered_task_defaults_to_domain_model(self, tmp_path):
        """Task with no tier field defaults to domain-model → warning, no raise."""
        task = _make_task(tier=None)  # no tier field in dict
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        # Warning is expected (defaults to domain-model)
        assert "warnings" in result


# ─── 3. Promise-evidence mismatch: wired → hard-block ────────────────────────


class TestPromiseEvidenceMismatchHardBlock:
    def test_wired_prisma_connector_fixture_only_raises(self, tmp_path):
        """wired-tier task titled 'Prisma connector for orders' with fixture-only test → hard-block."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/orders",
            title="Prisma connector for orders",
            description="Persist order data via Prisma ORM.",
            test_strategy="unit test parses a fixture file",
        )
        path = _write_tasks_file(tmp_path, [task])
        with pytest.raises(CommandError) as exc_info:
            run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        err = exc_info.value
        problems_text = " ".join(str(p) for p in err.extra.get("problems", []))
        # Must mention the claim term or the fixture-only signal
        assert "fixture-only" in problems_text or "connector" in problems_text or "prisma" in problems_text.lower()

    def test_promise_evidence_mismatch_direct_suggested_title(self, tmp_path):
        """_promise_evidence_mismatch returns suggested_title containing 'file adapter' for Prisma."""
        task = _make_task(
            title="Prisma connector for orders",
            description="Persist order data.",
            test_strategy="unit test parses a fixture",
        )
        result = _promise_evidence_mismatch(task)
        assert result is not None
        assert result["evidence_altitude"] == "fixture-only"
        assert "file adapter" in result["suggested_title"].lower()

    def test_promise_evidence_mismatch_client_suggested_title(self):
        """_promise_evidence_mismatch: 'client' claim → 'parser' in suggested_title."""
        task = _make_task(
            title="HTTP client for external API",
            description="Fetch data from vendor.",
            test_strategy="unit test parses sample fixture",
        )
        result = _promise_evidence_mismatch(task)
        assert result is not None
        assert "parser" in result["suggested_title"].lower()


# ─── 4. Promise-evidence mismatch: domain-model → warning, no raise ──────────


class TestPromiseEvidenceMismatchWarningOnly:
    def test_domain_model_mismatch_does_not_raise(self, tmp_path):
        """domain-model task with claim/fixture mismatch must NOT raise."""
        task = _make_task(
            tier="domain-model",
            title="Prisma connector for orders",
            description="Persist order data.",
            test_strategy="unit test parses a fixture",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True

    def test_domain_model_mismatch_appears_in_warnings(self, tmp_path):
        """domain-model mismatch appears in warnings (not problems)."""
        task = _make_task(
            tier="domain-model",
            title="Prisma connector for orders",
            description="Persist order data.",
            test_strategy="unit test parses a fixture",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        warnings = result.get("warnings", [])
        # At least one warning mentioning the mismatch
        mismatch_warnings = [w for w in warnings if "fixture-only" in w or "connector" in w or "prisma" in w.lower()]
        assert mismatch_warnings, f"Expected mismatch warning in warnings; got: {warnings}"

    def test_domain_model_mismatch_suggested_title_in_warning(self, tmp_path):
        """domain-model mismatch warning must include suggested_title."""
        task = _make_task(
            tier="domain-model",
            title="Prisma connector for orders",
            description="Persist order data.",
            test_strategy="unit test parses a fixture",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        warnings = result.get("warnings", [])
        # Suggested title "file adapter" must appear in the warning text
        assert any("file adapter" in w.lower() for w in warnings), (
            f"Expected 'file adapter' in warning text; got: {warnings}"
        )


# ─── 5. Live test strategy → no flag ─────────────────────────────────────────


class TestLiveTestStrategyNoFlag:
    def test_wired_integration_test_no_flag(self, tmp_path):
        """wired task with integration-test testStrategy → NO promise-evidence flag."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/orders",
            title="API connector for orders endpoint",
            description="Wire the orders REST integration.",
            test_strategy="integration test hits the /orders endpoint via http request",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        # No mismatch warning should appear
        warnings = result.get("warnings", [])
        mismatch_warnings = [w for w in warnings if "fixture-only" in w]
        assert not mismatch_warnings, f"Unexpected mismatch warning: {mismatch_warnings}"

    def test_promise_evidence_mismatch_returns_none_for_live_strategy(self):
        """_promise_evidence_mismatch returns None when testStrategy has live signal."""
        task = _make_task(
            title="Prisma connector for orders",
            description="Persist order data.",
            test_strategy="run integration test against real postgres connection",
        )
        result = _promise_evidence_mismatch(task)
        assert result is None


# ─── 6. run_validate_tasks returns 'warnings' key on success ─────────────────


class TestWarningsKeyOnSuccess:
    def test_success_result_has_warnings_key(self, tmp_path):
        """run_validate_tasks always returns a 'warnings' list on success."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/x",
            title="Clean task",
            description="No suspicious claims.",
            test_strategy="run pytest tests/ -q",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    def test_clean_task_has_empty_warnings(self, tmp_path):
        """A fully clean wired task with live test → warnings list is empty."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/x",
            title="Add order endpoint handler",
            description="Handle POST /orders via REST.",
            test_strategy="integration test hits the /orders endpoint via http",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["warnings"] == []


# ─── 7. domain-model mismatch in warnings not problems ───────────────────────


class TestDomainModelMismatchInWarningsOnly:
    def test_domain_model_mismatch_not_in_problems(self, tmp_path):
        """domain-model mismatch must go to warnings, never to problems."""
        task = _make_task(
            tier="domain-model",
            title="Prisma connector for orders",
            description="Pure domain logic.",
            test_strategy="unit test parses a fixture",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        assert "warnings" in result
        # The warning should mention fixture-only or the claim term
        warnings = result["warnings"]
        assert any("fixture-only" in w or "connector" in w or "prisma" in w.lower() for w in warnings)


# ─── 8. Anchoring: client substring does NOT trigger hard-block ──────────────


class TestClientSubstringAnchoring:
    def test_client_side_warns_not_blocks(self, tmp_path):
        """'client-side' matches \\bclient\\b (hyphen is a word boundary), but 'client'
        is now a soft/ambiguous term — it produces an advisory warning, never a hard-block
        even for wired/live tasks."""
        task = _make_task(
            tier="wired",
            reachable_via="component.HydrationLayer",
            title="client-side hydration layer",
            description="Pure client-side rendering with React.",
            test_strategy="write unit tests for component props",
        )
        path = _write_tasks_file(tmp_path, [task])
        # Must NOT raise — client is soft/warn-only
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        # But a warning should be present
        warnings = result.get("warnings", [])
        assert any("client" in w.lower() for w in warnings), (
            f"Expected advisory warning mentioning 'client'; got: {warnings}"
        )

    def test_api_substring_does_not_match_rapid(self):
        """'rapid' should NOT trigger the \\bapi\\b pattern."""
        task = _make_task(
            title="Rapid prototyping for UI layer",
            description="Quick iteration cycle.",
            test_strategy="unit test parses a fixture",
        )
        result = _promise_evidence_mismatch(task)
        # If a mismatch fires, it should NOT be for 'api' (rapid does not contain \bapi\b)
        if result is not None:
            assert result["claim_term"].lower() != "api", (
                f"'rapid' should not match \\bapi\\b, but got claim_term={result['claim_term']!r}"
            )

    def test_api_standalone_word_does_trigger(self):
        """Title containing 'integration' (a hard term) plus 'API' and 'client' (soft
        terms) still triggers a mismatch because hard terms are checked first.
        'integration' is precise/hard so it fires as the matched term."""
        task = _make_task(
            title="API client for vendor integration",
            description="Fetch from vendor API.",
            test_strategy="unit test parses a sample fixture file",
        )
        result = _promise_evidence_mismatch(task)
        assert result is not None
        # 'integration' is the first hard term to match; api/client are soft (checked after hard)
        assert result["claim_term"].lower() in {"integration", "api", "client"}
        # The result must not be soft — 'integration' is a hard claim term
        assert not result.get("soft"), "Expected hard mismatch (integration is a precise term)"

    def test_cli_does_not_match_client(self):
        """'client' should not trigger the \\bcli\\b pattern."""
        task = _make_task(
            title="HTTP client wrapper",
            description="Wrap HTTP calls.",
            test_strategy="unit test parses a fixture",
        )
        result = _promise_evidence_mismatch(task)
        if result is not None:
            # It might match 'client' but must NOT report 'cli' as the matched term
            # (because 'client' does not match \bcli\b — 'client' has extra chars after 'cli')
            # Actually \bcli\b won't match inside 'client' because 'e' follows 'i'
            # \b is at word boundary: cli-ent, 'i'→'e' are both word chars, so no boundary
            assert result["claim_term"].lower() != "cli", (
                f"'client' should not match \\bcli\\b, but got claim_term={result['claim_term']!r}"
            )


# ─── 9. Hand-authored vs AI-authored: checks fire regardless ─────────────────


class TestHandAuthoredCoverage:
    def test_hand_authored_task_triggers_reachability_check(self, tmp_path):
        """Hand-crafted wired task without reachableVia must still hard-block."""
        # This simulates a task authored manually (not by AI)
        raw_task = {
            "id": 1,
            "title": "Hand-built route handler",
            "description": "Manually written task.",
            "details": "This was written by a human developer.",
            "testStrategy": "pytest tests/test_handler.py",
            "priority": "high",
            "status": "pending",
            "tier": "wired",
            "dependencies": [],
            "subtasks": [
                {"id": 1, "title": "First", "description": "Step one", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Second", "description": "Step two", "status": "pending", "dependencies": [1]},
            ],
            # No reachableVia — intentionally omitted
        }
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [raw_task]}))
        with pytest.raises(CommandError) as exc_info:
            run_validate_tasks(str(tasks_file), allow_empty_subtasks=True, require_phase_config=False)
        assert "reachableVia" in " ".join(str(p) for p in exc_info.value.extra.get("problems", []))

    def test_hand_authored_domain_model_no_hard_block(self, tmp_path):
        """Hand-crafted domain-model task without reachableVia → warn, not hard-block."""
        raw_task = {
            "id": 1,
            "title": "Domain model for orders",
            "description": "Pure business logic.",
            "details": "No integration needed.",
            "testStrategy": "pytest tests/ -q",
            "priority": "low",
            "status": "pending",
            "tier": "domain-model",
            "dependencies": [],
            "subtasks": [
                {"id": 1, "title": "Model class", "description": "Define model", "status": "pending", "dependencies": []},
                {"id": 2, "title": "Validators", "description": "Add validators", "status": "pending", "dependencies": [1]},
            ],
        }
        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps({"tasks": [raw_task]}))
        result = run_validate_tasks(str(tasks_file), allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        assert "warnings" in result


# ─── 10. Unscoped reachableVia → advisory warning ────────────────────────────


class TestUnscopedReachableVia:
    def test_bare_word_reachable_via_warns(self, tmp_path):
        """reachableVia with no colon, slash, dot, or dash → advisory warning."""
        task = _make_task(
            tier="wired",
            reachable_via="ordersroute",  # no scope marker
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        warnings = result.get("warnings", [])
        assert any("unscoped" in w or "ordersroute" in w for w in warnings)

    def test_scoped_reachable_via_no_warning(self, tmp_path):
        """reachableVia with a colon (e.g. 'route:/x') → no unscoped warning."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/orders",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        warnings = result.get("warnings", [])
        unscoped_warnings = [w for w in warnings if "unscoped" in w]
        assert not unscoped_warnings


# ─── 11. Spike tier follows soft rules ───────────────────────────────────────


class TestSpikeTierSoftRules:
    def test_spike_empty_reachable_via_warns_not_blocks(self, tmp_path):
        """spike-tier task with empty reachableVia → warning, not hard-block."""
        task = _make_task(tier="spike", reachable_via=None)
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        warnings = result.get("warnings", [])
        assert any("reachableVia" in w for w in warnings)

    def test_spike_mismatch_warns_not_blocks(self, tmp_path):
        """spike-tier task with promise-evidence mismatch → warning, not hard-block."""
        task = _make_task(
            tier="spike",
            title="Prisma connector spike",
            description="Research Prisma integration.",
            test_strategy="unit test parses a fixture",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True
        warnings = result.get("warnings", [])
        # There should be a mismatch warning
        assert any("fixture-only" in w or "connector" in w or "prisma" in w.lower() for w in warnings)


# ─── 12. Soft claim terms: no false hard-block on wired/live ──────────────────


class TestSoftClaimTermsNoFalseHardBlock:
    """Ambiguous claim terms (store/route/sync/client/api) must NEVER hard-block
    wired or live tasks — only produce advisory warnings."""

    def test_wired_redux_store_unit_tests_warns_not_blocks(self, tmp_path):
        """wired 'Redux store' + 'write unit tests' → ok:True, warning present."""
        task = _make_task(
            tier="wired",
            reachable_via="component.ReduxStore",
            title="Redux store for cart state",
            description="Manage cart state with Redux.",
            test_strategy="write unit tests for reducers",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True, (
            "wired 'Redux store' with unit tests should not hard-block — 'store' is a soft term"
        )
        warnings = result.get("warnings", [])
        assert any("store" in w.lower() or "fixture-only" in w for w in warnings), (
            f"Expected advisory warning for 'store'; got: {warnings}"
        )

    def test_wired_api_route_handler_unit_tests_warns_not_blocks(self, tmp_path):
        """wired 'API route handler' + 'write unit tests' → ok:True, warning present."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/orders",
            title="API route handler for orders",
            description="Handle order requests via the API route.",
            test_strategy="write unit tests for the handler function",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True, (
            "wired 'API route handler' with unit tests should not hard-block — 'api'/'route' are soft terms"
        )
        warnings = result.get("warnings", [])
        assert any("api" in w.lower() or "route" in w.lower() or "fixture-only" in w for w in warnings), (
            f"Expected advisory warning for 'api'/'route'; got: {warnings}"
        )

    def test_wired_client_side_hydration_unit_tests_warns_not_blocks(self, tmp_path):
        """wired 'client-side hydration' + 'unit tests' → ok:True, warning present."""
        task = _make_task(
            tier="wired",
            reachable_via="component.HydrationShell",
            title="client-side hydration shell",
            description="Implement React client-side hydration for SSR pages.",
            test_strategy="unit tests for hydration props",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True, (
            "wired 'client-side hydration' with unit tests should not hard-block — 'client' is a soft term"
        )
        warnings = result.get("warnings", [])
        assert any("client" in w.lower() or "fixture-only" in w for w in warnings), (
            f"Expected advisory warning for 'client'; got: {warnings}"
        )

    def test_wired_sync_props_unit_tests_warns_not_blocks(self, tmp_path):
        """wired 'sync props/state' + 'write unit tests' → ok:True, warning present."""
        task = _make_task(
            tier="wired",
            reachable_via="component.SyncedPanel",
            title="Sync props between parent and child components",
            description="Use useEffect to sync state props in React.",
            test_strategy="write unit tests for the sync hook",
        )
        path = _write_tasks_file(tmp_path, [task])
        result = run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        assert result["ok"] is True, (
            "wired 'sync props' with unit tests should not hard-block — 'sync' is a soft term"
        )
        warnings = result.get("warnings", [])
        assert any("sync" in w.lower() or "fixture-only" in w for w in warnings), (
            f"Expected advisory warning for 'sync'; got: {warnings}"
        )

    def test_soft_term_mismatch_is_marked_soft(self):
        """_promise_evidence_mismatch sets soft=True for ambiguous claim terms."""
        task = _make_task(
            title="Redux store reducer",
            description="Manage UI state store.",
            test_strategy="unit tests for reducer pure functions",
        )
        result = _promise_evidence_mismatch(task)
        assert result is not None
        assert result.get("soft") is True, (
            f"Expected soft=True for 'store' claim term; got: {result}"
        )

    def test_hard_term_mismatch_is_not_soft(self):
        """_promise_evidence_mismatch sets soft=False for precise claim terms."""
        task = _make_task(
            title="Prisma connector for orders",
            description="Persist data via Prisma ORM.",
            test_strategy="unit test parses a fixture",
        )
        result = _promise_evidence_mismatch(task)
        assert result is not None
        assert result.get("soft") is False, (
            f"Expected soft=False for 'prisma'/'connector' claim term; got: {result}"
        )


# ─── 13. Precise terms still hard-block wired/live ───────────────────────────


class TestPreciseTermsStillHardBlock:
    """Precise/unambiguous terms (prisma, webhook, connector, endpoint, etc.)
    must continue to hard-block wired/live tasks."""

    def test_wired_webhook_integration_fixture_only_raises(self, tmp_path):
        """wired 'webhook integration' + fixture-only test → hard-block."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/webhooks/stripe",
            title="webhook integration for Stripe events",
            description="Handle Stripe webhook payloads.",
            test_strategy="unit test parses a fixture payload",
        )
        path = _write_tasks_file(tmp_path, [task])
        with pytest.raises(CommandError) as exc_info:
            run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        err = exc_info.value
        problems_text = " ".join(str(p) for p in err.extra.get("problems", []))
        assert "fixture-only" in problems_text or "webhook" in problems_text, (
            f"Expected 'webhook' or 'fixture-only' in problems; got: {problems_text}"
        )

    def test_wired_prisma_connector_fixture_still_hard_blocks(self, tmp_path):
        """wired 'Prisma connector' + fixture-only test → hard-block (unchanged)."""
        task = _make_task(
            tier="wired",
            reachable_via="route:/api/v1/orders",
            title="Prisma connector for order persistence",
            description="Persist orders to the database via Prisma.",
            test_strategy="unit test parses a fixture file",
        )
        path = _write_tasks_file(tmp_path, [task])
        with pytest.raises(CommandError):
            run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)

    def test_wired_database_migration_fixture_still_hard_blocks(self, tmp_path):
        """wired 'database migration' + fixture-only test → hard-block."""
        task = _make_task(
            tier="wired",
            reachable_via="cli:migrate",
            title="database migration for user schema",
            description="Add migration to update the users table.",
            test_strategy="unit tests parse fixture SQL",
        )
        path = _write_tasks_file(tmp_path, [task])
        with pytest.raises(CommandError) as exc_info:
            run_validate_tasks(path, allow_empty_subtasks=True, require_phase_config=False)
        err = exc_info.value
        problems_text = " ".join(str(p) for p in err.extra.get("problems", []))
        assert "fixture-only" in problems_text or "database" in problems_text or "migration" in problems_text
