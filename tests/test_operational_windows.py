"""P5 SOFTWARE: genuine worker startup, real SQLite and bounded CPU effect seams."""

from __future__ import annotations

import copy
import gzip
import hashlib
import importlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from contextvars import copy_context
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest

from cloud_edge_robot_arm.contracts.models import RobotState
from cloud_edge_robot_arm.research.operational_time_v1 import (
    OperationalEventToken,
    OperationalTimeError,
    _open_clock_for_test,
)
from tests.test_operational_time_v1 import _identity


def marker_cpu_inputs():
    """Pinned historical pixels for CPU logic only; never new live/admission evidence."""
    from cloud_edge_robot_arm.contracts.models import TaskTarget
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests/fixtures/p5_marker_source_v1"
    provenance = json.loads((fixture / "provenance.json").read_text())
    assert provenance["scope"] == "SOFTWARE_ONLY_DEVELOPMENT_DIAGNOSTIC_REUSE_NOT_NEW_ACTUAL"
    compressed = (fixture / "observation-full.json.gz").read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == (
        "21bf6d3787eca744af20c205469b8c56c51b46cd14e53068f12d7dbf1f251fca"
    )
    pixels = gzip.decompress(compressed)
    assert hashlib.sha256(pixels).hexdigest() == provenance["original_frame"]["sha256"]
    module = importlib.import_module("cloud_edge_robot_arm.vision.marker_association")
    observation = RGBDObservation.model_validate_json(pixels)
    registration = module.load_marker_registration(
        fixture / "registration.json",
        expected_registry_sha256="3e9cf0c1d44116cec83d913e003b53ec8157d09acf36164078825ae6c836c5bc",
        root=root,
    )
    assert registration.sources_valid()
    assert registration.admission_scope == "DEVELOPMENT_ONLY"
    context = module.marker_frame_context(
        observation,
        registration,
        task_id="diagnostic-task",
        task_target=TaskTarget(
            object_id="object", object_class="cube", target_region_id="target_region"
        ),
        instruction="pick the red cube and place it in the green target region",
        context_hash="1" * 64,
        role_bundle_hash="2" * 64,
        active_asset_sha256=registration.pose_marker.marked_asset_sha256,
        plan_version=1,
        command_seq=1,
    )
    return module, observation, registration, context


@contextmanager
def supervision_cpu_utc(monkeypatch, runtime, claim):
    """One software node's UTC basis; real SQL/source/lease and TTL gates still run."""
    stored = runtime.source.event_repository.get_visual_supervision(runtime.episode_id)
    payload = stored.to_payload()
    basis = datetime.now(UTC)
    assert basis >= datetime.fromisoformat(payload["claims"][claim.claim_id]["reserved_at"])
    assert all(basis >= datetime.fromisoformat(item["committed_at"]) for item in payload["history"])

    class CpuUtcDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return basis.replace(tzinfo=None) if tz is None else basis.astimezone(tz)

    with monkeypatch.context() as local:
        for name in (
            "cloud_edge_robot_arm.vision.worker_owner",
            "cloud_edge_robot_arm.vision.worker_runtime",
            "cloud_edge_robot_arm.repositories.event_autonomy.sqlite",
        ):
            local.setattr(importlib.import_module(name), "datetime", CpuUtcDateTime)
        yield basis


def frozen_json(value):
    if type(value) is dict:
        return MappingProxyType({key: frozen_json(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(frozen_json(item) for item in value)
    return value


def legacy_codec(name):
    """Use frozen pre-P5 bytes, not a copied expected value from today's codec."""
    path = Path(
        "artifacts/research/process/20261004-ced-development/astra-rounds/"
        "round102-p5-preflight-plan-shape-20261008/implementation/source-before/"
        "src/cloud_edge_robot_arm/repositories/event_autonomy"
    ) / (name + ".py")
    namespace = {
        "__name__": "cloud_edge_robot_arm.repositories.event_autonomy." + name,
    }
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    return namespace


class CpuCounter:
    resolution_seconds = 1e-9

    def __init__(self):
        self.now = 0
        self.close_call_count = 0
        self.current_identity = _identity()

    def identity(self):
        return self.current_identity

    def read_ns(self):
        return self.now


def api():
    # Deliberately local: absent planned API is a named RED, not collection failure.
    return importlib.import_module("cloud_edge_robot_arm.vision.operational_windows")


def event(owner, kind="capture"):
    token = owner.clock.begin_event(kind)
    owner.clock.mark_event(token)
    return token, owner.clock.end_event(token)


def exercise(
    monkeypatch,
    tmp_path,
    callback,
    *,
    initialize=None,
    settle=None,
    startup_config=None,
    startup_parameters=None,
):
    module = api()
    from tests.test_visual_worker_factory import software_factory

    counter = CpuCounter()
    clocks = []

    def clock_factory():
        clock = _open_clock_for_test(counter)
        original = clock.close

        def close():
            counter.close_call_count += 1
            original()

        clock.close = close
        clocks.append(clock)
        return clock

    monkeypatch.setattr(module, "open_operational_clock", clock_factory)
    errors, results = [], []
    received = []

    def run(worker, repo, job, root):
        try:
            runtime = received[0][3].worker_runtime
            results.append(callback(module, runtime, counter, worker, repo, job))
        except BaseException as error:
            errors.append(error)
            raise

    data = software_factory(
        monkeypatch,
        tmp_path,
        during_initialize=initialize,
        during_settle=settle,
        during_episode=run,
    )
    repo, job, worker, calls, actual_received, backend, events = data
    received = actual_received
    if startup_parameters is not None:
        from tests.test_visual_worker_factory import persist_original_runtime_parameters

        persist_original_runtime_parameters(repo, job, startup_parameters)
    if startup_config:
        task_s, verification_s = startup_config
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute(
                "UPDATE simulation_jobs SET timeout_seconds=? WHERE job_id=?",
                (task_s, job.job_id),
            )
        from cloud_edge_robot_arm.vision.role_models import configuration_hash

        binding = worker.visual_role_binding
        policy = binding.evidence()["edge_policy"]
        policy["verification_budget"]["deadline_s"] = verification_s
        edge = replace(binding.edge_snapshot, request_config_hash=configuration_hash(policy))
        worker.visual_role_binding = replace(
            binding,
            edge_policy=policy,
            edge_snapshot=edge,
            bundle=replace(binding.bundle, edge_provider_hash=edge.digest()),
        )
    try:
        assert worker.poll_once()
        if errors:
            raise errors[0]
        assert results, repo.get_job(job.job_id).error_message
        assert clocks and counter.close_call_count == 1
        assert clocks[0]._closed
        return results[0], data, counter
    finally:
        events.close()


def captured(runtime, identifier="p5-frame"):
    from tests.test_visual_worker_runtime import frame

    claim = runtime.reserve_capture(RobotState(connected=True), initial=True)
    observation = frame(identifier).model_copy(update={"episode_id": runtime.episode_id})
    # Revalidate checksum after the actual CPU acquisition identity changes.
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    payload = observation.model_dump(mode="json")
    payload["checksum_sha256"] = ""
    observation = RGBDObservation.model_validate(payload)
    runtime.complete_capture(claim, observation, RobotState(connected=True))
    return observation


def usable_plan(runtime, observation):
    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
    from tests.test_visual_owner_registration import values

    claim = runtime.reserve_plan(RobotState(connected=True))
    parsed = values()["original"].contract.model_dump(mode="json")
    parsed["user_instruction"] = runtime.bootstrap.definition.user_instruction
    draft = PlannerDraft(
        raw_text="SOFTWARE_ONLY",
        parsed_json=parsed,
        observation_evidence={
            **observation.evidence(),
            "model_snapshot_hash": runtime.bootstrap.definition.model_snapshot_hash,
            "role_bundle_hash": runtime.bootstrap.definition.role_bundle_hash,
        },
    )
    runtime.complete_plan(claim, draft, RobotState(connected=True))
    return draft


def test_five_seconds_inclusive_and_plus_one_ns_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        token, receipt = event(owner)
        window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=())
        smaller = owner.issue("capture", receipt, budget_ns=1_000_000_000, parent_ids=())
        raw.now = 1_000_000_000
        assert owner.check(smaller, after=token).status == "VALID"
        raw.now += 1
        assert owner.check(smaller, after=token).status == "INVALID"
        raw.now = 5_000_000_000
        assert owner.check(window, after=token).status == "VALID"
        raw.now += 1
        assert owner.check(window, after=token).status == "INVALID"

    exercise(monkeypatch, tmp_path, run)


@pytest.mark.parametrize("hard_source", ["task", "verification", "parent_hard"])
def test_deadline_equality_rejected(monkeypatch, tmp_path, hard_source):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        token, receipt = event(owner)
        parents = ()
        if hard_source == "parent_hard":
            parent = owner.issue(
                "bootstrap", owner.task_origin, budget_ns=5_000_000_000, parent_ids=()
            )
            parents = (parent,)
        window = owner.issue("plan", receipt, budget_ns=5_000_000_000, parent_ids=parents)
        assert owner.export_record(window)["deadline_ns"] == 5_000_000_000
        raw.now = 4_999_999_999
        assert owner.check(window, after=token).status == "VALID"
        raw.now += 1
        assert owner.check(window, after=token).status == "INVALID"

    config = {"task": (5, 120), "verification": (120, 5), "parent_hard": (120, 120)}
    exercise(monkeypatch, tmp_path, run, startup_config=config[hard_source])


def test_missing_pair_foreign_domain_and_copied_handle_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        token, receipt = event(owner)
        forged = OperationalEventToken(owner.clock.domain, token.event_identity, token.kind)
        window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=())
        assert owner.check(window, after=forged).status == "UNKNOWN"
        foreign = _open_clock_for_test(CpuCounter())
        other = foreign.begin_event("capture")
        foreign.mark_event(other)
        foreign_receipt = foreign.end_event(other)
        with pytest.raises(OperationalTimeError):
            owner.issue("capture", foreign_receipt, budget_ns=1, parent_ids=())
        with pytest.raises(OperationalTimeError):
            copy.copy(owner)
        with pytest.raises(OperationalTimeError):
            copy.copy(receipt)
        foreign.close()

    exercise(monkeypatch, tmp_path, run)


def test_valid_overlap_accepted_future_and_out_of_order_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        token, receipt = event(owner)
        window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=())
        # Equal raw bounds still have a real event-before-current logical sequence.
        assert owner.check(window, after=token).status == "VALID"
        pending = owner.clock.begin_event("unfinished")
        assert owner.check(window, after=pending).status == "UNKNOWN"
        raw.now = -1
        assert owner.check(window, after=token).status == "UNKNOWN"
        raw.now = 0
        assert owner.check(window, after=token).status == "UNKNOWN"
        assert owner._clock._closed

    exercise(monkeypatch, tmp_path, run)


def test_reply_reobserve_and_new_event_do_not_refresh_origin(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        origin = owner.task_origin
        first = owner.export_record(owner.task_window)
        raw.now = 2_000_000_000
        _, receipt = event(owner, "plan")
        child = owner.issue(
            "plan", receipt, budget_ns=5_000_000_000, parent_ids=(owner.task_window,)
        )
        assert owner.task_origin is origin
        assert owner.export_record(child)["deadline_ns"] <= first["deadline_ns"]
        assert owner.export_record(owner.task_window) == first
        with pytest.raises(OperationalTimeError):
            owner.issue("plan", receipt, budget_ns=5_000_000_001, parent_ids=())

    exercise(monkeypatch, tmp_path, run)


def test_cached_frame_preserves_original_acquisition_window(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        first = module._reference_for_observation(observation, "condition")
        raw.now = 4_000_000_000
        cached = observation.model_copy(deep=True)
        assert module._reference_for_observation(cached, "condition") == first
        raw.now = 5_000_000_001
        assert module._check_observation(cached, "condition") is False

    exercise(monkeypatch, tmp_path, run)


def test_external_utc_deadline_cannot_be_relabelled_operational(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        assert reference["lease_deadline_domain"] == "UTC_LEGACY_VETO"
        assert "lease_deadline_ns" not in reference
        fake = {**reference, "schema_version": "external.utc.v1"}
        assert module._check_reference(fake).status == "UNKNOWN"
        from cloud_edge_robot_arm.edge.evidence.conditions import (
            ConditionSpec,
            OnlineEvidenceSnapshot,
            evaluate_conditions,
        )

        verdict = evaluate_conditions(
            [ConditionSpec("robot_stopped")],
            OnlineEvidenceSnapshot(observation, RobotState(connected=True)),
            now=observation.captured_at + timedelta(seconds=6),
        )[0]
        assert verdict.status == "UNKNOWN"  # Unlabelled legacy UTC remains strict.

    exercise(monkeypatch, tmp_path, run)


def test_utc_jump_is_diagnostic_only_for_supported_local_domain(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        from cloud_edge_robot_arm.edge.evidence.conditions import (
            ConditionSpec,
            OnlineEvidenceSnapshot,
            evaluate_conditions,
        )

        evidence = OnlineEvidenceSnapshot(
            observation, RobotState(connected=True, stopped=True), operational_reference=reference
        )
        for delta in (-1000, 1000):
            verdict = evaluate_conditions(
                [ConditionSpec("robot_stopped")],
                evidence,
                now=observation.captured_at + timedelta(seconds=delta),
            )[0]
            assert verdict.status == "PASS"
        raw.now = 5_000_000_001
        assert (
            evaluate_conditions([ConditionSpec("robot_stopped")], evidence)[0].status == "UNKNOWN"
        )

    exercise(monkeypatch, tmp_path, run)


def test_source_and_budget_changes_invalidate_window(monkeypatch, tmp_path):
    owners, nonces, repositories, case_results = [], [], [], []
    for mutation in ("budget", "source"):
        case_root = tmp_path / mutation
        case_root.mkdir()
        with monkeypatch.context() as local_patch:

            def run(module, runtime, raw, worker, repo, job, mutation=mutation):
                owner = runtime._operational_owner
                assert not owner._closed
                nonce = owner.clock.domain.startup_nonce
                owners.append(owner)
                nonces.append(nonce)
                repositories.append(Path(repo.database_path))
                token, receipt = event(owner)
                window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=())
                baseline = owner.check(window, after=token).status
                assert baseline == "VALID" and not owner._closed
                original_counter = raw.now
                original_timeout = repo.get_job(job.job_id).timeout_seconds
                assert original_timeout == job.timeout_seconds
                path = runtime.source.source_root / "device.py"
                original = path.read_bytes()
                expected_sha = runtime.source.source_hashes["device.py"]
                assert hashlib.sha256(original).hexdigest() == expected_sha
                if mutation == "budget":
                    try:
                        with sqlite3.connect(repo.database_path) as connection:
                            connection.execute(
                                "UPDATE simulation_jobs SET timeout_seconds=? WHERE job_id=?",
                                (original_timeout + 1, job.job_id),
                            )
                        assert not owner._closed
                        rejected = owner.check(window, after=token).status
                        assert rejected == "UNKNOWN"
                    finally:
                        with sqlite3.connect(repo.database_path) as connection:
                            connection.execute(
                                "UPDATE simulation_jobs SET timeout_seconds=? WHERE job_id=?",
                                (original_timeout, job.job_id),
                            )
                    assert path.read_bytes() == original
                else:
                    assert repo.get_job(job.job_id).timeout_seconds == original_timeout
                    try:
                        path.write_bytes(original + b"# drift\n")
                        assert path.read_bytes() != original
                        changed_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                        assert changed_sha != expected_sha
                        assert not owner._closed
                        rejected = owner.check(window, after=token).status
                        assert rejected == "UNKNOWN"
                    finally:
                        path.write_bytes(original)
                        assert path.read_bytes() == original
                assert repo.get_job(job.job_id).timeout_seconds == original_timeout
                assert raw.now == original_counter
                return {
                    "mutation": mutation,
                    "owner_object_id": id(owner),
                    "startup_nonce": nonce,
                    "repository": str(repo.database_path),
                    "source_path": str(path),
                    "registered_source_sha256": expected_sha,
                    "baseline": baseline,
                    "rejected": rejected,
                    "original_timeout_s": original_timeout,
                    "original_D_ns": original_counter,
                    "restored_source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }

            result, _, counter = exercise(local_patch, case_root, run)
            assert counter.close_call_count == 1
            assert owners[-1]._closed
            case_results.append(result)
            (case_root / "drift-case-result.json").write_text(json.dumps(result, indent=2) + "\n")
    assert owners[0] is not owners[1]
    assert nonces[0] != nonces[1]
    assert repositories[0] != repositories[1]
    (tmp_path / "case-pair.json").write_text(
        json.dumps({"independent_lifecycles": 2, "cases": case_results}, indent=2) + "\n"
    )


def test_public_worker_or_source_without_startup_capability_cannot_issue(monkeypatch, tmp_path):
    def run(module, runtime, raw, worker, repo, job):
        with pytest.raises(OperationalTimeError):
            module.OperationalWindowOwner.from_worker(worker, job_id=job.job_id)
        public = runtime.source
        with pytest.raises(OperationalTimeError):
            module.OperationalWindowOwner.from_worker(public, job_id=job.job_id)
        with pytest.raises(OperationalTimeError):
            module.OperationalWindowOwner.from_worker({}, job_id=job.job_id)
        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

        replay = VisualWorkerRuntime(
            public,
            episode_id=runtime.episode_id,
            instruction=runtime.bootstrap.definition.user_instruction,
            role_binding=runtime.role_binding,
            model_snapshot_hash=runtime.bootstrap.definition.model_snapshot_hash,
            verification_limits=runtime.bootstrap.definition.verification_limits,
        )
        assert replay._operational_owner is None

    exercise(monkeypatch, tmp_path, run)


def test_ended_prefix_owner_or_lease_cannot_authorize_new_attempt(monkeypatch, tmp_path):
    module = api()
    result, data, _ = exercise(monkeypatch, tmp_path, lambda m, r, raw, *a: r._operational_owner)
    worker, job = data[2], data[1]
    worker._operational_prefix_application = result
    with pytest.raises(OperationalTimeError):
        module.OperationalWindowOwner.from_worker(worker, job_id=job.job_id)


def test_closed_owner_or_changed_live_lease_attempt_fencing_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, worker, repo, job):
        owner = runtime._operational_owner
        token, receipt = event(owner)
        window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=())
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute(
                "UPDATE simulation_jobs SET attempt=attempt+1 WHERE job_id=?", (job.job_id,)
            )
        assert owner.check(window, after=token).status == "UNKNOWN"
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute(
                "UPDATE simulation_jobs SET attempt=attempt-1 WHERE job_id=?", (job.job_id,)
            )
        return owner, window, token

    (owner, window, token), _, _ = exercise(monkeypatch, tmp_path, run)
    assert owner.check(window, after=token).status == "UNKNOWN"


def test_startup_origin_precedes_reset_and_settle(monkeypatch, tmp_path):
    module = api()
    origins = []

    def initialize(worker, *args):
        owner = module._owner_for_worker(worker)
        origins.append(owner.task_origin)
        owner.clock._source.now = 1_000_000_000

    def settle(worker, *args):
        owner = module._owner_for_worker(worker)
        assert owner.task_origin is origins[0]
        owner.clock._source.now = 2_000_000_000

    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        assert owner.task_origin is origins[0]
        assert owner.task_origin.lower_ns == 0
        assert owner.export_record(owner.task_window)["origin_domain"] == "ORIGINAL_TASK_D"
        assert owner.check(owner.task_window, after=owner.task_origin_token).status == "VALID"
        assert raw.now == 2_000_000_000

    exercise(monkeypatch, tmp_path, run, initialize=initialize, settle=settle)


@pytest.mark.parametrize("termination", ["normal", "exception", "cancellation", "lease_loss"])
def test_startup_failure_and_cleanup_revoke_once(monkeypatch, tmp_path, termination):
    def run(module, runtime, raw, worker, repo, job):
        owner = runtime._operational_owner
        if termination == "exception":
            # _execute handles this, but cleanup must remain observable afterward.
            worker._raise_if_cancelled_or_timed_out = lambda *a: (_ for _ in ()).throw(
                RuntimeError("CPU failure")
            )
        elif termination == "cancellation":
            from cloud_edge_robot_arm.simulation_runtime.worker import CancelledByOperator

            worker._raise_if_cancelled_or_timed_out = lambda *a: (_ for _ in ()).throw(
                CancelledByOperator("CPU cancelled")
            )
        elif termination == "lease_loss":
            repo.release_lease(runtime.source.lease_id)
            assert owner.check(owner.task_window, after=owner.task_origin_token).status == "UNKNOWN"
        return owner

    owner, data, raw = exercise(monkeypatch, tmp_path, run)
    api()._revoke_worker(data[2])
    assert raw.close_call_count == 1
    assert owner.check(owner.task_window, after=owner.task_origin_token).status == "UNKNOWN"


@pytest.mark.parametrize(
    "category", ["bootstrap", "capture", "plan", "grounding", "supervision", "marker", "condition"]
)
def test_all_p5_categories_use_same_original_owner(monkeypatch, tmp_path, category):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, category)
        assert reference["task_origin_event_id"] == owner.task_origin_token.event_identity
        assert module._check_reference(reference).status == "VALID"
        if category in {"bootstrap", "capture", "plan"}:
            usable_plan(runtime, observation)
            assert runtime.bootstrap.planning_source_usable
        elif category == "condition":
            from cloud_edge_robot_arm.edge.evidence.conditions import (
                ConditionSpec,
                OnlineEvidenceSnapshot,
                evaluate_conditions,
            )

            evidence = OnlineEvidenceSnapshot(
                observation,
                RobotState(connected=True, stopped=True),
                operational_reference=reference,
            )
            assert (
                evaluate_conditions([ConditionSpec("robot_stopped")], evidence)[0].status == "PASS"
            )
        elif category == "supervision":
            from cloud_edge_robot_arm.vision.observations import RGBDObservation
            from cloud_edge_robot_arm.vision.supervision import decide_supervision
            from tests.test_visual_worker_supervision_runtime import context_for, decision_for

            usable_plan(runtime, observation)
            runtime.adopt_plan(RobotState(connected=True))
            runtime.initialize_supervision(0.000001, RobotState(connected=True))
            claim = runtime.reserve_supervision_capture(1, RobotState(connected=True))
            with supervision_cpu_utc(monkeypatch, runtime, claim) as software_now:
                payload = observation.model_dump(mode="json")
                payload.update(
                    captured_at=software_now.isoformat(),
                    observation_id="p5-supervisor",
                    frame_id="p5-supervisor",
                    checksum_sha256="",
                )
                fresh = RGBDObservation.model_validate(payload)
                context = context_for(claim, fresh).model_copy(
                    update={
                        "task_instruction": runtime.bootstrap.definition.user_instruction,
                    }
                )
                runtime.complete_supervision_capture(
                    claim, fresh, context, RobotState(connected=True)
                )
                frame = runtime.reserve_supervision_plan(claim, RobotState(connected=True))
                reply = decision_for(frame)
                reference = module._reference_for_observation(fresh, "supervision")
                assert (
                    decide_supervision(
                        reply,
                        frame.context,
                        frame.context,
                        maximum_age_s=5,
                        operational_reference=frozen_json(reference),
                    )
                    == "CONTINUE"
                )
                assert (
                    decide_supervision(
                        reply,
                        frame.context,
                        frame.context,
                        maximum_age_s=6,
                        operational_reference=frozen_json(reference),
                    )
                    == "DISCARD"
                )
                record = runtime.complete_supervision_plan(frame, reply, RobotState(connected=True))
                assert (
                    record.to_payload()["claims"][frame.claim_id]["plan_completed_at"] is not None
                )
        elif category == "grounding":
            usable_plan(runtime, observation)
            contract, publication = runtime.adopt_plan(RobotState(connected=True))
            from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding

            step = contract.steps[0].model_copy(
                update={"preconditions": [], "success_conditions": []}
            )
            now = datetime.now(UTC)
            binding = StepGroundingBinding(
                runtime.original.digest(),
                runtime.original.identity,
                runtime.original.requirements[step.step_id],
                publication.owner_revision,
                publication.state_generation + 1,
                publication.checkpoint.checkpoint_hash,
                observation.observation_id,
                observation.checksum_sha256,
                observation.calibration_version,
                contract.plan_version,
                contract.command_seq,
                "6" * 64,
                "7" * 64,
                None,
                runtime.source.source_hashes,
                step.model_dump_json(),
                runtime.original.requirements[step.step_id].expected_duration_s,
                now,
                now + timedelta(seconds=3),
            )
            assert runtime.publish_grounding(binding, RobotState(connected=True)) is not None
        else:
            # Real marker consumer's freshness gate over an actual CPU image source.
            from cloud_edge_robot_arm.vision.marker_association import associate_marker_target
            from cloud_edge_robot_arm.vision.observations import RGBDObservation

            marker, original, registration, context = marker_cpu_inputs()
            payload = original.model_dump(mode="json")
            payload.update(
                episode_id=runtime.episode_id,
                captured_at=datetime.now(UTC).isoformat(),
                observation_id="cpu-marker",
                frame_id="cpu-marker",
                checksum_sha256="",
            )
            fresh = RGBDObservation.model_validate(payload)
            token, receipt = event(owner)
            module._register_observation(owner, receipt, fresh)
            context = replace(
                context,
                observation_id=fresh.observation_id,
                observation_sha256=fresh.checksum_sha256,
                episode_id=runtime.episode_id,
                operational_reference=module._reference_for_observation(fresh, "marker"),
            )
            frozen = context.operational_reference
            assert isinstance(frozen, MappingProxyType)
            assert isinstance(frozen["domain"], MappingProxyType)
            assert type(frozen["hard_deadlines"]) is tuple
            positive = associate_marker_target(fresh, registration, context, now=datetime.now(UTC))
            assert positive.status == "OBSERVED_CANDIDATE"
            assert positive.admission_status == "NOT_ADMITTED"
            changed = module._descriptor_plain(frozen)
            changed["source_identity"] = "0" * 64
            assert (
                associate_marker_target(
                    fresh,
                    registration,
                    replace(context, operational_reference=changed),
                    now=datetime.now(UTC),
                ).status
                != "OBSERVED_CANDIDATE"
            )
            legacy_context = replace(context, operational_reference=None)
            legacy_body = {
                name: getattr(legacy_context, name)
                for name in legacy_context.__dataclass_fields__
                if name != "operational_reference"
            }
            assert legacy_context.digest() == marker._digest(legacy_body)
        raw.now = 5_000_000_000
        assert module._check_reference(reference).status == "VALID"
        raw.now += 1
        assert module._check_reference(reference).status == "INVALID"
        if category == "marker":
            assert (
                associate_marker_target(fresh, registration, context, now=datetime.now(UTC)).status
                != "OBSERVED_CANDIDATE"
            )
        rebound = {**reference, "job_id": "foreign-job"}
        assert module._check_reference(rebound).status == "UNKNOWN"

    exercise(
        monkeypatch,
        tmp_path,
        run,
        startup_parameters={"supervision_period_ms": 0.001} if category == "supervision" else None,
    )


def test_public_replay_descriptor_never_live_authority(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        usable_plan(runtime, observation)
        from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
            InMemoryEventAutonomyRepository,
        )
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
            VisualBootstrapDefinition,
            VisualBootstrapRecord,
            VisualBootstrapTransitionInput,
            derive_bootstrap,
        )
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
            VisualSupervisionDefinition,
        )
        from tests.test_visual_supervision_repository import definition, initialize

        original = runtime.bootstrap
        detached = VisualBootstrapRecord.from_json(original.to_json())
        assert detached.to_json() == original.to_json()
        historical_definition = VisualBootstrapDefinition.from_payload(
            frozen_json(original.definition.to_payload())
        )
        assert historical_definition.digest() == original.definition.digest()
        history = original.to_payload()["history"]
        request = VisualBootstrapTransitionInput.from_payload(frozen_json(history[-1]["request"]))
        references = request.to_payload()["operational_windows"]
        assert references
        result = derive_bootstrap(detached, request, now=datetime.now(UTC))
        assert result.write_disposition == "HISTORICAL_DUPLICATE"
        payload = request.to_payload()
        payload["event_key"] = "public-forged-new-transition"
        copied = VisualBootstrapTransitionInput.from_payload(payload)
        with pytest.raises(OperationalTimeError):
            derive_bootstrap(detached, copied, now=datetime.now(UTC))

        # Compare legacy no-new-field output to independently frozen pre-P5 codec.
        legacy_arguments = {
            field.name: getattr(original.definition, field.name)
            for field in fields(original.definition)
            if field.init and field.name != "operational_windows"
        }
        legacy = VisualBootstrapDefinition(**legacy_arguments)
        old_bootstrap = legacy_codec("visual_bootstrap")
        old_legacy = old_bootstrap["VisualBootstrapDefinition"](**legacy_arguments)
        assert legacy.to_payload() == old_legacy.to_payload()
        assert legacy.digest() == old_legacy.digest()
        assert VisualBootstrapRecord.start(legacy).to_json() == (
            old_bootstrap["VisualBootstrapRecord"].start(old_legacy).to_json()
        )
        repo = InMemoryEventAutonomyRepository()
        try:
            data = initialize(repo)
            legacy_supervision = definition(data)
            legacy_payload = legacy_supervision.to_payload()
            old_supervision = legacy_codec("visual_supervision")
            old_definition = old_supervision["VisualSupervisionDefinition"].from_payload(
                legacy_payload
            )
            assert legacy_supervision.to_payload() == old_definition.to_payload()
            assert legacy_supervision.digest() == old_definition.digest()
            assert legacy_supervision._json == old_definition._json
            described = {**legacy_payload, "operational_windows": references}
            immutable = VisualSupervisionDefinition.from_payload(frozen_json(described))
            roundtrip = VisualSupervisionDefinition.from_payload(
                json.loads(module._json(described))
            )
            assert immutable.to_payload() == roundtrip.to_payload()
            assert immutable.digest() == roundtrip.digest()
        finally:
            repo.close()
        return references[0]

    reference, _, _ = exercise(monkeypatch, tmp_path, run)
    assert api()._check_reference(frozen_json(reference)).status == "UNKNOWN"
    assert api()._check_reference(json.loads(json.dumps(reference))).status == "UNKNOWN"


def test_utc_lease_guard_remains_independent(monkeypatch, tmp_path):
    def run(module, runtime, raw, worker, repo, job):
        owner = runtime._operational_owner
        assert owner.check(owner.task_window, after=owner.task_origin_token).status == "VALID"
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute(
                "UPDATE simulation_jobs SET lease_expires_at=? WHERE job_id=?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), job.job_id),
            )
        assert owner.check(owner.task_window, after=owner.task_origin_token).status == "UNKNOWN"

    exercise(monkeypatch, tmp_path, run)


def test_foreign_thread_has_no_owner_context(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        results = []
        context = copy_context()
        thread = threading.Thread(
            target=lambda: results.append(context.run(module._check_reference, reference))
        )
        thread.start()
        thread.join()
        assert results[0].status == "UNKNOWN"
        assert module._check_reference(reference).status == "VALID"

    exercise(monkeypatch, tmp_path, run)


def test_parent_age_closed_boundary_and_no_refresh(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        _, acquisition = event(owner)
        parent = owner.issue("capture", acquisition, budget_ns=5_000_000_000, parent_ids=())
        original = owner.export_record(parent)
        raw.now = 2_000_000_000
        token, reply = event(owner, "plan")
        child = owner.issue("plan", reply, budget_ns=5_000_000_000, parent_ids=(parent,))
        raw.now = 5_000_000_000
        assert owner.check(child, after=token).status == "VALID"
        assert owner.export_record(parent) == original
        assert len(owner.export_record(child)["age_constraints"]) == 2
        raw.now += 1
        assert owner.check(child, after=token).status == "INVALID"

    exercise(monkeypatch, tmp_path, run)


def test_window_export_preserves_typed_boundary_constraints(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        from cloud_edge_robot_arm.edge.evidence.models import VisualEvidence

        owner = runtime._operational_owner
        token, receipt = event(owner)
        parent = owner.issue("bootstrap", owner.task_origin, budget_ns=5_000_000_000, parent_ids=())
        window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=(parent,))
        record = owner.export_record(window)
        assert record["budget_semantics"] == "AGE_CLOSED"
        assert record["deadline_semantics"] == "HARD_OPEN"
        assert record["age_constraints"][0]["upper_age_inclusive"] is True
        assert all(h["end_exclusive"] for h in record["hard_deadlines"])
        assert record["effective_upper"] == {"value_ns": 5_000_000_000, "inclusive": False}
        assert all(a["source_id"] and a["event_id"] for a in record["age_constraints"])
        immutable = frozen_json(record)
        assert module._json(immutable) == module._json(record)
        module._validate_references((immutable,))
        evidence = VisualEvidence(
            "cpu-descriptor",
            "cpu-calibration",
            datetime.now(UTC),
            None,
            None,
            "UNKNOWN",
            "VALID",
            operational_reference=record,
        )
        assert isinstance(evidence.operational_reference, MappingProxyType)
        assert module._check_reference(evidence.operational_reference).status == "VALID"
        assert module._check_reference(immutable).status == "VALID"
        malformed = []
        limits = {
            "native_authority": ("UNAVAILABLE", "AVAILABLE"),
            "future_horizon": ("UNKNOWN", "FINITE_CERTIFIED"),
            "restart_suspend_hostpause": ("NOT_TESTED_OC3_GATE", "VALIDATED"),
        }
        for key, (original_value, forged_value) in limits.items():
            assert record["domain"][key] == original_value
            missing = copy.deepcopy(record)
            del missing["domain"][key]
            malformed.append(missing)
            for value in (forged_value, True):
                changed = copy.deepcopy(record)
                changed["domain"][key] = value
                malformed.append(changed)
        extra = copy.deepcopy(record)
        extra["domain"]["unknown_extra_field"] = "UNAVAILABLE"
        malformed.append(extra)
        for key, value in (("attempt", True), ("budget_ns", True), ("budget_ns", 2.5)):
            changed = copy.deepcopy(record)
            changed[key] = value
            malformed.append(changed)
        for key, value in (
            ("lower_ns", True),
            ("upper_ns", 0.5),
            ("upper_age_inclusive", 1),
            ("expiry_upper_ns", 1),
        ):
            changed = copy.deepcopy(record)
            changed["age_constraints"][0][key] = value
            malformed.append(changed)
        for key, value in (("end_exclusive", 1), ("budget_ns", True), ("deadline_ns", 1.5)):
            changed = copy.deepcopy(record)
            changed["hard_deadlines"][0][key] = value
            malformed.append(changed)
        for key, value in (("pid", True), ("startup_counter_ns", 0.5)):
            changed = copy.deepcopy(record)
            changed["domain"][key] = value
            malformed.append(changed)
        changed = copy.deepcopy(record)
        changed["effective_upper"]["inclusive"] = True
        malformed.append(changed)
        for changed in malformed:
            with pytest.raises(ValueError):
                module._validate_references([changed])
            assert module._check_reference(frozen_json(changed)).status == "UNKNOWN"
        for changed in ({**record, "window_id": "forged"}, {**record, "budget_ns": 1}):
            assert module._check_reference(changed).status == "UNKNOWN"
        for bad in (float("nan"), float("inf"), float("-inf"), object(), b"bytes", {1: "key"}):
            with pytest.raises(ValueError):
                module._json({"value": bad})
        cycle = []
        cycle.append(cycle)
        with pytest.raises(ValueError):
            module._json(cycle)
        alias = {"valid": [None, True, 1, 1.5, "文本"]}
        assert module._json([alias, alias]) == json.dumps(
            [alias, alias], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        with pytest.raises(OperationalTimeError):
            owner.issue("capture", receipt, budget_ns=5_000_000_001, parent_ids=())
        assert owner.check(window, after=token).status == "VALID"
        return json.loads(json.dumps(record))

    reference, _, _ = exercise(monkeypatch, tmp_path, run)
    assert api()._check_reference(reference).status == "UNKNOWN"


def test_nonzero_bracket_age_uses_original_lower_boundary(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        owner = runtime._operational_owner
        raw.now = 10
        token = owner.clock.begin_event("capture")
        raw.now = 15
        owner.clock.mark_event(token)
        raw.now = 20
        receipt = owner.clock.end_event(token)
        window = owner.issue("capture", receipt, budget_ns=5_000_000_000, parent_ids=())
        raw.now = 5_000_000_010
        assert owner.check(window, after=token).status == "VALID"
        raw.now += 1
        assert owner.check(window, after=token).status == "INVALID"

    exercise(monkeypatch, tmp_path, run)
