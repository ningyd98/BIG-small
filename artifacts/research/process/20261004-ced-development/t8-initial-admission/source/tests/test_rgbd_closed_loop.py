"""T7 boundaries: independent truth never becomes online completion evidence."""

from dataclasses import asdict

import pytest

from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import EpisodeOutcome
from cloud_edge_robot_arm.vision.evaluation import (
    ExecutionPolicy,
    combine_outcome,
    independent_top_center,
    localization_error,
)


def physical(success=True):
    return EpisodeOutcome(
        success,
        "SUCCESS" if success else "FAILED",
        False,
        None if success else "HOLD_TOO_SHORT",
        0.1,
        0.5,
        1.2,
        8.0,
    )


def test_online_false_done_is_not_episode_success():
    outcome = combine_outcome(physical(False), online_complete=True, records=())
    assert not outcome.success
    assert outcome.online_reported_complete is True
    assert outcome.physical_success is False


def test_oracle_outcome_cannot_change_online_routing():
    records = ({"route": "STOP", "verification_status": "UNKNOWN"},)
    success = combine_outcome(physical(), online_complete=False, records=records)
    failure = combine_outcome(physical(False), online_complete=False, records=records)
    assert success.verification_records == failure.verification_records
    assert not success.success
    assert not failure.success


def test_teacher_outcome_serialization_remains_unchanged():
    assert "online_reported_complete" not in asdict(physical())


def test_localization_error_uses_independent_reference():
    labels = {
        "instances": [
            {"role": "target", "position": [0.2, 0.1, 0.03], "half_size": [0.03, 0.03, 0.03]}
        ]
    }
    center = independent_top_center(labels)
    assert center == pytest.approx((0.2, 0.1, 0.06))
    assert localization_error({"x": 0.22, "y": 0.1, "z": 0.06}, center) >= 0.019999


def test_policy_rejects_unbounded_or_unfrozen_online_runs():
    with pytest.raises(ValueError):
        ExecutionPolicy(instruction="pick", timeout_s=float("inf"))
    with pytest.raises(ValueError):
        ExecutionPolicy(instruction="pick", model_snapshot_hash="")


def test_all_failed_smoke_cannot_pass_acceptance():
    from scripts.run_rgbd_smoke import summarize

    rows = [{"case_id": f"case-{i}", "kind": "NORMAL", "success": False} for i in range(20)]
    result = summarize({"assigned": 20}, rows)
    assert result["assigned"] == 20
    assert result["succeeded"] == 0
    assert result["smoke_passed"] is False


def test_smoke_preregisters_twenty_independent_cases_before_attempts():
    import yaml
    from scripts.run_rgbd_smoke import DEFAULT_CONFIG, build_assignments

    assignments = build_assignments(yaml.safe_load(DEFAULT_CONFIG.read_text()))
    assert assignments["assigned"] == 20
    assert len({case["scene_hash"] for case in assignments["cases"]}) == 20
    assert [case["kind"] for case in assignments["cases"]].count("NORMAL") == 12
    assert [case["kind"] for case in assignments["cases"]].count("MISSING_TARGET") == 4


def test_missing_model_retains_every_assigned_case(tmp_path, monkeypatch):
    from scripts import run_rgbd_smoke as smoke

    def unavailable(_path):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(smoke, "load_frozen_planner", unavailable)
    summary = smoke.run_smoke(smoke.DEFAULT_CONFIG, tmp_path / "smoke")
    assert summary["assigned"] == summary["recorded"] == summary["blocked"] == 20
    assert summary["smoke_passed"] is False
    assert summary["stage_coverage"]["executed_actions"] == 0


def test_explicit_calibrated_tcp_is_consumed_without_object_truth():
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import Pose, RobotState, SkillName, TaskStep
    from cloud_edge_robot_arm.vision.execution import resolved_step

    robot = SimpleNamespace(get_state=lambda: RobotState(tcp_pose=Pose(x=0.3, y=0.0, z=0.16)))
    step = TaskStep(
        step_id="approach",
        skill=SkillName.APPROACH,
        expected_duration_ms=1000,
        timeout_ms=8000,
        retry_limit=0,
    )
    evidence = {
        "resolved_top_grasp_tcp": {"x": 0.31, "y": 0.02, "z": 0.044},
        "grounded_destination": {"x": 0.2, "y": 0.25, "z": 0.004},
        "top_grasp_support_height_m": 0.0,
        "grounded_target": {"x": 8, "y": 8, "z": 8},
    }
    result = resolved_step(step, robot, evidence)
    assert result.parameters["target_pose"] == {"x": 0.31, "y": 0.02, "z": 0.044}


def test_final_unknown_reobserves_without_completing():
    import time
    from types import SimpleNamespace

    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionEventKind
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.edge.recovery.verification_router import (
        VerificationBudget,
        VerificationBudgetState,
    )
    from cloud_edge_robot_arm.vision.execution import _VisualEpisode
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    run = _VisualEpisode.__new__(_VisualEpisode)
    run.policy = ExecutionPolicy(instruction="pick", model_snapshot_hash="a" * 64)
    run.deadline = time.monotonic() + 60
    run.budget = VerificationBudgetState.start(VerificationBudget(2, 0, 5, 60))
    run.robot = SimpleNamespace(get_state=lambda: RobotState())
    run.tracker = None
    run.records = []
    run.backend = SimpleNamespace(step=lambda **_kwargs: None)
    run.observation = RGBDObservation.model_validate(observation_payload())
    captures = []

    def fresh():
        captures.append(True)
        data = observation_payload()
        data["frame_id"] = f"new-{len(captures)}"
        run.observation = RGBDObservation.model_validate(data)
        return run.observation

    run.recapture = fresh
    assert not run.verify(
        [ConditionSpec("object_inside_target_region", target_id="object")],
        DecisionEventKind.RESULT_VERIFIED,
    )
    assert len(captures) == 2
    assert [row["route"] for row in run.records] == ["REOBSERVE", "REOBSERVE", "STOP"]
    assert all(row["event"]["kind"] == "VERIFICATION_FAILED" for row in run.records)


def test_two_separate_same_color_objects_are_not_one_confirmed_identity():
    import base64
    import io

    import numpy as np
    from PIL import Image

    from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    rgb = np.zeros((80, 80, 3), dtype="uint8") + 100
    rgb[25:35, 10:20] = [240, 20, 20]
    rgb[25:35, 35:45] = [240, 20, 20]
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    data = observation_payload()
    data.update(
        width=80,
        height=80,
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(np.ones((80, 80), dtype="<f4").tobytes()).decode(),
    )
    observation = RGBDObservation.model_validate(data)
    color = np.array([240.0, 20.0, 20.0]) / 280
    assert RGBDTargetTracker._geometry(observation, color) is None


def test_offline_evaluation_uses_labels_only_after_online_request(tmp_path, monkeypatch):
    import io
    import json
    from types import SimpleNamespace

    import numpy as np

    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft, SceneSummary
    from cloud_edge_robot_arm.datasets.rgbd import writer
    from cloud_edge_robot_arm.vision import offline_reader
    from cloud_edge_robot_arm.vision.evaluation import evaluate_model
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "seed": 7,
                "group_assignments": {"g": "test"},
                "sample_assignments": {"s": "test"},
                "counts": {"test": 1},
            }
        )
    )
    observation = RGBDObservation.model_validate(observation_payload())
    record = SimpleNamespace(
        sample_id="s",
        group_id="g",
        content_hash="independent",
        labels={
            "instruction": "Move red block.",
            "target_instance_id": 1,
            "destination_instance_id": 5,
            "instances": [
                {"role": "target", "position": [0.2, 0.1, 0.03], "half_size": [0.03, 0.03, 0.03]}
            ],
        },
    )
    array_file = io.BytesIO()
    np.save(array_file, np.array([[1, 1], [5, 0]], dtype="<i4"), allow_pickle=False)
    monkeypatch.setattr(writer, "load_records", lambda _path: [record])
    monkeypatch.setattr(offline_reader, "load_offline_observation", lambda _record: observation)
    monkeypatch.setattr(offline_reader, "resolve_payload", lambda *_args: audit)
    monkeypatch.setattr(
        offline_reader, "verified_payloads", lambda _record: {"instance": array_file.getvalue()}
    )
    requests = []

    def plan(request):
        requests.append(request)
        return PlannerDraft(
            raw_text="{}",
            parsed_json={"steps": [{}]},
            observed_scene=SceneSummary(scene_version=1, updated_at=observation.captured_at),
            observation_evidence={
                "original_pixel_target": [1, 0],
                "original_pixel_destination": [0, 1],
                "target_visible_surface": {"x": 0.22, "y": 0.1, "z": 0.06},
            },
        )

    report = evaluate_model(tmp_path, "test", SimpleNamespace(plan=plan), tmp_path / "out")
    assert report.assigned == report.succeeded == 1
    assert report.localization_errors_m[0] >= 0.019999
    assert not requests[0].scene.objects
    assert not requests[0].scene.regions
    assert requests[0].observation is observation


def test_late_cancelled_model_return_cannot_produce_dispatchable_draft():
    import time
    from types import SimpleNamespace

    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
    from cloud_edge_robot_arm.edge.recovery.verification_router import (
        VerificationBudget,
        VerificationBudgetState,
    )
    from cloud_edge_robot_arm.vision.execution import _VisualEpisode
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.request_control import ModelCallCancelled
    from tests.test_rgbd_observations import observation_payload

    cancellation = [False]
    run = _VisualEpisode.__new__(_VisualEpisode)
    run.policy = ExecutionPolicy(
        instruction="pick", model_snapshot_hash="a" * 64, cancelled=lambda: cancellation[0]
    )
    run.deadline = time.monotonic() + 60
    run.budget = VerificationBudgetState.start(VerificationBudget(2, 0, 5, 60))
    run.observation = RGBDObservation.model_validate(observation_payload())
    run.calls = 0
    run.records = []

    def plan(_request):
        cancellation[0] = True
        return PlannerDraft(raw_text="{}", parsed_json={"steps": ["GRASP"]})

    run.planner = SimpleNamespace(plan=plan, base_url="local-test-cancelled")
    with pytest.raises(ModelCallCancelled):
        run.plan()
    assert run.records == []


def _safety_gate_run(overspeed_phase):
    import time
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import Pose, RobotState, TaskContract
    from cloud_edge_robot_arm.edge.recovery.verification_router import (
        VerificationBudget,
        VerificationBudgetState,
    )
    from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
    from cloud_edge_robot_arm.vision.execution import (
        _VisualEpisode,
        research_safety_shield,
    )
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    now = datetime.now(UTC)
    contract = TaskContract.model_validate(
        {
            "task_id": "test",
            "plan_version": 1,
            "command_seq": 1,
            "timestamp": now,
            "control_mode": "PERIODIC_CLOUD_SUPERVISION",
            "issued_at": now,
            "valid_until": now + timedelta(seconds=60),
            "user_instruction": "pick",
            "scene_version": 1,
            "expected_scene_version": 1,
            "task_target": {
                "object_id": "object",
                "object_class": "block",
                "target_region_id": "region",
            },
            "steps": [
                {
                    "step_id": "move",
                    "skill": "MOVE_ABOVE",
                    "expected_duration_ms": 1000,
                    "timeout_ms": 10000,
                    "retry_limit": 0,
                    "parameters": {
                        "object_id": "object",
                        "target_pose": {"x": 0.3, "y": 0.1, "z": 0.16},
                        "tcp_velocity": 0.15,
                        "acceleration": 0.5,
                    },
                }
            ],
            "safety_constraints": {
                "max_joint_velocity": 1.5,
                "max_tcp_velocity": 0.15,
                "minimum_safe_height": 0.08,
                "workspace_id": "mujoco",
            },
            "failure_policy": {
                "local_retry_limit": 0,
                "on_timeout": "STOP",
                "on_safety_rejection": "STOP",
                "on_network_loss": "STOP",
            },
            "completion_criteria": ["gripper_released"],
        }
    )
    run = _VisualEpisode.__new__(_VisualEpisode)
    run.policy = ExecutionPolicy(instruction="pick", model_snapshot_hash="a" * 64)
    run.started_at = time.monotonic()
    run.deadline = run.started_at + 60
    run.budget = VerificationBudgetState.start(VerificationBudget(2, 0, 5, 60))
    run.observation = RGBDObservation.model_validate(observation_payload())
    run.records = []
    run.actions = 0
    run.tracker = None
    state = RobotState(tcp_pose=Pose(x=0.3, y=0.1, z=0.16), connected=True)
    run.robot = SimpleNamespace(get_state=lambda: state)
    dispatched = []

    def velocities():
        exceeded = overspeed_phase == "pre" or bool(dispatched)
        return SimpleNamespace(velocities=[-4.0 if exceeded else 0.0, 0.0, 0.5])

    run.backend = SimpleNamespace(get_joint_state=velocities, total_physics_steps=0)
    run.shield = research_safety_shield()

    def execute(**_kwargs):
        dispatched.append(True)
        return StepExecutionResult("test", "move", "MOVE_ABOVE", 1, True, None, None, 1, now)

    run.executor = SimpleNamespace(execute_attempt=execute)
    run.recapture = lambda: run.observation
    return run, contract, dispatched


@pytest.mark.parametrize("overspeed_phase", ["pre", "post"])
def test_negative_joint_overspeed_rejected_at_actual_execution_gates(overspeed_phase):
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped

    run, contract, dispatched = _safety_gate_run(overspeed_phase)
    if overspeed_phase == "pre":
        with pytest.raises(_EpisodeStopped, match="SAFETY_REJECTED"):
            run.execute(contract, contract.steps[0])
        assert dispatched == []
    else:
        assert run.execute(contract, contract.steps[0]) is False
        assert len(dispatched) == 1
    layer = "SAFETY_PRECHECK" if overspeed_phase == "pre" else "SAFETY_POSTCHECK"
    check = next(row for row in run.records if row["layer"] == layer)
    assert check["evaluation"]["decision"] == "REJECT"


def test_absent_instruction_target_cannot_become_success_by_moving_other_object():
    from scripts.run_rgbd_smoke import apply_independent_semantics

    original = {"success": True, "physical_success": True, "online_reported_complete": True}
    scored = apply_independent_semantics({"kind": "MISSING_TARGET"}, original)
    assert original["success"] is True
    assert scored["visual_episode_success"] is True
    assert scored["physical_success"] is True
    assert scored["semantic_success"] is False
    assert scored["task_success"] is False
    assert scored["success"] is False
    assert scored["false_completion"] is True
    assert scored["semantic_used_for_online_routing"] is False


def _tracked_scene(frame, *, split_depth=None, moved_pixels=0):
    import base64
    import io
    from datetime import UTC, datetime

    import numpy as np
    from PIL import Image

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    rgb = np.zeros((40, 40, 3), dtype="uint8") + 100
    depth = np.zeros((40, 40), dtype="<f4") + 1.2
    rgb[10:22, 8 + moved_pixels : 20 + moved_pixels] = [240, 20, 20]
    depth[10:22, 8 + moved_pixels : 20 + moved_pixels] = 1.0
    rgb[26:36, 26:36] = [20, 240, 20]
    if split_depth is not None:
        rgb[10:22, 13 + moved_pixels : 15 + moved_pixels] = [100, 100, 100]
        depth[10:22, 13 + moved_pixels : 15 + moved_pixels] = split_depth
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    return RGBDObservation(
        frame_id=frame,
        captured_at=datetime.now(UTC),
        sim_time_s=1.0,
        width=40,
        height=40,
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        intrinsics=(100.0, 100.0, 20.0, 20.0),
        camera_to_world=(
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        source="mujoco_camera",
        episode_id="same",
        calibration_version="one",
    )


@pytest.mark.parametrize("occluding_depth,visible", [(0.8, True), (1.2, False)])
def test_temporal_fragments_require_actual_foreground_depth(occluding_depth, visible):
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker

    tracker = RGBDTargetTracker(
        _tracked_scene("initial"),
        {
            "original_pixel_target": [10, 12],
            "original_pixel_destination": [30, 30],
            "top_grasp_support_height_m": 0.0,
        },
    )
    facts = tracker.facts(_tracked_scene("after", split_depth=occluding_depth), RobotState())
    assert ("target_visible" in facts) is visible
    if visible:
        assert facts["target_visible"]["measured_values"]["temporal_identity"]["occlusion_verified"]


def test_transport_prediction_uses_confirmed_contact_and_tcp_motion():
    from cloud_edge_robot_arm.contracts import Pose, RobotState
    from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker

    tracker = RGBDTargetTracker(
        _tracked_scene("initial"),
        {
            "original_pixel_target": [10, 12],
            "original_pixel_destination": [30, 30],
            "top_grasp_support_height_m": 0.0,
        },
    )
    attached = RobotState(
        gripper_open=False, holding_object_id="object", tcp_pose=Pose(x=0.0, y=0.0, z=0.1)
    )
    tracker.facts(_tracked_scene("attached"), attached)
    moved = attached.model_copy(update={"tcp_pose": Pose(x=0.02, y=0.0, z=0.1)})
    facts = tracker.facts(_tracked_scene("moved", split_depth=0.8, moved_pixels=2), moved)
    measured = facts["target_visible"]["measured_values"]["temporal_identity"]
    assert measured["prediction_source"] == "BILATERAL_CONTACT_AND_TCP_DISPLACEMENT"
    assert measured["predicted_displacement_m"] == pytest.approx([0.02, 0.0, 0.0])


def test_interrupted_physical_action_is_retained_in_action_denominator():
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision.request_control import ModelCallCancelled

    run, contract, _ = _safety_gate_run("partial")

    def interrupted(**_kwargs):
        run.backend.total_physics_steps += 7
        raise ModelCallCancelled("cancelled after stepping")

    run.executor = SimpleNamespace(execute_attempt=interrupted)
    with pytest.raises(ModelCallCancelled):
        run.execute(contract, contract.steps[0])
    assert run.actions == 1
    partial = next(row for row in run.records if row["layer"] == "PARTIAL_SKILL_RETURN")
    assert partial["physics_steps"] == 7
    assert partial["complete"] is False


def test_initial_estop_routes_hard_stop_before_model_or_action():
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped

    run, _, dispatched = _safety_gate_run("safe")
    state = run.robot.get_state().model_copy(update={"estop_engaged": True})
    run.robot = SimpleNamespace(get_state=lambda: state)

    def forbidden():
        pytest.fail("model must not be called with an existing hard safety fault")

    run.plan = forbidden
    with pytest.raises(_EpisodeStopped, match="SAFETY_REJECTED"):
        run.run_online()
    assert dispatched == []
    assert run.records[-1]["route"] == "STOP"
    assert run.records[-1]["conditions"][0]["measured_values"]["hard_safety_fault"]


def test_model_wait_is_bounded_by_shorter_verification_deadline(monkeypatch):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision import request_control

    run, _, _ = _safety_gate_run("safe")
    run.budget.deadline_at = datetime.now(UTC) + timedelta(seconds=0.2)
    run.calls = 0
    run.planner = SimpleNamespace(plan=lambda _request: None, base_url="deadline-test")
    budgets = []

    def bounded(_call, **kwargs):
        budgets.append(kwargs["timeout_s"])
        raise request_control.ModelCallTimedOut("expired")

    monkeypatch.setattr(request_control, "bounded_model_call", bounded)
    with pytest.raises(request_control.ModelCallTimedOut):
        run.plan()
    assert 0 < budgets[0] <= 0.2


def test_temporal_track_rejects_new_same_color_candidate_outside_original_support():
    import base64
    import io

    import numpy as np
    from PIL import Image

    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    initial = _tracked_scene("initial")
    tracker = RGBDTargetTracker(
        initial,
        {
            "original_pixel_target": [10, 12],
            "original_pixel_destination": [30, 30],
            "top_grasp_support_height_m": 0.0,
        },
    )
    new = _tracked_scene("new", split_depth=0.8)
    rgb = np.array(Image.open(io.BytesIO(base64.b64decode(new.rgb_png_base64))))
    rgb[2:6, 30:34] = [240, 20, 20]
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    changed = new.model_dump()
    changed.update(rgb_png_base64=base64.b64encode(stream.getvalue()).decode(), checksum_sha256="")
    ambiguous = RGBDObservation.model_validate(changed)
    assert tracker.facts(ambiguous, RobotState()) == {}


def test_depth_mixing_at_color_boundary_is_excluded_but_interior_mismatch_is_not():
    import base64

    import numpy as np

    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    def with_bad_depth(interior):
        observation = _tracked_scene("after", split_depth=0.8)
        depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(40, 40)
        if interior:
            depth[14:18, 16:19] = 0.8
        else:
            depth[10:22, 8] = 0.8
        values = observation.model_dump()
        values.update(
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(), checksum_sha256=""
        )
        return RGBDObservation.model_validate(values)

    tracker = RGBDTargetTracker(
        _tracked_scene("initial"),
        {
            "original_pixel_target": [10, 12],
            "original_pixel_destination": [30, 30],
            "top_grasp_support_height_m": 0.0,
        },
    )
    good = tracker.facts(with_bad_depth(False), RobotState())
    assert (
        good["target_visible"]["measured_values"]["temporal_identity"]["excluded_boundary_pixels"]
        == 12
    )
    assert tracker.facts(with_bad_depth(True), RobotState()) == {}


def _lift_hold_run(*, hidden=False, lose_contact_at=None, lifted=True):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import RobotState

    run, _, _ = _safety_gate_run("safe")
    backend = SimpleNamespace(total_physics_steps=0, _config=SimpleNamespace(physics_dt_s=0.01))
    backend.get_sim_time = lambda: 1.0 + backend.total_physics_steps * 0.01
    state = RobotState(gripper_open=False, holding_object_id="object", connected=True)
    run.robot = SimpleNamespace(get_state=lambda: state)
    run.require_continuous_grasp = False

    def step(*, steps):
        for _ in range(steps):
            backend.total_physics_steps += 1
            if lose_contact_at == backend.total_physics_steps:
                state.holding_object_id = None
            run.monitor_physics_state()

    backend.step = step
    run.backend = backend
    run.count = 0

    def capture():
        run.count += 1
        observation = _tracked_scene(f"hold-{run.count}")
        run.observation = observation.model_copy(update={"sim_time_s": backend.get_sim_time()})
        return run.observation

    run.recapture = capture
    run.recapture()

    def facts(observation, _state):
        if hidden:
            return {}
        return {
            "target_visible": {
                "source": "rgbd_estimate",
                "observation_id": observation.observation_id,
                "target_id": "object",
                "identity_confirmed": True,
                "value": True,
                "pixel": [10, 12],
                "measured_values": {"center": [0.0, 0.0, 1.1 if lifted else 1.0]},
            }
        }

    run.tracker = SimpleNamespace(initial={"center": [0.0, 0.0, 1.0]}, facts=facts)
    return run


def test_lift_hold_steps_real_time_and_records_visible_stability():
    run = _lift_hold_run()
    assert run.hold_lift()
    assert run.backend.total_physics_steps >= 60
    assert run.count >= 7
    record = run.records[-1]
    assert record["route"] == "CONTINUE"
    stable = record["visual_facts"]["object_stable"]["measured_values"]
    assert stable["observed_sim_duration_s"] >= 0.6
    assert stable["max_displacement_m"] == 0.0
    assert stable["continuous_bilateral_contact"] is True


@pytest.mark.parametrize("hidden,lifted", [(True, True), (False, False)])
def test_lift_hold_cannot_substitute_tcp_for_rgbd_height(hidden, lifted):
    run = _lift_hold_run(hidden=hidden, lifted=lifted)
    assert run.hold_lift() is False
    assert run.records[-1]["route"] == "STOP"
    assert all(row.get("route") != "CONTINUE" for row in run.records)


def test_lift_hold_stops_on_first_lost_contact_and_preserves_partial_steps():
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped

    run = _lift_hold_run(lose_contact_at=3)
    with pytest.raises(_EpisodeStopped, match="GRASP_LOST_DURING_LIFT_HOLD"):
        run.hold_lift()
    assert run.backend.total_physics_steps == 3
    assert run.require_continuous_grasp is False
    record = next(row for row in run.records if row["layer"] == "PASSIVE_OBSERVATION")
    assert record["physics_steps"] == 3
    assert record["complete"] is False
