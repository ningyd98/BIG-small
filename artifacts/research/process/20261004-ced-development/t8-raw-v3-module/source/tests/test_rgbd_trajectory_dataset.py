"""T5 independent physics scoring and executed RGB-D trajectory contracts."""

from __future__ import annotations

import base64
import io
import struct
from dataclasses import replace
from datetime import UTC, datetime
from math import nan

import pytest
from PIL import Image
from pydantic import ValidationError

from cloud_edge_robot_arm.edge.robot_adapter import build_action_result

_DT = 0.005


def _sample(
    step: int,
    *,
    z: float = 0.035,
    x: float = 0.45,
    y: float = 0.0,
    left: bool = False,
    right: bool = False,
    opened: bool = True,
    speed: float = 0.0,
    contact_pairs: tuple[tuple[str, str], ...] = (),
    joint_violation: bool = False,
    self_collision: bool = False,
    self_collision_checked: bool = False,
) -> object:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import PhysicalSample

    return PhysicalSample(
        episode_id="episode-1",
        physics_step=step,
        sim_time_s=round(step * _DT, 9),
        object_position_m=(x, y, z),
        object_bottom_z_m=z - 0.035,
        object_half_extent_xy_m=(0.035, 0.035),
        object_linear_speed_m_s=speed,
        object_angular_speed_rad_s=0.0,
        region_center_xy_m=(0.2, 0.25),
        region_half_extent_xy_m=(0.08, 0.08),
        table_height_m=0.0,
        gripper_open=opened,
        left_finger_contact=left,
        right_finger_contact=right,
        contact_pairs=contact_pairs,
        joint_limit_violation=joint_violation,
        joint_velocity_violation=False,
        workspace_violation=False,
        self_collision_violation=self_collision,
        self_collision_checked_pairs=(("link4", "link6"),) if self_collision_checked else (),
    )


def _sequence(
    *,
    lift_m: float = 0.05,
    hold_s: float = 0.5,
    place_s: float = 1.0,
    placement_speed_m_s: float = 0.0,
    placement_x: float = 0.2,
) -> list[object]:
    samples = [_sample(0)]
    hold_count = round(hold_s / _DT) + 1
    for step in range(1, hold_count + 1):
        samples.append(
            _sample(
                step,
                z=0.035 + lift_m,
                left=True,
                right=True,
                opened=False,
                contact_pairs=(
                    ("left_finger_geom", "object_geom"),
                    ("right_finger_geom", "object_geom"),
                ),
            )
        )
    place_count = round(place_s / _DT) + 1
    for step in range(hold_count + 1, hold_count + place_count + 1):
        samples.append(
            _sample(
                step,
                x=placement_x,
                y=0.25,
                speed=placement_speed_m_s,
                contact_pairs=(("table", "object_geom"),),
            )
        )
    return samples


def test_script_completion_is_not_task_success() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    scripted_action = build_action_result(
        action_type="RELEASE", success=True, state_before={}, state_after={}, duration_ms=5
    )
    outcome = evaluate_evidence(
        [_sample(0), _sample(1, x=0.2, y=0.25)],
        CompletionCriteria(object_id="object", target_region_id="target_region"),
    )

    assert scripted_action.success
    assert not outcome.success
    assert outcome.failure_reason == "LIFT_BELOW_THRESHOLD"


@pytest.mark.parametrize(
    ("changes", "expected_reason"),
    [
        ({"lift_m": 0.049}, "LIFT_BELOW_THRESHOLD"),
        ({"hold_s": 0.49}, "HOLD_TOO_SHORT"),
        ({"place_s": 0.99}, "PLACE_NOT_STABLE"),
        ({"placement_speed_m_s": 0.04}, "PLACE_NOT_STABLE"),
        ({"placement_x": 0.25}, "PLACE_NOT_STABLE"),
    ],
)
def test_lift_and_place_require_stability(
    changes: dict[str, float], expected_reason: str
) -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    outcome = evaluate_evidence(
        _sequence(**changes),
        CompletionCriteria(object_id="object", target_region_id="target_region"),
    )

    assert not outcome.success
    assert outcome.failure_reason == expected_reason


def test_full_physical_sequence_succeeds_with_normal_grasp_contacts() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    outcome = evaluate_evidence(
        _sequence(), CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert outcome.success
    assert outcome.status == "SUCCESS"
    assert outcome.measured_lift_m == pytest.approx(0.05)
    assert outcome.hold_s == pytest.approx(0.5)
    assert outcome.placed_stable_s == pytest.approx(1.0)
    assert not outcome.safety_violation


def test_placement_must_still_be_stable_in_region_at_episode_end() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    evidence = _sequence()
    evidence.append(_sample(evidence[-1].physics_step + 1, x=0.45, y=0.0))
    outcome = evaluate_evidence(
        evidence, CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert not outcome.success
    assert outcome.failure_reason == "PLACEMENT_LOST"


def test_missing_or_mixed_physics_steps_fail_closed() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    sequence = _sequence()
    missing = sequence[:40] + sequence[41:]
    foreign = sequence.copy()
    foreign[50] = replace(_sample(50), episode_id="other-episode")
    criteria = CompletionCriteria(object_id="object", target_region_id="target_region")

    assert evaluate_evidence(missing, criteria).status == "INCOMPLETE"
    assert evaluate_evidence(foreign, criteria).status == "INCOMPLETE"


def test_nonfinite_physical_truth_fails_closed() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    evidence = _sequence()
    evidence[50] = replace(evidence[50], object_position_m=(0.45, 0.0, nan))
    outcome = evaluate_evidence(
        evidence, CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert outcome.status == "INCOMPLETE"
    assert outcome.failure_reason == "INVALID_PHYSICAL_EVIDENCE"


def test_settled_scene_can_start_evaluation_after_initial_physics_steps() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    settled = [
        replace(sample, physics_step=sample.physics_step + 120,
                sim_time_s=sample.sim_time_s + 0.5)
        for sample in _sequence()
    ]
    outcome = evaluate_evidence(
        settled, CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert outcome.success
    assert outcome.elapsed_s == pytest.approx(_sequence()[-1].sim_time_s)


def test_lift_baseline_uses_settled_step_but_safety_covers_initial_settling() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    settling = [_sample(step, z=0.043 - 0.0008 * step) for step in range(10)]
    executed = [
        replace(sample, physics_step=sample.physics_step + 10,
                sim_time_s=round(sample.sim_time_s + 10 * _DT, 9))
        for sample in _sequence(lift_m=0.05)
    ]
    evidence = [*settling, *executed]
    criteria = CompletionCriteria(object_id="object", target_region_id="target_region")

    assert evaluate_evidence(evidence, criteria).failure_reason == "LIFT_BELOW_THRESHOLD"
    settled = evaluate_evidence(evidence, criteria, evaluation_start_step=10)
    assert settled.success
    assert settled.measured_lift_m == pytest.approx(0.05)
    assert evaluate_evidence(
        evidence, criteria, evaluation_start_step=999
    ).failure_reason == "MISSING_EVALUATION_START"

    evidence[2] = replace(evidence[2], workspace_violation=True)
    unsafe = evaluate_evidence(evidence, criteria, evaluation_start_step=10)
    assert unsafe.status == "SAFETY_VIOLATION"
    assert "WORKSPACE_BOUNDARY" in unsafe.safety_events


def test_nonpermitted_contact_and_hard_limit_are_safety_violations() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    evidence = _sequence()
    evidence[20] = _sample(
        20,
        z=0.085,
        left=True,
        right=True,
        opened=False,
        contact_pairs=(
            ("left_finger_geom", "object_geom"),
            ("right_finger_geom", "object_geom"),
            ("left_finger_geom", "table"),
        ),
        joint_violation=True,
    )
    outcome = evaluate_evidence(
        evidence, CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert not outcome.success
    assert outcome.status == "SAFETY_VIOLATION"
    assert outcome.safety_violation
    assert "NONPERMITTED_CONTACT" in outcome.safety_events
    assert "HARD_JOINT_LIMIT" in outcome.safety_events


def test_static_distractor_table_support_is_allowed_but_robot_collision_is_not() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    criteria = CompletionCriteria(object_id="object", target_region_id="target_region")
    supported = [
        replace(sample, contact_pairs=(*sample.contact_pairs,
                                       ("table", "dataset_distractor_0_geom")))
        for sample in _sequence()
    ]
    allowed = evaluate_evidence(supported, criteria)
    assert allowed.success
    assert not allowed.safety_violation

    supported[20] = replace(
        supported[20],
        contact_pairs=(*supported[20].contact_pairs,
                       ("left_finger_geom", "dataset_distractor_0_geom")),
    )
    collision = evaluate_evidence(supported, criteria)
    assert collision.status == "SAFETY_VIOLATION"
    assert "NONPERMITTED_CONTACT" in collision.safety_events


def test_self_collision_uses_signed_distance_and_reports_checked_scope() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    evidence = _sequence()
    evidence[20] = _sample(
        20, z=0.085, left=True, right=True, opened=False,
        self_collision=True, self_collision_checked=True,
        contact_pairs=(
            ("left_finger_geom", "object_geom"),
            ("right_finger_geom", "object_geom"),
        ),
    )
    outcome = evaluate_evidence(
        evidence, CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert not outcome.success
    assert "SELF_COLLISION" in outcome.safety_events
    assert ("link4", "link6") in outcome.self_collision_checked_pairs


def test_unmeasured_self_collision_is_reported_partial() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    outcome = evaluate_evidence(
        _sequence(), CompletionCriteria(object_id="object", target_region_id="target_region")
    )

    assert outcome.success
    assert outcome.safety_assessment == "PARTIAL"


def test_nonfinite_self_collision_distance_fails_closed() -> None:
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
        sample_physical_observation,
    )

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        raw = backend.current_physics_observation()
        invalid = replace(raw, self_collision_distances_m=(("base", "link2", nan),))
        criteria = CompletionCriteria(object_id="object", target_region_id="target_region")
        sample = sample_physical_observation(invalid, criteria)
        assert not sample.self_collision_evidence_valid
        outcome = evaluate_evidence(
            [sample, replace(sample, physics_step=1, sim_time_s=0.0042)], criteria
        )
        assert outcome.status == "INCOMPLETE"
        assert outcome.failure_reason == "INVALID_PHYSICAL_EVIDENCE"
    finally:
        backend.shutdown()


def test_sampler_reads_mujoco_truth_without_mutation() -> None:
    import numpy as np

    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_episode,
        sample_physical_observation,
        sample_physical_state,
    )

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        model, data = backend._model, backend._data
        assert model is not None and data is not None
        qpos, qvel = data.qpos.copy(), data.qvel.copy()
        commands, time_s = backend.command_records, backend.get_sim_time()
        criteria = CompletionCriteria(object_id="object", target_region_id="target_region")

        sample = sample_physical_state(backend, criteria)
        converted = sample_physical_observation(backend.current_physics_observation(), criteria)
        missing_history = evaluate_episode(backend, criteria)

        assert sample == converted
        assert sample.object_position_m[2] == pytest.approx(
            float(data.xpos[model.body("object").id, 2])
        )
        assert sample.physics_step == 0
        assert not missing_history.success
        assert missing_history.status == "INCOMPLETE"
        assert np.array_equal(data.qpos, qpos)
        assert np.array_equal(data.qvel, qvel)
        assert backend.get_sim_time() == time_s
        assert backend.command_records == commands
        assert backend.total_physics_steps == 0
    finally:
        backend.shutdown()


def test_online_robot_cannot_read_evaluator_truth(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unresolved online skill cannot promote hidden MuJoCo truth to a target."""
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        robot = MuJoCoSkillRobot(backend)

        def forbidden_truth() -> None:
            raise AssertionError("online robot attempted to read evaluator truth")

        monkeypatch.setattr(backend, "current_physics_observation", forbidden_truth)
        assert robot.object_region("object") is None
        assert robot.resolve_target_pose("MOVE_ABOVE", {"object_id": "object"}) is None
        locate = robot.locate_object("object")
        move = robot.move_above("object")
        assert locate.error_code == "VISUAL_LOCALIZATION_REQUIRED"
        assert move.error_code == "TARGET_NOT_RESOLVED"
        assert locate.details["physics_steps"] == move.details["physics_steps"] == 0
        assert backend.total_physics_steps == 0

        # A genuinely executed online skill must still avoid the evaluator
        # snapshot; its target is an explicit external pose, not hidden truth.
        executed = robot.move_above(
            "object", resolved_target=Pose(x=0.45, y=0.0, z=0.16), timeout_ms=8000
        )
        assert executed.details["physics_steps"] > 0
        assert backend.total_physics_steps == executed.details["physics_steps"]
    finally:
        backend.shutdown()


def test_snapshot_conversion_applies_registered_joint_and_workspace_limits() -> None:
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        sample_physical_observation,
    )

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        raw = backend.current_physics_observation()
        altered = replace(
            raw,
            joint_velocities_rad_s=(4.0, *raw.joint_velocities_rad_s[1:]),
            tcp_position_m=(1.1, 0.0, 0.4),
        )
        criteria = CompletionCriteria(object_id="object", target_region_id="target_region")
        converted = sample_physical_observation(altered, criteria)

        assert converted.joint_velocity_violation
        assert converted.workspace_violation
    finally:
        backend.shutdown()


def test_tcp_workspace_is_robot_envelope_not_table_footprint() -> None:
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        sample_physical_observation,
    )

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        model, data, mujoco = backend._model, backend._data, backend._mujoco
        assert model is not None and data is not None and mujoco is not None
        # The capture setup parks joint1 here during reset for an unobstructed view.
        data.qpos[model.joint("joint1").qposadr[0]] = -0.8
        mujoco.mj_forward(model, data)
        raw = backend.current_physics_observation()
        criteria = CompletionCriteria(object_id="object", target_region_id="target_region")

        assert raw.tcp_position_m[1] < -0.45  # Outside the tabletop footprint.
        assert not sample_physical_observation(raw, criteria).workspace_violation
        outside = replace(raw, tcp_position_m=(0.7, 0.7, 0.5))
        assert sample_physical_observation(outside, criteria).workspace_violation
    finally:
        backend.shutdown()


def test_signed_self_collision_distance_has_one_millimetre_tolerance() -> None:
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        sample_physical_observation,
    )

    backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
    try:
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=31))
        raw = backend.current_physics_observation()
        criteria = CompletionCriteria(object_id="object", target_region_id="target_region")
        assert len(raw.self_collision_distances_m) == 33
        assert not sample_physical_observation(raw, criteria).self_collision_violation
        pair = raw.self_collision_distances_m[0][:2]
        tolerated = replace(raw, self_collision_distances_m=((*pair, -0.0005),))
        penetrated = replace(raw, self_collision_distances_m=((*pair, -0.002),))

        assert not sample_physical_observation(tolerated, criteria).self_collision_violation
        assert sample_physical_observation(penetrated, criteria).self_collision_violation
    finally:
        backend.shutdown()


def _observation(frame_id: str, sim_time_s: float, *, episode_id: str = "episode-1") -> object:
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    output = io.BytesIO()
    Image.new("RGB", (1, 1), (200, 20, 20)).save(output, format="PNG")
    return RGBDObservation(
        frame_id=frame_id,
        captured_at=datetime.now(UTC),
        sim_time_s=sim_time_s,
        width=1,
        height=1,
        rgb_png_base64=base64.b64encode(output.getvalue()).decode("ascii"),
        depth_float32_base64=base64.b64encode(struct.pack("<f", 1.0)).decode("ascii"),
        intrinsics=(1.0, 1.0, 0.0, 0.0),
        camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        source="mujoco_camera",
        episode_id=episode_id,
    )


def test_trajectory_frame_binds_action_to_next_observation() -> None:
    from cloud_edge_robot_arm.datasets.rgbd.models import TrajectoryFrame

    action = build_action_result(
        action_type="APPROACH", success=False, state_before={}, state_after={}, duration_ms=50
    )
    before = _observation("before", 1.0)
    after = _observation("after", 1.05)
    frame = TrajectoryFrame(
        observation=before,
        action=action,
        next_observation=after,
        sim_time_s=1.05,
        skill_boundary=True,
    )

    assert frame.action.action_id == action.action_id
    assert frame.next_observation.frame_id == "after"
    assert not frame.action.success  # Failed executions remain in the trajectory.
    assert TrajectoryFrame.model_validate_json(frame.model_dump_json()).sim_time_s == 1.05
    with pytest.raises(ValidationError, match="same episode"):
        TrajectoryFrame(
            observation=before, action=action,
            next_observation=_observation("foreign", 1.05, episode_id="episode-2"),
            sim_time_s=1.05, skill_boundary=True,
        )
    with pytest.raises(ValidationError, match="later"):
        TrajectoryFrame(
            observation=before, action=action,
            next_observation=_observation("earlier", 0.99),
            sim_time_s=0.99, skill_boundary=True,
        )
    with pytest.raises(ValidationError, match="next observation"):
        TrajectoryFrame(
            observation=before, action=action,
            next_observation=after, sim_time_s=1.04, skill_boundary=True,
        )
