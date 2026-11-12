"""Production preparation and strict current readout, using disposable source records."""

import importlib.util
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.evidence import conditions
from cloud_edge_robot_arm.edge.recovery.lifecycle import checkpoint_digest
from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api
from cloud_edge_robot_arm.research import native_collection_application as application
from cloud_edge_robot_arm.research import native_full_horizon_originals as reader
from cloud_edge_robot_arm.research.native_calibration_collection import digest, load_json
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision import owner_registration as owner
from cloud_edge_robot_arm.vision import registered_object_tracking, tracking, worker_owner
from tests.test_registered_object_geometry import frame, revised
from tests.test_registered_object_tracking import later
from tests.test_visual_owner_registration import values

ROOT = Path(__file__).resolve().parents[1]


def context(tmp_path, monkeypatch, skill=SkillName.MOVE_ABOVE):
    repository = SQLiteSimulationJobRepository(tmp_path / "source.db")
    job = repository.create_job(
        run_id="registered-source",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="CLOUD",
        seed=0,
        manifest_id="software",
        reproducibility_hash="a" * 64,
        draft={},
        timeout_seconds=120,
        max_attempts=1,
        artifact_root="software",
        source_commit="software",
        source_tree_hash="b" * 64,
    )
    repository.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="software",
        worker_id="",
        lease_id="",
    )
    lease = repository.acquire_lease(
        worker_id="registered-worker", backend="MUJOCO", lease_ttl_seconds=60
    )
    assert lease is not None
    repository.start_attempt(job.job_id, worker_id=lease.worker_id)
    for old, new in (
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ):
        assert repository.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="software",
            worker_id=lease.worker_id,
            lease_id=lease.lease_id,
            expected_lease_id=lease.lease_id,
        )
    stamp = datetime.now(UTC)
    clock = [stamp]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return clock[0]

    for module in (application, reader, registered_object_tracking, tracking, worker_owner):
        monkeypatch.setattr(module, "datetime", Clock)
    ref, _ = frame()
    ref = revised(ref, captured_at=stamp)
    current = later(ref, fragment=True)
    protocol = tmp_path / "protocol"
    protocol_api.prepare_registered_grounding_protocol(output=protocol)
    registration = protocol_api.read_protocol(protocol)
    lease_source = worker_owner.read_visual_worker_lease(
        repository,
        job_id=job.job_id,
        run_id=job.run_id,
        worker_id=lease.worker_id,
        lease_id=lease.lease_id,
    )
    before = values()
    contract = before["original"].contract
    step = contract.steps[0].model_copy(
        update={"skill": skill, "parameters": {"object_id": "object"}}, deep=True
    )
    target = contract.task_target.model_copy(
        update={"object_id": "object", "target_region_id": "target_region"}
    )
    contract = contract.model_copy(
        update={
            "steps": [step],
            "task_target": target,
            "timestamp": stamp,
            "issued_at": stamp,
            "valid_until": stamp + timedelta(seconds=40),
        },
        deep=True,
    )
    identity = lease_source.identity(
        episode_id=ref.episode_id,
        task_id=contract.task_id,
        plan_id="registered-plan",
        robot_id="registered-robot",
    )
    original = worker_owner.compile_worker_original_plan(
        lease_source=lease_source,
        identity=identity,
        contract=contract,
        observation=ref,
        proposal_hash="b" * 64,
        role_bundle_hash="c" * 64,
        source_hashes=registration["source_hashes"],
        registered_at=stamp,
        task_deadline_at=stamp + timedelta(seconds=35),
        verification_deadline_at=stamp + timedelta(seconds=30),
    )
    state = before["online"].robot_state
    cp = before["source_checkpoint"].model_copy(
        update={
            "plan_id": identity.plan_id,
            "robot_id": identity.robot_id,
            "pending_step_ids": ["move"],
            "created_at": stamp,
            "updated_at": stamp,
            "robot_state": state.model_dump(mode="json"),
            "checkpoint_hash": "",
        },
        deep=True,
    )
    cp = cp.model_copy(update={"checkpoint_hash": checkpoint_digest(cp)})
    clock[0] = current.captured_at
    args = dict(
        repository=repository,
        original=original,
        source_checkpoint=cp,
        reference_observation=ref,
        observation=current,
        robot_state=state,
        owner_revision=1,
        state_generation=2,
    )
    return protocol, args, clock


def prepare(tmp_path, monkeypatch, skill=SkillName.MOVE_ABOVE):
    protocol, args, clock = context(tmp_path, monkeypatch, skill)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "prepared"
    result = app.prepare_step(**args, output=output)
    record = output / "prepared-step.json"
    return protocol, args, clock, result, record


def test_application_protocol_and_consumer_api_exist():
    assert hasattr(protocol_api, "prepare_registered_grounding_protocol"), "v6 protocol missing"
    assert hasattr(application, "RegisteredGroundingPreparationApplication"), (
        "preparation application missing"
    )


@pytest.mark.parametrize("skill", [SkillName.MOVE_ABOVE, SkillName.APPROACH])
def test_application_real_joined_source_prepares_without_promoting_visibility(
    tmp_path, monkeypatch, skill
):
    protocol, args, _, result, record = prepare(tmp_path, monkeypatch, skill)
    p = protocol_api.read_protocol(protocol)
    assert p["schema_version"] == "native.calibration.operational.v6"
    assert p["assignments"] == [] and p["released_assignments"] == []
    assert all(value == 0 for value in p["authorized_actual_budget"].values())
    assert result["status"] == "PREPARED_CANDIDATE" and result["execution_admitted"] is False
    payload = load_json(record)["content"]
    admission = payload["admission"]
    assert admission["candidate_ready"] is True and admission["execution_admitted"] is False
    assert admission["unknown_allowance_rows"] == []
    assert admission["pose_verdict"]["status"] == "PASS"
    visible = next(v for v in admission["preconditions"] if v["condition_name"] == "target_visible")
    reachable = next(
        v for v in admission["preconditions"] if v["condition_name"] == "target_reachable"
    )
    assert visible["status"] == reachable["status"] == "UNKNOWN"
    assert "protocol_prepare_only_not_released" in admission["blockers"]
    assert payload["binding"]["grounded_step"]["skill"] == skill.value
    grasp_z = payload["inputs"]["grasp_tcp_world_m"][2]
    expected_z = max(0.16, grasp_z + 0.10) if skill == SkillName.MOVE_ABOVE else grasp_z
    assert payload["binding"]["grounded_step"]["parameters"]["target_pose"]["z"] == expected_z
    assert args["repository"].get_job(args["original"].identity.job_id).attempt == 1
    assert not (protocol / "claims").exists()


@pytest.mark.parametrize("change", ["budget", "release", "schema", "extra", "basis"])
def test_application_protocol_rejects_resealed_authority_and_downgrade(tmp_path, change):
    output = tmp_path / "protocol"
    protocol_api.prepare_registered_grounding_protocol(output=output)
    payload = load_json(output / "protocol.json")
    if change == "budget":
        payload["authorized_actual_budget"]["teacher"] = 1
    elif change == "release":
        payload["execution_release"] = "RELEASED"
    elif change == "schema":
        payload["schema_version"] = "native.calibration.operational.v2"
    elif change == "basis":
        payload["geometry_basis"] = "MEASURED"
    else:
        payload["extra"] = True
    (output / "protocol.json").write_text(json.dumps(payload))
    with pytest.raises((ValueError, TypeError)):
        protocol_api.read_protocol(output)


@pytest.mark.parametrize("fault", ["missing", "incomplete", "left_cut"])
def test_application_unavailable_region_retains_unknown_without_candidate(
    tmp_path, monkeypatch, fault
):
    protocol, args, clock = context(tmp_path, monkeypatch)
    current = later(
        args["reference_observation"], region="missing" if fault == "missing" else "incomplete"
    )
    if fault == "left_cut":
        from tests.test_registered_object_tracking import cut_region

        current = cut_region(args["reference_observation"], "left")
    args["observation"] = current
    clock[0] = current.captured_at
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "unknown"
    result = app.prepare_step(**args, output=output)
    payload = load_json(output / "prepared-step.json")["content"]
    assert result["status"] == "PREPARATION_UNKNOWN"
    assert payload["inputs"] is None and payload["binding"] is None
    assert payload["preview"]["grasp_tcp_world_m"] is None
    assert payload["admission"]["candidate_ready"] is False


def test_application_refuses_cancelled_source_before_output(tmp_path, monkeypatch):
    protocol, args, _ = context(tmp_path, monkeypatch)
    args["repository"].request_cancel(args["original"].identity.job_id)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "never"
    with pytest.raises(ValueError):
        app.prepare_step(**args, output=output)
    assert not output.exists()


def test_application_old_factory_and_old_condition_registry_still_refuse(tmp_path):
    protocol = tmp_path / "protocol"
    protocol_api.prepare_registered_grounding_protocol(output=protocol)
    output = tmp_path / "never"
    with pytest.raises(ValueError, match="prepare-only"):
        application.NativeCollectionApplication.from_startup(
            protocol, assignment_id="none", output=output
        )
    assert not output.exists() and not (protocol / "claims").exists()


@pytest.mark.parametrize("failure", ["cancel", "expiry", "write"])
def test_application_checks_final_boundaries_and_does_not_return_success(
    tmp_path, monkeypatch, failure
):
    from cloud_edge_robot_arm.research import native_collection_grounding as grounding

    protocol, args, clock = context(tmp_path, monkeypatch)
    original_preview = grounding.registered_collection_grounding_preview_v1

    def changed_after_preview(*a, **kw):
        result = original_preview(*a, **kw)
        if failure == "cancel":
            args["repository"].request_cancel(args["original"].identity.job_id)
        elif failure == "expiry":
            clock[0] += timedelta(seconds=5.01)
        return result

    monkeypatch.setattr(
        grounding, "registered_collection_grounding_preview_v1", changed_after_preview
    )
    if failure == "write":

        def failed_write(*a, **kw):
            raise OSError("disposable output unavailable")

        monkeypatch.setattr(application, "save_exclusive", failed_write)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    with pytest.raises((ValueError, OSError)):
        app.prepare_step(**args, output=tmp_path / "refused")
    assert not (tmp_path / "refused/prepared-step.json").exists()


def test_application_pose_only_inputs_do_not_change_legacy_conditions(tmp_path, monkeypatch):
    _, args, _, _, record = prepare(tmp_path, monkeypatch)
    payload = load_json(record)["content"]
    online = conditions.OnlineEvidenceSnapshot(
        args["observation"], args["robot_state"], {"target_visible": payload["inputs"]}
    )
    verdicts = conditions.evaluate_conditions(
        [
            conditions.ConditionSpec("target_visible", "object"),
            conditions.ConditionSpec("registered_object_pose_available", "object"),
        ],
        online,
        now=args["observation"].captured_at,
    )
    assert [v.status for v in verdicts] == ["UNKNOWN", "UNKNOWN"]


def test_application_alias_output_and_legacy_full_horizon_mode_refuse(tmp_path, monkeypatch):
    protocol, args, _ = context(tmp_path, monkeypatch)
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    with pytest.raises(ValueError):
        app.prepare_step(**args, output=alias / "never")
    with pytest.raises(ValueError, match="current-frame"):
        protocol_api.verify_native_calibration_collection(protocol, output=tmp_path / "legacy")
    assert not (tmp_path / "never").exists() and not (tmp_path / "legacy").exists()


def test_reader_api_exists():
    assert hasattr(reader, "verify_registered_prepared_step"), "strict preparation reader missing"


def test_reader_reconstructs_actual_production_record_and_legacy_decoder_refuses(
    tmp_path, monkeypatch
):
    protocol, args, _, _, record = prepare(tmp_path, monkeypatch)
    result = reader.verify_registered_prepared_step(
        protocol, record, repository=args["repository"], source_root=ROOT, output=tmp_path / "read"
    )
    assert result["status"] == "PREPARED_CANDIDATE_RECONSTRUCTED"
    assert result["execution_admitted"] is False and result["formal"] == "NOT_ACCEPTED"
    assert result["binding_sha256"] == digest(load_json(record)["content"]["binding"])
    from cloud_edge_robot_arm.research.raw_episode_v3 import _owner_decode
    from cloud_edge_robot_arm.vision.owner_registration import StepGroundingBinding

    with pytest.raises((ValueError, TypeError)):
        _owner_decode(StepGroundingBinding, load_json(record)["content"]["binding"])


@pytest.mark.parametrize(
    "change",
    [
        "candidate",
        "bound",
        "basis",
        "source",
        "checkpoint",
        "epoch",
        "policy",
        "time",
        "admission",
    ],
)
def test_reader_rejects_resealed_tampering(tmp_path, monkeypatch, change):
    protocol, args, _, _, record = prepare(tmp_path, monkeypatch)
    envelope = load_json(record)
    payload = envelope["content"]
    if change == "candidate":
        payload["binding"]["grounded_step"]["parameters"]["target_pose"]["x"] += 0.2
    elif change == "bound":
        payload["inputs"]["geometric_error_bound_m"] = 0.001
    elif change == "basis":
        payload["inputs"]["geometry_basis"] = "MEASURED"
    elif change == "source":
        payload["inputs"]["asset_sha256"] = "e" * 64
    elif change == "checkpoint":
        payload["context"]["source_checkpoint"]["command_seq"] += 1
    elif change == "epoch":
        payload["binding"]["current_identity"]["owner_epoch"] = "e" * 64
    elif change == "policy":
        payload["policy"]["clearance_m"] = 0.01
    elif change == "time":
        payload["binding"]["created_at"] = (
            args["observation"].captured_at - timedelta(seconds=1)
        ).isoformat()
    else:
        payload["admission"]["execution_admitted"] = True
    envelope["content_sha256"] = digest(payload)
    record.write_text(json.dumps(envelope))
    with pytest.raises((ValueError, TypeError)):
        reader.verify_registered_prepared_step(
            protocol,
            record,
            repository=args["repository"],
            source_root=ROOT,
            output=tmp_path / "refused",
        )
    assert not (tmp_path / "refused").exists()


def test_reader_current_expiry_refuses_without_time_rewind(tmp_path, monkeypatch):
    protocol, args, clock, _, record = prepare(tmp_path, monkeypatch)
    clock[0] = args["observation"].captured_at + timedelta(seconds=5.01)
    with pytest.raises(ValueError, match="stale|expired|fresh"):
        reader.verify_registered_prepared_step(
            protocol,
            record,
            repository=args["repository"],
            source_root=ROOT,
            output=tmp_path / "stale",
        )
    assert not (tmp_path / "stale").exists()


def test_cli_calls_protocol_prepare_and_strict_reader_in_process(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "registered_cli", ROOT / "scripts/collect_native_calibration.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(
        sys,
        "argv",
        ["collect", "--prepare-registered-protocol", "--output", str(tmp_path / "cli-protocol")],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "REGISTERED_PROTOCOL_PREPARED"
    protocol, args, _ = context(tmp_path, monkeypatch)
    from cloud_edge_robot_arm.research.native_calibration_collection import detached

    ctx = tmp_path / "context.json"
    ctx.write_text(json.dumps({k: detached(v) for k, v in args.items() if k != "repository"}))
    common = ["--protocol", str(protocol), "--repository", str(args["repository"].database_path)]
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--prepare-registered-step",
            *common,
            "--context",
            str(ctx),
            "--output",
            str(tmp_path / "cli-prepare"),
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["execution_admitted"] is False
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "collect",
            "--verify-registered-step",
            *common,
            "--prepared",
            str(tmp_path / "cli-prepare/prepared-step.json"),
            "--output",
            str(tmp_path / "cli-read"),
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "PREPARED_CANDIDATE_RECONSTRUCTED"


@pytest.mark.parametrize("consumer", ["app", "reader"])
@pytest.mark.parametrize("limit", ["frame", "lease"])
def test_review_i1_final_join_rechecks_real_time(tmp_path, monkeypatch, consumer, limit):
    if consumer == "app":
        protocol, args, clock = context(tmp_path, monkeypatch)
        app = application.RegisteredGroundingPreparationApplication.from_protocol(
            protocol, source_root=ROOT
        )
    else:
        protocol, args, clock, _, record = prepare(tmp_path, monkeypatch)
    if limit == "lease":
        from cloud_edge_robot_arm.simulation_runtime import sqlite_repository as sqlite_source

        monkeypatch.setattr(sqlite_source, "_now", lambda: clock[0])
        args["repository"].heartbeat_lease(args["original"].identity.lease_id, lease_ttl_seconds=1)
    module = application if consumer == "app" else worker_owner
    genuine = module.read_visual_worker_lease
    calls = []

    def waiting_join(*a, **kw):
        calls.append("now" in kw)
        result = genuine(*a, **kw)
        if len(calls) == 2:
            clock[0] = (
                clock[0] + timedelta(seconds=5.01)
                if limit == "frame"
                else result.expires_at + timedelta(seconds=0.001)
            )
            if limit == "lease":
                assert (clock[0] - args["observation"].captured_at).total_seconds() < 5
        return result

    monkeypatch.setattr(module, "read_visual_worker_lease", waiting_join)
    output = tmp_path / "join-refused"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        if consumer == "app":
            app.prepare_step(**args, output=output)
        else:
            reader.verify_registered_prepared_step(
                protocol, record, repository=args["repository"], source_root=ROOT, output=output
            )
    assert not any(calls), "owning production APIs must not supply cached now to lease joins"
    assert not output.exists()


def short_original(args, *, condition_ttl=None, deadline=None):
    original = args["original"]
    changes = {}
    if condition_ttl is not None:
        requirements = {}
        for name, requirement in original.requirements.items():

            def changed(c):
                return replace(c, tolerances={**c.tolerances, "max_age_s": condition_ttl})

            requirements[name] = replace(
                requirement,
                preconditions=tuple(changed(c) for c in requirement.preconditions),
                postconditions=tuple(changed(c) for c in requirement.postconditions),
            )
        changes["requirements"] = requirements
    if deadline is not None:
        changes["verification_deadline_at"] = deadline
    args["original"] = owner.freeze_original_visual_plan(**{**original.freeze_inputs(), **changes})


@pytest.mark.parametrize(
    "boundary", ["admission", "serialization", "reader_rebuild", "reader_admission"]
)
def test_review_i1_late_validation_rechecks_deadline(tmp_path, monkeypatch, boundary):
    protocol, args, clock = context(tmp_path, monkeypatch)
    short_original(args, deadline=clock[0] + timedelta(seconds=0.15))
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    if boundary.startswith("reader"):
        app.prepare_step(**args, output=tmp_path / "valid")
        if boundary == "reader_rebuild":
            genuine = owner.prepare_registered_step_binding
            calls = [0]

            def slow_rebuild(*a, **kw):
                result = genuine(*a, **kw)
                calls[0] += 1
                if calls[0] == 2:
                    clock[0] += timedelta(seconds=0.2)
                return result

            monkeypatch.setattr(owner, "prepare_registered_step_binding", slow_rebuild)
        else:
            genuine = application.registered_preparation_admission

            def slow_admission(*a, **kw):
                result = genuine(*a, **kw)
                clock[0] += timedelta(seconds=0.2)
                return result

            monkeypatch.setattr(application, "registered_preparation_admission", slow_admission)
    elif boundary == "admission":
        genuine = application.registered_preparation_admission

        def slow_admission(*a, **kw):
            result = genuine(*a, **kw)
            clock[0] += timedelta(seconds=0.2)
            return result

        monkeypatch.setattr(application, "registered_preparation_admission", slow_admission)
    else:
        genuine = application._registered_context_payload
        calls = [0]

        def slow_materialization(*a, **kw):
            result = genuine(*a, **kw)
            calls[0] += 1
            if calls[0] == 2:
                clock[0] += timedelta(seconds=0.2)
            return result

        monkeypatch.setattr(application, "_registered_context_payload", slow_materialization)
    output = tmp_path / "late-refused"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        if boundary.startswith("reader"):
            reader.verify_registered_prepared_step(
                protocol,
                tmp_path / "valid/prepared-step.json",
                repository=args["repository"],
                source_root=ROOT,
                output=output,
            )
        else:
            app.prepare_step(**args, output=output)
    assert not output.exists()


def test_review_i2_rejects_future_frame_before_processing_catches_up(tmp_path, monkeypatch):
    protocol, args, clock = context(tmp_path, monkeypatch)
    args["observation"] = revised(
        args["observation"], captured_at=clock[0] + timedelta(seconds=0.02)
    )
    genuine = application.read_visual_worker_lease
    calls = [0]

    def catching_up(*a, **kw):
        result = genuine(*a, **kw)
        calls[0] += 1
        if calls[0] == 1:
            clock[0] += timedelta(seconds=0.03)
        return result

    monkeypatch.setattr(application, "read_visual_worker_lease", catching_up)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "future-refused"
    with pytest.raises(ValueError, match="future|fresh|deadline"):
        app.prepare_step(**args, output=output)
    assert calls[0] == 0 and not output.exists()


def authentic_unknown(tmp_path, monkeypatch, limit=None):
    protocol, args, clock = context(tmp_path, monkeypatch)
    args["observation"] = later(args["reference_observation"], region="missing")
    if limit == "ttl":
        short_original(args, condition_ttl=0.2)
    elif limit == "absolute":
        short_original(args, deadline=clock[0] + timedelta(seconds=0.2))
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    app.prepare_step(**args, output=tmp_path / "unknown-valid")
    return protocol, args, clock, tmp_path / "unknown-valid/prepared-step.json"


def test_review_i3_authentic_unknown_reconstructs_before_deadline(tmp_path, monkeypatch):
    protocol, args, _, record = authentic_unknown(tmp_path, monkeypatch)
    result = reader.verify_registered_prepared_step(
        protocol,
        record,
        repository=args["repository"],
        source_root=ROOT,
        output=tmp_path / "unknown-read",
    )
    assert result["status"] == "PREPARATION_UNKNOWN_RECONSTRUCTED"
    assert result["execution_admitted"] is False and result["native_authority"] == "UNAVAILABLE"


@pytest.mark.parametrize("limit", ["ttl", "absolute"])
def test_review_i3_unknown_entry_deadline_refuses(tmp_path, monkeypatch, limit):
    protocol, args, clock, record = authentic_unknown(tmp_path, monkeypatch, limit)
    clock[0] += timedelta(seconds=0.21)
    output = tmp_path / "unknown-expired"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        reader.verify_registered_prepared_step(
            protocol, record, repository=args["repository"], source_root=ROOT, output=output
        )
    assert not output.exists()


def test_review_i3_unknown_final_deadline_refuses(tmp_path, monkeypatch):
    protocol, args, clock, record = authentic_unknown(tmp_path, monkeypatch, "ttl")
    genuine = worker_owner.read_visual_worker_lease
    calls = [0]

    def late_unknown_join(*a, **kw):
        result = genuine(*a, **kw)
        calls[0] += 1
        if calls[0] == 2:
            clock[0] += timedelta(seconds=0.21)
        return result

    monkeypatch.setattr(worker_owner, "read_visual_worker_lease", late_unknown_join)
    output = tmp_path / "unknown-final-expired"
    with pytest.raises(ValueError, match="stale|expired|deadline|fresh"):
        reader.verify_registered_prepared_step(
            protocol, record, repository=args["repository"], source_root=ROOT, output=output
        )
    assert not output.exists()


@pytest.mark.parametrize("value", [True, 0])
def test_review_i3_unknown_never_coerces_condition_ttl(tmp_path, monkeypatch, value):
    protocol, args, _ = context(tmp_path, monkeypatch)
    args["observation"] = later(args["reference_observation"], region="missing")
    short_original(args, condition_ttl=value)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    output = tmp_path / "invalid-ttl"
    with pytest.raises(ValueError):
        app.prepare_step(**args, output=output)
    assert not output.exists()


def test_review_normal_nonzero_times_are_honest_and_readable(tmp_path, monkeypatch):
    protocol, args, clock = context(tmp_path, monkeypatch)
    genuine_join = application.read_visual_worker_lease
    genuine_admission = application.registered_preparation_admission

    def nonzero_join(*a, **kw):
        clock[0] += timedelta(seconds=0.01)
        result = genuine_join(*a, **kw)
        clock[0] += timedelta(seconds=0.01)
        return result

    def nonzero_admission(*a, **kw):
        result = genuine_admission(*a, **kw)
        clock[0] += timedelta(seconds=0.01)
        return result

    monkeypatch.setattr(application, "read_visual_worker_lease", nonzero_join)
    monkeypatch.setattr(application, "registered_preparation_admission", nonzero_admission)
    app = application.RegisteredGroundingPreparationApplication.from_protocol(
        protocol, source_root=ROOT
    )
    app.prepare_step(**args, output=tmp_path / "nonzero")
    record = tmp_path / "nonzero/prepared-step.json"
    p = load_json(record)["content"]
    parse = datetime.fromisoformat
    assert (
        parse(p["started_at"])
        < parse(p["lease_before"]["observed_at"])
        < parse(p["lease_after"]["observed_at"])
        < parse(p["evaluated_at"])
        < parse(p["finished_at"])
    )
    assert p["binding"]["created_at"] == p["evaluated_at"]
    result = reader.verify_registered_prepared_step(
        protocol,
        record,
        repository=args["repository"],
        source_root=ROOT,
        output=tmp_path / "nonzero-read",
    )
    assert result["status"] == "PREPARED_CANDIDATE_RECONSTRUCTED"
