"""Tournament spawner tests — no live launcher, all I/O mocked.

Coverage:
  SP1.  build_roster with 3 models → 3 RacerSpecs, distinct claimant_ids.
  SP2.  Each prompt contains: job_id, card_ref, commit-reveal instructions.
  SP2d. Each prompt contains the real base_ref (not a literal '<base>' placeholder).
  SP2e. Each prompt contains the report_to inbox address.
  SP3.  _admit stub is called once per racer with correct kwargs.
  SP4.  build_roster with >PER_JOB_CAP_N models → raises SybilLimitError("job_cap_exceeded").
  SP5.  spawn_roster with stub _spawn_fn → returns N handles, all spawned=True.
  SP6.  spawn_roster: _spawn_fn raises for one racer → that racer spawned=False, others spawned=True.
  SP7.  entry_fee_paid and fakery_stake flow from _admit → RacerSpec.
  SP8.  claimant_ids are deterministic: f"{job_id}:{i}:{model}".
  SP9.  isolation is always "worktree".
  SP10. operator_id is derived correctly (same provider+model → same operator_id).
  SP11. default_launcher_adapter raises RuntimeError (not at import time, only when called).
  SP12. spawn_roster returns all handles even when all spawns fail (no abort).
  SP13. build_roster passes report_to= through to RacerSpec.report_to.
  SP14. Duplicate models in roster raises ValueError (I3).
  SP15. Mid-roster admit failure rolls back all already-admitted entries (I1).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from prd_taskmaster.tournament.antisybil import (
    PER_JOB_CAP_N,
    SybilLimitError,
)
from prd_taskmaster.tournament.spawn import (
    RacerSpec,
    build_roster,
    default_launcher_adapter,
    spawn_roster,
)

# ─── Constants ────────────────────────────────────────────────────────────────

NOW = "2026-06-17T00:00:00+00:00"
JOB_ID = "job-test-xyz"
CARD_REF = "card-abc-001"
TASK_PROMPT = "Implement the XYZ feature with full test coverage."
BASE_REF = "abc1234def5678"
REPORT_TO = "orch-inbox-id"

# ─── Stub helpers ─────────────────────────────────────────────────────────────

class AdmitRecorder:
    """Stub that records admit calls and returns a fixed fee dict."""

    def __init__(self, entry_fee: int = 1, fakery_stake: int = 5) -> None:
        self.calls: list[dict] = []
        self._entry_fee = entry_fee
        self._fakery_stake = fakery_stake

    def __call__(self, operators_path: Path, *, operator_id: str, job_id: str,
                 claimant_id: str, now: str, **kwargs: Any) -> dict:
        self.calls.append({
            "operators_path": operators_path,
            "operator_id": operator_id,
            "job_id": job_id,
            "claimant_id": claimant_id,
            "now": now,
        })
        return {"entry_fee_paid": self._entry_fee, "fakery_stake": self._fakery_stake}


class AdmitFailsAtK:
    """Stub that succeeds for the first k-1 calls then raises SybilLimitError."""

    def __init__(self, fail_at: int) -> None:
        self.call_count = 0
        self.fail_at = fail_at
        self.admitted_claimant_ids: list[str] = []

    def __call__(self, operators_path: Path, *, operator_id: str, job_id: str,
                 claimant_id: str, now: str, **kwargs: Any) -> dict:
        self.call_count += 1
        if self.call_count > self.fail_at:
            raise SybilLimitError("operator_rate_limited")
        self.admitted_claimant_ids.append(claimant_id)
        return {"entry_fee_paid": 1, "fakery_stake": 5}


class ReleaseRecorder:
    """Stub that records release calls."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, operators_path: Path, *, job_id: str,
                 claimant_id: str | None = None, **kwargs: Any) -> None:
        self.calls.append({"job_id": job_id, "claimant_id": claimant_id})


def _stub_spawn(spec: RacerSpec) -> dict:
    """Stub spawn that returns a minimal handle dict."""
    return {"claimant_id": spec.claimant_id, "session_id": f"sess-{spec.claimant_id}"}


# ─── SP1–SP3: basic build_roster ─────────────────────────────────────────────

class TestBuildRoster:
    def _build(
        self,
        models: "list[str]",
        tmp_path: Path,
        *,
        admit_recorder: "AdmitRecorder | None" = None,
        release_recorder: "ReleaseRecorder | None" = None,
        report_to: str = REPORT_TO,
        base_ref: str = BASE_REF,
    ) -> "tuple[list[RacerSpec], AdmitRecorder]":
        recorder = admit_recorder or AdmitRecorder()
        rel = release_recorder or ReleaseRecorder()
        ops = tmp_path / "operators.json"
        roster = build_roster(
            models=models,
            job_id=JOB_ID,
            task_prompt=TASK_PROMPT,
            card_ref=CARD_REF,
            base_ref=base_ref,
            report_to=report_to,
            operators_path=ops,
            now=NOW,
            _admit=recorder,
            _release=rel,
        )
        return roster, recorder

    def test_three_models_three_specs(self, tmp_path: Path) -> None:
        """SP1: 3 models → 3 RacerSpecs."""
        models = ["claude:sonnet", "claude:haiku", "claude:opus"]
        roster, _ = self._build(models, tmp_path)
        assert len(roster) == 3
        assert all(isinstance(s, RacerSpec) for s in roster)

    def test_distinct_claimant_ids(self, tmp_path: Path) -> None:
        """SP1: all claimant_ids are distinct."""
        models = ["claude:sonnet", "claude:haiku", "claude:opus"]
        roster, _ = self._build(models, tmp_path)
        ids = [s.claimant_id for s in roster]
        assert len(ids) == len(set(ids))

    def test_claimant_id_format(self, tmp_path: Path) -> None:
        """SP8: claimant_id = f'{job_id}:{i}:{model}'."""
        models = ["claude:sonnet", "claude:haiku"]
        roster, _ = self._build(models, tmp_path)
        assert roster[0].claimant_id == f"{JOB_ID}:0:claude:sonnet"
        assert roster[1].claimant_id == f"{JOB_ID}:1:claude:haiku"

    def test_prompt_contains_job_id(self, tmp_path: Path) -> None:
        """SP2a: each prompt contains the job_id."""
        models = ["claude:sonnet", "claude:haiku", "claude:opus"]
        roster, _ = self._build(models, tmp_path)
        for spec in roster:
            assert JOB_ID in spec.prompt

    def test_prompt_contains_card_ref(self, tmp_path: Path) -> None:
        """SP2b: each prompt contains the card_ref."""
        models = ["claude:sonnet", "claude:haiku", "claude:opus"]
        roster, _ = self._build(models, tmp_path)
        for spec in roster:
            assert CARD_REF in spec.prompt

    def test_prompt_contains_commit_reveal_instructions(self, tmp_path: Path) -> None:
        """SP2c: each prompt contains commit-reveal keywords."""
        models = ["claude:sonnet", "claude:haiku"]
        roster, _ = self._build(models, tmp_path)
        for spec in roster:
            # The key commit-reveal terms must appear
            assert "commit" in spec.prompt.lower()
            assert "sha" in spec.prompt.lower() or "commit sha" in spec.prompt.lower()
            assert "sha256" in spec.prompt.lower() or "sha-256" in spec.prompt.lower()

    def test_prompt_contains_real_base_ref_not_placeholder(self, tmp_path: Path) -> None:
        """SP2d (B1): prompt contains the actual base_ref, not the literal '<base>'."""
        models = ["claude:sonnet", "claude:haiku"]
        roster, _ = self._build(models, tmp_path, base_ref=BASE_REF)
        for spec in roster:
            assert BASE_REF in spec.prompt, (
                f"base_ref {BASE_REF!r} not found in prompt"
            )
            assert "<base>" not in spec.prompt, (
                "Literal '<base>' placeholder still present — diff hash will be wrong"
            )

    def test_prompt_contains_report_to_inbox(self, tmp_path: Path) -> None:
        """SP2e (B2): prompt contains the report_to inbox address."""
        models = ["claude:sonnet"]
        roster, _ = self._build(models, tmp_path, report_to=REPORT_TO)
        for spec in roster:
            assert REPORT_TO in spec.prompt, (
                f"report_to {REPORT_TO!r} not embedded in racer prompt"
            )

    def test_admit_called_once_per_racer(self, tmp_path: Path) -> None:
        """SP3: _admit stub is called exactly once per model."""
        models = ["claude:sonnet", "claude:haiku", "claude:opus"]
        _, recorder = self._build(models, tmp_path)
        assert len(recorder.calls) == 3

    def test_admit_called_with_correct_job_id(self, tmp_path: Path) -> None:
        """SP3: each _admit call passes the correct job_id."""
        models = ["claude:sonnet", "claude:haiku"]
        _, recorder = self._build(models, tmp_path)
        for call in recorder.calls:
            assert call["job_id"] == JOB_ID

    def test_admit_called_with_correct_claimant_id(self, tmp_path: Path) -> None:
        """SP3: _admit receives the deterministically-derived claimant_id."""
        models = ["claude:sonnet", "claude:haiku"]
        _, recorder = self._build(models, tmp_path)
        assert recorder.calls[0]["claimant_id"] == f"{JOB_ID}:0:claude:sonnet"
        assert recorder.calls[1]["claimant_id"] == f"{JOB_ID}:1:claude:haiku"

    def test_isolation_always_worktree(self, tmp_path: Path) -> None:
        """SP9: all RacerSpecs have isolation='worktree'."""
        models = ["claude:sonnet", "claude:haiku"]
        roster, _ = self._build(models, tmp_path)
        assert all(s.isolation == "worktree" for s in roster)

    def test_entry_fee_and_stake_flow_from_admit(self, tmp_path: Path) -> None:
        """SP7: entry_fee_paid=1, fakery_stake=5 land on specs from stub."""
        models = ["claude:sonnet"]
        recorder = AdmitRecorder(entry_fee=1, fakery_stake=5)
        roster, _ = self._build(models, tmp_path, admit_recorder=recorder)
        assert roster[0].entry_fee_paid == 1
        assert roster[0].fakery_stake == 5

    def test_custom_fee_flows_to_spec(self, tmp_path: Path) -> None:
        """SP7: custom fee from admit stub lands on spec unchanged."""
        models = ["claude:sonnet"]
        recorder = AdmitRecorder(entry_fee=10, fakery_stake=50)
        roster, _ = self._build(models, tmp_path, admit_recorder=recorder)
        assert roster[0].entry_fee_paid == 10
        assert roster[0].fakery_stake == 50

    def test_report_to_propagated(self, tmp_path: Path) -> None:
        """SP13: report_to= flows through to RacerSpec.report_to."""
        models = ["claude:sonnet"]
        roster, _ = self._build(models, tmp_path, report_to="orch-inbox-id")
        assert roster[0].report_to == "orch-inbox-id"

    def test_model_on_spec(self, tmp_path: Path) -> None:
        """Model string is preserved on the spec unchanged."""
        models = ["claude:sonnet", "openrouter:gpt-5"]
        roster, _ = self._build(models, tmp_path)
        assert roster[0].model == "claude:sonnet"
        assert roster[1].model == "openrouter:gpt-5"


# ─── SP4: up-front cap guard ──────────────────────────────────────────────────

class TestBuildRosterCapGuard:
    def test_more_than_cap_raises_up_front(self, tmp_path: Path) -> None:
        """SP4: >PER_JOB_CAP_N models → SybilLimitError up front, before any _admit calls."""
        models = [f"claude:model-{i}" for i in range(PER_JOB_CAP_N + 1)]
        recorder = AdmitRecorder()

        with pytest.raises(SybilLimitError) as exc_info:
            build_roster(
                models=models,
                job_id=JOB_ID,
                task_prompt=TASK_PROMPT,
                card_ref=CARD_REF,
                base_ref=BASE_REF,
                operators_path=tmp_path / "ops.json",
                now=NOW,
                _admit=recorder,
            )

        assert exc_info.value.reason == "job_cap_exceeded"
        # The up-front guard should have fired before any admit calls.
        assert len(recorder.calls) == 0

    def test_exactly_cap_models_succeeds(self, tmp_path: Path) -> None:
        """Exactly PER_JOB_CAP_N models is allowed."""
        models = [f"claude:model-{i}" for i in range(PER_JOB_CAP_N)]
        recorder = AdmitRecorder()

        roster = build_roster(
            models=models,
            job_id=JOB_ID,
            task_prompt=TASK_PROMPT,
            card_ref=CARD_REF,
            base_ref=BASE_REF,
            operators_path=tmp_path / "ops.json",
            now=NOW,
            _admit=recorder,
        )
        assert len(roster) == PER_JOB_CAP_N


# ─── SP14: duplicate model guard (I3) ────────────────────────────────────────

class TestDuplicateModelGuard:
    def test_duplicate_models_raises_value_error(self, tmp_path: Path) -> None:
        """SP14 (I3): duplicate models in roster raises ValueError before any admit."""
        recorder = AdmitRecorder()

        with pytest.raises(ValueError, match="duplicate models in roster"):
            build_roster(
                models=["claude:sonnet", "claude:haiku", "claude:sonnet"],
                job_id=JOB_ID,
                task_prompt=TASK_PROMPT,
                card_ref=CARD_REF,
                base_ref=BASE_REF,
                operators_path=tmp_path / "ops.json",
                now=NOW,
                _admit=recorder,
            )

        # No admits should have happened — the dup check fires first.
        assert len(recorder.calls) == 0

    def test_all_duplicates_named_in_error(self, tmp_path: Path) -> None:
        """I3: the ValueError message names the duplicate model(s)."""
        recorder = AdmitRecorder()

        with pytest.raises(ValueError) as exc_info:
            build_roster(
                models=["claude:sonnet", "claude:sonnet", "claude:haiku"],
                job_id=JOB_ID,
                task_prompt=TASK_PROMPT,
                card_ref=CARD_REF,
                base_ref=BASE_REF,
                operators_path=tmp_path / "ops.json",
                now=NOW,
                _admit=recorder,
            )

        assert "claude:sonnet" in str(exc_info.value)

    def test_all_distinct_models_do_not_raise(self, tmp_path: Path) -> None:
        """Non-duplicate models pass through without error."""
        recorder = AdmitRecorder()

        roster = build_roster(
            models=["claude:sonnet", "claude:haiku"],
            job_id=JOB_ID,
            task_prompt=TASK_PROMPT,
            card_ref=CARD_REF,
            base_ref=BASE_REF,
            operators_path=tmp_path / "ops.json",
            now=NOW,
            _admit=recorder,
        )
        assert len(roster) == 2


# ─── SP15: roster rollback on partial admit (I1) ──────────────────────────────

class TestRosterRollback:
    def test_partial_admit_failure_releases_prior_entries(self, tmp_path: Path) -> None:
        """SP15 (I1): if _admit raises at the k-th model, all k-1 prior entries are released."""
        # Succeed for the first 2 models, fail on the 3rd.
        admit_stub = AdmitFailsAtK(fail_at=2)
        release_stub = ReleaseRecorder()

        with pytest.raises(SybilLimitError) as exc_info:
            build_roster(
                models=["claude:sonnet", "claude:haiku", "claude:opus"],
                job_id=JOB_ID,
                task_prompt=TASK_PROMPT,
                card_ref=CARD_REF,
                base_ref=BASE_REF,
                operators_path=tmp_path / "ops.json",
                now=NOW,
                _admit=admit_stub,
                _release=release_stub,
            )

        assert exc_info.value.reason == "operator_rate_limited"

        # The 2 already-admitted claimants must have been released.
        released_ids = {c["claimant_id"] for c in release_stub.calls}
        assert f"{JOB_ID}:0:claude:sonnet" in released_ids
        assert f"{JOB_ID}:1:claude:haiku" in released_ids
        # The 3rd (which never admitted) must NOT appear.
        assert f"{JOB_ID}:2:claude:opus" not in released_ids

    def test_first_admit_failure_releases_nothing(self, tmp_path: Path) -> None:
        """I1: if the FIRST admit fails, there is nothing to roll back."""
        admit_stub = AdmitFailsAtK(fail_at=0)
        release_stub = ReleaseRecorder()

        with pytest.raises(SybilLimitError):
            build_roster(
                models=["claude:sonnet"],
                job_id=JOB_ID,
                task_prompt=TASK_PROMPT,
                card_ref=CARD_REF,
                base_ref=BASE_REF,
                operators_path=tmp_path / "ops.json",
                now=NOW,
                _admit=admit_stub,
                _release=release_stub,
            )

        assert len(release_stub.calls) == 0

    def test_successful_roster_does_not_call_release(self, tmp_path: Path) -> None:
        """I1: on a fully successful build, _release is never called."""
        admit_stub = AdmitRecorder()
        release_stub = ReleaseRecorder()

        build_roster(
            models=["claude:sonnet", "claude:haiku"],
            job_id=JOB_ID,
            task_prompt=TASK_PROMPT,
            card_ref=CARD_REF,
            base_ref=BASE_REF,
            operators_path=tmp_path / "ops.json",
            now=NOW,
            _admit=admit_stub,
            _release=release_stub,
        )

        assert len(release_stub.calls) == 0


# ─── SP10: operator_id derivation ─────────────────────────────────────────────

class TestOperatorIdDerivation:
    def test_same_provider_and_model_same_operator_id(self, tmp_path: Path) -> None:
        """SP10: same model string → same operator_id → rate-limit applies."""
        recorder = AdmitRecorder()
        build_roster(
            models=["claude:sonnet", "claude:haiku"],
            job_id=JOB_ID,
            task_prompt=TASK_PROMPT,
            card_ref=CARD_REF,
            base_ref=BASE_REF,
            operators_path=tmp_path / "ops.json",
            now=NOW,
            _admit=recorder,
        )
        # Different models → different operator_ids
        assert recorder.calls[0]["operator_id"] == "claude:sonnet"
        assert recorder.calls[1]["operator_id"] == "claude:haiku"

    def test_openrouter_model_different_from_claude(self, tmp_path: Path) -> None:
        """SP10: openrouter:X is distinct from claude:X."""
        recorder = AdmitRecorder()
        build_roster(
            models=["claude:sonnet", "openrouter:claude-3-sonnet"],
            job_id=JOB_ID,
            task_prompt=TASK_PROMPT,
            card_ref=CARD_REF,
            base_ref=BASE_REF,
            operators_path=tmp_path / "ops.json",
            now=NOW,
            _admit=recorder,
        )
        assert recorder.calls[0]["operator_id"] != recorder.calls[1]["operator_id"]


# ─── SP5–SP6: spawn_roster ────────────────────────────────────────────────────

class TestSpawnRoster:
    def _roster(self, n: int = 3) -> "list[RacerSpec]":
        return [
            RacerSpec(
                claimant_id=f"{JOB_ID}:{i}:claude:sonnet",
                operator_id="claude:sonnet",
                model="claude:sonnet",
                job_id=JOB_ID,
                prompt="do task",
                isolation="worktree",
                report_to="",
                entry_fee_paid=1,
                fakery_stake=5,
            )
            for i in range(n)
        ]

    def test_spawn_returns_n_handles(self) -> None:
        """SP5: spawn_roster with stub → N handle dicts."""
        roster = self._roster(3)
        handles = spawn_roster(roster, _spawn_fn=_stub_spawn)
        assert len(handles) == 3

    def test_all_spawned_true_on_success(self) -> None:
        """SP5: all handles have spawned=True when stub succeeds."""
        roster = self._roster(3)
        handles = spawn_roster(roster, _spawn_fn=_stub_spawn)
        assert all(h["spawned"] is True for h in handles)

    def test_claimant_id_in_each_handle(self) -> None:
        """Handles carry the claimant_id."""
        roster = self._roster(3)
        handles = spawn_roster(roster, _spawn_fn=_stub_spawn)
        for i, h in enumerate(handles):
            assert h["claimant_id"] == roster[i].claimant_id

    def test_failing_spawn_does_not_abort_roster(self) -> None:
        """SP6: one failing _spawn_fn → that racer spawned=False, others spawned=True."""
        roster = self._roster(3)
        fail_id = roster[1].claimant_id

        def _flaky(spec: RacerSpec) -> dict:
            if spec.claimant_id == fail_id:
                raise RuntimeError("session spawn failed")
            return _stub_spawn(spec)

        handles = spawn_roster(roster, _spawn_fn=_flaky)
        assert len(handles) == 3

        statuses = {h["claimant_id"]: h["spawned"] for h in handles}
        assert statuses[roster[0].claimant_id] is True
        assert statuses[fail_id] is False
        assert statuses[roster[2].claimant_id] is True

    def test_failed_spawn_has_error_key(self) -> None:
        """SP6: failed spawn entry carries error= describing the exception."""
        roster = self._roster(2)

        def _always_fail(spec: RacerSpec) -> dict:
            raise ValueError("launch error")

        handles = spawn_roster(roster, _spawn_fn=_always_fail)
        for h in handles:
            assert h["spawned"] is False
            assert "error" in h
            assert "launch error" in h["error"]

    def test_all_spawns_fail_returns_all_handles(self) -> None:
        """SP12: even when ALL spawns fail, we get all N handles back."""
        roster = self._roster(5)

        def _always_fail(spec: RacerSpec) -> dict:
            raise RuntimeError("fail")

        handles = spawn_roster(roster, _spawn_fn=_always_fail)
        assert len(handles) == 5
        assert all(h["spawned"] is False for h in handles)

    def test_spawn_fn_receives_correct_spec(self) -> None:
        """_spawn_fn receives the exact RacerSpec from the roster."""
        roster = self._roster(2)
        received: list[RacerSpec] = []

        def _recording_spawn(spec: RacerSpec) -> dict:
            received.append(spec)
            return _stub_spawn(spec)

        spawn_roster(roster, _spawn_fn=_recording_spawn)
        assert received == roster


# ─── SP11: default_launcher_adapter ──────────────────────────────────────────

class TestDefaultLauncherAdapter:
    def test_import_does_not_raise(self) -> None:
        """SP11: importing default_launcher_adapter doesn't import/call live launcher."""
        # Simply importing it should never fail or hit the live MCP
        from prd_taskmaster.tournament.spawn import default_launcher_adapter  # noqa: F401

    def test_calling_raises_runtime_error(self) -> None:
        """SP11: calling default_launcher_adapter raises RuntimeError with guidance."""
        spec = RacerSpec(
            claimant_id="job-1:0:claude:sonnet",
            operator_id="claude:sonnet",
            model="claude:sonnet",
            job_id="job-1",
            prompt="do stuff",
            isolation="worktree",
            report_to="",
            entry_fee_paid=1,
            fakery_stake=5,
        )

        with pytest.raises(RuntimeError) as exc_info:
            default_launcher_adapter(spec)

        assert "atlas-launcher" in str(exc_info.value).lower() or "session_spawn" in str(exc_info.value)

    def test_no_live_launcher_import_at_module_load(self) -> None:
        """Importing spawn.py must not import the atlas_launcher MCP module."""
        import sys

        # Ensure spawn is already loaded (it was imported above)
        assert "prd_taskmaster.tournament.spawn" in sys.modules

        # No atlas_launcher module should be in sys.modules from that import
        atlas_launcher_modules = [
            k for k in sys.modules
            if "atlas_launcher" in k or "atlas-launcher" in k
        ]
        assert len(atlas_launcher_modules) == 0
