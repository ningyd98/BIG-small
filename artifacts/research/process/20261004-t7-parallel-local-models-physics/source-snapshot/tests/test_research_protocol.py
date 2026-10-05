"""Frozen research boundaries cannot be manufactured from incomplete pilot data."""

import json

import pytest

from cloud_edge_robot_arm.research.protocol import (
    FrozenProtocol,
    ProtocolSpec,
    build_scene_pools,
    freeze_protocol,
    load_protocol,
)
from cloud_edge_robot_arm.datasets.rgbd.models import content_digest


def write_reader_fixture(output):
    # A reader fixture exercises integrity checks; it is never a research freeze.
    spec = ProtocolSpec(tcap_s=130, pool_hashes={"fixture": "a" * 64},
                        model_snapshot_hash="b" * 64, opportunity_hash="c" * 64,
                        recovery_fault_manifest_hash="d" * 64)
    payload = {"spec": spec.model_dump(mode="json"), "stage": "INITIAL"}
    frozen = FrozenProtocol(spec=spec, stage="INITIAL", content_hash=content_digest(payload))
    output.mkdir()
    (output / "protocol.json").write_text(frozen.model_dump_json())
    return frozen


def test_protocol_has_twelve_balanced_cells():
    spec = ProtocolSpec()
    assert len(spec.strata) == 12
    assert spec.formal_ns == (600, 1200, 1800, 2400)
    assert all(n // len(spec.strata) >= 50 for n in spec.formal_ns)
    assert spec.hypothesis_family == (
        "G2_REQUESTS", "G2_SUCCESS", "G2_SAFETY", "G3_FALSE_ACCEPT", "G4_DURATION"
    )


def test_pilot_pools_are_disjoint_from_candidates():
    pools = build_scene_pools(seed=81001, excluded_groups={"existing"})
    expected = {"foundation": 120, "power": 120, "formal": 2400,
                "recovery": 200, "ood": 300}
    seen = {"existing"}
    for name, count in expected.items():
        assert len(pools[name]) == count
        groups = {row["scene"]["group_id"] for row in pools[name]}
        assert len(groups) == count
        assert not seen & groups
        seen.update(groups)
    assert len({row["scene_hash"] for rows in pools.values() for row in rows}) == 3140
    assert all(sum(row["stratum_id"] == s for row in pools["formal"]) == 200
               for s in ProtocolSpec().strata)


def test_initial_protocol_cannot_start_formal_runs(tmp_path):
    frozen = write_reader_fixture(tmp_path / "initial")
    with pytest.raises(ValueError, match="FINAL"):
        frozen.require_formal()
    assert load_protocol(tmp_path / "initial").content_hash == frozen.content_hash


def test_hash_drift_or_overwriting_is_rejected(tmp_path):
    output = tmp_path / "initial"
    write_reader_fixture(output)
    with pytest.raises(ValueError, match="evidence"):
        freeze_protocol(ProtocolSpec(tcap_s=120), output, "INITIAL")
    payload = json.loads((output / "protocol.json").read_text())
    payload["spec"]["tcap_s"] = 120
    (output / "protocol.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash"):
        load_protocol(output)


def test_no_b0_success_blocks_tcap_freeze(tmp_path):
    with pytest.raises(ValueError, match="Tcap"):
        freeze_protocol(ProtocolSpec(), tmp_path / "bad", "INITIAL")


def test_final_protocol_needs_frozen_method_and_allowed_n(tmp_path):
    with pytest.raises(ValueError):
        freeze_protocol(ProtocolSpec(tcap_s=130), tmp_path / "bad", "FINAL")


def test_each_stratum_has_balanced_independent_perturbation_parameters():
    pools = build_scene_pools(seed=81001, excluded_groups=set())
    for stratum in ProtocolSpec().strata:
        rows = [row for row in pools["foundation"] if row["stratum_id"] == stratum]
        for parameter in ("movement_speed_m_s", "noise_m", "invalid_fraction",
                          "occlusion_fraction"):
            values = [row["perturbation"][parameter] for row in rows]
            counts = [values.count(v) for v in set(values)]
            assert len(counts) == 3
            assert max(counts) - min(counts) <= 1


def test_tcap_alone_cannot_manufacture_an_initial_freeze(tmp_path):
    with pytest.raises(ValueError, match="evidence"):
        freeze_protocol(ProtocolSpec(tcap_s=130), tmp_path / "forged", "INITIAL")


def test_yaml_cannot_override_evidence_or_fixed_design():
    from scripts.freeze_rgbd_protocol import apply_settings

    for override in ({"tcap_s": 600}, {"pool_hashes": {}}, {"model_snapshot_hash": None},
                     {"opportunity_hash": None}, {"minimum_baseline_overall_success": .01}):
        with pytest.raises(ValueError, match="override"):
            apply_settings(ProtocolSpec(tcap_s=130), override)
