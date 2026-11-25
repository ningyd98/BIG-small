"""A prospective camera slot must be unique before an owner or device can open."""

import pytest


def test_conflicting_identity_seed_and_old_xy_are_rejected():
    from prospective import ensure_new_placements

    rows = [dict(id="p1", seed=91, reset_fixture_center_m=[0.44, 0.01, 0.035])]
    ensure_new_placements(rows, [{"record": {"seed": 90, "center": [0.46, 0.01, 0.035]}}])
    for older in ({"seed": 91}, {"pose": [0.44, 0.01, 0.035, 0.7]}):
        with pytest.raises(ValueError, match="reused"):
            ensure_new_placements(rows, [older])
    with pytest.raises(ValueError, match="reused"):
        ensure_new_placements(rows + rows, [])
