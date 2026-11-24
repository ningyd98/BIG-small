from copy import deepcopy
from xml.etree import ElementTree as ET

import mujoco
import numpy as np
import pytest
from scripts.graduation import g1_dual_asset_v2 as parent
from scripts.graduation import g1_visibility_radial as radial
from scripts.graduation.perception_io import ROOT, sha


@pytest.mark.parametrize(("offset", "mass"), [(15, 0.10102432), (30, 0.10126432)])
def test_shifted_scene_has_registered_ink_safe_collision_shells_and_physical_inertia(offset, mass):
    spec = radial.details(offset)
    original = (ROOT / parent.ASSET_PATH).read_bytes()
    xml = radial.build_xml(original, offset)
    artifact = ROOT / spec["asset_path"]
    assert artifact.read_bytes() == xml and sha(artifact) == spec["asset_sha256"]
    assert spec["body_mass_kg"] == pytest.approx(mass, abs=1e-12)
    old_body = ET.fromstring(original).find(".//body[@name='object']")
    new = ET.fromstring(xml)
    new_body = new.find(".//body[@name='object']")
    assert len(new_body.findall("geom")) == 81
    for code, axis in ((7, 1), (8, 0)):
        prefix = f"g1_dual_id{code}_"
        center = spec["centers"][code]
        assert center[axis] == pytest.approx((100 + offset) / 1000)
        for suffix in [
            "plate",
            "quiet",
            "upright",
            *(f"r{r}c{c}" for r in range(6) for c in range(6)),
        ]:
            name = prefix + suffix
            before = old_body.find(f"geom[@name='{name}']")
            after = new_body.find(f"geom[@name='{name}']")
            a, b = [np.fromstring(e.attrib["pos"], sep=" ") for e in (before, after)]
            shift = np.zeros(3)
            shift[axis] = offset / 1000
            np.testing.assert_allclose(b - a, shift, atol=1e-12)
            assert {k: v for k, v in before.attrib.items() if k != "pos"} == {
                k: v for k, v in after.attrib.items() if k != "pos"
            }
        beam = new_body.find(f"geom[@name='{prefix}crossbar']")
        xyz, half = [np.fromstring(beam.get(k), sep=" ") for k in ("pos", "size")]
        assert (xyz[axis] - half[axis], xyz[axis] + half[axis]) == pytest.approx(
            (0.035, 0.056 + offset / 1000)
        )
        assert float(beam.get("mass")) == pytest.approx(500 * 8 * np.prod(half))
    faces = radial.verify_parts(new, offset)
    model = mujoco.MjModel.from_xml_path(str(artifact))
    assert radial.compiled_faces(model, offset) == pytest.approx(faces)
    assert len(faces) == 6 and min(faces.values()) > 0
    assert model.body_mass[model.body("object").id] == pytest.approx(mass, abs=1e-12)
    broken = deepcopy(new)
    broken.find(".//geom[@name='g1_dual_id7_plate']").set("contype", "0")
    with pytest.raises(ValueError):
        radial.verify_parts(broken, offset)
    broken = deepcopy(new)
    broken.find(".//geom[@name='g1_dual_id8_r2c3']").set("rgba", "1 0 0 1")
    with pytest.raises(ValueError):
        radial.verify_parts(broken, offset)


def test_unregistered_offsets_and_foreign_parent_are_refused():
    with pytest.raises(ValueError):
        radial.build_xml(b"<mujoco/>", 15)
    for offset in (0, 16, 15.0, True):
        with pytest.raises(ValueError):
            radial.details(offset)


def test_screen_registration_changes_actual_transforms_for_both_codes_and_preserves_camera():
    import json

    path = (
        ROOT
        / "artifacts/research/process/20261004-ced-development/astra-rounds"
        / "round-g1-formal-paired-20261124/trial-allocation.public.json"
    )
    geometries = json.loads(path.read_bytes())["geometries"]
    old = geometries[parent.FAMILY]
    before = deepcopy(old)
    for offset in (15, 30):
        registration = radial.geometry_for_screen(old, offset)
        spec = radial.details(offset)
        assert old == before
        assert registration["camera"] == old["camera"]
        assert registration["contact_points_m"] == old["contact_points_m"]
        assert registration["object_to_tcp"] == old["object_to_tcp"]
        assert registration["development_dual"]["agreement_m"] == 0.010
        assert registration["pose_marker"]["marked_asset_sha256"] == spec["asset_sha256"]
        assert (
            registration["marker_to_object"]
            == registration["development_dual"]["markers"]["7"]["object_T_marker"]
        )
        for key in ("7", "8"):
            side = registration["development_dual"]["markers"][key]
            previous = old["development_dual"]["markers"][key]
            assert side["dictionary_rows"] == previous["dictionary_rows"]
            np.testing.assert_array_equal(
                np.asarray(side["object_T_marker"]).reshape(4, 4)[:3, 3], spec["centers"][int(key)]
            )
            assert side["marker_registration_hash"] != previous["marker_registration_hash"]
    with pytest.raises(ValueError):
        radial.geometry_for_screen(next(g for k, g in geometries.items() if k != parent.FAMILY), 15)
    model = mujoco.MjModel.from_xml_path(str(ROOT / radial.details(15)["asset_path"]))
    with pytest.raises(ValueError):
        radial.compiled_faces(model, 30)
