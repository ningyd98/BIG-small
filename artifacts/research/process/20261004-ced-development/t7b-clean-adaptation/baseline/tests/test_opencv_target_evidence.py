"""Real image/metric fixtures catch unsafe identity and incomplete-extent claims."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def scene(
    frame="initial",
    *,
    time=0.0,
    x=10,
    lift=0.0,
    damage=None,
    started=None,
    resolution=1,
    **metadata,
):
    """Downward optical camera: red 60mm top, green 160mm flat target."""
    rgb = np.full((64, 80, 3), 100, dtype=np.uint8)
    depth = np.full((64, 80), 1.0, dtype="<f4")
    rgb[20:36, 45:61] = [20, 230, 20]
    rgb[24:30, x : x + 6] = [230, 20, 20]
    depth[24:30, x : x + 6] = 0.94 - lift
    if damage == "missing":
        rgb[24:30, x : x + 6] = 100
    elif damage == "decoy":
        rgb[5:11, 10:16] = [230, 20, 20]
        depth[5:11, 10:16] = 0.94
    elif damage == "occluded":
        rgb[24:30, x + 2 : x + 4] = 100
        depth[24:30, x + 2 : x + 4] = 0.8
    elif damage == "partial":
        rgb[24:30, x : x + 2] = 100
        depth[24:30, x : x + 2] = 0.8
    elif damage == "edge_occluder":
        depth[24:30, x - 1] = 0.8
    elif damage == "invalid_edge":
        depth[24:30, x - 1] = 0
    elif damage == "mild_edge":
        depth[24:30, x - 1] = 0.938
    elif damage == "coplanar_edge":
        depth[24:30, x - 1] = 0.94 - lift
    elif damage == "depth":
        depth[26, x + 2] = 0
    elif damage == "depth_spike":
        depth[26, x + 2] = 0.8
    elif damage == "wrong_color":
        rgb[24:30, x : x + 6] = [20, 20, 230]
    rgb = np.repeat(np.repeat(rgb, resolution, axis=0), resolution, axis=1)
    depth = np.repeat(np.repeat(depth, resolution, axis=0), resolution, axis=1)
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    return RGBDObservation(
        frame_id=frame,
        captured_at=(started or datetime.now(UTC) - timedelta(seconds=2)) + timedelta(seconds=time),
        sim_time_s=time,
        width=80 * resolution,
        height=64 * resolution,
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        intrinsics=tuple(v * resolution for v in (100.0, 100.0, 40.0, 32.0)),
        camera_to_world=(
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        **{
            "source": "rgbd_camera",
            "episode_id": "device-evidence",
            "calibration_version": "test-cal",
            **metadata,
        },
    )


def tracker(observation=None, **changes):
    module = import_module("cloud_edge_robot_arm.vision.tracking")
    resolution = (observation.width // 80) if observation is not None else 1
    return module.OpenCVTargetTracker(
        observation or scene(),
        {
            "original_pixel_target": [12 * resolution, 26 * resolution],
            "original_pixel_destination": [57 * resolution, 32 * resolution],
            "top_grasp_support_height_m": 0.0,
            "depth_error_bound_m": 0.001,
            **changes,
        },
    )


def test_uniquely_visible_target_has_metric_extent_and_provenance():
    original = scene()
    tracked = tracker(original)
    current = scene("next", time=0.1, started=original.captured_at)
    fact = tracked.facts(current)["target_visible"]
    assert fact["value"] is True
    assert fact["identity_confirmed"] is True
    assert fact["observation_id"] == "next"
    assert fact["captured_at"] == current.captured_at.isoformat()
    assert fact["calibration_version"] == "test-cal"
    extent = fact["measured_values"]
    assert extent["extent_complete"] is True
    assert extent["min"][0] <= -0.286
    assert extent["max"][0] >= -0.2303  # outer edge: (15.5 - 40) * 0.94 / 100
    assert extent["center"][2] == pytest.approx(0.06, abs=1e-6)


@pytest.mark.parametrize(
    "damage", ["missing", "decoy", "occluded", "partial", "depth", "depth_spike", "wrong_color"]
)
def test_missing_ambiguous_occluded_or_invalid_depth_is_unknown(damage):
    original = scene()
    facts = tracker(original).facts(
        scene("next", time=0.1, damage=damage, started=original.captured_at)
    )
    assert facts["target_visible"]["value"] is None
    assert facts["object_inside_target_region"]["value"] is None
    assert facts["target_visible"]["reasons"]


def test_invalid_initial_identity_rejects_before_executor_can_start():
    with pytest.raises(ValueError):
        tracker(scene(damage="decoy"))


def test_old_crop_cannot_create_fresh_extent_evidence():
    original = scene()
    facts = tracker(original).facts(original.crop((0, 0, 70, 50)))
    assert facts["target_visible"]["value"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"episode_id": "another"},
        {"calibration_version": "another"},
        {"frame_id": "renamed", "observation_id": "renamed"},
    ],
)
def test_new_name_without_new_capture_or_changed_binding_is_unknown(changes):
    original = scene()
    changed = original.model_copy(update=changes)
    assert tracker(original).facts(changed)["target_visible"]["value"] is None


def test_partial_pixels_inside_region_do_not_prove_whole_object_inside():
    original = scene()
    tracked = tracker(original)
    for index, x in enumerate((20, 30, 40, 44), 1):
        facts = tracked.facts(
            scene(str(index), time=index * 0.1, x=x, started=original.captured_at)
        )
    assert facts["object_inside_target_region"]["value"] is False


def test_occluded_extent_cannot_prove_placement():
    original = scene()
    tracked = tracker(original)
    for index, x in enumerate((20, 30, 40, 48), 1):
        tracked.facts(scene(str(index), time=index * 0.1, x=x, started=original.captured_at))
    facts = tracked.facts(
        scene("occluded", time=0.5, x=48, damage="partial", started=original.captured_at)
    )
    assert facts["object_inside_target_region"]["value"] is None


def test_absent_depth_error_bound_cannot_prove_placement():
    original = scene()
    tracked = tracker(original, depth_error_bound_m=None)
    assert tracked.facts(original)["object_inside_target_region"]["value"] is None


def test_foreground_at_contour_edge_cannot_certify_complete_extent():
    initial = scene()
    facts = tracker(initial).facts(
        scene("new", time=0.1, damage="edge_occluder", started=initial.captured_at)
    )
    assert facts["target_visible"]["value"] is None


def test_full_extent_contains_supported_upright_body_not_only_top_surface():
    initial = scene()
    fact = tracker(initial).facts(initial)["target_visible"]
    assert fact["measured_values"]["full_extent_min"][2] <= 0.0
    assert fact["measured_values"]["full_extent_max"][2] >= 0.06


def image_variant(observation, change):
    """Build valid checksummed acquisitions after a test-owned raster mutation."""
    rgb = np.array(Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))))
    depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(
        observation.height, observation.width
    )
    change(rgb, depth)
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    payload = observation.model_dump()
    payload.update(
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
    )
    return RGBDObservation.model_validate(payload)


@pytest.mark.parametrize("topology", ["rotated", "hole", "notch"])
def test_unsupported_region_topology_cannot_certify_aabb_placement(topology):
    def alter(rgb, depth):
        if topology == "rotated":
            rgb[20:36, 45:61] = 100
            yy, xx = np.indices(depth.shape)
            rgb[(abs(xx - 53) + abs(yy - 28)) <= 11] = [20, 230, 20]
        elif topology == "hole":
            rgb[23:27, 48:52] = 100
        else:
            rgb[20:29, 45:50] = 100

    invalid = image_variant(scene(), alter)
    with pytest.raises(ValueError):
        tracker(invalid)


@pytest.mark.parametrize("damage", ["invalid_edge", "mild_edge", "coplanar_edge"])
def test_unresolved_depth_at_outer_boundary_is_unknown(damage):
    initial = scene()
    facts = tracker(initial).facts(
        scene("new", time=0.1, damage=damage, started=initial.captured_at)
    )
    assert facts["target_visible"]["value"] is None


@pytest.mark.parametrize("episode", [None, ""])
def test_initial_capture_requires_nonempty_episode_binding(episode):
    with pytest.raises(ValueError):
        tracker(scene(episode_id=episode))


def test_stale_initial_capture_cannot_establish_lift_baseline():
    with pytest.raises(ValueError):
        tracker(scene(started=datetime.now(UTC) - timedelta(seconds=10)))


def test_placement_uncertainty_overlap_is_unknown_not_definite_failure():
    initial = scene()
    tracked = tracker(initial)
    for index, x in enumerate((20, 30, 40, 46), 1):
        facts = tracked.facts(scene(str(index), time=index * 0.1, x=x, started=initial.captured_at))
    assert facts["object_inside_target_region"]["value"] is None


@pytest.mark.parametrize("occluder_depth", [0.0, 0.938, 0.94])
def test_small_missing_strip_with_unresolved_depth_cannot_shrink_full_extent(occluder_depth):
    initial = scene(resolution=3)
    tracked = tracker(initial)
    current = scene("new", time=0.1, resolution=3, started=initial.captured_at)

    def hide_strip(rgb, depth):
        rgb[72:90, 30:32] = 100
        depth[72:90, 30:32] = occluder_depth

    facts = tracked.facts(image_variant(current, hide_strip))
    assert facts["target_visible"]["value"] is None
    assert facts["object_inside_target_region"]["value"] is None


def test_world_rotated_region_is_rejected_even_with_rectangular_image_support():
    angle = np.pi / 4
    payload = scene().model_dump()
    payload.update(
        camera_to_world=(
            np.cos(angle),
            np.sin(angle),
            0.0,
            0.0,
            np.sin(angle),
            -np.cos(angle),
            0.0,
            0.0,
            0.0,
            0.0,
            -1.0,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        checksum_sha256="",
    )
    with pytest.raises(ValueError):
        tracker(RGBDObservation.model_validate(payload))


def test_observed_horizontal_plane_with_pitched_camera_is_unsupported():
    original = scene(resolution=10)
    pitch = np.pi / 6
    cosine, sine = np.cos(pitch), np.sin(pitch)

    def observed_plane(rgb, depth):
        ys = np.indices(depth.shape)[0]
        depth[:] = 1 / (cosine - sine * (ys - 320) / 1000)
        depth[rgb[:, :, 0] > 200] *= 0.94

    pitched = image_variant(original, observed_plane)
    payload = pitched.model_dump()
    payload.update(
        camera_to_world=(
            1.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -cosine,
            -sine,
            0.0,
            0.0,
            sine,
            -cosine,
            1.0,
            0.0,
            0.0,
            0.0,
            1.0,
        ),
        checksum_sha256="",
    )
    acquisition = RGBDObservation.model_validate(payload)
    with pytest.raises(ValueError, match="camera_orientation_not_supported"):
        tracker(acquisition, depth_error_bound_m=0.000001)


def test_equal_corner_depth_does_not_certify_nonplanar_region_interior():
    def deform_region(rgb, depth):
        depth[26:30, 52:56] = 1.006

    acquisition = image_variant(scene(), deform_region)
    with pytest.raises(ValueError, match="region_plane_depth_unresolved"):
        tracker(acquisition, depth_error_bound_m=0.000001)


def saved_development_capture(monkeypatch):
    """Replay immutable development pixels under their original acquisition clock."""
    directory = Path(__file__).resolve().parents[1] / (
        "artifacts/research/process/20261004-ced-development/t7b-real-capture-v2/initial"
    )
    hashes = {
        "observation-full.json": "937f1044ee36332db0bc23598c026fcd67a226ece2e0225787f71cc25b2376e3",
        "rgb.png": "419cab290f50df585986df994273154f5aafa10d50c9b72cd8edac65f6a1c77c",
        "depth.f32": "3b6561d8de1b196dbac5dbc4fff466c09bfbaebd19a5062d568abd19da355481",
    }
    for filename, expected in hashes.items():
        assert hashlib.sha256((directory / filename).read_bytes()).hexdigest() == expected
    acquisition = RGBDObservation.model_validate(
        json.loads((directory / "observation-full.json").read_text())
    )

    class ReplayClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return acquisition.captured_at + timedelta(seconds=1)

    module = import_module("cloud_edge_robot_arm.vision.tracking")
    monkeypatch.setattr(module, "datetime", ReplayClock)
    return acquisition


def real_capture_tracker(observation):
    module = import_module("cloud_edge_robot_arm.vision.tracking")
    return module.OpenCVTargetTracker(
        observation,
        {
            "original_pixel_target": [179, 120],
            "original_pixel_destination": [132, 74],
            "top_grasp_support_height_m": 4.758834838858306e-05,
        },
    )


def test_saved_development_cube_separates_top_from_visible_sides_without_fake_bound(monkeypatch):
    acquisition = saved_development_capture(monkeypatch)
    tracked = real_capture_tracker(acquisition)
    facts = tracked.facts(acquisition)
    observed = facts["target_visible"]["measured_values"]
    assert facts["target_visible"]["value"] is True
    assert observed["silhouette_complete"] is True
    assert observed["top_pixels"] < observed["visible_pixels"]
    assert observed["side_pixels"] > 0
    assert 0.067 < observed["center"][2] < 0.073
    assert observed["observed_body_min"][2] < 0.05
    assert observed["top_plane_status"] == "UNVALIDATED_DEPTH_ERROR_BOUND"
    assert observed["extent_complete"] is False
    assert observed["conservative_full_extent_min"] is None
    for condition in (
        "target_reachable",
        "object_lifted",
        "object_inside_target_region",
        "object_stable",
        "placement_stable",
        "object_placed",
    ):
        assert facts[condition]["value"] is None


def test_saved_antialias_region_uses_observed_inside_rectangle_without_filling_corner(monkeypatch):
    acquisition = saved_development_capture(monkeypatch)
    region = real_capture_tracker(acquisition).destination
    left, top, right, bottom = region["inside_pixel_rectangle"]
    assert left > 117 and right < 146
    assert top > 59 and bottom < 88
    assert region["mask"][top : bottom + 1, left : right + 1].all()
    assert not region["mask"][59, 117]
    assert region["top_plane_status"] == "UNVALIDATED_DEPTH_ERROR_BOUND"


def test_supported_inside_rectangle_does_not_fill_antialias_corner():
    def missing_corner(rgb, depth):
        rgb[20, 45] = 100

    acquisition = image_variant(scene(), missing_corner)
    region = tracker(acquisition).destination
    assert not region["mask"][20, 45]
    assert region["inside_pixel_rectangle"] == [46, 21, 59, 34]
