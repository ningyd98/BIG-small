"""Real zero-step mechanical controls and analytic shape tests for the reset clearance gate."""

import math

import mujoco
import numpy as np
import pytest
from scripts.graduation import g1_dual_asset as asset


def _api(name):
    assert hasattr(asset, name), "missing positive geometric separation gate: " + name
    return getattr(asset, name)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (mujoco.mjtGeom.mjGEOM_CAPSULE, [0.10071067811865, 0.03, 0.10071067811865]),
        (mujoco.mjtGeom.mjGEOM_CYLINDER, [0.09192388155425, 0.03, 0.09192388155425]),
    ],
)
def test_tilted_round_geometry_uses_its_world_axis(kind, expected):
    diagonal = math.sqrt(0.5)
    rotation = [[diagonal, 0, diagonal], [0, 1, 0], [-diagonal, 0, diagonal]]
    bounds = _api("compiled_world_bounds")(kind, [0.03, 0.10, 0], [0, 0, 0], rotation)
    assert bounds["maximum_world_m"] == pytest.approx(expected, abs=1e-12)
    assert np.asarray(bounds["minimum_world_m"]) == pytest.approx(-np.asarray(expected), abs=1e-12)


def test_rotated_box_and_invalid_compiled_parameters():
    bounds = _api("compiled_world_bounds")
    s = math.sqrt(0.5)
    rot = [[s, -s, 0], [s, s, 0], [0, 0, 1]]
    result = bounds(mujoco.mjtGeom.mjGEOM_BOX, [0.1, 0.2, 0.3], [0, 0, 0.3], rot)
    assert result["maximum_world_m"] == pytest.approx([0.3 * s, 0.3 * s, 0.6])
    for args in (
        (mujoco.mjtGeom.mjGEOM_MESH, [1, 1, 1], [0, 0, 0], rot),
        (mujoco.mjtGeom.mjGEOM_BOX, [-1, 1, 1], [0, 0, 0], rot),
        (mujoco.mjtGeom.mjGEOM_BOX, [1, 1, 1], [float("nan"), 0, 0], rot),
        (mujoco.mjtGeom.mjGEOM_BOX, [1, 1, 1], [0, 0, 0], np.ones((3, 3))),
    ):
        with pytest.raises(ValueError):
            bounds(*args)


@pytest.mark.parametrize("gap", [0.0, -0.00005, 0.06801])
def test_exact_compiled_support_table_clearance_at_touch_penetration_and_separation(gap):
    audit = _api("reset_pair_clearance")
    scene = f"""<mujoco><worldbody>
        <geom name="table" type="box" pos=".35 0 -.025" size=".65 .45 .025"/>
        <body name="fixture" pos=".45 .0425 {gap + 0.001:.17g}"><freejoint/>
        <geom name="fixture_support" type="box" size=".006 .0075 .001"/></body>
        </worldbody></mujoco>"""
    model = mujoco.MjModel.from_xml_string(scene)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    actual = (
        data.geom("fixture_support").xpos[2]
        - model.geom("fixture_support").size[2]
        - data.geom("table").xpos[2]
        - model.geom("table").size[2]
    )
    assert actual == pytest.approx(gap, abs=1e-15)
    if gap <= 0:
        with pytest.raises(ValueError):
            audit(model, data, "fixture_support", "table")
    else:
        result = audit(model, data, "fixture_support", "table")
        assert result["raw_mj_geomDistance_m"] == 0.0
        assert result["table_vertical_gap_m"] == pytest.approx(gap, abs=1e-12)
        assert gap - 3e-12 < result["expanded_aabb_lower_bound_m"] < gap
        assert result["raw_zero_despite_separation"] and not result["contact_observed"]
    assert data.time == 0


def test_overlapping_boxes_in_world_projection_require_a_proof_even_when_api_is_positive():
    audit = _api("reset_pair_clearance")
    scene = """<mujoco><worldbody>
        <geom name="fixed" type="box" euler="0 0 45" size=".1 .005 .005"/>
        <body pos="-.01414213562373095 .01414213562373095 0" euler="0 0 45"><freejoint/>
        <geom name="part" type="box" size=".1 .005 .005"/></body></worldbody></mujoco>"""
    model = mujoco.MjModel.from_xml_string(scene)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    assert (
        mujoco.mj_geomDistance(
            model, data, model.geom("part").id, model.geom("fixed").id, 3.0, None
        )
        > 0
    )
    assert data.ncon == 0
    with pytest.raises(ValueError, match="strict separation"):
        audit(model, data, "part", "fixed")
