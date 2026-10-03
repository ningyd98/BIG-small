"""Offline labels follow actual rendered, settled geometry and retain hard negatives."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig, SceneSpec


def test_sampler_reproducible_and_camera_variants_stay_in_group() -> None:
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene

    config = DatasetConfig(dataset_id="labels")
    first = sample_scene(config, 17)
    assert first == sample_scene(config, 17)
    other = sample_scene(config, 18)
    assert first.group_id != other.group_id
    params = dict(first.scene_parameters)
    params["camera"] = {**params["camera"], "fovy": 48}
    variant = SceneSpec.from_parameters(params, first.asset_family_hash, 500)
    assert variant.group_id == first.group_id
    assert variant.scene_hash != first.scene_hash
    for obj in [params["target"], *params["distractors"]]:
        assert obj["position"][2] > obj["half_size"][2]


def test_capture_labels_use_real_instances_and_reuse_model() -> None:
    from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
    from cloud_edge_robot_arm.datasets.rgbd.labels import label_frame
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    config = DatasetConfig(dataset_id="labels", distractor_count=(3, 3), half_size=(.04, .04),
                           camera_height=(1.2, 1.2),
                           depth_noise_m=(0,), invalid_depth_fractions=(0,))
    with MuJoCoCaptureSession(SimulatorConfig()) as session:
        scene = sample_scene(config, 17)
        session.apply_scene(scene)
        adapter = OfflineSceneAdapter(session, settle_steps=config.settle_steps)
        frame, truth = adapter.capture()
        model, camera = session._backend._model, session._backend._camera
        labels = label_frame(frame, truth)
        assert labels["positive"], labels["negative_reasons"]
        assert len(labels["instances"]) == 5
        assert labels["execution_verified"] is False
        assert labels["surface_point"][2] > labels["object_center"][2]
        target = labels["instances"][0]
        assert np.allclose(target["half_size"], scene.scene_parameters["target"]["half_size"])
        u, v = labels["target_pixel"]
        assert frame.instance_ids[v * frame.observation.width + u] in target["geom_ids"]
        assert abs(target["position"][2] - target["half_size"][2]) < .002
        assert truth["settling"]["max_linear_speed_m_s"] < .02
        assert model.body("object").mass[0] == pytest.approx(
            scene.scene_parameters["target"]["mass_kg"])
        assert model.geom("object_geom").friction[0] == pytest.approx(
            scene.scene_parameters["target"]["friction"])
        assert np.allclose(model.geom("object_geom").rgba,
                           scene.scene_parameters["target"]["rgba"])
        assert np.allclose([frame.observation.camera_to_world[i] for i in (3, 7, 11)],
                           scene.scene_parameters["camera"]["position"])
        assert model.camera("rgbd").fovy[0] == pytest.approx(
            scene.scene_parameters["camera"]["fovy"])
        assert "instances" not in frame.observation.model_dump()
        assert frame.observation.scene_id == scene.group_id
        second_scene = sample_scene(config, 18)
        session.apply_scene(second_scene)
        second, _ = adapter.capture()
        assert session._backend._model is model
        assert session._backend._camera is camera
        assert second.observation.checksum_sha256 != frame.observation.checksum_sha256
        assert second.observation.episode_id != frame.observation.episode_id
        session.apply_scene(scene)
        repeated, repeated_truth = adapter.capture()
        assert repeated.observation.rgb_png_base64 == frame.observation.rgb_png_base64
        assert repeated.observation.depth_float32_base64 == frame.observation.depth_float32_base64
        assert repeated.physics_state_hash == frame.physics_state_hash
        assert repeated_truth == truth
        hidden = replace(frame, instance_ids=tuple(
            -1 if geom in target["geom_ids"] else geom for geom in frame.instance_ids))
        hidden_labels = label_frame(hidden, truth)
        assert not hidden_labels["positive"]
        assert hidden_labels["target_pixel"] is None
        assert hidden_labels["instances"][0]["bbox_xyxy"] is None


def test_depth_corruption_preserves_original_and_becomes_negative() -> None:
    from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
    from cloud_edge_robot_arm.datasets.rgbd.labels import label_frame
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    config = DatasetConfig(dataset_id="labels", depth_noise_m=(.005,),
                           invalid_depth_fractions=(1,))
    with MuJoCoCaptureSession(SimulatorConfig()) as session:
        session.apply_scene(sample_scene(config, 17))
        frame, truth = OfflineSceneAdapter(session).capture()
        labels = label_frame(frame, truth)
        raw = truth["_raw_captured_frame"]
        assert not labels["positive"]
        assert "TARGET_DEPTH_INVALID" in labels["negative_reasons"]
        assert labels["target_pixel"] is None
        assert labels["suggested_action"] == "REQUEST_MORE_OBSERVATION"
        assert not any(frame.observation.valid_mask_bytes())
        assert any(raw.observation.valid_mask_bytes())
        assert raw.observation.captured_at == frame.observation.captured_at
        assert raw.physics_state_hash == frame.physics_state_hash


def test_capture_rejects_unsettled_scene_and_unknown_parameters() -> None:
    from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    scene = sample_scene(DatasetConfig(dataset_id="labels"), 17)
    with MuJoCoCaptureSession(SimulatorConfig()) as session:
        session.apply_scene(scene)
        with pytest.raises(ValueError, match="settled"):
            OfflineSceneAdapter(session, settle_steps=0).capture()
        bad = scene.model_copy(deep=True)
        bad.scene_parameters["unapplied"] = 99
        with pytest.raises(ValueError, match="parameters"):
            session.apply_scene(bad)
        wrong_color = scene.model_copy(deep=True)
        wrong_color.scene_parameters["target"]["color_name"] = "red"
        wrong_color.scene_parameters["target"]["rgba"] = [.08, .2, .9, 1]
        with pytest.raises(ValueError, match="color"):
            session.apply_scene(wrong_color)


@pytest.mark.parametrize("failure", ["angular_velocity", "rotated_bounds"])
def test_settling_checks_rotation_and_world_bounds(failure: str) -> None:
    from cloud_edge_robot_arm.datasets.rgbd.capture import OfflineSceneAdapter
    from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    session = MuJoCoCaptureSession(SimulatorConfig())
    backend = session._backend
    try:
        # CPU physical model suffices: this probe exercises truth checks, not rendering.
        backend.initialize(SimulatorConfig(render_rgb=False, render_depth=False))
        backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
        session._open = True
        session._dataset_scene = sample_scene(
            DatasetConfig(dataset_id="probe", distractor_count=(0, 0)), 0)
        model, data, mj = backend._model, backend._data, backend._mujoco
        joint = model.joint("object_free")
        if failure == "angular_velocity":
            data.qvel[joint.dofadr[0] + 3] = 25
        else:
            adr = joint.qposadr[0]
            data.qpos[adr:adr + 3] = [.96, 0, .035]
            data.qpos[adr + 3:adr + 7] = [np.cos(np.pi / 8), 0, 0, np.sin(np.pi / 8)]
            mj.mj_forward(model, data)
        with pytest.raises(ValueError, match="settled|bounds"):
            OfflineSceneAdapter(session).capture_ground_truth()
    finally:
        backend.shutdown()
