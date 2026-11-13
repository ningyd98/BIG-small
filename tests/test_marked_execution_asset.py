"""开发标记变体必须证明物理结构一致，不能仅跳过资产哈希。"""

import importlib
from pathlib import Path

import pytest

from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.top_grasp import calibration_asset_sha256

ROOT = Path(__file__).resolve().parents[1]


def api():
    return importlib.import_module("cloud_edge_robot_arm.vision.marked_asset")


@pytest.mark.parametrize(
    "family_id",
    ["outboard_id7_45mm_v3", "side_y_plus_id7_75mm_r593", "side_y_plus_id7_75mm_component_v1"],
)
def test_exact_registered_visual_only_asset_has_development_receipt(family_id):
    family = marker_family(family_id)
    receipt = api().validate_development_marker_asset(
        ROOT / family.asset_path, "mujoco_upright_box_v2", family_id
    )
    assert receipt["physics_equivalent"] is True
    assert receipt["scope"] == "MUJOCO_DEVELOPMENT_ONLY"
    assert receipt["marker_geoms"] == 37
    assert receipt["marked_asset_sha256"] == family.asset_sha256
    assert receipt["calibrated_asset_sha256"] == (
        "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
    )
    assert calibration_asset_sha256("mujoco_upright_box_v2") == receipt["calibrated_asset_sha256"]
    assert receipt["formal_qualification"] == "NOT_GRANTED"


@pytest.mark.parametrize(
    "old,new",
    [
        ('mass="0"', 'mass="0.01"'),
        ('contype="0" conaffinity="0" group="2"', 'contype="1" conaffinity="0" group="2"'),
        ('fovy="50"', 'fovy="51"'),
        ('kp="20"', 'kp="21"'),
        ('pos="0.075 0.009 0"', 'pos="0.075 0.01 0"'),
    ],
)
def test_visual_exception_rejects_any_physical_camera_or_control_difference(old, new):
    original = (ROOT / "assets/robots/franka_panda/scene.xml").read_bytes()
    marked = (ROOT / marker_family("outboard_id7_45mm_v3").asset_path).read_bytes()
    assert old.encode() in marked
    changed = marked.replace(old.encode(), new.encode(), 1)
    with pytest.raises(ValueError):
        api().validate_marker_physics_equivalence(changed, original)


def test_identical_bytes_under_an_unregistered_path_do_not_select_asset_policy(tmp_path):
    family = marker_family("outboard_id7_45mm_v3")
    path = tmp_path / "arbitrary.xml"
    path.write_bytes((ROOT / family.asset_path).read_bytes())
    with pytest.raises(ValueError, match="registered"):
        api().validate_development_marker_asset(path, "mujoco_upright_box_v2", family.family_id)


def test_old_profile_cannot_acquire_current_marker_geometry():
    family = marker_family("outboard_id7_45mm_v3")
    with pytest.raises(ValueError, match="profile"):
        api().validate_development_marker_asset(
            ROOT / family.asset_path, "mujoco_upright_box_v1", family.family_id
        )


def test_default_episode_asset_gate_remains_strict():
    family = marker_family("outboard_id7_45mm_v3")
    with pytest.raises(ValueError, match="calibrated"):
        api().validate_episode_asset(ROOT / family.asset_path, "mujoco_upright_box_v2")
    assert (
        api().validate_episode_asset(
            ROOT / "assets/robots/franka_panda/scene.xml", "mujoco_upright_box_v2"
        )["scope"]
        == "EXACT_CALIBRATED_ASSET"
    )
    assert (
        api().validate_episode_asset(
            ROOT / family.asset_path, "mujoco_upright_box_v2", development_family=family.family_id
        )["scope"]
        == "MUJOCO_DEVELOPMENT_ONLY"
    )
