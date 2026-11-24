from dataclasses import replace

import pytest
from scripts.graduation import dynamic_vision as runner

from cloud_edge_robot_arm.research import native_collection_grounding as g


def test_opt_in_policy_requires_current_catalog_and_registered_asset():
    geometry = runner.geometry_registration(marker_family_id=runner.SIDE_PREPARE_ONLY_FAMILY)
    catalog = runner.inventory()
    p = g.BootstrapCornerPolicy.for_development(catalog, geometry)
    assert p.refinement(catalog, geometry) == "SUBPIX"
    with pytest.raises(ValueError, match="bound"):
        replace(p, mode="OTHER").refinement(catalog, geometry)
    with pytest.raises(ValueError, match="bound"):
        replace(p, schema="other").refinement(catalog, geometry)
    with pytest.raises(ValueError, match="bound"):
        p.refinement({**catalog, "bad": "0" * 64}, geometry)
    with pytest.raises(ValueError, match="bound"):
        replace(p, asset_sha256="0" * 64).refinement(catalog, geometry)


def test_new_emission_scope_preserves_default_and_rejects_foreign_arm():
    from scripts.graduation.proposal_bootstrap_policy import positions

    rows = positions()
    assert [r["arm"] for r in rows] == [
        "EXACT_DEFAULT",
        "EXPLICIT_SUBPIX",
        "EXPLICIT_SUBPIX",
        "EXACT_DEFAULT",
        "EXACT_DEFAULT",
        "EXPLICIT_SUBPIX",
    ]
    assert len({r["id"] for r in rows}) == 6
    assert [r["seed"] for r in rows[::2]] == [24112601, 24112602, 24112603]
    for a, b in zip(rows[::2], rows[1::2], strict=True):
        assert all(a[k] == b[k] for k in ("seed", "reset_fixture_center_m", "yaw_rad", "group"))


def test_default_evidence_and_explicit_v2_region_consumer_use_bound_frame():
    from datetime import UTC, datetime

    from tests.test_registered_object_geometry import frame, revised

    original, reg = frame()
    catalog = runner.inventory()
    payload = reg.to_payload()
    policy = g.BootstrapCornerPolicy.for_development(catalog, payload)
    default = g.collection_bootstrap_evidence(original, payload)
    rows = []
    measured = g.collection_bootstrap_evidence(original, payload, corner_trace=rows.append)
    assert measured == default and rows[0]["corner_refinement"] == "NONE"
    fresh = revised(original, captured_at=datetime.now(UTC))
    rows = []
    g.bootstrap_registered_collection_tracker_v2(
        fresh,
        reg,
        source_root=runner.ROOT,
        source_hashes=catalog,
        nominal_policy=g.registered_nominal_region_policy_v1(catalog),
        corner_policy=policy,
        corner_trace=rows.append,
    )
    assert len(rows) == 1 and rows[0]["frame_sha256"] == fresh.checksum_sha256
    assert rows[0]["corner_refinement"] == "SUBPIX" and rows[0]["marker_ids"] == [7]
    with pytest.raises(ValueError, match="source-bound"):
        g.collection_bootstrap_evidence(
            original, payload, corner_policy="SUBPIX", source_hashes=catalog
        )
