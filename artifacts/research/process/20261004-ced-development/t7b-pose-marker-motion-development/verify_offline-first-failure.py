"""Read-only post-run replay, scorer and truth-qualified occlusion diagnostic."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from cloud_edge_robot_arm.simulation.mujoco.episode_evaluator import (
    CompletionCriteria, PhysicalSample, evaluate_evidence,
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
        assert hashlib.sha256((HERE / "source" / name).read_bytes()).hexdigest() == digest, name
    summary = load("summary.json")
    physics, actuators, actions = rows("raw-physics.jsonl"), rows("raw-actuators.jsonl"), rows("raw-actions.jsonl")
    assert [r["physics_step"] for r in physics] == list(range(summary["physics_steps"] + 1))
    assert [r["physics_step"] for r in actuators] == list(range(1, summary["physics_steps"] + 1))
    assert len(actions) == summary["executed_framed_actions"] == 9
    commands = load("commands.json")
    assert [r["command_seq"] for r in commands] == list(range(1, len(commands)+1))
    for r in [*physics, *actuators, *commands, *actions]:
        assert r["episode_id"] == summary["episode_id"]
    for previous, current in zip(actions, actions[1:]):
        assert previous["end_step"] == current["start_step"]
        assert previous["command_seq_end"] == current["command_seq_start"]
    assert actions[-1]["end_step"] == summary["physics_steps"]
    samples = [PhysicalSample(**{**r, "self_collision_checked_pairs": tuple(tuple(x) for x in r["self_collision_checked_pairs"])})
               for r in load("physical-samples.json")]
    independent = asdict(evaluate_evidence(samples, CompletionCriteria("object", "target_region"),
                          evaluation_start_step=summary["evaluation_start_step"]))
    assert json.loads(json.dumps(independent)) == summary["outcome"]
    registration = PoseMarkerRegistration(7, .045,
        "2ba368bb5150becd1c021fe52495f3c59bd155f862502ec590b2ecd3a57899e4")
    offline = []
    for folder in sorted((RUN / "frames").iterdir()):
        observation = RGBDObservation.model_validate_json((folder / "observation-full.json").read_text())
        # Replay decoder FIRST with RGBD+registration only. Offline truth is read below.
        estimate = detect_pose_marker(observation, registration)
        serialized = asdict(estimate)
        serialized["captured_at"] = estimate.captured_at.isoformat()
        assert json.loads(json.dumps(serialized)) == json.loads((folder / "marker-estimate.json").read_text())
        truth = min(physics, key=lambda r: abs(r["sim_time_s"]-observation.sim_time_s))
        assert abs(truth["sim_time_s"]-observation.sim_time_s) < 1e-9
        rotation = np.asarray(truth["object_geom_rotation_row_major"]).reshape(3,3)
        center = np.asarray(truth["object_geom_position_m"])
        corners = np.array([[-.0225,.0225,.03505],[.0225,.0225,.03505],
                            [.0225,-.0225,.03505],[-.0225,-.0225,.03505]]) @ rotation.T + center
        transform = np.asarray(observation.camera_to_world).reshape(4,4)
        cam = (corners-transform[:3,3]) @ transform[:3,:3]
        fx,fy,cx,cy = observation.intrinsics
        pixels = np.column_stack((fx*cam[:,0]/cam[:,2]+cx, fy*cam[:,1]/cam[:,2]+cy))
        roi = np.zeros((observation.height,observation.width),np.uint8)
        cv2.fillConvexPoly(roi,np.round(pixels).astype(np.int32),1)
        ys,xs = np.nonzero(roi)
        rays = np.column_stack(((xs-cx)/fx,(ys-cy)/fy,np.ones(len(xs))))
        normal = rotation[:,2] @ transform[:3,:3]
        expected = (normal @ cam[0]) / (rays @ normal)
        actual = np.frombuffer(observation.depth_bytes(), dtype="<f4").reshape(observation.height,observation.width)[ys,xs]
        valid = (actual>0)&np.isfinite(actual)&np.isfinite(expected)&(expected>0)
        foreground = valid & (actual < expected-.005)
        offline.append({"boundary":folder.name, "scope":"OFFLINE_SIMULATOR_TRUTH_PROJECTED_OCCLUSION_DIAGNOSTIC_NOT_ONLINE_EVIDENCE",
            "physics_step":truth["physics_step"], "detector_status":estimate.status,
            "nominal_tag_roi_pixels":len(xs), "available_depth_pixels":int(valid.sum()),
            "measured_foreground_depth_pixels":int(foreground.sum()),
            "foreground_fraction":float(foreground.sum()/len(xs)) if len(xs) else None,
            "foreground_threshold_m":.005, "calibrated_occlusion_error_bound":None,
            "truth_used_by_detector":False})
    (HERE / "offline-occlusion-diagnostic.json").write_text(json.dumps(offline,indent=2)+"\n")
    print("PASS raw byte hashes, source25, episode/step/command/action identity, independent saved-sample scorer and10 decoder replays")
    print(json.dumps(offline,indent=2))


if __name__ == "__main__":
    main()
