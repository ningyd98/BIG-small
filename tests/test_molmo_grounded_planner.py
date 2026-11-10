"""识别点到原始深度几何及云端技能的真实代码契约测试。"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import numpy as np
import pytest

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from tests.test_opencv_target_evidence import scene

SKILLS = [
    "HOME",
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
    "HOME",
]


def request_scene(**kwargs):
    observation = scene(started=datetime.now(UTC), **({"source": "mujoco_camera"} | kwargs))
    return InitialPlanningRequest(
        request_id="grounded-test",
        user_instruction="Move the red block to the green region.",
        observation=observation,
    )


def grounded(request):
    from cloud_edge_robot_arm.vision.planner import ground_observation

    return ground_observation(
        request,
        request.observation,
        target_pixel=(12, 26),
        destination_pixel=(52, 27),
        target_label="red block",
        grasp_profile="mujoco_upright_box_v2",
        evidence={"source_marker": "CPU_GEOMETRY_FIXTURE"},
    )


def test_grounding_helper_has_no_model_confidence():
    result = grounded(request_scene())
    e = result.evidence
    assert e["original_pixel_target"] == [12, 26]
    assert e["grounded_target"] == pytest.approx({"x": -0.2632, "y": 0.0564, "z": 0.06}, abs=1e-7)
    assert e["grounded_destination"] == pytest.approx({"x": 0.12, "y": 0.05, "z": 0})
    assert e["resolved_top_grasp_tcp"]["z"] == pytest.approx(0.04, abs=1e-7)
    assert e["estimated_object_height_m"] == pytest.approx(0.06, abs=1e-7)
    assert "reported_confidence" not in json.dumps(e)
    assert result.scene.objects[0].pose is None


@pytest.mark.parametrize("endpoint", [(12, 26), (52, 27)])
def test_grounding_rejects_zero_depth_at_either_endpoint(endpoint):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    request = request_scene()
    payload = request.observation.model_dump()
    depth = np.asarray(request.observation.depth_values(), dtype="<f4").reshape(64, 80)
    depth[endpoint[1], endpoint[0]] = 0
    payload.update(
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
    )
    request = request.model_copy(update={"observation": RGBDObservation.model_validate(payload)})
    with pytest.raises(ValueError, match="invalid depth"):
        grounded(request)


@pytest.mark.parametrize("change", ["profile", "source", "table", "patch", "height"])
def test_grounding_rejects_invalid_depth_and_profile(change):
    from cloud_edge_robot_arm.vision.planner import ground_observation

    request = request_scene(
        damage="depth_spike" if change == "patch" else None, lift=0.15 if change == "height" else 0
    )
    observation = request.observation
    if change == "source":
        observation = observation.model_copy(update={"source": "rgbd_camera"})
    with pytest.raises(ValueError):
        ground_observation(
            request,
            observation,
            target_pixel=(30, 40) if change == "table" else (12, 26),
            destination_pixel=(52, 27),
            target_label="red block",
            grasp_profile="bad" if change == "profile" else "mujoco_upright_box_v2",
            evidence={},
        )


@pytest.mark.parametrize("order", [SKILLS, SKILLS[1:], SKILLS[:-1], SKILLS[1:-1]])
def test_contract_builder_preserves_whitelist_and_trusted_fields(order):
    from cloud_edge_robot_arm.vision.planner import build_grounded_contract

    request = request_scene()
    draft = build_grounded_contract(
        request, grounded(request), order, raw_text="actual cloud content"
    )
    assert draft.raw_text == "actual cloud content"
    assert [s["skill"] for s in draft.parsed_json["steps"]] == order
    assert draft.parsed_json["task_id"] == "" and draft.parsed_json["plan_version"] == 0
    assert draft.parsed_json["issued_at"] == "" and draft.parsed_json["command_seq"] == 0


@pytest.mark.parametrize(
    "order", [[], ["GRASP"], list(reversed(SKILLS)), SKILLS + ["HOME"], ["HOME"] + SKILLS]
)
def test_contract_builder_rejects_bad_skill_order(order):
    from cloud_edge_robot_arm.vision.planner import build_grounded_contract

    request = request_scene()
    with pytest.raises(ValueError, match="sequence"):
        build_grounded_contract(request, grounded(request), order, raw_text="actual cloud content")


class FixturePoints:
    def __init__(self, *, status="POINT", mismatch=None, after=None):
        self.queries = []
        self.status = status
        self.mismatch = mismatch
        self.after = after

    def point(self, observation, phrase):
        import hashlib

        from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point

        self.queries.append(phrase)
        # 80x64: (150,410)->(12,26), (650,425)->(52,27), hand-derived.
        coords = "150 410" if len(self.queries) == 1 else "650 425"
        raw = f'<points coords="1 1 {coords}">requested support</points>'
        if self.status != "POINT":
            raw = "ABSENT" if self.status == "ABSENT" else "unparseable fixture"
        checksum = observation.checksum_sha256
        query = hashlib.sha256(phrase.encode()).hexdigest()
        rgb = observation.evidence()["rgb_sha256"]
        if self.mismatch == "observation":
            checksum = "0" * 64
        if self.mismatch == "rgb":
            rgb = "0" * 64
        if self.mismatch == "query":
            query = "0" * 64
        if self.after:
            self.after()
        return BoundPointResult(
            parse_native_point(raw),
            checksum,
            rgb,
            query,
            {"evidence_scope": "CPU_CONTRACT_FIXTURE"},
        )


def cloud_fixture(monkeypatch, reply=None, *, allow_paid=True, after=None, fail=False):
    import io
    import urllib.request

    from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter

    snapshot = ModelConfigSnapshot(
        provider="openai_compatible",
        model="gpt-6.1-sol",
        endpoint="https://api.openai.com",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"reasoning_effort": "low", "max_completion_tokens": 4096},
        timeout_s=30,
        grasp_profile="mujoco_upright_box_v2",
    )
    cloud = RGBDPlannerAdapter(
        base_url=snapshot.endpoint,
        model=snapshot.model,
        provider=snapshot.provider,
        model_snapshot=snapshot,
        allow_paid=allow_paid,
        chat_path="/v1/chat/completions",
        api_key="test-only-cloud-secret",
    )
    bodies = []

    class ExternalBoundary:
        def open(self, request, timeout):
            bodies.append(json.loads(request.data))
            if after:
                after()
            if fail:
                raise TimeoutError("external fixture timeout")
            content = json.dumps(
                reply if reply is not None else {"skills": SKILLS, "reason": "fixture"}
            )
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: ExternalBoundary())
    return cloud, bodies


def adapter_fixture(monkeypatch, *, points=None, **kwargs):
    from cloud_edge_robot_arm.vision.grounded_planner import (
        GroundingTaskDescriptor,
        MolmoGroundedPlannerAdapter,
    )

    cloud, bodies = cloud_fixture(monkeypatch, **kwargs)
    points = points or FixturePoints()
    descriptor = GroundingTaskDescriptor(
        instruction="Move the red block to the green region.",
        target_phrase="red block",
        destination_phrase="green region",
        target_label="red block",
    )
    return (
        MolmoGroundedPlannerAdapter(point_provider=points, cloud=cloud, task=descriptor),
        points,
        bodies,
    )


def test_grounded_adapter_pipeline_success(monkeypatch):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    adapter, points, bodies = adapter_fixture(monkeypatch)
    response = PlanningPipeline(planner=adapter).process(request_scene())
    assert response.outcome == "PLANNED"
    assert response.contract.task_target.object_id == "visual_target"
    e = response.attempts[0].draft.observation_evidence
    assert e["original_pixel_target"] == [12, 26]
    assert e["perception_model_image_count"] == 1 and e["cloud_model_image_count"] == 0
    assert e["depth_consumed_by"] == "DETERMINISTIC_RGBD_OPENCV"
    assert "reported_confidence" not in json.dumps(e)
    assert e["opencv_initial_geometry"]["target"]["extent_complete"] is False
    assert points.queries == ["visible top center of red block", "interior of green region"]
    assert bodies[0]["model"] == "gpt-6.1-sol"
    assert bodies[0]["reasoning_effort"] == "low" and bodies[0]["max_completion_tokens"] == 4096
    assert "max_tokens" not in bodies[0] and "temperature" not in bodies[0]
    assert all(isinstance(m["content"], str) for m in bodies[0]["messages"])
    assert "CPU_CONTRACT_FIXTURE" not in json.dumps(bodies)


def test_query_descriptor_is_bound_to_instruction(monkeypatch):
    adapter, points, bodies = adapter_fixture(monkeypatch)
    request = request_scene().model_copy(update={"user_instruction": "Move a different target."})
    draft = adapter.plan(request)
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert points.queries == [] and bodies == []


@pytest.mark.parametrize("value", ["", " ", "<points>", "x" * 161, "red\nblock"])
def test_descriptor_rejects_unbounded_or_markup_phrase(value):
    from cloud_edge_robot_arm.vision.grounded_planner import GroundingTaskDescriptor

    with pytest.raises(ValueError):
        GroundingTaskDescriptor(
            instruction="Move red.",
            target_phrase=value,
            destination_phrase="green region",
            target_label="red block",
        )


@pytest.mark.parametrize(
    "status,mismatch",
    [
        ("ABSENT", None),
        ("INVALID", None),
        ("POINT", "observation"),
        ("POINT", "rgb"),
        ("POINT", "query"),
    ],
)
def test_absent_invalid_or_mismatched_point_skips_cloud(monkeypatch, status, mismatch):
    adapter, points, bodies = adapter_fixture(
        monkeypatch, points=FixturePoints(status=status, mismatch=mismatch)
    )
    draft = adapter.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert bodies == [] and draft.raw_text == ""


@pytest.mark.parametrize("damage", ["decoy", "occluded", "depth", "edge_occluder"])
def test_native_grounding_opencv_fail_closed(monkeypatch, damage):
    adapter, _, bodies = adapter_fixture(monkeypatch)
    draft = adapter.plan(request_scene(damage=damage))
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert bodies == []


@pytest.mark.parametrize(
    "field,value", [("source", "rgbd_camera"), ("episode_id", None), ("calibration_version", None)]
)
def test_native_grounding_rejects_unbound_sensor(monkeypatch, field, value):
    adapter, points, bodies = adapter_fixture(monkeypatch)
    request = request_scene(**{field: value})
    assert adapter.plan(request).parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert bodies == [] and points.queries == []


@pytest.mark.parametrize("stage", ["before", "local", "cloud", "future"])
def test_expiry_during_local_or_cloud_call(monkeypatch, stage):
    from datetime import timedelta

    import cloud_edge_robot_arm.vision.grounded_planner as module

    request = request_scene()
    clock = [request.observation.captured_at]
    def advance() -> None:
        clock[0] = clock[0] + timedelta(seconds=6)
    points = FixturePoints(after=advance if stage == "local" else None)
    adapter, _, bodies = adapter_fixture(
        monkeypatch, points=points, after=advance if stage == "cloud" else None
    )
    if stage == "before":
        advance()
    if stage == "future":
        clock[0] -= timedelta(seconds=0.051)
    monkeypatch.setattr(module, "_utcnow", lambda: clock[0])
    draft = adapter.plan(request)
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert len(bodies) == (1 if stage == "cloud" else 0)


@pytest.mark.parametrize(
    "extra",
    [
        "target_pixel",
        "grounded_target",
        "target_label",
        "reported_confidence",
        "issued_at",
        "disable_safety",
    ],
)
def test_cloud_skill_only_rejects_override(monkeypatch, extra):
    adapter, _, _ = adapter_fixture(monkeypatch, reply={"skills": SKILLS, extra: [1, 2]})
    draft = adapter.plan(request_scene())
    assert draft.parsed_json is None and draft.parse_error


@pytest.mark.parametrize("skills", [None, True, ["FLY"], ["GRASP"], list(reversed(SKILLS))])
def test_cloud_skill_only_rejects_invalid_sequence(monkeypatch, skills):
    adapter, _, _ = adapter_fixture(monkeypatch, reply={"skills": skills})
    draft = adapter.plan(request_scene())
    assert draft.parsed_json is None and draft.parse_error


def test_empty_skills_requests_observation(monkeypatch):
    adapter, _, _ = adapter_fixture(monkeypatch, reply={"skills": [], "reason": "uncertain"})
    draft = adapter.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert json.loads(draft.raw_text)["skills"] == []


def test_cloud_failure_has_no_fixture_fallback(monkeypatch):
    adapter, _, bodies = adapter_fixture(monkeypatch, fail=True)
    draft = adapter.plan(request_scene())
    assert draft.parse_error and draft.parsed_json is None
    assert draft.raw_text == "" and len(bodies) == 1


def test_selected_sol_transport_preserved(monkeypatch, tmp_path):
    from cloud_edge_robot_arm.model_control.models import PlannerProviderKind
    from cloud_edge_robot_arm.model_control.secret_store import InMemorySecretStore
    from cloud_edge_robot_arm.model_control.service import ModelControlService
    from cloud_edge_robot_arm.model_control.sqlite_repository import SQLiteModelProfileRepository
    from cloud_edge_robot_arm.vision.grounded_planner import (
        GroundingTaskDescriptor,
        build_molmo_grounded_planner,
    )

    service = ModelControlService(
        repository=SQLiteModelProfileRepository(tmp_path / "models.db"),
        secret_store=InMemorySecretStore(),
    )
    profile = service.create_profile(
        display_name="Sol fixture",
        model_name="gpt-6.1-sol",
        provider_kind=PlannerProviderKind.OPENAI_COMPATIBLE,
        base_url="https://api.openai.com",
        api_key="test-only-factory-secret",
    )
    task = GroundingTaskDescriptor(
        instruction=request_scene().user_instruction,
        target_phrase="red block",
        destination_phrase="green region",
        target_label="red block",
    )
    adapter = build_molmo_grounded_planner(
        service=service,
        profile_id=profile.profile_id,
        point_provider=FixturePoints(),
        task=task,
        grasp_profile="mujoco_upright_box_v2",
    )
    assert adapter.cloud.model_name == "gpt-6.1-sol"
    assert adapter.cloud.allow_paid is False
    assert service.repository.get_active_profile_id() == ""
    assert "test-only-factory-secret" not in json.dumps(adapter.cloud.role_snapshot.evidence())
    # Actual request path refuses paid transmission with the default setting.
    draft = adapter.plan(request_scene())
    assert draft.parse_error and draft.parsed_json is None


@pytest.mark.parametrize("normalized,pixel", [(0, 0), (500, 40), (1000, 79)])
def test_pixel_mapping_once(monkeypatch, normalized, pixel):
    from dataclasses import replace

    from cloud_edge_robot_arm.vision.molmo_pointing import parse_native_point

    class BoundaryPoints(FixturePoints):
        def point(self, observation, phrase):
            value = super().point(observation, phrase)
            if len(self.queries) == 1:
                value = replace(
                    value,
                    result=parse_native_point(
                        f'<points coords="1 1 {normalized} 410">support</points>'
                    ),
                )
            return value

    adapter, _, _ = adapter_fixture(monkeypatch, points=BoundaryPoints())
    draft = adapter.plan(request_scene())
    assert draft.observation_evidence["original_pixel_target"] == [pixel, 26]


def test_scene_oracle_metadata_does_not_enter_requests(monkeypatch):
    from cloud_edge_robot_arm.cloud.planning.models import SceneObjectSummary

    adapter, points, bodies = adapter_fixture(monkeypatch)
    request = request_scene()
    request.scene.objects = [
        SceneObjectSummary(object_id="SECRET_ORACLE", object_class="SECRET_ORACLE")
    ]
    draft = adapter.plan(request)
    assert draft.parsed_json is not None and not draft.parse_error
    assert "SECRET_ORACLE" not in json.dumps(bodies)
    assert "SECRET_ORACLE" not in json.dumps(points.queries)


def test_cloud_configuration_drift_during_reply_is_closed(monkeypatch):
    adapter, _, bodies = adapter_fixture(monkeypatch)
    original = adapter.cloud._request_visual

    def drift(*args):
        response = original(*args)
        adapter.cloud.timeout_s = 29
        return response

    monkeypatch.setattr(adapter.cloud, "_request_visual", drift)
    draft = adapter.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert len(bodies) == 1


def test_small_frame_never_uses_legacy_geometry_bypass(monkeypatch):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_rgbd_observations import observation_payload

    adapter, points, bodies = adapter_fixture(monkeypatch)
    request = request_scene().model_copy(
        update={"observation": RGBDObservation.model_validate(observation_payload())}
    )
    assert adapter.plan(request).parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert points.queries == [] and bodies == []
