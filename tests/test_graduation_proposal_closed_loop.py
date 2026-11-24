"""Checks for the independent proposal development allocation and original reset ledger."""

import copy
import hashlib
import math

import numpy as np
import pytest
from scripts.graduation import proposal_closed_loop as study
from scripts.graduation.perception_capture import VIEWS, optical_transform

from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.vision.marker_families import SIDE_PREPARE_ONLY_FAMILY


def geometry():
    return geometry_registration(marker_family_id=SIDE_PREPARE_ONLY_FAMILY)


def test_four_new_poses_and_alternating_paired_order():
    rows = study.allocated_cases("right")
    assert [r["view"] for r in rows] == [
        "nominal",
        "right",
        "right",
        "nominal",
        "nominal",
        "right",
        "right",
        "nominal",
    ]
    assert len({r["id"] for r in rows}) == 8
    nominal = study.allocated_cases("nominal")
    assert len(nominal) == 4
    assert [r["seed"] for r in nominal] == list(range(24112401, 24112405))
    for i in range(4):
        first, second = rows[2 * i : 2 * i + 2]
        assert first["group"] == second["group"] == nominal[i]["group"]
        for field in ("seed", "reset_fixture_center_m", "yaw_rad"):
            assert first[field] == second[field] == nominal[i][field]
    with pytest.raises(ValueError):
        study.allocated_cases("hidden")


def test_camera_must_bind_original_intrinsics_requested_view_and_actual_hash():
    original = geometry()
    cam = original["camera"].copy()
    cam["camera_to_world"] = optical_transform(*VIEWS["left"]).ravel().tolist()
    values = cam["intrinsics"] + cam["camera_to_world"]
    cam["calibration_version"] = hashlib.sha256(
        np.array(values, dtype="<f8").tobytes()
    ).hexdigest()[:16]
    adapted = study.register_camera("left", cam, original)
    assert adapted["camera"] == cam
    assert adapted["pose_marker"] == original["pose_marker"]
    assert study.register_camera("nominal", original["camera"], original) == original
    for bad in (
        {**cam, "calibration_version": original["camera"]["calibration_version"]},
        {**cam, "width": 640},
        original["camera"],
    ):
        with pytest.raises(ValueError, match="camera"):
            study.register_camera("left", bad, original)


def test_reset_readback_checks_original_request_rotation_episode_and_step():
    row = study.allocated_cases("nominal")[0]
    x, y, z = row["reset_fixture_center_m"]
    yaw = row["yaw_rad"]
    co, si = math.cos(yaw), math.sin(yaw)
    state = dict(
        episode_id="unique",
        physics_step=0,
        sim_time_s=0.0,
        object_geom_position_m=[x, y, z],
        object_position_m=[x, y, z],
        object_geom_rotation_row_major=[co, -si, 0, si, co, 0, 0, 0, 1],
    )
    requested = dict(
        seed=row["seed"],
        scenario_id="S01_NORMAL_STATIC",
        object_pose={"x": x, "y": y, "z": z},
        object_yaw_rad=yaw,
    )
    end = dict(
        kind="RESET",
        phase="END",
        operation_id=1,
        error_type=None,
        error=None,
        physics_step=0,
        sim_time_s=0.0,
        episode_id="unique",
        parameters={"requested": requested},
        result={"physics_state": state, "physics_dt_s": 1 / 240},
    )
    begin = {**end, "phase": "BEGIN", "result": None, "episode_id": None, "sim_time_s": None}
    assert study.readback_reset(row, [begin, end])["episode_id"] == "unique"
    for changes in ({"physics_step": 1}, {"episode_id": "another"}, {"error": "interrupted"}):
        with pytest.raises(ValueError, match="reset"):
            study.readback_reset(row, [begin, {**end, **changes}])
    for value in ("object_geom_position_m", "object_geom_rotation_row_major"):
        bad = copy.deepcopy(end)
        bad["result"]["physics_state"][value][0] += 1e-4
        with pytest.raises(ValueError, match="reset"):
            study.readback_reset(row, [begin, bad])
    with pytest.raises(ValueError, match="reset"):
        study.readback_reset({**row, "yaw_rad": -yaw}, [begin, end])


def test_oblique_falls_back_only_for_an_original_orientation_refusal():
    probes = {
        "nominal": {"supported": True, "reason": None},
        "right": {
            "supported": False,
            "reason": "initial registered geometry unavailable: camera_orientation_not_supported",
        },
    }
    assert study.executable_view("right", probes) == "nominal"
    original = {
        **probes["right"],
        "reason": "initial registered observation unavailable: camera_orientation_not_supported",
    }
    assert study.executable_view("right", {**probes, "right": original}) == "nominal"
    assert study.executable_view("nominal", probes) == "nominal"
    with pytest.raises(ValueError, match="unexpected"):
        study.executable_view("right", {**probes, "right": {"supported": False, "reason": "other"}})
    with pytest.raises(ValueError, match="nominal"):
        study.executable_view(
            "right", {**probes, "nominal": {"supported": False, "reason": "missing"}}
        )


def test_probe_file_requires_both_original_path_and_bytes(tmp_path):
    original = tmp_path / "original.json"
    original.write_text('{"supported": true}')
    expected = {original: study.sha(original)}
    assert study.pin_probe(original, expected) == {"supported": True}
    other = tmp_path / "foreign.json"
    other.write_bytes(original.read_bytes())
    with pytest.raises(ValueError, match="path"):
        study.pin_probe(other, expected)
    original.write_text('{"supported": false}')
    with pytest.raises(ValueError, match="SHA256"):
        study.pin_probe(original, expected)
