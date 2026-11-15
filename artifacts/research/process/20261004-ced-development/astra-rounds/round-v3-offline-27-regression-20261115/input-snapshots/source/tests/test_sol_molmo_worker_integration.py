"""真实SQLite/MuJoCo/worker软件集成；仅外部云与权重由协议替身替代。"""

import base64
import hashlib
import importlib
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
    "through_entry,after_capture_fails,scene_split",
    [(False, False, None), (True, False, None), (False, True, None), (True, False, "held-out")],
)
def test_real_worker_runs_explicit_component_diagnostic_with_safety_and_physical_evidence(
    tmp_path, monkeypatch, through_entry, after_capture_fails, scene_split
):
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository

    monkeypatch.setenv("MUJOCO_GL", "egl")
    module = importlib.import_module("cloud_edge_robot_arm.research.sol_molmo_single_episode")
    if after_capture_fails:
        from cloud_edge_robot_arm.vision import capture

        original_save = capture.save_captured_frame

        def save_frame(captured, destination):
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
            "scripts.probe_molmo_grounded_planner._admit_resources", lambda *a, **k: nullcontext()
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
    if scene_split:
        assert requests == [] and points.calls == 1
        assert result["executed_actions"] == 0
        assert result["terminal_reason"] == "COMPONENT_INITIAL_PLANNING_REJECTED"
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
    else:
        assert result["worker_status"] == "SUCCEEDED"
        assert result["status"] == "COMPONENTS_COMPLETED"
        assert (output / "after/marker-validation.json").is_file()
        endpoint = json.loads((output / "after/marker-validation.json").read_text())
        assert endpoint["status"] == "OBSERVED", endpoint
        assert endpoint["observed_marker_ids"] == [7]
    assert (output / "component/physical-evidence.json").is_file()

    payload = json.loads(requests[0]["messages"][1]["content"])
    assert payload["execution_scope"] == "MUJOCO_COMPONENT_DIAGNOSTIC"
    assert payload["hardware_dispatch"] is False
    assert "component_scene" not in payload and "object_yaw_rad" not in payload
