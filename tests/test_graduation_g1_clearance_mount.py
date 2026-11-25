from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATION = "5c09e38b82e09a8c52de407bee97775aca8b8a48b4d14a3bfc387ffd626fa212"
PARENT = (
    ROOT
    / "experiments/results/g1-visibility-pose-repair-20261124/builds"
    / GENERATION
    / "runtime-source"
)
OLD = "assets/robots/franka_panda/scene_g1_development_dual_id7_y130_id8_x130_low_bracket_v3.xml"
SOURCE = "scripts/graduation/g1_dual_asset.py"


def mount():
    if importlib.util.find_spec("scripts.graduation.g1_clearance_mount") is None:
        return None
    from scripts.graduation import g1_clearance_mount

    return g1_clearance_mount


def test_end_wings_leave_both_cube_gripping_faces_unobstructed():
    fixture = mount()
    original = (ROOT / OLD).read_bytes()
    xml = fixture.build_xml(original) if fixture else original
    model = mujoco.MjModel.from_xml_string(xml.decode())
    for code, sign in ((7, -1), (8, 1)):
        prefix = f"g1_dual_id{code}_"
        beam = model.geom(prefix + "crossbar")
        assert sign * beam.pos[0] - beam.size[0] == pytest.approx(0.035), (
            f"ID{code} beam root must meet the non-gripping X end face"
        )
        for name in ("crossbar", "upright", "plate"):
            g = model.geom(prefix + name)
            assert sign * g.pos[0] - g.size[0] >= 0.035 - 1e-12
            assert np.array_equal((g.contype, g.conaffinity), [[1], [3]])
        assert abs(beam.pos[1]) + beam.size[1] < 0.035
    assert fixture.compiled_faces(model) == pytest.approx(fixture.verify_parts(ET.fromstring(xml)))
    assert len(fixture.compiled_faces(model)) == 6
    body = model.body("object")
    assert body.mass[0] == pytest.approx(0.10126432, abs=1e-12)
    assert list(body.ipos[:2]) == pytest.approx([0, 0], abs=1e-12)


def test_physical_print_bits_move_rigidly_without_reflection():
    fixture = mount()
    before = (ROOT / OLD).read_bytes()
    after = fixture.build_xml(before) if fixture else before
    tree0, tree1 = (ET.fromstring(x) for x in (before, after))
    for code, original_center, expected_center in (
        (7, (0, 0.130), (-0.130, 0)),
        (8, (0.130, 0), (0.130, 0)),
    ):
        for row in range(6):
            for col in range(6):
                path = f".//geom[@name='g1_dual_id{code}_r{row}c{col}']"
                old, new = tree0.find(path), tree1.find(path)
                offset = np.fromstring(old.get("pos"), sep=" ")[:2] - original_center
                measured = np.fromstring(new.get("pos"), sep=" ")[:2]
                np.testing.assert_allclose(measured, expected_center + offset, atol=1e-12)
                assert {k: v for k, v in old.attrib.items() if k != "pos"} == {
                    k: v for k, v in new.attrib.items() if k != "pos"
                }
    assert after == (ROOT / fixture.ASSET_PATH).read_bytes()
    with pytest.raises(ValueError, match="parent"):
        fixture.build_xml(before + b" ")


@pytest.mark.skipif(not PARENT.exists(), reason="private frozen runtime unavailable")
def test_exported_geometry_and_native_registry_match_compiled_mount(tmp_path):
    fixture = mount()
    assert fixture is not None, "a generation-specific mount provider is required"
    tree = tmp_path / "runtime-source"
    shutil.copytree(PARENT, tree)
    additions = fixture.overlays(PARENT)
    assert SOURCE in additions and fixture.ASSET_PATH in additions
    for name, data in additions.items():
        dest = tree / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    program = """
import json
from pathlib import Path
from scripts.graduation import g1_dual_asset as a
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.marker_families import marker_family
p = a.geometry_descriptor()
reg = NativeGeometryRegistration(p)
reg.validate_asset(Path.cwd())
assert marker_family(a.FAMILY).asset_path == a.ASSET_PATH
audit = a.audit_asset(Path.cwd())
print(json.dumps(dict(family=a.FAMILY, markers=p["development_dual"]["markers"],
                      digest=p["pose_marker"]["marked_asset_sha256"], audit=audit)))
"""
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=os.pathsep.join([str(tree), str(tree / "src")]),
    )
    output = subprocess.check_output([sys.executable, "-B", "-c", program], env=env, cwd=tree)
    payload = json.loads(output)
    assert payload["family"] == fixture.FAMILY
    for id_, x in (("7", -0.130), ("8", 0.130)):
        marker = payload["markers"][id_]
        T = np.array(marker["object_T_marker"]).reshape(4, 4)
        np.testing.assert_allclose(T[:3, 3], [x, 0, 0.03505], atol=1e-12)
        assert marker["marker_size_m"] == 0.075
    assert payload["audit"]["verified_reset_pair_count"] == 132
    assert payload["digest"] == payload["audit"]["asset_sha256"]
    assert payload["audit"]["physics_steps"] == 0
