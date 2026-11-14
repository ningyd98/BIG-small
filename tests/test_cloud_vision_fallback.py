"""Cloud image candidates never substitute for current original-depth evidence."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_molmo_grounded_planner import (
    SKILLS,
    FixturePoints,
    cloud_fixture,
)
from tests.test_molmo_grounded_planner import request_scene as grounded_request_scene

CORE = SKILLS[1:-1]
REPLY = {
    "action": "CANDIDATE",
    "target_normalized_1000": [150, 410],
    "destination_normalized_1000": [650, 425],
    "skills": CORE,
    "reason": "visible supports; local geometry must validate",
}


def request_scene(**kwargs):
    return grounded_request_scene(scene_id="cloud-fallback-test", **kwargs)


def adapter(monkeypatch, *, reply=None, points=None, enabled=True, **cloud_kwargs):
    from cloud_edge_robot_arm.vision.grounded_planner import (
        GroundingTaskDescriptor,
        MolmoGroundedPlannerAdapter,
    )

    cloud, bodies = cloud_fixture(monkeypatch, reply=reply or copy.deepcopy(REPLY), **cloud_kwargs)
    points = points or FixturePoints(status="ABSENT")
    result = MolmoGroundedPlannerAdapter(
        point_provider=points,
        cloud=cloud,
        task=GroundingTaskDescriptor(
            instruction="Move the red block to the green region.",
            target_phrase="red block",
            destination_phrase="green region",
            target_label="red block",
        ),
        worker_owned_refresh=True,
        component_diagnostic=True,
        cloud_vision_fallback=enabled,
    )
    return result, points, bodies


def fresh_request(request, **changes):
    values = request.observation.model_dump()
    values.update(
        frame_id="worker-new-exposure", observation_id="", checksum_sha256="",
        captured_at=datetime.now(UTC),
    )
    values.update(changes)
    return request.model_copy(update={"observation": RGBDObservation.model_validate(values)})


def test_absent_native_target_recovers_only_after_fresh_local_geometry(monkeypatch):
    planner, points, bodies = adapter(monkeypatch)
    request = request_scene()
    first = planner.plan(request)
    assert first.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert planner.awaiting_owned_refresh
    assert len(bodies) == 1
    images = [p for m in bodies[0]["messages"] if isinstance(m["content"], list)
              for p in m["content"] if p["type"] == "image_url"]
    assert images
    assert base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1]) == base64.b64decode(
        request.observation.rgb_png_base64
    )
    result = PlanningPipeline(planner=planner).process(fresh_request(request))
    assert result.outcome == "PLANNED"
    evidence = result.attempts[-1].draft.observation_evidence
    assert evidence["grounding_point_source"] == "CLOUD_VISION_CANDIDATE"
    assert evidence["original_pixel_target"] == [12, 26]
    assert evidence["post_cloud_revalidation"]["status"] == "PASSED"
    assert evidence["cloud_vision_fallback"]["local_failure"] == "native_target_absent_or_invalid"
    assert evidence["cloud_model_image_count"] == len(images)
    assert len(points.queries) == 1 and len(bodies) == 1
    assert planner.plan(fresh_request(request)).parse_error == "owned planning budget exhausted"


def test_enabled_route_keeps_successful_local_plan_text_only(monkeypatch):
    from tests.test_sol_molmo_worker_integration import RGBPointFixture

    planner, _, bodies = adapter(
        monkeypatch, points=RGBPointFixture(), reply={"skills": CORE, "reason": "normal"}
    )
    request = request_scene()
    planner.plan(request)
    assert planner.awaiting_owned_refresh
    assert all(isinstance(m["content"], str) for m in bodies[0]["messages"])
    assert PlanningPipeline(planner=planner).process(fresh_request(request)).outcome == "PLANNED"


def test_disabled_route_preserves_absence_without_cloud_request(monkeypatch):
    planner, _, bodies = adapter(monkeypatch, enabled=False)
    draft = planner.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert not planner.awaiting_owned_refresh and not bodies


@pytest.mark.parametrize("mismatch", ["observation", "rgb", "query"])
def test_native_binding_violation_never_sends_images(monkeypatch, mismatch):
    planner, _, bodies = adapter(monkeypatch, points=FixturePoints(mismatch=mismatch))
    planner.plan(request_scene())
    assert not bodies and not planner.awaiting_owned_refresh


@pytest.mark.parametrize("error", [
    RuntimeError("native inference requires a dedicated process main thread"),
    RuntimeError("native inference cannot replace an existing deadline"),
    RuntimeError("native generation budget exhausted"),
    RuntimeError("unknown native execution failure"),
    OSError("native evidence storage unavailable"),
])
def test_native_execution_or_io_failure_never_sends_images(monkeypatch, error):
    class FailedPoints(FixturePoints):
        def point(self, observation, phrase):
            raise error

    planner, _, bodies = adapter(monkeypatch, points=FailedPoints())
    draft = planner.plan(request_scene())
    assert not bodies and not planner.awaiting_owned_refresh
    assert draft.parse_error == f"native perception failed: {type(error).__name__}"


def test_native_inference_timeout_can_request_one_cloud_candidate(monkeypatch):
    class TimedOutPoints(FixturePoints):
        def point(self, observation, phrase):
            raise TimeoutError("Molmo native operation deadline exceeded")

    planner, _, bodies = adapter(monkeypatch, points=TimedOutPoints())
    planner.plan(request_scene())
    assert len(bodies) == 1 and planner.awaiting_owned_refresh


@pytest.mark.parametrize("status", ["ABSENT", "INVALID"])
def test_inconsistent_native_status_never_sends_images(monkeypatch, status):
    class InconsistentPoints(FixturePoints):
        def point(self, observation, phrase):
            bound = super().point(observation, phrase)
            return replace(bound, result=replace(
                bound.result, status=status, normalized_1000=None, object_index=None
            ))

    planner, _, bodies = adapter(monkeypatch, points=InconsistentPoints())
    draft = planner.plan(request_scene())
    assert not bodies and not planner.awaiting_owned_refresh
    assert draft.parsed_json["_reason"] == "native_point_raw_result_mismatch"


def test_legitimate_native_output_cap_can_request_one_cloud_candidate(tmp_path, monkeypatch):
    from tests.test_molmo_pointing import native_fixture

    provider, _, _, _ = native_fixture(tmp_path, monkeypatch, cap=True)
    planner, _, bodies = adapter(monkeypatch, points=provider)
    planner.plan(request_scene())
    assert len(bodies) == 1 and planner.awaiting_owned_refresh
    assert provider.generation_calls_started == 1


def test_native_invalid_grammar_can_request_one_cloud_candidate(monkeypatch):
    planner, _, bodies = adapter(monkeypatch, points=FixturePoints(status="INVALID"))
    planner.plan(request_scene())
    assert len(bodies) == 1 and planner.awaiting_owned_refresh


def test_expired_input_never_sends_images(monkeypatch):
    planner, _, bodies = adapter(monkeypatch)
    request = fresh_request(request_scene(), captured_at=datetime.now(UTC) - timedelta(seconds=10))
    draft = planner.plan(request)
    assert draft.parsed_json["_reason"] == "capture_time_not_fresh"
    assert not bodies


@pytest.mark.parametrize("change", [
    {"target_normalized_1000": [1001, 410]},
    {"target_normalized_1000": [True, 410]},
    {"target_normalized_1000": [150.0, 410]},
    {"target_normalized_1000": ["150", 410]},
    {"destination_normalized_1000": None},
    {"target_pose": {"x": 0.45, "y": 0, "z": 0.07}},
    {"confidence": 0.99},
    {"skills": ["GRASP"]},
])
def test_invalid_cloud_candidate_cannot_create_pending_execution(monkeypatch, change):
    reply = copy.deepcopy(REPLY)
    reply.update(change)
    planner, _, bodies = adapter(monkeypatch, reply=reply)
    result = planner.plan(request_scene())
    assert result.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert not planner.awaiting_owned_refresh and len(bodies) == 1


@pytest.mark.parametrize("action", ["REOBSERVE", "ABSENT"])
def test_cloud_refusal_stops_without_retry(monkeypatch, action):
    reply = {"action": action, "target_normalized_1000": None,
             "destination_normalized_1000": None, "skills": [], "reason": "need another view"}
    planner, _, bodies = adapter(monkeypatch, reply=reply)
    draft = planner.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert not planner.awaiting_owned_refresh
    assert len(bodies) == 1


@pytest.mark.parametrize("damage,reason", [
    ("edge_occluder", "target_outer_boundary_depth_unresolved"),
    ("depth", "invalid original depth"),
    ("decoy", "color_identity_ambiguous"),
])
def test_cloud_candidate_cannot_bypass_bad_original_geometry(monkeypatch, damage, reason):
    planner, _, bodies = adapter(monkeypatch)
    request = request_scene(damage=damage)
    planner.plan(request)
    result = PlanningPipeline(planner=planner).process(fresh_request(request))
    assert result.outcome != "PLANNED" and result.contract is None
    assert reason in result.reason
    assert len(bodies) == 1


@pytest.mark.parametrize("change", ["reuse", "episode", "rgb", "calibration"])
def test_cloud_candidate_rejects_changed_or_reused_worker_frame(monkeypatch, change):
    planner, _, bodies = adapter(monkeypatch)
    request = request_scene()
    planner.plan(request)
    if change == "reuse":
        fresh = request
    elif change == "episode":
        fresh = fresh_request(request, episode_id="another-episode")
    elif change == "calibration":
        fresh = fresh_request(request, calibration_version="another-calibration")
    else:
        fresh = fresh_request(request)
        changed = request_scene(damage="wrong_color").observation
        fresh = fresh_request(request, rgb_png_base64=changed.rgb_png_base64)
    result = PlanningPipeline(planner=planner).process(fresh)
    assert result.outcome != "PLANNED" and result.contract is None
    assert len(bodies) == 1


def test_cloud_images_still_require_paid_permission(monkeypatch):
    planner, _, bodies = adapter(monkeypatch, allow_paid=False)
    result = planner.plan(request_scene())
    assert result.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert not planner.awaiting_owned_refresh and not bodies


def test_cloud_timeout_stops_without_retry(monkeypatch):
    planner, _, bodies = adapter(monkeypatch, fail=True)
    planner.plan(request_scene())
    assert not planner.awaiting_owned_refresh and len(bodies) == 1
    assert planner.plan(request_scene()).parse_error == "owned planning budget exhausted"
    assert len(bodies) == 1


def test_cloud_reply_after_five_seconds_uses_new_worker_capture(monkeypatch):
    planner, _, bodies = adapter(monkeypatch, after=lambda: time.sleep(5.05))
    request = request_scene()
    planner.plan(request)
    assert (datetime.now(UTC) - request.observation.captured_at).total_seconds() > 5
    assert planner.awaiting_owned_refresh
    result = PlanningPipeline(planner=planner).process(fresh_request(request))
    assert result.outcome == "PLANNED", result.reason
    assert len(bodies) == 1


def test_fallback_flag_changed_during_call_cannot_create_pending_plan(monkeypatch):
    planner, _, bodies = adapter(monkeypatch)
    original = planner.cloud._request_visual

    def changed(*args):
        response = original(*args)
        planner.cloud_vision_fallback = False
        return response

    monkeypatch.setattr(planner.cloud, "_request_visual", changed)
    draft = planner.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert not planner.awaiting_owned_refresh and len(bodies) == 1


def test_duplicate_cloud_candidate_json_is_rejected(monkeypatch):
    planner, _, bodies = adapter(monkeypatch)
    original = planner.cloud._request_visual

    def duplicate(*args):
        response = original(*args)
        raw = json.dumps(REPLY)
        response["choices"][0]["message"]["content"] = raw[:-1] + ',"action":"REOBSERVE"}'
        return response

    monkeypatch.setattr(planner.cloud, "_request_visual", duplicate)
    draft = planner.plan(request_scene())
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert not planner.awaiting_owned_refresh and len(bodies) == 1


def test_crop_is_original_rgb_with_explicit_full_image_mapping(monkeypatch):
    planner, _, bodies = adapter(monkeypatch, points=FixturePoints())
    request = request_scene(damage="edge_occluder")
    first = planner.plan(request)
    audit = first.observation_evidence["cloud_vision_fallback"]
    images = [part for message in bodies[0]["messages"] if isinstance(message["content"], list)
              for part in message["content"] if part["type"] == "image_url"]
    assert len(images) == audit["image_count"] == 2
    crop = audit["images"][1]
    assert crop["full_image_box_xyxy"] == [0, 0, 61, 64]
    crop_bytes = base64.b64decode(images[1]["image_url"]["url"].split(",", 1)[1])
    assert hashlib.sha256(crop_bytes).hexdigest() == crop["sha256"]
    with Image.open(io.BytesIO(base64.b64decode(request.observation.rgb_png_base64))) as source:
        with Image.open(io.BytesIO(crop_bytes)) as selected:
            assert selected.size == (61, 64)
            assert selected.tobytes() == source.crop((0, 0, 61, 64)).tobytes()
