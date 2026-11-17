"""Score exact RGB-bound answers against archived labels and offline production geometry."""
import argparse
import json
import math
import statistics
from pathlib import Path

import numpy as np

from cases import CASES, FRAMES, INSTRUCTION, WORKTREE, rgb_sha, sha, write_json
from run_molmo import replay_observation

ARTIFACT_FILES = ("rgb.png", "observation.json", "depth.f32", "valid_mask.u8", "instance_geom_ids.i32")
GEOMETRY_FRAMES = ("fixed-top", "varied-top")

def fixtures():
    obs, truth, sources = {}, {}, {}
    for frame, folder in FRAMES.items():
        meta = json.loads((folder / "observation.json").read_text())
        obs[frame] = replay_observation(folder)
        image = np.frombuffer((folder / "instance_geom_ids.i32").read_bytes(), dtype="<i4")
        image = image.reshape(obs[frame].height, obs[frame].width)
        labels = {name: int(index) for index, name in meta["instance_labels"].items()}
        truth[frame] = {label: image == labels[label] for label in ("object_geom", "target_region_geom")}
        size = {label: int(mask.sum()) for label, mask in truth[frame].items()}
        if not all(n > 0 for n in size.values()):
            raise ValueError(f"fixture unexpectedly occluded: {frame}")
        sources[frame] = {
            "archive_path": str(folder.relative_to(WORKTREE)),
            "frame_id": obs[frame].frame_id, "checksum_sha256": obs[frame].checksum_sha256,
            "rgb_resolution": [obs[frame].width, obs[frame].height],
            "optical_axis_world_z": obs[frame].camera_to_world[10], "truth_pixel_counts": size,
            "file_sha256": {name: sha((folder / name).read_bytes()) for name in ARTIFACT_FILES},
        }
    return obs, truth, sources

def geometry(frame, obs, pixels):
    from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest, SceneSummary
    from cloud_edge_robot_arm.research.sol_molmo_offline_regression import _historical_clock
    from cloud_edge_robot_arm.vision.planner import ground_observation
    from cloud_edge_robot_arm.vision.point_association import associate_target_point
    from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

    target = pixels[f"{frame}/target"]
    destination = pixels[f"{frame}/destination"]
    if target is None or destination is None:
        return {"status": "NO_POINT_PAIR"}
    request = InitialPlanningRequest(
        request_id=f"robotmanip-probe/{frame}", user_instruction=INSTRUCTION, observation=obs,
        scene=SceneSummary(scene_version=1, updated_at=obs.captured_at),
    )
    stage = "target association"
    report = {"target_pixel": target, "destination_pixel": destination}
    try:
        association = associate_target_point(obs, tuple(target), target_phrase="red block")
        report["target_association"] = association.evidence["status"]
        report["associated_target_pixel"] = list(association.pixel)
        stage = "metric RGB-D grounding"
        grounded = ground_observation(
            request, obs, target_pixel=association.pixel, destination_pixel=tuple(destination),
            target_label="red block", grasp_profile="mujoco_upright_box_v2", evidence={},
        )
        stage = "initial OpenCV tracker"
        with _historical_clock(obs):
            tracker = OpenCVTargetTracker(obs, grounded.evidence)
        report["target_world_xyz_m"] = grounded.evidence["grounded_target"]
        report["destination_world_xyz_m"] = grounded.evidence["grounded_destination"]
        report["tracker_algorithm_sha256"] = tracker.algorithm_sha256
        report["status"] = "ACCEPTED"
    except ValueError as exc:
        report.update(status="REJECTED", stage=stage, reason=str(exc))
    return report

def calculate(path, obs, truth):
    from cloud_edge_robot_arm.vision.messages import model_to_observation_pixel

    result = json.loads(path.read_text())
    rows = result["results"]
    if len(rows) != len(CASES):
        raise ValueError(f"expected {len(CASES)} results: {path}")
    verdicts = []
    pixels = {}
    latencies = []
    for row, (case, frame, phrase, label) in zip(rows, CASES, strict=True):
        if (row["case"], row["frame"], row["phrase"], row["rgb_sha256"]) != (case, frame, phrase, rgb_sha(frame)):
            raise ValueError(f"source binding drift: {case} {path}")
        status = row["status"]
        pixel = None
        if status == "POINT":
            pixel = model_to_observation_pixel(
                tuple(row["normalized_1000"]), obs[frame], coordinate_system="normalized_1000",
            )
        pixels[case] = pixel
        latency = row.get("evidence", {}).get("end_to_end_s")
        if latency is not None:
            latencies.append(latency)
        score = {"case": case, "expected": label or "ABSENT", "status": status,
                 "pixel": pixel, "end_to_end_s": latency}
        if label is None:
            outcome = {"ABSENT": "CORRECT_ABSENCE", "POINT": "FALSE_POINT"}.get(status, status)
        elif pixel is None:
            outcome = "FALSE_ABSENCE" if status == "ABSENT" else status
        else:
            x, y = pixel
            mask = truth[frame][label]
            ys, xs = np.nonzero(mask)
            score["distance_to_expected_support_px"] = math.sqrt(int(((ys-y)**2 + (xs-x)**2).min()))
            outcome = "HIT" if mask[y, x] else "MISS"
        verdicts.append(score | {"outcome": outcome})
    counts = {outcome: sum(row["outcome"] == outcome for row in verdicts)
              for outcome in ("HIT", "MISS", "FALSE_ABSENCE", "CORRECT_ABSENCE", "FALSE_POINT", "INVALID", "ERROR")}
    gates = {frame: geometry(frame, obs[frame], pixels) for frame in GEOMETRY_FRAMES}
    for frame, gate in gates.items():
        if gate["status"] == "ACCEPTED":
            tx, ty = gate["associated_target_pixel"]
            dx, dy = gate["destination_pixel"]
            gate["associated_target_on_expected_geom"] = bool(truth[frame]["object_geom"][ty, tx])
            gate["destination_on_expected_geom"] = bool(truth[frame]["target_region_geom"][dy, dx])
    return {"model": result["model"], "input_result_sha256": sha(path.read_bytes()),
            "present_count": sum(row[3] is not None for row in CASES),
            "absence_count": sum(row[3] is None for row in CASES),
            "counts": counts, "rows": verdicts, "top_down_geometry": gates,
            "latency_seconds": {"min": min(latencies), "median": statistics.median(latencies),
                                "max": max(latencies)} if latencies else None,
            "native_action_results": result.get("action_results")}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("model_results", nargs="+", type=Path)
    args = parser.parse_args()
    obs, truth, sources = fixtures()
    write_json(args.out, {
        "inputs": sources, "tracker_replay_clock": "captured_at + 100ms (offline only)",
        "results": [calculate(p, obs, truth) for p in args.model_results],
    })

if __name__ == "__main__":
    main()
