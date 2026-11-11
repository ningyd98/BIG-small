"""A separate v5 policy releases one teacher assignment without native authority."""

import copy
import errno
import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.research import native_calibration_collection as collection
from cloud_edge_robot_arm.vision.marker_families import SIDE_PREPARE_ONLY_FAMILY

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "native.calibration.operational.v5"
FAMILY = SIDE_PREPARE_ONLY_FAMILY
CONFIG = "configs/research/native_operational_calibration_side_y_plus_single_teacher_r595.yaml"
CONFIG_SHA = "da7426ab451bf59e76c682d605e5b211c79395b73fbe127990c1e0a1e2cf53cd"
PREPARE_CONFIG = "configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml"
ASSET = "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml"
SOURCE = "src/cloud_edge_robot_arm/research/native_collection_application.py"


def prepare(tmp_path, config=CONFIG):
    directory = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(ROOT / config, output=directory)
    return directory, receipt, collection.load_json(directory / "protocol.json")


def store(directory, protocol):
    (directory / "protocol.json").write_text(json.dumps(protocol))


def reseal(protocol):
    protocol["source_generation"] = collection.digest(protocol["source_hashes"])
    protocol["release_reference"]["source_generation"] = protocol["source_generation"]


def rejected(directory, protocol):
    store(directory, protocol)
    for current in (False, True):
        with pytest.raises(ValueError):
            collection.read_protocol(directory, current_sources=current)


def test_protocol_exact_v5_releases_only_first_assignment_and_preserves_recipe(tmp_path):
    directory, receipt, protocol = prepare(tmp_path)
    assert protocol["schema_version"] == SCHEMA and protocol["marker_family"] == FAMILY
    assert protocol["config_sha256"] == CONFIG_SHA
    assert protocol["execution_release"] == "SINGLE_TEACHER_ASSIGNMENT_RELEASED"
    assert protocol["budget_basis"] == "SINGLE_TEACHER_ATTEMPT_CEILINGS"
    assert receipt["released_assignments"] == ["native-r595-0001"]
    assert protocol["settings"]["released_assignment"] == "native-r595-0001"
    rows = protocol["assignments"]
    assert [row["assignment_id"] for row in rows] == [f"native-r595-{i:04d}" for i in range(1, 10)]
    assert [row["seed"] for row in rows] == list(range(595001, 595010))
    assert [row["ancestors"] for row in rows] == [
        [f"native-r595-preregistered-{i:04d}"] for i in range(1, 10)
    ]
    assert [row["status"] for row in rows] == ["RELEASED"] + ["PREASSIGNED_NOT_RUN"] * 8
    assert all(row["pool"] == "CALIBRATION_ONLY" for row in rows)
    assert protocol["physical_budget"] == 12960
    assert protocol["explicit_acquisition_budget"] == 12976
    assert protocol["implicit_capture_budget"] == 12962
    assert protocol["render_pass_budget"] == 64852
    assert collection.canonical(protocol["actions"]) == collection.canonical(
        collection.action_horizons()
    )
    budget = protocol["authorized_actual_budget"]
    assert budget["teacher_acquisitions"] == budget["mujoco_compile"] == 1
    assert budget["controller"] == 8 and budget["physics_steps"] == 12960
    assert budget["render"] == 64852
    assert (budget["MjData"], budget["mj_forward"], budget["mj_jacSite"]) == (19, 4501, 4500)
    assert protocol["authorized_actual_roles"] == {
        "MjData": {"ENGINE": 1, "IK_SCRATCH": 18},
        "mj_forward": {"RESET": 1, "IK_SCRATCH": 4500},
        "mj_jacSite": {"IK_SCRATCH": 4500},
    }
    for name, roles in protocol["authorized_actual_roles"].items():
        assert sum(roles.values()) == budget[name]
    assert all(budget[key] == 0 for key in ("model_loads", "generations", "paid", "hardware"))
    assert protocol["native_qualification"] == receipt["native_qualification"] == "UNKNOWN"
    assert protocol["admission"]["execution_admitted"] is False
    assert protocol["admission"]["online_effect_status"] == "UNKNOWN"
    assert protocol["role"]["provider"] is protocol["role"]["model"] is None
    assert protocol["role"]["model_requests"] == 0
    assert {CONFIG, ASSET, collection.MARKED_ASSET} <= protocol["source_hashes"].keys()
    assert PREPARE_CONFIG not in protocol["source_hashes"]
    assert protocol["source_hashes"][CONFIG] == CONFIG_SHA
    _, _, prepared = prepare(tmp_path / "prepare-reference", PREPARE_CONFIG)
    assert protocol["geometry"] == prepared["geometry"]
    assert (
        protocol["release_reference"]["command_tcp_rotation"]
        == prepared["release_reference"]["command_tcp_rotation"]
    )
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == protocol
    assert not (directory / "claims").exists()


@pytest.mark.parametrize("formatting", ["compact", "indent4", "newline"])
def test_protocol_config_bytes_are_admitted_before_output(tmp_path, monkeypatch, formatting):
    original = (ROOT / CONFIG).read_bytes()
    payload = json.loads(original)
    changed = {
        "compact": json.dumps(payload).encode(),
        "indent4": json.dumps(payload, indent=4).encode(),
        "newline": original[:-1],
    }[formatting]
    assert json.loads(changed) == payload and changed != original
    path = tmp_path / "same-values.json"
    path.write_bytes(changed)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("config reached output creation")

    monkeypatch.setattr(collection, "fresh_directory", forbidden)
    with pytest.raises(ValueError):
        collection.prepare_native_calibration(path, output=tmp_path / "out")
    assert calls == [] and not (tmp_path / "out").exists()


def test_protocol_exact_config_copy_roundtrips(tmp_path):
    supplied = tmp_path / "copied.json"
    supplied.write_bytes((ROOT / CONFIG).read_bytes())
    directory = tmp_path / "protocol"
    receipt = collection.prepare_native_calibration(supplied, output=directory)
    data = collection.load_json(directory / "protocol.json")
    assert data["config_sha256"] == CONFIG_SHA
    assert receipt["protocol_sha256"] == collection.digest(data)
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == data


@pytest.mark.parametrize(
    "case",
    [
        "family",
        "schema",
        "config_sha",
        "source_config",
        "source_alias",
        "source_asset",
        "geometry",
        "second_release",
        "seed",
        "ancestor",
        "action_order",
        "extra_action",
        "budget",
        "native",
        "admission",
        "release",
    ],
)
def test_protocol_rejects_resealed_identity_release_and_recipe_mutations(tmp_path, case):
    directory, _, protocol = prepare(tmp_path)
    if case == "family":
        protocol["marker_family"] = "outboard_id7_75mm_r579"
    elif case == "schema":
        protocol["schema_version"] = "native.calibration.operational.v4"
    elif case == "config_sha":
        protocol["config_sha256"] = collection.load_json(ROOT / PREPARE_CONFIG)[
            "marked_asset_sha256"
        ]
    elif case == "source_config":
        protocol["source_hashes"][PREPARE_CONFIG] = protocol["source_hashes"].pop(CONFIG)
    elif case == "source_alias":
        protocol["source_hashes"]["configs/alias.json"] = protocol["source_hashes"].pop(CONFIG)
    elif case == "source_asset":
        protocol["source_hashes"][ASSET] = collection.MARKED_SHA
    elif case == "geometry":
        protocol["geometry"]["marker_to_object"][7] = -0.1
    elif case == "second_release":
        protocol["assignments"][1]["status"] = "RELEASED"
    elif case == "seed":
        protocol["assignments"][0]["seed"] = 593001
    elif case == "ancestor":
        protocol["assignments"][0]["ancestors"] = ["native-r593-preregistered-0001"]
    elif case == "action_order":
        protocol["actions"].reverse()
    elif case == "extra_action":
        protocol["actions"].append(copy.deepcopy(protocol["actions"][-1]))
    elif case == "budget":
        protocol["authorized_actual_budget"]["controller"] += 1
    elif case == "native":
        protocol["native_qualification"] = "VALID"
    elif case == "admission":
        protocol["admission"]["execution_admitted"] = True
    else:
        protocol["execution_release"] = "PREPARE_ONLY_NOT_RELEASED"
    reseal(protocol)
    rejected(directory, protocol)


@pytest.mark.parametrize(
    "residue",
    [
        "config_sha",
        "source_path",
        "source_alias",
        "release_source_path",
        "release_source_alias",
        "assignment",
        "seed",
        "ancestor",
    ],
)
def test_protocol_isolated_v5_residue_cannot_downgrade_to_historical_legacy(tmp_path, residue):
    directory, _, protocol = prepare(tmp_path, collection.CONFIG)
    if residue == "config_sha":
        protocol["config_sha256"] = CONFIG_SHA
    elif residue == "assignment":
        protocol["assignments"][0]["assignment_id"] = "native-r595-0001"
    elif residue == "seed":
        protocol["assignments"][0]["seed"] = 595001
    elif residue == "ancestor":
        protocol["assignments"][0]["ancestors"] = ["native-r595-preregistered-0001"]
    else:
        sources = (
            protocol["release_reference"]["source_hashes"]
            if residue.startswith("release_")
            else (protocol["source_hashes"])
        )
        sources["configs/alias.json" if residue.endswith("alias") else CONFIG] = CONFIG_SHA
    reseal(protocol)
    rejected(directory, protocol)


@pytest.mark.parametrize(
    "config", [collection.CONFIG, collection._PREPARE_CONFIG, PREPARE_CONFIG, CONFIG]
)
def test_protocol_current_and_synthetic_historical_sources_keep_exact_config_keys(tmp_path, config):
    directory, _, protocol = prepare(tmp_path, config)
    assert config in protocol["source_hashes"]
    if config != CONFIG:
        assert CONFIG not in protocol["source_hashes"]
    for current in (False, True):
        assert collection.read_protocol(directory, current_sources=current) == protocol
    protocol["source_hashes"][SOURCE] = "1" * 64
    if SOURCE in protocol["release_reference"]["source_hashes"]:
        protocol["release_reference"]["source_hashes"][SOURCE] = "1" * 64
    reseal(protocol)
    store(directory, protocol)
    assert collection.read_protocol(directory, current_sources=False) == protocol
    with pytest.raises(ValueError):
        collection.read_protocol(directory, current_sources=True)


@pytest.mark.parametrize(
    "schema,family",
    [
        (SCHEMA, None),
        (SCHEMA, "outboard_id7_75mm_r579"),
        ("native.calibration.operational.v3", FAMILY),
        ("unknown", FAMILY),
    ],
)
def test_protocol_source_inventory_refuses_unregistered_schema_family_pairs(schema, family):
    with pytest.raises(ValueError):
        collection.source_inventory(marker_family_id=family, protocol_schema=schema)


@pytest.mark.parametrize(
    "case", ["omitted_ik", "missing_roles", "missing_role", "unknown_role", "role_sum"]
)
def test_protocol_exact_ik_role_contract_cannot_be_weakened(tmp_path, case):
    directory, _, protocol = prepare(tmp_path)
    if case == "omitted_ik":
        protocol["authorized_actual_budget"]["mj_forward"] = 1
    elif case == "missing_roles":
        del protocol["authorized_actual_roles"]
    elif case == "missing_role":
        del protocol["authorized_actual_roles"]["mj_forward"]["IK_SCRATCH"]
    elif case == "unknown_role":
        protocol["authorized_actual_roles"]["mj_forward"]["UNKNOWN"] = 1
    else:
        protocol["authorized_actual_roles"]["mj_forward"]["IK_SCRATCH"] = 4499
    rejected(directory, protocol)


def application(tmp_path, config=CONFIG):
    from cloud_edge_robot_arm.research.native_collection_application import (
        NativeCollectionApplication,
    )

    directory, _, protocol = prepare(tmp_path, config)
    assignment = protocol["settings"]["released_assignment"]
    return NativeCollectionApplication.from_startup(
        directory, assignment_id=assignment, output=tmp_path / "run"
    )


def test_authority_job_carries_v5_and_claim_is_one_shot(tmp_path):
    from cloud_edge_robot_arm.research.native_collection_application import (
        _REGISTRY,
        NativeCollectionApplication,
    )

    app = application(tmp_path)
    live = _REGISTRY[app]
    try:
        job = app.prepare_once()
        assert job.manifest_id == SCHEMA
        assert job.seed == 595001 and job.max_attempts == 1
        assert live.origin.upper_ns < live.deadline.deadline_ns
        assert live.deadline.deadline_ns == live.origin.lower_ns + 1800 * 10**9
        with pytest.raises(RuntimeError, match="once"):
            app.prepare_once()
        with pytest.raises(RuntimeError, match="claimed"):
            NativeCollectionApplication.from_startup(
                live.protocol_path, assignment_id="native-r595-0001", output=tmp_path / "retry"
            )
        assert not (tmp_path / "retry").exists()
    finally:
        if live.owner is not None:
            live.owner.close()


@pytest.mark.parametrize("assignment", ["native-r595-0002", "native-r593-0001", "unknown"])
def test_authority_unreleased_assignment_refuses_before_output(tmp_path, monkeypatch, assignment):
    from cloud_edge_robot_arm.research import native_collection_application as module

    directory, _, _ = prepare(tmp_path)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("unreleased assignment created output")

    monkeypatch.setattr(module, "fresh_directory", forbidden)
    with pytest.raises(ValueError):
        module.NativeCollectionApplication.from_startup(
            directory, assignment_id=assignment, output=tmp_path / "run"
        )
    assert not (tmp_path / "run").exists() and calls == []


@pytest.mark.parametrize("fail_gate", [1, 2])
def test_authority_source_drift_stops_before_construction_or_action_dispatch(
    tmp_path, monkeypatch, fail_gate
):
    from cloud_edge_robot_arm.edge.runtime import skill_executor
    from cloud_edge_robot_arm.research import native_collection_application as module
    from cloud_edge_robot_arm.research import native_full_horizon_recorder as recorder_module
    from cloud_edge_robot_arm.simulation.mujoco import backend, native_horizon, skill_robot
    from cloud_edge_robot_arm.vision import capture, execution, top_grasp

    app = application(tmp_path)
    seen = []
    effects = []
    original_check = module.check_sources

    def check(expected, **kwargs):
        seen.append(kwargs)
        assert kwargs == {"marker_family_id": FAMILY, "protocol_schema": SCHEMA}
        if len(seen) == fail_gate:
            raise RuntimeError("synthetic source drift")
        return original_check(expected, **kwargs)

    # Workflow-only stubs: no sensor arrays, native data, camera or physics calls.
    class Backend:
        def __init__(self):
            effects.append("construct")
            self.total_physics_steps = 0
            self.execution_guard_events = []
            self._model = object()

        def initialize(self, config):
            effects.append("initialize")
            self._config = config

        def reset(self, scenario):
            effects.append("reset")

        def step(self, steps):
            self.total_physics_steps += steps

        def capture_each_physics_step(self, **kwargs):
            return nullcontext()

        def shutdown(self):
            effects.append("shutdown")

    class Capture:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class Recorder(Capture):
        bytes_written = 0
        render_accounting = {"exact_passes": 0, "known_completed_passes": 0, "status": "EXACT"}

        def require_clean_reset(self):
            pass

        def purpose(self, purpose):
            return nullcontext()

        def capture(self):
            return object()

        def bind_collection_source(self, source):
            pass

        def _write_original(self, *args):
            pass

        def record_shield_config(self, shield):
            pass

        def record_failure(self, *args):
            pass

        def freeze(self):
            pass

    def no_dispatch(*args, **kwargs):
        effects.append("dispatch")
        raise AssertionError("source drift reached action grounding")

    monkeypatch.setattr(module, "check_sources", check)
    monkeypatch.setattr(backend, "MuJoCoPhysicsBackend", Backend)
    monkeypatch.setattr(skill_robot, "MuJoCoSkillRobot", lambda value: object())
    monkeypatch.setattr(skill_executor, "SkillExecutor", lambda **kwargs: object())
    monkeypatch.setattr(capture, "MuJoCoCaptureSession", Capture)
    monkeypatch.setattr(recorder_module, "NativeFullHorizonRecorder", Recorder)
    monkeypatch.setattr(top_grasp, "matches_calibrated_gripper", lambda *args: True)
    monkeypatch.setattr(module, "_collection_guard", lambda *args: nullcontext())
    monkeypatch.setattr(module, "_record_bootstrap_tracker", lambda *args, **kwargs: (object(), {}))
    monkeypatch.setattr(module, "build_collection_contract", lambda **kwargs: object())
    monkeypatch.setattr(
        module, "_handoff_registered_capture", lambda live, obs, *args, **kwargs: obs
    )
    monkeypatch.setattr(native_horizon, "_issue_collection_session", lambda *args: object())
    monkeypatch.setattr(execution, "research_safety_shield", lambda *args: SimpleNamespace())
    monkeypatch.setattr(module, "_collect_grounded_step", no_dispatch)
    with pytest.raises(RuntimeError, match="worker terminal outcome:") as caught:
        app.execute_once()
    assert "synthetic source drift" in str(caught.value)
    result = collection.load_json(app.output / "collection-result.json")
    assert result["status"] == "COLLECTION_PARTIAL"
    assert len(seen) == fail_gate
    assert "dispatch" not in effects
    assert ("construct" in effects) is (fail_gate == 2)
    assert result["completed_action_count"] == 0
    assert result["native_qualification"] == "UNKNOWN" and not result["execution_admitted"]
    assert "synthetic source drift" in result["worker_snapshot"]["job"]["error_message"]
    assert result["online_effect_status"] == "UNKNOWN"
    assert result["teacher_collection_admitted"] is False
    assert result["qualified_group_score"] is result["joint_bound_m"] is None
    assert (
        result["final_lifecycle_receipt"] is True and result["owner_closure"]["completed"] is True
    )


def local_helper(round_name, filename):
    path = (
        ROOT
        / "artifacts/research/process/20261004-ced-development/astra-rounds"
        / round_name
        / "implementation"
        / filename
    )
    if not path.is_file():
        pytest.skip("Local research invocation helper is outside the public software delivery")
    spec = importlib.util.spec_from_file_location("local_research_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def accounting():
    module = local_helper("round596-original-ik-accounting-20261112", "count_original_cli.py")
    calls = []
    result = object()
    fault = ValueError("native fake failure")

    def data(model):
        calls.append(("data", model))
        return object()

    def forward(model, value, **kwargs):
        calls.append(("forward", model, value, kwargs))
        if native.fail:
            raise fault
        return result

    def jac(*args, **kwargs):
        calls.append(("jac", args, kwargs))

    native = SimpleNamespace(MjData=data, mj_forward=forward, mj_jacSite=jac, fail=False)

    class Backend:
        def __init__(self):
            self._model = object()

        def initialize(self):
            self._data = native.MjData(self._model)

        def reset(self):
            return native.mj_forward(self._model, self._data, token=result)

    class Controller:
        def __init__(self, backend):
            self._backend = backend
            self.starts, self.iterations, self.use_engine = 3, 250, False

        def move_tcp(self, *args, **kwargs):
            return self._inverse_kinematics(*args, **kwargs)

        def _inverse_kinematics(self, *args, **kwargs):
            for _ in range(self.starts):
                scratch = native.MjData(self._backend._model)
                for _ in range(self.iterations):
                    native.mj_forward(
                        self._backend._model, self._backend._data if self.use_engine else scratch
                    )
                    native.mj_jacSite(self._backend._model, scratch, *args, **kwargs)
            return result

    class Skill:
        def _move(self, controller, *args, **kwargs):
            return controller.move_tcp(*args, **kwargs)

    class Writer:
        fail_finish = False

        def __init__(self):
            self.events = []
            self.final = None

        def boundary(self, payload):
            self.events.append(copy.deepcopy(payload))

        def finish(self, payload):
            if self.fail_finish:
                raise OSError("counter writer unavailable")
            self.final = copy.deepcopy(payload)

    writer = Writer()
    counter = module.CallAccounting(native, Backend, Controller, Skill, writer)
    counter.install()
    backend = Backend()
    controller = Controller(backend)
    context = SimpleNamespace(
        module=module,
        native=native,
        backend=backend,
        controller=controller,
        skill=Skill(),
        writer=writer,
        counter=counter,
        calls=calls,
        result=result,
        fault=fault,
    )
    try:
        yield context
    finally:
        counter.restore()


def test_monitor_original_ik_adapter_preserves_calls_and_exact_valid_boundaries(accounting):
    ctx = accounting

    def original():
        ctx.backend.initialize()
        assert ctx.backend.reset() is ctx.result
        for _ in range(6):
            assert ctx.skill._move(ctx.controller, "position", flag=ctx.result) is ctx.result

    ctx.counter.run(original)
    report = ctx.writer.final
    assert report["status"] == "COMPLETE" and report["refused_count"] == 0
    assert {
        name: report["totals"][name]["completed"] for name in ("MjData", "mj_forward", "mj_jacSite")
    } == {"MjData": 19, "mj_forward": 4501, "mj_jacSite": 4500}
    assert (
        report["totals"]["move_tcp"]["completed"]
        == report["totals"]["inverse_kinematics"]["completed"]
        == 6
    )
    assert report["roles"]["MjData"]["ENGINE"]["completed"] == 1
    assert report["roles"]["mj_forward"]["RESET"]["completed"] == 1
    assert all(row["pending"] == row["failed"] == 0 for row in report["totals"].values())
    assert ctx.calls[1][3] == {"token": ctx.result}
    assert next(row for row in ctx.calls if row[0] == "jac")[1][2:] == ("position",)
    assert next(row for row in ctx.calls if row[0] == "jac")[2] == {"flag": ctx.result}


@pytest.mark.parametrize(
    "case",
    ["unknown_caller", "engine_as_scratch", "fourth_start", "extra_iteration", "seventh_motion"],
)
def test_monitor_original_ik_adapter_refuses_before_undeclared_delegate(accounting, case):
    ctx = accounting

    def original():
        ctx.backend.initialize()
        ctx.backend.reset()
        if case == "unknown_caller":
            ctx.native.MjData(ctx.backend._model)
        elif case == "engine_as_scratch":
            ctx.controller.use_engine = True
            ctx.skill._move(ctx.controller)
        elif case == "fourth_start":
            ctx.controller.starts, ctx.controller.iterations = 4, 1
            ctx.skill._move(ctx.controller)
        elif case == "extra_iteration":
            ctx.controller.iterations = 251
            ctx.skill._move(ctx.controller)
        else:
            ctx.controller.starts = ctx.controller.iterations = 1
            for _ in range(7):
                ctx.skill._move(ctx.controller)

    with pytest.raises(RuntimeError, match="accounting refused"):
        ctx.counter.run(original)
    report = ctx.writer.final
    assert report["status"] == "INCOMPLETE" and report["refused_count"] == 1
    assert all(row["pending"] == 0 for row in report["totals"].values())
    assert len([r for r in ctx.calls if r[0] == "data"]) == report["totals"]["MjData"]["completed"]
    assert (
        len([r for r in ctx.calls if r[0] == "forward"])
        == report["totals"]["mj_forward"]["completed"]
    )
    assert (
        len([r for r in ctx.calls if r[0] == "jac"]) == report["totals"]["mj_jacSite"]["completed"]
    )


def test_monitor_original_ik_adapter_preserves_native_exception_and_failed_counts(accounting):
    ctx = accounting

    def original():
        ctx.backend.initialize()
        ctx.native.fail = True
        ctx.backend.reset()

    with pytest.raises(ValueError) as caught:
        ctx.counter.run(original)
    assert caught.value is ctx.fault
    row = ctx.writer.final["totals"]["mj_forward"]
    assert (row["started"], row["completed"], row["failed"], row["pending"]) == (1, 0, 1, 0)


def test_monitor_original_systemexit_survives_secondary_counter_failure(accounting):
    ctx = accounting
    ctx.writer.fail_finish = True
    original = SystemExit(7)

    def cli():
        raise original

    with pytest.raises(SystemExit) as caught:
        ctx.counter.run(cli)
    assert caught.value is original and caught.value.code == 7
    assert ctx.counter.errors == ["OSError: final counters"]


def test_monitor_missing_terminal_retains_only_incomplete_lower_bound(tmp_path):
    module = local_helper("round596-original-ik-accounting-20261112", "count_original_cli.py")
    path = tmp_path / "counts.json"
    writer = module.Journal(path)
    writer.boundary({"event": "STARTED", "totals": {"MjData": {"started": 1, "completed": 0}}})
    writer.close()
    report = module.read_counters(path)
    assert report["status"] == "INCOMPLETE" and not path.exists()
    assert report["lower_bound_snapshot"]["totals"]["MjData"] == {"started": 1, "completed": 0}
    with pytest.raises(FileExistsError):
        module.Journal(path)


def supervisor():
    return local_helper("round595-side-marker-single-teacher-release-20261112", "run_stage.py")


@pytest.mark.parametrize("popen_failure", [False, True])
def test_monitor_launch_intent_is_durable_exclusive_and_precedes_popen(
    tmp_path, monkeypatch, popen_failure
):
    module = supervisor()
    events = tmp_path / "attempts.jsonl"
    calls = []

    def popen(*args, **kwargs):
        intent = json.loads(events.read_text())
        assert intent["event"] == "SINGLE_TEACHER_LAUNCH_INTENT"
        assert intent["round_allowance_consumed"] == 1
        calls.append((args, kwargs))
        if popen_failure:
            raise OSError("synthetic Popen failure")
        return SimpleNamespace(pid=123)

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    spec = {"argv": ["registered-original-cli"], "cwd": str(tmp_path), "env": {}}
    if popen_failure:
        with pytest.raises(OSError, match="synthetic Popen"):
            module.launch_child("full", spec, None, None, events)
    else:
        assert module.launch_child("full", spec, None, None, events).pid == 123
    with pytest.raises(FileExistsError):
        module.launch_child("full", spec, None, None, events)
    assert len(calls) == 1
    module.append_attempt(events, {"event": "TEST_TERMINAL"})
    assert [json.loads(line)["event"] for line in events.read_text().splitlines()] == [
        "SINGLE_TEACHER_LAUNCH_INTENT",
        "TEST_TERMINAL",
    ]


def test_monitor_source_generation_drift_rejects_before_launch(tmp_path, monkeypatch):
    module = supervisor()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    code = tmp_path / "src/cloud_edge_robot_arm/registered.py"
    config = tmp_path / "configs/fixed.json"
    code.parent.mkdir(parents=True)
    config.parent.mkdir()
    code.write_text("original = 1\n")
    config.write_text("{}")
    expected = {str(p.relative_to(tmp_path)): module.sha(p) for p in (code, config)}
    frozen = {"source_hashes": expected, "input_pins": []}
    assert module.sources(frozen) == expected
    code.write_text("original = 2\n")
    with pytest.raises(ValueError, match="source generation drift"):
        module.sources(frozen)


@pytest.mark.parametrize("live", [True, False])
def test_monitor_sqlite_enoent_allowance_remains_live_only_and_exact(tmp_path, monkeypatch, live):
    module = supervisor()
    root = tmp_path / "raw"
    root.mkdir()
    wal = root / "runtime.db-wal"
    wal.write_bytes(b"volatile")
    original = root / "frame.f32"
    original.write_bytes(b"original")
    module.VOLATILE_EXACT = {wal}
    old_lstat = Path.lstat

    def disappearing(path):
        if path == wal:
            raise FileNotFoundError(errno.ENOENT, "transient sqlite", str(path))
        return old_lstat(path)

    monkeypatch.setattr(Path, "lstat", disappearing)
    if live:
        result = module.file_bytes(root, live=True)
        assert result["bytes"] == len(b"original")
        assert result["status"] == "NON_ATOMIC_CONCURRENT_SCAN"
        assert len(result["volatility_events"]) == 1 and result["enumeration_had_skips"]
    else:
        with pytest.raises(FileNotFoundError):
            module.file_bytes(root, live=False)


def test_monitor_original_payload_disappearance_and_symlinks_are_fatal(tmp_path):
    module = supervisor()
    root = tmp_path / "raw"
    root.mkdir()
    original = root / "frame.f32"
    original.write_bytes(b"original")
    module.file_bytes(root, live=True)
    original.unlink()
    with pytest.raises(ValueError, match="retained evidence disappeared"):
        module.file_bytes(root, live=True)
    other = tmp_path / "other"
    other.mkdir()
    (other / "alias").symlink_to(root)
    with pytest.raises(ValueError, match="symlink"):
        module.file_bytes(other)


def test_monitor_requires_exact_frozen_v5_protocol(tmp_path, monkeypatch):
    module = supervisor()
    directory, _, protocol = prepare(tmp_path / "prepare")
    round_root = tmp_path / "round"
    target = round_root / "actual/protocol"
    target.mkdir(parents=True)
    (target / "protocol.json").write_bytes((directory / "protocol.json").read_bytes())
    monkeypatch.setattr(module, "ROUND", round_root)
    frozen = {"expected_protocol": copy.deepcopy(protocol)}
    assert module.protocol_check(frozen)["source_generation"] == protocol["source_generation"]
    protocol["assignments"][1]["status"] = "RELEASED"
    assert frozen["expected_protocol"]["assignments"][1]["status"] == "PREASSIGNED_NOT_RUN"
    (target / "protocol.json").write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="protocol/source/recipe identity"):
        module.protocol_check(frozen)


@pytest.mark.parametrize("case", ["normal", "stubborn_fsync", "primary_and_fsync"])
def test_monitor_exit_receipt_failure_still_reaps_owned_process(tmp_path, monkeypatch, case):
    module = supervisor()
    root, round_root, raw = (tmp_path / name for name in ("workspace", "round", "raw"))
    root.mkdir()
    prepare_evidence = round_root / "actual/prepare-evidence"
    prepare_evidence.mkdir(parents=True)
    implementation = round_root / "implementation"
    implementation.mkdir()
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "ROUND", round_root)
    monkeypatch.setattr(module, "RAW", raw)
    (round_root / "plan.json").write_text("{}")
    monkeypatch.setattr(module, "PLAN_SHA", module.sha(round_root / "plan.json"))
    evidence = round_root / "actual/full-evidence"
    lock = tmp_path / "existing.lock"
    lock.write_bytes(b"persistent")
    protocol_path = round_root / "actual/protocol/protocol.json"
    protocol_path.parent.mkdir()
    protocol = {"source_generation": "synthetic-test-only"}
    protocol_path.write_text(json.dumps(protocol))
    spec = {
        "argv": ["fake-original-cli", "--output", str(raw)],
        "cwd": str(root),
        "env": {"XDG_CACHE_HOME": str(round_root / "actual/cache"),
                "TMPDIR": str(round_root / "actual/tmp")},
        "evidence_directory": str(evidence),
        "child_wall_s": 0,
        "tree_RSS_bytes": 8 << 30,
        "output_bytes_limit": 1 << 30,
        "free_disk_min_bytes": 32 << 30,
    }
    frozen = {
        "effective_plans": [], "baseline_head": "synthetic-head",
        "runner_sha256": module.sha(Path(module.__file__)),
        "plan_sha256": module.PLAN_SHA, "expected_protocol": protocol,
        "monitor_contract": {"volatile_exact_files": [], "volatile_subtrees": []},
        "stages": {"full": spec}, "budgets": {"raw_bytes": 1 << 30},
        "gpu_admission": {"lock_path": str(lock)},
    }
    (implementation / "frozen-invocations.local.json").write_text(json.dumps(frozen))
    (prepare_evidence / "result.json").write_text(json.dumps({
        "returncode": 0, "reaped": True, "remaining_live": [], "errors": [],
    }))
    (prepare_evidence / "protocol-pin.json").write_text(json.dumps(module.protocol_check(frozen)))
    events, sources, fsync_faults = [], [], []
    clock = [100.0]
    live = [case != "normal"]
    pid = 987654321

    class Child:
        returncode = None if live[0] else 0

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            events.append(("wait", timeout, clock[0]))
            assert not live[0]
            return self.returncode

    child = Child()
    child.pid = pid

    def popen(*args, **kwargs):
        assert args[0] == spec["argv"] and kwargs["start_new_session"]
        events.append(("popen", clock[0]))
        return child

    def process(value):
        if value == pid and live[0]:
            return {"pid": pid, "starttime": 123, "state": "S", "pgid": pid,
                    "sid": pid, "rss_bytes": 0}
        return None

    def deliver(value, sig):
        assert value == pid
        events.append((module.signal.Signals(sig).name, clock[0]))
        if sig == module.signal.SIGKILL or case == "primary_and_fsync":
            live[0] = False
            child.returncode = -int(sig)

    def sleep(seconds):
        clock[0] += seconds

    handlers = {sig: object() for sig in (module.signal.SIGINT, module.signal.SIGTERM)}
    original_handlers = handlers.copy()

    def signal(sig, handler):
        old = handlers[sig]
        handlers[sig] = handler
        return old

    def flock(stream, operation):
        if operation == module.fcntl.LOCK_UN:
            assert not live[0] and any(row[0] == "wait" for row in events)
            assert (evidence / "final-receipt.json").is_file()
            events.append(("unlock", clock[0]))
        else:
            assert operation == module.fcntl.LOCK_EX | module.fcntl.LOCK_NB
            events.append(("lock", clock[0]))

    waited = [False]

    def waitpid(value, options):
        assert value == -1 and options == module.os.WNOHANG
        events.append(("waitpid", clock[0]))
        if not waited[0]:
            waited[0] = True
            return pid + 1, 0
        return 0, 0

    original_fsync, original_scan = module.os.fsync, module.file_bytes

    def fsync(fd):
        target = evidence / "exit-before-cleanup.json"
        if case != "normal" and target.is_file():
            opened, retained = module.os.fstat(fd), target.stat()
            if (opened.st_dev, opened.st_ino) == (retained.st_dev, retained.st_ino):
                fsync_faults.append(fd)
                raise OSError(errno.EIO, "synthetic exit-receipt fsync failure")
        return original_fsync(fd)

    def scan(path, **kwargs):
        if case == "primary_and_fsync" and path == raw and kwargs.get("live"):
            raise RuntimeError("synthetic monitor observation failure")
        return original_scan(path, **kwargs)

    monkeypatch.setattr(module, "sources", lambda plan: sources.append("checked"))
    monkeypatch.setattr(module, "admission", lambda *args: events.append(("admission", clock[0])))
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(
        module.subprocess, "check_output",
        lambda argv, **kwargs: "synthetic-head\n" if "rev-parse" in argv else "",
    )
    monkeypatch.setattr(module, "process", process)
    monkeypatch.setattr(
        module, "children", lambda value: [pid] if value == module.os.getpid() and live[0] else []
    )
    monkeypatch.setattr(module.os, "killpg", deliver)
    monkeypatch.setattr(module.os, "kill", deliver)
    monkeypatch.setattr(module.os, "waitpid", waitpid)
    monkeypatch.setattr(module.os, "fsync", fsync)
    monkeypatch.setattr(module.signal, "signal", signal)
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(module.time, "sleep", sleep)
    monkeypatch.setattr(module.ctypes, "CDLL", lambda *a, **k: SimpleNamespace(prctl=lambda *a: 0))
    monkeypatch.setattr(module.fcntl, "flock", flock)
    monkeypatch.setattr(module.shutil, "disk_usage", lambda *args: SimpleNamespace(free=100 << 30))
    monkeypatch.setattr(module.resource, "getrusage", lambda *args: SimpleNamespace(ru_maxrss=0))
    monkeypatch.setattr(module, "file_bytes", scan)
    escaped, outcome = None, None
    try:
        outcome = module.run("full")
    except BaseException as error:
        escaped = error
    assert any(row[0] == "wait" for row in events), f"cleanup skipped after {escaped!r}"
    assert escaped is None
    assert not live[0] and handlers == original_handlers
    assert len([row for row in events if row[0] == "popen"]) == 1
    assert sources == ["checked", "checked"] and events[-1][0] == "unlock"
    result = json.loads((evidence / "result.json").read_text())
    assert result["reaped"] and result["remaining_live"] == []
    assert result["adopted_reaped"] == [{"pid": pid + 1, "status": 0}]
    assert next(row[1] for row in events if row[0] == "wait") == 3
    if case == "normal":
        assert outcome == 0 and result["errors"] == [] and fsync_faults == []
        assert not any(row[0] in {"SIGTERM", "SIGKILL"} for row in events)
    else:
        assert outcome == 2 and len(fsync_faults) == 1
        receipt_error = next(row for row in result["errors"] if row.get("phase") == "exit-receipt")
        assert receipt_error["type"] == "OSError" and "fsync failure" in receipt_error["message"]
        signals = [row for row in events if row[0] in {"SIGTERM", "SIGKILL"}]
        if case == "stubborn_fsync":
            assert result["reason"] == "WALL_LIMIT"
            assert [row[0] for row in signals] == ["SIGTERM", "SIGKILL"]
            assert 5 <= signals[1][1] - signals[0][1] < 5.1
        else:
            assert [row[0] for row in signals] == ["SIGTERM"]
            assert result["state"] == "FAILED_STOPPED"
            assert any(row["message"] == "synthetic monitor observation failure"
                       for row in result["errors"])
