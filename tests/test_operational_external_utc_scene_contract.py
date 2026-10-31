"""R369 contract: `_b_t3_external_utc` must build SceneSummary with the required
`updated_at`, using the same value production passes (the observation's captured_at).

The contract calls the unchanged real helper with real, model-validated
RGBDObservation/TaskContract instances. Only the pipeline clock is fixed.
"""
from __future__ import annotations

import base64
import io
import json
import struct
from datetime import UTC, datetime, timedelta

from PIL import Image
import pytest

from cloud_edge_robot_arm.contracts.models import (
    ControlMode,
    FailurePolicy,
    SafetyConstraints,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_operational_runtime_closure import _b_t3_external_utc

AT = datetime(2026, 10, 26, 0, 0, 0, tzinfo=UTC)


def _png(width: int, height: int, colour: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def _observation() -> RGBDObservation:
    return RGBDObservation.model_validate({
        "frame_id": "r369-frame",
        "captured_at": AT,
        "sim_time_s": 0.0,
        "width": 2,
        "height": 2,
        "rgb_png_base64": base64.b64encode(_png(2, 2, (255, 0, 0))).decode("ascii"),
        "depth_float32_base64": base64.b64encode(struct.pack("<4f", 2.0, 2.0, 2.0, 0.0)).decode("ascii"),
        "intrinsics": [2.0, 2.0, 0.0, 0.0],
        "camera_to_world": [1, 0, 0, 1, 0, 1, 0, 2, 0, 0, 1, 3, 0, 0, 0, 1],
        "source": "rgbd_camera",
        "episode_id": "r369-episode",
        "calibration_version": "r369-calibration",
        "checksum_sha256": "",
    })


def _contract() -> TaskContract:
    return TaskContract(
        task_id="r369-task",
        plan_version=1,
        command_seq=1,
        timestamp=AT,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=AT,
        valid_until=AT + timedelta(seconds=30),
        user_instruction="place the red cube into bin a",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(object_id="red_cube", object_class="cube", target_region_id="bin_a"),
        steps=[TaskStep(step_id="home", skill="HOME", parameters={},
                        expected_duration_ms=10, timeout_ms=100, retry_limit=0)],
        safety_constraints=SafetyConstraints(max_joint_velocity=0.5, max_tcp_velocity=0.15,
                                             minimum_safe_height=0.08, workspace_id="workspace_a",
                                             collision_check_required=True),
        failure_policy=FailurePolicy(local_retry_limit=0, on_timeout="SAFE_STOP",
                                     on_safety_rejection="PAUSE_AND_REPORT",
                                     on_network_loss="SAFE_STOP"),
        completion_criteria=["robot_in_safe_pose"],
    )


def test_external_utc_scene_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.cloud.planning import pipeline

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return AT if tz is None else AT.astimezone(tz)

    monkeypatch.setattr(pipeline, "datetime", FixedClock)
    observation = _observation()
    contract = _contract()
    captured_at = observation.captured_at
    checksum = observation.checksum_sha256

    payload = _b_t3_external_utc(observation, contract, AT)

    rows = payload["scene_boundaries"]
    assert [row["offset_ms"] for row in rows] == [1000, 1001, -5000, -5001]
    assert [row["reason"] is None for row in rows] == [True, False, True, False]
    decision = json.loads(json.dumps(payload["expired_external_decision"], default=str))
    assert decision["status"] == "INVALID"
    assert "decision_future_or_expired" in repr(decision)
    assert observation.captured_at == captured_at
    assert observation.checksum_sha256 == checksum


def test_rgbd_scene_exact_utc_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.cloud.planning import pipeline
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return AT if tz is None else AT.astimezone(tz)

    monkeypatch.setattr(pipeline, "datetime", FixedClock)
    observation = _observation()
    cases = (
        (5000, 999999, True),
        (5000, 1000000, True),
        (5000, 1000001, False),
        (5000, 1001000, False),
        (5000, -4999999, True),
        (5000, -5000000, True),
        (5000, -5000001, False),
        (5000, -5001000, False),
        (1001, -1000999, True),
        (1001, -1001000, True),
        (1001, -1001001, False),
        (1001, -1002000, False),
    )
    for ttl_ms, offset_us, valid in cases:
        payload = observation.model_dump(mode="json")
        payload.update(
            captured_at=(AT + timedelta(microseconds=offset_us)).isoformat(),
            checksum_sha256="",
        )
        external = RGBDObservation.model_validate(payload)
        request = InitialPlanningRequest(
            request_id="rgbd-exact-utc-boundaries",
            user_instruction="place the red cube into bin a",
            observation=external,
            scene=SceneSummary(scene_version=1, updated_at=external.captured_at),
        )
        reason = pipeline.check_scene_sufficiency(request, scene_staleness_ms=ttl_ms)
        assert (reason is None) is valid, ("rgbd", offset_us, ttl_ms, reason)


def test_summary_scene_exact_utc_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    from cloud_edge_robot_arm.cloud.planning import pipeline
    from cloud_edge_robot_arm.cloud.planning.models import (
        InitialPlanningRequest,
        SceneObjectSummary,
        SceneSummary,
        TargetRegionSummary,
    )
    from cloud_edge_robot_arm.contracts import Pose

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return AT if tz is None else AT.astimezone(tz)

    monkeypatch.setattr(pipeline, "datetime", FixedClock)
    cases = (
        (5000, 999999, True),
        (5000, 1000000, True),
        (5000, 1000001, True),
        (5000, 1001000, True),
        (5000, -4999999, True),
        (5000, -5000000, True),
        (5000, -5000001, False),
        (5000, -5001000, False),
        (1001, -1000999, True),
        (1001, -1001000, True),
        (1001, -1001001, False),
        (1001, -1002000, False),
    )
    for ttl_ms, offset_us, valid in cases:
        scene = SceneSummary(
            scene_version=1,
            updated_at=AT + timedelta(microseconds=offset_us),
            objects=[
                SceneObjectSummary(
                    object_id="red_cube",
                    object_class="cube",
                    pose=Pose(x=0.2, y=0.0, z=0.02),
                    pose_confidence=1.0,
                )
            ],
            regions=[
                TargetRegionSummary(
                    region_id="bin_a", center=Pose(x=0.3, y=0.1, z=0.02), radius_m=0.08
                )
            ],
            scene_confidence=1.0,
        )
        request = InitialPlanningRequest(
            request_id="summary-exact-utc-boundaries",
            user_instruction="place the red cube into bin a",
            scene=scene,
        )
        reason = pipeline.check_scene_sufficiency(request, scene_staleness_ms=ttl_ms)
        assert (reason is None) is valid, ("summary", offset_us, ttl_ms, reason)
