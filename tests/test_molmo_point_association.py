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


def colored_boundary_scene(change=None):
    """构造边缘原生点；所有图像改动仅用于合成 CPU 测试。"""
    observation = association_scene()
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64)))).copy()
    depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(240, 320)
    pixel = (179, 113)
    if change in {"two_red", "two_blue", "two_invalid"}:
        rgb[112:115, 162:165] = [20, 20, 240] if change == "two_blue" else [240, 50, 50]
        if change == "two_invalid":
            depth[112:115, 162:165] = 0
    elif change == "mixed_hue":
        rgb[114, 172] = [20, 20, 240]
    elif change in {"component_depth", "selected_depth", "patch_depth", "native_depth"}:
        x, y = {
            "component_depth": (172, 113), "selected_depth": (179, 119),
            "patch_depth": (178, 118), "native_depth": pixel,
        }[change]
        depth[y, x] = 0
    elif change in {"thin", "touch_window", "cross_window", "image"}:
        rgb[113:127, 172:186] = 225
        if change == "thin":
            rgb[113:127, 178:180] = [240, 50, 50]
        elif change in {"touch_window", "cross_window"}:
            rgb[113 : (133 if change == "touch_window" else 140), 172:186] = [240, 50, 50]
        else:
            rgb[113:127, 3:17] = [240, 50, 50]
            pixel = (10, 113)
    elif change == "tiny_native":
        rgb[112:114, 166:168] = [240, 50, 50]
        pixel = (167, 113)
    elif change == "threshold_boundary":
        rgb[113:127, 172:186] = [60, 25, 25]
        rgb[112:115, 162:165] = [240, 50, 50]
    elif change == "threshold_interior":
        rgb[113:127, 172:186] = [60, 25, 25]
        pixel = (180, 120)
    elif change in {"interior_spike", "interior_zero", "interior_competitor"}:
        pixel = (180, 120)
        if change == "interior_competitor":
            rgb[112:115, 162:165] = [240, 50, 50]
        else:
            depth[119, 179] = 0 if change == "interior_zero" else 1.31
    elif change == "far_interior":
        rgb[113:127, 172:186] = 225
        rgb[113, 179:195] = [240, 50, 50]
        rgb[113:126, 194] = [240, 50, 50]
        rgb[125:132, 191:198] = [240, 50, 50]
    elif change is not None:
        raise AssertionError(f"unknown CPU boundary fixture: {change}")
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    payload = observation.model_dump()
    payload.update(
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None, checksum_sha256="",
    )
    return RGBDObservation.model_validate(payload), pixel


def test_colored_boundary_moves_only_to_unique_rgb_interior():
    observation, native = colored_boundary_scene()
    before = observation.model_dump()
    result = associate(observation, native)
    assert result.pixel == (179, 119)
    assert result.evidence["status"] == "ASSOCIATED"
    assert result.evidence["association_trigger"] == "NATIVE_COLORED_BOUNDARY"
    assert result.evidence["native_rgb_patch_complete"] is False
    assert result.evidence["native_pixel"] == [179, 113]
    assert result.evidence["selected_pixel"] == [179, 119]
    assert result.evidence["displacement_px"] == 6
    assert result.evidence["candidate_count"] == 1
    assert result.evidence["selected_source"] == "RGB_LOCAL_COMPONENT_ASSOCIATION"
    assert observation.model_dump() == before
    for key in ("rgb_sha256", "depth_sha256"):
        assert result.evidence[key] == observation.evidence()[key]


@pytest.mark.parametrize(
    "change",
    [
        "two_red", "two_blue", "two_invalid", "mixed_hue", "component_depth",
        "selected_depth", "patch_depth", "native_depth", "thin", "touch_window",
        "cross_window", "image",
    ],
)
def test_colored_boundary_cannot_bypass_component_guards(change):
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    observation, pixel = colored_boundary_scene(change)
    with pytest.raises(PointAssociationError) as caught:
        associate(observation, pixel)
    assert caught.value.evidence["status"] == "REJECTED"
    assert caught.value.evidence["native_pixel"] == list(pixel)
    if change.startswith("two_"):
        assert caught.value.evidence["candidate_count"] == 2


@pytest.mark.parametrize("change", ["tiny_native", "threshold_boundary"])
def test_colored_native_component_cannot_jump_to_another_candidate(change):
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    observation, pixel = colored_boundary_scene(change)
    with pytest.raises(PointAssociationError) as caught:
        associate(observation, pixel)
    assert caught.value.evidence["candidate_count"] == 1
    assert caught.value.evidence["selected_pixel"] is None


def test_complete_chroma35_direct_patch_is_preserved():
    observation, pixel = colored_boundary_scene("threshold_interior")
    result = associate(observation, pixel)
    assert result.pixel == (180, 120)
    assert result.evidence["status"] == "UNCHANGED"


@pytest.mark.parametrize("change", ["interior_spike", "interior_zero", "interior_competitor"])
def test_direct_interior_is_preserved_and_nonflat_depth_is_not_hunted(change):
    from cloud_edge_robot_arm.vision.top_grasp import resolve_top_grasp

    observation, pixel = colored_boundary_scene(change)
    result = associate(observation, pixel)
    assert result.pixel == pixel == (180, 120)
    assert result.evidence["status"] == "UNCHANGED"
    if change != "interior_competitor":
        with pytest.raises(ValueError, match="invalid|flat"):
            resolve_top_grasp(observation, result.pixel, 0.0)


@pytest.mark.parametrize("pixel", [(179, 113), (180, 120)])
def test_colored_unsupported_descriptor_is_never_shifted(pixel):
    result = associate(association_scene(), pixel, "the requested object")
    assert result.pixel == pixel
    assert result.evidence["status"] == "UNCHANGED"
    assert result.evidence["descriptor_color_status"] == "UNSUPPORTED_DIRECT_UNCHANGED"


@pytest.mark.parametrize("pixel", [(179, 113), (180, 120)])
def test_colored_wrong_descriptor_still_rejects(pixel):
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    with pytest.raises(PointAssociationError):
        associate(association_scene(), pixel, "blue block")


def test_colored_boundary_tie_break_remains_nearest_then_row_then_column():
    observation, pixel = colored_boundary_scene()
    assert [associate(observation, pixel).pixel for _ in range(3)] == [(179, 119)] * 3


def test_colored_boundary_never_substitutes_closer_point_for_out_of_radius_maximum():
    from cloud_edge_robot_arm.vision.point_association import PointAssociationError

    observation, pixel = colored_boundary_scene("far_interior")
    with pytest.raises(PointAssociationError) as caught:
        associate(observation, pixel)
    assert caught.value.evidence["candidate_count"] == 1
    assert caught.value.evidence["displacement_px"] > caught.value.evidence["radius_px"]
