"""只读重放原始失败帧；静态几何结果不构成新鲜规划或真实模型复测。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest
from cloud_edge_robot_arm.vision.grounded_planner import (
    GroundingTaskDescriptor,
    MolmoGroundedPlannerAdapter,
)
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter, ground_observation
from cloud_edge_robot_arm.vision.point_association import associate_target_point
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker, _rgb


def main() -> None:
    """原件逐文件核验后只计算静态几何，并验证生产入口仍拒绝过期帧。"""
    root = Path(__file__).resolve().parents[7]
    raw = root / "datasets/model-cache/molmo-grounded-r542-20261110/native-01"
    manifest = json.loads((raw / "raw-manifest.local.json").read_text())
    for row in manifest["files"]:
        data = (raw / row["path"]).read_bytes()
        assert len(data) == row["bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
    request = InitialPlanningRequest.model_validate_json(
        (raw / "raw/capture-01/request.json").read_bytes()
    )
    observation = request.observation
    captured = observation.captured_at.isoformat()
    checksum = observation.checksum_sha256
    original = json.loads((raw / "report.json").read_text())
    assert original["diagnostic_passed"] is False
    native = tuple(original["attempts"][0]["evidence"]["original_pixel_target"])
    destination = tuple(original["attempts"][0]["evidence"]["original_pixel_destination"])
    arguments = dict(
        target_label="red block",
        grasp_profile="mujoco_upright_box_v2",
        destination_pixel=destination,
        evidence={"scope": "OFFLINE_STATIC_DIAGNOSTIC"},
    )
    try:
        ground_observation(request, observation, target_pixel=native, **arguments)
    except ValueError as exc:
        old_reason = str(exc)
    else:
        raise AssertionError("archived native point unexpectedly passed original geometry")
    assert old_reason == original["attempts"][0]["reason"]
    association = associate_target_point(observation, native, target_phrase="red block")
    assert association.pixel == (179, 119)
    measured = ground_observation(request, observation, target_pixel=association.pixel, **arguments)
    # Static diagnostic only: this shell never enters a live pipeline or controller.
    tracker = object.__new__(OpenCVTargetTracker)
    tracker.depth_error_bound_m = None
    tracker.support_z = measured.evidence["top_grasp_support_height_m"]
    rgb = _rgb(observation)
    target, target_reason = tracker._geometry(
        observation, tracker._color(rgb, association.pixel), target=True
    )
    region, region_reason = tracker._geometry(
        observation, tracker._color(rgb, destination), target=False
    )
    assert target is not None and target_reason is None
    assert region is not None and region_reason is None

    class UncalledPoints:
        calls = 0

        def point(self, *args):
            self.calls += 1
            raise AssertionError("stale archive must not invoke perception")

    class UncalledCloud(RGBDPlannerAdapter):
        calls = 0

        def _request_visual(self, *args):
            self.calls += 1
            raise AssertionError("stale archive must not invoke cloud")

    snapshot = ModelConfigSnapshot(
        provider="openai_compatible",
        model="not-invoked",
        endpoint="http://127.0.0.1:11434",
        weight_digest=None,
        quantization=None,
        image_size=(320, 240),
        generation_parameters={"temperature": 0, "num_predict": 512},
        timeout_s=30,
        grasp_profile="mujoco_upright_box_v2",
    )
    cloud = UncalledCloud(
        base_url=snapshot.endpoint,
        provider=snapshot.provider,
        model=snapshot.model,
        model_snapshot=snapshot,
    )
    points = UncalledPoints()
    task = GroundingTaskDescriptor.model_validate_json(
        (raw / "raw/inputs/task-01.json").read_bytes()
    )
    draft = MolmoGroundedPlannerAdapter(point_provider=points, cloud=cloud, task=task).plan(request)
    assert draft.parsed_json["_sentinel"] == "REQUEST_MORE_OBSERVATION"
    assert draft.parsed_json["_reason"] == "capture_time_not_fresh"
    assert points.calls == cloud.calls == 0
    assert observation.captured_at.isoformat() == captured
    assert observation.checksum_sha256 == checksum
    print(
        json.dumps(
            {
                "scope": "OFFLINE_STATIC_DIAGNOSTIC",
                "status": "PASS",
                "raw_files_verified": len(manifest["files"]),
                "raw_bytes_verified": sum(row["bytes"] for row in manifest["files"]),
                "observation_captured_at_unchanged": captured,
                "checksum_unchanged": checksum,
                "original_geometry_rejection": old_reason,
                "association": association.evidence,
                "static_geometry": measured.evidence,
                "static_tracker_target": tracker._public(target),
                "static_tracker_destination": tracker._public(region),
                "live_adapter_archived_frame": draft.parsed_json,
                "model_loads": 0,
                "generations": 0,
                "cloud_calls": 0,
                "hardware_dispatch": False,
                "note": (
                    "Static-only calculations bypass no production gate; "
                    "archived frame remains stale."
                ),
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
