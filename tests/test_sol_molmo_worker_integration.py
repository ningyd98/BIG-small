"""真实SQLite/MuJoCo/worker软件集成；仅外部云与权重由协议替身替代。"""

import base64
import hashlib
import importlib
import inspect
import io
import json
import threading

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
from tests.test_sol_molmo_single_episode import selected_profile


class RGBPointFixture:
    """仅在测试替代神经网络；从实际传入RGB选择可见色块内部点。"""

    def __init__(self):
        self.calls = 0
        self.model_loads_started = 0

    @property
    def generation_calls_started(self):
        return self.calls

    @property
    def generation_calls_completed(self):
        return self.calls

    def point(self, observation, phrase):
        assert threading.current_thread() is threading.main_thread()
        self.calls += 1
        with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as source:
            rgb = np.asarray(source.convert("RGB"), dtype=float)
        r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
        mask = (
            (r > 1.5 * g) & (r > 1.5 * b) & (r > 80)
            if "red block" in phrase
            else (g > 1.3 * r) & (g > 1.3 * b) & (g > 50)
        )
        y, x = np.nonzero(mask)
        assert len(x) > 20
        u, v = int(np.median(x)), int(np.median(y))
        raw = (
            f'<points coords="1 1 {round(u * 1000 / observation.width)} '
            f'{round(v * 1000 / observation.height)}">visible support</points>'
        )
        return BoundPointResult(
            parse_native_point(raw),
            observation.checksum_sha256,
            observation.evidence()["rgb_sha256"],
            hashlib.sha256(phrase.encode()).hexdigest(),
            {"evidence_scope": "SOFTWARE_ONLY_RGB_POINT_FIXTURE"},
        )


@pytest.mark.parametrize(
    "through_entry,after_capture_fails,scene_split,servo,fault",
    [
        (False, False, None, False, None),
        (True, False, None, False, None),
        (False, True, None, False, None),
        (True, False, "held-out", False, None),
        (True, False, None, True, None),
        pytest.param(True, True, None, False, "before", id="before-and-after-fail"),
        pytest.param(True, False, None, False, "initialize", id="outer-initialize-fails"),
        pytest.param(True, False, None, True, "servo", id="servo-initialize-fails"),
    ],
)
def test_real_worker_runs_explicit_component_diagnostic_with_safety_and_physical_evidence(
    tmp_path, monkeypatch, through_entry, after_capture_fails, scene_split, servo, fault
):
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot

    calls = []
    original_stop = MuJoCoSkillRobot.safe_stop
    original_shutdown = MuJoCoPhysicsBackend.shutdown

    def safe_stop(robot, **kwargs):
        calls.append("safe_stop")
        return original_stop(robot, **kwargs)

    def shutdown(backend):
        calls.append("shutdown")
        return original_shutdown(backend)

    class UnprintableValueError(ValueError):
        def __str__(self):
            raise AssertionError("unexpected formatting of an exception")

        def __getattribute__(self, name):
            if name in {"args", "__traceback__"}:
                raise AssertionError("unexpected overridden exception attribute access")
            return super().__getattribute__(name)

    sensitive = "Bearer EXCEPTION_SECRET_SENTINEL at /private/EXCEPTION_PATH_SENTINEL"

    def fail_initialization(*args, **kwargs):
        raise ValueError("model_xml and model_parameters are mutually exclusive")

    def fail_servo_feedback(*args, **kwargs):
        raise ValueError("servo MuJoCo calibration does not match frame intrinsics and pose")

    monkeypatch.setattr(MuJoCoSkillRobot, "safe_stop", safe_stop)
    monkeypatch.setattr(MuJoCoPhysicsBackend, "shutdown", shutdown)
    if fault == "initialize":
        monkeypatch.setattr(MuJoCoPhysicsBackend, "initialize", fail_initialization)
    if fault == "servo":
        monkeypatch.setattr(
            "cloud_edge_robot_arm.vision.servo.OpenCVServoFeedback", fail_servo_feedback,
        )

    monkeypatch.setenv("MUJOCO_GL", "egl")
    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_single_episode")
    if after_capture_fails:
        from cloud_edge_robot_arm.vision import capture

        original_save = capture.save_captured_frame

        def save_frame(captured, destination):
            if destination.name == "before" and fault == "before":
                raise UnprintableValueError(sensitive)
            if destination.name == "after":
                raise RuntimeError("injected after-capture archive failure")
            return original_save(captured, destination)

        monkeypatch.setattr(capture, "save_captured_frame", save_frame)
    database, profile, secrets = selected_profile(tmp_path)
    service = ModelControlService(
        repository=SQLiteModelProfileRepository(database), secret_store=secrets
    )
    requests = []

    class Opener:
        def open(self, request, **kwargs):
            body = json.loads(request.data)
            assert body["model"] == "gpt-6.1-sol" and "image_url" not in request.data.decode()
            requests.append(body)
            skills = [
                "MOVE_ABOVE",
                "APPROACH",
                "GRASP",
                "LIFT",
                "MOVE_TO_REGION",
                "PLACE",
                "RELEASE",
                "RETREAT",
            ]
            return io.BytesIO(
                json.dumps(
                    {"choices": [{"message": {"content": json.dumps({"skills": skills})}}]}
                ).encode()
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *args: Opener())
    assignment = module.scene_assignment(
        42001,
        "side_y_plus_id7_75mm_component_v1",
        **({"scene_split": scene_split} if scene_split else {}),
    )
    assignment["component_diagnostic"] = True
    output = tmp_path / "worker-run"
    points = RGBPointFixture()
    if scene_split:
        # Isolate state application from pose-dependent perception capability.
        # An explicit model ABSENT must stop even after a valid varied reset.
        def absent_point(observation, phrase):
            points.calls += 1
            return BoundPointResult(
                parse_native_point("ABSENT"),
                observation.checksum_sha256,
                observation.evidence()["rgb_sha256"],
                hashlib.sha256(phrase.encode()).hexdigest(),
                {"evidence_scope": "SOFTWARE_ONLY_EXPLICIT_ABSENCE"},
            )

        monkeypatch.setattr(points, "point", absent_point)
    if through_entry:
        from contextlib import nullcontext

        manifest = tmp_path / "software-model-manifest.json"
        manifest.write_text('{"scope":"SOFTWARE_ONLY"}')
        monkeypatch.setattr(module, "selected_sol_service", lambda *a, **k: service)
        monkeypatch.setattr(
            "cloud_edge_robot_arm.vision.model_resources.admit_resources",
            lambda *a, **k: nullcontext(),
        )
        monkeypatch.setattr(
            "cloud_edge_robot_arm.vision.molmo_pointing.MolmoPointProvider", lambda **k: points
        )
        result = module.run_single_episode(
            output=output,
            mode="execute",
            component_diagnostic=True,
            seed=42001,
            marker_family_id=assignment["marker_family_id"],
            profile_id=profile.profile_id,
            model_control_db=database,
            model_directory=tmp_path / "software-only-model",
            asset_manifest=manifest,
            allow_paid=True,
            **({"visual_servo": True, "camera_position_m": (0.35, 0, 1.35)} if servo else {}),
            **({"scene_split": scene_split} if scene_split else {}),
        )
    else:
        output.mkdir()
        planner, binding = module.create_molmo_opencv_bridge(
            service=service,
            profile_id=profile.profile_id,
            points=points,
            assignment=assignment,
            output=output,
            asset_manifest_sha256="a" * 64,
        )
        result = {"executed_actions": 0, "model_calls": 0}
        module.run_worker_episode(assignment, output, result, planner=planner, binding=binding)
    episode_path = output / "component/episode.json"
    episode = json.loads(episode_path.read_text())
    assert episode == result["outcome"]
    assert calls == (
        ["safe_stop", "shutdown"] if fault in {"before", "servo"} or scene_split
        else ["shutdown"]
    )
    if fault:
        assert episode["status"] == "FAILED"
        assert episode["executed_actions"] == 0
        assert episode["cloud_requests"] == len(requests)
        assert episode["local_generations"] == points.calls
        assert episode["model_calls"] == len(requests) + points.calls
        if fault == "before":
            assert episode["terminal_reason"] == "UnprintableValueError"
            assert episode["physical_success"] is False
            assert result["worker_status"] == "FAILED"
            assert len(requests) == points.calls == 0
        elif fault == "initialize":
            assert episode["terminal_reason"] == "ValueError"
            assert episode["physical_success"] is None
            assert result["worker_status"] == "FAILED"
            assert len(requests) == points.calls == 0
        else:
            assert episode["terminal_reason"] == "ValueError"
            assert episode["physical_success"] is False
            assert result["worker_status"] == "FAILED"
            assert len(requests) == 1 and points.calls == 4
        diagnostic = episode["exception"]
        if fault == "before":
            assert diagnostic["type"] == "UnprintableValueError"
            assert diagnostic["phase"] == "INITIALIZATION"
            assert diagnostic["message"] == "[redacted]"
            assert diagnostic["traceback"][-1]["function"] == "save_frame"
            assert episode["after_capture_error_type"] == "RuntimeError"
            after, = episode["secondary_exceptions"]
            assert after["type"] == "RuntimeError" and after["phase"] == "AFTER_CAPTURE"
            assert "EXCEPTION_SECRET_SENTINEL" not in episode_path.read_text()
            assert "EXCEPTION_PATH_SENTINEL" not in episode_path.read_text()
        elif fault == "initialize":
            assert diagnostic["type"] == "ValueError"
            assert diagnostic["phase"] == "INITIALIZATION"
            assert diagnostic["message"] == "model_xml and model_parameters are mutually exclusive"
            assert diagnostic["traceback"][-1]["line"] == (
                inspect.getsourcelines(fail_initialization)[1] + 1
            )
            assert diagnostic["traceback"][-1]["function"] == "fail_initialization"
        else:
            assert diagnostic["type"] == "ValueError"
            assert diagnostic["phase"] == "SERVO_INITIALIZATION"
            assert diagnostic["message"] == (
                "servo MuJoCo calibration does not match frame intrinsics and pose"
            )
            assert diagnostic["step_id"] == "step-01" and diagnostic["skill"] == "MOVE_ABOVE"
            assert diagnostic["traceback"][-1]["line"] == (
                inspect.getsourcelines(fail_servo_feedback)[1] + 1
            )
            assert diagnostic["traceback"][-1]["function"] == "fail_servo_feedback"
        assert diagnostic["traceback"][-1]["file"] == "tests/test_sol_molmo_worker_integration.py"
        assert diagnostic["traceback"][0]["function"] == "run_component_episode"
        assert "locals" not in diagnostic["traceback"][-1]
        return
    if scene_split:
        assert requests == [] and points.calls == 1
        assert result["executed_actions"] == 0
        assert result["terminal_reason"] == "COMPONENT_INITIAL_PLANNING_REJECTED"
        assert episode["exception"]["type"] == "ComponentStopped"
        assert episode["exception"]["message"] == "COMPONENT_INITIAL_PLANNING_REJECTED"
        assert episode["exception"]["phase"] == "PLANNING"
        assert result["outcome"]["native_action_qualification"] == "UNKNOWN_NOT_GRANTED"
        applied = json.loads((output / "component/scene-application.json").read_text())
        desired = assignment["component_scene"]
        assert applied["object_position_m"] == pytest.approx(desired["object_position_m"])
        assert applied["object_position_m"] != pytest.approx([0.45, 0.0, 0.035])
        assert applied["object_quaternion_wxyz"][3] == pytest.approx(
            __import__("math").sin(desired["object_yaw_rad"] / 2)
        )
        return
    assert len(requests) == 1 and points.calls == 4, result.get("terminal_reason")
    assert result["execution_scope"] == "MUJOCO_COMPONENT_DIAGNOSTIC"
    assert result["online_reported_complete"] is None
    if servo:
        outcome = result["outcome"]
        assert outcome["visual_servo_enabled"] is True
        assert outcome["camera_position_m"] == [0.35, 0, 1.35]
        servo_actions = [action for action in outcome["actions"] if "visual_servo" in action]
        assert servo_actions and servo_actions[0]["visual_servo"]["control_samples"]
        assert servo_actions[0]["controller_result"]["success"], outcome.get("terminal_reason")
        first_post = next(check for check in outcome["safety_checks"] if check["phase"] == "POST")
        assert first_post["verdict"]["allowed"], outcome.get("terminal_reason")
        dynamic = [check for check in outcome["safety_checks"] if check["phase"] == "SERVO"]
        assert len(dynamic) > 3
        assert all(check["checked_target_pose"] for check in dynamic)
        raw_frames = list((output / "component/servo-frames").rglob("observation.json"))
        archived = {json.loads(path.read_text())["observation_id"]: path for path in raw_frames}
        assert all(check["observation_id"] in archived for check in dynamic)
        for check in (dynamic[0], dynamic[-1]):
            metadata = archived[check["observation_id"]]
            values = json.loads(metadata.read_text())
            assert hashlib.sha256((metadata.parent / "depth.f32").read_bytes()).hexdigest() == (
                values["depth_sha256"]
            )
            assert len(values["camera_to_world"]) == 16
        assert result["outcome"]["native_action_qualification"] == "UNKNOWN_NOT_GRANTED"
        assert result["physical_success"] is True, outcome.get("terminal_reason")
        assert outcome["independent_physical_outcome"]["measured_lift_m"] >= 0.05
        assert outcome["independent_physical_outcome"]["hold_s"] >= 0.5
        assert outcome["independent_physical_outcome"]["placed_stable_s"] >= 1.0
        assert outcome["diagnostic_complete"] is True, outcome.get("terminal_reason")
        assert outcome["terminal_reason"] is None
        assert "exception" not in episode
        assert outcome["actions"][-1]["skill"] == "RETREAT"
        assert outcome["marker_frames"][-1]["status"] == "OBSERVED"
        return
    assert result["executed_actions"] >= 7, result.get("terminal_reason")
    assert result["physical_success"] is True
    assert result["outcome"]["native_action_qualification"] == "UNKNOWN_NOT_GRANTED"
    assert result["outcome"]["qualified_groups_added"] == 0
    assert result["outcome"]["model_calls"] == 5
    assert result["outcome"]["cloud_requests"] == 1
    assert result["outcome"]["local_generations"] == 4
    assert result["outcome"]["safety_checks"]
    assert result["outcome"]["actions"]
    assert (output / "runtime.db").is_file()
    assert (output / "events.db").is_file()
    if after_capture_fails:
        assert result["status"] == "FAILED"
        assert result["terminal_reason"] == "AFTER_CAPTURE_FAILED:RuntimeError"
        assert not result["outcome"]["diagnostic_complete"]
        assert result["outcome"]["after_capture_error_type"] == "RuntimeError"
        assert episode["exception"]["phase"] == "AFTER_CAPTURE"
        assert episode["exception"]["type"] == "RuntimeError"
        assert "secondary_exceptions" not in episode
    else:
        assert result["worker_status"] == "SUCCEEDED"
        assert result["status"] == "COMPONENTS_COMPLETED"
        assert "exception" not in episode
        assert (output / "after/marker-validation.json").is_file()
        endpoint = json.loads((output / "after/marker-validation.json").read_text())
        assert endpoint["status"] == "OBSERVED", endpoint
        assert endpoint["observed_marker_ids"] == [7]
    assert (output / "component/physical-evidence.json").is_file()

    payload = json.loads(requests[0]["messages"][1]["content"])
    assert payload["execution_scope"] == "MUJOCO_COMPONENT_DIAGNOSTIC"
    assert payload["hardware_dispatch"] is False
    assert "component_scene" not in payload and "object_yaw_rad" not in payload
