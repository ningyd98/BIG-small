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

    adapter, _, bodies = adapter_fixture(monkeypatch, points=BoundaryPoints())
    draft = adapter.plan(request_scene())
    assert draft.observation_evidence["native_original_pixel_target"] == [pixel, 26]
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert bodies == []


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


@pytest.mark.parametrize("stage", ["local1", "local2", "cloud"])
@pytest.mark.parametrize("field", ["observation", "instruction", "control_mode", "descriptor"])
def test_inflight_request_context_drift_is_closed(monkeypatch, stage, field):
    request = request_scene()
    adapter, points, bodies = adapter_fixture(monkeypatch)

    def mutate():
        if field == "observation":
            request.observation = request_scene().observation
        elif field == "instruction":
            request.user_instruction = "Move the blue cylinder."
        elif field == "control_mode":
            request.control_mode = "PERIODIC_CLOUD_SUPERVISION"
        else:
            adapter.task = adapter.task.model_copy(update={"target_label": "blue cylinder"})

    if stage == "cloud":
        original = adapter.cloud._request_visual

        def callback(*args):
            value = original(*args)
            mutate()
            return value

        monkeypatch.setattr(adapter.cloud, "_request_visual", callback)
    else:
        original = points.point

        def callback(observation, phrase):
            value = original(observation, phrase)
            if len(points.queries) == (1 if stage == "local1" else 2):
                mutate()
            return value

        monkeypatch.setattr(points, "point", callback)
    draft = adapter.plan(request)
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert len(bodies) == (1 if stage == "cloud" else 0)


@pytest.mark.parametrize("variant", ["refusal-first", "refusal-last", "equal", "reason", "escaped"])
def test_skill_json_duplicate_keys_are_rejected(monkeypatch, variant):
    adapter, _, _ = adapter_fixture(monkeypatch)
    skills = json.dumps(SKILLS)
    payloads = {
        "refusal-first": '{"skills":[],"skills":' + skills + "}",
        "refusal-last": '{"skills":' + skills + ',"skills":[]}',
        "equal": '{"skills":' + skills + ',"skills":' + skills + "}",
        "reason": '{"skills":' + skills + ',"reason":"x","reason":"y"}',
        "escaped": '{"skills":[],"sk\\u0069lls":' + skills + "}",
    }
    monkeypatch.setattr(
        adapter.cloud,
        "_request_visual",
        lambda *a: {"choices": [{"message": {"content": payloads[variant]}}]},
    )
    draft = adapter.plan(request_scene())
    assert draft.parsed_json is None and draft.parse_error


def test_cloud_snapshot_provenance_is_recorded(monkeypatch):
    adapter, _, _ = adapter_fixture(monkeypatch)
    draft = adapter.plan(request_scene())
    assert (
        draft.observation_evidence["cloud_model_snapshot_hash"]
        == adapter.cloud.model_snapshot.digest()
    )
    assert draft.observation_evidence["cloud_role_snapshot"] is None
    assert "test-only-cloud-secret" not in json.dumps(draft.observation_evidence)


def near_background_points():
    class NearbyPoints(FixturePoints):
        def point(self, observation, phrase):
            import hashlib

            from cloud_edge_robot_arm.vision.molmo_pointing import (
                BoundPointResult,
                parse_native_point,
            )

            if self.queries:
                return super().point(observation, phrase)
            self.queries.append(phrase)
            raw = '<points coords="1 1 150 360">visible top center of red block</points>'
            return BoundPointResult(
                parse_native_point(raw),
                observation.checksum_sha256,
                observation.evidence()["rgb_sha256"],
                hashlib.sha256(phrase.encode()).hexdigest(),
                {"evidence_scope": "CPU_CONTRACT_FIXTURE"},
            )

    return NearbyPoints()


def test_nearby_point_association_composes_with_original_pipeline(monkeypatch):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    adapter, _, bodies = adapter_fixture(monkeypatch, points=near_background_points())
    response = PlanningPipeline(planner=adapter).process(request_scene())
    assert response.outcome == "PLANNED"
    evidence = response.attempts[0].draft.observation_evidence
    assert evidence["native_results"][0]["normalized_1000"] == (150, 360)
    assert evidence["native_original_pixel_target"] == [12, 23]
    assert evidence["associated_pixel_target"] == [12, 26]
    assert evidence["original_pixel_target"] == [12, 26]
    assert evidence["target_point_association"]["status"] == "ASSOCIATED"
    assert evidence["native_original_pixel_destination"] == [52, 27]
    assert len(bodies) == 1


@pytest.mark.parametrize(
    "damage",
    ["decoy", "partial", "occluded", "edge_occluder", "invalid_edge", "depth", "depth_spike"],
)
def test_association_cannot_bypass_original_geometry_or_tracker(monkeypatch, damage):
    adapter, _, bodies = adapter_fixture(monkeypatch, points=near_background_points())
    draft = adapter.plan(request_scene(damage=damage))
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert bodies == []
    assert draft.observation_evidence["native_original_pixel_target"] == [12, 23]


def refresh_fixture(
    monkeypatch, *, content=None, fresh_transform=None, drift=None, point_hook=None
):
    """One deterministic slow cloud, a true second fixture payload and bound queries."""
    import hashlib
    from types import SimpleNamespace

    import cloud_edge_robot_arm.cloud.planning.pipeline as pipeline_module
    import cloud_edge_robot_arm.vision.grounded_planner as module
    import cloud_edge_robot_arm.vision.tracking as tracking_module
    from cloud_edge_robot_arm.vision.molmo_pointing import BoundPointResult, parse_native_point
    from tests.test_molmo_revalidation import rebuild

    request = request_scene(scene_id="S01_TEST_STATIC")
    state = SimpleNamespace(
        clock=request.observation.captured_at, calls=[], captures=[], queries=[], bindings=[]
    )

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return state.clock if tz else state.clock.replace(tzinfo=None)

    monkeypatch.setattr(module, "_utcnow", lambda: state.clock)
    monkeypatch.setattr(tracking_module, "datetime", Clock)
    monkeypatch.setattr(pipeline_module, "datetime", Clock)

    class Points:
        def point(self, observation, phrase):
            state.queries.append(phrase)
            state.bindings.append(observation.checksum_sha256)
            coords = "150 410" if phrase.startswith("visible top center") else "650 425"
            raw = f'<points coords="1 1 {coords}">support</points>'
            result = BoundPointResult(
                parse_native_point(raw),
                observation.checksum_sha256,
                observation.evidence()["rgb_sha256"],
                hashlib.sha256(phrase.encode()).hexdigest(),
                {"evidence_scope": "CPU_FRESH_CAPTURE_FIXTURE"},
            )
            if point_hook:
                point_hook(state, len(state.queries))
            return result

    cloud, _ = cloud_fixture(monkeypatch)

    def post(path, body):
        from datetime import timedelta

        state.calls.append((path, body))
        state.clock += timedelta(seconds=6)
        if drift:
            drift(state, "cloud")
        return {"choices": [{"message": {"content": content or json.dumps({"skills": SKILLS})}}]}

    monkeypatch.setattr(cloud, "_post", post)

    def capture():
        from datetime import timedelta

        state.clock += timedelta(milliseconds=10)
        fresh = rebuild(request.observation, frame_id="fresh-grounded", captured_at=state.clock)
        # A small actual depth change makes stale versus fresh geometry distinguishable.
        depth = np.asarray(fresh.depth_values(), dtype="<f4")
        depth[26 * 80 + 12] += 0.0001
        fresh = rebuild(fresh, depth_float32_base64=base64.b64encode(depth.tobytes()).decode())
        if fresh_transform:
            fresh = fresh_transform(fresh, state)
        state.captures.append(fresh)
        if drift:
            drift(state, "supplier")
        return fresh

    descriptor = module.GroundingTaskDescriptor(
        instruction=request.user_instruction,
        target_phrase="red block",
        destination_phrase="green region",
        target_label="red block",
    )
    state.adapter = module.MolmoGroundedPlannerAdapter(
        point_provider=Points(),
        cloud=cloud,
        task=descriptor,
        post_cloud_observation_supplier=capture,
    )
    state.request = request
    state.original_json = request.model_dump_json()
    state.cloud = cloud
    return state


def test_slow_cloud_uses_independently_grounded_fresh_frame_and_existing_pipeline(monkeypatch):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    state = refresh_fixture(monkeypatch)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.outcome == "PLANNED" and response.contract is not None
    assert response.validation.passed and not response.attempts[0].repaired
    assert len(state.calls) == len(state.captures) == 1
    assert len(state.queries) == 4
    fresh = state.captures[0]
    evidence = response.attempts[0].draft.observation_evidence
    assert evidence["checksum_sha256"] == fresh.checksum_sha256
    assert evidence["captured_at"] == fresh.captured_at.isoformat()
    assert (
        evidence["cloud_reference"]["checksum_sha256"] == state.request.observation.checksum_sha256
    )
    assert evidence["post_cloud_revalidation"]["status"] == "PASSED"
    assert (
        len(evidence["native_results"]) == len(evidence["cloud_reference"]["native_results"]) == 2
    )
    assert evidence["perception_model_image_count"] == 2
    assert evidence["cloud_model_image_count"] == 0
    assert (
        state.bindings
        == [state.request.observation.checksum_sha256] * 2 + [fresh.checksum_sha256] * 2
    )
    assert evidence["grounded_target"] == fresh.world_point((12, 26)).model_dump()
    assert evidence["grounded_target"] != evidence["cloud_reference"]["grounded_target"]
    assert response.attempts[0].draft.observed_scene.updated_at == fresh.captured_at
    assert response.contract.issued_at >= fresh.captured_at
    assert state.request.model_dump_json() == state.original_json


@pytest.mark.parametrize(
    "content",
    [
        "not-json",
        '{"skills":[],"skills":["HOME"]}',
        '{"skills":[],"reason":NaN}',
        json.dumps({"skills": ["FLY"]}),
        json.dumps({"skills": SKILLS, "issued_at": "override"}),
        json.dumps({"skills": []}),
        json.dumps({"skills": ["GRASP"]}),
        json.dumps({"skills": list(reversed(SKILLS))}),
    ],
)
def test_invalid_or_empty_cloud_skills_never_trigger_new_capture(monkeypatch, content):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    state = refresh_fixture(monkeypatch, content=content)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.contract is None and response.outcome != "PLANNED"
    assert len(state.calls) == 1 and len(state.queries) == 2 and state.captures == []


@pytest.mark.parametrize(
    "variant", ["same_id", "old_time", "pre_cloud", "episode", "checksum", "type", "exception"]
)
def test_supplier_binding_or_acquisition_failure_never_reuses_old_geometry(monkeypatch, variant):
    from datetime import timedelta

    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from tests.test_molmo_revalidation import rebuild

    def change(fresh, state):
        reference = state.request.observation
        if variant == "same_id":
            return rebuild(fresh, frame_id=reference.frame_id)
        if variant == "old_time":
            return rebuild(fresh, captured_at=reference.captured_at)
        if variant == "pre_cloud":
            return rebuild(fresh, captured_at=reference.captured_at + timedelta(seconds=1))
        if variant == "episode":
            return rebuild(fresh, episode_id="new-episode")
        if variant == "checksum":
            return fresh.model_copy(update={"checksum_sha256": reference.checksum_sha256})
        if variant == "type":
            return object()
        raise RuntimeError("fixture capture unavailable")

    state = refresh_fixture(monkeypatch, fresh_transform=change)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.contract is None and response.outcome != "PLANNED"
    assert len(state.calls) == 1 and len(state.queries) == 2
    assert len(state.captures) <= 1
    terminal = response.attempts[0].draft.observation_evidence["post_cloud_revalidation"]
    assert terminal["status"] == "REJECTED"
    assert terminal["reason"] == response.reason


@pytest.mark.parametrize("stage", ["cloud", "supplier"])
@pytest.mark.parametrize(
    "field", ["request", "task", "provider", "supplier", "cloud", "settings", "profile"]
)
def test_inflight_binding_drift_is_closed_before_further_perception(monkeypatch, stage, field):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    def mutate(state, current):
        if current != stage:
            return
        adapter = state.adapter
        if field == "request":
            state.request.capabilities.supported_skills.append("FLY")
        elif field == "task":
            adapter.task = adapter.task.model_copy(update={"target_phrase": "blue block"})
        elif field == "provider":
            adapter.point_provider = object()
        elif field == "supplier":
            adapter.post_cloud_observation_supplier = lambda: state.request.observation
        elif field == "cloud":
            adapter.cloud = object()
        elif field == "profile":
            adapter.cloud.role_snapshot = object()
        else:
            adapter.cloud.timeout_s = 31

    state = refresh_fixture(monkeypatch, drift=mutate)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.contract is None and response.outcome != "PLANNED"
    assert len(state.calls) == 1 and len(state.queries) == 2
    assert len(state.captures) == (1 if stage == "supplier" else 0)


@pytest.mark.parametrize(
    "damage", ["missing", "decoy", "depth", "depth_spike", "wrong_color", "occluded"]
)
def test_fresh_scene_or_depth_change_does_not_create_a_contract(monkeypatch, damage):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    def change(fresh, state):
        return scene(
            "fresh-damaged",
            started=state.clock,
            source="mujoco_camera",
            scene_id="S01_TEST_STATIC",
            damage=damage,
        )

    state = refresh_fixture(monkeypatch, fresh_transform=change)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.contract is None and response.outcome != "PLANNED"
    assert len(state.calls) == len(state.captures) == 1
    assert len(state.queries) == 2


@pytest.mark.parametrize("query", [3, 4])
def test_fresh_ttl_expiration_during_either_query_rejects_contract(monkeypatch, query):
    from datetime import timedelta

    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    def expire(state, index):
        if index == query:
            state.clock += timedelta(seconds=6)

    state = refresh_fixture(monkeypatch, point_hook=expire)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.outcome == "REQUEST_MORE_OBSERVATION" and response.contract is None
    assert len(state.calls) == len(state.captures) == 1 and len(state.queries) == query
    terminal = response.attempts[0].draft.observation_evidence["post_cloud_revalidation"]
    assert terminal["status"] == "REJECTED"
    assert terminal["reason"] == response.reason


def test_expiration_after_candidate_construction_cannot_return_a_stale_draft(monkeypatch):
    from datetime import timedelta

    import cloud_edge_robot_arm.vision.grounded_planner as module
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    state = refresh_fixture(monkeypatch)
    original = module.build_grounded_contract

    def delayed(*args, **kwargs):
        draft = original(*args, **kwargs)
        state.clock += timedelta(seconds=6)
        return draft

    monkeypatch.setattr(module, "build_grounded_contract", delayed)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.outcome == "REQUEST_MORE_OBSERVATION" and response.contract is None
    assert len(state.calls) == len(state.captures) == 1 and len(state.queries) == 4
    terminal = response.attempts[0].draft.observation_evidence["post_cloud_revalidation"]
    assert terminal["status"] == "REJECTED"
    assert terminal["reason"] == response.reason


@pytest.mark.parametrize("which", [3, 4])
def test_fresh_tracker_support_mask_must_match_its_reference_role(monkeypatch, which):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    state = refresh_fixture(monkeypatch)
    original = OpenCVTargetTracker._geometry
    calls = []

    def changed(self, *args, **kwargs):
        geometry, reason = original(self, *args, **kwargs)
        calls.append(1)
        if len(calls) == which and geometry is not None:
            geometry["mask"] = geometry["mask"].copy()
            geometry["mask"][0, 0] = not geometry["mask"][0, 0]
        return geometry, reason

    monkeypatch.setattr(OpenCVTargetTracker, "_geometry", changed)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.contract is None and response.outcome != "PLANNED"
    assert len(state.calls) == len(state.captures) == 1 and len(state.queries) == 4
    terminal = response.attempts[0].draft.observation_evidence["post_cloud_revalidation"]
    assert terminal["status"] == "REJECTED"
    assert terminal["reason"] == response.reason


def test_fresh_native_failure_keeps_terminal_rejection_and_original_error(monkeypatch):
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    state = refresh_fixture(monkeypatch)
    original = state.adapter.point_provider.point

    def unavailable(observation, phrase):
        if len(state.queries) >= 2:
            raise RuntimeError("fresh fixture generation failure")
        return original(observation, phrase)

    monkeypatch.setattr(state.adapter.point_provider, "point", unavailable)
    response = PlanningPipeline(planner=state.adapter).process(state.request)
    assert response.contract is None and response.outcome == "PLANNER_FAILED"
    draft = response.attempts[0].draft
    assert draft.parse_error == "native perception failed: RuntimeError"
    assert draft.observation_evidence["post_cloud_revalidation"]["status"] == "REJECTED"
    assert len(state.calls) == len(state.captures) == 1


@pytest.mark.parametrize("absent_at", [1, 2], ids=["target", "destination"])
def test_native_absence_alias_stops_target_or_destination(monkeypatch, absent_at):
    import hashlib
    from dataclasses import replace

    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
    from cloud_edge_robot_arm.vision.molmo_pointing import parse_native_point

    raw = "There are none.<|im_end|>"

    class AbsencePoints(FixturePoints):
        def point(self, observation, phrase):
            bound = super().point(observation, phrase)
            if len(self.queries) == absent_at:
                return replace(bound, result=parse_native_point(raw))
            return bound

    adapter, points, bodies = adapter_fixture(monkeypatch, points=AbsencePoints())

    def forbidden_cloud(*args, **kwargs):
        raise AssertionError("absence must stop before cloud transport")

    monkeypatch.setattr(adapter.cloud, "_post", forbidden_cloud)
    response = PlanningPipeline(planner=adapter).process(request_scene())
    assert response.outcome == "REQUEST_MORE_OBSERVATION"
    assert response.contract is None and response.dispatch is None
    assert len(points.queries) == absent_at and bodies == []
    evidence = response.attempts[-1].draft.observation_evidence
    assert len(evidence["native_results"]) == absent_at
    assert evidence["native_results"][-1]["status"] == "ABSENT"
    assert evidence["native_results"][-1]["normalized_1000"] is None
    assert evidence["native_results"][-1]["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
