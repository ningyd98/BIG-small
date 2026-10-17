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


@pytest.fixture(scope="module")
def independently_scored_first_actual_recovery():
    """Read immutable actual records; never execute or relabel the first group."""
    import yaml

    from cloud_edge_robot_arm.research.protocol_evidence import _recovery
    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import PhysicalSample

    root = Path(__file__).resolve().parents[1]
    raw = root / (
        "artifacts/research/process/20261004-ced-development/"
        "astra-repair-execution/R07/producer/raw/recovery-0001/attempt-1"
    )
    if not raw.is_dir():
        pytest.skip("requires the immutable R07 first actual source for CPU-only regression")
    plan = json.loads((raw / "execution-plan.json").read_text())
    samples, proof = _recovery(
        raw / "source", plan["row"], plan["fault"], yaml.safe_load(api().RULES_PATH.read_text())
    )
    assert samples[0]["physics_step"] == 0 and samples[0]["sim_time_s"] == 0
    assert proof["independent_outcome"]["status"] == "SUCCESS"
    return (
        [PhysicalSample(**sample) for sample in samples],
        proof,
        json.loads((raw / "source/attempt.json").read_text())["recovery_start_step"],
    )


def producer_deadline_check(proof):
    """Execute the actual duration guard alone, with no collector/source mock.

    Isolating this original statement prevents physical execution and allocation
    while checking the real producer criterion rather than a copied formula.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(api().execute_recovery_once))
    guards = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and len(node.body) == 1
        and isinstance(node.body[0], ast.Raise)
        and any(
            isinstance(child, ast.Constant) and child.value == "fault-start Rcap result exceeded"
            for child in ast.walk(node)
        )
    ]
    assert len(guards) == 1
    code = ast.fix_missing_locations(ast.Module(body=guards, type_ignores=[]))
    exec(
        compile(code, "producer-duration-guard", "exec"),
        {"proof": proof, "BudgetExceeded": api().BudgetExceeded},
    )


@pytest.mark.parametrize("past_deadline", [False, True], ids=["under60", "over60"])
def test_actual_reset_elapsed_uses_fault_start_deadline_only(
    independently_scored_first_actual_recovery, past_deadline
):
    """SOFTWARE_ONLY: extend scored samples, never forge raw/source/PROVEN.

    The independent evaluator scores the complete reset0 sample sequence and
    returns elapsed from reset0 even when its lift baseline begins at recovery.
    A stable software tail tests both sides of the original 60s contract.
    """
    import math
    from dataclasses import asdict, replace

    from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
        CompletionCriteria,
        evaluate_evidence,
    )

    samples, original, recovery_start_step = independently_scored_first_actual_recovery
    dt = samples[-1].sim_time_s / samples[-1].physics_step
    last_under_step = math.floor((original["injection_start_s"] + 60.0) / dt)
    end_step = last_under_step + (1 if past_deadline else 0)
    tail = [
        replace(samples[-1], physics_step=step, sim_time_s=step * dt)
        for step in range(samples[-1].physics_step + 1, end_step + 1)
    ]
    outcome = evaluate_evidence(
        samples + tail,
        CompletionCriteria("object", "target_region"),
        evaluation_start_step=recovery_start_step,
    )
    assert outcome.success and outcome.safety_assessment == "SCOPED_NO_VIOLATION"
    assert outcome.elapsed_s == tail[-1].sim_time_s
    elapsed_from_fault = tail[-1].sim_time_s - original["injection_start_s"]
    assert (elapsed_from_fault > 60) is past_deadline
    scored = {**original, "independent_outcome": asdict(outcome)}
    if past_deadline:
        with pytest.raises(api().BudgetExceeded, match="fault-start Rcap"):
            producer_deadline_check(scored)
    else:
        producer_deadline_check(scored)


def cpu_predecessor(tmp_path):
    """One honest CPU allocation failure; no fabricated physical success."""
    path, _ = history(tmp_path)
    predecessor = tmp_path / "initial"
    prepared = api().prepare_generation([path], predecessor)
    output = tmp_path / "failed-cpu-allocation"
    output.mkdir()
    (output / "result.json").write_text(
        json.dumps({"status": "FAILED", "reason": "CPU_ONLY_NO_PHYSICAL_CALL"})
    )
    allocations = predecessor / "allocations"
    allocations.mkdir()
    (allocations / "recovery-0001-attempt-1.json").write_text(
        json.dumps(
            {
                "assignment_id": "recovery-0001",
                "attempt": 1,
                "state": "ALLOCATED",
                "protocol_hash": prepared["protocol_hash"],
                "output": str(output.resolve()),
            }
        )
    )
    return predecessor, prepared["protocol_hash"]


def successor(tmp_path):
    predecessor, reviewed_hash = cpu_predecessor(tmp_path)
    output = tmp_path / "successor"
    report = api().prepare_successor_generation(
        predecessor, output, expected_predecessor_hash=reviewed_hash
    )
    return predecessor, output, report


def test_successor_preserves_all_rows_payloads_and_consumed_namespace(tmp_path):
    predecessor, output, report = successor(tmp_path)
    original = json.loads((predecessor / "generation.json").read_text())
    overlay = json.loads((output / "generation.json").read_text())
    assert overlay["schema_version"] == "ced.recovery-generation.v2"
    assert overlay["payload_hashes"] == original["payload_hashes"]
    assert overlay["seed"] == original["seed"]
    assert not (output / "pools.json").exists(), "references original; never copies/relabels rows"
    plan = api().preflight_generation(output, "recovery-0002")
    assert plan["allocation_directory"] == str((predecessor / "allocations").resolve())
    assert plan["input_directory"] == str(predecessor.resolve())
    assert plan["denominator"] == 200 and plan["attempted"] == 1 and plan["unattempted"] == 199
    assert plan["fault"]["parameters"]["direction_y"] == -1.0
    assert plan["actual_calls"] == 0 and report["actual_calls"] == 0
    assert not (output / "allocations").exists()
    with pytest.raises(ValueError, match="consumed"):
        api().preflight_generation(output, "recovery-0001", 1)
    with pytest.raises(ValueError, match="previous|ordinal"):
        api().preflight_generation(output, "recovery-0002", 2)


def test_successor_copy_cannot_reset_shared_allocation_namespace(tmp_path):
    import shutil

    _, output, _ = successor(tmp_path)
    cloned = tmp_path / "copied-successor"
    shutil.copytree(output, cloned)
    with pytest.raises(ValueError, match="directory"):
        api().preflight_generation(cloned, "recovery-0002")


@pytest.mark.parametrize(
    "drift", ["missing_predecessor", "payload", "source_archive", "actual_pin"]
)
def test_successor_rejects_missing_or_drifted_originals_before_backend(tmp_path, drift):
    predecessor, output, _ = successor(tmp_path)
    overlay = json.loads((output / "generation.json").read_text())
    if drift == "missing_predecessor":
        (predecessor / "generation.json").unlink()
    elif drift == "payload":
        (predecessor / "pools.json").write_text("{}")
    elif drift == "source_archive":
        archived = output / "source-archive" / next(iter(overlay["source_archive_hashes"]))
        archived.write_text("altered")
    else:
        (tmp_path / "failed-cpu-allocation/result.json").write_text("{}")
    with pytest.raises((ValueError, FileNotFoundError)):
        api().preflight_generation(output, "recovery-0002")


def test_successor_requires_reviewed_predecessor_hash_before_freeze(tmp_path):
    predecessor, _ = cpu_predecessor(tmp_path)
    output = tmp_path / "wrong-review"
    with pytest.raises(ValueError, match="predecessor"):
        api().prepare_successor_generation(predecessor, output, expected_predecessor_hash="0" * 64)
    assert not output.exists()


def test_successor_accounts_new_cpu_failure_in_shared_200_denominator(tmp_path, monkeypatch):
    predecessor, output, report = successor(tmp_path)

    def fail_before_physics(plan, destination):
        raise RuntimeError("CPU_ONLY_NO_PHYSICAL_CALL")

    monkeypatch.setattr(api(), "_run_physical", fail_before_physics)
    result = api().execute_recovery_once(
        output,
        "recovery-0002",
        tmp_path / "new-failed-allocation",
        expected_protocol_hash=report["protocol_hash"],
    )
    assert result["status"] == "FAILED"
    assert (
        result["denominator"] == 200 and result["attempted"] == 2 and result["unattempted"] == 198
    )
    assert (predecessor / "allocations/recovery-0002-attempt-1.json").is_file()
    assert not (output / "allocations").exists()
    with pytest.raises(ValueError, match="consumed"):
        api().preflight_generation(output, "recovery-0002", 1)


def test_successor_pins_immutable_first_actual_without_relabeling(tmp_path):
    root = Path(__file__).resolve().parents[1]
    predecessor = root / (
        "artifacts/research/process/20261004-ced-development/"
        "astra-repair-execution/R07/producer/protocol-final"
    )
    if not predecessor.is_dir():
        pytest.skip("requires immutable first R07 actual predecessor")
    api().prepare_successor_generation(
        predecessor,
        tmp_path / "actual-successor",
        expected_predecessor_hash="66570b912ba08e0924e4cbe31098be9df7f1f02ed43548b131f65b2695ded724",
    )
    plan = api().preflight_generation(tmp_path / "actual-successor", "recovery-0002")
    assert plan["attempted"] == 1 and plan["unattempted"] == 199
    assert any(
        path.endswith("attempt-1/result.json") for path in plan["predecessor_evidence_hashes"]
    )
    with pytest.raises(ValueError, match="consumed|PROVEN"):
        api().preflight_generation(tmp_path / "actual-successor", "recovery-0001", 1)
    with pytest.raises(ValueError, match="PROVEN"):
        api().preflight_generation(tmp_path / "actual-successor", "recovery-0001", 2)
    with pytest.raises(ValueError, match="source"):
        api().preflight_generation(predecessor, "recovery-0002")


def test_successor_cli_freezes_overlay_and_default_preflight_is_cpu_only(tmp_path):
    import subprocess

    predecessor, reviewed_hash = cpu_predecessor(tmp_path)
    output = tmp_path / "cli-successor"
    root = Path(__file__).resolve().parents[1]
    common = [str(root / ".venv/bin/python"), "scripts/generate_rgbd_protocol_evidence.py"]
    prepared = subprocess.run(
        common
        + [
            "--prepare",
            "--protocol",
            str(output),
            "--successor-of",
            str(predecessor),
            "--expected-predecessor-hash",
            reviewed_hash,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepared.returncode == 0, prepared.stderr + prepared.stdout
    assert json.loads(prepared.stdout)["attempted"] == 1
    preflight = subprocess.run(
        common + ["--protocol", str(output), "--assignment", "recovery-0002"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert preflight.returncode == 0, preflight.stderr + preflight.stdout
    plan = json.loads(preflight.stdout)
    assert plan["status"] == "PREFLIGHT_ONLY" and plan["actual_calls"] == 0
    assert plan["attempted"] == 1 and plan["unattempted"] == 199
    assert plan["fault"]["parameters"]["direction_y"] == -1.0
    assert not (output / "allocations").exists()
    assert len(list((predecessor / "allocations").glob("*.json"))) == 1


@pytest.fixture
def recovery_wall_cpu_only(monkeypatch):
    """Fail if these CPU cases reach a native effect or a real clock probe."""
    import socket

    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    native_attempts = []

    def forbidden(*args, **kwargs):
        native_attempts.append((args, kwargs))
        raise AssertionError("RW1 must not initialize/inject/step/render/capture/network")

    for cls, names in (
        (MuJoCoPhysicsBackend, ("__init__", "initialize", "inject_fault", "step")),
        (MuJoCoRGBDCamera, ("__init__", "_capture")),
        (MuJoCoCaptureSession, ("__enter__",)),
    ):
        for name in names:
            monkeypatch.setattr(cls, name, forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    def no_real_clock(_clock_id):
        raise AssertionError("RW1 must reuse saved platform capability evidence")

    monkeypatch.setattr(api().time, "clock_gettime_ns", no_real_clock)
    yield
    assert native_attempts == []


class RecoveryWallCPUBackend:
    """Owned synchronous-source fixture; it never constructs a native backend."""

    def __init__(self):
        self._episode_id = "cpu-episode-1"
        self.total_physics_steps = 3
        self.sim_time_s = 1.0
        self.events = []

    def get_sim_time(self):
        return self.sim_time_s

    @property
    def fault_records(self):
        return [dict(event) for event in self.events]

    def event(self):
        return {
            "event": "TARGET_MOTION_STARTED",
            "physics_step": self.total_physics_steps,
            "sim_time_s": self.sim_time_s,
            "speed_m_s": 0.02,
            "direction_y": 1.0,
            "duration_s": 1.0,
            "mechanism": "CPU fixture only; not actual fault evidence",
        }


def recovery_wall_fixture(tmp_path, *, counters=None, prefix=None):
    """Raw counters are injected; owner validation and verdict stay real."""
    from itertools import chain, repeat

    module = api()
    output = tmp_path / "attempt"
    output.mkdir()
    allocations = tmp_path / "canonical" / "allocations"
    allocations.mkdir(parents=True)
    plan = {
        "row": {"assignment_id": "recovery-0002"},
        "attempt": 1,
        "protocol_hash": "a" * 64,
        "allocation_directory": str(allocations.resolve()),
        "budgets": {"rcap_s": 60.0},
    }
    allocation = {
        "assignment_id": "recovery-0002",
        "attempt": 1,
        "state": "ALLOCATED",
        "protocol_hash": "a" * 64,
        "output": str(output.resolve()),
    }
    (allocations / "recovery-0002-attempt-1.json").write_text(json.dumps(allocation))
    identity = {
        "pid": 12345,
        "process_start_ticks": "987654",
        "boot_id": "cpu-boot-1",
        "time_namespace": "time:[cpu-1]",
        "time_namespace_offsets": "monotonic 0 0\nboottime 0 0\n",
        "app_nonce": "cpu-startup-1",
    }
    values = chain(counters or [0, 100, 110, 120, 121], repeat(200))

    def read():
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    backend = RecoveryWallCPUBackend()
    backend.events = json.loads(json.dumps(prefix if prefix is not None else [], allow_nan=False))
    owner = module._open_recovery_wall_owner_for_test(
        plan,
        output,
        backend=backend,
        raw_read=read,
        identity_read=lambda: dict(identity),
    )
    return owner, backend, identity, plan, output


def recovery_wall_begin(owner, backend):
    owner.begin_fault(
        backend=backend,
        episode_id=backend._episode_id,
        step=backend.total_physics_steps,
        sim_time_s=backend.get_sim_time(),
    )


def recovery_wall_end(owner, backend):
    owner.end_fault_injection(step=backend.total_physics_steps, sim_time_s=backend.get_sim_time())


def recovery_wall_finish(owner, backend, failure=None):
    return owner.finish(
        step=backend.total_physics_steps,
        sim_time_s=backend.get_sim_time(),
        failure=failure,
    )


@pytest.mark.parametrize(
    "case",
    [
        "below",
        "equal",
        "above",
        "stopped_s",
        "jump",
        "utc_jump",
        "advance_s",
        "repeat_begin",
        "missing_pair",
        "negative",
        "bool",
        "rollback",
        "pair_reverse",
        "cross_domain",
        "missing_end",
        "writer_error",
    ],
)
def test_recovery_wall_integer_deadline_boundaries(
    tmp_path, monkeypatch, recovery_wall_cpu_only, case
):
    # A shifted/refreshed deadline, float/clamped counter or S-derived age fails here.
    counters = {
        "below": [0, 100, 110, 60_000_000_098, 60_000_000_099],
        "equal": [0, 100, 110, 60_000_000_099, 60_000_000_100],
        "above": [0, 100, 110, 60_000_000_100, 60_000_000_101],
        "stopped_s": [0, 100, 110, 60_000_000_099, 60_000_000_100],
        "jump": [0, 100, 110, 90_000_000_100, 90_000_000_101],
        "missing_pair": [0, 100, 110, 120, None],
        "negative": [0, 100, 110, -1, 121],
        "bool": [0, 100, 110, True, 121],
        "rollback": [0, 100, 110, 109, 121],
        "pair_reverse": [0, 100, 110, 120, 119],
    }.get(case)
    owner, backend, identity, _plan, output = recovery_wall_fixture(tmp_path, counters=counters)
    recovery_wall_begin(owner, backend)
    original_begin = (output / "wall-start.json").read_bytes()
    assert json.loads(original_begin)["fault_begin"]["lower_ns"] == 100
    if case == "repeat_begin":
        with pytest.raises((ValueError, RuntimeError), match="already|repeat"):
            recovery_wall_begin(owner, backend)
    elif case != "missing_end":
        backend.events.append(backend.event())
        recovery_wall_end(owner, backend)
    if case == "utc_jump":
        monkeypatch.setattr(api().time, "time", lambda: -9_000_000_000.0)
    if case == "advance_s":
        backend.total_physics_steps = 4
        backend.sim_time_s = 1.005
    if case == "cross_domain":
        identity["boot_id"] = "foreign-domain"
    invalid = {"missing_pair", "negative", "bool", "rollback", "pair_reverse"}
    if case in invalid | {"cross_domain"}:
        with pytest.raises((ValueError, RuntimeError), match="counter|identity|lifecycle"):
            owner.check("CURRENT", step=3, sim_time_s=1.0)
    if case == "writer_error":
        owner._journal.error = OSError("scripted writer failure")
        with pytest.raises(RuntimeError, match="journal|spool"):
            owner.check("CURRENT", step=3, sim_time_s=1.0)
    result = recovery_wall_finish(owner, backend)
    assert result["deadline_ns"] == 60_000_000_100
    assert (output / "wall-start.json").read_bytes() == original_begin
    should_pass = case in {"below", "utc_jump", "advance_s"}
    assert result["wall_pass"] is should_pass
    assert result["scope"] == "r07.recovery-wall.development.v1"
    assert result["clock_semantics"] == "LINUX_BOOTTIME_INCLUDES_SUSPEND"
    if case in {"equal", "above", "stopped_s", "jump"}:
        assert "deadline" in result["failure"]
        assert backend.get_sim_time() == 1.0
    if not should_pass:
        assert result["status"] in {"FAILED", "INCOMPLETE"}
    assert (output / "wall-terminal.json").is_file()
    assert (output / "raw-wall-checks.jsonl").is_file()


@pytest.mark.parametrize(
    "case",
    [
        "foreign_lease",
        "object_flags",
        "copied_lease",
        "copied_owner",
        "deepcopied_owner",
        "pickled_owner",
        "forged_owner",
        "pid",
        "process_start_ticks",
        "boot_id",
        "time_namespace",
        "time_namespace_offsets",
        "app_nonce",
        "allocation_drift",
        "attempt_drift",
        "protocol_drift",
        "backend_foreign",
        "backend_episode",
        "released_owner",
        "unsupported_boottime",
        "raw_read_failure",
        "production_rejects_cpu_lease",
    ],
)
def test_recovery_wall_owner_lifecycle_fail_closed(
    tmp_path, monkeypatch, recovery_wall_cpu_only, case
):
    # Accepting copied/offline/caller flags or a changed process/allocation fails here.
    import copy
    import pickle
    from types import SimpleNamespace

    module = api()
    if case == "unsupported_boottime":
        monkeypatch.delattr(module.time, "CLOCK_BOOTTIME", raising=False)
        monkeypatch.setattr(module.time, "monotonic", lambda: pytest.fail("no fallback"))
        with pytest.raises((ValueError, RuntimeError), match="BOOTTIME|unsupported"):
            module._recovery_wall_boottime_reader()
        return
    if case == "raw_read_failure":
        monkeypatch.setattr(module.time, "monotonic", lambda: pytest.fail("no fallback"))
        reader = module._recovery_wall_boottime_reader()
        with pytest.raises((ValueError, RuntimeError), match="BOOTTIME|counter"):
            reader()
        return
    owner, backend, identity, plan, output = recovery_wall_fixture(tmp_path)
    recovery_wall_begin(owner, backend)
    begin = (output / "wall-start.json").read_bytes()
    backend.events.append(backend.event())
    recovery_wall_end(owner, backend)
    if case in {"foreign_lease", "object_flags", "production_rejects_cpu_lease"}:
        lease = {
            "foreign_lease": "pid:12345:boot:cpu-boot-1",
            "object_flags": SimpleNamespace(live=True, pid=12345, authorized=True),
            "production_rejects_cpu_lease": owner._lease,
        }[case]
        with pytest.raises((ValueError, RuntimeError), match="lease|renderer"):
            module._open_recovery_wall_owner(plan, output, renderer_lease=lease)
    elif case in {"copied_lease", "copied_owner", "deepcopied_owner", "pickled_owner"}:
        target = owner._lease if case == "copied_lease" else owner
        action = {
            "copied_lease": copy.copy,
            "copied_owner": copy.copy,
            "deepcopied_owner": copy.deepcopy,
            "pickled_owner": pickle.dumps,
        }[case]
        with pytest.raises((ValueError, TypeError, RuntimeError), match="copy|pickle|live"):
            action(target)
    elif case == "forged_owner":
        forged = object.__new__(type(owner))
        forged.__dict__.update(owner.__dict__)
        with pytest.raises((ValueError, RuntimeError), match="owner|live"):
            forged.check("CURRENT", step=3, sim_time_s=1.0)
    elif case == "backend_foreign":
        with pytest.raises((ValueError, RuntimeError), match="backend|already|repeat"):
            owner.begin_fault(
                backend=RecoveryWallCPUBackend(),
                episode_id="cpu-episode-1",
                step=3,
                sim_time_s=1.0,
            )
    else:
        if case in identity:
            identity[case] = "changed" if case != "pid" else 12346
        elif case == "allocation_drift":
            allocation = Path(plan["allocation_directory"]) / "recovery-0002-attempt-1.json"
            allocation.write_text(allocation.read_text() + " ")
        elif case == "attempt_drift":
            plan["attempt"] = 2
        elif case == "protocol_drift":
            plan["protocol_hash"] = "b" * 64
        elif case == "backend_episode":
            backend._episode_id = "cpu-episode-restarted"
        elif case == "released_owner":
            recovery_wall_finish(owner, backend)
        with pytest.raises(
            (ValueError, RuntimeError), match="identity|lifecycle|allocation|episode|owner|plan"
        ):
            owner.check("CURRENT", step=3, sim_time_s=1.0)
    assert (output / "wall-start.json").read_bytes() == begin
    if case != "released_owner":
        recovery_wall_finish(owner, backend, failure="CPU lifecycle refusal retained")


@pytest.mark.parametrize(
    "case",
    [
        "healthy",
        "later_advance",
        "foreign_backend",
        "caller_episode",
        "caller_step",
        "caller_s",
        "missing_episode",
        "episode_drift",
        "episode_reset",
        "no_event",
        "stale_event",
        "replayed_payload",
        "duplicate",
        "extra_event",
        "wrong_event_kind",
        "prefix_changed",
        "prefix_truncated",
        "reset_records",
        "event_missing_step",
        "event_missing_s",
        "event_wrong_step",
        "event_wrong_s",
        "event_bool_step",
        "event_negative_step",
        "event_string_step",
        "event_bool_s",
        "event_nan_s",
        "event_inf_s",
        "event_negative_s",
        "event_string_s",
        "begin_bool_step",
        "begin_negative_step",
        "begin_bool_s",
        "begin_nan_s",
        "end_step_advanced",
        "end_s_advanced",
        "end_bad_step",
        "end_bad_s",
        "source_not_list",
        "source_not_dict",
        "caller_crafted_event",
        "repeat_begin",
        "repeat_end",
        "failure_after_begin",
    ],
)
def test_recovery_wall_event_episode_provenance(tmp_path, recovery_wall_cpu_only, case):
    # Trusting caller copies or forgetting owned prefix/ordinal/live state fails here.
    prefix = [{"event": "CPU_PREFIX", "physics_step": 2, "sim_time_s": 0.5}]
    if case in {"stale_event", "replayed_payload"}:
        prefix = [RecoveryWallCPUBackend().event()]
    prefix_snapshot = json.dumps(prefix, allow_nan=False).encode()
    owner, backend, _identity, _plan, output = recovery_wall_fixture(tmp_path, prefix=prefix)
    begin_refusals = {
        "foreign_backend": "backend",
        "caller_episode": "episode",
        "caller_step": "step",
        "caller_s": "sim|state",
        "missing_episode": "episode",
        "begin_bool_step": "step",
        "begin_negative_step": "step",
        "begin_bool_s": "sim|state",
        "begin_nan_s": "sim|state",
    }
    if case in begin_refusals:
        kwargs = {
            "backend": backend,
            "episode_id": backend._episode_id,
            "step": 3,
            "sim_time_s": 1.0,
        }
        if case == "foreign_backend":
            kwargs["backend"] = RecoveryWallCPUBackend()
        if case == "caller_episode":
            kwargs["episode_id"] = "caller-only-episode"
        if case == "caller_step":
            kwargs["step"] = 4
        if case == "caller_s":
            kwargs["sim_time_s"] = 1.005
        if case == "missing_episode":
            backend._episode_id = None
        if case == "begin_bool_step":
            backend.total_physics_steps = True
        if case == "begin_negative_step":
            backend.total_physics_steps = -1
        if case == "begin_bool_s":
            backend.sim_time_s = True
        if case == "begin_nan_s":
            backend.sim_time_s = float("nan")
        with pytest.raises((ValueError, RuntimeError), match=begin_refusals[case]):
            owner.begin_fault(**kwargs)
        assert not (output / "wall-start.json").exists()
        assert not recovery_wall_finish(owner, backend, failure="BEGIN refused")["wall_pass"]
        return
    recovery_wall_begin(owner, backend)
    begin = (output / "wall-start.json").read_bytes()
    if case == "failure_after_begin":
        result = recovery_wall_finish(owner, backend, failure="scripted injection failure")
        assert not result["wall_pass"] and result["fault_end"] is None
        assert (output / "wall-start.json").read_bytes() == begin
        return
    event = backend.event()
    if case not in {"no_event", "stale_event", "caller_crafted_event"}:
        backend.events.append(event)
    if case == "caller_crafted_event":
        with pytest.raises(TypeError):
            owner.end_fault_injection(step=3, sim_time_s=1.0, event=event, success=True)
    elif case == "episode_drift":
        backend._episode_id = "different-episode"
    elif case == "episode_reset":
        backend._episode_id = None
    elif case == "duplicate":
        backend.events.append(dict(event))
    elif case == "extra_event":
        backend.events.append({"event": "CPU_EXTRA"})
    elif case == "wrong_event_kind":
        event["event"] = "TARGET_MOTION_FINISHED"
    elif case == "prefix_changed":
        backend.events[0]["sim_time_s"] = 0.25
    elif case == "prefix_truncated":
        backend.events.pop(0)
    elif case == "reset_records":
        backend.events.clear()
    elif case == "event_missing_step":
        del event["physics_step"]
    elif case == "event_missing_s":
        del event["sim_time_s"]
    elif case.startswith("event_"):
        field = "physics_step" if case.endswith("step") else "sim_time_s"
        event[field] = {
            "event_wrong_step": 4,
            "event_wrong_s": 1.005,
            "event_bool_step": True,
            "event_negative_step": -1,
            "event_string_step": "3",
            "event_bool_s": True,
            "event_nan_s": float("nan"),
            "event_inf_s": float("inf"),
            "event_negative_s": -1.0,
            "event_string_s": "1.0",
        }[case]
    elif case == "end_step_advanced":
        backend.total_physics_steps = 4
    elif case == "end_s_advanced":
        backend.sim_time_s = 1.005
    elif case == "end_bad_step":
        backend.total_physics_steps = True
    elif case == "end_bad_s":
        backend.sim_time_s = float("inf")
    elif case == "source_not_list":
        type(backend).fault_records = property(lambda _self: {})
    elif case == "source_not_dict":
        backend.events.append("not-a-source-dict")
    elif case == "repeat_begin":
        with pytest.raises((ValueError, RuntimeError), match="already|repeat"):
            recovery_wall_begin(owner, backend)
    good = case in {"healthy", "later_advance", "repeat_end"}
    if good:
        recovery_wall_end(owner, backend)
        if case == "repeat_end":
            with pytest.raises((ValueError, RuntimeError), match="already|repeat"):
                recovery_wall_end(owner, backend)
        if case == "later_advance":
            backend.total_physics_steps = 4
            backend.sim_time_s = 1.005
    else:
        error_type = ValueError if case == "source_not_dict" else (ValueError, RuntimeError)
        error_message = (
            "^owned fault source read/type/payload invalid$"
            if case == "source_not_dict"
            else "episode|source|prefix|event|step|sim|already|failed"
        )
        with pytest.raises(error_type, match=error_message):
            recovery_wall_end(owner, backend)
        # Failed END cannot be converted into a later successful END.
        assert json.dumps(prefix, allow_nan=False).encode() == prefix_snapshot
        backend._episode_id = "cpu-episode-1"
        backend.total_physics_steps = 3
        backend.sim_time_s = 1.0
        backend.events = json.loads(prefix_snapshot) + [backend.event()]
        with pytest.raises((ValueError, RuntimeError), match="failed|already"):
            recovery_wall_end(owner, backend)
    result = recovery_wall_finish(owner, backend)
    assert result["wall_pass"] is (case in {"healthy", "later_advance"})
    assert (output / "wall-start.json").read_bytes() == begin
    assert result["deadline_ns"] == json.loads(begin)["fault_begin"]["deadline_ns"]
    assert json.dumps(prefix, allow_nan=False).encode() == prefix_snapshot
    if case == "source_not_dict":
        assert result["fault_end"] is None
        assert result["failure"].startswith(
            "ValueError: owned fault source read/type/payload invalid"
        )
    if case in {"healthy", "later_advance"}:
        end = result["fault_end"]
        assert end["event_ordinal"] == 1
        assert end["event"] == event
        assert "episode_id" not in end["event"]
        assert end["episode_id"] == "cpu-episode-1"
        assert end["episode_source"] == "owned_live_backend._episode_id"
        assert end["event_source"] == "owned_backend.fault_records"
        journal = [
            json.loads(line) for line in (output / "raw-wall-checks.jsonl").read_text().splitlines()
        ]
        assert [row["record_seq"] for row in journal] == list(range(1, len(journal) + 1))
    if case == "source_not_list":
        type(backend).fault_records = property(lambda self: [dict(row) for row in self.events])


ROUND76_POSITIONS = (
    "BEGIN_LOWER",
    "END_UPPER",
    "CHECK_LOWER",
    "CHECK_UPPER",
    "TERMINAL_LOWER",
    "TERMINAL_UPPER",
)


def round76_journal(output):
    return [
        json.loads(line) for line in (output / "raw-wall-checks.jsonl").read_text().splitlines()
    ]


def round76_counter_failure(rows, position):
    matches = [
        (row["payload"], observation)
        for row in rows
        for observation in row["payload"].get("counter_observations", [])
        if observation["position"] == position and observation["validated"] is False
    ]
    assert len(matches) == 1, f"one rejected original D observation required at {position}"
    return matches[0]


@pytest.mark.parametrize(
    "entry,cause",
    [
        (entry, cause)
        for entry in ("begin", "end", "check")
        for cause in ("plan_attempt", "allocation_bytes", "process_identity")
    ],
    ids=[
        f"{entry}-{cause}"
        for entry in ("begin", "end", "check")
        for cause in ("plan_attempt", "allocation_bytes", "process_identity")
    ],
)
def test_recovery_wall_restored_lifecycle_is_sticky(tmp_path, recovery_wall_cpu_only, entry, cause):
    owner, backend, identity, plan, output = recovery_wall_fixture(tmp_path)
    if entry != "begin":
        recovery_wall_begin(owner, backend)
        backend.events.append(backend.event())
    if entry == "check":
        recovery_wall_end(owner, backend)
    start = output / "wall-start.json"
    original_begin = start.read_bytes() if start.exists() else None
    allocation = Path(plan["allocation_directory"]) / "recovery-0002-attempt-1.json"
    original_allocation = allocation.read_bytes()
    original_pid = identity["pid"]
    message = {
        "plan_attempt": "recovery wall plan allocation identity changed",
        "allocation_bytes": "canonical allocation bytes changed",
        "process_identity": "renderer lease process identity/lifecycle changed",
    }[cause]
    call = {
        "begin": lambda: recovery_wall_begin(owner, backend),
        "end": lambda: recovery_wall_end(owner, backend),
        "check": lambda: owner.check("CURRENT", step=3, sim_time_s=1.0),
    }[entry]
    retry_error = None
    try:
        if cause == "plan_attempt":
            plan["attempt"] = 2
        elif cause == "allocation_bytes":
            allocation.write_bytes(original_allocation + b" ")
        else:
            identity["pid"] += 1
        with pytest.raises(ValueError, match=f"^{message}$"):
            call()
        plan["attempt"] = 1
        allocation.write_bytes(original_allocation)
        identity["pid"] = original_pid
        try:
            call()
        except (ValueError, RuntimeError) as exc:
            retry_error = exc
    finally:
        plan["attempt"] = 1
        allocation.write_bytes(original_allocation)
        identity["pid"] = original_pid
        result = recovery_wall_finish(owner, backend, failure=None)
    assert retry_error is not None, "restoring identity must not authorize retry"
    assert "failed" in str(retry_error) or "already" in str(retry_error)
    assert result["wall_pass"] is False
    assert result["status"] in {"FAILED", "INCOMPLETE"}
    assert result["failure"].startswith(f"ValueError: {message}")
    failures = [
        row["payload"]
        for row in round76_journal(output)
        if row["kind"].endswith("FAILED") and row["payload"].get("failure") == message
    ]
    assert failures and failures[0]["error_type"] == "ValueError"
    if original_begin is not None:
        assert start.read_bytes() == original_begin
        assert result["deadline_ns"] == json.loads(original_begin)["fault_begin"]["deadline_ns"]
        assert result["deadline_ns"] == 60_000_000_100
    else:
        assert not start.exists() and result["fault_begin"] is None


@pytest.mark.parametrize(
    "position,value_kind",
    [
        (position, kind)
        for position in ROUND76_POSITIONS
        for kind in ("negative", "bool", "returned_none", "rollback")
    ],
    ids=[
        f"{position}-{kind}"
        for position in ROUND76_POSITIONS
        for kind in ("negative", "bool", "returned_none", "rollback")
    ],
)
def test_recovery_wall_rejected_counter_raw_evidence(
    tmp_path, recovery_wall_cpu_only, position, value_kind
):
    index = {
        "BEGIN_LOWER": 1,
        "END_UPPER": 2,
        "CHECK_LOWER": 3,
        "CHECK_UPPER": 4,
        "TERMINAL_LOWER": 5,
        "TERMINAL_UPPER": 6,
    }[position]
    counters = [10, 100, 110, 120, 121, 200, 201]
    previous = counters[index - 1]
    bad = {"negative": -1, "bool": True, "returned_none": None, "rollback": previous - 1}[
        value_kind
    ]
    counters[index] = bad
    owner, backend, _identity, _plan, output = recovery_wall_fixture(tmp_path, counters=counters)
    try:
        if position == "BEGIN_LOWER":
            with pytest.raises(RuntimeError, match="counter"):
                recovery_wall_begin(owner, backend)
        else:
            recovery_wall_begin(owner, backend)
            backend.events.append(backend.event())
            if position == "END_UPPER":
                with pytest.raises(RuntimeError, match="counter"):
                    recovery_wall_end(owner, backend)
            else:
                recovery_wall_end(owner, backend)
                if position.startswith("CHECK"):
                    with pytest.raises(RuntimeError, match="counter"):
                        owner.check("CURRENT", step=3, sim_time_s=1.0)
                else:
                    owner.check("CURRENT", step=3, sim_time_s=1.0)
    finally:
        result = recovery_wall_finish(owner, backend, failure=None)
    payload, observation = round76_counter_failure(round76_journal(output), position)
    assert "read_error" not in observation
    assert type(observation["raw_value"]) is type(bad)
    assert observation["raw_value"] == bad
    assert observation["previous_accepted_ns"] == previous
    assert result["wall_pass"] is False and result["status"] in {"FAILED", "INCOMPLETE"}
    slot = "upper_ns" if position.endswith("UPPER") else "lower_ns"
    assert slot not in payload, "rejected D must not enter accepted slot"
    if position == "BEGIN_LOWER":
        assert result["fault_begin"] is None and not (output / "wall-start.json").exists()
    if position == "END_UPPER":
        assert result["fault_end"] is None and payload["end_source_state"]["step"] == 3
    if position in {"CHECK_UPPER", "TERMINAL_UPPER"}:
        assert payload["lower_ns"] == counters[index - 1]
        assert payload["episode_id"] == "cpu-episode-1" and payload["step"] == 3
    if result["fault_begin"] is not None:
        assert result["deadline_ns"] == 60_000_000_100
        assert "episode_id" not in backend.events[0]


@pytest.mark.parametrize("position", ["CHECK_LOWER", "CHECK_UPPER"])
def test_recovery_wall_counter_read_exception_position(tmp_path, recovery_wall_cpu_only, position):
    index = 3 if position == "CHECK_LOWER" else 4
    counters = [10, 100, 110, 120, 121]
    previous = counters[index - 1]
    counters[index] = OSError("CPU original D read exception")
    owner, backend, _identity, _plan, output = recovery_wall_fixture(tmp_path, counters=counters)
    try:
        recovery_wall_begin(owner, backend)
        backend.events.append(backend.event())
        recovery_wall_end(owner, backend)
        with pytest.raises(RuntimeError, match="counter read failed"):
            owner.check("CURRENT", step=3, sim_time_s=1.0)
    finally:
        result = recovery_wall_finish(owner, backend, failure=None)
    payload, observation = round76_counter_failure(round76_journal(output), position)
    assert "raw_value" not in observation
    assert observation["read_error"] == {
        "type": "OSError",
        "message": "CPU original D read exception",
    }
    assert observation["previous_accepted_ns"] == previous
    if position == "CHECK_UPPER":
        assert payload["lower_ns"] == 120 and payload["step"] == 3
    assert result["wall_pass"] is False


def test_recovery_wall_read_then_identity_drift_retains_raw(tmp_path, recovery_wall_cpu_only):
    owner, backend, identity, _plan, output = recovery_wall_fixture(tmp_path)
    recovery_wall_begin(owner, backend)
    original_begin = (output / "wall-start.json").read_bytes()
    backend.events.append(backend.event())
    recovery_wall_end(owner, backend)
    original_read = owner._raw_read
    original_pid = identity["pid"]

    def read_and_drift():
        value = original_read()
        identity["pid"] += 1
        return value

    owner._raw_read = read_and_drift
    try:
        with pytest.raises(ValueError, match="renderer lease process identity/lifecycle changed"):
            owner.check("CURRENT", step=3, sim_time_s=1.0)
    finally:
        identity["pid"] = original_pid
        owner._raw_read = original_read
        result = recovery_wall_finish(owner, backend, failure=None)
    _payload, observation = round76_counter_failure(round76_journal(output), "CHECK_LOWER")
    assert observation["raw_value"] == 120 and type(observation["raw_value"]) is int
    assert observation["previous_accepted_ns"] == 110
    assert result["wall_pass"] is False
    assert result["failure"].startswith(
        "ValueError: renderer lease process identity/lifecycle changed"
    )
    assert (output / "wall-start.json").read_bytes() == original_begin
    assert result["deadline_ns"] == 60_000_000_100


@pytest.mark.parametrize("case", ["healthy_pair", "forged_shared_handle", "finished_handle"])
def test_recovery_wall_lifecycle_evidence_controls(tmp_path, recovery_wall_cpu_only, case):
    owner, backend, _identity, _plan, output = recovery_wall_fixture(tmp_path)
    calls = []
    original_read = owner._raw_read

    def counted_read():
        calls.append("D")
        return original_read()

    owner._raw_read = counted_read
    recovery_wall_begin(owner, backend)
    backend.events.append(backend.event())
    recovery_wall_end(owner, backend)
    if case == "finished_handle":
        assert recovery_wall_finish(owner, backend, failure=None)["wall_pass"] is True
        target = owner
    else:
        target = object.__new__(type(owner))
        target.__dict__ = owner.__dict__
    if case != "healthy_pair":
        before = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        before_calls = list(calls)
        failure_before = owner._failure
        for action in (
            lambda: recovery_wall_begin(target, backend),
            lambda: recovery_wall_end(target, backend),
            lambda: target.check("CURRENT", step=3, sim_time_s=1.0),
            lambda: recovery_wall_finish(target, backend, failure=None),
        ):
            with pytest.raises(ValueError, match="owner|finished|foreign"):
                action()
        assert {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()} == before
        assert calls == before_calls and owner._failure == failure_before
    if case != "finished_handle":
        result = recovery_wall_finish(owner, backend, failure=None)
        assert result["wall_pass"] is True and result["status"] == "PASS"
        assert result["deadline_ns"] == 60_000_000_100
