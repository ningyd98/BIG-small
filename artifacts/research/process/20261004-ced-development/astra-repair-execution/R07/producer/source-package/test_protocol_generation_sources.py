"""CPU-only producer contracts. Fake hook events are never research evidence."""

import importlib
import json
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import DatasetConfig
from cloud_edge_robot_arm.datasets.rgbd.scene_sampler import sample_scene


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.protocol_generation")


def history(tmp_path):
    scene = sample_scene(DatasetConfig(dataset_id="history", groups=1), 7751)
    path = tmp_path / "used.json"
    path.write_text(json.dumps({"scene": scene.model_dump(), "scene_hash": scene.scene_hash}))
    return path, scene


def test_inventory_connects_scene_and_component_aliases(tmp_path):
    path, scene = history(tmp_path)
    alias = tmp_path / "alias.json"
    alias.write_text(
        json.dumps(
            {
                "group_id": "renamed-used",
                "scene_hash": scene.scene_hash,
                "component": "used-component",
            }
        )
    )
    linked = tmp_path / "linked.json"
    linked.write_text(json.dumps({"group_id": "component-copy", "component": "used-component"}))
    result = api().inventory_history([path, alias, linked])
    assert result["complete"]
    assert set(result["group_ids"]) == {scene.group_id, "renamed-used", "component-copy"}
    assert len(result["components"]) == 1
    assert len(result["physical_keys"]) == 1


def test_unknown_history_identity_is_explicit_and_blocks_actual(tmp_path):
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps({"group_id": "unknown-used"}))
    report = api().prepare_generation([path], tmp_path / "protocol")
    assert report["status"] == "BLOCKED_HISTORY"
    assert report["history"]["unresolved_groups"] == ["unknown-used"]
    with pytest.raises(ValueError, match="history"):
        api().preflight_generation(tmp_path / "protocol", "recovery-0001")


def test_prepare_locks_all_3260_new_assignments_and_fixed_fault_schedule(tmp_path):
    path, scene = history(tmp_path)
    output = tmp_path / "protocol"
    report = api().prepare_generation([path], output)
    assert report["status"] == "READY_FOR_REVIEW"
    pools = json.loads((output / "pools.json").read_text())
    assert {name: len(rows) for name, rows in pools.items() if not name.startswith("_")} == {
        "selection": 120,
        "foundation": 120,
        "power": 120,
        "formal": 2400,
        "recovery": 200,
        "ood": 300,
    }
    assert scene.group_id in pools["_evidence"]["excluded_groups"]
    assert (
        sum(
            scene.group_id == r["scene"]["group_id"]
            for rows in pools.values()
            if isinstance(rows, list)
            for r in rows
        )
        == 0
    )
    first = api().preflight_generation(output, "recovery-0001")
    second = api().preflight_generation(output, "recovery-0002")
    assert first["fault"]["parameters"] == {
        "speed_m_s": 0.02,
        "duration_s": 1.0,
        "direction_y": 1.0,
    }
    assert second["fault"]["parameters"]["direction_y"] == -1.0
    assert first["budgets"] == {
        "wall_s": 1800.0,
        "retained_bytes": 2 * 1024**3,
        "min_free_bytes": 10 * 1024**3,
        "rcap_s": 60.0,
    }
    assert first["config"]["camera_width"] == 320
    assert first["config"]["camera_height"] == 240
    assert first["settle_steps"] == 120
    assert first["provider_calls"] == 0
    with pytest.raises(FileExistsError):
        api().prepare_generation([path], output)


def test_history_or_recipe_drift_rejects_before_backend_creation(tmp_path):
    path, _ = history(tmp_path)
    api().prepare_generation([path], tmp_path / "protocol")
    path.write_text("{}")
    with pytest.raises(ValueError, match="history"):
        api().preflight_generation(tmp_path / "protocol", "recovery-0001")


def test_default_cli_does_not_initialize_backend(tmp_path):
    import subprocess

    path, _ = history(tmp_path)
    api().prepare_generation([path], tmp_path / "protocol")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            str(root / ".venv/bin/python"),
            "scripts/generate_rgbd_protocol_evidence.py",
            "--protocol",
            str(tmp_path / "protocol"),
            "--assignment",
            "recovery-0001",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "PREFLIGHT_ONLY"
    assert report["actual_calls"] == 0
    assert not (tmp_path / "protocol" / "attempts").exists()


def test_budget_uses_fault_start_and_preserves_boundary_before_raise(tmp_path):
    clock = [0.0]
    guard = api().GenerationBudget(
        {"wall_s": 1800.0, "retained_bytes": 1024, "min_free_bytes": 0, "rcap_s": 60.0},
        tmp_path,
        clock=lambda: clock[0],
        disk_free=lambda: 999999,
    )
    guard.fault_start_s = 1.0
    guard.check(60.9, 100)
    with pytest.raises(api().BudgetExceeded, match="Rcap"):
        guard.check(61.001, 100)
    clock[0] = 1801.0
    with pytest.raises(api().BudgetExceeded, match="wall"):
        guard.check(1.0, 100)


@pytest.mark.parametrize("mode", ["exception", "no_fault", "budget"])
def test_execute_preserves_allocation_and_partial_sources_without_hidden_retry(
    tmp_path, monkeypatch, mode
):
    path, _ = history(tmp_path)
    protocol = tmp_path / "protocol"
    prepared = api().prepare_generation([path], protocol)
    calls = []

    def collect(plan, output):
        calls.append(plan["fault"]["parameters"])
        (output / "raw-observations.jsonl").write_text('{"physics_step":0}\n')
        if mode == "budget":
            raise api().BudgetExceeded("wall budget exceeded")
        if mode == "exception":
            raise RuntimeError("actual teacher failed")
        return {"physical_calls": 1}

    monkeypatch.setattr(api(), "_run_physical", collect)
    result = api().execute_recovery_once(
        protocol,
        "recovery-0002",
        tmp_path / "attempt",
        expected_protocol_hash=prepared["protocol_hash"],
    )
    assert result["status"] in {"FAILED", "INCOMPLETE"}
    assert result["denominator"] == 200
    assert result["attempted"] == 1
    assert result["unattempted"] == 199
    assert result["g4_measured"] is False
    assert calls == [{"speed_m_s": 0.02, "duration_s": 1.0, "direction_y": -1.0}]
    assert (tmp_path / "attempt" / "raw-observations.jsonl").is_file()
    assert (tmp_path / "attempt" / "result.json").is_file()
    with pytest.raises((ValueError, FileExistsError)):
        api().execute_recovery_once(
            protocol,
            "recovery-0002",
            tmp_path / "another",
            expected_protocol_hash=prepared["protocol_hash"],
        )
    assert len(calls) == 1


def test_wrong_review_pin_cannot_dispatch_and_existing_output_is_preserved(tmp_path, monkeypatch):
    path, _ = history(tmp_path)
    protocol = tmp_path / "protocol"
    api().prepare_generation([path], protocol)

    def forbidden(*args):
        pytest.fail("backend creation is forbidden in this CPU preflight")

    monkeypatch.setattr(api(), "_run_physical", forbidden)
    with pytest.raises(ValueError, match="review"):
        api().execute_recovery_once(
            protocol, "recovery-0001", tmp_path / "attempt", expected_protocol_hash="0" * 64
        )
    assert not (protocol / "allocations").exists()


def test_registered_empty_history_cannot_claim_complete_inventory(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("{}")
    result = api().inventory_history([path])
    assert result["complete"] is False


def test_physical_identity_survives_asset_camera_and_colour_renaming(tmp_path):
    path, scene = history(tmp_path)
    alias = scene.model_dump()
    alias["group_id"] = "visual-rename"
    alias["asset_family_hash"] = "1" * 64
    alias["scene_parameters"]["camera"]["fovy"] = 55.0
    alias["scene_parameters"]["target"]["rgba"] = [0.1, 0.9, 0.1, 1.0]
    other = tmp_path / "visual.json"
    other.write_text(json.dumps({"scene": alias, "scene_hash": "2" * 64}))
    result = api().inventory_history([path, other])
    assert len(result["physical_keys"]) == 1
    assert len(result["components"]) == 1


def test_byte_and_disk_budget_never_authorize_dispatch(tmp_path):
    guard = api().GenerationBudget(
        {"wall_s": 1800.0, "retained_bytes": 100, "min_free_bytes": 10, "rcap_s": 60.0},
        tmp_path,
        clock=lambda: 0.0,
        disk_free=lambda: 1000,
    )
    with pytest.raises(api().BudgetExceeded, match="byte"):
        guard.check(0.0, 101)
    guard.disk_free = lambda: 15
    with pytest.raises(api().BudgetExceeded, match="disk"):
        guard.check(0.0, 6)


def test_no_success_label_can_replace_original_fault_execution(tmp_path, monkeypatch):
    path, _ = history(tmp_path)
    protocol = tmp_path / "protocol"
    prepared = api().prepare_generation([path], protocol)

    def fake_summary(plan, output):
        return {"physical_calls": 100, "success": True, "fault_finished": True}

    monkeypatch.setattr(api(), "_run_physical", fake_summary)
    result = api().execute_recovery_once(
        protocol,
        "recovery-0001",
        tmp_path / "attempt",
        expected_protocol_hash=prepared["protocol_hash"],
    )
    assert result["status"] != "PROVEN"
    assert result["proof"] is None
    assert result["denominator"] == 200


def test_prepare_cli_consumes_explicit_source_catalogue_cpu_only(tmp_path):
    import subprocess

    path, _ = history(tmp_path)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"sources": [str(path)]}))
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            str(root / ".venv/bin/python"),
            "scripts/generate_rgbd_protocol_evidence.py",
            "--prepare",
            "--protocol",
            str(tmp_path / "protocol"),
            "--history-catalog",
            str(catalog),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["actual_calls"] == 0


def test_detached_step_spool_persists_original_prefix_outside_callbacks(tmp_path):
    spool = api().StepSpool(tmp_path / "steps.jsonl")
    try:
        spool.append("PHYSICS", {"physics_step": 0, "episode_id": "original"})
        spool.append("ACTUATOR_PRE", {"physics_step": 1, "sim_time_s": 0.0, "ctrl": [0.1]})
    finally:
        spool.close()
    values = [json.loads(line) for line in (tmp_path / "steps.jsonl").read_text().splitlines()]
    assert [r["record_seq"] for r in values] == [1, 2]
    assert values[1]["payload"] == {"physics_step": 1, "sim_time_s": 0.0, "ctrl": [0.1]}
    assert values[1]["kind"] == "ACTUATOR_PRE"


def test_wall_deadline_installs_stop_and_restores_previous_alarm():
    import signal

    original = signal.getsignal(signal.SIGALRM)
    with api().wall_deadline(1800.0):
        handler = signal.getsignal(signal.SIGALRM)
        with pytest.raises(api().BudgetExceeded, match="wall"):
            handler(signal.SIGALRM, None)
    assert signal.getsignal(signal.SIGALRM) == original
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_actual_path_wires_existing_detached_hooks_without_real_backend(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from dataclasses import fields

    import yaml

    from cloud_edge_robot_arm.research.protocol_evidence import _observation, _recovery
    from cloud_edge_robot_arm.simulation.mujoco.backend import (
        ActuatorStepObservation,
        MuJoCoPhysicsBackend,
    )
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import EpisodeOutcome
    from tests.test_protocol_evidence_generation import inputs, recovery

    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    row = inputs(fixture_dir)["recovery"][0]
    source = recovery(fixture_dir, row)
    raw = [_observation(v) for v in json.loads((source / "physical-observations.json").read_text())]
    actions = json.loads((source / "teacher-actions.json").read_text())
    commands = [v["backend_record"] for v in json.loads((source / "commands.json").read_text())]
    controls = json.loads((source / "actuator-provenance.json").read_text())["steps"]
    actuator_rows = [
        ActuatorStepObservation(**{f.name: v[f.name] for f in fields(ActuatorStepObservation)})
        for v in controls
    ]
    faults = json.loads((source / "fault-events.json").read_text())
    fault = {
        "fault_type": "TARGET_MOTION",
        "parameters": {"speed_m_s": 0.02, "duration_s": 1.0, "direction_y": 1.0},
    }
    rules = yaml.safe_load(api().RULES_PATH.read_text())
    _, proof = _recovery(source, row, fault, rules)
    forbidden_calls = []

    def forbid_initialize(*args):
        forbidden_calls.append("initialize")
        pytest.fail("This integration test is CPU-only")

    monkeypatch.setattr(MuJoCoPhysicsBackend, "initialize", forbid_initialize)

    class Backend:
        total_physics_steps = 0
        physical = None
        actuator = None
        fault_records = []
        teacher_active = False

        @property
        def command_records(self):
            return [
                v
                for v in commands
                if self.teacher_active and v["physics_step"] <= self.total_physics_steps
            ]

        def current_physics_observation(self):
            return raw[self.total_physics_steps]

        def get_sim_time(self):
            return self.current_physics_observation().sim_time_s

        @contextmanager
        def observe_physics_steps(self, callback):
            assert self.physical is None, "No nested observer allowed"
            self.physical = callback
            try:
                yield
            finally:
                self.physical = None

        @contextmanager
        def observe_actuator_steps(self, callback):
            self.actuator = callback
            try:
                yield
            finally:
                self.actuator = None

        def step(self, steps=1):
            for _ in range(steps):
                self.actuator(actuator_rows[self.total_physics_steps])
                self.total_physics_steps += 1
                if self.total_physics_steps == 520:
                    self.fault_records.append(faults[1])
                self.physical(raw[self.total_physics_steps])

        def inject_fault(self, value):
            assert value.parameters == fault["parameters"]
            assert self.total_physics_steps == 20
            self.fault_records = [faults[0]]

    backend = Backend()

    class Capture:
        def __init__(self, config):
            assert (config.camera_width, config.camera_height) == (320, 240)
            self._backend = backend

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def apply_scene(self, scene):
            assert scene.group_id == row["scene"]["group_id"]

    def teacher(scene, robot, recorder, *, settle_steps, physical_observer, action_observer):
        assert settle_steps == 0 and backend.total_physics_steps == 520
        backend.teacher_active = True
        physical_observer(backend.current_physics_observation())
        with backend.observe_physics_steps(physical_observer):
            for event in actions:
                backend.step(event["end_step"] - backend.total_physics_steps)
                action_observer(
                    {
                        k: event[k]
                        for k in (
                            "result",
                            "episode_id",
                            "start_step",
                            "end_step",
                            "command_seq_start",
                            "command_seq_end",
                        )
                    }
                )
        return EpisodeOutcome(**proof["independent_outcome"])

    monkeypatch.setattr("cloud_edge_robot_arm.vision.capture.MuJoCoCaptureSession", Capture)
    monkeypatch.setattr("cloud_edge_robot_arm.datasets.rgbd.teacher.run_teacher_episode", teacher)
    output = tmp_path / "collected"
    output.mkdir()
    plan = {
        "row": row,
        "config": {"camera_width": 320, "camera_height": 240, "physics_dt_s": 0.002},
        "settle_steps": 20,
        "fault": fault,
        "budgets": api().BUDGETS,
    }
    diagnostics = api()._run_physical(plan, output)
    _, reconstructed = _recovery(output / "source", row, fault, rules)
    assert reconstructed["independent_outcome"]["success"]
    assert diagnostics["teacher_actions"] == 9
    assert json.loads((output / "source/attempt.json").read_text())["reset_step"] == 0
    actual_rows = json.loads((output / "source/physical-observations.json").read_text())
    assert len(actual_rows) == len(raw)
    assert (
        json.loads((output / "source/commands.json").read_text())[0]["backend_record"][
            "command_seq"
        ]
        == 1
    )
    assert not forbidden_calls


def test_copied_protocol_directory_cannot_reset_attempt_identity(tmp_path):
    import shutil

    path, _ = history(tmp_path)
    original = tmp_path / "protocol"
    api().prepare_generation([path], original)
    copied = tmp_path / "renamed-protocol"
    shutil.copytree(original, copied)
    with pytest.raises(ValueError, match="directory"):
        api().preflight_generation(copied, "recovery-0001")


def test_renderer_lease_excludes_concurrent_producer_before_any_backend(tmp_path):
    with api().renderer_exclusive(tmp_path / "renderer.lock"):
        with pytest.raises(api().BudgetExceeded, match="renderer"):
            with api().renderer_exclusive(tmp_path / "renderer.lock"):
                pytest.fail("concurrent actual producer must be rejected")
    with api().renderer_exclusive(tmp_path / "renderer.lock"):
        pass
