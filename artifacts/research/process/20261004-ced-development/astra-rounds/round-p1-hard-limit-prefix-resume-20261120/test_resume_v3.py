import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import resume_v3 as r


@pytest.fixture
def archive():
    root = r.original.OWNER / "native/development-18"
    if not root.is_dir():
        pytest.skip("local original live archive unavailable")
    return root


def test_real_controller_prefix_rejects_modified_steps_or_late_motion(archive):
    ep = r.original.read(archive / "component/episode.json")
    commands = r.original.read(archive / "component/commands.json")
    assert r.exact_action_prefix(ep, commands)["unreturned_action_step"] == "step-02"
    with pytest.raises(ValueError, match="terminal hold/stop sequence"):
        r.exact_action_prefix(ep, commands + [commands[-4] | {"command_seq": 220}])
    with pytest.raises(ValueError, match="terminal hold/stop sequence"):
        r.exact_action_prefix(ep, commands[:-1])
    ep["actions"][1]["end_step"] = 1217
    with pytest.raises(ValueError, match="controller prefix differs"):
        r.exact_action_prefix(ep, commands)


def test_real_world_positions_enforce_threshold(archive):
    rows = r.original.read(archive / "component/robot-feedback.json")
    bounds = ((0.0, 0.04), (0.0, 0.04))
    assert r.finger_window(rows, bounds, 0.0001)["first_offending_step"] == 1218
    with pytest.raises(ValueError, match="guard does not match"):
        r.finger_window(rows, bounds, 0.001)
    rows[-1]["finger_positions_m"][1] = 0.04
    with pytest.raises(ValueError, match="no exact first"):
        r.finger_window(rows, bounds, 0.0001)


def test_actual_native_job_owns_seed_and_failure(archive):
    job = r.original.read(archive / "worker/job.json")
    original = r.original.read(archive / "result.json")
    episode = r.original.read(archive / "component/episode.json")
    worker = r.original.read(archive / "worker/result.json")
    r.native_finger_fields(original, episode, job, worker, {"runtime_seed": job["seed"]})
    with pytest.raises(ValueError, match="native finger-stop"):
        r.native_finger_fields(original, episode, job, worker, {"runtime_seed": job["seed"] + 1})


def test_real_simulated_limit_cannot_be_reported_as_no_violation(archive):
    ep = r.original.read(archive / "component/episode.json")
    physical = ep["independent_physical_outcome"]
    r.validate_physical(physical, physical)
    with pytest.raises(ValueError, match="physical violation must remain"):
        r.validate_physical(physical | {"safety_violation": False}, physical)


def test_residual_lease_cannot_clear_slot(archive, tmp_path):
    path = tmp_path / "runtime.db"
    shutil.copyfile(archive / "runtime.db", path)

    class LocalCase:
        root = tmp_path

        @staticmethod
        def read(name):
            return (tmp_path / name).read_bytes()

    job = r.original.read(archive / "worker/job.json")
    assert r.original.terminal_attempt(LocalCase(), job)["lease_released"]
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE simulation_job_leases SET released_at = ''")
        db.commit()
    with pytest.raises(ValueError, match="did not terminate and release"):
        r.original.terminal_attempt(LocalCase(), job)


def test_open_begin_cannot_reenter(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(r.original, "OWNER", tmp_path)
    (tmp_path / "receipts").mkdir()
    slot = {"assignment_id": r.FINGER_SLOT, "native_output": "native/development-18"}
    paths = r.original.slot_paths(tmp_path, slot)
    r.original.persist(paths["begin"], {"attempt": 1})
    with pytest.raises(ValueError, match="original 18 claim differs"):
        r.assessment({}, slot)
