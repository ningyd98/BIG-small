from __future__ import annotations

import copy
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest


def module():
    from scripts.graduation import g1_formal_trials

    return g1_formal_trials


def allocation(tmp_path):
    root = tmp_path / "formal-run"
    root.mkdir()
    (root / "claims").mkdir()
    raw = root / "trials"
    raw.mkdir()
    rows = []
    for n, arm in enumerate(("original", "dual"), 1):
        case = "f01-" + arm
        (raw / case).mkdir()
        rows.append(
            dict(id=case, slot=n, visual_id="test-formal/" + case, allocation_sha256=str(n) * 64)
        )
    return root, {"release": "test-formal", "cases": rows}, "b" * 64


def test_out_of_order_never_claims_and_concurrent_claim_is_one_shot(tmp_path):
    t = module()
    root, batch, digest = allocation(tmp_path)
    row, second = batch["cases"]
    with pytest.raises(ValueError, match="earlier"):
        t.claim_slot(root, batch, second, digest)
    assert not list((root / "claims").iterdir())
    barrier = threading.Barrier(2)

    def dispatch():
        barrier.wait(timeout=5)
        try:
            t.claim_slot(root, batch, row, digest)
        except FileExistsError:
            return False
        return True

    with ThreadPoolExecutor(2) as workers:
        claims = list(workers.map(lambda _: dispatch(), range(2)))
    assert sorted(claims) == [False, True]
    ledger = root / "claims/f01-original.json"
    original = ledger.read_bytes()
    claim = json.loads(original)
    assert claim["assignment"] == "test-formal/f01-original"
    assert claim["allocation_sha256"] == "1" * 64
    assert claim["batch_sha256"] == digest
    assert claim["output_root"] == str(root)
    assert claim["attempt"] == 1
    assert (root / "trials/f01-original/claim.json").read_bytes() == original
    with pytest.raises(ValueError, match="earlier"):
        t.claim_slot(root, batch, second, digest)
    with pytest.raises(FileExistsError):
        t.claim_slot(root, batch, row, digest)
    assert ledger.read_bytes() == original


def test_existing_instance_or_cross_slot_claim_is_rejected_before_consumption(tmp_path):
    t = module()
    root, batch, digest = allocation(tmp_path)
    row, second = batch["cases"]
    (root / "trials/f01-original/instance").mkdir()
    with pytest.raises((ValueError, FileExistsError)):
        t.claim_slot(root, batch, row, digest)
    assert not (root / "claims/f01-original.json").exists()
    stray = root / "claims/f01-dual.json"
    stray.write_text("{}")
    with pytest.raises(ValueError):
        t.checked_claim(root, batch, second, digest)


def test_missing_and_interrupted_evidence_keep_allocation_without_reopening(tmp_path):
    t = module()
    root, batch, digest = allocation(tmp_path)
    first, second = batch["cases"]
    before = t.audit_slot(root, batch, first, digest)
    assert not before["acquired"] and before["evidence_status"] == "MISSING"
    t.claim_slot(root, batch, first, digest)
    current = root / "trials/f01-original/instance"
    current.mkdir()
    (current / "interrupted.json").write_text('{"type":"KeyboardInterrupt","error":"stopped"}')
    observed = t.audit_slot(root, batch, first, digest)
    assert not observed["acquired"] and observed["evidence_status"] == "INTERRUPTED"
    assert len(observed["interruption_sha256"]) == 64
    assert len(observed["claim_sha256"]) == 64
    t.claim_slot(root, batch, second, digest)
    with pytest.raises(FileExistsError):
        t.claim_slot(root, batch, first, digest)


def test_crossed_prior_receipt_and_redirected_ledger_cannot_consume_a_slot(tmp_path):
    t = module()
    root, batch, digest = allocation(tmp_path)
    first, second = batch["cases"]
    t.claim_slot(root, batch, first, digest)
    current = root / "trials/f01-original/instance"
    current.mkdir()
    (current / "receipt.json").write_text(
        json.dumps(
            dict(
                case=second["id"],
                batch_sha256=digest,
                allocation_sha256=second["allocation_sha256"],
            )
        )
    )
    with pytest.raises(ValueError, match="earlier"):
        t.claim_slot(root, batch, second, digest)
    assert not (root / "claims/f01-dual.json").exists()
    another = tmp_path / "redirected"
    another.mkdir()
    safe = root / "claims"
    safe.rename(root / "frozen-claims")
    safe.symlink_to(another, target_is_directory=True)
    with pytest.raises(ValueError, match="redirect"):
        t.claim_slot(root, batch, second, digest)
    assert not list(another.iterdir())


def test_registered_physical_scene_and_owner_reach_actual_sqlite_and_reset_reader(tmp_path):
    from scripts.graduation import g1_formal_runtime as builder
    from scripts.graduation import g1_mount_runtime_build as historical

    root = Path(__file__).resolve().parents[1]
    name = "scripts/graduation/dynamic_vision.py"
    previous = historical.configure_vision((root / name).read_bytes())
    effective = builder.adapt_source(name, previous)
    with pytest.raises(ValueError, match="source"):
        builder.adapt_source(name, previous + b" ")
    replay = ModuleType("formal_test_vision")
    exec(compile(effective, name, "exec"), replay.__dict__)
    ids = module().identities("smoke-formal/unit")
    case = dict(visual_id="smoke-formal/unit", visual_seed=42, release="smoke-formal", **ids)
    owner = replay.Owner(
        tmp_path,
        dict(case=case, intent_descriptor={}, baseline="a" * 40, component_catalog_sha256="e" * 64),
        "f" * 64,
    )
    lease = owner.current()
    identity = lease.identity(
        episode_id="unit", robot_id="panda", task_id=ids["task_id"], plan_id=ids["plan_id"]
    )
    assert identity.run_id == "smoke-formal:unit"
    assert (
        identity.task_id == "smoke-formal:unit:task"
        and identity.plan_id == "smoke-formal:unit:plan"
    )
    owner.close(False)
    with sqlite3.connect(tmp_path / "development-worker.db") as db:
        job = db.execute(
            "SELECT run_id, scenario_id, batch_id, manifest_id, control_mode FROM simulation_jobs"
        ).fetchone()
    assert job == (
        "smoke-formal:unit",
        "smoke-formal/unit",
        "smoke-formal",
        "smoke-formal",
        "FORMAL_G1_PAIRED",
    )


def test_bound_dual_observer_rejects_other_slot_and_restores_historical_scope():
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_formal_runtime as builder

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_graduation_g1_dual_observer import software_frame

    root = Path(__file__).resolve().parents[1]
    name = "scripts/graduation/g1_dual_observer.py"
    observer = ModuleType("formal_test_observer")
    exec(
        compile(builder.adapt_source(name, (root / name).read_bytes()), name, "exec"),
        observer.__dict__,
    )
    geometry = asset.geometry_descriptor()
    historical = software_frame([(7, 160, 80)])

    def packet(scene, episode="SOFTWARE_ONLY"):
        return RGBDObservation.model_validate(
            {
                **historical.model_dump(),
                "scene_id": scene,
                "episode_id": episode,
                "checksum_sha256": "",
            }
        )

    current = packet("fixture/registered-dual")
    assert observer.measure_frame(historical, geometry)["usable"]
    assert observer.measure_frame(current, geometry)["reason"] == "registered_scene_mismatch"
    with pytest.raises(KeyboardInterrupt), builder.bind_scene("fixture/registered-dual"):
        assert observer.measure_frame(current, geometry)["usable"]
        assert observer.servo_measure(current)[0] is not None
        for bad in (
            historical,
            packet("fixture/other-dual"),
            packet(None),
            packet("fixture/registered-dual", None),
        ):
            assert observer.measure_frame(bad, geometry)["reason"] == "registered_scene_mismatch"
        raise KeyboardInterrupt
    assert observer.measure_frame(historical, geometry)["usable"]
    assert observer.measure_frame(current, geometry)["reason"] == "registered_scene_mismatch"
    with pytest.raises(ValueError), builder.bind_scene(""):
        pytest.fail("empty assignment entered")


def test_effective_descriptor_only_changes_observer_byte_pin_and_source_digest():
    from scripts.graduation import g1_dual_asset as asset
    from scripts.graduation import g1_formal_runtime as builder

    parent = asset.geometry_descriptor()
    data = copy.deepcopy(parent)
    sources = data["development_dual"]["development_sources_sha256"]
    old_sources = sources.copy()
    key = "scripts/graduation/g1_dual_observer.py"
    sources[key] = "a" * 64
    import hashlib

    data["development_dual"]["development_source_generation"] = hashlib.sha256(
        json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    lock = {"baseline_files_sha256": old_sources, "runtime_files_sha256": sources.copy()}
    assert builder.checked_geometry("dual", parent, data, lock) == data
    for bad in (
        {**data, "scene_id": "forged"},
        {**data, "camera": {}},
        {
            **data,
            "development_dual": {
                **data["development_dual"],
                "development_source_generation": "b" * 64,
            },
        },
    ):
        with pytest.raises(ValueError):
            builder.checked_geometry("dual", parent, bad, lock)
