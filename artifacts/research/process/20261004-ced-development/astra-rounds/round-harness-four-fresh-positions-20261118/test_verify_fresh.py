"""Offline controls for the four-slot independent archive reader."""

import copy
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_fresh as runner
import verify_fresh as audit
from tests.test_opencv_target_evidence import scene

from cloud_edge_robot_arm.harness.config import load_config
from cloud_edge_robot_arm.vision.role_models import configuration_hash
from cloud_edge_robot_arm.vision.servo import save_servo_frame

ROUND = Path(__file__).resolve().parent


@pytest.fixture
def records():
    slot = audit.read_allocation(ROUND / "preallocation.json")["episodes"][0]
    desired = {key: value for key, value in slot.items() if key != "id"}
    config = load_config().model_copy(update={"seed": slot["seed"], "scene_split": slot["split"]})
    assignment = {"seed": slot["seed"], "component_scene": desired}
    application = {
        "scope": "OFFLINE_INITIAL_PHYSICS_AUDIT_NOT_ONLINE_MODEL_INPUT",
        "requested_scene": copy.deepcopy(desired),
        "object_position_m": list(slot["object_position_m"]),
        "object_quaternion_wxyz": [
            math.cos(slot["object_yaw_rad"] / 2),
            0,
            0,
            math.sin(slot["object_yaw_rad"] / 2),
        ],
    }
    return slot, config, assignment, application


def test_exact_registered_requested_and_applied_pose(records):
    checked = audit.check_pose(*records)
    assert checked["position_error_m"] == [0, 0, 0]
    assert checked["yaw_error_rad"] == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize("fault", ["seed", "split", "request", "position", "yaw"])
def test_pose_checks_both_sampling_and_actual_physics(records, fault):
    slot, config, assignment, application = records
    if fault == "seed":
        assignment["seed"] += 1
    elif fault == "split":
        assignment["component_scene"]["split"] = "held-out"
    elif fault == "request":
        application["requested_scene"]["object_yaw_rad"] = 0.9
    elif fault == "position":
        application["object_position_m"][0] += 0.001
    else:
        application["object_quaternion_wxyz"] = [1, 0, 0, 0]
    with pytest.raises(ValueError, match="pose|split|seed"):
        audit.check_pose(slot, config, assignment, application)


def test_batch_rejects_unknown_slot_directory(tmp_path, records):
    slot, *_ = records
    history = tmp_path / "native"
    history.mkdir()
    (history / "fresh-999999").mkdir()
    with pytest.raises(ValueError, match="unknown slot"):
        audit.check_slot_directories(history, [slot])


def test_external_freeze_digest_cannot_be_replaced(tmp_path):
    path = tmp_path / "freeze-receipt.json"
    path.write_text('{"schema":"different"}')
    with pytest.raises(ValueError, match="freeze"):
        audit.read_freeze(path, "a" * 64)


def test_role_bytes_join_the_frozen_source_and_bundle():
    pinned = "a" * 64
    cloud = {"source_hashes": {"cloud.py": pinned}}
    edge = {"source_hashes": {"edge.py": pinned}}
    device = {"device.py": pinned}
    bundle = {
        "cloud_snapshot": cloud,
        "edge_provider_hash": configuration_hash(edge),
        "device_pipeline_hash": configuration_hash(device),
    }
    role = {
        "bundle": bundle,
        "bundle_hash": configuration_hash(bundle),
        "edge_policy": {},
        "edge_snapshot": edge,
        "device_source_hashes": device,
    }
    expected = {"role_binding_sha256": configuration_hash(role)}
    frozen = {"cloud.py": pinned, "edge.py": pinned, "device.py": pinned, "entry.py": pinned}
    sources = {"files": {"entry.py": pinned}}
    assert audit.check_sources(role, sources, frozen, expected) == 4
    role = copy.deepcopy(role)
    role["device_source_hashes"]["device.py"] = "b" * 64
    expected["role_binding_sha256"] = configuration_hash(role)
    with pytest.raises(ValueError, match="role|source"):
        audit.check_sources(role, sources, frozen, expected)


def _counts():
    return {
        "cloud_requests": 0,
        "cloud_request_reservations": 0,
        "local_generations": 2,
        "local_generations_completed": 2,
        "model_loads": 1,
    }


def test_zero_cloud_rejection_has_valid_budget():
    counts = _counts()
    budget = audit.check_budget(counts, counts)
    assert budget["cloud_requests"] == 0
    assert budget["local_generations"] == 2


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("cloud_requests", 2),
        ("cloud_request_reservations", 2),
        ("model_loads", 2),
        ("local_generations", 5),
        ("local_generations_completed", 3),
        ("cloud_requests", True),
    ],
)
def test_out_of_budget_or_wrong_type_is_rejected(key, value):
    counts = _counts() | {key: value}
    with pytest.raises(ValueError, match="budget"):
        audit.check_budget(counts, counts)


def test_a_valid_count_still_needs_native_evidence():
    with pytest.raises(ValueError, match="budget"):
        audit.check_budget(_counts(), _counts() | {"local_generations": 3})


def test_missing_or_replaced_frame_cannot_pass_the_index(tmp_path):
    frame = scene()
    save_servo_frame(frame, tmp_path / "frame")
    files = {}
    for path in (tmp_path / "frame").iterdir():
        data = path.read_bytes()
        files[path.relative_to(tmp_path).as_posix()] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    assert audit.read_frame(tmp_path, files, "frame", frame.episode_id) == frame
    without_depth = dict(files)
    del without_depth["frame/depth.f32"]
    with pytest.raises(ValueError) as missing:
        audit.read_frame(tmp_path, without_depth, "frame", frame.episode_id)
    assert str(missing.value) == "FROZEN_FILE_NOT_BOUND"
    (tmp_path / "frame/rgb.png").write_bytes(b"replacement")
    with pytest.raises(ValueError) as changed:
        audit.read_frame(tmp_path, files, "frame", frame.episode_id)
    assert str(changed.value) == "FROZEN_FILE_HASH_MISMATCH:frame/rgb.png"


def test_manifest_is_mandatory(tmp_path):
    (tmp_path / "result.json").write_text(json.dumps({"seed": 2026111801}))
    with pytest.raises((FileNotFoundError, ValueError)):
        audit.read_index(tmp_path)


@pytest.mark.parametrize(
    ("success", "reason", "codes", "signal", "stop_reason", "allowed"),
    [
        (True, None, (0, 0, 0), None, None, True),
        (False, "COMPONENT_INITIAL_PLANNING_REJECTED", (2, 2, 2), None, None, True),
        (False, "CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED", (2, 2, 2), None, None, True),
        (True, None, (1, 1, 1), None, None, False),
        (False, "COMPONENT_INITIAL_PLANNING_REJECTED", (1, 1, 1), None, None, False),
        (True, None, (0, 0, 1), None, None, False),
        (True, None, (0, 1, 0), None, None, False),
        (True, None, (0, 0, 0), 15, None, False),
        (True, None, (0, 0, 0), None, "TIMEOUT", False),
        (False, "COMPONENT_INITIAL_PLANNING_REJECTED", (124, 124, -15), 15, "TIMEOUT", False),
        (
            False,
            "COMPONENT_INITIAL_PLANNING_REJECTED",
            (130, 130, -2),
            2,
            "WRAPPER_INTERRUPT",
            False,
        ),
        (True, None, (False, 0, 0), None, None, False),
        (True, None, (0, 0, None), None, None, False),
    ],
)
def test_only_bound_production_exit_can_release_next_slot(
    success,
    reason,
    codes,
    signal,
    stop_reason,
    allowed,
):
    actual_exit, wrapper_exit, child_exit = codes
    row = {
        "audit_status": "VERIFIED",
        "component_success": success,
        "terminal_reason": reason,
        "physical": {"safety_violation": False},
        "signal": signal,
        "returncode": actual_exit,
        "wrapper_exit_code": wrapper_exit,
        "episode_exit_code": child_exit,
        "wrapper_stop_reason": stop_reason,
    }
    assert runner._contained_stops(row) is allowed


def test_begin_is_permanent_across_same_and_alternate_roots(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    canonical = tmp_path / "first"
    alternate = tmp_path / "second"
    monkeypatch.setattr(runner, "REGISTERED_CHECKOUT", checkout, raising=False)
    monkeypatch.setattr(runner, "REGISTERED_RAW_ROOT", canonical, raising=False)
    checkout.mkdir()
    fixed_input = tmp_path / "fixture"
    fixed_input.write_text("fixture")
    digest = runner.sha256_file(fixed_input)
    slots = runner.read_allocation(ROUND / "preallocation.json")["episodes"]
    slot = slots[0]
    resources = {
        "--model-directory": str(tmp_path),
        "--asset-manifest": str(fixed_input),
        "--native-python": str(fixed_input),
    }
    freeze = {
        "schema": runner.FREEZE_SCHEMA,
        "preallocation_sha256": runner.PREALLOCATION_SHA256,
        "commit": "test",
        "native_python_sha256": digest,
        "installed_launcher_sha256": digest,
        "asset_manifest_sha256": digest,
        "history_roots": [str(checkout)],
        "slots": {
            row["id"]: {"config_sha256": digest, "role_binding_sha256": "role"} for row in slots
        },
    }
    monkeypatch.setattr(runner, "verify_frozen_sources", lambda *_: None)
    monkeypatch.setattr(runner, "_git", lambda *_: "test")
    monkeypatch.setattr(runner, "_resources", lambda *_: resources)
    monkeypatch.setattr(runner, "_check_free_space", lambda *_: {})
    monkeypatch.setattr(runner, "_role_config", lambda *_: "role")
    monkeypatch.setattr(runner, "load_config", lambda *_: None)
    called = []

    def interrupt_before_provider(*_, cwd, **__):
        called.append(cwd)
        raise OSError("fixture stopped after BEGIN, before any process")

    monkeypatch.setattr(runner.subprocess, "run", interrupt_before_provider)
    for root in (canonical, alternate):
        (root / "configs").mkdir(parents=True)
        (root / "configs" / f"{slot['id']}.json").write_text("fixture")
        runner.write_new(root / "freeze-receipt.json", freeze)

    def attempt(raw_root):
        path = raw_root / "freeze-receipt.json"
        return runner.launch(
            SimpleNamespace(
                allow_paid=True,
                raw_root=raw_root,
                checkout=checkout,
                seed=slot["seed"],
                resources_from=fixed_input,
                cli=fixed_input,
                freeze_sha256=runner.sha256_file(path),
            )
        )

    with pytest.raises(OSError, match="fixture stopped"):
        attempt(canonical)
    begin = canonical / "receipts" / f"{slot['id']}-started.json"
    before = begin.read_bytes()
    with pytest.raises(ValueError, match="already claimed"):
        attempt(canonical)
    with pytest.raises(ValueError, match="registered"):
        attempt(alternate)
    assert called == [canonical]
    assert begin.read_bytes() == before
    assert not list(alternate.glob("receipts/*-started.json"))
