"""Actual boundary plumbing; SOFTWARE_ONLY fixtures plus explicit passive two steps."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module, util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import JointCommand, PhysicalScenarioConfig, SensorFrame
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    MuJoCoPhysicsBackend,
    PhysicsStepObservation,
)
from tests import test_visual_worker_runtime as runtime_tests
from tests.test_raw_episode_v3 import state

runtime_source = runtime_tests.runtime_source


def recorder_fixture(tmp_path):
    """Software sources, real boundary dispatch and sole real SkillExecutor."""
    module = recorder_api()
    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.research.raw_episode_v3 import RawEpisodeIdentityV3
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
    from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan
    from tests.test_visual_owner_registration import values

    backend = software_backend()
    robot = MuJoCoSkillRobot(backend)
    executor = SkillExecutor(robot=robot, registry=SkillRegistry.default())
    capture = MuJoCoCaptureSession(backend._config, backend=backend)
    sources = {}
    repository = Path(__file__).resolve().parents[1]
    source_root = tmp_path / "sources"
    for name in module.RECORDER_SOURCE_PATHS:
        content = (repository / name).read_bytes()
        target = source_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        sources[name] = hashlib.sha256(content).hexdigest()
    base = values()["original"]
    now = datetime.now(UTC)
    contract = base.contract.model_copy(
        update={"issued_at": now - timedelta(seconds=1), "valid_until": now + timedelta(seconds=60)}
    )
    identity = replace(base.identity, episode_id=backend._episode_id)
    requirements = {
        name: replace(value, policy_source_hashes=sources)
        for name, value in base.requirements.items()
    }
    original = freeze_original_visual_plan(
        identity=identity,
        contract=contract,
        proposal_hash=base.proposal_hash,
        role_bundle_hash=base.role_bundle_hash,
        compiler_source_hashes=sources,
        source_hashes=sources,
        requirements=requirements,
        dependencies=base.dependencies,
        task_deadline_at=now + timedelta(seconds=60),
        verification_deadline_at=now + timedelta(seconds=40),
        registered_at=now,
    )
    raw_identity = RawEpisodeIdentityV3(
        "raw-attempt-1",
        "assignment-1",
        "a" * 64,
        backend._episode_id,
        "SOFTWARE_ONLY",
        identity,
        "a" * 64,
        "a" * 64,
        "a" * 64,
        base.role_bundle_hash,
        "a" * 64,
        sources,
        "software-clock-1",
    )
    recorder = module.VisualRawRecorderV3(
        backend,
        capture,
        executor,
        directory=tmp_path / "raw",
        source_root=source_root,
        source_hashes=sources,
    )
    return recorder, backend, capture, executor, raw_identity, original


def software_sensor_camera(backend):
    """Only render is substituted; backend CAPTURE boundary and converter are real."""
    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from tests.test_visual_owner_registration import values

    observation = values()["online"].observation
    backend._config = backend._config.model_copy(update={"render_rgb": True, "render_depth": True})
    counter = 0

    def capture_with_instances(data, **_kwargs):
        nonlocal counter
        counter += 1
        count = observation.width * observation.height
        frame = SensorFrame(
            frame_id=f"software-frame-{counter}",
            sim_time_s=backend.get_sim_time(),
            width=observation.width,
            height=observation.height,
            rgb=bytes([100, 120, 150]) * count,
            depth=(0.5,) * count,
            intrinsics=tuple(observation.intrinsics),
            camera_to_world=tuple(observation.camera_to_world),
            captured_at=datetime.now(UTC),
            episode_id=backend._episode_id,
            scene_id="software-scene",
            calibration_version=observation.calibration_version,
            valid_mask=bytes([1]) * count,
        )
        digest = MuJoCoRGBDCamera._physics_state_hash(data)
        return frame, (-1,) * count, {-1: "background"}, (digest,) * 3

    backend._camera = SimpleNamespace(capture_with_instances=capture_with_instances)


def boundary_api():
    assert hasattr(MuJoCoPhysicsBackend, "observe_operation_boundaries"), (
        "paired readonly operation boundaries are missing"
    )
    return import_module("cloud_edge_robot_arm.simulation.mujoco.backend")


def recorder_api():
    assert util.find_spec("cloud_edge_robot_arm.vision.raw_recorder_v3") is not None, (
        "actual raw-v3 recorder module is missing"
    )
    return import_module("cloud_edge_robot_arm.vision.raw_recorder_v3")


def software_backend():
    """No MjData/renderer/real physics: preserve real backend dispatch/control semantics."""
    backend = MuJoCoPhysicsBackend()
    backend._config = SimulatorConfig(physics_dt_s=1 / 240, domain_randomization=False)
    backend._scenario = PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0)
    backend._episode_id = "software-episode"
    backend._model = SimpleNamespace(
        actuator_gainprm=np.full((9, 10), 20.0), actuator_ctrlrange=np.array([[-3.0, 3.0]] * 9)
    )
    backend._data = SimpleNamespace(
        time=0.0,
        qpos=np.zeros(16),
        qvel=np.zeros(15),
        act=np.zeros(0),
        ctrl=np.zeros(9),
        qfrc_bias=np.zeros(15),
    )
    backend._data.qpos[7:9] = 0.039
    backend._data.ctrl[7:9] = 0.039

    def mj_step(_model, data):
        data.time += backend._config.physics_dt_s

    backend._mujoco = SimpleNamespace(mj_step=mj_step)
    backend._read_contacts = lambda: []

    def observation(_contacts):
        payload = state(backend.total_physics_steps)
        payload.update(
            episode_id=backend._episode_id,
            sim_time_s=backend.get_sim_time(),
            joint_positions_rad=tuple(float(x) for x in backend._data.qpos[:7]),
            joint_velocities_rad_s=tuple(float(x) for x in backend._data.qvel[:7]),
            finger_positions_m=tuple(float(x) for x in backend._data.qpos[7:9]),
            finger_velocities_m_s=tuple(float(x) for x in backend._data.qvel[7:9]),
            estop_engaged=backend.estop_engaged,
        )
        return PhysicsStepObservation(**payload)

    backend._build_physics_observation = observation
    backend._update_sensor_frame = lambda: None
    return backend


def test_real_render_disabled_passive_two_steps_have_ordered_actual_begin_end_and_old_observers():
    boundary_api()
    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(domain_randomization=False, physics_dt_s=1 / 240))
    events, physics, controls = [], [], []
    try:
        with backend.observe_operation_boundaries(events.append):
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=41))
            with (
                backend.observe_physics_steps(physics.append),
                backend.observe_actuator_steps(controls.append),
            ):
                result = backend.step(steps=2)
        assert result.physics_steps == backend.total_physics_steps == 2
        assert [row.physics_step for row in physics] == [1, 2]
        assert [row.physics_step for row in controls] == [1, 2]
        assert [(event.kind, event.phase) for event in events] == [
            ("RESET", "BEGIN"),
            ("RESET", "END"),
            ("CONTROL", "BEGIN"),
            ("CONTROL", "END"),
            ("PHYSICS", "BEGIN"),
            ("PHYSICS", "END"),
            ("CONTROL", "BEGIN"),
            ("CONTROL", "END"),
            ("PHYSICS", "BEGIN"),
            ("PHYSICS", "END"),
        ]
        ends = [event for event in events if event.kind == "PHYSICS" and event.phase == "END"]
        assert [event.result["physics_state"]["physics_step"] for event in ends] == [1, 2]
        assert not any(event.kind == "CAPTURE" for event in events)
        assert backend.command_records == []
    finally:
        backend.shutdown()


def test_nested_new_hook_and_callback_reentrant_mutation_reject_without_extra_steps():
    boundary_api()
    backend = software_backend()

    def observe(_event):
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.step()
        with pytest.raises(RuntimeError, match="observer callback"):
            backend.emergency_stop()

    with backend.observe_operation_boundaries(observe):
        with pytest.raises(RuntimeError, match="already active"):
            with backend.observe_operation_boundaries(lambda event: None):
                pass
        backend.step()
    assert backend.total_physics_steps == 1
    assert not backend.operation_observer_failures


def test_observer_failure_cannot_suppress_hard_stop_or_erase_its_ordered_original_commands():
    boundary_api()
    backend = software_backend()

    def failed(_event):
        raise RuntimeError("software audit sink failed")

    with backend.observe_operation_boundaries(failed):
        backend.emergency_stop()
    assert backend.estop_engaged
    assert [row["type"] for row in backend.command_records] == [
        "hold_current_joints",
        "emergency_stop",
    ]
    assert all(row["accepted"] for row in backend.command_records)
    assert backend.operation_observer_failures
    assert (
        sum(
            row["kind"] == "COMMAND" and row["phase"] == "BEGIN" for row in backend.operation_ledger
        )
        == 2
    )
    assert backend.operation_observer_overhead_ns >= 0


def test_original_command_exception_and_rejection_are_both_actual_operation_sources():
    boundary_api()
    backend = software_backend()
    events = []
    with backend.observe_operation_boundaries(events.append):
        with pytest.raises(ValueError):
            backend.apply_joint_targets(JointCommand(positions=[0.0] * 6))
        backend.emergency_stop()
        backend.apply_joint_targets(JointCommand(positions=[1.0] * 7))
    assert events[0].kind == "COMMAND" and events[0].phase == "BEGIN"
    assert events[1].phase == "END" and events[1].error_type == "ValueError"
    assert events[-1].result["command_records"][-1]["accepted"] is False
    assert backend.command_records[-1]["reason"] == "emergency_stop"
    assert backend.total_physics_steps == 0


def test_observer_payloads_are_detached_and_nested_readonly():
    boundary_api()
    backend = software_backend()
    events = []
    requested = JointCommand(positions=[0.03] * 7)
    with backend.observe_operation_boundaries(events.append):
        backend.apply_joint_targets(requested)
    requested.positions[0] = 9.0
    assert events[0].parameters["requested"]["positions"][0] == 0.03
    with pytest.raises(TypeError):
        events[0].parameters["requested"]["positions"][0] = 9.0
    with pytest.raises(TypeError):
        events[-1].result["command_records"][0]["accepted"] = False
    assert backend.command_records[0]["accepted"] is True


def test_missing_recorder_module_qualifies_feature_red_before_any_actual_operation():
    module = recorder_api()
    assert callable(module.VisualRawRecorderV3)


def test_capture_state_read_failure_still_allocates_begin_and_end_without_camera_call():
    boundary_api()
    backend = software_backend()
    events = []
    with backend.observe_operation_boundaries(events.append):
        backend._data = None  # SOFTWARE_ONLY source failure, no actual simulator state.
        with pytest.raises((RuntimeError, AssertionError)):
            backend.capture_sensor_frame_with_instances()
    assert [(row["kind"], row["phase"]) for row in backend.operation_ledger] == [
        ("CAPTURE", "BEGIN"),
        ("CAPTURE", "END"),
    ]
    assert backend.operation_observer_failures


def test_unprintable_observer_exception_cannot_prevent_the_actual_software_stop():
    boundary_api()
    backend = software_backend()

    class Unprintable(RuntimeError):
        def __str__(self):
            raise RuntimeError("message source unavailable")

    def failure(_event):
        raise Unprintable()

    with backend.observe_operation_boundaries(failure):
        backend.emergency_stop()
    assert backend.estop_engaged
    assert len(backend.command_records) == 2
    assert backend.operation_observer_failures


def test_failed_capture_keeps_allocated_denominator_and_original_exception(tmp_path):
    recorder, backend, capture, _executor, identity, original = recorder_fixture(tmp_path)
    with capture, recorder:
        recorder.bind_source(identity, original)
        with pytest.raises(RuntimeError, match="rendering is not enabled"):
            recorder.capture()
        assert recorder.allocated_acquisition_ids == ("acquisition-1",)
        records = recorder.build_records()
        assert len(records.frames) == 1 and records.frames[0].observation_payload is None
        assert records.intervals[0].disposition == "ABORTED"
        report = recorder.flush()
    ledger = json.loads((tmp_path / "raw" / "allocation-ledger.json").read_text())
    assert ledger["allocated_acquisition_ids"] == ["acquisition-1"]
    assert ledger["backend_operation_allocations"] == 1
    assert report["source_consistency"] != "COMPLETE"
    assert backend.total_physics_steps == 0 and backend.command_records == []


def test_preplan_capture_is_buffered_then_bound_without_second_acquisition(tmp_path):
    recorder, backend, capture, _executor, identity, original = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    with capture, recorder:
        observation = recorder.capture()
        assert recorder.allocated_acquisition_ids == ("acquisition-1",)
        recorder.bind_source(identity, original)
        records = recorder.build_records()
        assert len(records.frames) == 1
        assert records.frames[0].observation_payload["observation_id"] == observation.observation_id
        assert records.frames[0].input_role == "ONLINE"
        assert (
            records.frames[0].pass_state_hashes
            == (recorder.last_captured_frame.physics_state_hash,) * 3
        )
        assert backend.total_physics_steps == 0
        with pytest.raises(RuntimeError, match="already bound"):
            recorder.bind_source(identity, original)
        recorder.flush()
    assert (
        len(
            [
                row
                for row in backend.operation_ledger
                if row["kind"] == "CAPTURE" and row["phase"] == "BEGIN"
            ]
        )
        == 1
    )
    manifest = json.loads((tmp_path / "raw" / "raw-artifacts.json").read_text())
    for name, digest in manifest["file_hashes"].items():
        assert hashlib.sha256((tmp_path / "raw" / name).read_bytes()).hexdigest() == digest


def test_recorder_same_owner_validation_rejects_foreign_capture_and_executor(tmp_path):
    recorder, backend, capture, executor, _identity, _original = recorder_fixture(tmp_path)
    other_backend = software_backend()
    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    for foreign_capture, foreign_executor in (
        (MuJoCoCaptureSession(backend._config, backend=other_backend), executor),
        (
            capture,
            SkillExecutor(robot=MuJoCoSkillRobot(other_backend), registry=SkillRegistry.default()),
        ),
    ):
        with pytest.raises(ValueError, match="same backend"):
            recorder_api().VisualRawRecorderV3(
                backend,
                foreign_capture,
                foreign_executor,
                directory=tmp_path / "invalid",
                source_root=recorder.source_root,
                source_hashes=recorder.source_hashes,
            )
    assert not (tmp_path / "invalid").exists()
    assert backend.command_records == [] and other_backend.command_records == []


def test_actual_executor_rejection_and_partial_exception_both_remain_in_denominator(tmp_path):
    recorder, backend, capture, executor, identity, original = recorder_fixture(tmp_path)
    from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan

    step = original.contract.steps[0].model_copy(
        update={"preconditions": [], "success_conditions": []}
    )
    contract = original.contract.model_copy(update={"steps": [step, original.contract.steps[1]]})
    requirements = dict(original.requirements)
    requirements[step.step_id] = replace(
        requirements[step.step_id], _original_step_json=step.model_dump_json()
    )
    original = freeze_original_visual_plan(
        **{**original.freeze_inputs(), "contract": contract, "requirements": requirements}
    )
    rejected = step.model_copy(
        update={"parameters": {"object_id": contract.task_target.object_id, "bad": True}}
    )

    def partial_action(*_args, **_kwargs):
        backend.apply_joint_targets(JointCommand(positions=[0.02] * 7))
        backend.step()
        raise RuntimeError("software interruption after one step")

    executor._robot.move_above = partial_action
    with capture, recorder:
        recorder.bind_source(identity, original)
        rejection = recorder.execute_attempt(contract=contract, step=rejected, attempt=1)
        assert not rejection.success and rejection.action_result is None
        with pytest.raises(RuntimeError, match="software interruption"):
            recorder.execute_attempt(contract=contract, step=step, attempt=1)
        records = recorder.build_records()
        assert recorder.allocated_action_span_ids == ("action-span-1", "action-span-2")
        assert [row.disposition for row in records.actions] == ["REJECTED", "PARTIAL"]
        assert records.actions[0].command_seq_start == records.actions[0].command_seq_end == 1
        assert (records.actions[1].command_seq_start, records.actions[1].command_seq_end) == (1, 2)
        assert records.commands[0].owner_action_span_id == "action-span-2"
        assert len(records.physics) == 1 and backend.total_physics_steps == 1
        assert records.actions[1].returned_result is None
        recorder.flush()
    assert backend.command_records[0]["accepted"] is True


def test_unbound_and_collector_sink_failure_keep_backend_stop_and_ledger(tmp_path):
    recorder, backend, capture, _executor, _identity, _original = recorder_fixture(tmp_path)
    with capture, recorder:
        recorder._clock_pair = lambda: (_ for _ in ()).throw(
            RuntimeError("audit clock unavailable")
        )
        backend.emergency_stop()
        recorder.flush()
    ledger = json.loads((tmp_path / "raw" / "allocation-ledger.json").read_text())
    assert backend.estop_engaged
    assert [row["type"] for row in backend.command_records] == [
        "hold_current_joints",
        "emergency_stop",
    ]
    assert (
        ledger["backend_operation_allocations"] == 3
    )  # Two commands and actual control application.
    assert ledger["source_binding"] == "UNBOUND"
    assert ledger["observer_failures"]


def test_failed_purpose_clock_cannot_suppress_actual_stop_inside_the_boundary(tmp_path):
    recorder, backend, capture, _executor, _identity, _original = recorder_fixture(tmp_path)
    with capture, recorder:
        recorder._clock_pair = lambda: (_ for _ in ()).throw(RuntimeError("clock source failed"))
        try:
            with recorder.purpose("TERMINATION"):
                backend.emergency_stop()
        except RuntimeError:
            pass
        assert backend.estop_engaged, "collector clock failure suppressed the existing stop"
        report = recorder.flush()
    assert backend.estop_engaged
    assert [row["type"] for row in backend.command_records] == [
        "hold_current_joints",
        "emergency_stop",
    ]
    ledger = json.loads((tmp_path / "raw" / "allocation-ledger.json").read_text())
    assert ledger["allocated_purpose_interval_ids"] == ["purpose-1"]
    assert report["source_consistency"] == "INCOMPLETE"


def test_failed_attempt_clock_cannot_suppress_same_executor_stop_or_erase_allocation(tmp_path):
    recorder, backend, capture, executor, identity, original = recorder_fixture(tmp_path)
    from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
    from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan

    step = original.contract.steps[0].model_copy(
        update={"preconditions": [], "success_conditions": []}
    )
    contract = original.contract.model_copy(update={"steps": [step, original.contract.steps[1]]})
    requirements = dict(original.requirements)
    requirements[step.step_id] = replace(
        requirements[step.step_id], _original_step_json=step.model_dump_json()
    )
    original = freeze_original_visual_plan(
        **{**original.freeze_inputs(), "contract": contract, "requirements": requirements}
    )

    def stop_action(*_args, **_kwargs):
        started = datetime.now(UTC)
        backend.emergency_stop()
        return build_action_result(
            action_type="MOVE_ABOVE",
            success=False,
            state_before={},
            state_after={},
            duration_ms=0,
            started_at=started,
            error_code="SOFTWARE_ONLY_STOP",
            details={"physics_steps": 0},
        )

    executor._robot.move_above = stop_action
    with capture, recorder:
        recorder.bind_source(identity, original)
        recorder._clock_pair = lambda: (_ for _ in ()).throw(RuntimeError("clock source failed"))
        try:
            recorder.execute_attempt(contract=contract, step=step, attempt=1)
        except RuntimeError:
            pass
        assert backend.estop_engaged, "collector clock failure suppressed same executor stop"
        records = recorder.build_records()
        assert recorder.allocated_action_span_ids == ("action-span-1",)
        assert records.actions[0].command_seq_end - records.actions[0].command_seq_start == 2
        assert records.actions[0].returned_result["error"]["code"] == "SOFTWARE_ONLY_STOP"


def test_complete_software_graph_has_all_121_steps_one_executor_and_exact_frame_joins(tmp_path):
    recorder, backend, capture, executor, identity, original = recorder_fixture(tmp_path)
    from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
    from cloud_edge_robot_arm.research.raw_episode_v3 import (
        RawEpisodeEnvelopeV3,
        RawEpisodeRecordsV3,
        validate_raw_episode_v3,
    )
    from cloud_edge_robot_arm.vision.owner_registration import freeze_original_visual_plan

    # SOFTWARE_ONLY: no MjData, renderer or mj_step is available in this fixture.
    backend._mujoco.mj_resetData = lambda _model, data: setattr(data, "time", 0.0)
    backend._mujoco.mj_forward = lambda _model, _data: None
    backend._model.joint = lambda name: SimpleNamespace(id=0 if name == "finger_left_joint" else 1)
    backend._model.jnt_qposadr = [7, 8]
    backend._set_free_body_pose = lambda *_args: None
    backend._set_body_mass = lambda *_args: None
    backend._set_geom_friction = lambda *_args: None
    step = original.contract.steps[0].model_copy(
        update={"preconditions": [], "success_conditions": []}
    )
    requirements = dict(original.requirements)
    requirements[step.step_id] = replace(
        requirements[step.step_id], _original_step_json=step.model_dump_json()
    )
    contract = original.contract.model_copy(update={"steps": [step, original.contract.steps[1]]})

    def software_return(*_args, **_kwargs):
        started = datetime.now(UTC)
        backend.apply_joint_targets(JointCommand(positions=[0.02] * 7))
        backend.step()
        return build_action_result(
            action_type="MOVE_ABOVE",
            success=True,
            state_before={},
            state_after={},
            duration_ms=4,
            started_at=started,
            details={"physics_steps": 1},
        )

    executor._robot.move_above = software_return
    with capture, recorder:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
        owner = replace(original.identity, episode_id=backend._episode_id)
        original = freeze_original_visual_plan(
            **{
                **original.freeze_inputs(),
                "identity": owner,
                "contract": contract,
                "requirements": requirements,
            }
        )
        identity = replace(identity, episode_id=backend._episode_id, owner_identity=owner)
        with recorder.purpose("SETTLE"):
            backend.step(steps=120)
        software_sensor_camera(backend)
        before = recorder.capture()
        recorder.bind_source(identity, original)
        returned = recorder.execute_attempt(contract=contract, step=step, attempt=1)
        assert returned.success and returned.action_result.success
        after = recorder.capture()
        with recorder.purpose("TERMINATION"):
            pass
        terminal = recorder.capture()
        recorder.join_frame("action-span-1", terminal, "TERMINAL")
        report = recorder.flush()
        assert report["source_consistency"] == "COMPLETE", report["reasons"]
    envelope = RawEpisodeEnvelopeV3.from_json((tmp_path / "raw" / "raw-envelope.json").read_text())
    records = RawEpisodeRecordsV3.from_json((tmp_path / "raw" / "raw-records.json").read_text())
    view = validate_raw_episode_v3(envelope, records)
    assert view.status == "COMPLETE" and view.utc_mapping == "UNAVAILABLE"
    assert view.continuous_motion == "NOT_CERTIFIED"
    assert view.counts["physics_expected"] == view.counts["physics_recorded"] == 121
    assert view.counts["allocated_actions"] == view.counts["recorded_actions"] == 1
    assert view.counts["allocated_acquisitions"] == view.counts["recorded_acquisitions"] == 3
    assert [join.relation for join in records.joins] == [
        "BEFORE_SUBMIT",
        "AFTER_RETURN",
        "TERMINAL",
    ]
    assert [frame.observation_payload["observation_id"] for frame in records.frames] == [
        before.observation_id,
        after.observation_id,
        terminal.observation_id,
    ]
    assert len(backend.command_records) == 1


def test_material_source_change_is_invalid_and_keeps_all_capture_allocations(tmp_path):
    recorder, backend, capture, _executor, identity, original = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    with capture, recorder:
        recorder.capture()
        recorder.bind_source(identity, original)
        source = recorder.source_root / "src/cloud_edge_robot_arm/vision/capture.py"
        source.write_bytes(source.read_bytes() + b"\n# SOFTWARE_ONLY source changed\n")
        report = recorder.flush()
        assert report["source_consistency"] == "INVALID"
        assert report["allocated_acquisitions"] == 1
    ledger = json.loads((tmp_path / "raw" / "allocation-ledger.json").read_text())
    assert ledger["allocated_acquisition_ids"] == ["acquisition-1"]
    assert backend.total_physics_steps == 0


def test_original_instance_ids_and_labels_are_persisted_for_offline_audit(tmp_path):
    recorder, backend, capture, _executor, identity, original = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    with capture, recorder:
        observation = recorder.capture()
        recorder.bind_source(identity, original)
        recorder.flush()
    directory = tmp_path / "raw" / "frames" / "acquisition-1"
    import struct

    assert (directory / "instances.i32").is_file(), "actual original instance denominator missing"
    assert (directory / "instances.i32").read_bytes() == struct.pack(
        f"<{observation.width * observation.height}i",
        *([-1] * (observation.width * observation.height)),
    )
    metadata = json.loads((directory / "source-frame.json").read_text())
    assert metadata["instance_labels"] == {"-1": "background"}
    assert metadata["observation"]["observation_id"] == observation.observation_id
    assert metadata["online_geometry_source"] is False


@pytest.mark.parametrize("binding_change", ["none", "cancel", "config"])
def test_worker_binding_uses_real_open_attempt_and_actual_reset_sources(
    tmp_path, runtime_source, binding_change
):
    module = recorder_api()
    assert hasattr(module.VisualRawRecorderV3, "bind_worker_source"), (
        "actual worker source binding missing"
    )
    from cloud_edge_robot_arm.contracts.models import RobotState
    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
    from tests.test_visual_worker_runtime import frame, plan, runtime

    data = dict(runtime_source)
    source = data["source"]
    repository = Path(__file__).resolve().parents[1]
    sources = dict(source.source_hashes)
    for name in module.RECORDER_SOURCE_PATHS:
        path = source.source_root / name
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((repository / name).read_bytes())
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    data["source"] = replace(source, source_hashes=sources)
    backend = software_backend()
    backend._mujoco.mj_resetData = lambda _model, data: setattr(data, "time", 0.0)
    backend._mujoco.mj_forward = lambda _model, _data: None
    backend._model.joint = lambda name: SimpleNamespace(id=0 if name == "finger_left_joint" else 1)
    backend._model.jnt_qposadr = [7, 8]
    backend._set_free_body_pose = lambda *_args: None
    backend._set_body_mass = lambda *_args: None
    backend._set_geom_friction = lambda *_args: None
    capture = MuJoCoCaptureSession(backend._config, backend=backend)
    executor = SkillExecutor(robot=MuJoCoSkillRobot(backend), registry=SkillRegistry.default())
    recorder = module.VisualRawRecorderV3(
        backend,
        capture,
        executor,
        directory=tmp_path / "actual-job-raw",
        source_root=source.source_root,
        source_hashes=sources,
    )
    with capture, recorder:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
        owner = runtime(data, episode_id=backend._episode_id)
        robot = RobotState(connected=True)
        claim = owner.reserve_capture(robot, initial=True)
        observation = frame().model_validate(
            {**frame().model_dump(), "episode_id": backend._episode_id, "checksum_sha256": ""}
        )
        owner.complete_capture(claim, observation, robot)
        plan(owner, observation)
        owner.adopt_plan(robot)
        if binding_change != "none":
            if binding_change == "cancel":
                source.job_repository.request_cancel(source.job_id)
            else:
                backend._config = backend._config.model_copy(update={"camera_width": 121})
            with pytest.raises(ValueError):
                recorder.bind_worker_source(owner)
            assert recorder._identity is None
        else:
            identity = recorder.bind_worker_source(owner)
            actual_attempt = source.job_repository.list_attempts(source.run_id)[0]
            assert identity.source_kind == "ONLINE_CED"
            assert identity.assignment_id == source.run_id
            assert identity.owner_identity.attempt == actual_attempt.attempt == 1
            assert identity.owner_identity.job_id == source.job_id
            assert identity.model_snapshot_hash == "5" * 64
            assert identity.episode_id == backend._episode_id
            assert (
                identity.asset_hash
                == hashlib.sha256(Path(backend._config.model_path).read_bytes()).hexdigest()
            )
            assert identity.scene_hash != identity.config_hash
            assert identity.attempt_id.startswith("attempt-")
            assert len(identity.attempt_id) == 72
    assert backend.command_records == [] and backend.total_physics_steps == 0
