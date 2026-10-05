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
