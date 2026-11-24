"""Exercise the registered allocation gate before a device or native trial can be reached."""

import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import pytest
from scripts.graduation import g1_visibility_radial_contact as contact
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation.perception_io import read, sha


def test_replacement_has_one_identity_and_excludes_rejected_batch_from_allocation():
    assert contact.ASSIGNMENTS == {
        "train-radial30-contact-d02-02": ["d02"],
        "train-radial30-contact-d01-01": ["d01"],
    }
    assert contact.REJECTED_LABEL not in contact.ASSIGNMENTS
    assert contact.PARENT == "2d67f55f990226db232ac8c09ee454d2ae40fabc31b43156ff05f5d069dd372d"


def test_frozen_public_issue_was_rejected_before_device_or_attempt():
    private = Path.cwd() / build.PRIVATE
    old = private / "batches" / "train-radial30-contact-d02-01"
    if not (old / "allocation.json").is_file():
        pytest.skip("original private rejection unavailable")
    gate = old / "gate.json"
    _, lock = build.verify_build(private, read(old / "allocation.json")["runtime_build_sha256"])
    with pytest.raises(ValueError, match="offline and negative control release"):
        trials.release_gate(Path.cwd(), gate, sha(gate), lock)
    assert not (old / "d02" / "attempt.json").exists()
    assert not (old / "d02" / "instance").exists()


def _claim_once(path):
    try:
        return trials.reserve_attempt(Path(path), {"pid": os.getpid()})
    except FileExistsError:
        return None


def test_existing_and_racing_processes_cannot_take_a_second_physical_attempt(tmp_path):
    path = tmp_path / "attempt.json"
    with ProcessPoolExecutor(max_workers=4, mp_context=get_context("spawn")) as pool:
        results = list(pool.map(_claim_once, [str(path)] * 8))
    assert len([x for x in results if x]) == 1
    assert _claim_once(path) is None
    other = tmp_path / "interrupted"
    other.write_bytes(b"{")
    assert _claim_once(other) is None
