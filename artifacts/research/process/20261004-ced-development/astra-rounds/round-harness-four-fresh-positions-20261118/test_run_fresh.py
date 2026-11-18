"""Zero-cost controls for the independent four-slot launcher."""

import fcntl
from argparse import Namespace
from pathlib import Path

import pytest
import run_fresh as runner


def test_paid_flag_is_checked_before_any_output(tmp_path):
    root = tmp_path / "does-not-exist"
    with pytest.raises(ValueError, match="explicit --allow-paid"):
        runner.launch(Namespace(raw_root=root, allow_paid=False))
    assert not root.exists()


def test_lock_contention_prevents_the_second_launcher(tmp_path, monkeypatch):
    def must_not_reach(*_):
        raise AssertionError("second launcher crossed the batch lock")

    monkeypatch.setattr(runner, "_launch_locked", must_not_reach)
    arguments = Namespace(raw_root=tmp_path, allow_paid=True, checkout=tmp_path)
    with (tmp_path / ".batch-launch.lock").open("a+b") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            runner.launch(arguments)
    assert not (tmp_path / "receipts").exists()


def test_launch_releases_lock_on_internal_exception(tmp_path, monkeypatch):
    def fail_without_launch(*_):
        raise ValueError("expected offline test failure")

    monkeypatch.setattr(runner, "_launch_locked", fail_without_launch)
    arguments = Namespace(raw_root=tmp_path, allow_paid=True, checkout=tmp_path)
    with pytest.raises(ValueError, match="expected offline test failure"):
        runner.launch(arguments)
    with (tmp_path / ".batch-launch.lock").open("a+b") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_unknown_prior_consumption_cannot_authorize_the_next_slot():
    assert runner._contained_stops({"audit_status": "LAUNCHED_UNKNOWN"}) is False
    assert runner._contained_stops({"audit_status": "AUDIT_REJECTED"}) is False


def test_history_rejects_an_existing_new_slot_seed(tmp_path):
    root = tmp_path / "results" / "existing"
    root.mkdir(parents=True)
    (root / "scene-assignment.json").write_text('{"seed":2026111801}')
    preregistration = runner.read_allocation(Path(runner.ROUND) / "preallocation.json")
    with pytest.raises(ValueError, match="existing assigned seed or pose"):
        runner.check_history((tmp_path,), preregistration["episodes"])
