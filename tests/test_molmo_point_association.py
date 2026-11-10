"""小目标局部关联须保持原生点并拒绝歧义、无效深度及不完整支撑。"""

from __future__ import annotations

import base64
import io
from datetime import UTC, datetime

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def association_scene(change=None):
    rgb = np.full((240, 320, 3), 225, dtype=np.uint8)
    depth = np.full((240, 320), 1.4, dtype="<f4")
    rgb[113:127, 172:186] = [240, 50, 50]
    depth[113:127, 172:186] = 1.33
    if change in {"missing", "far", "tiny", "thin", "roi", "image"}:
        rgb[113:127, 172:186] = 225
        depth[113:127, 172:186] = 1.4
        if change == "far":
            rgb[141:155, 172:186] = [240, 50, 50]
        elif change == "tiny":
            rgb[114:116, 178:181] = [240, 50, 50]
        elif change == "thin":
            rgb[113:127, 178:180] = [240, 50, 50]
        elif change == "roi":
            rgb[123:137, 172:186] = [240, 50, 50]
        elif change == "image":
            rgb[113:127, 3:17] = [240, 50, 50]
            depth[113:127, 3:17] = 1.33
    elif change in {"two_red", "two_blue", "two_invalid"}:
        rgb[112:115, 162:165] = [20, 20, 240] if change == "two_blue" else [240, 50, 50]
        if change == "two_invalid":
            depth[112:115, 162:165] = 0
    elif change == "wrong_color":
        rgb[113:127, 172:186] = [20, 240, 20]
    elif change == "direct_wrong_color":
        rgb[109, 179] = [20, 20, 240]
    elif change == "native_depth":
        depth[109, 179] = 0
    elif change == "selected_depth":
        depth[119, 179] = 0
    elif change == "component_depth":
        depth[113, 172] = 0
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    return RGBDObservation(
        frame_id="cpu-association-fixture",
        captured_at=datetime.now(UTC),
        sim_time_s=0.0,
        width=320,
        height=240,
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        intrinsics=(257.34, 257.34, 159.5, 119.5),
        camera_to_world=(
            1.0,
            0.0,
            0.0,
            0.35,
            0.0,
            -1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            1.4,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        source="mujoco_camera",
        episode_id="cpu-fixture",
        calibration_version="cpu-fixture",
    )


def associate(observation, pixel=(179, 109), phrase="red block"):
    from cloud_edge_robot_arm.vision.point_association import associate_target_point

    return associate_target_point(observation, pixel, target_phrase=phrase)


def test_near_small_component_keeps_native_and_chooses_complete_interior():
    observation = association_scene()
    checksum = observation.checksum_sha256
    result = associate(observation)
    assert result.pixel == (179, 119)
    assert result.evidence["native_pixel"] == [179, 109]
    assert result.evidence["selected_pixel"] == [179, 119]
    assert result.evidence["status"] == "ASSOCIATED"
    assert result.evidence["selected_source"] == "RGB_LOCAL_COMPONENT_ASSOCIATION"
    assert result.evidence["candidate_count"] == 1
    assert result.evidence["displacement_px"] == pytest.approx(10)
    assert result.evidence["observation_checksum"] == checksum
    assert observation.checksum_sha256 == checksum
    assert "confidence" not in str(result.evidence)


def test_colored_direct_point_is_not_shifted():
    result = associate(association_scene(), (180, 120))
    assert result.pixel == (180, 120)
    assert result.evidence["status"] == "UNCHANGED"


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "far",
        "tiny",
        "thin",
        "roi",
        "two_red",
        "two_blue",
        "two_invalid",
        "wrong_color",
        "direct_wrong_color",
        "native_depth",
        "selected_depth",
        "component_depth",
    ],
)
def test_unsafe_component_cannot_replace_native_target(change):
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    with pytest.raises(PointAssociationError) as caught:
        associate(association_scene(change))
    evidence = caught.value.evidence
    assert evidence["status"] == "REJECTED" and evidence["native_pixel"] == [179, 109]
    assert evidence["reason"]
    if change.startswith("two_"):
        assert evidence["candidate_count"] == 2


@pytest.mark.parametrize(
    "phrase", ["not red block", "red or blue block", "orange cube", "red blocks"]
)
def test_ambiguous_or_unsupported_descriptor_never_rescues(phrase):
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    with pytest.raises(PointAssociationError):
        associate(association_scene(), phrase=phrase)


def test_unsupported_descriptor_retains_legacy_direct_behavior():
    assert associate(association_scene(), (180, 120), "the requested object").pixel == (180, 120)


@pytest.mark.parametrize("pixel", [(-1, 109), (320, 109), (179.0, 109), (True, 109), (179, 1)])
def test_bad_pixel_or_image_boundary_cannot_initiate_rescue(pixel):
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    with pytest.raises(PointAssociationError):
        associate(association_scene(), pixel)


def test_unique_candidate_cannot_rescue_a_window_truncated_by_image():
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    with pytest.raises(PointAssociationError) as caught:
        associate(association_scene("image"), (10, 109))
    assert caught.value.evidence["candidate_count"] == 1
    assert "truncated by image boundary" in caught.value.evidence["reason"]
