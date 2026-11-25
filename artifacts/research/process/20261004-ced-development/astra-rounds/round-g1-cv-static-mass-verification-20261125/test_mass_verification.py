import numpy as np
import pytest

SHAPES = {
    "mass_kg": (),
    "principal_inertia_kg_m2": (3,),
    "body_local_center_of_mass_m": (3,),
    "inertial_quaternion_wxyz": (4,),
}


def zero():
    return {k: np.zeros(shape).tolist() for k, shape in SHAPES.items()}


@pytest.mark.parametrize("field", SHAPES)
def test_native_tolerance_and_next_float(field):
    from capture_v2 import compare_properties

    base = zero()
    assert all(diff == 0.0 for diff in compare_properties(base, zero()).values())
    edge = base | {field: np.full(SHAPES[field], 1e-12).tolist()}
    assert compare_properties(base, edge)[field] == 1e-12
    other = base | {field: np.full(SHAPES[field], np.nextafter(1e-12, np.inf)).tolist()}
    with pytest.raises(ValueError):
        compare_properties(base, other)


@pytest.mark.parametrize("bad", ["extra", "missing", "shape", "nan", "inf", "text", "boolean"])
def test_malformed_values(bad):
    from capture_v2 import compare_properties

    left = zero()
    right = zero()
    if bad == "extra":
        right["color"] = [0.0]
    elif bad == "missing":
        del right["mass_kg"]
    else:
        right["principal_inertia_kg_m2"] = {
            "shape": [[0.0, 0.0, 0.0]],
            "nan": [0.0, np.nan, 0.0],
            "inf": [np.inf, 0.0, 0.0],
            "text": ["0", "0", "0"],
            "boolean": [False, False, False],
        }[bad]
    with pytest.raises(ValueError):
        compare_properties(left, right)


def test_registered_last_bit_difference():
    from capture_v2 import compare_properties

    before = zero() | {"mass_kg": 0.10126432}
    after = zero() | {"mass_kg": 0.10126431999999999}
    assert compare_properties(before, after)["mass_kg"] == abs(before["mass_kg"] - after["mass_kg"])
