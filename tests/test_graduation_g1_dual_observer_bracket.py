"""The sole preregistered mechanical alternative has independent geometry and source bindings."""

import hashlib
import importlib
import importlib.util
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from scripts.graduation import g1_dual_asset as v1

ROOT = Path(__file__).resolve().parents[1]


def candidate():
    name = "scripts.graduation.g1_dual_asset_v2"
    assert importlib.util.find_spec(name), "missing registered low bracket configuration"
    return importlib.import_module(name)


def scene():
    return candidate().replace_v1_xml((ROOT / v1.ASSET_PATH).read_bytes())


def test_only_two_physical_bridges_change_into_the_four_preregistered_load_bearing_parts():
    variant = candidate()
    data = scene()
    assert hashlib.sha256(data).hexdigest() == variant.ASSET_SHA != v1.ASSET_SHA
    old, new = [ET.fromstring(content) for content in ((ROOT / v1.ASSET_PATH).read_bytes(), data)]
    body = new.find("./worldbody/body[@name='object']")
    expected_parts = {}
    for code in (7, 8):
        axis = 1 if code == 7 else 0
        for name, low, high, mass in [
            ("crossbar", [0.035, -0.004, 0.017], [0.056, 0.004, 0.019], 0.000168),
            ("upright", [0.052, -0.004, 0.019], [0.056, 0.004, 0.03301], 0.00022416),
        ]:
            if axis == 1:
                low[0], low[1] = low[1], low[0]
                high[0], high[1] = high[1], high[0]
            full = f"g1_dual_id{code}_{name}"
            part = body.find(f"geom[@name='{full}']")
            pos, size = [np.fromstring(part.attrib[k], sep=" ") for k in ("pos", "size")]
            assert pos - size == pytest.approx(low, abs=1e-12)
            assert pos + size == pytest.approx(high, abs=1e-12)
            assert part.attrib["rgba"] == "0.4 0.4 0.4 1"
            assert (part.attrib["contype"], part.attrib["conaffinity"]) == ("1", "3")
            assert float(part.attrib["mass"]) == pytest.approx(mass, abs=1e-14)
            assert mass / (8 * np.prod(size)) == pytest.approx(500.0)
            expected_parts[full] = mass
            body.remove(part)
    old_body = old.find("./worldbody/body[@name='object']")
    for code in (7, 8):
        old_body.remove(old_body.find(f"geom[@name='g1_dual_id{code}_support']"))

    def signatures(tree):
        return [(n.tag, n.attrib) for n in tree.iter()]

    assert signatures(old) == signatures(new)
    assert sum(expected_parts.values()) + 0.08 + 0.02 == pytest.approx(0.10078432)
    with pytest.raises(ValueError):
        variant.replace_v1_xml(data)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("mass", "0.0000168"),
        ("contype", "0"),
        ("conaffinity", "1"),
        ("pos", "0 0.0435 0.018"),
    ],
)
def test_changed_assembly_mass_collision_or_attachment_cannot_pass_structure_audit(field, bad):
    variant = candidate()
    tree = ET.fromstring(scene())
    tree.find(".//geom[@name='g1_dual_id7_crossbar']").set(field, bad)
    with pytest.raises(ValueError):
        variant.verify_parts(tree)


def test_only_the_audited_v1_provider_can_construct_v2_with_its_own_identity():
    variant = candidate()
    original = (ROOT / "scripts/graduation/g1_dual_asset.py").read_bytes()
    compile(variant.provider_source(original), "g1_dual_asset.py", "exec")
    assert variant.FAMILY != v1.FAMILY and variant.ASSET_PATH != v1.ASSET_PATH
    with pytest.raises(ValueError):
        variant.provider_source(original + b"\n")


def test_compiled_candidate_tampering():
    """Run the actual compiled candidate controls after the qualifying static intervention."""
    import mujoco

    variant = candidate()
    model = mujoco.MjModel.from_xml_string(scene().decode())
    assert len(variant.compiled_faces(model)) == 6
    obj = model.body("object").id
    expected_mass = float(model.body_mass[obj])
    model.body_mass[obj] = 0.08
    with pytest.raises(ValueError, match="mass"):
        variant.compiled_faces(model)
    model.body_mass[obj] = expected_mass
    geom = model.geom("g1_dual_id7_crossbar").id
    model.geom_conaffinity[geom] = 0
    with pytest.raises(ValueError, match="collision"):
        variant.compiled_faces(model)
