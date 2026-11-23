"""Development grid, pixel-only decisions and independently paired scoring controls."""

from __future__ import annotations

import base64
import inspect

import numpy as np
import pytest

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_pose_marker_evidence import observation, registration


def test_preregistered_grid_contains_every_group_height_view_and_step() -> None:
    from scripts.graduation.perception_capture import allocated_cells

    cells = allocated_cells()
    assert len(cells) == len({cell["id"] for cell in cells}) == 54
    assert len({cell["seed"] for cell in cells}) == 54
    assert len({cell["scene_id"] for cell in cells}) == 54
    assert sum(len(cell["steps"]) for cell in cells) == 324
    assert {tuple(cell["steps"]) for cell in cells} == {(0, 1, 2, 4, 8, 12)}
    for split in ("exploration", "holdout"):
        selected = [c for c in cells if c["split"] == split]
        assert len(selected) == 27
        assert len({c["group"] for c in selected}) == 3
        assert {c["initial_height_offset_m"] for c in selected} == {0, 0.05, 0.085}
        assert {c["view"] for c in selected} == {"axial", "left", "right"}


@pytest.mark.parametrize("bias", [-10, -5, 0, 5, 10, None])
def test_depth_bias_is_in_optical_millimetres_and_preserves_source(bias: int | None) -> None:
    from scripts.graduation.perception_pixels import biased_observation

    base = observation()
    depths = np.frombuffer(base64.b64decode(base.depth_float32_base64), "<f4").copy()
    depths[0] = 0
    base = RGBDObservation.model_validate(
        {
            **base.model_dump(),
            "depth_float32_base64": base64.b64encode(depths.tobytes()).decode(),
            "valid_mask_base64": None,
            "checksum_sha256": "",
        }
    )
    derived = biased_observation(base, bias)
    after = np.frombuffer(base64.b64decode(derived.depth_float32_base64), "<f4")
    assert derived.frame_id != base.frame_id
    assert derived.observation_id == derived.frame_id
    assert derived.checksum_sha256 != base.checksum_sha256
    assert derived.rgb_png_base64 == base.rgb_png_base64
    assert (derived.camera_to_world, derived.intrinsics, derived.calibration_version) == (
        base.camera_to_world,
        base.intrinsics,
        base.calibration_version,
    )
    assert np.array_equal(
        after,
        0 * depths
        if bias is None
        else np.where(
            depths > 0,
            depths + bias / 1000,
            0,
        ).astype("<f4"),
    )
    assert derived.valid_mask_bytes() == (after > 0).astype("u1").tobytes()


def test_pixel_api_excludes_truth_and_rejects_no_depth() -> None:
    from dataclasses import asdict

    from scripts.graduation.perception_pixels import biased_observation, measure

    base = observation()
    geometry = {
        "pose_marker": asdict(registration()),
        "marker_to_object": np.eye(4).ravel().tolist(),
        "object_half_extent_m": [0.035] * 3,
    }
    assert list(inspect.signature(measure).parameters) == ["frame", "geometry", "mode"]
    observed = measure(base, geometry, "SUBPIX")
    assert observed["status"] == "OBSERVED"
    assert observed["object_top_center_world_m"][2] == pytest.approx(0.535, abs=0.002)
    assert observed["effective_depth_bound_m"] is None
    assert observed["interval_motion_bound_m_s"] is None
    with pytest.raises(TypeError):
        measure(base, geometry, "SUBPIX", truth={"center": [0, 0, 0.5]})
    changed = biased_observation(base, 10)
    assert measure(changed, geometry, "SUBPIX")["object_top_center_world_m"][2] == pytest.approx(
        observed["object_top_center_world_m"][2] - 0.010,
        abs=2e-7,
    )
    zero = measure(biased_observation(base, 0), geometry, "SUBPIX")
    assert zero == observed
    missing = measure(biased_observation(base, None), geometry, "SUBPIX")
    assert (missing["status"], missing["reason"]) == ("UNKNOWN", "marker_metric_depth_unavailable")
    assert missing["object_top_center_world_m"] is None


def test_unknown_and_unacquired_stay_in_denominator_without_zero_error() -> None:
    from scripts.graduation.perception_score import describe

    rows = []
    for status, metric in [("OBSERVED", 0.004), ("UNKNOWN", None), ("NOT_CAPTURED", None)]:
        rows.append(
            {
                "status": status,
                "reason": status,
                "group": "p1",
                "cell_id": "c1",
                "step": len(rows),
                "metrics": {}
                if metric is None
                else {
                    "object_top_center_3d_m": metric,
                },
            }
        )
    result = describe(rows)
    assert result["allocated"] == 3 and result["captured"] == 2 and result["observed"] == 1
    assert result["coverage"] == pytest.approx(1 / 3)
    assert result["errors"]["object_top_center_3d_m"]["p90"] == 0.004
    assert result["errors"]["object_top_center_3d_m"]["n"] == 1
    assert describe(rows[1:])["errors"]["object_top_center_3d_m"] is None


def test_pairing_rejects_changed_truth_episode_step_frame_and_checksum() -> None:
    from scripts.graduation.perception_score import same_acquisition

    key = {
        "cell_id": "test",
        "step": 2,
        "scene_id": "scene",
        "episode_id": "episode",
        "sim_time_s": 2 / 240,
        "frame_id": "rgbd-a",
        "checksum_sha256": "a" * 64,
    }
    same_acquisition(key, dict(key))
    for name in key:
        with pytest.raises(ValueError, match="acquisition"):
            same_acquisition(key, {**key, name: "other"})


def test_interleaved_camera_observers_keep_their_own_frame_and_counts() -> None:
    from collections import Counter
    from types import SimpleNamespace

    from scripts.graduation.perception_capture import cell_observer

    first_counts, next_counts = Counter(), Counter()
    first_source, next_source = {}, {}
    first = cell_observer(first_counts, first_source)
    second = cell_observer(next_counts, next_source)

    def event(kind="CAPTURE", phase="END", result=None, error=None, number=1):
        return SimpleNamespace(
            kind=kind,
            phase=phase,
            result=result,
            error_type=error,
            physics_step=number,
            operation_id=number + 10,
        )

    def capture(name):
        return {"pass_state_hashes": [name, name], "sensor_frame": {"frame_id": name}}

    first(event(result=capture("first"), number=1))
    second(event(kind="PHYSICS", result=capture("skip")))
    second(event(phase="BEGIN", result=capture("skip")))
    second(event(result=capture("second"), number=4))
    first(event(error="CameraUnavailable", number=5))
    second(event(result=capture("last"), number=8))
    assert first_source == {
        "step": 1,
        "operation_id": 11,
        "frame_id": "first",
        "pass_state_hashes": ["first"] * 2,
    }
    assert next_source == {
        "step": 8,
        "operation_id": 18,
        "frame_id": "last",
        "pass_state_hashes": ["last"] * 2,
    }
    assert first_counts == {"camera_acquisitions": 2, "capture_failures": 1, "render_passes": 2}
    assert next_counts == {"camera_acquisitions": 2, "render_passes": 4}
