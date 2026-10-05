"""Offline-only MuJoCo teacher and contiguous executed-action recording."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cloud_edge_robot_arm.contracts import ActionResult, Pose
from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, TrajectoryFrame
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.simulation.mujoco.backend import (
    MuJoCoPhysicsBackend,
    PhysicsStepObservation,
)
from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    EpisodeOutcome,
    PhysicalSample,
    evaluate_episode,
    sample_physical_observation,
)
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame

TeacherCase = Literal["NORMAL", "NO_CONTACT"]


class EpisodeRecorder:
    """Collect action transitions without inferring task success from the script."""

    source: Literal["GROUND_TRUTH_TEACHER"] = "GROUND_TRUTH_TEACHER"

    def __init__(self) -> None:
        self.frames: list[TrajectoryFrame] = []
        self.unframed_actions: list[ActionResult] = []
        self.physical_samples: list[PhysicalSample] = []
        self.evaluation_start_step: int | None = None
        self.execution_verified = False
        self.outcome: EpisodeOutcome | None = None

    def append(self, frame: TrajectoryFrame) -> None:
        if self.frames:
            previous = self.frames[-1]
            if frame.observation.episode_id != previous.observation.episode_id:
                raise ValueError("all teacher frames must share one episode")
            if frame.observation.observation_id != previous.next_observation.observation_id:
                raise ValueError("teacher frames must form a contiguous observation chain")
            if frame.observation.checksum_sha256 != previous.next_observation.checksum_sha256:
                raise ValueError("previous next observation differs from current observation")
            if frame.sim_time_s <= previous.sim_time_s:
                raise ValueError("teacher frame simulation time must increase")
        self.frames.append(frame)

    def _finish(self, outcome: EpisodeOutcome) -> None:
        self.outcome = outcome
        self.execution_verified = outcome.success and bool(self.frames)


def _capture(backend: MuJoCoPhysicsBackend) -> RGBDObservation:
    sensor, _, _, pass_hashes = backend.capture_sensor_frame_with_instances()
    if len(set(pass_hashes)) != 1:
        raise RuntimeError("teacher RGB-D render crossed physics states")
    return observation_from_sensor_frame(sensor, source="mujoco_camera")


def _dwell(robot: MuJoCoSkillRobot, seconds: float, purpose: str) -> ActionResult:
    backend = robot._backend
    config = backend._config
    if config is None:
        raise RuntimeError("MuJoCo backend is not initialized")
    steps = max(1, int(round(seconds / config.physics_dt_s)))
    before = robot.get_state().model_dump(mode="json")
    started_at = datetime.now(UTC)
    backend.step(steps=steps)
    after = robot.get_state().model_dump(mode="json")
    return build_action_result(
        action_type="OBSERVE",
        success=True,
        state_before=before,
        state_after=after,
        duration_ms=int(round(steps * config.physics_dt_s * 1000)),
        details={"physics_steps": steps, "purpose": purpose},
        started_at=started_at,
    )


def run_teacher_episode(
    scene: SceneSpec,
    robot: MuJoCoSkillRobot,
    recorder: EpisodeRecorder,
    *,
    case: TeacherCase = "NORMAL",
    settle_steps: int = 120,
    physical_observer: Callable[[PhysicsStepObservation], None] | None = None,
    action_observer: Callable[[Mapping[str, Any]], None] | None = None,
) -> EpisodeOutcome:
    """Execute an offline ground-truth teacher inside one prepared MuJoCo episode.

    The caller applies ``scene`` before invoking this function. Simulator truth
    is used only here to form explicit targets and by the independent scorer;
    it is never offered to the online robot as a lookup capability.
    """
    if case not in {"NORMAL", "NO_CONTACT"} or not 0 <= settle_steps <= 10000:
        raise ValueError("unsupported teacher case or settling budget")
    if recorder.frames or recorder.unframed_actions or recorder.outcome is not None:
        raise ValueError("teacher recorder must be empty at episode start")
    backend = robot._backend
    config = backend._config
    if config is None or backend._episode_id is None or backend._scenario is None:
        raise RuntimeError("MuJoCo scene is not initialized and reset")
    if backend._scenario.scenario_id != scene.group_id:
        raise ValueError("teacher scene and backend episode disagree")
    asset_hash = hashlib.sha256(Path(config.model_path).read_bytes()).hexdigest()
    if scene.asset_family_hash != asset_hash:
        raise ValueError("teacher scene asset family differs from current robot model")
    criteria = CompletionCriteria(object_id="object", target_region_id="target_region")
    initial_snapshot = backend.current_physics_observation()
    recorder.physical_samples.append(sample_physical_observation(initial_snapshot, criteria))
    if physical_observer is not None:
        backend._in_observer_callback = True
        try:
            physical_observer(initial_snapshot)
        finally:
            backend._in_observer_callback = False

    def on_step(snapshot: PhysicsStepObservation) -> None:
        recorder.physical_samples.append(sample_physical_observation(snapshot, criteria))
        if physical_observer is not None:
            physical_observer(snapshot)

    with backend.observe_physics_steps(on_step):
        if settle_steps:
            backend.step(steps=settle_steps)
        recorder.evaluation_start_step = backend.total_physics_steps
        initial_truth = sample_physical_observation(
            backend.current_physics_observation(), criteria
        )
        target = initial_truth.object_position_m
        destination = initial_truth.region_center_xy_m
        half_height = target[2] - initial_truth.object_bottom_z_m
        observation = _capture(backend)

        def execute(action: Callable[[], ActionResult]) -> bool:
            nonlocal observation
            before_step = backend.total_physics_steps
            command_start = len(backend.command_records) + 1
            result = action()
            details = dict(result.details)
            details["teacher_source"] = "GROUND_TRUTH_TEACHER"
            if "target_pose" in details:
                details["resolved_target_source"] = "GROUND_TRUTH_TEACHER"
            result = result.model_copy(update={"details": details})
            actual_steps = backend.total_physics_steps - before_step
            if action_observer is not None:
                event = {
                    "result": result.model_dump(mode="json"),
                    "episode_id": backend._episode_id,
                    "start_step": before_step,
                    "end_step": backend.total_physics_steps,
                    "command_seq_start": command_start,
                    "command_seq_end": len(backend.command_records) + 1,
                }
                backend._in_observer_callback = True
                try:
                    action_observer(event)
                finally:
                    backend._in_observer_callback = False
            if actual_steps == 0:
                recorder.unframed_actions.append(result)
                return False
            if result.details.get("physics_steps") != actual_steps:
                raise RuntimeError("teacher action physics step count disagrees with backend")
            try:
                next_observation = _capture(backend)
            except Exception:
                recorder.unframed_actions.append(result)
                raise
            recorder.append(TrajectoryFrame(
                observation=observation,
                action=result,
                next_observation=next_observation,
                sim_time_s=next_observation.sim_time_s,
                skill_boundary=True,
            ))
            observation = next_observation
            return result.success

        if case == "NO_CONTACT":
            execute(lambda: robot.grasp("object", timeout_ms=1000))
        else:
            planned_actions: tuple[Callable[[], ActionResult], ...] = (
                lambda: robot.move_above(
                    "object", resolved_target=Pose(x=target[0], y=target[1], z=0.16),
                    timeout_ms=8000,
                ),
                lambda: robot.approach(
                    "object", resolved_target=Pose(
                        x=target[0], y=target[1], z=target[2] + 0.01,
                    ), timeout_ms=8000,
                ),
                lambda: robot.grasp("object", timeout_ms=1000),
                lambda: robot.lift(height_m=0.10, timeout_ms=8000),
                lambda: _dwell(robot, 0.5, "post_lift_stability"),
                lambda: robot.move_to_region(
                    "target_region", resolved_target=Pose(
                        x=destination[0], y=destination[1], z=0.16,
                    ), timeout_ms=10000,
                ),
                lambda: robot.place(
                    "target_region", resolved_target=Pose(
                        x=destination[0], y=destination[1], z=half_height + 0.01,
                    ), timeout_ms=8000,
                ),
                lambda: robot.release(timeout_ms=1000),
                lambda: _dwell(robot, 1.2, "post_release_stability"),
            )
            for action in planned_actions:
                if not execute(action):
                    break

    outcome = evaluate_episode(
        backend,
        criteria,
        evidence=recorder.physical_samples,
        evaluation_start_step=recorder.evaluation_start_step,
    )
    recorder._finish(outcome)
    return outcome
