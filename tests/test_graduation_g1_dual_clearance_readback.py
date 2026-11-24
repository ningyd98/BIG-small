import numpy as np
import pytest
from scripts.graduation import g1_dual_probe_readback as audit


def item(other):
    a = [[0, 0, 1.05], [1, 1, 1.15]]
    b = [[-1, -1, -0.5], [1, 1, 0]]
    r = {
        "name": "plate",
        "other": other,
        "original_mj_geomDistance_m": 0.0,
        "conservative_world_aabb_lower_bound_m": 1.05,
    }
    if other == "table":
        r.update(aabb_a_m=a, aabb_b_m=b)
    return r, np.array(a), np.array(b)


@pytest.mark.parametrize(
    "change",
    [
        "missing_one",
        "table_missing_both",
        "tamper_scalar",
        "tamper_bounds",
        "unexpected_arm_bounds",
        "missing_name",
    ],
)
def test_partial_legacy_clearance_fields_fail_closed(change):
    row, a, b = item("hand" if change == "unexpected_arm_bounds" else "table")
    if change == "missing_one":
        row.pop("aabb_b_m")
    elif change == "table_missing_both":
        row.pop("aabb_a_m")
        row.pop("aabb_b_m")
    elif change == "tamper_scalar":
        row["conservative_world_aabb_lower_bound_m"] += 0.001
    elif change == "tamper_bounds":
        row["aabb_a_m"][0][2] += 0.001
    elif change == "missing_name":
        row.pop("name")
    else:
        row.update(aabb_a_m=a.tolist(), aabb_b_m=b.tolist())
    with pytest.raises(ValueError):
        audit.legacy_bounds(row, a, b)


def test_recorded_and_recomputed_envelopes_have_same_separation():
    for name in ("table", "hand"):
        args = item(name)
        distance, stored = audit.legacy_bounds(*args)
        assert distance == 1.05 and stored == (name == "table")


def test_wrong_xml_digest_refuses_before_model_loading(tmp_path, monkeypatch):
    tree = tmp_path / "reset-clearance-first-generation/runtime-source"
    tree.mkdir(parents=True)
    (tree / "scene.xml").write_bytes(b"archived model")
    lock = {"runtime_files_sha256": {"scene.xml": audit.sha(tree / "scene.xml")}}
    monkeypatch.setattr(audit, "pinned", lambda path, expected: lock)
    with pytest.raises(ValueError, match="incorrect original asset"):
        audit.first_model(tmp_path, "0" * 64, "scene.xml")
