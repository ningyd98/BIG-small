import hashlib
import json

import pytest
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation, camera_hash


def inputs():
    a, b, c = (v * 64 for v in "abc")
    camera = dict(
        width=320,
        height=240,
        calibration_version="rgbd-v1",
        source="mujoco_camera",
        intrinsics=[257, 257, 159.5, 119.5],
        camera_to_world=[1, 0, 0, 0.35, 0, -1, 0, 0, 0, 0, -1, 1.4, 0, 0, 0, 1],
    )
    geo = dict(
        registration_id="rig",
        marker_family="named-registered-pair",
        camera=camera,
        development_dual=dict(
            scene_id="design", scene_asset_sha256=a, camera_sha256=camera_hash(camera)
        ),
        pose_marker=dict(marked_asset_sha256=a),
    )
    record = dict(
        case=dict(
            scene_id="distinct/runtime-instance", id="id", asset_sha256=a, physics_dt_s="1/240"
        ),
        geometry=geo,
        asset_sha256=a,
        runtime_build_sha256=b,
        calibration_sha256=c,
    )
    payload = json.dumps(record).encode()
    kwargs = dict(
        allocation_sha256=hashlib.sha256(payload).hexdigest(),
        generation_sha256=b,
        calibration_sha256=c,
        asset_sha256=a,
        reset_scene_id=record["case"]["scene_id"],
        reset_episode_id="random-reset",
    )
    return payload, kwargs


def test_independent_instances_bind_without_assigning_the_design_scene_to_the_sensor():
    payload, params = inputs()
    state = bind_allocation(payload, **params)
    assert state.scene_id == "distinct/runtime-instance" and state.episode_id == "random-reset"
    assert state.design_scene_id == "design"
    with pytest.raises(AttributeError):
        state.scene_id = "another"


@pytest.mark.parametrize(
    "key",
    [
        "allocation_sha256",
        "calibration_sha256",
        "generation_sha256",
        "asset_sha256",
        "reset_scene_id",
        "reset_episode_id",
    ],
)
def test_divergent_or_missing_authority_does_not_build_context(key):
    payload, k = inputs()
    k[key] = "" if key == "reset_episode_id" else "f" * 64
    with pytest.raises(ValueError):
        bind_allocation(payload, **k)
