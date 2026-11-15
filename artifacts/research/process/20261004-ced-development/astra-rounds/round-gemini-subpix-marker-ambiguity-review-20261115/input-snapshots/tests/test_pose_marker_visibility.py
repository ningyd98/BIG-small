"""Outboard-marker development asset; no renderer or admission in these checks."""

from __future__ import annotations

import importlib
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "assets/robots/franka_panda/scene.xml"
OLD = BASE.with_name("scene_pose_marker_color_v2.xml")


def api():
    module = "cloud_edge_robot_arm.vision.pose_marker_visibility"
    assert importlib.util.find_spec(module) is not None, "outboard visibility asset is missing"
    return importlib.import_module(module)


def test_outboard_tag_is_rigidly_attached_outside_cube_without_changing_original_geometry():
    before, centered = BASE.read_bytes(), OLD.read_bytes()
    generated = api().build_outboard_pose_marker_xml(before)
    assert generated == api().build_outboard_pose_marker_xml(before)
    tree = ET.fromstring(generated)
    original = {node.get("name"): node for node in ET.fromstring(before).iter() if node.get("name")}
    modified = {node.get("name"): node for node in tree.iter() if node.get("name")}
    for name, node in original.items():
        assert modified[name].attrib == node.attrib
    body = tree.find("./worldbody/body[@name='object']")
    assert body is not None
    additions = [node for node in body.findall("geom") if node.get("name") not in original]
    assert len(additions) == 37
    quiet = next(node for node in additions if node.get("name") == "pose_marker_outboard_v3_quiet")
    assert [float(v) for v in quiet.get("pos").split()] == pytest.approx([0.1, 0, 0.03502])
    assert [float(v) for v in quiet.get("size").split()] == pytest.approx([0.03, 0.03, 0.00001])
    assert (
        min(
            float(node.get("pos").split()[0]) - float(node.get("size").split()[0])
            for node in additions
        )
        > 0.035
    )
    assert all(node.get("mass") == node.get("density") == "0" for node in additions)
    assert all(node.get("contype") == node.get("conaffinity") == "0" for node in additions)
    assert BASE.read_bytes() == before and OLD.read_bytes() == centered


@pytest.mark.parametrize("mutation", [b'mass="0.09"', b'mass="0.07"'])
def test_changed_physical_base_cannot_generate_the_registered_visible_variant(mutation):
    with pytest.raises(ValueError, match="frozen base"):
        api().build_outboard_pose_marker_xml(BASE.read_bytes().replace(b'mass="0.08"', mutation))


def test_outboard_pattern_is_same_strict_id7_dictionary_and_metric_size():
    from cloud_edge_robot_arm.vision.pose_marker_assets import build_colored_pose_marker_xml

    centered = ET.fromstring(build_colored_pose_marker_xml(BASE.read_bytes()))
    moved = ET.fromstring(api().build_outboard_pose_marker_xml(BASE.read_bytes()))
    cells = [node for node in moved.iter("geom") if "outboard_v3_r" in node.get("name", "")]
    assert len(cells) == 36
    for cell in cells:
        original = centered.find(
            ".//geom[@name='" + cell.get("name").replace("outboard_v3", "color_v2") + "']"
        )
        assert original is not None
        assert cell.get("rgba") == original.get("rgba")
        assert cell.get("size") == original.get("size")
        old_pos = np.fromstring(original.get("pos"), sep=" ")
        new_pos = np.fromstring(cell.get("pos"), sep=" ")
        assert np.allclose(new_pos - old_pos, [0.1, 0, 0], atol=1e-12, rtol=0)


def test_compiled_outboard_asset_retains_physics_camera_and_controller():
    import mujoco

    original = mujoco.MjModel.from_xml_path(str(BASE))
    marked = mujoco.MjModel.from_xml_string(
        api().build_outboard_pose_marker_xml(BASE.read_bytes()).decode()
    )
    for field in ("nq", "nv", "nu", "nbody", "njnt", "ncam", "nsite"):
        assert getattr(marked, field) == getattr(original, field)
    for field in (
        "body_mass",
        "body_inertia",
        "body_ipos",
        "body_iquat",
        "body_pos",
        "body_quat",
        "jnt_type",
        "jnt_axis",
        "jnt_pos",
        "jnt_range",
        "dof_damping",
        "dof_armature",
        "actuator_gainprm",
        "actuator_biasprm",
        "actuator_ctrlrange",
        "actuator_trnid",
        "cam_pos",
        "cam_quat",
        "cam_fovy",
        "site_pos",
        "site_size",
        "qpos0",
    ):
        assert np.array_equal(getattr(marked, field), getattr(original, field)), field
    for index in range(original.ngeom):
        name = mujoco.mj_id2name(original, mujoco.mjtObj.mjOBJ_GEOM, index)
        other = marked.geom(name).id
        for field in (
            "geom_type",
            "geom_size",
            "geom_pos",
            "geom_quat",
            "geom_contype",
            "geom_conaffinity",
            "geom_friction",
            "geom_solref",
            "geom_solimp",
            "geom_margin",
            "geom_gap",
            "geom_rgba",
        ):
            assert np.array_equal(getattr(original, field)[index], getattr(marked, field)[other])
