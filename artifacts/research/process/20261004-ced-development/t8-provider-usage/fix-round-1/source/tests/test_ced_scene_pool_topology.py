"""The v2 selection pool is separate from every pilot/formal/recovery source group."""

from collections import Counter

import pytest

from cloud_edge_robot_arm.research.protocol import STRATA, build_scene_pools


def test_ced_v2_has_independent_selection_and_complete_fixed_topology():
    pools = build_scene_pools(2026100411, set(), protocol_version="ced.research.v2")
    assert {key: len(rows) for key, rows in pools.items()} == {
        "selection": 120,
        "foundation": 120,
        "power": 120,
        "formal": 2400,
        "recovery": 200,
        "ood": 300,
    }
    groups = [row["scene"]["group_id"] for rows in pools.values() for row in rows]
    assert len(groups) == len(set(groups)) == 3260
    assert Counter(row["stratum_id"] for row in pools["selection"]) == {
        stratum: 10 for stratum in STRATA
    }
    assert pools["selection"][0]["assignment_id"] == "selection-0001"
    excluded = set(groups)
    second = build_scene_pools(2026100411, excluded, protocol_version="ced.research.v2")
    assert not excluded.intersection(
        row["scene"]["group_id"] for rows in second.values() for row in rows
    )


def test_unknown_protocol_version_cannot_silently_build_legacy_pools():
    with pytest.raises(ValueError, match="version"):
        build_scene_pools(11, set(), protocol_version="typo")
