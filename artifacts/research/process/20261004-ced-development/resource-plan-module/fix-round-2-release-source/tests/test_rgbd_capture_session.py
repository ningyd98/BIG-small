"""A continuous camera session must produce synchronized, identifiable real frames."""

from __future__ import annotations

import json
import math
import struct
from datetime import UTC, datetime, timedelta

import mujoco
import pytest

from cloud_edge_robot_arm.simulation.config import SimulatorConfig


def test_render_passes_share_frozen_state() -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        first = session.capture_with_instances()
        second = session.capture_with_instances()
        assert len(first.pass_state_hashes) == 3
        assert len(set(first.pass_state_hashes)) == 1
        assert first.physics_state_hash == first.pass_state_hashes[0]
        assert first.observation.sim_time_s == second.observation.sim_time_s == 0.0
        assert first.observation.observation_id != second.observation.observation_id
        assert first.observation.scene_id == "S01_NORMAL_STATIC"
        assert first.observation.episode_id == second.observation.episode_id
        assert first.observation.calibration_version
        assert len(first.instance_ids) == 320 * 240


def test_plane_back_projection_within_5mm() -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        captured = session.capture_with_instances()
        table_ids = [key for key, value in captured.instance_labels.items() if value == "table"]
        assert len(table_ids) == 1
        width = captured.observation.width
        pixels = [
            (index % width, index // width)
            for index, geom_id in enumerate(captured.instance_ids)
            if geom_id == table_ids[0]
        ]
        assert len(pixels) > 1000
        samples = pixels[:: max(1, len(pixels) // 20)][:20]
        errors = [abs(captured.observation.world_point(pixel).z) for pixel in samples]
        assert max(errors) <= 0.005, f"table plane z=0 errors: {errors}"


def test_capture_session_reuses_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    renderer = mujoco.Renderer
    created = []

    def counted_renderer(*args: object, **kwargs: object) -> mujoco.Renderer:
        result = renderer(*args, **kwargs)
        created.append(result)
        return result

    monkeypatch.setattr(mujoco, "Renderer", counted_renderer)
    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        first = session.capture()
        second = session.capture()
        assert first.observation_id != second.observation_id
        assert len(created) == 1
    assert len(created) == 1
    with pytest.raises(RuntimeError):
        created[0].render()


def test_capture_session_supports_maximum_resolution() -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    config = SimulatorConfig(camera_width=1280, camera_height=720)
    with MuJoCoCaptureSession(config) as session:
        captured = session.capture_with_instances()
        observation = captured.observation
        assert (observation.width, observation.height) == (1280, 720)
        assert len(observation.depth_values()) == 1280 * 720
        assert len(observation.valid_mask_bytes()) == 1280 * 720
        assert len(captured.instance_ids) == 1280 * 720
        assert len(captured.pass_state_hashes) == 3
        assert len(set(captured.pass_state_hashes)) == 1


def test_camera_preserves_larger_offscreen_framebuffer() -> None:
    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

    model = mujoco.MjModel.from_xml_path(SimulatorConfig().model_path)
    model.vis.global_.offwidth = 960
    model.vis.global_.offheight = 600
    camera = MuJoCoRGBDCamera(mujoco, model, width=320, height=240)
    try:
        assert model.vis.global_.offwidth == 960
        assert model.vis.global_.offheight == 600
    finally:
        camera.close()


def test_capture_artifacts_include_raw_depth_mask_instances_and_calibration(tmp_path) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession, save_captured_frame

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        frame = session.capture_with_instances()
        assert math.isfinite(frame.observation.depth_range()[0])
        assert frame.observation.checksum_sha256
        paths = save_captured_frame(frame, tmp_path)
    depth = struct.unpack(
        f"<{frame.observation.width * frame.observation.height}f", paths["depth"].read_bytes()
    )
    assert max(depth) > 0
    assert paths["mask"].read_bytes() == frame.observation.valid_mask_bytes()
    assert len(paths["instances"].read_bytes()) == len(depth) * 4
    metadata = json.loads(paths["observation"].read_text())
    assert metadata["physics_state_hash"] == frame.physics_state_hash
    assert metadata["pass_state_hashes"] == list(frame.pass_state_hashes)
    assert "instance_ids" not in frame.observation.model_dump()


def test_concurrent_physics_change_rejects_mixed_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with pytest.raises(RuntimeError, match="physics state changed"):
        with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
            backend = session._backend
            assert backend._camera is not None and backend._data is not None
            renderer_type = type(backend._camera._renderer)
            original_render = renderer_type.render
            count = 0

            def moved_render(renderer, *args, **kwargs):
                nonlocal count
                image = original_render(renderer, *args, **kwargs)
                count += 1
                if count == 1:
                    backend._data.qpos[0] += 0.01
                return image

            monkeypatch.setattr(renderer_type, "render", moved_render)
            session.capture_with_instances()
    assert backend._camera is None


def test_capture_timestamp_includes_render_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.simulation.mujoco import camera
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    started_at = datetime(2026, 10, 3, tzinfo=UTC)
    current_time = started_at

    class CaptureClock:
        @staticmethod
        def now(tz):
            return current_time.astimezone(tz)

    with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
        renderer_type = type(session._backend._camera._renderer)
        original_render = renderer_type.render

        def delayed_render(renderer, *args, **kwargs):
            nonlocal current_time
            image = original_render(renderer, *args, **kwargs)
            current_time += timedelta(seconds=2)
            return image

        monkeypatch.setattr(camera, "datetime", CaptureClock)
        monkeypatch.setattr(renderer_type, "render", delayed_render)
        captured = session.capture_with_instances()

    assert captured.observation.captured_at == started_at
    assert (current_time - captured.observation.captured_at).total_seconds() == 6


@pytest.mark.parametrize("field", ["cam_xpos", "cam_xmat", "cam_fovy", "znear", "zfar", "extent"])
def test_concurrent_calibration_change_rejects_mixed_frame(
    monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    with pytest.raises(RuntimeError, match="camera calibration changed"):
        with MuJoCoCaptureSession(SimulatorConfig(render_rgb=True, render_depth=True)) as session:
            backend = session._backend
            assert backend._camera is not None and backend._data is not None
            renderer_type = type(backend._camera._renderer)
            original_render = renderer_type.render
            count = 0

            def changed_calibration_render(renderer, *args, **kwargs):
                nonlocal count
                image = original_render(renderer, *args, **kwargs)
                count += 1
                if count == 1:
                    camera_id = backend._camera._camera_id
                    if field == "cam_fovy":
                        backend._model.cam_fovy[camera_id] += 1.0
                    elif field == "cam_xpos":
                        backend._data.cam_xpos[camera_id, 0] += 0.1
                    elif field == "cam_xmat":
                        # A 180-degree rotation remains a valid right-handed calibration.
                        backend._data.cam_xmat[camera_id, :6] *= -1
                    elif field == "extent":
                        backend._model.stat.extent *= 1.1
                    else:
                        clipping = backend._model.vis.map
                        setattr(clipping, field, getattr(clipping, field) * 1.1)
                return image

            monkeypatch.setattr(renderer_type, "render", changed_calibration_render)
            session.capture_with_instances()
    assert backend._camera is None
