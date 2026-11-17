"""Partial region support needs current depth and reprojected world anchors."""

import base64
import io

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_opencv_target_evidence import scene, tracker


def partial_region(reference, damage=None, translated=False):
    rgb = np.asarray(Image.open(io.BytesIO(base64.b64decode(reference.rgb_png_base64)))).copy()
    depth = np.frombuffer(base64.b64decode(reference.depth_float32_base64), dtype="<f4").copy()
    depth = depth.reshape(reference.height, reference.width)
    rgb[25:30, 50:55] = 100
    depth[25:30, 50:55] = 0.8
    if damage == "coplanar":
        depth[25:30, 50:55] = 1.0
    elif damage == "background":
        depth[25:30, 50:55] = 1.05
    elif damage == "invalid":
        depth[25:30, 50:55] = 0
    elif damage == "decoy":
        rgb[3:8, 3:8] = [20, 230, 20]
    elif damage == "two_corners":
        rgb[20:36, 57:61] = 100
        depth[20:36, 57:61] = 0.8
    elif damage == "missing":
        rgb[20:36, 45:61] = 100
        depth[20:36, 45:61] = 0.8
    elif damage == "mixed_foreground_edge":
        depth[25, 49] = 0.8  # Green edge RGB paired with current foreground depth.
    elif damage == "interior_depth_spike":
        depth[22, 48] = 0.8
    elif damage in {"shaded_green", "shaded_green_spike", "shaded_green_invalid"}:
        rgb[22, 48] = [35, 125, 35]
        if damage == "shaded_green_spike":
            depth[22, 48] = 0.8
        elif damage == "shaded_green_invalid":
            depth[22, 48] = 0
    elif damage in {"low_red_edge", "mixed_low_edge", "blue_low_edge",
                    "coplanar_red_edge", "detached_low_red", "mixed_plane_edge",
                    "mixed_background_edge", "detached_mixed_plane", "connected_low_sidewall",
                    "mixed_after_low_sidewall"}:
        # A low object sidewall at the silhouette of current high foreground.
        rgb[25:30, 49] = [76, 17, 13]
        depth[25:30, 49] = 1.0 if damage == "coplanar_red_edge" else 0.9975
        if damage == "detached_low_red":
            rgb[22, 48], depth[22, 48] = [76, 17, 13], 0.9975
        elif damage == "mixed_low_edge":
            rgb[25, 49] = [68, 47, 25]
        elif damage == "blue_low_edge":
            rgb[25, 49] = [17, 13, 76]
        elif damage in {"mixed_plane_edge", "mixed_background_edge", "detached_mixed_plane"}:
            rgb[25:30, 49], depth[25:30, 49] = [60, 74, 35], 1.0
            if damage == "mixed_background_edge":
                depth[25, 49] = 1.05
            elif damage == "detached_mixed_plane":
                rgb[22, 48], depth[22, 48] = [60, 74, 35], 1.0
        elif damage == "connected_low_sidewall":
            rgb[25:30, 48], depth[25:30, 48] = [76, 17, 13], 0.9975
        elif damage == "mixed_after_low_sidewall":
            rgb[25:30, 48], depth[25:30, 48] = [60, 74, 35], 1.0
    matrix = list(reference.camera_to_world)
    if translated:
        rgb[:, :-1] = rgb[:, 1:]
        rgb[:, -1] = 100
        depth[:, :-1] = depth[:, 1:]
        depth[:, -1] = 1.0
        matrix[3] += 0.01
    png = io.BytesIO()
    Image.fromarray(rgb).save(png, format="PNG")
    return RGBDObservation.model_validate(reference.model_dump() | {
        "frame_id": "partial", "observation_id": "partial", "checksum_sha256": "",
        "rgb_png_base64": base64.b64encode(png.getvalue()).decode(),
        "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
        "valid_mask_base64": None, "camera_to_world": tuple(matrix),
        "calibration_version": "translated" if translated else reference.calibration_version,
    })


@pytest.mark.parametrize("translated", [False, True])
def test_foreground_occlusion_keeps_static_region_only_with_current_support(translated):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    tracked = tracker(reference)
    observation = partial_region(reference, translated=translated)
    assert tracked._geometry(observation, tracked.destination_color, target=False)[0] is None
    region, reason = measure_servo_region(observation, tracked)
    assert region is not None, reason
    assert region["center"] == pytest.approx(tracked.destination["center"])
    assert region["source"] == "CURRENT_RGBD_REPROJECTED_STATIC_REGION_SUPPORT"
    assert region["occluded_pixels"] > 0
    assert region["observed_corner_anchors"] >= 3
    assert region["formal_geometry_qualification"] == "UNKNOWN"


@pytest.mark.parametrize("damage", ["coplanar", "background", "invalid", "decoy",
                                  "two_corners", "missing", "interior_depth_spike"])
def test_reference_never_fills_unexplained_current_missing_region(damage):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    tracked = tracker(reference)
    region, reason = measure_servo_region(partial_region(reference, damage), tracked)
    assert region is None and reason


def test_mixed_foreground_edge_is_not_counted_as_region_plane_support():
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    tracked = tracker(reference)
    region, reason = measure_servo_region(
        partial_region(reference, "mixed_foreground_edge"), tracked,
    )
    assert region is not None, reason
    assert region["occluded_pixels"] == 26


@pytest.mark.parametrize("damage", ["shaded_green", "shaded_green_spike", "shaded_green_invalid"])
def test_current_green_hue_survives_gray_lighting_without_ignoring_its_depth(damage):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    region, reason = measure_servo_region(partial_region(reference, damage), tracker(reference))
    if damage == "shaded_green":
        assert region is not None, reason
    else:
        assert region is None and reason


@pytest.mark.parametrize("damage", ["low_red_edge", "mixed_low_edge", "blue_low_edge",
                                  "coplanar_red_edge", "detached_low_red"])
@pytest.mark.parametrize("bound", [None, 0.001])
def test_low_sidewall_needs_current_foreground_neighbor_target_color_and_positive_height(
    damage, bound,
):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    region, reason = measure_servo_region(
        partial_region(reference, damage), tracker(reference, depth_error_bound_m=bound),
    )
    if damage in {"low_red_edge", "mixed_low_edge"}:
        assert region is not None, reason
        assert region["low_object_sidewall_pixels"] == 5
    else:
        assert region is None and reason


@pytest.mark.parametrize("bound", [None, 0.001])
@pytest.mark.parametrize("damage", ["connected_low_sidewall", "mixed_after_low_sidewall"])
def test_measured_sidewall_connects_to_high_foreground_before_its_raster_edge(bound, damage):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    region, reason = measure_servo_region(
        partial_region(reference, damage), tracker(reference, depth_error_bound_m=bound),
    )
    if bound is not None and damage == "mixed_after_low_sidewall":
        assert region is None and reason
    else:
        assert region is not None, reason
        assert region["low_object_sidewall_pixels"] == (10 if damage == "connected_low_sidewall"
                                                       else 5)
        assert region["mixed_occluder_footprint_pixels"] == (
            5 if damage == "mixed_after_low_sidewall" else 0
        )


@pytest.mark.parametrize("damage", ["mixed_plane_edge", "mixed_background_edge",
                                  "detached_mixed_plane"])
@pytest.mark.parametrize("bound", [None, 0.001])
def test_only_uncalibrated_visibility_can_exclude_current_mixed_boundary_footprint(damage, bound):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    region, reason = measure_servo_region(
        partial_region(reference, damage), tracker(reference, depth_error_bound_m=bound),
    )
    if damage == "mixed_plane_edge" and bound is None:
        assert region is not None, reason
        assert region["mixed_occluder_footprint_pixels"] == 5
        assert region["formal_geometry_qualification"] == "UNKNOWN"
    else:
        assert region is None and reason


@pytest.mark.parametrize("locations", [((21, 45), (22, 45)), ((22, 48), (32, 56))])
def test_uncalibrated_depth_band_never_claims_a_calibrated_plane_interval(locations):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    observation = partial_region(reference)
    depth = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").copy()
    depth = depth.reshape(observation.height, observation.width)
    depth[locations[0]], depth[locations[1]] = 0.993, 1.007
    observation = RGBDObservation.model_validate(observation.model_dump() | {
        "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
        "checksum_sha256": "", "valid_mask_base64": None,
    })
    region, _ = measure_servo_region(observation, tracker(reference, depth_error_bound_m=None))
    assert region and region["formal_geometry_qualification"] == "UNKNOWN"
    assert measure_servo_region(observation, tracker(reference))[0] is None


def test_moved_camera_cannot_use_the_original_pixel_support():
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    tracked = tracker(reference)
    observation = partial_region(reference)
    matrix = list(observation.camera_to_world)
    matrix[3] += 0.10  # Pixels did not move with the claimed camera.
    observation = RGBDObservation.model_validate(observation.model_dump() | {
        "camera_to_world": tuple(matrix), "calibration_version": "moved",
        "checksum_sha256": "",
    })
    assert measure_servo_region(observation, tracked)[0] is None


def oblique_region(reference, *, damage=None):
    """Render the same measured horizontal region with analytic optical rays."""
    angle = np.deg2rad(24)
    rotation = np.array([[1, 0, 0], [0, -np.cos(angle), np.sin(angle)],
                         [0, -np.sin(angle), -np.cos(angle)]])
    transform = np.eye(4)
    transform[:3, :3], transform[:3, 3] = rotation, [0, -0.4, 1]
    yy, xx = np.indices((reference.height, reference.width))
    fx, fy, cx, cy = reference.intrinsics
    rays = np.stack(((xx - cx) / fx, (yy - cy) / fy, np.ones(xx.shape)), axis=-1)
    world_rays = rays @ rotation.T
    depth = (-1 / world_rays[:, :, 2]).astype("<f4")
    world = world_rays * depth[:, :, None] + transform[:3, 3]
    green = ((world[:, :, 0] >= 0.05) & (world[:, :, 0] <= 0.20)
             & (world[:, :, 1] >= -0.03) & (world[:, :, 1] <= 0.12))
    rgb = np.full((*xx.shape, 3), 100, dtype=np.uint8)
    rgb[green] = [20, 230, 20]
    if damage == "occluded":
        inside = green & (world[:, :, 0] > 0.10) & (world[:, :, 0] < 0.14)
        inside &= (world[:, :, 1] > 0.02) & (world[:, :, 1] < 0.07)
        rgb[inside] = 100
        depth[inside] *= 0.8
    png = io.BytesIO()
    Image.fromarray(rgb).save(png, format="PNG")
    return RGBDObservation.model_validate(reference.model_dump() | {
        "frame_id": "oblique", "observation_id": "oblique", "checksum_sha256": "",
        "rgb_png_base64": base64.b64encode(png.getvalue()).decode(),
        "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
        "valid_mask_base64": None, "camera_to_world": tuple(transform.ravel()),
        "calibration_version": "oblique-camera",
    })


@pytest.mark.parametrize("damage", [None, "occluded"])
def test_rotated_camera_reprojects_region_with_current_rgbd(damage):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera")
    tracked = tracker(reference)
    observation = oblique_region(reference, damage=damage)
    region, reason = measure_servo_region(observation, tracked)
    assert region is not None, reason
    assert region["center"] == pytest.approx(tracked.destination["center"])
    assert region["observed_corner_anchors"] >= 3
    assert (region["occluded_pixels"] > 0) == (damage == "occluded")
    # A rotated pose with the old calibration cannot authorize new pixels.
    stale = RGBDObservation.model_validate(observation.model_dump() | {
        "calibration_version": reference.calibration_version, "checksum_sha256": "",
    })
    assert measure_servo_region(stale, tracked)[0] is None


@pytest.mark.parametrize("margin_m", [-5e-6, 5e-6])
def test_calibrated_oblique_sidewall_requires_full_ray_and_pixel_depth_error(margin_m):
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    reference = scene(source="mujoco_camera", resolution=4)
    tracked = tracker(reference, depth_error_bound_m=0.001)
    observation = oblique_region(reference)
    transform = np.array(observation.camera_to_world).reshape(4, 4)
    depth = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4")
    depth = depth.copy().reshape(observation.height, observation.width)
    yy, xx = np.indices(depth.shape)
    fx, fy, cx, cy = observation.intrinsics
    rays = np.stack(((xx - cx) / fx, (yy - cy) / fy, np.ones(xx.shape)), axis=-1)
    world = (rays @ transform[:3, :3].T) * depth[:, :, None] + transform[:3, 3]
    rgb = np.full((*depth.shape, 3), 100, dtype=np.uint8)
    # Same analytic plane and the original repeated fixture's green footprint.
    green = ((world[:, :, 0] >= 0.05) & (world[:, :, 0] <= 0.2075)
             & (world[:, :, 1] >= -0.0375) & (world[:, :, 1] <= 0.12))
    rgb[green] = [20, 230, 20]
    x, y, bound = 205, 151, 0.001
    derivative = float(transform[2, :3] @ rays[y, x])
    pixel_derivative = abs(transform[2, 0]) / (2 * fx) + abs(transform[2, 1]) / (2 * fy)
    # Solve the independent height threshold including the depth/pixel cross
    # term; float32 quantization is much smaller than this 5 micrometre margin.
    height = (tracked.destination["uncertainty_m"][2] + abs(derivative) * bound
              + pixel_derivative * (bound - transform[2, 3] / derivative) + margin_m)
    height /= 1 - pixel_derivative / derivative
    rgb[y, x], depth[y, x] = [76, 17, 13], (height - transform[2, 3]) / derivative
    rgb[y - 1, x] = [76, 17, 13]
    depth[y - 1, x] = (0.03 - transform[2, 3]) / (transform[2, :3] @ rays[y - 1, x])
    png = io.BytesIO()
    Image.fromarray(rgb).save(png, format="PNG")
    observation = RGBDObservation.model_validate(observation.model_dump() | {
        "rgb_png_base64": base64.b64encode(png.getvalue()).decode(),
        "depth_float32_base64": base64.b64encode(depth.tobytes()).decode(),
        "checksum_sha256": "", "valid_mask_base64": None,
    })
    region, reason = measure_servo_region(observation, tracked)
    if margin_m < 0:
        assert region is None and reason == "region_missing_color_not_explained_by_foreground"
    else:
        assert region is not None, reason
        assert region["observed_corner_anchors"] == 4
        assert region["low_object_sidewall_pixels"] == 1
