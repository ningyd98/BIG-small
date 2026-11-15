"""离线输出边界必须严格绑定，实际执行仍由原worker及安全门禁负责。"""

from __future__ import annotations

import hashlib
import json
import os
import socket
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
    FrozenCase,
    FrozenCloudReplayAdapter,
    FrozenPointProvider,
    NetworkDenyGuard,
    load_v3_manifest,
    new_output,
    run_frozen_component_case,
    validate_source_imports,
)
from tests.test_molmo_grounded_planner import request_scene


def sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def frozen(tmp_path):
    obs = request_scene().observation
    files = {}

    def put(name, value):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = {"path": name, "sha256": sha(data), "bytes": len(data)}

    for folder in ("before", "component/frames/post-cloud"):
        put(folder + "/observation.json", obs.model_dump(mode="json") | obs.evidence())
    from cloud_edge_robot_arm.vision.molmo_pointing import parse_native_point

    for i, phrase in enumerate(["red", "green", "red", "green"], 1):
        folder = f"raw/molmo/request-{i:04d}/"
        raw = f'<points coords="1 1 200 400">{phrase}</points><|im_end|>'
        started = {
            "observation_checksum": obs.checksum_sha256,
            "rgb_sha256": obs.evidence()["rgb_sha256"],
            "query_sha256": sha(phrase.encode()),
            "phrase": phrase,
        }
        put(folder + "started.json", started)
        put(folder + "raw-response.txt", raw.encode())
        put(
            folder + "result.json",
            started
            | {
                "raw_sha256": sha(raw.encode()),
                "native": asdict(parse_native_point(raw)),
                "output_tokens": 32,
                "reached_cap": False,
            },
        )
    body = {"model": "gpt-6.1-sol", "messages": [{"role": "user", "content": "geometry:0.451"}]}
    put("raw/cloud/request.json", body)
    put("raw/cloud/response.json", {"choices": [{"message": {"content": "frozen"}}]})
    return FrozenCase(tmp_path, files, {"case": "fixture"}), obs, put, body


def test_point_rebinds_only_identical_input_without_inference(frozen):
    case, obs, _, _ = frozen
    provider = FrozenPointProvider(case)
    current = obs.model_copy(update={"checksum_sha256": "a" * 64})
    for phrase in ("red", "green", "red", "green"):
        bound = provider.point(current, phrase)
        assert bound.observation_checksum == current.checksum_sha256
        assert bound.evidence["historical_observation_checksum"] == obs.checksum_sha256
        assert bound.evidence["scope"] == "OFFLINE_FROZEN_OUTPUT_REPLAY"
    assert provider.replay_calls == 4
    assert provider.model_loads_started == provider.generation_calls_started == 0
    assert provider.generation_calls_completed == 0
    with pytest.raises(ValueError, match="BUDGET"):
        provider.point(current, "red")


@pytest.mark.parametrize(
    "change", ["phrase", "rgb", "calibration", "intrinsics", "phase", "raw", "query"]
)
def test_point_rejects_wrong_input_before_consumption(frozen, change):
    case, obs, put, _ = frozen
    phrase = "red"
    if change == "phrase":
        phrase = "green"
    elif change == "rgb":
        from tests.test_molmo_grounded_planner import request_scene

        obs = request_scene(damage="occluded").observation
    elif change == "calibration":
        obs = obs.model_copy(update={"calibration_version": "wrong"})
    elif change == "intrinsics":
        obs = obs.model_copy(update={"intrinsics": (300, 300, 10, 10)})
    elif change == "phase":
        meta = case.json("component/frames/post-cloud/observation.json")
        meta["sim_time_s"] = 9
        put("component/frames/post-cloud/observation.json", meta)
    elif change == "raw":
        (case.root / "raw/molmo/request-0001/raw-response.txt").write_text("tampered")
    else:
        name = "raw/molmo/request-0001/started.json"
        put(name, case.json(name) | {"query_sha256": "b" * 64})
    provider = FrozenPointProvider(case)
    if change == "phase":
        provider.point(obs, "red")
        provider.point(obs, "green")
    before = provider.replay_calls
    with pytest.raises(ValueError):
        provider.point(obs, phrase)
    assert provider.replay_calls == before


@pytest.mark.parametrize("change", ["message", "model", "number", "path"])
def test_cloud_rejects_any_full_request_change(frozen, change):
    case, _, _, body = frozen
    cloud = FrozenCloudReplayAdapter(
        case,
        base_url="https://api.openai.com/v1",
        model="gpt-6.1-sol",
        provider="openai_compatible",
        allow_paid=True,
    )
    path = "/chat/completions"
    if change == "message":
        body["messages"].append({"role": "user", "content": "extra"})
    elif change == "model":
        body["model"] = "other"
    elif change == "number":
        body["messages"][0]["content"] = "geometry:0.452"
    else:
        path = "/v1/chat/completions"
    with pytest.raises(ValueError, match="FROZEN_CLOUD_REQUEST_MISMATCH"):
        cloud._post(path, body)
    assert cloud.replay_calls == 0


def test_cloud_is_local_bounded_deep_copy_with_empty_ledger(frozen):
    case, _, _, body = frozen
    from cloud_edge_robot_arm.research.cost_ledger import CostLedger

    ledger = CostLedger()
    cloud = FrozenCloudReplayAdapter(
        case,
        base_url="https://api.openai.com/v1",
        model="gpt-6.1-sol",
        provider="openai_compatible",
        allow_paid=True,
        cost_ledger=ledger,
    )
    with NetworkDenyGuard() as guard:
        response = cloud._post("/chat/completions", body)
    response["choices"].clear()
    assert case.json("raw/cloud/response.json")["choices"]
    assert guard.attempts == []
    assert ledger.snapshot().cloud_model_requests == 0
    with pytest.raises(ValueError, match="BUDGET"):
        cloud._post("/chat/completions", body)


def test_network_guard_stops_actual_socket_before_connection():
    with NetworkDenyGuard() as guard, socket.socket() as client:
        with pytest.raises(RuntimeError, match="OFFLINE_NETWORK_DENIED"):
            client.connect(("127.0.0.1", 9))
    assert len(guard.attempts) == 1


def test_frozen_case_rejects_escape_duplicate_and_byte_change(frozen):
    case, _, _, _ = frozen
    with pytest.raises(ValueError):
        case.read("../outside")
    path = case.root / "raw/cloud/request.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="HASH"):
        case.read("raw/cloud/request.json")


def test_output_is_exclusive_and_protected(tmp_path):
    frozen_root = tmp_path / "frozen"
    frozen_root.mkdir()
    with pytest.raises(ValueError, match="PROTECTED"):
        new_output(frozen_root / "new", [frozen_root])
    out = tmp_path / "out"
    new_output(out, [frozen_root])
    with pytest.raises(FileExistsError):
        new_output(out, [frozen_root])


def test_source_pin_rejects_other_checkout():
    with pytest.raises(ValueError, match="SOURCE_IMPORT_MISMATCH"):
        validate_source_imports(Path("/tmp/wrong-source"), {})


def test_fixed_worker_binding_preserves_absent_component_scene(tmp_path):
    root = os.environ.get("BIGSMALL_V3_REGRESSION_ROOT")
    if not root:
        pytest.skip("explicit read-only V3 fixture required")
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import build_frozen_worker

    manifest = load_v3_manifest(
        Path(root),
        Path(__file__).resolve().parents[1]
        / "artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json",
    )
    worker, binding, points, cloud = build_frozen_worker(
        manifest.cases["fixed-042001"], manifest, tmp_path
    )
    assert "component_scene" not in binding.evidence()["edge_policy"]
    assert points.replay_calls == cloud.replay_calls == worker.calls == 0


def _scene_case(frozen, split):
    case, _, put, _ = frozen
    seed = {"fixed": 42001, "development": 43001, "held-out": 44001}[split]
    assignment = {
        "seed": seed,
        "scenario_id": "S01_NORMAL_STATIC",
        "scene_sampling": "FIXED_REGISTERED_SCENE",
        "independent_random_scene": False,
    }
    policy = {}
    if split != "fixed":
        from cloud_edge_robot_arm.research.sol_molmo_scenarios import sample_component_scene

        assignment.update(
            scene_sampling="SEEDED_COMPONENT_POSE_V1",
            independent_random_scene=True,
            component_scene=sample_component_scene(seed, split),
        )
        policy["component_scene"] = assignment["component_scene"]
    case.row.update(seed=seed, split=split)
    put("scene-assignment.json", assignment)
    put("role-binding.json", {"edge_policy": policy})
    put("worker/job.json", {"seed": seed, "scenario_id": "S01_NORMAL_STATIC"})
    return case, put


@pytest.mark.parametrize("split", ["fixed", "development", "held-out"])
def test_component_scene_restores_exact_optional_semantics(frozen, split):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
        _validated_component_scene,
    )

    case, _ = _scene_case(frozen, split)
    scene = _validated_component_scene(case)
    assert scene == case.json("scene-assignment.json").get("component_scene")


@pytest.mark.parametrize(
    "change",
    [
        "fixed_null",
        "fixed_empty",
        "fixed_fake",
        "seeded_missing",
        "seeded_null",
        "role_difference",
        "seed",
        "split",
        "job",
        "sampling",
        "flag",
    ],
)
def test_component_scene_rejects_fabrication_or_binding_drift(frozen, change):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
        _validated_component_scene,
    )

    case, put = _scene_case(frozen, "fixed" if change.startswith("fixed_") else "development")
    assignment = case.json("scene-assignment.json")
    if change.startswith("fixed_"):
        assignment["component_scene"] = {
            "fixed_null": None,
            "fixed_empty": {},
            "fixed_fake": {"seed": 42001},
        }[change]
    elif change == "seeded_missing":
        del assignment["component_scene"]
    elif change == "seeded_null":
        assignment["component_scene"] = None
    elif change == "role_difference":
        put("role-binding.json", {"edge_policy": {"component_scene": {}}})
    elif change == "seed":
        assignment["seed"] = True
    elif change == "split":
        assignment["component_scene"]["split"] = "held-out"
    elif change == "job":
        put("worker/job.json", {"seed": 43002, "scenario_id": "S01_NORMAL_STATIC"})
    elif change == "sampling":
        assignment["scene_sampling"] = "unknown"
    else:
        assignment["independent_random_scene"] = False
    put("scene-assignment.json", assignment)
    with pytest.raises(ValueError, match="COMPONENT_SCENE"):
        _validated_component_scene(case)


@pytest.mark.parametrize("skill", ["MOVE_ABOVE", "APPROACH"])
def test_unknown_mixed_ids_cannot_supply_missing_grasp_geometry(monkeypatch, skill):
    components, tracker, evidence, state, observation = _unknown_grounding_fixture(monkeypatch)
    with pytest.raises(components.ComponentStopped, match="CURRENT_GRASP_GEOMETRY_UNAVAILABLE"):
        components._ground_component(
            observation, tracker, evidence, "side_y_plus_id7_75mm_component_v1", skill, state
        )


@pytest.mark.parametrize("skill", ["LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE"])
def test_transport_unknown_requires_real_closed_holding_feedback(monkeypatch, skill):
    components, tracker, evidence, state, observation = _unknown_grounding_fixture(monkeypatch)
    with pytest.raises(components.ComponentStopped, match="COMPONENT_GRASP_FEEDBACK_LOST"):
        components._ground_component(
            observation, tracker, evidence, "side_y_plus_id7_75mm_component_v1", skill, state
        )
    state = state.model_copy(update={"gripper_open": False, "holding_object_id": "object"})
    _, audit = components._ground_component(
        observation, tracker, evidence, "side_y_plus_id7_75mm_component_v1", skill, state
    )
    assert (
        audit["target_source"]
        == "VISIBLE_SUPPORT_AND_COMPONENT_PROPRIOCEPTION_NO_EXTENT_CERTIFICATE"
    )


def test_retreat_unknown_after_release_is_allowed_by_existing_geometry_policy(monkeypatch):
    components, tracker, evidence, state, observation = _unknown_grounding_fixture(monkeypatch)
    _, audit = components._ground_component(
        observation, tracker, evidence, "side_y_plus_id7_75mm_component_v1", "RETREAT", state
    )
    assert audit["formal_geometry_qualification"] == "UNKNOWN"


def test_complete_geometry_takes_over_when_marker_is_unknown(monkeypatch):
    components, tracker, evidence, state, observation = _unknown_grounding_fixture(monkeypatch)
    tracker._geometry = lambda *args, **kwargs: ({"center": [0.4, 0.1, 0.06]}, None)
    _, audit = components._ground_component(
        observation, tracker, evidence, "side_y_plus_id7_75mm_component_v1", "APPROACH", state
    )
    assert audit["target_source"] == "CURRENT_OPENCV_RGBD_COMPLETE_SUPPORT"


def _unknown_grounding_fixture(monkeypatch):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.research import sol_molmo_components as components

    observation = request_scene().observation
    tracker = SimpleNamespace(
        target_color=None,
        destination_color=None,
        destination=None,
        initial={"center": [0.4, 0.1, 0.06]},
        _geometry=lambda *args, **kwargs: (None, "INCOMPLETE_SUPPORT"),
    )
    monkeypatch.setattr(
        components,
        "detect_pose_marker",
        lambda *args, **kwargs: SimpleNamespace(status="UNKNOWN", observed_marker_ids=(0, 7)),
    )
    monkeypatch.setattr(
        components,
        "_visible_support",
        lambda *args, **kwargs: (None, {"status": "VISIBLE_COLOR_SUPPORT_ONLY"}),
    )
    return components, tracker, {"resolved_top_grasp_tcp": {"z": 0.04}}, RobotState(), observation


@pytest.mark.parametrize("phase", ["PRE", "POST", "HARD"])
def test_actual_worker_stops_at_injected_safety_boundary(tmp_path, monkeypatch, phase):
    root = os.environ.get("BIGSMALL_V3_REGRESSION_ROOT")
    if not root:
        pytest.skip("explicit read-only V3 fixture required")
    from cloud_edge_robot_arm.contracts import SafetyDecision
    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.safety.context_builder import SafetyContextBuilder
    from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
    from cloud_edge_robot_arm.research import sol_molmo_components as components

    calls = []
    contexts = {}
    original_build = SafetyContextBuilder.build

    def build(self, **kwargs):
        context = original_build(self, **kwargs)
        contexts[id(context)] = (kwargs["contract"], kwargs["step"])
        return context

    monkeypatch.setattr(SafetyContextBuilder, "build", build)
    original_execute = SkillExecutor.execute_attempt

    def execute(self, **kwargs):
        calls.append(("EXECUTE", kwargs["contract"], kwargs["step"]))
        return original_execute(self, **kwargs)

    monkeypatch.setattr(SkillExecutor, "execute_attempt", execute)
    for method, label in (("pre_check", "PRE"), ("post_check", "POST")):
        original = getattr(SafetyShield, method)

        def check(self, context, original=original, label=label):
            verdict = original(self, context)
            calls.append((label, *contexts[id(context)]))
            return (
                replace(verdict, allowed=False, decision=SafetyDecision.REJECT)
                if phase == label
                else verdict
            )

        monkeypatch.setattr(SafetyShield, method, check)
    if phase == "HARD":

        def hard(backend, robot):
            raise components.ComponentStopped("INJECTED_HARD_STATE")

        monkeypatch.setattr(components, "check_component_hard_state", hard)
    manifest = load_v3_manifest(
        Path(root),
        Path(__file__).resolve().parents[1]
        / "artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json",
    )
    result = run_frozen_component_case("fixed-042001", manifest, tmp_path / "episode")
    assert result["component_success"] is False
    episode = result["outcome"]
    if phase in {"PRE", "HARD"}:
        assert not any(item[0] == "EXECUTE" for item in calls)
        assert episode["executed_actions"] == 0
    else:
        assert [item[0] for item in calls] == ["PRE", "EXECUTE", "POST"]
        assert calls[0][1] is calls[1][1] is calls[2][1]
        assert calls[0][2] is calls[1][2] is calls[2][2]
        assert "diagnostic_settle_steps" not in episode["actions"][0]
        assert not any(item["label"].startswith("post-00") for item in episode["frames"])
