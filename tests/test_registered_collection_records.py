"""Separate collection records and recorded-time computation never confer live authority."""

import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta

import pytest

from cloud_edge_robot_arm.research import native_archived_tracker as archived
from cloud_edge_robot_arm.research import native_collection_grounding as collection
from cloud_edge_robot_arm.research import raw_episode_v3 as raw
from cloud_edge_robot_arm.vision import owner_registration as owner
from tests.test_registered_grounding_binding import binding_data
from tests.test_registered_object_tracking import ROOT, STAMP, environment, later
from tests.test_visual_owner_registration import values


@contextmanager
def dispatch_context(tmp_path, monkeypatch):
    """Real SQL/owner, recorder, runner and executor seam; synthetic camera only."""
    import base64
    import io
    import time
    from types import SimpleNamespace

    from PIL import Image

    from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
    from cloud_edge_robot_arm.research import native_collection_application as api
    from cloud_edge_robot_arm.research.native_calibration_collection import canonical, digest
    from cloud_edge_robot_arm.simulation.models import SensorFrame
    from cloud_edge_robot_arm.simulation.mujoco.native_horizon import _issue_collection_session
    from tests.test_native_collection_authority import application, source_recorder
    from tests.test_registered_collection_execution import consumer_context

    _, _, prepared_live, protocol, args, clock, _, _ = consumer_context(
        tmp_path / "context", monkeypatch
    )
    app = application(tmp_path / "application")
    app.prepare_once()  # Genuine disposable owner origin, never the v7 public factory.
    live = api._REGISTRY[app]
    recorder, backend, capture, unused_owner, _ = source_recorder(tmp_path / "recorder")
    unused_owner.close()
    repository = args["repository"]
    job = repository.get_job(args["original"].identity.job_id)
    app.repository = live.repository = live.worker.repository = repository
    live.worker.worker_id = job.worker_id
    live.worker.active_job_id = live.job_id = job.job_id
    live.worker_origin = (job.job_id, time.monotonic(), clock[0])
    live.worker._active_task_origin = live.worker_origin
    live.job_basis = api._job_basis(job)
    # Test-only internal consumer setup; the real v7 startup rejection remains tested.
    live.protocol_json = canonical(protocol)
    live.entered = True
    live.original = args["original"]
    live.tracker = prepared_live.tracker
    live.registered_tracker = prepared_live.registered_tracker
    live.grounding_evidence = prepared_live.grounding_evidence
    live.recorder = recorder
    live.backend = backend
    live.capture = capture
    live.executor = recorder.executor
    live.robot = recorder.executor._robot
    # The software backend has no MuJoCo kinematics; use the complete source state.
    monkeypatch.setattr(live.robot, "get_state", lambda: args["robot_state"])
    recorder.application, recorder.owner = app, live.owner
    recorder.source_root, recorder.source_hashes = ROOT, dict(protocol["source_hashes"])
    observation = args["observation"]
    backend._episode_id = observation.episode_id
    backend._total_physics_steps = round(observation.sim_time_s * 240)
    backend._data.time = observation.sim_time_s
    pixels = Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))).tobytes()
    depths = observation.depth_values()
    number = [0]

    def synthetic_camera(data, **_kwargs):
        number[0] += 1
        frame = SensorFrame(
            frame_id=f"registered-software-{number[0]}",
            sim_time_s=backend.get_sim_time(),
            width=observation.width,
            height=observation.height,
            rgb=pixels,
            depth=depths,
            intrinsics=tuple(observation.intrinsics),
            camera_to_world=tuple(observation.camera_to_world),
            captured_at=clock[0],
            episode_id=observation.episode_id,
            scene_id=observation.scene_id,
            calibration_version=observation.calibration_version,
            valid_mask=observation.valid_mask_bytes(),
        )
        return frame, (-1,) * len(depths), {-1: "background"}, ("a" * 64,) * 3

    backend._camera = SimpleNamespace(capture_with_instances=synthetic_camera)
    calls = []

    def software_controller(*, contract, step, attempt):
        calls.append((clock[0], contract.task_id, step.step_id, attempt))
        # Admitted entry is observable; no synthetic control success or full H claim.
        return StepExecutionResult(
            contract.task_id, step.step_id, step.skill.value, attempt, False,
            "SOFTWARE_ONLY_NO_CONTROL", None, 1, clock[0]
        )

    monkeypatch.setattr(recorder.executor, "execute_attempt", software_controller)
    identity = raw.RawEpisodeIdentityV3(
        "software-attempt", "software-assignment", "a" * 64, observation.episode_id,
        "SOFTWARE_ONLY", live.original.identity, "a" * 64, "a" * 64, "a" * 64,
        live.original.role_bundle_hash, None, protocol["source_hashes"], "software-clock"
    )
    try:
        with capture, recorder:
            recorder.bind_source(identity, live.original)
            current = recorder.capture()
            contract, step, binding, _, _ = api._collect_grounded_step(
                live, 0, current, protocol, consume_capture=app._consume_capture
            )
            live.session = _issue_collection_session(app)
            live.pending = (0, digest(step.model_dump(mode="json")), binding.digest())
            with backend.enforce_execution_guard(lambda _: None, event_limit=1024), \
                    backend.capture_each_physics_step(max_captures=2):
                yield api, app, live, contract, step, binding, current, clock, calls
    finally:
        live.owner.close()
        live.closed = True


def test_interval_work_cannot_dispatch_after_registered_frame_deadline(tmp_path, monkeypatch):
    """Removing the final executor gate lets the callback run after its frame expires."""
    with dispatch_context(tmp_path, monkeypatch) as (
        _, app, live, contract, step, binding, _, clock, calls
    ):
        deadline = binding.valid_until
        allocate = live.recorder._new_interval

        def delayed_interval(*args):
            row = allocate(*args)
            if args[1] == "EXECUTOR_ATTEMPT":
                clock[0] = deadline
            return row

        monkeypatch.setattr(live.recorder, "_new_interval", delayed_interval)
        with pytest.raises(RuntimeError, match="registered dispatch.*(deadline|source)"):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert calls == [], f"executor entered at/after expiry: {calls!r} >= {deadline}"
        assert live.recorder._actions[-1]["disposition"] == "ABORTED"
        assert live.recorder.horizons[-1]["failure_type"] == "RuntimeError"
        assert live.pending is None


def test_valid_elapsed_dispatch_reaches_existing_executor_once(tmp_path, monkeypatch):
    """An always-reject or mixed-clock-token gate must fail this positive admission control."""
    with dispatch_context(tmp_path, monkeypatch) as (
        _, _, live, contract, step, binding, observation, clock, calls
    ):
        clock[0] += timedelta(milliseconds=30)
        with pytest.raises(RuntimeError, match="controller or registered horizon incomplete"):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert calls == [(observation.captured_at + timedelta(milliseconds=30),
                          contract.task_id, step.step_id, 1)]
        assert live.pending is live.registered_dispatch is None
        with pytest.raises(RuntimeError):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert len(calls) == 1


@pytest.mark.parametrize(
    "problem",
    ["join", "lease_read", "short_lease", "frame5", "future", "acquisition",
     "identity", "cancelled", "protocol", "step", "source_during_lease"],
)
def test_late_invalid_dispatch_stays_aborted_without_executor(tmp_path, monkeypatch, problem):
    """Each mutation happens after the accepted PRE and early dispatch checks."""
    import sqlite3
    from dataclasses import replace

    from cloud_edge_robot_arm.research import native_calibration_collection as protocol_api

    with dispatch_context(tmp_path, monkeypatch) as (
        api, _, live, contract, step, binding, observation, clock, calls
    ):
        active = [False]
        lease_read = api._registered_lease
        short_until = clock[0] + timedelta(milliseconds=40)
        changed_source = None
        if problem == "source_during_lease":
            copied = tmp_path / "copied-sources"
            names = set(live.original.source_hashes) | {protocol_api.CONFIG}
            names.update(p.config for p in protocol_api._PREPARE_POLICIES.values())
            for name in names:
                destination = copied / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / name).read_bytes())
            monkeypatch.setattr(protocol_api, "ROOT", copied)
            live.registered_tracker._provider._source_root = copied
            changed_source = copied / "src/cloud_edge_robot_arm/vision/owner_registration.py"

        def read_then_delay(*args):
            result = lease_read(*args)
            if active[0]:
                if problem == "lease_read":
                    clock[0] = binding.valid_until
                elif problem == "short_lease":
                    clock[0] = short_until
                elif problem == "source_during_lease":
                    changed_source.write_bytes(changed_source.read_bytes() + b"\n# changed\n")
            return result

        monkeypatch.setattr(api, "_registered_lease", read_then_delay)
        allocate = live.recorder._new_interval
        join = live.recorder._add_join

        def join_then_delay(*args):
            join(*args)
            if problem == "join" and args[2] == "BEFORE_SUBMIT":
                clock[0] = binding.valid_until

        monkeypatch.setattr(live.recorder, "_add_join", join_then_delay)

        def late_change(*args):
            row = allocate(*args)
            if args[1] != "EXECUTOR_ATTEMPT":
                return row
            active[0] = True
            if problem == "short_lease":
                with sqlite3.connect(live.repository.database_path) as connection:
                    connection.execute(
                        "UPDATE simulation_jobs SET lease_expires_at=? WHERE job_id=?",
                        (short_until.isoformat(), live.original.identity.job_id),
                    )
                    connection.execute(
                        "UPDATE simulation_job_leases SET expires_at=? WHERE lease_id=?",
                        (short_until.isoformat(), live.original.identity.lease_id),
                    )
            elif problem == "frame5":
                clock[0] = observation.captured_at + timedelta(seconds=5)
            elif problem == "future":
                clock[0] = observation.captured_at - timedelta(milliseconds=10)
            elif problem == "acquisition":
                clock[0] += timedelta(milliseconds=1)
                live.recorder.capture()  # A distinct actual software acquisition at the same S.
            elif problem == "identity":
                live.original = replace(live.original, proposal_hash="f" * 64)
            elif problem == "cancelled":
                live.repository.request_cancel(live.original.identity.job_id)
            elif problem == "protocol":
                substituted = json.loads(live.protocol_json)
                substituted["schema_version"] = "native.calibration.operational.v2"
                live.protocol_json = protocol_api.canonical(substituted)
            elif problem == "step":
                step.parameters["target_pose"]["z"] += 0.1
            return row

        monkeypatch.setattr(live.recorder, "_new_interval", late_change)
        with pytest.raises((RuntimeError, ValueError)):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert calls == []
        assert live.pending is live.registered_dispatch is None
        assert live.recorder._actions[-1]["disposition"] == "ABORTED"
        interval = next(r for r in live.recorder._intervals if r["kind"] == "EXECUTOR_ATTEMPT")
        assert interval["disposition"] == "ABORTED" and interval["error"]
        assert live.recorder.horizons[-1]["failure_type"]


def test_v7_partial_visibility_consumer_stops_without_pending(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.contracts import SafetyDecision
    from cloud_edge_robot_arm.edge.safety.models import SafetyEvaluationResult

    with dispatch_context(tmp_path, monkeypatch) as (
        _, app, live, _, step, binding, observation, _, calls
    ):
        live.pending = None
        with pytest.raises(RuntimeError, match="collection admission stopped"):
            app._evaluate_collection_admission(
                phase="PRE", step=step,
                conditions=live.original.requirements[step.step_id].preconditions,
                observation=observation,
                shield=SafetyEvaluationResult(True, SafetyDecision.ALLOW, []),
                binding=binding,
            )
        decision = live.recorder.decisions[-1]
        assert decision["decision_kind"] == "STOP"
        assert decision["inputs"]["registered_pose_verdict"]["status"] == "PASS"
        visible = next(v for v in decision["inputs"]["supplemental"]
                       if v["condition_name"] == "target_visible")
        assert visible["status"] == "UNKNOWN"
        assert "common_geometry_proprioception_or_shield_gate" in decision["decision"]["reasons"]
        assert live.pending is None and calls == []


def test_admitted_executor_partial_failure_is_retained_and_cannot_replay(tmp_path, monkeypatch):
    with dispatch_context(tmp_path, monkeypatch) as (
        _, _, live, contract, step, binding, _, _, calls
    ):
        def partial_controller(**_kwargs):
            calls.append("partial")
            live.backend.hold_current_joints()
            raise OSError("software controller failed after command")

        monkeypatch.setattr(live.executor, "execute_attempt", partial_controller)
        with pytest.raises(OSError, match="after command"):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert live.recorder._actions[-1]["disposition"] == "PARTIAL"
        assert live.recorder.horizons[-1]["failure_type"] == "OSError"
        assert live.pending is live.registered_dispatch is None
        with pytest.raises(RuntimeError):
            live.session.execute(index=0, contract=contract, step=step, binding=binding)
        assert calls == ["partial"]


def test_span_api():
    assert hasattr(raw, "RegisteredCollectionActionSpanV1"), "registered span decoder missing"


def test_reader_api():
    assert hasattr(archived, "_ArchivedRegisteredCollectionTracker"), (
        "registered archive adapter missing"
    )


def span_payload(tmp_path, monkeypatch):
    data = binding_data(tmp_path, monkeypatch)
    prepared = owner.prepare_registered_step_binding(**data)
    binding = owner.RegisteredCollectionStepBinding.from_prepared(
        prepared, collection_policy_id="registered-model-collection-v1"
    )
    original = data["original"]
    identity = raw.RawEpisodeIdentityV3(
        "software-attempt",
        "software-assignment",
        "a" * 64,
        original.identity.episode_id,
        "SOFTWARE_ONLY",
        original.identity,
        "a" * 64,
        "a" * 64,
        "a" * 64,
        original.role_bundle_hash,
        None,
        original.source_hashes,
        "software-clock",
    )
    return {
        "schema_version": "native.registered.action-span.v1",
        "record_seq": 1,
        "identity": identity.to_payload(),
        "span_id": "software-span",
        "original_plan": original.to_payload(),
        "step_id": "move",
        "attempt": 1,
        "grounding": binding.to_payload(),
        "interval_id": "software-attempt-interval",
        "command_seq_start": 1,
        "command_seq_end": 1,
        "returned_result": None,
        "disposition": "ABORTED",
        "error": "software fixture did not dispatch",
        "executed_step_payload": binding.grounded_step.model_dump(mode="json"),
    }


def test_new_span_roundtrips_and_is_rejected_by_raw_v3(tmp_path, monkeypatch):
    payload = span_payload(tmp_path, monkeypatch)
    result = raw.RegisteredCollectionActionSpanV1.from_payload(payload)
    assert result.to_payload() == payload
    assert result.grounding.prepared.to_payload()["execution_allowed"] is False
    assert result.disposition == "ABORTED"
    assert result.command_seq_start == result.command_seq_end == 1
    assert result.original_plan.identity == result.identity.owner_identity
    with pytest.raises(ValueError):
        raw.TypedActionSpanV3.from_json(result.to_json())
    payload["grounding"]["prepared"]["grounded_step"]["parameters"]["target_pose"]["z"] = 100
    assert result.grounding.grounded_step.parameters["target_pose"]["z"] < 1


@pytest.mark.parametrize("axis", ["schema", "identity", "original", "step", "binding", "sequence"])
def test_resealed_new_span_rejects_semantic_crosslinks(tmp_path, monkeypatch, axis):
    payload = span_payload(tmp_path, monkeypatch)
    if axis == "schema":
        payload["schema_version"] = "raw.episode.v3"
    elif axis == "identity":
        payload["grounding"]["prepared"]["current_identity"]["lease_id"] = "foreign"
    elif axis == "original":
        payload["grounding"]["prepared"]["original_plan_hash"] = "f" * 64
    elif axis == "step":
        payload["executed_step_payload"]["retry_limit"] = 1
    elif axis == "binding":
        payload["grounding"]["prepared"]["grounded_step"]["parameters"]["target_pose"]["x"] = 3
    else:
        payload["record_seq"] = True
    with pytest.raises((ValueError, TypeError)):
        raw.RegisteredCollectionActionSpanV1.from_json(json.dumps(payload))


def archive_environment(tmp_path, monkeypatch):
    module, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    name = "src/cloud_edge_robot_arm/research/native_archived_tracker.py"
    blob = (ROOT / name).read_bytes()
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    hashes[name] = hashlib.sha256(blob).hexdigest()
    return module, ref, reg, root, hashes, clock


@pytest.mark.parametrize("region", [None, "missing", "incomplete"])
def test_archived_preview_recomputes_pixels_without_becoming_current(tmp_path, monkeypatch, region):
    _, ref, reg, root, hashes, clock = archive_environment(tmp_path, monkeypatch)
    live = collection.bootstrap_registered_collection_tracker_v1(
        ref, reg, source_root=root, source_hashes=hashes
    )
    current = later(ref, fragment=True, region=region)
    state = values()["online"].robot_state
    clock[0] = current.captured_at
    old_geometry = live._region_tracker._geometry

    def geometry_with_elapsed_work(*args, **kwargs):
        result = old_geometry(*args, **kwargs)
        clock[0] += timedelta(milliseconds=20)
        return result

    monkeypatch.setattr(live._region_tracker, "_geometry", geometry_with_elapsed_work)
    saved = collection.registered_collection_grounding_preview_v1(live, current, state)
    clock[0] += timedelta(seconds=60)
    archive = archived._ArchivedRegisteredCollectionTracker(
        ref, reg, source_root=root, source_hashes=hashes, initialized_at=STAMP
    )
    rebuilt = archive.preview_at(
        current, state, evaluated_at=saved.track.evaluated_at, finished_at=saved.evaluated_at
    )
    assert rebuilt.to_payload() == saved.to_payload()
    assert rebuilt.native_authority == "UNAVAILABLE"
    with pytest.raises(TypeError, match="owned"):
        collection.registered_collection_grounding_preview_v1(archive, current, state)
    with pytest.raises(ValueError, match="recorded"):
        archive._provider.update(current)
    if region is None:
        assert saved.status == "DERIVED"
        assert saved.track.evaluated_at < saved.evaluated_at
    else:
        assert saved.status == "UNKNOWN"
        assert saved.grasp_tcp_world_m is None


@pytest.mark.parametrize("timing", ["future", "reverse", "expired"])
def test_archived_preview_refuses_invalid_original_times(tmp_path, monkeypatch, timing):
    _, ref, reg, root, hashes, _ = archive_environment(tmp_path, monkeypatch)
    archive = archived._ArchivedRegisteredCollectionTracker(
        ref, reg, source_root=root, source_hashes=hashes, initialized_at=STAMP
    )
    current = later(ref)
    start = current.captured_at
    finish = start + timedelta(milliseconds=20)
    if timing == "future":
        start = current.captured_at - timedelta(milliseconds=1)
    elif timing == "reverse":
        finish = start - timedelta(milliseconds=1)
    else:
        finish = current.captured_at + timedelta(seconds=5)
    with pytest.raises(ValueError):
        archive.preview_at(
            current, values()["online"].robot_state, evaluated_at=start, finished_at=finish
        )


def test_legacy_admission_rejects_partial_registered_binding_before_capture(tmp_path, monkeypatch):
    from tests.test_native_collection_authority import application

    payload = span_payload(tmp_path / "candidate", monkeypatch)
    binding = owner.RegisteredCollectionStepBinding.from_payload(payload["grounding"])
    app = application(tmp_path / "legacy")
    with pytest.raises(TypeError, match="legacy"):
        app._evaluate_collection_admission(
            phase="PRE",
            step=binding.grounded_step,
            conditions=(),
            observation=None,
            shield=None,
            binding=binding,
        )


def test_registered_recorder_and_reader_keep_partial_actions_out_of_qualification(tmp_path):
    from cloud_edge_robot_arm.research.native_calibration_collection import load_json
    from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
    from tests.test_native_collection_authority import source_recorder
    from tests.test_registered_object_geometry import frame

    recorder, backend, capture, clock_owner, original = source_recorder(tmp_path)
    recorder.application.protocol = {"schema_version": "native.calibration.operational.v7"}
    try:
        with capture, recorder:
            recorder.capture()
            manifest = recorder.freeze()
        assert manifest["schema_version"] == "native.registered.full-horizon.inventory.v1"
        saved = load_json(recorder.directory / "partial-originals.json")
        assert saved["schema_version"] == "native.registered.full-horizon.originals.v1"
        assert saved["actions"] == []
        _, registration = frame()
        legacy = _Audit({"geometry": registration.to_payload()}, {}, tmp_path)
        legacy.directory = recorder.directory
        with pytest.raises(ValueError, match="schema"):
            legacy.inventory()
    finally:
        clock_owner.close()


def test_registered_reader_decodes_own_span_and_rejects_foreign_global_identity(
    tmp_path, monkeypatch
):
    from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
    from tests.test_registered_object_geometry import frame

    payload = span_payload(tmp_path, monkeypatch)
    _, registration = frame()
    audit = _Audit(
        {
            "geometry": registration.to_payload(),
            "schema_version": "native.calibration.operational.v7",
        },
        {},
        tmp_path,
    )
    audit.identity = raw.RawEpisodeIdentityV3.from_json(json.dumps(payload["identity"]))
    result = audit.action_span(payload)
    assert result.disposition == "ABORTED"
    assert result.grounding.grounded_step.step_id == "move"
    audit.raw = {"actions": [payload], "horizons": [], "allocated_actions": ["software-span"]}
    with pytest.raises(ValueError, match="eight"):
        audit.horizons()
    payload["identity"]["clock_domain_id"] = "foreign-clock"
    with pytest.raises(ValueError, match="identity"):
        audit.action_span(payload)


def test_v7_full_reader_does_not_invent_a_released_group(tmp_path):
    from cloud_edge_robot_arm.research.native_calibration_collection import (
        prepare_registered_collection_protocol,
    )
    from cloud_edge_robot_arm.research.native_full_horizon_originals import (
        read_native_full_horizon_group,
    )

    protocol = tmp_path / "v7"
    prepare_registered_collection_protocol(output=protocol)
    with pytest.raises(ValueError, match="release"):
        read_native_full_horizon_group(
            protocol, assignment_id="native-r595-0001", root=tmp_path / "missing"
        )
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(
    "tamper", [None, "input", "candidate", "lease", "policy", "time", "preview"]
)
def test_independent_registered_grounding_reconstruction_checks_semantics(
    tmp_path, monkeypatch, tamper
):
    from datetime import datetime

    from cloud_edge_robot_arm.research.native_calibration_collection import digest
    from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
    from tests.test_registered_collection_execution import consumer_context

    application, _, live, protocol, args, _, records, consume = consumer_context(
        tmp_path, monkeypatch
    )
    _, step, binding, _, _ = application._collect_grounded_step(
        live, 0, args["observation"], protocol, consume_capture=consume
    )
    evidence = records[0]
    audit = _Audit(protocol, {}, tmp_path)
    audit.original = live.original
    audit.registered_tracker = archived._ArchivedRegisteredCollectionTracker(
        args["reference_observation"],
        audit.scope,
        source_root=ROOT,
        source_hashes=live.original.source_hashes,
        initialized_at=args["reference_observation"].captured_at,
    )
    audit.registered_preview_finished = args["reference_observation"].captured_at
    # Only the unrelated complete operational graph is outside this unit.
    # Its original validator is covered separately; this does not certify a clock.
    monkeypatch.setattr(
        audit,
        "tracker_clock",
        lambda row, *_args, **_kwargs: datetime.fromisoformat(row["evaluated_at"]),
    )
    if tamper == "input":
        evidence["inputs"]["grasp_tcp_world_m"][0] += 0.1
        evidence["inputs_sha256"] = digest(evidence["inputs"])
    elif tamper == "candidate":
        evidence["binding"]["prepared"]["grounded_step"]["parameters"]["target_pose"]["x"] += 0.1
        evidence["binding_sha256"] = digest(evidence["binding"])
        binding = owner.RegisteredCollectionStepBinding.from_payload(evidence["binding"])
    elif tamper == "lease":
        evidence["lease_source"]["lease_id"] = "foreign"
    elif tamper == "policy":
        evidence["policy"]["tcp_velocity"] = 0.3
        evidence["policy_sha256"] = digest(evidence["policy"])
    elif tamper == "time":
        expired = (args["observation"].captured_at + timedelta(seconds=5)).isoformat()
        evidence["final_validation_at"] = expired
        evidence["tracker_clock"]["finished_at"] = expired
    elif tamper == "preview":
        evidence["registered_preview"]["track"]["geometry"]["object_center_world_m"][0] += 0.1

    def reconstruct():
        return audit.registered_grounding(
            evidence, args["observation"], args["robot_state"], step, binding, 0
        )

    if tamper:
        with pytest.raises(ValueError):
            reconstruct()
    else:
        reconstruct()
        assert audit.policies["MOVE_ABOVE"].tcp_velocity == 0.15
        assert audit.source_ok is False and audit.horizon_ok is False
