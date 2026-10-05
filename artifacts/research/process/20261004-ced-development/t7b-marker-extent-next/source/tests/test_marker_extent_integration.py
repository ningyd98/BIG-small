"""SOFTWARE_ONLY measured-boundary integration; no native extent admission.

Existing saved RGBD is replayed at its original capture time. Edited bytes are
qualified counterexamples, not newly captured or physically accepted evidence.
"""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.contracts.models import TaskTarget
from cloud_edge_robot_arm.vision.marker_association import (
    load_marker_registration,
    marker_frame_context,
    replay_marker_target_development,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/ced_marker_registration_v1.yaml"
PROCESS = ROOT / "artifacts/research/process/20261004-ced-development"
STATIC = PROCESS / "t7b-pose-marker-color/actual-capture-640/frame/observation-full.json"
INITIAL = (
    PROCESS
    / "t7b-pose-marker-motion-development/attempt-1/frames/INITIAL_SETTLED/observation-full.json"
)


def replay(observation):
    registration = load_marker_registration(
        CONFIG, expected_registry_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(), root=ROOT
    )
    context = marker_frame_context(
        observation,
        registration,
        task_id="software-only-boundary-replay",
        task_target=TaskTarget(
            object_id="object", object_class="cube", target_region_id="target_region"
        ),
        instruction="pick the red cube and place it in the green target region",
        context_hash="1" * 64,
        role_bundle_hash="2" * 64,
        active_asset_sha256=registration.pose_marker.marked_asset_sha256,
        plan_version=1,
        command_seq=1,
    )
    return replay_marker_target_development(observation, registration, context), registration


def depth_changed(observation, value, pixel=(344, 230)):
    depths = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").copy()
    # This actual exterior neighbor is outside the registered face hypothesis.
    x, y = pixel
    depths[y * observation.width + x] = value
    return RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "depth_float32_base64": base64.b64encode(depths.tobytes()).decode(),
            "valid_mask_base64": None,
            "checksum_sha256": "",
        }
    )


@pytest.mark.parametrize("pixel", [(344, 230), (372, 235)])
def test_missing_exterior_neighbor_depth_blocks_candidate_even_outside_projected_face(pixel):
    # Break caught: checking only projected layout depth ignores the real boundary neighborhood.
    observation = RGBDObservation.model_validate_json(STATIC.read_text())
    original, registration = replay(observation)
    face = np.frombuffer(original.region_hypotheses["face_region"], np.uint8).reshape(480, 640)
    x, y = pixel
    assert face[y, x] == 0 and original.status == "OBSERVED_CANDIDATE"
    changed = depth_changed(observation, 0.0, pixel)
    assert detect_pose_marker(changed, registration.pose_marker).status == "OBSERVED"
    result, _ = replay(changed)
    assert result.status == "UNKNOWN"
    assert "outer_boundary_depth_unavailable" in result.reasons
    assert result.admission_status == "NOT_ADMITTED" and result.extent_complete is False


@pytest.mark.parametrize("path", [STATIC, INITIAL])
def test_raw_outer_contour_and_neighbor_samples_are_separate_from_region_hypotheses(path):
    # Break caught: projected/fill pixels replace measured support, or RGBD samples are omitted.
    observation = RGBDObservation.model_validate_json(path.read_text())
    result, _ = replay(observation)
    support = getattr(result, "boundary_support", None)
    assert support is not None, "measured outer-boundary RGBD samples are missing"
    assert result.status == "OBSERVED_CANDIDATE"
    shape = (observation.height, observation.width)
    raw = np.frombuffer(result.support_masks["requested_color"], np.uint8).reshape(shape)
    boundary = np.frombuffer(result.support_masks["observed_color_outer_boundary"], np.uint8)
    neighbor = np.frombuffer(
        result.support_masks["observed_outer_boundary_neighbor_depth"], np.uint8
    )
    assert np.all(raw.ravel()[boundary > 0] == 1)
    assert np.all(raw.ravel()[neighbor > 0] == 0)
    assert boundary[230 * observation.width + 345] == 1
    assert neighbor[230 * observation.width + 344] == 1
    expected_counts = (102, 110) if path == STATIC else (105, 114)
    assert (int(boundary.sum()), int(neighbor.sum())) == expected_counts
    for name, mask in (("outer_boundary", boundary), ("outer_neighborhood", neighbor)):
        samples = support[name]
        pixels = samples["pixels"]
        assert len(pixels) == int(mask.sum()) == len(samples["depth_m"])
        assert len(pixels) == len(samples["rgb"]) == len(samples["points_world_m"])
        assert len(pixels) == len(samples["marker_plane_signed_residual_m"])
        rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))))
        depths = np.asarray(observation.depth_values()).reshape(shape)
        for index, (x, y) in enumerate(pixels):
            assert mask[y * observation.width + x] == 1
            assert samples["depth_m"][index] == pytest.approx(float(depths[y, x]), abs=1e-7)
            assert samples["rgb"][index] == tuple(int(v) for v in rgb[y, x])
    assert support["depth_convention"] == "optical_z_m"
    assert support["calibrated_error_bound_m"] is None
    assert result.coverage["outer_boundary_verified"] is False
    assert result.coverage["outer_boundary_depth_separation_status"] == "UNKNOWN_UNCALIBRATED"
    assert result.whole_target_identity_status == "UNKNOWN" and result.extent_complete is False
    assert result.geometric_error_bound_m is None and result.motion_bound_m_s is None
    with pytest.raises(TypeError):
        support["outer_boundary"]["depth_m"][0] = 0


def test_finite_positive_exterior_foreground_is_reported_without_claiming_complete_extent():
    # Break caught: geometry is inferred solely from tag/layout while ignoring real exterior depth.
    observation = RGBDObservation.model_validate_json(STATIC.read_text())
    baseline, registration = replay(observation)
    changed = depth_changed(observation, 0.5)
    assert detect_pose_marker(changed, registration.pose_marker).status == "OBSERVED"
    result, _ = replay(changed)
    support = getattr(result, "boundary_support", None)
    assert support is not None, "exterior foreground measurement is missing"
    samples = support["outer_neighborhood"]
    index = samples["pixels"].index((344, 230))
    assert samples["depth_m"][index] == 0.5
    assert result.coverage["outer_neighbor_strictly_farther_than_rim_pixels"] == (
        baseline.coverage["outer_neighbor_strictly_farther_than_rim_pixels"] - 1
    )
    assert result.coverage["outer_boundary_depth_separation_status"] == "UNKNOWN_UNCALIBRATED"
    assert result.admission_status == "NOT_ADMITTED" and result.extent_complete is False


def test_color_outer_boundary_clipping_cannot_be_explained_by_an_unclipped_tag_layout():
    # Break caught: an unclipped small tag/layout hides a color component extending off image.
    observation = RGBDObservation.model_validate_json(STATIC.read_text())
    _, registration = replay(observation)
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64)))).copy()
    rgb[230:232, :346] = [255, 0, 0]  # joins the visible red rim to the image edge
    png = io.BytesIO()
    Image.fromarray(rgb).save(png, format="PNG")
    changed = RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "rgb_png_base64": base64.b64encode(png.getvalue()).decode(),
            "checksum_sha256": "",
        }
    )
    assert detect_pose_marker(changed, registration.pose_marker).status == "OBSERVED"
    result, _ = replay(changed)
    assert result.status == "UNKNOWN"
    assert "color_outer_boundary_clipped" in result.reasons


def test_actual_occluded_motion_boundaries_never_reuse_static_marker_extent():
    # Break caught: stale marker/boundary support persists after the top tag is occluded.
    frames = PROCESS / "t7b-pose-marker-motion-development/attempt-1/frames"
    paths = sorted(frames.glob("AFTER_*/observation-full.json"))
    assert len(paths) == 9
    for path in paths:
        result, _ = replay(RGBDObservation.model_validate_json(path.read_text()))
        assert result.pose_estimate.status == "UNKNOWN"
        assert result.status == "UNKNOWN" and result.extent_complete is False
        assert result.admission_status == "NOT_ADMITTED"
        assert getattr(result, "boundary_support", {}) == {}
