"""SOFTWARE_ONLY tests; saved renderer frames remain excluded diagnostics."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml
from PIL import Image

from cloud_edge_robot_arm.contracts.models import TaskTarget
from cloud_edge_robot_arm.vision.observations import RGBDObservation

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/research/ced_marker_registration_v1.yaml"
PROCESS = ROOT / "artifacts/research/process/20261004-ced-development"
STATIC = PROCESS / "t7b-pose-marker-color/actual-capture-640/frame/observation-full.json"
INITIAL = (
    PROCESS
    / "t7b-pose-marker-motion-development/attempt-1/frames/INITIAL_SETTLED/observation-full.json"
)
INSTRUCTION = "pick the red cube and place it in the green target region"


def api():
    return importlib.import_module("cloud_edge_robot_arm.vision.marker_association")


def inputs(path=STATIC):
    module = api()
    observation = RGBDObservation.model_validate_json(path.read_text())
    registration = module.load_marker_registration(
        CONFIG, expected_registry_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(), root=ROOT
    )
    context = module.marker_frame_context(
        observation,
        registration,
        task_id="diagnostic-task",
        task_target=TaskTarget(
            object_id="object", object_class="cube", target_region_id="target_region"
        ),
        instruction=INSTRUCTION,
        context_hash="1" * 64,
        role_bundle_hash="2" * 64,
        active_asset_sha256=registration.pose_marker.marked_asset_sha256,
        plan_version=1,
        command_seq=1,
    )
    return module, observation, registration, context


@pytest.mark.parametrize("path", [STATIC, INITIAL])
def test_saved_static_candidate_is_separate_measured_support_never_admission(path):
    module, observation, registration, context = inputs(path)
    result = module.replay_marker_target_development(observation, registration, context)
    assert result.status == "OBSERVED_CANDIDATE"
    assert result.replay_mode == "DEVELOPMENT_REPLAY"
    assert result.pose_estimate.status == "OBSERVED"
    assert result.coverage["requested_color_pixels"] >= 100
    assert (
        result.support_masks["requested_color"]
        != result.support_masks["observed_tag_depth_support"]
    )
    assert result.observation_sha256 == observation.checksum_sha256
    assert result.admission_status == "NOT_ADMITTED"
    assert result.whole_target_identity_status == "UNKNOWN" and result.extent_complete is False
    assert result.geometric_error_bound_m is None and result.motion_bound_m_s is None
    assert result.angular_velocity_bound_rad_s is None and result.stability_status == "UNKNOWN"
    assert not any("identity_confirmed" in name for name in result.coverage)


def test_accepted_registry_scope_and_result_status_cannot_be_requested():
    module, observation, registration, context = inputs()
    payload = yaml.safe_load(CONFIG.read_text())
    payload["admission_scope"] = "ACCEPTED_IDENTITY_SOURCE"
    with pytest.raises(ValueError, match="DEVELOPMENT_ONLY"):
        module.MarkerObjectRegistration.from_payload(payload, root=ROOT)
    result = module.replay_marker_target_development(observation, registration, context)
    with pytest.raises(ValueError):
        replace(result, admission_status="ACCEPTED")
    with pytest.raises(ValueError):
        replace(result, status="VALID")


def test_layout_and_context_are_detached_from_caller_mutable_payloads():
    module = api()
    payload = yaml.safe_load(CONFIG.read_text())
    registration = module.MarkerObjectRegistration.from_payload(payload, root=ROOT)
    digest = registration.digest()
    payload["appearance_layout"]["quiet_polygon_m"][0][0] = 99
    payload["registration_source_hashes"].clear()
    assert registration.digest() == digest
    with pytest.raises(TypeError):
        registration.appearance_layout["quiet_polygon_m"][0][0] = 99
    module, observation, registration, context = inputs()
    result = module.replay_marker_target_development(observation, registration, context)
    with pytest.raises(TypeError):
        result.coverage["requested_color_pixels"] = 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("instruction", "Do not pick the red cube and place it in the green target region"),
        ("instruction", "pick the blue cube and place it in the green target region"),
        ("object_id", "decoy"),
        ("object_class", "sphere"),
        ("target_region_id", "wrong-region"),
        ("active_asset_sha256", "0" * 64),
        ("observation_sha256", "0" * 64),
        ("registration_sha256", "0" * 64),
        ("camera_profile_sha256", "0" * 64),
        ("plan_version", True),
    ],
)
def test_identity_context_instruction_and_registry_tamper_are_never_candidates(field, value):
    module, observation, registration, context = inputs()
    altered = replace(context, **{field: value})
    result = module.replay_marker_target_development(observation, registration, altered)
    assert result.status != "OBSERVED_CANDIDATE" and result.admission_status == "NOT_ADMITTED"


def test_live_freshness_does_not_accept_historical_frame_or_rewrite_capture_time():
    module, observation, registration, context = inputs()
    before = observation.captured_at
    result = module.associate_marker_target(
        observation, registration, context, now=before + timedelta(seconds=6)
    )
    assert result.status == "UNKNOWN" and "capture_not_fresh" in result.reasons
    assert observation.captured_at == before
    assert result.replay_mode == "LIVE_DIAGNOSTIC"


def recolor(observation, transform):
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))))
    changed = transform(rgb.copy())
    image = io.BytesIO()
    Image.fromarray(changed).save(image, format="PNG")
    return RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "rgb_png_base64": base64.b64encode(image.getvalue()).decode(),
            "checksum_sha256": "",
        }
    )


@pytest.mark.parametrize("kind", ["wrong_color", "missing_tag", "unexplained_hole"])
def test_wrong_color_missing_tag_and_unexplained_rim_hole_are_negative(kind):
    module, observation, registration, _ = inputs()

    def alter(rgb):
        red = (rgb[:, :, 0] > rgb[:, :, 1] * 1.3) & (rgb[:, :, 0] > rgb[:, :, 2] * 1.3)
        if kind == "wrong_color":
            rgb[red] = [0, 0, 255]
        elif kind == "missing_tag":
            rgb[230:250, 349:368] = [128, 128, 128]
        else:
            assert red[235:244, 345:348].any()  # qualified cut crosses the observed rim
            rgb[235:244, 345:348] = [128, 128, 128]
        return rgb

    changed = recolor(observation, alter)
    _, _, _, context = inputs()
    context = replace(context, observation_sha256=changed.checksum_sha256)
    result = module.replay_marker_target_development(changed, registration, context)
    assert result.status != "OBSERVED_CANDIDATE"


def test_registry_loader_checks_expected_bytes_and_live_sources(tmp_path):
    module, observation, registration, context = inputs()
    with pytest.raises(ValueError, match="registry"):
        module.load_marker_registration(CONFIG, expected_registry_sha256="0" * 64, root=ROOT)
    for name in registration.registration_source_hashes:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / name).read_bytes())
    altered = replace(registration, root=tmp_path)
    (tmp_path / "src/cloud_edge_robot_arm/vision/online_intent.py").write_text("changed")
    result = module.replay_marker_target_development(observation, altered, context)
    assert result.status == "INVALID" and "registration_source_changed" in result.reasons


def test_depth_hole_invalid_mask_and_camera_change_cannot_reuse_identity():
    module, observation, registration, context = inputs()
    data = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").copy()
    data[240 * observation.width + 358] = 0
    with pytest.raises(ValueError, match="valid mask"):
        RGBDObservation.model_validate(
            {
                **observation.model_dump(),
                "depth_float32_base64": base64.b64encode(data.tobytes()).decode(),
                "checksum_sha256": "",
            }
        )
    changed = RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "depth_float32_base64": base64.b64encode(data.tobytes()).decode(),
            "valid_mask_base64": None,
            "checksum_sha256": "",
        }
    )
    result = module.replay_marker_target_development(
        changed, registration, replace(context, observation_sha256=changed.checksum_sha256)
    )
    assert result.status == "UNKNOWN"
    changed = RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "intrinsics": (observation.intrinsics[0] + 1, *observation.intrinsics[1:]),
            "checksum_sha256": "",
        }
    )
    result = module.replay_marker_target_development(
        changed, registration, replace(context, observation_sha256=changed.checksum_sha256)
    )
    assert result.status == "INVALID" and "camera_profile_changed" in result.reasons


@pytest.mark.parametrize(
    "field,value",
    [
        ("object_id", "decoy"),
        ("object_class", "sphere"),
        ("expected_color", "blue"),
        ("object_half_extent_m", [0.04, 0.04, 0.04]),
        (
            "marker_to_object",
            [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.04, 0.0, 0.0, 0.0, 1.0],
        ),
    ],
)
def test_development_registry_cannot_claim_other_asset_object_or_attachment(field, value):
    module = api()
    payload = yaml.safe_load(CONFIG.read_text())
    payload[field] = value
    with pytest.raises(ValueError, match="frozen colored-v2"):
        module.MarkerObjectRegistration.from_payload(payload, root=ROOT)


def test_registered_layout_cannot_be_expanded_to_explain_arbitrary_holes():
    module = api()
    payload = yaml.safe_load(CONFIG.read_text())
    payload["appearance_layout"]["quiet_polygon_m"][0][0] = -0.04
    with pytest.raises(ValueError, match="frozen colored-v2"):
        module.MarkerObjectRegistration.from_payload(payload, root=ROOT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("whole_target_identity_status", "CONFIRMED"),
        ("extent_complete", True),
        ("geometric_error_bound_m", 0.001),
        ("motion_bound_m_s", 0.0),
        ("angular_velocity_bound_rad_s", 0.0),
        ("stability_status", "PASS"),
    ],
)
def test_result_invariants_cannot_be_forged_by_constructor_or_replace(field, value):
    module, observation, registration, context = inputs()
    result = module.replay_marker_target_development(observation, registration, context)
    with pytest.raises(ValueError):
        replace(result, **{field: value})
    with pytest.raises(TypeError):
        module.MarkerTargetAssociation(
            "OBSERVED_CANDIDATE",
            (),
            "0" * 64,
            "1" * 64,
            "2" * 64,
            "DEVELOPMENT_REPLAY",
            **{field: value},
        )


def test_two_actual_copied_tag_patterns_are_ambiguous_without_truth_inputs():
    module, observation, registration, context = inputs()

    def duplicate(rgb):
        rgb[220:260, 400:440] = rgb[220:260, 340:380]
        return rgb

    changed = recolor(observation, duplicate)
    result = module.replay_marker_target_development(
        changed, registration, replace(context, observation_sha256=changed.checksum_sha256)
    )
    assert result.status == "UNKNOWN"
    assert result.pose_estimate.observed_marker_ids == (7, 7)


def test_foreign_native_decodable_tag_cannot_bind_expected_id7():
    module, observation, registration, context = inputs()
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    pattern = cv2.aruco.generateImageMarker(dictionary, 8, 18)

    def foreign(rgb):
        rgb[231:249, 350:368] = pattern[:, :, None]
        return rgb

    changed = recolor(observation, foreign)
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(changed.rgb_png_base64))))
    _, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(rgb)
    assert ids is not None and ids.flatten().tolist() == [8]  # qualifies wrong-tag fixture
    result = module.replay_marker_target_development(
        changed, registration, replace(context, observation_sha256=changed.checksum_sha256)
    )
    assert result.status == "UNKNOWN" and result.pose_estimate.observed_marker_ids == (8,)


def test_missing_quiet_depth_cannot_be_explained_as_registered_marker_hole():
    module, observation, registration, context = inputs()
    data = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").copy()
    data[240 * observation.width + 348] = 0
    changed = RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "depth_float32_base64": base64.b64encode(data.tobytes()).decode(),
            "valid_mask_base64": None,
            "checksum_sha256": "",
        }
    )
    result = module.replay_marker_target_development(
        changed, registration, replace(context, observation_sha256=changed.checksum_sha256)
    )
    assert result.status == "UNKNOWN" and "layout_depth_unavailable" in result.reasons


def test_projected_regions_are_hypotheses_not_observed_filled_support():
    module, observation, registration, context = inputs()
    result = module.replay_marker_target_development(observation, registration, context)
    assert "tag_region" not in result.support_masks
    assert set(result.region_hypotheses) == {"tag_region", "quiet_region", "face_region"}
    assert len(result.support_masks["requested_color"]) == observation.width * observation.height


def test_foreground_depth_on_quiet_area_is_unknown_even_if_tag_and_red_remain():
    module, observation, registration, context = inputs()
    data = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").copy()
    depths = data.reshape(observation.height, observation.width)
    depths[237:242, 347:350] = 0.5  # finite positive foreground; tag corners/center stay intact
    changed = RGBDObservation.model_validate(
        {
            **observation.model_dump(),
            "depth_float32_base64": base64.b64encode(data.tobytes()).decode(),
            "checksum_sha256": "",
        }
    )
    result = module.replay_marker_target_development(
        changed, registration, replace(context, observation_sha256=changed.checksum_sha256)
    )
    assert result.pose_estimate.status == "OBSERVED"  # qualified non-tag occlusion fixture
    assert result.status == "UNKNOWN" and "quiet_plane_sanity_failed" in result.reasons
