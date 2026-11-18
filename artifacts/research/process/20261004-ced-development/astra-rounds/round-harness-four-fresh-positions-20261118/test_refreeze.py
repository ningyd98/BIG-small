"""Offline controls for the single owner and atomic successor selection."""

import fcntl
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_fresh as run
import verify_fresh as audit


@pytest.fixture
def batch(tmp_path, monkeypatch):
    root = tmp_path / "owner"
    root.mkdir()
    for name in ("receipts", "native", "verification"):
        (root / name).mkdir()
    older = root / "freeze-receipt.json"
    older.write_bytes(b'{"old":"original"}')
    old_digest = run.sha256_file(older)
    staged = root / "verification/v5-5103e7f4/freeze-receipt.json"
    staged.parent.mkdir()
    staged.write_bytes(b'{"new":"verified"}')
    identity = run.sha256_file(staged)
    snapshot = tmp_path / "readonly"
    monkeypatch.setattr(run, "REGISTERED_RAW_ROOT", root)
    monkeypatch.setattr(run, "OLD_STAGE_ARCHIVE", snapshot, raising=False)
    monkeypatch.setattr(run, "OLD_FREEZE_SHA256", old_digest, raising=False)
    monkeypatch.setattr(run, "_validate_successor_stage", lambda *_: staged, raising=False)
    inventory = {"freeze-receipt.json": {"bytes": older.stat().st_size, "sha256": old_digest}}
    monkeypatch.setattr(run, "_old_stage_inventory", lambda: inventory, raising=False)
    return root, older, old_digest, staged, identity, snapshot


def test_successor_selection_is_atomic_and_keeps_old_stage(batch):
    root, older, old_digest, staged, identity, snapshot = batch
    run._activate_locked(root, identity)
    assert older.read_bytes() == staged.read_bytes()
    assert run.sha256_file(snapshot / older.name) == old_digest
    assert (snapshot / older.name).stat().st_mode & 0o222 == 0
    with pytest.raises(ValueError, match="old freeze"):
        run._activate_locked(root, identity)
    assert run.sha256_file(older) == identity


@pytest.mark.parametrize(
    "record",
    [
        "receipts/fresh-2026111801-started.json",
        "receipts/unknown-started.json",
        "receipts/fresh-2026111801.stderr",
        "native/fresh-2026111802",
        "native/.unexpected.lock",
    ],
)
def test_opaque_or_known_use_blocks_refreeze_before_selection(batch, record):
    root, older, old_digest, _, identity, snapshot = batch
    (root / record).write_bytes(b"possible occupation")
    with pytest.raises(ValueError, match="occupancy"):
        run._activate_locked(root, identity)
    assert run.sha256_file(older) == old_digest
    assert not snapshot.exists()


def test_interruption_before_atomic_install_preserves_both_versions(batch, monkeypatch):
    root, older, old_digest, staged, identity, snapshot = batch

    def interrupt(*_):
        raise OSError("fixture interruption before selection")

    with monkeypatch.context() as patch:
        patch.setattr(run, "_install_active_freeze", interrupt, raising=False)
        with pytest.raises(OSError, match="fixture interruption"):
            run._activate_locked(root, identity)
    assert run.sha256_file(older) == old_digest
    assert (snapshot / older.name).read_bytes() == older.read_bytes()
    assert run.sha256_file(staged) == identity
    run._activate_locked(root, identity)
    assert run.sha256_file(older) == identity


def test_config_tree_cannot_escape_the_selected_staging(tmp_path):
    slot = "fresh-2026111801"
    assert audit.slot_config_path(tmp_path, {}, slot) == tmp_path / "configs" / (slot + ".json")
    assert audit.slot_config_path(tmp_path, {"staging": "verification/v5-5103e7f4"}, slot) == (
        tmp_path / "verification/v5-5103e7f4/configs" / (slot + ".json")
    )
    with pytest.raises(ValueError, match="staging"):
        audit.slot_config_path(tmp_path, {"staging": "../another-owner"}, slot)


def test_successor_dry_prepare_pin_is_exact_path_and_content(tmp_path, monkeypatch):
    root = tmp_path / "results" / "owner"
    path = root / "verification/v5-5103e7f4/verification/dry-prepare/scene-assignment.json"
    path.parent.mkdir(parents=True)
    data = b'{"seed":2026111801}'
    path.write_bytes(data)
    monkeypatch.setattr(run, "REGISTERED_RAW_ROOT", root)
    allocation = run.read_allocation(Path(run.ROUND) / "preallocation.json")["episodes"]
    summary = run.check_history(
        (tmp_path,),
        allocation,
        successor_dry_sha=hashlib.sha256(data).hexdigest(),
    )
    assert summary["successor_dry_prepare"]["sha256"] == hashlib.sha256(data).hexdigest()
    path.write_bytes(b"{}")
    with pytest.raises(ValueError, match="dry-prepare assignment"):
        run.check_history(
            (tmp_path,), allocation, successor_dry_sha=hashlib.sha256(data).hexdigest()
        )


def test_changed_configuration_or_dry_proof_cannot_become_active(tmp_path, monkeypatch):
    stage = audit.SUCCESSOR_STAGE
    slots = audit.read_allocation(run.ROUND / "preallocation.json")["episodes"]
    proof = {"assignment_sha256": "dry-prepare-original"}
    freeze = {
        "schema": audit.FREEZE_SCHEMA,
        "preallocation_sha256": audit.PREALLOCATION_SHA256,
        "staging": stage,
        "commit": run.SUCCESSOR_COMMIT,
        "wheel_sha256": run.SUCCESSOR_WHEEL_SHA256,
        "dry_prepare": proof,
        "slots": {},
    }
    for slot in slots:
        path = audit.slot_config_path(tmp_path, freeze, slot["id"])
        run.write_new(path, slot)
        freeze["slots"][slot["id"]] = {"config_sha256": run.sha256_file(path)}
    frozen = tmp_path / stage / "freeze-receipt.json"
    run.write_new(frozen, freeze)
    frozen_sha = run.sha256_file(frozen)
    monkeypatch.setattr(run, "verify_frozen_sources", lambda *_: None)
    monkeypatch.setattr(run, "_dry_prepare_proof", lambda _: proof)
    assert run._validate_successor_stage(tmp_path, frozen_sha) == frozen
    with monkeypatch.context() as patch:
        patch.setattr(run, "_dry_prepare_proof", lambda _: {"assignment_sha256": "changed"})
        with pytest.raises(ValueError, match="dry-prepare evidence"):
            run._validate_successor_stage(tmp_path, frozen_sha)
    first = audit.slot_config_path(tmp_path, freeze, slots[0]["id"])
    first.write_bytes(b"replacement")
    with pytest.raises(ValueError, match="frozen configuration changed"):
        run._validate_successor_stage(tmp_path, frozen_sha)


def test_activation_refuses_other_checkout_and_held_owner_lock(batch, monkeypatch, tmp_path):
    root, older, old_digest, _, identity, _ = batch
    verified = tmp_path / "verified-v5"
    verified.mkdir()
    monkeypatch.setattr(run, "REGISTERED_CHECKOUT", verified)
    with pytest.raises(ValueError, match="registered batch locations"):
        run.activate(SimpleNamespace(checkout=tmp_path, raw_root=root, freeze_sha256=identity))
    with (root / ".batch-launch.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run.activate(SimpleNamespace(checkout=verified, raw_root=root, freeze_sha256=identity))
    assert run.sha256_file(older) == old_digest
