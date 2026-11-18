"""组件诊断保留真实机器人硬停止，未知视觉支持不能升级为可见。"""

import importlib
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from tests.test_visual_worker_owner import running as running


@pytest.mark.parametrize("damage", ["released", "changed_attempt"])
def test_component_poll_rechecks_full_concrete_lease_and_attempt(
    running, damage  # noqa: F811 - pytest imports and injects this concrete SQLite fixture.
):
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    repository, job, lease, attempt = running
    worker = SimpleNamespace(
        repository=repository,
        worker_id=lease.worker_id,
        _heartbeat_failed=threading.Event(),
        _frozen_operational_time_mode=None,
    )
    worker._raise_if_cancelled_or_timed_out = lambda *args: (
        SimulationWorker._raise_if_cancelled_or_timed_out(worker, *args)
    )
    start = time.monotonic()
    module.check_component_lease(worker, job, start, expected_attempt=attempt.attempt)
    if damage == "released":
        repository.release_lease(lease.lease_id)
    else:
        repository.finish_open_attempts(job.job_id, result="FAILED", error="software-only")
        repository.start_attempt(job.job_id, worker_id=lease.worker_id)
    with pytest.raises(module.ComponentStopped, match="LEASE_SOURCE"):
        module.check_component_lease(worker, job, start, expected_attempt=attempt.attempt)


@pytest.mark.parametrize(
    "damage,reason", [("position", "HARD_JOINT_LIMIT"), ("velocity", "HARD_JOINT_VELOCITY")]
)
def test_real_joint_feedback_stops_component_before_next_command(damage, reason):
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    backend = MuJoCoPhysicsBackend()
    try:
        backend.initialize(SimulatorConfig())
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=42001))
        robot = MuJoCoSkillRobot(backend)
        module.check_component_hard_state(backend, robot)
        if damage == "position":
            backend._data.qpos[0] = 2.91
        else:
            backend._data.qvel[0] = 3.01
        with pytest.raises(module.ComponentStopped, match=reason):
            module.check_component_hard_state(backend, robot)
        assert backend.total_physics_steps == 0
    finally:
        backend.shutdown()


def test_missing_color_support_cannot_be_replaced_by_proprioception():
    from tests.test_molmo_grounded_planner import request_scene

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    observation = request_scene().observation
    _, visible = module._visible_support(observation, np.array([0.8, 0.1, 0.1]))
    assert visible["visible_pixels"] >= 4
    assert visible["metric_error_bound_m"] is None
    with pytest.raises(module.ComponentStopped, match="IDENTITY"):
        module._visible_support(observation, np.array([0.1, 0.1, 0.8]))


def test_zero_depth_cannot_support_component_identity():
    import base64

    from tests.test_molmo_grounded_planner import request_scene
    from tests.test_molmo_revalidation import rebuild

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    observation = request_scene().observation
    invalid = rebuild(
        observation,
        depth_float32_base64=base64.b64encode(
            np.zeros(observation.width * observation.height, dtype="<f4").tobytes()
        ).decode(),
    )
    with pytest.raises(module.ComponentStopped, match="DEPTH"):
        module._visible_support(invalid, np.array([0.8, 0.1, 0.1]))


def test_split_visible_support_unions_inside_reference_and_rejects_outside_decoy():
    import base64
    import io

    from PIL import Image

    from tests.test_molmo_grounded_planner import request_scene
    from tests.test_molmo_revalidation import rebuild

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    observation = request_scene().observation
    green = np.array([0.08, 0.85, 0.08])
    ref_mask, base_info = module._visible_support(observation, green)
    # 模拟机械臂横跨绿色区域将其分割成两块（均在参考掩码内部）
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as src:
        rgb = np.asarray(src.convert("RGB")).copy()
    ys, xs = np.nonzero(ref_mask)
    mid_x = int(xs.mean())
    split_rgb = rgb.copy()
    split_rgb[ys, mid_x - 1 : mid_x + 2] = [180, 180, 180]
    buf = io.BytesIO()
    Image.fromarray(split_rgb).save(buf, format="PNG")
    split_obs = rebuild(observation, rgb_png_base64=base64.b64encode(buf.getvalue()).decode())

    with pytest.raises(module.ComponentStopped, match="IDENTITY"):
        module._visible_support(split_obs, green)
    selected, info = module._visible_support(split_obs, green, reference_mask=ref_mask)
    assert info["visible_pixels"] < base_info["visible_pixels"]
    assert np.all(selected <= ref_mask)

    # 若在参考掩码之外存在外来同色连通块，即便提供 reference_mask 也必须拒绝
    decoy_rgb = split_rgb.copy()
    decoy_rgb[2:8, 2:8] = [20, 240, 20]
    buf2 = io.BytesIO()
    Image.fromarray(decoy_rgb).save(buf2, format="PNG")
    decoy_obs = rebuild(observation, rgb_png_base64=base64.b64encode(buf2.getvalue()).decode())
    with pytest.raises(module.ComponentStopped, match="IDENTITY"):
        module._visible_support(decoy_obs, green, reference_mask=ref_mask)


@pytest.mark.parametrize("damage", ["job", "policy", "camera", "nonbool"])
def test_continuous_servo_cannot_bypass_exact_job_role_binding(damage):
    from dataclasses import asdict

    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import VisualServoConfig

    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_components")
    parameters = {"sol_molmo_visual_servo": True, "sol_molmo_camera_position_m": "[0.35,0,1.4]"}
    policy = {"visual_servo": asdict(VisualServoConfig()), "camera_position_m": [0.35, 0, 1.4]}
    if damage == "job":
        parameters["sol_molmo_visual_servo"] = False
    elif damage == "policy":
        policy["visual_servo"]["max_correction_m"] = 1.0
    elif damage == "camera":
        parameters["sol_molmo_camera_position_m"] = "[0.36,0,1.4]"
    else:
        parameters["sol_molmo_visual_servo"] = 1
    with pytest.raises(ValueError):
        module.component_servo_settings(parameters, policy)


@pytest.mark.parametrize("fault", [
    None, "no_clearance", "other_task", "other_step", "other_start", "continuation",
    "holding", "closed", "lateral",
])
def test_retreat_depth_reobservation_requires_bound_empty_vertical_clearance(fault):
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.edge.safety.clearance import VerticalClearancePath
    from cloud_edge_robot_arm.research.sol_molmo_components import (
        _retreat_clearance_allows_depth_reobserve,
    )

    path = VerticalClearancePath("task", "8a", "RETREAT", (0.20, 0.20, 0.05),
                                (0.20, 0.20, 0.16), 0.08)
    robot = SimpleNamespace(
        gripper_open=fault != "closed",
        holding_object_id="object" if fault == "holding" else None,
        tcp_pose=Pose(x=0.21 if fault == "other_start" else 0.20, y=0.20, z=0.05),
    )
    step = SimpleNamespace(
        step_id="8b" if fault == "other_step" else "8a", skill=SimpleNamespace(value="RETREAT"),
        parameters={"target_pose": {"x": 0.21 if fault == "lateral" else 0.20,
                                    "y": 0.20, "z": 0.16}},
    )
    allowed = _retreat_clearance_allows_depth_reobserve(
        None if fault == "no_clearance" else path, step, robot,
        task_id="other" if fault == "other_task" else "task",
        minimum_height_m=0.08, continuation=fault == "continuation",
    )
    assert allowed is (fault is None)


@pytest.mark.parametrize("eligible", [False, True])
def test_retreat_refresh_requires_eligible_clearance_and_current_frame(monkeypatch, eligible):
    from cloud_edge_robot_arm.research import sol_molmo_components as components

    observation = SimpleNamespace(observation_id="accepted-clearance")
    marker = SimpleNamespace(observation_id=observation.observation_id)
    feedback = SimpleNamespace(last_observation=observation, last_accepted_marker=marker)

    def propose(frame, estimate, *_rest):
        assert frame.observation_id == estimate.observation_id == "accepted-clearance"
        return {"observation_id": frame.observation_id}

    monkeypatch.setattr(components, "_current_transport_view_proposals", propose)
    result = components._refresh_transport_camera_proposal(
        "RETREAT", feedback, None, "fixture", None, 0.07, None, retreat_clearance=eligible,
    )
    assert result == ({"observation_id": "accepted-clearance"} if eligible else None)


@pytest.mark.parametrize("fault", [None, "counter", "time", "joint", "wrong_camera"])
def test_component_sample_guards_backend_and_only_new_camera_command(fault):
    from cloud_edge_robot_arm.research.sol_molmo_components import (
        ComponentStopped,
        _check_component_camera_sample,
    )

    class Backend:
        total_physics_steps = 7
        sim_time = 0.125
        _command_records = [object()] * 128

        def get_sim_time(self):
            return self.sim_time

    backend = Backend()
    cursor = len(backend._command_records)
    position, aim = (0.2, -0.1, 0.8), (0.2, 0.2, 0.1)
    row = {"type": "camera_position", "accepted": True, "position_m": list(position),
           "look_at_m": list(aim), "physics_step": 7, "sim_time_s": 0.125,
           "command_seq": cursor + 1}
    if fault == "counter":
        backend.total_physics_steps += 1
    elif fault == "time":
        backend.sim_time += 0.01
    elif fault == "joint":
        row["type"] = "joint_target"
    elif fault == "wrong_camera":
        row["position_m"] = (0.2, -0.2, 0.8)
    backend._command_records = [*backend._command_records, row]
    if fault is None:
        end = _check_component_camera_sample(
            backend, 7, 0.125, cursor, camera_move=(position, aim),
        )
        assert end == cursor + 1
        assert _check_component_camera_sample(backend, 7, 0.125, end) == end
    else:
        with pytest.raises(ComponentStopped, match="SERVO_CAMERA_SAMPLE_"):
            _check_component_camera_sample(backend, 7, 0.125, cursor, camera_move=(position, aim))
