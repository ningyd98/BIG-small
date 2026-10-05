"""Role/source drift and native CV uncertainty cannot authorize a skill."""

import hashlib
import importlib
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.vision.evaluation import ExecutionPolicy
from cloud_edge_robot_arm.vision.role_models import (
    RoleModelBundle,
    RoleProviderSnapshot,
    cloud_request_settings,
    configuration_hash,
)


def api():
    return importlib.import_module("cloud_edge_robot_arm.vision.runtime_binding")


def role_binding(tmp_path):
    from cloud_edge_robot_arm.vision.model_resolver import (
        ModelConfigSnapshot,
        resolve_visual_planner,
    )

    snapshot = ModelConfigSnapshot(provider="openai_compatible", model="qwen3.8-max",
        endpoint="https://example.invalid", weight_digest=None, quantization=None,
        image_size=(320, 240), generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30)
    planner = resolve_visual_planner(snapshot, api_key="", allow_paid=False)
    sources = {}
    for name in ("cloud.py", "edge.py", "device.py"):
        path = tmp_path / name
        path.write_text("# frozen implementation\n")
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    cloud = RoleProviderSnapshot("CLOUD", "max", "REMOTE_SERVICE", planner.model_name,
        None, None, None, configuration_hash(cloud_request_settings(planner)),
        {"cloud.py": sources["cloud.py"]})
    edge_policy = {"provider": "rules", "local_recover_enabled": False,
        "verification_budget": asdict(ExecutionPolicy("legacy", model_snapshot_hash="a" * 64)
                                      .verification_budget),
        "runtime_router": "verification_router.v1",
        "capabilities": ["CONTINUE", "REOBSERVE", "STOP"]}
    router = "src/cloud_edge_robot_arm/edge/recovery/verification_router.py"
    original = Path(__file__).resolve().parents[1] / router
    copied = tmp_path / router
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes(original.read_bytes())
    edge_sources = {"edge.py": sources["edge.py"],
                    router: hashlib.sha256(copied.read_bytes()).hexdigest()}
    edge = RoleProviderSnapshot("EDGE", "rules", "LOCAL_HOST", None, None, None, None,
        configuration_hash(edge_policy), edge_sources)
    device = {"device.py": sources["device.py"]}
    bundle = RoleModelBundle(cloud, edge.provider_id, edge.digest(), configuration_hash(device))
    planner.role_snapshot = cloud
    return planner, api().RoleRuntimeBinding(bundle, edge, device, edge_policy, root=tmp_path)


@pytest.mark.parametrize("drift", ["model", "endpoint", "timeout", "cloud", "edge", "device"])
def test_mutable_role_or_source_drift_is_rechecked_at_boundary(tmp_path, drift):
    planner, binding = role_binding(tmp_path)
    binding.validate(planner)
    if drift == "model":
        planner.model_name = "other"
    elif drift == "endpoint":
        planner.base_url = "http://other"
    elif drift == "timeout":
        planner.timeout_s += 1
    else:
        (tmp_path / f"{drift}.py").write_text("# changed\n")
    with pytest.raises(ValueError):
        binding.validate(planner)


def test_role_binding_rejects_swapped_edge_and_fake_device_digest(tmp_path):
    planner, binding = role_binding(tmp_path)
    with pytest.raises(ValueError):
        replace(binding, bundle=replace(binding.bundle, device_pipeline_hash="f" * 64))
    planner.role_snapshot = binding.edge_snapshot
    with pytest.raises(ValueError):
        binding.validate(planner)


def test_device_pipeline_requires_complete_role_binding():
    with pytest.raises(ValueError):
        ExecutionPolicy("pick red", model_snapshot_hash="a" * 64, device_pipeline="OPENCV")


def test_opencv_factory_preserves_native_unknown_in_canonical_conditions(tmp_path):
    from cloud_edge_robot_arm.edge.evidence.conditions import (
        OnlineEvidenceSnapshot,
        evaluate_conditions,
    )
    from cloud_edge_robot_arm.vision.execution import make_target_tracker, terminal_conditions
    from tests.test_opencv_target_evidence import scene
    from tests.test_rgbd_online_verification import evidence

    _, binding = role_binding(tmp_path)
    policy = ExecutionPolicy("Move the red block to the green region.",
        model_snapshot_hash="a" * 64, device_pipeline="OPENCV", role_binding=binding)
    observation = scene()
    tracker = make_target_tracker(observation, {
        "original_pixel_target": [12, 26], "original_pixel_destination": [57, 32],
        "top_grasp_support_height_m": 0.0,
    }, policy)
    facts = tracker.facts(observation)
    snap = OnlineEvidenceSnapshot(observation, evidence().robot_state, facts, 1, 1, "test")
    verdicts = evaluate_conditions(terminal_conditions(policy), snap)
    assert "placement_stable" in {row.condition_name for row in verdicts}
    assert any(row.status.value == "UNKNOWN" for row in verdicts)


def test_role_drift_before_skill_stops_before_safety_and_dispatch(tmp_path):
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode

    planner, binding = role_binding(tmp_path)
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.planner = planner
    episode.policy = ExecutionPolicy("pick red", model_snapshot_hash="a" * 64,
        device_pipeline="OPENCV", role_binding=binding)
    episode.check_active = lambda: None
    episode.observation = SimpleNamespace(observation_id="fresh")
    calls = []
    episode.shield = SimpleNamespace(pre_check=lambda _: calls.append("safety"))
    episode.executor = SimpleNamespace(execute_attempt=lambda **_: calls.append("dispatch"))
    planner.model_name = "swapped"
    with pytest.raises(_EpisodeStopped, match="ROLE_BINDING_CHANGED"):
        episode.execute(None, None)
    assert calls == []


def test_role_paths_cannot_follow_symlink_or_escape_root(tmp_path):
    planner, binding = role_binding(tmp_path)
    (tmp_path / "device.py").unlink()
    (tmp_path / "device.py").symlink_to(tmp_path / "cloud.py")
    with pytest.raises(ValueError, match="source"):
        binding.validate(planner)


@pytest.mark.parametrize("damage", [None, "occluded"])
def test_native_stability_is_not_overwritten_by_legacy_endpoint_hold(tmp_path, damage):
    from cloud_edge_robot_arm.vision.execution import _VisualEpisode
    from tests.test_opencv_target_evidence import scene, tracker

    _, binding = role_binding(tmp_path)
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.policy = ExecutionPolicy("pick red", model_snapshot_hash="a" * 64,
        device_pipeline="OPENCV", role_binding=binding)
    episode.observation = scene()
    episode.tracker = tracker(episode.observation)
    if damage:
        episode.observation = scene("occluded", time=.1, damage=damage,
            started=episode.tracker._reference.captured_at)
    from cloud_edge_robot_arm.contracts import RobotState

    state = RobotState(connected=True)
    episode.robot = SimpleNamespace(get_state=lambda: state)
    backend = SimpleNamespace(total_physics_steps=0, _config=SimpleNamespace(physics_dt_s=.1))
    backend.step = lambda steps: setattr(backend, "total_physics_steps",
        backend.total_physics_steps + steps)
    episode.backend = backend
    episode.records = []
    episode.monitor_physics_state = lambda: None
    episode.recapture = lambda: None
    observed = []
    episode.verify = lambda *_, **kwargs: observed.append(kwargs.get("facts_transform")) or False
    assert episode.hold_lift() is False
    assert observed == [None]


@pytest.mark.parametrize("changed_during_call", [False, True])
def test_cloud_return_checks_binding_before_accepting_draft(tmp_path, changed_during_call):
    import time
    from datetime import UTC, datetime, timedelta

    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
    from cloud_edge_robot_arm.vision.execution import _EpisodeStopped, _VisualEpisode
    from tests.test_opencv_target_evidence import scene

    planner, binding = role_binding(tmp_path)
    episode = _VisualEpisode.__new__(_VisualEpisode)
    episode.policy = ExecutionPolicy("pick red", model_snapshot_hash="a" * 64,
        device_pipeline="OPENCV", role_binding=binding)
    episode.planner = planner
    episode.check_active = lambda: None
    episode.observation = scene()
    episode.calls = 0
    episode.deadline = time.monotonic() + 10
    episode.budget = SimpleNamespace(deadline_at=datetime.now(UTC) + timedelta(seconds=10))
    episode.wait_clock = None
    episode.records = []
    episode.route = lambda *_: DecisionAction.CONTINUE
    calls = []

    def plan(request):
        calls.append(request.observation.observation_id)
        if changed_during_call:
            planner.model_name = "changed-during-inference"
        return PlannerDraft(planner_name="fixture", model_name=planner.model_name,
            raw_text="{}", parsed_json={"steps": []}, parse_error=None)

    planner.plan = plan
    if changed_during_call:
        with pytest.raises(_EpisodeStopped, match="ROLE_BINDING_CHANGED"):
            episode.plan()
        assert episode.records == []
    else:
        draft = episode.plan()
        assert draft.observation_evidence["role_bundle_hash"] == binding.bundle.digest()
    assert len(calls) == 1


def test_legacy_runtime_import_does_not_require_optional_opencv():
    import subprocess
    import sys

    code = '''
import builtins
original = builtins.__import__
def without_cv(name, *args, **kwargs):
    if name == "cv2" or name.startswith("cv2."):
        raise ModuleNotFoundError("optional OpenCV is intentionally absent")
    return original(name, *args, **kwargs)
builtins.__import__ = without_cv
from cloud_edge_robot_arm.vision.execution import RGBDTargetTracker
assert RGBDTargetTracker is not None
'''
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_identical_role_bundle_cannot_change_consumed_verification_limits(tmp_path):
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget

    _, binding = role_binding(tmp_path)
    with pytest.raises(ValueError, match="budget"):
        ExecutionPolicy("Move the red block to the green region.", model_snapshot_hash="a" * 64,
            device_pipeline="OPENCV", role_binding=binding,
            verification_budget=VerificationBudget(100, 0, 100, 120))


def test_binding_cannot_omit_the_actual_verification_router_source(tmp_path):
    _, binding = role_binding(tmp_path)
    edge = replace(binding.edge_snapshot, source_hashes={"edge.py": "a" * 64})
    bundle = replace(binding.bundle, edge_provider_hash=edge.digest())
    with pytest.raises(ValueError, match="router source"):
        replace(binding, bundle=bundle, edge_snapshot=edge)
