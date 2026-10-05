"""Read-only post-run replay, scorer and truth-qualified occlusion diagnostic."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria,
    PhysicalSample,
    evaluate_evidence,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker

HERE = Path(__file__).resolve().parent
RUN = HERE / "attempt-1"


def load(name):
    return json.loads((RUN / name).read_text())


def rows(name):
    return [json.loads(line) for line in (RUN / name).read_text().splitlines()]


def main():
    for name, digest in load("raw-hashes.json").items():
        assert hashlib.sha256((RUN / name).read_bytes()).hexdigest() == digest, name
    for name, digest in json.loads((HERE / "source-hashes.json").read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    summary = load("summary.json")
    physics, actuators, actions = (
        rows("raw-physics.jsonl"),
        rows("raw-actuators.jsonl"),
        rows("raw-actions.jsonl"),
    )
    assert [r["physics_step"] for r in physics] == list(range(summary["physics_steps"] + 1))
    assert [r["physics_step"] for r in actuators] == list(range(1, summary["physics_steps"] + 1))
    assert len(actions) == summary["executed_framed_actions"] == 9
    commands = load("commands.json")
    assert [r["command_seq"] for r in commands] == list(range(1, len(commands) + 1))
    for r in [*physics, *actuators, *commands, *actions]:
        assert r["episode_id"] == summary["episode_id"]
    for previous, current in zip(actions[:-1], actions[1:], strict=True):
        assert previous["end_step"] == current["start_step"]
        assert previous["command_seq_end"] == current["command_seq_start"]
    assert actions[-1]["end_step"] == summary["physics_steps"]
    samples = [
        PhysicalSample(
            **{
                **r,
                "self_collision_checked_pairs": tuple(
                    tuple(x) for x in r["self_collision_checked_pairs"]
                ),
            }
        )
        for r in load("physical-samples.json")
    ]
    independent = asdict(
        evaluate_evidence(
            samples,
            CompletionCriteria("object", "target_region"),
            evaluation_start_step=summary["evaluation_start_step"],
        )
    )
    assert json.loads(json.dumps(independent)) == summary["outcome"]
    registration = PoseMarkerRegistration(
        7, 0.045, "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"
    )
    offline = []
    for folder in sorted((RUN / "frames").iterdir()):
        observation = RGBDObservation.model_validate_json(
            (folder / "observation-full.json").read_text()
        )
        # Replay decoder FIRST with RGBD+registration only. Offline truth is read below.
        estimate = detect_pose_marker(observation, registration)
        serialized = asdict(estimate)
        serialized["captured_at"] = estimate.captured_at.isoformat()
        assert json.loads(json.dumps(serialized)) == json.loads(
            (folder / "marker-estimate.json").read_text()
        )
        truth = min(physics, key=lambda r: abs(r["sim_time_s"] - observation.sim_time_s))
        assert abs(truth["sim_time_s"] - observation.sim_time_s) < 1e-9
        rotation = np.asarray(truth["object_geom_rotation_row_major"]).reshape(3, 3)
        center = np.asarray(truth["object_geom_position_m"])
        corners = (
            np.array(
                [
                    [0.0775, 0.0225, 0.03505],
                    [0.1225, 0.0225, 0.03505],
                    [0.1225, -0.0225, 0.03505],
                    [0.0775, -0.0225, 0.03505],
                ]
            )
            @ rotation.T
            + center
        )
        transform = np.asarray(observation.camera_to_world).reshape(4, 4)
        cam = (corners - transform[:3, 3]) @ transform[:3, :3]
        fx, fy, cx, cy = observation.intrinsics
        pixels = np.column_stack((fx * cam[:, 0] / cam[:, 2] + cx, fy * cam[:, 1] / cam[:, 2] + cy))
        roi = np.zeros((observation.height, observation.width), np.uint8)
        cv2.fillConvexPoly(roi, np.round(pixels).astype(np.int32), 1)
        ys, xs = np.nonzero(roi)
        rays = np.column_stack(((xs - cx) / fx, (ys - cy) / fy, np.ones(len(xs))))
        normal = rotation[:, 2] @ transform[:3, :3]
        expected = (normal @ cam[0]) / (rays @ normal)
        actual = np.frombuffer(
            base64.b64decode(observation.depth_float32_base64), dtype="<f4"
        ).reshape(observation.height, observation.width)[ys, xs]
        valid = (actual > 0) & np.isfinite(actual) & np.isfinite(expected) & (expected > 0)
        foreground = valid & (actual < expected - 0.005)
        marker_truth = rotation @ np.array([0.1, 0.0, 0.03505]) + center
        marker_center_error = None
        inferred_object_center_error = None
        rotation_error_rad = None
        if estimate.status == "OBSERVED":
            observed_rotation = np.asarray(estimate.rotation_marker_to_world).reshape(3, 3)
            observed_center = np.asarray(estimate.marker_center_world_m)
            marker_center_error = float(np.linalg.norm(observed_center - marker_truth))
            inferred_center = observed_center - observed_rotation @ np.array([0.1, 0.0, 0.03505])
            inferred_object_center_error = float(np.linalg.norm(inferred_center - center))
            rotation_error_rad = float(
                np.arccos(np.clip((np.trace(rotation.T @ observed_rotation) - 1) / 2, -1, 1))
            )
        offline.append(
            {
                "boundary": folder.name,
                "scope": (
                    "OFFLINE_SIMULATOR_TRUTH_PROJECTED_OCCLUSION_DIAGNOSTIC_NOT_ONLINE_EVIDENCE"
                ),
                "physics_step": truth["physics_step"],
                "detector_status": estimate.status,
                "nominal_tag_roi_pixels": len(xs),
                "available_depth_pixels": int(valid.sum()),
                "measured_foreground_depth_pixels": int(foreground.sum()),
                "foreground_fraction": float(foreground.sum() / len(xs)) if len(xs) else None,
                "foreground_threshold_m": 0.005,
                "calibrated_occlusion_error_bound": None,
                "truth_used_by_detector": False,
                "marker_center_residual_m": marker_center_error,
                "inferred_object_center_residual_m": inferred_object_center_error,
                "rotation_residual_rad": rotation_error_rad,
                "metric_residual_scope": (
                    "ONE_EXCLUDED_DEVELOPMENT_EPISODE_DIAGNOSTIC_NOT_CALIBRATED_BOUND"
                ),
            }
        )
    (HERE / "offline-occlusion-diagnostic.json").write_text(json.dumps(offline, indent=2) + "\n")
    previous = HERE.parent / "t7b-pose-marker-motion-development" / "attempt-1"
    old_physics = [
        json.loads(line) for line in (previous / "raw-physics.jsonl").read_text().splitlines()
    ]
    assert len(old_physics) == len(physics)
    same_physical_trajectory = all(
        a["physics_step"] == b["physics_step"]
        and a["object_geom_position_m"] == b["object_geom_position_m"]
        and a["object_geom_rotation_row_major"] == b["object_geom_rotation_row_major"]
        and a["joint_positions_rad"] == b["joint_positions_rad"]
        for a, b in zip(old_physics, physics, strict=True)
    )
    writeback = {
        "status": "PASS",
        "source_bytes_match": True,
        "raw_bytes_match": True,
        "episode_step_command_action_identity": True,
        "independent_score_matches": True,
        "strict_decoder_replays": len(offline),
        "observed_frames": sum(r["detector_status"] == "OBSERVED" for r in offline),
        "physics_steps": summary["physics_steps"],
        "controller_commands": len(commands),
        "actions": len(actions),
        "exact_prior_centered_marker_physical_trajectory": same_physical_trajectory,
        "max_marker_center_residual_m": max(
            (
                r["marker_center_residual_m"]
                for r in offline
                if r["marker_center_residual_m"] is not None
            ),
            default=None,
        ),
        "max_inferred_object_center_residual_m": max(
            (
                r["inferred_object_center_residual_m"]
                for r in offline
                if r["inferred_object_center_residual_m"] is not None
            ),
            default=None,
        ),
        "max_rotation_residual_rad": max(
            (r["rotation_residual_rad"] for r in offline if r["rotation_residual_rad"] is not None),
            default=None,
        ),
        "formal_accepted": False,
        "calibrated_bounds": None,
        "continuous_motion": "NOT_CERTIFIED",
    }
    (HERE / "offline-verification.json").write_text(json.dumps(writeback, indent=2) + "\n")
    print(json.dumps(writeback, indent=2))
    print(json.dumps(offline, indent=2))


if __name__ == "__main__":
    main()
