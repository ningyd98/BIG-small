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


def _new_observation(obs, **updates):
    from datetime import timedelta

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    payload = obs.model_dump()
    payload.update(
        observation_id=obs.observation_id + "-fresh",
        frame_id=obs.frame_id + "-fresh",
        captured_at=obs.captured_at + timedelta(milliseconds=100),
        checksum_sha256="",
    )
    payload.update(updates)
    return RGBDObservation.model_validate(payload)


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
    current = _new_observation(obs)
    fresh = _new_observation(current)
    for index, phrase in enumerate(("red", "green", "red", "green")):
        phase_observation = current if index < 2 else fresh
        bound = provider.point(phase_observation, phrase)
        assert bound.observation_checksum == phase_observation.checksum_sha256
        assert bound.evidence["historical_observation_checksum"] == obs.checksum_sha256
        assert bound.evidence["scope"] == "OFFLINE_FROZEN_OUTPUT_REPLAY"
    assert provider.replay_calls == 4
    assert provider.model_loads_started == provider.generation_calls_started == 0
    assert provider.generation_calls_completed == 0
    with pytest.raises(ValueError, match="BUDGET"):
        provider.point(current, "red")


def test_point_phase_rejects_reused_before_without_consuming_or_polluting_state(frozen):
    case, obs, _, _ = frozen
    provider = FrozenPointProvider(case)
    provider.point(obs, "red")
    provider.point(obs, "green")
    with pytest.raises(ValueError, match="PHASE"):
        provider.point(obs, "red")
    assert provider.replay_calls == len(provider.records) == 2
    fresh = _new_observation(obs)
    provider.point(fresh, "red")
    provider.point(fresh.model_copy(), "green")
    assert provider.replay_calls == 4


@pytest.mark.parametrize("index", [2, 4])
def test_point_same_phase_requires_same_observation_identity(frozen, index):
    case, obs, _, _ = frozen
    provider = FrozenPointProvider(case)
    provider.point(obs, "red")
    if index == 4:
        provider.point(obs, "green")
        obs = _new_observation(obs)
        provider.point(obs, "red")
    with pytest.raises(ValueError, match="PHASE"):
        provider.point(_new_observation(obs), "green")
    assert provider.replay_calls == len(provider.records) == index - 1
    provider.point(obs, "green")


@pytest.mark.parametrize("field", ["ids", "captured_at"])
def test_point_post_cloud_requires_new_ids_and_later_capture(frozen, field):
    case, obs, _, _ = frozen
    provider = FrozenPointProvider(case)
    provider.point(obs, "red")
    provider.point(obs, "green")
    updates = (
        {"observation_id": obs.observation_id, "frame_id": obs.frame_id}
        if field == "ids"
        else {"captured_at": obs.captured_at}
    )
    candidate = _new_observation(obs, **updates)
    assert candidate.observation_id == candidate.frame_id
    assert candidate.checksum_sha256 != obs.checksum_sha256
    if field == "ids":
        assert candidate.observation_id == obs.observation_id
        assert candidate.captured_at > obs.captured_at
    else:
        assert candidate.captured_at == obs.captured_at
    with pytest.raises(ValueError, match="FROZEN_POINT_PHASE_REFRESH_REQUIRED"):
        provider.point(candidate, "red")
    assert provider.replay_calls == len(provider.records) == 2


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


@pytest.mark.parametrize(
    "damage", ["trim8", "remove", "duplicate", "replace", "path", "sha", "bytes", "archive"]
)
def test_baseline_snapshot_bytes_are_anchored_before_trusting_members(tmp_path, damage):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import PROCESS, _read_baseline

    data = json.loads((PROCESS / "v3-baseline/snapshot.json").read_bytes())
    members = data["source_mapping"]
    if damage == "trim8":
        data["source_mapping"] = members[:8]
    elif damage == "remove":
        members.pop()
    elif damage == "duplicate":
        members.append(members[0])
    elif damage == "replace":
        members[-1] = dict(members[0])
    elif damage == "archive":
        data["source_archive_sha256"] = "a" * 64
    else:
        key = {"path": "archive_member", "sha": "sha256", "bytes": "bytes"}[damage]
        members[0][key] = 1 if key == "bytes" else "tampered"
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="BASELINE_SNAPSHOT_HASH_MISMATCH"):
        _read_baseline(path)


@pytest.mark.parametrize(
    "name", ["shield.py", "skill_robot.py", "asset.xml", "offline.py", "runner.py", "test.py"]
)
@pytest.mark.parametrize("damage", ["edit", "delete", "symlink"])
def test_complete_source_postcheck_rejects_any_member_or_entry_change(tmp_path, name, damage):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
        _capture_inventory,
        _verify_inventory,
    )

    path = tmp_path / name
    path.write_bytes(b"original")
    inventory = _capture_inventory([path])
    _verify_inventory(inventory)
    if damage == "edit":
        path.write_bytes(b"changed")
    elif damage == "delete":
        path.unlink()
    else:
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"original")
        path.unlink()
        path.symlink_to(replacement)
    with pytest.raises(ValueError, match="SOURCE_INVENTORY_CHANGED"):
        _verify_inventory(inventory)


def test_output_guard_covers_direct_file_writes_and_symlink_parents(tmp_path):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
        PROCESS,
        _write,
        output_path,
    )

    with pytest.raises(ValueError, match="OUTPUT"):
        output_path(Path("/home/ningyd/unauthorized-offline-result.json"))
    with pytest.raises(ValueError, match="OUTPUT"):
        output_path(Path("/tmp"))
    with pytest.raises(ValueError, match="PROTECTED"):
        _write(PROCESS / "v3-baseline/new.json", {})
    source = tmp_path / "source"
    source.mkdir()
    link = tmp_path / "link"
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match="PROTECTED"):
        output_path(link / "new.json", [source])
    with pytest.raises(ValueError, match="PROTECTED"):
        output_path(source / "new.json", [source])
    assert not (source / "new.json").exists()


def test_current_audit_protects_source_directories_and_allows_both_approved_outputs(
    tmp_path, monkeypatch
):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
        PROCESS,
        ROOT,
        _audit_protected_roots,
        output_path,
    )

    protected = _audit_protected_roots(ROOT)
    assert ROOT not in protected
    for name in ("src", "assets", "scripts", "tests"):
        assert ROOT / name in protected
    output_path(PROCESS / "offline-regression/path-validator-only/current.json", protected)
    output_path(tmp_path / "current.json", protected)
    from cloud_edge_robot_arm.research import sol_molmo_offline_regression as regression

    monkeypatch.setattr(regression, "_PROTECTED_INPUTS", set(regression._PROTECTED_INPUTS))
    regression._PROTECTED_INPUTS.update(protected)
    output_path(PROCESS / "offline-regression/path-validator-only/current.json")
    output_path(tmp_path / "current.json")
    assert not (PROCESS / "offline-regression/path-validator-only/current.json").exists()
    assert not (tmp_path / "current.json").exists()
    with pytest.raises(ValueError, match="PROTECTED"):
        output_path(ROOT / "src/forbidden.json", protected)


def test_historical_audit_protects_entire_source_tree_after_resolving_alias(tmp_path):
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import (
        _audit_protected_roots,
        output_path,
    )

    historical = tmp_path / "historical"
    historical.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(historical, target_is_directory=True)
    protected = _audit_protected_roots(alias)
    assert historical.resolve() in protected
    with pytest.raises(ValueError, match="PROTECTED"):
        output_path(alias / "new.json", protected)
    output_path(tmp_path / "new-output.json", protected)


def test_network_guard_covers_preexisting_thread_nested_context_and_cleanup():
    import sys
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: None).result()
        with NetworkDenyGuard() as outer:
            with NetworkDenyGuard() as inner:
                future = executor.submit(sys.audit, "socket.connect", None, ("127.0.0.1", 9))
                with pytest.raises(RuntimeError, match="OFFLINE_NETWORK_DENIED"):
                    future.result()
            with pytest.raises(RuntimeError, match="OFFLINE_NETWORK_DENIED"):
                sys.audit("socket.getaddrinfo", "example.invalid", 9, 0, 0, 0)
        assert len(outer.attempts) == 2
        assert len(inner.attempts) == 1
        executor.submit(sys.audit, "socket.connect", None, ("127.0.0.1", 9)).result()


@pytest.mark.parametrize(
    "damage", [None, "duplicate", "missing", "extra", "link", "traversal", "content"]
)
def test_archive_member_integrity_after_archive_digest_gate(tmp_path, monkeypatch, damage):
    import io
    import tarfile

    from cloud_edge_robot_arm.research import sol_molmo_offline_regression as regression

    rows = [("source/a.txt", b"a"), ("external/b.txt", b"b")]
    snapshot = {
        "source_mapping": [
            {"archive_member": name, "sha256": sha(data), "bytes": len(data)} for name, data in rows
        ]
    }
    path = tmp_path / "source.tar"

    def add(archive, name, data):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))

    with tarfile.open(path, "w") as archive:
        for index, (name, data) in enumerate(rows):
            if index == 1 and damage == "missing":
                continue
            if index == 1 and damage == "link":
                info = tarfile.TarInfo(name)
                info.type = tarfile.SYMTYPE
                info.linkname = "source/a.txt"
                archive.addfile(info)
            else:
                add(archive, name, b"evil" if damage == "content" and index == 1 else data)
        if damage == "duplicate":
            add(archive, *rows[0])
        elif damage in {"extra", "traversal"}:
            add(archive, "../escaped" if damage == "traversal" else "extra", b"extra")
    # 仅此微型夹具固定自身归档摘要，专门覆盖下一层成员验证；真实常量由monkeypatch恢复。
    monkeypatch.setattr(regression, "ARCHIVE_SHA", sha(path.read_bytes()))
    if damage is None:
        regression._verify_archive(snapshot, path)
    else:
        with pytest.raises(ValueError, match="BASELINE_ARCHIVE_MEMBER"):
            regression._verify_archive(snapshot, path)


@pytest.mark.parametrize(
    "operation", ["connect", "connect_ex", "send", "sendall", "sendto", "sendmsg", "dns"]
)
def test_actual_socket_apis_are_denied_before_system_call(operation):
    from concurrent.futures import ThreadPoolExecutor

    if operation == "sendmsg" and not hasattr(socket.socket, "sendmsg"):
        pytest.skip("Python socket.sendmsg unavailable")
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        executor.submit(lambda: None).result()
        calls = {
            "connect": lambda: client.connect(("127.0.0.1", 9)),
            "connect_ex": lambda: client.connect_ex(("127.0.0.1", 9)),
            "send": lambda: client.send(b"guard"),
            "sendall": lambda: client.sendall(b"guard"),
            "sendto": lambda: client.sendto(b"guard", ("127.0.0.1", 9)),
            "sendmsg": lambda: client.sendmsg([b"guard"], [], 0, ("127.0.0.1", 9)),
            "dns": lambda: socket.getaddrinfo("example.invalid", 9),
        }
        with NetworkDenyGuard() as guard:
            future = executor.submit(calls[operation])
            with pytest.raises(RuntimeError, match="OFFLINE_NETWORK_DENIED"):
                future.result()
        assert len(guard.attempts) == 1


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


def test_inventory_finally_preserves_worker_error_and_detects_independent_drift(
    tmp_path, monkeypatch
):
    root = os.environ.get("BIGSMALL_V3_REGRESSION_ROOT")
    if not root:
        pytest.skip("explicit read-only V3 fixture required")
    from cloud_edge_robot_arm.research import sol_molmo_offline_regression as regression
    from cloud_edge_robot_arm.research import sol_molmo_single_episode as single

    baseline = (
        Path(__file__).resolve().parents[1]
        / "artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json"
    )
    manifest = load_v3_manifest(Path(root), baseline)
    protected_fixture = tmp_path / "shield-fixture.py"
    protected_fixture.write_bytes(b"before")
    inventory = regression._capture_inventory([protected_fixture])
    monkeypatch.setattr(regression, "_source_inventory", lambda manifest: inventory)

    def fail(*args, **kwargs):
        protected_fixture.write_bytes(b"after")
        raise RuntimeError("original-worker-error")

    monkeypatch.setattr(single, "run_worker_episode", fail)
    result = run_frozen_component_case("fixed-042001", manifest, tmp_path / "episode")
    assert result["error"] == "original-worker-error"
    assert result["source_bytes_unchanged_after"] is False
    assert result["component_success"] is False
    assert "SOURCE_INVENTORY_CHANGED" in result["integrity_failure"]
    assert (tmp_path / "episode/result.json").is_file()


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
    hard_hits = []
    delegated_pre = []
    post_depth = {}
    injections = {"PRE": 0, "POST": 0, "HARD": 0}
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
    original_pre, original_post = SafetyShield.pre_check, SafetyShield.post_check

    def pre_check(self, context):
        verdict = original_pre(self, context)
        assert verdict.allowed and verdict.evaluated_rules
        if post_depth.get(id(self), 0):
            delegated_pre.append((context, *contexts[id(context)]))
            return verdict
        calls.append(("PRE", *contexts[id(context)]))
        if phase == "PRE":
            injections["PRE"] += 1
            return replace(verdict, allowed=False, decision=SafetyDecision.REJECT)
        return verdict

    def post_check(self, context):
        previous = post_depth.get(id(self), 0)
        post_depth[id(self)] = previous + 1
        try:
            verdict = original_post(self, context)
        finally:
            if previous:
                post_depth[id(self)] = previous
            else:
                post_depth.pop(id(self))
        assert verdict.allowed and verdict.evaluated_rules
        calls.append(("POST", *contexts[id(context)], context))
        if phase == "POST":
            injections["POST"] += 1
            return replace(verdict, allowed=False, decision=SafetyDecision.REJECT)
        return verdict

    monkeypatch.setattr(SafetyShield, "pre_check", pre_check)
    monkeypatch.setattr(SafetyShield, "post_check", post_check)
    if phase == "HARD":

        def hard(backend, robot):
            hard_hits.append(backend.total_physics_steps)
            injections["HARD"] += 1
            raise components.ComponentStopped("INJECTED_HARD_STATE")

        monkeypatch.setattr(components, "check_component_hard_state", hard)
    manifest = load_v3_manifest(
        Path(root),
        Path(__file__).resolve().parents[1]
        / "artifacts/research/process/20261115-v4-marker-ambiguity/v3-baseline/snapshot.json",
    )
    result = run_frozen_component_case("fixed-042001", manifest, tmp_path / "episode")
    assert post_depth == {}
    _assert_reached_safety_boundary(result, phase, calls, hard_hits, delegated_pre, injections)


def _assert_reached_safety_boundary(
    result, phase, calls, hard_hits, delegated_pre=(), injections=None
):
    assert result["component_success"] is False
    assert result["worker_status"] == "FAILED"
    assert result["point_replays"] == 4 and result["cloud_replays"] == 1
    assert result["model_loads_started"] == result["generation_calls_started"] == 0
    assert result["generation_calls_completed"] == result["cloud_requests"] == 0
    assert result["network_attempts"] == []
    assert result["source_bytes_unchanged_after"] is True
    episode = result["outcome"]
    assert episode["planning_passed"] is True
    assert episode["diagnostic_complete"] is False
    expected = {
        "PRE": "SAFETY_SHIELD_PRE_REJECTED_OR_LIMITED",
        "POST": "SAFETY_SHIELD_POST_REJECTED_OR_LIMITED",
        "HARD": "INJECTED_HARD_STATE",
    }
    assert result["terminal_reason"] == episode["terminal_reason"] == expected[phase]
    labels = [item["label"] for item in episode["marker_frames"]]
    assert "pre-00-move_above" in labels
    assert set(labels) <= {"before", "post-cloud", "pre-00-move_above", "after"}
    assert injections == {name: int(name == phase) for name in ("PRE", "POST", "HARD")}
    if phase == "PRE":
        assert [item[0] for item in calls] == ["PRE"]
        assert len(episode["safety_checks"]) == 1
        assert episode["safety_checks"][0]["verdict"]["allowed"] is False
        assert episode["actions"] == []
        assert episode["executed_actions"] == 0
        assert hard_hits == []
        assert delegated_pre == []
    elif phase == "HARD":
        assert len(hard_hits) == 1
        assert calls == episode["safety_checks"] == episode["actions"] == []
        assert episode["executed_actions"] == 0
        assert delegated_pre == []
    else:
        assert hard_hits == []
        assert [item[0] for item in calls] == ["PRE", "EXECUTE", "POST"]
        assert calls[0][1] is calls[1][1] is calls[2][1]
        assert calls[0][2] is calls[1][2] is calls[2][2]
        assert len(delegated_pre) == 1
        assert delegated_pre[0][0] is calls[2][3]
        assert delegated_pre[0][1] is calls[2][1]
        assert delegated_pre[0][2] is calls[2][2]
        assert [check["verdict"]["allowed"] for check in episode["safety_checks"]] == [True, False]
        assert len(episode["actions"]) == episode["executed_actions"] == 1
        assert "diagnostic_settle_steps" not in episode["actions"][0]
        assert episode["actions"][0]["end_step"] == episode["actions"][0]["controller_return_step"]


@pytest.mark.parametrize("index,phase", [(0, "PRE"), (1, "POST"), (2, "HARD")])
def test_early_planning_failure_cannot_pass_safety_boundary_acceptance(index, phase):
    root = Path(__file__).resolve().parents[1]
    evidence = root / "artifacts/research/process/20261004-ced-development/astra-rounds"
    path = evidence / "round-v3-offline-safety-boundary-environment-20261115/evidence/failed-faults"
    result = json.loads((path / str(index) / "result.json").read_bytes())
    with pytest.raises(AssertionError):
        _assert_reached_safety_boundary(result, phase, [], [])
