"""真实规划管线的两阶段worker补帧，不加载权重或连接云端。"""

from __future__ import annotations

import hashlib
import importlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.vision.grounded_planner import (
    GroundingTaskDescriptor,
    MolmoGroundedPlannerAdapter,
)
from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
from tests.test_molmo_grounded_planner import SKILLS, cloud_fixture, request_scene
from tests.test_molmo_revalidation import rebuild


class PhrasePoints:
    """完整的CPU点协议替身，真实关联器、深度和OpenCV管线继续运行。"""

    def __init__(self):
        self.calls = 0

    def point(self, observation, phrase):
        self.calls += 1
        raw = (
            '<points coords="1 1 '
            + ("150 410" if "red block" in phrase else "650 425")
            + '">support</points>'
        )
        return BoundPointResult(
            parse_native_point(raw),
            observation.checksum_sha256,
            observation.evidence()["rgb_sha256"],
            hashlib.sha256(phrase.encode()).hexdigest(),
            {"evidence_scope": "SOFTWARE_ONLY"},
        )


def owned(monkeypatch, *, config_version=1):
    cloud, bodies = cloud_fixture(monkeypatch, reply={"skills": SKILLS[1:-1]})
    cloud.role_config_version = config_version
    points = PhrasePoints()
    adapter = MolmoGroundedPlannerAdapter(
        cloud=cloud,
        point_provider=points,
        task=GroundingTaskDescriptor(
            instruction="Move the red block to the green region.",
            target_phrase="red block",
            destination_phrase="green region",
            target_label="red block",
        ),
        worker_owned_refresh=True,
    )
    request = request_scene(scene_id="SOFTWARE_ONLY_S01")
    return adapter, points, bodies, request


def fresh_request(request, **updates):
    fresh = rebuild(
        request.observation, frame_id="owned-fresh", captured_at=datetime.now(UTC), **updates
    )
    return request.model_copy(update={"observation": fresh, "request_id": "owned-second"})


def test_worker_owns_reobservation_between_single_cloud_and_final_contract(monkeypatch):
    adapter, points, bodies, request = owned(monkeypatch)
    response = PlanningPipeline(planner=adapter, max_repair_attempts=0).process(request)
    assert response.outcome == "REQUEST_MORE_OBSERVATION"
    assert adapter.awaiting_owned_refresh is True
    assert response.attempts[0].draft.observation_evidence["owned_refresh_required"] is True
    current = fresh_request(request)
    response = PlanningPipeline(planner=adapter, max_repair_attempts=0).process(current)
    assert response.outcome == "PLANNED", response.reason
    assert [s.skill.value for s in response.contract.steps] == SKILLS[1:-1]
    evidence = response.attempts[-1].draft.observation_evidence
    assert evidence["observation_id"] == "owned-fresh"
    assert evidence["cloud_reference"]["observation_id"] == request.observation.observation_id
    assert evidence["post_cloud_revalidation"]["status"] == "PASSED"
    assert evidence["final_plan_admission"]["status"] == "PASSED"
    assert points.calls == 4 and len(bodies) == 1
    assert adapter.awaiting_owned_refresh is False
    again = adapter.plan(fresh_request(current))
    assert again.parse_error
    assert len(bodies) == 1 and points.calls == 4


@pytest.mark.parametrize("change", ["old_frame", "sim_time", "task", "context"])
def test_owned_refresh_cannot_reuse_frame_or_changed_binding(monkeypatch, change):
    adapter, points, bodies, request = owned(monkeypatch)
    first = adapter.plan(request)
    assert first.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert first.observation_evidence["model_image_count"] == 1
    assert first.observation_evidence["acquisition_evidence"]["model_image_count"] == 2
    second = request if change == "old_frame" else fresh_request(request)
    if change == "sim_time":
        second = fresh_request(request, sim_time_s=0.1)
    elif change == "task":
        second = second.model_copy(update={"user_instruction": "move a different object"})
    elif change == "context":
        adapter.cloud.timeout_s += 1
    result = adapter.plan(second)
    assert result.parse_error or result.parsed_json.get("_sentinel") == "REQUEST_MORE_OBSERVATION"
    assert len(bodies) == 1 and points.calls == 2
    assert adapter.awaiting_owned_refresh is False


def test_owner_call_stays_on_main_thread_and_discards_late_or_cancelled_results():
    module = importlib.import_module("cloud_edge_robot_arm.vision.request_control")
    call = module.bounded_owner_model_call
    assert call(threading.get_ident, timeout_s=1) == threading.main_thread().ident
    with pytest.raises(module.ModelCallTimedOut):
        call(lambda: time.sleep(0.02) or "late", timeout_s=0.005)
    with pytest.raises(module.ModelCallCancelled):
        call(lambda: pytest.fail("cancelled call started"), timeout_s=1, cancelled=lambda: True)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(RuntimeError, match="main thread"):
            pool.submit(call, lambda: "wrong thread", timeout_s=1).result()


def test_slow_cloud_requests_owned_capture_instead_of_reusing_expired_frame(monkeypatch):
    from datetime import timedelta

    import cloud_edge_robot_arm.vision.grounded_planner as implementation

    now = datetime.now(UTC)
    clock = [now]
    monkeypatch.setattr(implementation, "_utcnow", lambda: clock[0])
    adapter, points, bodies, request = owned(monkeypatch)
    monkeypatch.setattr(implementation, "_utcnow", lambda: clock[0])
    old_request = request.model_copy(
        update={"observation": rebuild(request.observation, captured_at=now)}
    )
    original = adapter.cloud._request_visual

    def delayed(*args, **kwargs):
        answer = original(*args, **kwargs)
        clock[0] += timedelta(seconds=6)
        return answer

    monkeypatch.setattr(adapter.cloud, "_request_visual", delayed)
    draft = adapter.plan(old_request)
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert adapter.awaiting_owned_refresh is True
    assert len(bodies) == 1 and points.calls == 2


@pytest.mark.parametrize("config_version", [1, 7])
def test_worker_adapter_exposes_immutable_roles_and_validated_draft(
    monkeypatch, tmp_path, config_version
):
    from pathlib import Path

    from cloud_edge_robot_arm.vision.role_models import (
        RoleProviderSnapshot,
        cloud_request_settings,
        configuration_hash,
    )

    adapter, points, bodies, request = owned(monkeypatch, config_version=config_version)
    root = Path(__file__).resolve().parents[1]
    name = "src/cloud_edge_robot_arm/vision/grounded_planner.py"
    adapter.cloud.role_snapshot = RoleProviderSnapshot(
        "CLOUD",
        "sol",
        "REMOTE_SERVICE",
        "gpt-6.1-sol",
        None,
        None,
        None,
        configuration_hash(cloud_request_settings(adapter.cloud)),
        {name: hashlib.sha256((root / name).read_bytes()).hexdigest()},
    )
    module = importlib.import_module("cloud_edge_robot_arm.vision.molmo_worker")
    planner = module.MolmoWorkerPlanner(adapter, output=tmp_path)
    binding = module.make_worker_binding(planner, asset_manifest_sha256="a" * 64)
    binding.validate(planner)
    first = planner.plan(request)
    assert first.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert planner.awaiting_owned_refresh is True
    second = planner.plan(fresh_request(request))
    assert not second.parse_error and len(second.parsed_json["steps"]) == 8
    assert second.observation_evidence["model_snapshot_hash"] == planner.model_snapshot.digest()
    assert second.observation_evidence["final_plan_admission"]["status"] == "PASSED"
    assert len(bodies) == 1 and points.calls == 4
    planner.timeout_s += 1
    with pytest.raises(ValueError, match="settings"):
        binding.validate(planner)
