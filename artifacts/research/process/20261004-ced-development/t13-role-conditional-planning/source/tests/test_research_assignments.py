"""研究分配反例：配对场景、完整池散列和每层分母不可漂移。"""

from collections import Counter, defaultdict
from dataclasses import replace
from importlib import import_module, util

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research.protocol import STRATA, FrozenProtocol, ProtocolSpec


def api():
    name = "cloud_edge_robot_arm.research.assignments"
    assert util.find_spec(name) is not None, "missing production research assignments"
    return import_module(name)


@pytest.fixture(scope="module")
def scene_pool():
    # Explicit SOFTWARE scenes exercise bookkeeping, never physical acceptance.
    rows = []
    for index in range(2400):
        scene = SceneSpec.from_parameters({"software_fixture": index}, "fixture-assets", index)
        rows.append(
            {
                "assignment_id": f"formal-{index + 1:04d}",
                "stratum_id": STRATA[index % 12],
                "scene": scene.model_dump(mode="json"),
                "scene_hash": scene.scene_hash,
                "perturbation": {"noise_m": 0.0},
            }
        )
    return rows


def frozen(pool, n=600, stage="FINAL"):
    spec = ProtocolSpec(
        selected_n=n if stage == "FINAL" else None,
        tcap_s=120,
        pool_hashes={"formal": content_digest(pool)},
        model_snapshot_hash="a" * 64,
        method_hashes={key: content_digest(key) for key in ("JOINT", "B0", "B1", "B2")},
        initial_protocol_hash="b" * 64 if stage == "FINAL" else None,
        opportunity_hash="c" * 64,
        recovery_fault_manifest_hash="d" * 64,
    )
    payload = {"spec": spec.model_dump(mode="json"), "stage": stage}
    return FrozenProtocol(spec=spec, stage=stage, content_hash=content_digest(payload))


def test_paired_assignments_share_scene_seed_schedule(scene_pool):
    module = api()
    rows = module.build_assignments(
        frozen(scene_pool), ("JOINT", "B0", "B1", "B2"), scene_pool=scene_pool
    )
    groups = defaultdict(list)
    for row in rows:
        groups[row.group_id].append(row)
    assert len(groups) == 600
    assert all(len(values) == 4 for values in groups.values())
    for values in groups.values():
        assert (
            len(
                {
                    (
                        r.physics_seed,
                        r.network_schedule_id,
                        r.scene_payload_json,
                        r.perturbation_json,
                        r.network_schedule_json,
                    )
                    for r in values
                }
            )
            == 1
        )
    assert sorted(row.order_index for row in rows) == list(range(2400))
    assert [r.assignment_id for r in rows] == [
        r.assignment_id
        for r in module.build_assignments(
            frozen(scene_pool), ("JOINT", "B0", "B1", "B2"), scene_pool=scene_pool
        )
    ]


@pytest.mark.parametrize("n,per_layer", [(600, 50), (1200, 100), (1800, 150), (2400, 200)])
def test_all_methods_have_balanced_n(scene_pool, n, per_layer):
    rows = api().build_assignments(frozen(scene_pool, n), ("JOINT", "B0"), scene_pool=scene_pool)
    assert len(rows) == n * 2
    assert set(Counter((r.method_id, r.stratum_id) for r in rows).values()) == {per_layer}
    chosen = {row.group_id for row in rows}
    assert scene_pool[0]["scene"]["group_id"] in chosen
    if n < 2400:
        assert scene_pool[n]["scene"]["group_id"] not in chosen


def test_pool_omission_or_drift_cannot_create_assignments(scene_pool):
    module = api()
    with pytest.raises(ValueError, match="pool"):
        module.build_assignments(frozen(scene_pool), ("JOINT",))
    changed = [dict(row) for row in scene_pool]
    changed[0] = {**changed[0], "perturbation": {"noise_m": 0.005}}
    with pytest.raises(ValueError, match="hash"):
        module.build_assignments(frozen(scene_pool), ("JOINT",), scene_pool=changed)


def test_duplicate_or_incomplete_pool_is_rejected_before_subselection(scene_pool):
    module = api()
    duplicate = list(scene_pool)
    duplicate[-1] = duplicate[0]
    for bad in (scene_pool[:600], duplicate):
        with pytest.raises(ValueError, match="2400|duplicate|balance"):
            module.build_assignments(frozen(bad), ("JOINT",), scene_pool=bad)


def test_initial_or_unfrozen_method_cannot_create_formal_assignments(scene_pool):
    module = api()
    with pytest.raises(ValueError, match="FINAL"):
        module.build_assignments(
            frozen(scene_pool, stage="INITIAL"), ("JOINT",), scene_pool=scene_pool
        )
    with pytest.raises(ValueError, match="method"):
        module.build_assignments(frozen(scene_pool), ("UNKNOWN_METHOD",), scene_pool=scene_pool)
    with pytest.raises(ValueError, match="duplicate"):
        module.build_assignments(frozen(scene_pool), ("JOINT", "JOINT"), scene_pool=scene_pool)


def test_assignment_scene_mutation_is_rejected(scene_pool):
    module = api()
    row = module.build_assignments(frozen(scene_pool), ("JOINT",), scene_pool=scene_pool)[0]
    with pytest.raises(ValueError, match="scene|group"):
        replace(row, group_id="wrong-group")
    with pytest.raises(ValueError, match="seed"):
        replace(row, physics_seed=row.physics_seed + 1)


def test_network_schedule_content_cannot_change_under_same_id(scene_pool):
    import json

    row = api().build_assignments(frozen(scene_pool), ("JOINT",), scene_pool=scene_pool)[0]
    schedule = json.loads(row.network_schedule_json)
    schedule["seed"] += 1
    with pytest.raises(ValueError, match="network.*hash"):
        replace(row, network_schedule_json=json.dumps(schedule))


def test_ablation_changes_only_registered_component():
    module = import_module("cloud_edge_robot_arm.research.ablations")
    base = {
        "uncertainty_gate": True,
        "completion_age_gate": True,
        "local_repair": True,
        "safety_shield": True,
        "provider_hash": "x",
    }
    for method, changed in (
        ("NO_UNCERTAINTY", "uncertainty_gate"),
        ("NO_TIME_VALIDITY", "completion_age_gate"),
        ("NO_LOCAL_REPAIR", "local_repair"),
    ):
        result = module.apply_ablation(base, method)
        assert {key for key in base if base[key] != result[key]} == {changed}
        assert result[changed] is False
    assert all(base[key] for key in ("uncertainty_gate", "completion_age_gate", "local_repair"))
    with pytest.raises(ValueError):
        module.apply_ablation(base, "disable_safety")
