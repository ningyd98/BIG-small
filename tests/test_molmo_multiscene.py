"""多场景研究入口的预算、分类和存证测试；不运行模型/网络。"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningResponse


def api():
    return importlib.import_module("scripts.probe_molmo_multiscene")


def setup_run(tmp_path, *, source_hashes=None, asset_sha="a" * 64, execution_plan=None):
    module = api()
    cases = module.build_cases(asset_sha)
    root = tmp_path / "run"
    registry = module.preregister(root, cases, source_hashes or {}, execution_plan=execution_plan)
    ledger = module.RunLedger(root, registry)
    return module, cases, root, registry, ledger


def test_seven_assignments_are_static_unique_and_parameterized_before_rendering():
    cases = api().build_cases("a" * 64)
    assert [case.case_id for case in cases] == ["N01", "N02", "P01", "N03", "P02", "N04", "P03"]
    assert [case.point_cap for case in cases] == [2, 2, 4, 2, 4, 2, 4]
    assert sum(case.paid_cap for case in cases) == 3
    assert len({case.request_id for case in cases}) == 7
    assert all(
        case.task.instruction == f"Move the {case.task.target_phrase} to the green region."
        for case in cases
    )
    assert all(case.scene.scene_parameters["depth_noise_m"] == 0 for case in cases)
    assert cases[0].task.target_phrase == "blue block"
    assert cases[0].scene.scene_parameters["target"]["color_name"] == "red"
    assert len(cases[1].scene.scene_parameters["distractors"]) == 1
    assert cases[3].scene.scene_parameters["destination"]["rgba"] == [0.5, 0.5, 0.5, 1]


def test_preregistration_requires_a_new_root_and_exclusively_seals_its_contents(tmp_path):
    module, cases, root, registry, _ = setup_run(tmp_path)
    assert len(registry["cases"]) == 7
    assert registry["raw_root"] == str(root.resolve())
    assert (root / "registry.json").is_file() and (root / "registry.sha256").is_file()
    with pytest.raises((FileExistsError, ValueError)):
        module.preregister(root, cases, {})


@pytest.mark.parametrize("variant", ["missing", "duplicate", "unknown"])
def test_summary_keeps_fixed_denominator_and_invalidates_unknown_or_duplicate(tmp_path, variant):
    module, _, root, registry, _ = setup_run(tmp_path)
    records = [{"case_id": row["case_id"], "verdict": "FAIL_TEST"} for row in registry["cases"]]
    if variant == "missing":
        records.pop()
    elif variant == "duplicate":
        records.append(records[0].copy())
    else:
        records.append({"case_id": "UNREGISTERED", "verdict": "PASS_PLANNED"})
    result = module.summarize(registry, records, root=root)
    assert (
        result["total_cases"] == 7
        and result["positive_cases"] == 3
        and result["negative_cases"] == 4
    )
    assert len(result["cases"]) == 7 and not result["all_cases_pass"]
    assert result["missing_cases"] == (1 if variant == "missing" else 0)
    assert result["duplicate_cases"] == (1 if variant == "duplicate" else 0)
    assert result["unknown_records"] == (1 if variant == "unknown" else 0)
    if variant != "missing":
        assert not result["valid_suite"]


def test_claim_is_exclusive_and_a_crashed_group_cannot_be_restarted(tmp_path):
    module, _, root, registry, ledger = setup_run(tmp_path)
    ledger.claim("G1")
    ledger.close()
    restarted = module.RunLedger(root, registry)
    with pytest.raises(ValueError, match="claim"):
        restarted.claim("G1")
    restarted.close()


def test_group_order_and_concurrent_group_are_rejected(tmp_path):
    module, _, root, registry, ledger = setup_run(tmp_path)
    with pytest.raises(ValueError):
        ledger.claim("G2")
    ledger.claim("G1")
    other = module.RunLedger(root, registry)
    with pytest.raises((ValueError, BlockingIOError)):
        other.claim("G2")
    other.close()
    ledger.close()


@pytest.mark.parametrize("kind,case_id", [("point", "P03"), ("paid", "N01"), ("load", "N01")])
def test_ledger_refuses_cross_group_and_forbidden_reservations(tmp_path, kind, case_id):
    _, _, _, _, ledger = setup_run(tmp_path)
    ledger.claim("G1")
    ledger.reserve("load", group_id="G1", case_id=None)
    ledger.begin_case("G1", "N01")
    with pytest.raises(ValueError):
        ledger.reserve(kind, group_id="G1", case_id=case_id)
    ledger.close()


def test_order_load_point_case_and_group_caps_are_durable(tmp_path):
    _, _, root, _, ledger = setup_run(tmp_path)
    ledger.claim("G1")
    ledger.reserve("load", group_id="G1", case_id=None)
    with pytest.raises(ValueError):
        ledger.reserve("load", group_id="G1", case_id=None)
    with pytest.raises(ValueError):
        ledger.begin_case("G1", "P01")
    for case_id, cap in [("N01", 2), ("N02", 2), ("P01", 4)]:
        ledger.begin_case("G1", case_id)
        for _ in range(cap):
            path = ledger.reserve("point", group_id="G1", case_id=case_id)
            assert path.is_file()
        with pytest.raises(ValueError):
            ledger.reserve("point", group_id="G1", case_id=case_id)
        if case_id == "P01":
            ledger.reserve("paid", group_id="G1", case_id=case_id)
            with pytest.raises(ValueError):
                ledger.reserve("paid", group_id="G1", case_id=case_id)
        ledger.end_case("G1", case_id)
    assert len(list((root / "reservations").glob("point-*.json"))) == 8
    ledger.close()


def test_reservation_write_failure_does_not_create_a_successful_start(tmp_path, monkeypatch):
    module, _, root, _, ledger = setup_run(tmp_path)
    ledger.claim("G1")
    original = module._write

    def fail(path, value):
        if path.parent == root / "reservations":
            raise OSError("injected disk failure")
        return original(path, value)

    monkeypatch.setattr(module, "_write", fail)
    with pytest.raises(OSError):
        ledger.reserve("load", group_id="G1", case_id=None)
    assert not list((root / "reservations").glob("load-*.json"))
    assert ledger.fatal
    ledger.close()


def negative_response(case):
    return InitialPlanningResponse(
        request_id=case.request_id,
        outcome="REQUEST_MORE_OBSERVATION",
        reason="fixture visual refusal",
        created_at=datetime.now(UTC),
    )


@pytest.mark.parametrize(
    "fault", ["cloud_entry", "budget_block", "runtime_error", "capture_gap", "INVALID"]
)
def test_test_boundary_and_runtime_failures_never_count_as_visual_rejection(fault, tmp_path):
    module, cases, root, registry, _ = setup_run(tmp_path)
    case = cases[0]
    events = [
        {
            "kind": "point",
            "phase": "end",
            "status": "ABSENT",
            "bound": True,
            "actual_generation_delta": 1,
        }
    ]
    if fault == "INVALID":
        events[0]["status"] = "INVALID"
    else:
        events.append({"kind": fault})
    result = module.classify_case(
        case, negative_response(case), events, root=root, registry=registry
    )
    assert not result["passed"] and not result["verdict"].startswith("PASS")
    if fault == "cloud_entry":
        assert result["verdict"] == "FAIL_CLOUD_GATE_REACHED"


def test_bare_absence_and_geometry_fields_cannot_authorize_a_pass(tmp_path):
    module, cases, root, registry, _ = setup_run(tmp_path)
    case = cases[0]
    absence = [
        {
            "kind": "point",
            "phase": "end",
            "status": "ABSENT",
            "bound": True,
            "actual_generation_delta": 1,
        }
    ]
    result = module.classify_case(
        case, negative_response(case), absence, root=root, registry=registry
    )
    assert not result["passed"] and result["refusal_source"] is None
    geometry = [
        {
            "kind": "point",
            "phase": "end",
            "status": "POINT",
            "bound": True,
            "actual_generation_delta": 1,
        }
    ] * 2
    geometry += [
        {
            "kind": "stage",
            "phase": "error",
            "stage": "tracker",
            "error_type": "ValueError",
            "visual_rejection": True,
        }
    ]
    result = module.classify_case(
        case, negative_response(case), geometry, root=root, registry=registry
    )
    assert not result["passed"] and result["refusal_source"] is None


def test_a_positive_refusal_cannot_pass_as_a_negative(tmp_path):
    module, cases, root, registry, _ = setup_run(tmp_path)
    case = cases[2]
    result = module.classify_case(case, negative_response(case), [], root=root, registry=registry)
    assert not result["passed"]


def test_run_case_preserves_original_response_and_uses_only_two_capture_calls(
    tmp_path, monkeypatch
):
    from tests.test_molmo_grounded_planner import request_scene
    from tests.test_molmo_revalidation import rebuild

    module, cases, root, _, ledger = setup_run(tmp_path)
    # Complete the preceding negative slots without running perception.
    ledger.claim("G1")
    ledger.reserve("load", group_id="G1", case_id=None)
    for name in ["N01", "N02"]:
        ledger.begin_case("G1", name)
        ledger.end_case("G1", name)
    case = cases[2]
    base = request_scene().observation
    calls = []

    class Session:
        def __init__(self, config):
            self.index = 0

        def __enter__(self):
            calls.append("open")
            return self

        def __exit__(self, *args):
            calls.append("close")

        def apply_scene(self, scene):
            assert self.index == 0
            calls.append("apply")

        def capture(self):
            self.index += 1
            calls.append("capture")
            return rebuild(base, frame_id=f"frame-{self.index}", captured_at=datetime.now(UTC))

        def step(self, *args):
            raise AssertionError("physics step forbidden")

        def reset(self, *args):
            raise AssertionError("reset forbidden after setup")

    original_response = negative_response(case)
    cloud = SimpleNamespace(
        _request_visual=lambda *a: {}, _post=lambda *a: {}, raw_transport_observer=None
    )
    adapter = SimpleNamespace(cloud=cloud, post_cloud_observation_supplier=None)

    def factory(**kwargs):
        assert kwargs["task"] is case.task
        adapter.post_cloud_observation_supplier = kwargs["post_cloud_observation_supplier"]
        return adapter

    class Pipeline:
        def __init__(self, *, planner):
            self.planner = planner

        def process(self, request):
            assert request.user_instruction == case.task.instruction
            assert request.scene.objects == [] and request.scene.robot_state == {}
            assert "instance_ids" not in request.model_dump_json()
            assert request.observation is not None
            self.planner.post_cloud_observation_supplier()
            return original_response

    monkeypatch.setattr(module, "MuJoCoCaptureSession", Session)
    monkeypatch.setattr(module, "build_molmo_grounded_planner", factory)
    monkeypatch.setattr(module, "PlanningPipeline", Pipeline)
    returned = module.run_case(
        case, provider=object(), service=object(), profile_id="fixture", ledger=ledger, output=root
    )
    assert returned is original_response
    assert calls == ["open", "apply", "capture", "capture", "close"]
    ledger.close()


def test_mutated_registry_is_rejected_before_any_claim_or_load(tmp_path):
    module, _, root, registry, _ = setup_run(tmp_path)
    registry["cases"][0]["point_cap"] = 100
    with pytest.raises(ValueError):
        module.RunLedger(root, registry)
    assert not list((root / "claims").glob("group-*.json"))


def test_one_group_constructs_one_provider_and_visits_every_assigned_case(tmp_path, monkeypatch):
    _, _, _, _, state = recorded_suite(tmp_path, monkeypatch)
    assert len(state.providers) == 1 and state.case_index == 3
    assert [r["case_id"] for r in state.reports[0]["results"]] == ["N01", "N02", "P01"]
    assert state.reports[0]["actual_counts"]["loads"] == 1
    assert state.reports[0]["actual_counts"]["generations_started"] == 6


@pytest.mark.parametrize(
    "damage", [None, "binding", "frames", "final_gate", "paid", "query_count", "exception"]
)
def test_positive_requires_original_contract_all_bindings_and_both_gates(
    tmp_path, monkeypatch, damage
):
    module, cases, root, registry, _ = recorded_suite(tmp_path, monkeypatch)
    case = cases[2]
    response = saved_response(module, root, case)
    events = module.RunLedger(root, registry).events_for(case.case_id)
    points = [e for e in events if e["kind"] == "point" and e["phase"] == "end"]
    captures = [e for e in events if e["kind"] == "capture" and e["phase"] == "end"]
    if damage == "binding":
        points[0]["bound"] = False
    elif damage == "frames":
        captures[1]["observation_checksum"] = captures[0]["observation_checksum"]
    elif damage == "final_gate":
        response.attempts[0].draft.observation_evidence.pop("final_plan_admission")
    elif damage == "paid":
        events = [e for e in events if e["kind"] != "paid"]
    elif damage == "query_count":
        events.remove(points[0])
    elif damage == "exception":
        events.append({"kind": "runtime_error", "phase": "notice"})
    result = module.classify_case(case, response, events, root=root, registry=registry)
    assert result["passed"] is (damage is None), result


def recorded_suite(
    tmp_path,
    monkeypatch,
    *,
    groups=("G1",),
    native_fault=None,
    cloud_mode="normal",
    negative_mode="ABSENT",
    damage=None,
    setup_hook=None,
    capture_transform=None,
    execution_plan=None,
):
    """Exercise original pipeline/transport with CPU-only native and HTTP boundaries."""
    import hashlib
    import io
    import json
    import urllib.request
    import uuid
    from contextlib import nullcontext
    from dataclasses import asdict

    from cloud_edge_robot_arm.vision.grounded_planner import MolmoGroundedPlannerAdapter
    from cloud_edge_robot_arm.vision.molmo_pointing import (
        MODEL_ID,
        BoundPointResult,
        native_prompt,
        parse_native_point,
    )
    from tests.test_molmo_grounded_planner import SKILLS, cloud_fixture, request_scene
    from tests.test_molmo_revalidation import rebuild

    module = api()
    names = [
        "scripts/probe_molmo_multiscene.py",
        "assets/robots/franka_panda/scene.xml",
        "src/cloud_edge_robot_arm/vision/point_association.py",
        "src/cloud_edge_robot_arm/vision/tracking.py",
        "src/cloud_edge_robot_arm/vision/planner.py",
    ]
    sources = {
        name: hashlib.sha256((module.ROOT / name).read_bytes()).hexdigest() for name in names
    }
    execution = module._load_execution_plan(execution_plan) if execution_plan is not None else None
    if execution is not None:
        sources = execution["source_hashes"]
    module, cases, root, registry, _ = setup_run(
        tmp_path, source_hashes=sources, asset_sha=sources["assets/robots/franka_panda/scene.xml"],
        execution_plan=execution_plan,
    )
    state = SimpleNamespace(
        active=None,
        case_index=0,
        group=None,
        providers=[],
        calls=0,
        reports=[],
        responses=[],
        ledger=None,
    )

    class Session:
        def __init__(self, config):
            self.index = 0

        def __enter__(self):
            state.active = module.GROUPS[state.group][state.case_index]
            state.case_index += 1
            return self

        def __exit__(self, *args):
            pass

        def apply_scene(self, scene):
            case = next(c for c in cases if c.case_id == state.active)
            chosen = damage if state.active == "N02" else None
            if chosen is None and case.scene.scene_parameters["target"]["color_name"] == "blue":
                chosen = "wrong_color"
            self.base = request_scene(
                damage=chosen, scene_id=case.scene.group_id, episode_id=uuid.uuid4().hex
            ).observation

        def capture(self):
            self.index += 1
            observation = rebuild(
                self.base, frame_id=uuid.uuid4().hex, captured_at=datetime.now(UTC)
            )
            return capture_transform(observation) if capture_transform else observation

    class Provider:
        def __init__(self, *, raw_directory, **kwargs):
            self.raw_directory = raw_directory
            self.raw_directory.mkdir(parents=True)
            self.model_loads_started = 1
            self.generation_calls_started = 0
            self.generation_calls_completed = 0
            self.attempts = 0
            module._write(raw_directory / "load-started.json", {"model_loads_started": 1})
            module._write(
                raw_directory / "loaded.json",
                {"model_loads_started": 1, "load_s": 0.0, "runtime": {"scope": "CPU_FIXTURE"}},
            )
            state.providers.append(self)

        def point(self, observation, phrase):
            state.calls += 1
            self.attempts += 1
            folder = self.raw_directory / f"request-{self.attempts:04}"
            folder.mkdir()
            binding = {
                "observation_checksum": observation.checksum_sha256,
                "rgb_sha256": observation.evidence()["rgb_sha256"],
                "query_sha256": hashlib.sha256(phrase.encode()).hexdigest(),
            }
            module._write(
                folder / "started.json",
                binding | {"phrase": phrase, "started_at": datetime.now(UTC).isoformat()},
            )
            (folder / "prompt.txt").write_text(native_prompt(phrase))
            module._write(folder / "processor.json", {"scope": "CPU_FIXTURE"})
            module._write(folder / "input-token-ids.json", [1])
            try:
                if native_fault == "before_start":
                    raise OSError("CPU native preparation failure")
                self.generation_calls_started += 1
                module._write(
                    folder / "generation-started.json",
                    {"generation_calls_started": self.generation_calls_started},
                )
                if native_fault == "after_start":
                    raise RuntimeError("CPU native CUDA failure")
                self.generation_calls_completed += 1
                module._write(
                    folder / "generation-completed.json",
                    {
                        "generation_calls_completed": self.generation_calls_completed,
                        "generation_s": 0.001,
                        "output_tokens": 1,
                    },
                )
                module._write(folder / "output-token-ids.json", [2])
                if native_fault == "after_complete":
                    raise OSError("CPU raw persistence failure after generation")
                coords = "150 410" if phrase.startswith("visible top center") else "650 425"
                raw = f'<points coords="1 1 {coords}">support</points>'
                if state.active.startswith("N") and negative_mode != "POINT":
                    raw = "ABSENT" if negative_mode == "ABSENT" else "invalid fixture text"
                result = parse_native_point(raw)
                (folder / "raw-response.txt").write_text(raw)
                evidence = {
                    "model": MODEL_ID,
                    "precision": "BF16",
                    "model_image_count": 1,
                    "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "raw_directory": str(folder),
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "reached_cap": False,
                    "generation_s": 0.001,
                    "end_to_end_s": 0.001,
                    "generation_calls_started": self.generation_calls_started,
                    "generation_calls_completed": self.generation_calls_completed,
                }
                module._write(
                    folder / "result.json", binding | evidence | {"native": asdict(result)}
                )
                return BoundPointResult(
                    result,
                    binding["observation_checksum"],
                    binding["rgb_sha256"],
                    binding["query_sha256"],
                    evidence,
                )
            except Exception as exc:
                module._write(
                    folder / "failure.json",
                    binding
                    | {
                        "error_type": type(exc).__name__,
                        "generation_calls_started": self.generation_calls_started,
                        "generation_calls_completed": self.generation_calls_completed,
                    },
                )
                raise

    def factory(**kwargs):
        cloud, _ = cloud_fixture(monkeypatch)
        adapter = MolmoGroundedPlannerAdapter(
            cloud=cloud,
            point_provider=kwargs["point_provider"],
            task=kwargs["task"],
            post_cloud_observation_supplier=kwargs["post_cloud_observation_supplier"],
        )
        return adapter

    class External:
        def open(self, request, timeout):
            if cloud_mode == "http_error":
                from urllib.error import HTTPError

                raise HTTPError(request.full_url, 500, "CPU fixture", {}, io.BytesIO(b"http-error"))
            if cloud_mode == "malformed":
                return io.BytesIO(b"not-json-after-HTTP-response")
            return io.BytesIO(
                json.dumps(
                    {
                        "model": "gpt-6.1-sol",
                        "usage": {"total_tokens": 2},
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps({"skills": SKILLS, "reason": "CPU"})
                                }
                            }
                        ],
                    }
                ).encode()
            )

    def build(**kwargs):
        adapter = factory(**kwargs)
        monkeypatch.setattr(urllib.request, "build_opener", lambda *a: External())
        return adapter

    monkeypatch.setattr(module, "MuJoCoCaptureSession", Session)
    monkeypatch.setattr(module, "MolmoPointProvider", Provider)
    monkeypatch.setattr(module, "build_molmo_grounded_planner", build)
    if execution is None:
        monkeypatch.setattr(module, "_check_sources", lambda registry: None)
    monkeypatch.setattr(
        module,
        "_profile",
        lambda *a: (
            object(),
            {"secret_present": True, "settings_hash": module.SETTINGS_SHA, "role": {}},
        ),
    )
    monkeypatch.setattr(module, "_admit_resources", lambda *a: nullcontext({}))
    if setup_hook:
        setup_hook(module, state, root, registry)
    for group in groups:
        state.group, state.case_index = group, 0
        arguments = {
            "model_directory": root, "asset_manifest": root / "fake.json",
            "model_store": root / "fake.db", "profile_id": "fixture", "gpu_lock": root / "gpu.lock",
        }
        if execution is not None:
            runtime = execution["runtime"]
            arguments = {
                k: Path(runtime[k]) for k in ("model_directory", "model_store", "gpu_lock")
            }
            arguments.update(asset_manifest=Path(runtime["asset_manifest"]["path"]),
                             profile_id=runtime["profile_id"])
        try:
            report = module.run_group(
                group,
                registry=root / "registry.json",
                output=root,
                allow_paid=True,
                **arguments,
            )
            state.reports.append(report)
        except Exception as exc:
            state.reports.append({"raised": type(exc).__name__})
    return module, cases, root, registry, state


def checked_classify(module, case, response, events, root, registry):
    import inspect

    kwargs = (
        {"root": root, "registry": registry}
        if "root" in inspect.signature(module.classify_case).parameters
        else {}
    )
    return module.classify_case(case, response, events, **kwargs)


def checked_summary(module, registry, results, root):
    import inspect

    return module.summarize(
        registry,
        results,
        **({"root": root} if "root" in inspect.signature(module.summarize).parameters else {}),
    )


def saved_response(module, root, case):
    import json

    path = root / case.group_id / case.case_id / "pipeline-return.json"
    return (
        InitialPlanningResponse.model_validate(json.loads(path.read_bytes()))
        if path.exists()
        else None
    )


def test_r561_invalid_original_depth_never_counts_as_expected_rejection(tmp_path, monkeypatch):
    module, cases, root, registry, _ = recorded_suite(
        tmp_path, monkeypatch, negative_mode="POINT", damage="depth"
    )
    case = cases[1]
    events = module.RunLedger(root, registry).events_for(case.case_id)
    result = checked_classify(
        module, case, saved_response(module, root, case), events, root, registry
    )
    assert not result["passed"]
    assert result["refusal_source"] is None


@pytest.mark.parametrize(
    "fault,started,completed",
    [("before_start", 0, 0), ("after_start", 1, 0), ("after_complete", 1, 1)],
)
def test_r561_native_failure_counts_and_stops_resident_group(
    tmp_path, monkeypatch, fault, started, completed
):
    _, _, root, _, state = recorded_suite(tmp_path, monkeypatch, native_fault=fault)
    report = state.reports[0]
    assert state.calls == 1
    assert report["status"] == "INCOMPLETE"
    assert report["actual_counts"]["generations_started"] == started
    assert report["actual_counts"]["generations_completed"] == completed
    first = report["results"][0]
    assert first["actual_generations"] == started
    assert first["actual_generations_completed"] == completed
    assert [row["verdict"] for row in report["results"]][1:] == ["NOT_RUN", "NOT_RUN"]
    assert len(list((root / "reservations").glob("point-*.json"))) == 1


@pytest.mark.parametrize("mode", ["malformed", "http_error"])
def test_r561_received_error_cloud_bytes_are_accounted_without_parsed_success(
    tmp_path, monkeypatch, mode
):
    _, _, _, _, state = recorded_suite(tmp_path, monkeypatch, cloud_mode=mode)
    positive = next(row for row in state.reports[0]["results"] if row["case_id"] == "P01")
    assert not positive["passed"]
    assert positive["paid"]["reserved"] == 1
    assert positive["paid"]["delegated_post"] == 1
    assert positive["paid"]["response_observed"] == 1
    assert positive["paid"]["parsed_success"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "mkdir",
        "lock_open",
        "flock",
        "claim",
        "begin",
        "end",
        "enumerate",
        "read",
        "json",
        "fsync",
        "group_report",
        "manifest",
        "terminal",
    ],
)
def test_r561_persistence_fault_poison_stops_calls_and_releases_group_lock(
    tmp_path, monkeypatch, fault
):
    import fcntl
    from pathlib import Path

    fired = []

    def hook(module, state, root, registry):
        original_write, original_open, original_mkdir = module._write, Path.open, Path.mkdir
        original_glob, original_read, original_flock = Path.glob, Path.read_bytes, fcntl.flock

        def trigger():
            if not fired:
                fired.append(state.calls)
                raise OSError("CPU one-shot persistence failure")

        def write(path, value):
            if (
                (fault == "claim" and path.name == "group-G1.json")
                or (fault == "begin" and path.name == "case-N01-start.json")
                or (fault == "end" and path.name == "case-N01-end.json")
                or (fault == "group_report" and path.name == "group-end.json")
                or (fault == "manifest" and path.name == "case-evidence.manifest.json")
                or (
                    fault == "terminal"
                    and isinstance(value, dict)
                    and value.get("kind") == "point"
                    and value.get("phase") == "end"
                )
            ):
                trigger()
            return original_write(path, value)

        def opening(path, *a, **kw):
            if fault == "lock_open" and path == root / "ledger.lock":
                trigger()
            return original_open(path, *a, **kw)

        def mkdir(path, *a, **kw):
            if fault == "mkdir" and path == root / "events/N01":
                trigger()
            return original_mkdir(path, *a, **kw)

        def glob(path, pattern):
            if fault == "enumerate" and path == root / "reservations":
                trigger()
            return original_glob(path, pattern)

        def read(path):
            if fault == "read" and path == root / "registry.sha256":
                trigger()
            data = original_read(path)
            if fault == "json" and path == root / "registry.sha256" and not fired:
                fired.append(state.calls)
                return b"not-json"
            return data

        def flock(fd, op):
            if fault == "flock" and op & fcntl.LOCK_EX:
                trigger()
            return original_flock(fd, op)

        monkeypatch.setattr(module, "_write", write)
        monkeypatch.setattr(Path, "open", opening)
        monkeypatch.setattr(Path, "mkdir", mkdir)
        monkeypatch.setattr(Path, "glob", glob)
        monkeypatch.setattr(Path, "read_bytes", read)
        monkeypatch.setattr(fcntl, "flock", flock)
        if fault == "fsync":
            original_sync = module.os.fsync

            def sync(fd):
                trigger()
                return original_sync(fd)

            monkeypatch.setattr(module.os, "fsync", sync)

    _, _, root, _, state = recorded_suite(tmp_path, monkeypatch, setup_hook=hook)
    assert fired, fault
    assert state.calls == fired[0]
    assert state.reports[0].get("status") != "COMPLETED"
    with (root / "group.lock").open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(stream, fcntl.LOCK_UN)


def test_r561_complete_cpu_raw_positive_and_absence_pass_strictly(complete_cpu_disk):
    module, cases, root, registry, state = complete_cpu_disk
    results = [row for report in state.reports for row in report.get("results", [])]
    summary = checked_summary(module, registry, results, root)
    assert summary["all_cases_pass"]
    assert (summary["positive_passed"], summary["negative_passed"]) == (3, 4)
    for case in cases:
        events = module.RunLedger(root, registry).events_for(case.case_id)
        result = checked_classify(
            module, case, saved_response(module, root, case), events, root, registry
        )
        assert result["passed"]
    assert hasattr(module, "validate_case_evidence") and hasattr(module, "validate_group_evidence")


@pytest.mark.parametrize(
    "kind",
    [
        "capture",
        "native_text",
        "native_tokens",
        "native_result",
        "cloud",
        "pipeline",
        "case_manifest",
        "group_manifest",
        "group_end",
        "reservation",
        "start",
        "end",
        "seal",
    ],
)
def test_r561_missing_original_file_invalidates_case_or_suite(complete_cpu_disk, kind):
    module, _, root, registry, state = complete_cpu_disk
    choices = {
        "capture": "G1/P01/capture-01/depth.f32",
        "native_text": "G1/native/request-0003/raw-response.txt",
        "native_tokens": "G1/native/request-0003/output-token-ids.json",
        "native_result": "G1/native/request-0003/result.json",
        "cloud": "G1/P01/cloud/response-0001.json",
        "pipeline": "G1/P01/pipeline-return.json",
        "case_manifest": "G1/P01/case-evidence.manifest.json",
        "group_manifest": "G1/raw-manifest.local.json",
        "group_end": "G1/group-end.json",
        "reservation": "reservations/point-001.json",
        "start": "claims/case-N01-start.json",
        "end": "claims/case-N01-end.json",
        "seal": "registry.sha256",
    }
    path = root / choices[kind]
    assert path.exists(), f"complete CPU raw missing {kind} before mutation"
    original = path.read_bytes()
    results = [row for report in state.reports for row in report.get("results", [])]
    assert checked_summary(module, registry, results, root)["all_cases_pass"]
    try:
        path.unlink()
        summary = checked_summary(module, registry, results, root)
        assert not summary["all_cases_pass"]
        assert summary["total_cases"] == 7
    finally:
        path.write_bytes(original)


def test_r561_summary_never_accepts_only_seven_verdict_strings(tmp_path):
    module, _, root, registry, _ = setup_run(tmp_path)
    rows = [
        {
            "case_id": c["case_id"],
            "group_id": c["group_id"],
            "expected": c["expected"],
            "verdict": "PASS_PLANNED" if c["expected"] == "positive" else "PASS_EXPECTED_REJECTION",
            "passed": False,
        }
        for c in registry["cases"]
    ]
    result = checked_summary(module, registry, rows, root)
    assert not result["all_cases_pass"]
    assert result["passed_cases"] == 0


@pytest.fixture(scope="module")
def complete_cpu_disk(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        return recorded_suite(
            tmp_path_factory.mktemp("r561-full-disk"), patch, groups=("G1", "G2", "G3")
        )


def test_r561_allowed_original_geometry_refusal_has_complete_cpu_evidence(tmp_path, monkeypatch):
    _, _, _, _, state = recorded_suite(tmp_path, monkeypatch, negative_mode="POINT", damage="decoy")
    row = next(r for r in state.reports[0]["results"] if r["case_id"] == "N02")
    assert row["passed"] and row["refusal_source"] == "program_geometry", row


@pytest.mark.parametrize("field", ["source", "episode", "calibration", "ttl"])
def test_r561_original_context_fault_never_counts_as_expected_scene_refusal(
    tmp_path, monkeypatch, field
):
    from datetime import timedelta

    from tests.test_molmo_revalidation import rebuild

    def transform(observation):
        changes = {
            "source": {"source": "rgbd_camera"},
            "episode": {"episode_id": ""},
            "calibration": {"calibration_version": ""},
            "ttl": {"captured_at": datetime.now(UTC) - timedelta(seconds=6)},
        }
        return rebuild(observation, **changes[field])

    _, _, _, _, state = recorded_suite(tmp_path, monkeypatch, capture_transform=transform)
    assert state.calls == 0
    assert all(not row["passed"] for row in state.reports[0]["results"])


def test_r561_ledger_mkdir_failure_is_irreversible_poison(tmp_path, monkeypatch):
    from pathlib import Path

    module, _, root, _, ledger = setup_run(tmp_path)
    ledger.claim("G1")
    original = Path.mkdir

    def mkdir(path, *args, **kwargs):
        if path == root / "events/N01":
            raise OSError("CPU ledger mkdir failure")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", mkdir)
        with pytest.raises(OSError):
            ledger.record("N01", kind="runtime_error")
    assert ledger.fatal
    first = ledger.stop_reason
    ledger.poison("later failure")
    assert ledger.stop_reason == first
    with pytest.raises(RuntimeError):
        ledger.reserve("load", group_id="G1", case_id=None)
    ledger.close()


@pytest.mark.parametrize("phase", ["REQUEST", "RESPONSE"])
def test_r561_wire_persistence_fault_is_fatal_and_preserves_reservation(
    tmp_path, monkeypatch, phase
):
    from pathlib import Path

    fired = []

    def hook(module, state, root, registry):
        original = Path.open

        def opening(path, *args, **kwargs):
            if (
                path.name == f"{phase.lower()}-0001.json"
                and path.parent.name == "cloud"
                and not fired
            ):
                fired.append(state.calls)
                raise OSError("CPU wire persistence failure")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", opening)

    _, _, root, _, state = recorded_suite(tmp_path, monkeypatch, setup_hook=hook)
    assert fired and state.calls == fired[0]
    assert state.reports[0]["status"] == "INCOMPLETE"
    assert len(list((root / "reservations").glob("paid-*.json"))) == 1


def test_r561_invalid_native_return_is_a_case_failure_without_reusing_budget(tmp_path, monkeypatch):
    _, _, root, _, state = recorded_suite(tmp_path, monkeypatch, negative_mode="INVALID")
    assert state.case_index == 3
    assert state.reports[0]["status"] == "COMPLETED"
    assert [r["passed"] for r in state.reports[0]["results"]] == [False, False, True]
    assert len(list((root / "reservations").glob("point-*.json"))) == 6


def test_r561_actual_summary_cli_rejects_verdict_only_root(tmp_path, capsys):
    import json

    module, _, root, registry, _ = setup_run(tmp_path)
    for case in registry["cases"]:
        path = root / case["group_id"] / f"result-{case['case_id']}.json"
        module._write(
            path,
            {
                "case_id": case["case_id"],
                "group_id": case["group_id"],
                "expected": case["expected"],
                "passed": False,
                "verdict": "PASS_PLANNED"
                if case["expected"] == "positive"
                else "PASS_EXPECTED_REJECTION",
            },
        )
    status = module.main(
        ["summarize", "--registry", str(root / "registry.json"), "--output", str(root)]
    )
    assert status == 2
    assert json.loads(capsys.readouterr().out)["all_cases_pass"] is False
    assert not (root / "raw-manifest.local.json").exists()


def reseal_hashes_for_structural_test(module, root, backup):
    """Challenge semantic checks even when producer-side file hashes are consistent."""
    import json

    for path in sorted((root / "events").rglob("*.json")):
        data = json.loads(path.read_bytes())
        updated = [module._ref(root, root / ref["path"]) for ref in data.get("raw_refs", [])]
        if updated != data.get("raw_refs", []):
            backup.setdefault(path, path.read_bytes())
            data["raw_refs"] = updated
            path.write_bytes(module._canonical(data))
    manifests = [
        *sorted(root.glob("G*/*/case-evidence.manifest.json")),
        *sorted(root.glob("G*/raw-manifest.local.json")),
    ]
    for path in manifests:
        backup.setdefault(path, path.read_bytes())
        data = json.loads(path.read_bytes())
        data["files"] = [module._ref(root, root / ref["path"]) for ref in data["files"]]
        path.write_bytes(module._canonical(data))


@pytest.mark.parametrize(
    "mutation",
    [
        "unclosed",
        "duplicate_end",
        "unknown_op",
        "query",
        "same_frame",
        "native_token",
        "native_parse",
        "verdict",
    ],
)
def test_r561_consistent_hashes_do_not_hide_structural_contradictions(complete_cpu_disk, mutation):
    import json
    import uuid

    module, _, root, registry, state = complete_cpu_disk
    originals = {}
    added = []
    results = [row.copy() for report in state.reports for row in report["results"]]
    assert checked_summary(module, registry, results, root)["all_cases_pass"]

    def change(path, data):
        originals.setdefault(path, path.read_bytes())
        path.write_bytes(module._canonical(data))

    events = sorted((root / "events/P01").glob("*.json"))
    loaded = [(p, json.loads(p.read_bytes())) for p in events]
    point_starts = [(p, e) for p, e in loaded if e["kind"] == "point" and e["phase"] == "start"]
    point_ends = [(p, e) for p, e in loaded if e["kind"] == "point" and e["phase"] == "end"]
    try:
        if mutation in {"unclosed", "duplicate_end"}:
            event = dict(point_starts[0][1] if mutation == "unclosed" else point_ends[0][1])
            event["seq"] = len(events) + 1
            if mutation == "unclosed":
                event["op_id"] = uuid.uuid4().hex
            path = events[0].parent / f"{len(events) + 1:04}.json"
            path.write_bytes(module._canonical(event))
            added.append(path)
            for manifest in (
                root / "G1/P01/case-evidence.manifest.json",
                root / "G1/raw-manifest.local.json",
            ):
                data = json.loads(manifest.read_bytes())
                data["files"].append(module._ref(root, path))
                change(manifest, data)
        elif mutation == "query":
            path, event = point_starts[0]
            event["query"] = "interior of wrong region"
            change(path, event)
        elif mutation == "unknown_op":
            for path, event in (point_starts[0], point_ends[0]):
                event["kind"] = "invented_operation"
                change(path, event)
        elif mutation == "same_frame":
            captures = [(p, e) for p, e in loaded if e["kind"] == "capture" and e["phase"] == "end"]
            path, event = captures[1]
            event["observation_checksum"] = captures[0][1]["observation_checksum"]
            change(path, event)
        elif mutation == "native_token":
            change(root / "G1/native/request-0003/output-token-ids.json", ["invalid-token"])
        elif mutation == "native_parse":
            path = root / "G1/native/request-0003/result.json"
            data = json.loads(path.read_bytes())
            data["native"]["status"] = "ABSENT"
            change(path, data)
        elif mutation == "verdict":
            path = root / "G1/result-P01.json"
            data = json.loads(path.read_bytes())
            data["passed"] = False
            change(path, data)
            next(r for r in results if r["case_id"] == "P01")["passed"] = False
            path = root / "G1/group-end.json"
            data = json.loads(path.read_bytes())
            next(r for r in data["results"] if r["case_id"] == "P01")["passed"] = False
            change(path, data)
        reseal_hashes_for_structural_test(module, root, originals)
        result = checked_summary(module, registry, results, root)
        assert not result["all_cases_pass"], result
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
        for path in added:
            path.unlink()


@pytest.mark.parametrize("namespace", ["reservation", "claim", "event", "group"])
def test_r561_unregistered_accounting_namespace_invalidates_suite(complete_cpu_disk, namespace):
    import json

    module, _, root, registry, state = complete_cpu_disk
    results = [row for report in state.reports for row in report["results"]]
    assert checked_summary(module, registry, results, root)["all_cases_pass"]
    choices = {
        "reservation": root / "reservations/extra-001.json",
        "claim": root / "claims/case-EXTRA-start.json",
        "event": root / "events/EXTRA/0001.json",
        "group": root / "G9/result-EXTRA.json",
    }
    path = choices[namespace]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"case_id": "EXTRA", "kind": "unregistered_operation"}))
    try:
        summary = checked_summary(module, registry, results, root)
        assert not summary["all_cases_pass"]
    finally:
        path.unlink()
        if namespace in {"event", "group"}:
            path.parent.rmdir()
