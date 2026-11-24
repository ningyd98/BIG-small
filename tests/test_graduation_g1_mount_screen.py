"""Regression tests for scoring a moved visible fiducial on the original cube."""

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROUND = "round-g1-marker-mount-20261124"
ROOT = Path(__file__).resolve().parents[1]
PLAN = next(
    (ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds").glob(
        ROUND + "/plan.json"
    )
)
MOUNTS = json.loads(PLAN.read_bytes())["mounts"]


def module(name):
    qualified = "scripts.graduation." + name
    assert importlib.util.find_spec(qualified), f"missing G1 mount implementation {qualified}"
    return __import__(qualified, fromlist=["*"])


def test_compiled_mechanics_and_actual_stored_grid():
    geo = module("g1_mount_geometry")
    rows = [geo.audit_mount(m) for m in MOUNTS]
    assert {r["nonmarker_xml_sha256"] for r in rows} == {
        "6d1c1df9d78eb8106454b9d97e95d4742c79de63295d4f617e97e024a9758d3e"
    }
    assert len({r["compiled_physics_sha256"] for r in rows}) == 1
    assert [r["board_gap_m"] for r in rows] == pytest.approx([0.015, 0.015, 0.055])
    assert all(r["cells"] == 36 for r in rows)
    assert all(len(r["fk"]) == 2 for r in rows)
    assert all(p["max_corner_residual_m"] < 1e-10 for r in rows for p in r["fk"])
    for m in MOUNTS:
        altered = {**m, "object_T_marker_translation_m": [0, 0, 0.03505]}
        with pytest.raises(ValueError):
            geo.audit_mount(altered)
        with pytest.raises(ValueError):
            geo.descriptor({**m, "asset_sha256": "0" * 64})


def test_diagnostic_family_keeps_its_own_geometry_and_native_refusal():
    geo = module("g1_mount_geometry")
    for m in MOUNTS:
        g, reason = geo.descriptor(m)
        assert g["marker_family"] == m["family"]
        assert g["pose_marker"]["marked_asset_sha256"] == m["asset_sha256"]
        assert (reason is None) is m["expected_native_family_admissible"]
        assert np.asarray(g["marker_to_object"]).reshape(4, 4)[:3, 3] == pytest.approx(
            m["object_T_marker_translation_m"]
        )
    wrong = copy.deepcopy(MOUNTS[1])
    wrong["asset_path"] = MOUNTS[0]["asset_path"]
    with pytest.raises(ValueError):
        geo.descriptor(wrong)


def test_measured_target_is_rotated_object_tcp_for_two_yaws():
    geo = module("g1_mount_geometry")
    g, _ = geo.descriptor(MOUNTS[1])
    center = [0.45, 0, 0.035]
    for rotation, marker in [
        (np.eye(3), [0.55, 0, 0.07005]),
        (np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]]), [0.45, 0.1, 0.07005]),
    ]:
        target = [0.45, 0, 0.045]
        result = geo.verify_target(g, marker, rotation, target)
        assert result["object_center_world_m"] == pytest.approx(center)
        assert result["object_top_world_m"] == pytest.approx([0.45, 0, 0.07])
        with pytest.raises(ValueError, match="TCP"):
            geo.verify_target(g, marker, rotation, marker)
        incorrect, _ = geo.descriptor(MOUNTS[0])
        with pytest.raises(ValueError, match="TCP"):
            geo.verify_target(incorrect, marker, rotation, target)


def test_select_excludes_original_and_nonregistrable_candidate_and_allows_zero():
    screen = module("g1_mount_screen")
    rows = {
        "original": {"usable": 8, "evaluated": 8, "native": True, "probe_successes": 2},
        "r579": {"usable": 0, "evaluated": 8, "native": True, "probe_successes": 0},
        "component_v1": {"usable": 8, "evaluated": 8, "native": False, "probe_successes": 0},
    }
    assert screen.choose(rows) == "r579"
    rows["component_v1"].update(native=True, probe_successes=1)
    assert screen.choose(rows) == "component_v1"
    rows["r579"].update(usable=8, probe_successes=1)
    assert screen.choose(rows) == "r579"
    rows["r579"]["evaluated"] = 7
    with pytest.raises(ValueError):
        screen.choose(rows)
