"""Prespecify views from archived evidence, then capture once per eligible frozen slot."""

import argparse
import importlib.util
import json
from copy import copy, deepcopy
from pathlib import Path
from time import perf_counter

import numpy as np

from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.servo import save_servo_frame

ROOT = Path(__file__).resolve().parent
REPLAY_RAW = Path("experiments/results/phase9/real-harness-20261118/native-servo-region-replay")
ARCHIVE = REPLAY_RAW / "green"
ORIGIN = ARCHIVE / "component/servo-frames/step-05/sample-0104"
AZIMUTHS = (0, 90, 180, 270)
HEIGHTS = (0.80, 1.05)
ANGLE = 35
MARGIN = 16
PHYSICS_STEP = 3952
SIM_TIME_S = 16.466666666666054

spec = importlib.util.spec_from_file_location(
    "archived_region_diagnostics",
    ROOT.parent / "round-native-servo-region-20261118/diagnose_archived_region.py",
)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


def proposal_basis(rotation, attachment):
    rotation = np.asarray(rotation, dtype=float).reshape(3, 3)
    attachment = np.asarray(attachment, dtype=float).reshape(4, 4)
    attached_rotation = attachment[:3, :3]
    for matrix in (rotation, attached_rotation):
        if (
            not np.isfinite(matrix).all()
            or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-8, rtol=0)
            or not np.isclose(np.linalg.det(matrix), 1, atol=1e-8, rtol=0)
        ):
            raise ValueError("camera proposal requires finite proper rotations")
    if not np.isfinite(attachment).all() or not np.array_equal(attachment[3], [0, 0, 0, 1]):
        raise ValueError("camera proposal requires a finite registered attachment")
    offset = attachment[:3, 3]
    registered_horizontal = float(np.linalg.norm(offset[:2]))
    if registered_horizontal <= 0:
        raise ValueError("camera proposal requires a nonzero registered horizontal offset")
    object_rotation = rotation @ attached_rotation.T
    outward_world = object_rotation @ offset
    horizontal = float(np.linalg.norm(outward_world[:2]))
    if horizontal < registered_horizontal / 2:
        raise ValueError("registered outboard camera bearing is degenerate in world XY")
    return outward_world[:2] / horizontal, object_rotation, outward_world, horizontal


def context(episode):
    assignment = diag.read_json(episode / "scene-assignment.json")
    marker = marker_family(assignment["marker_family_id"])
    if assignment["asset_sha256"] != marker.asset_sha256 or (
        diag.sha(Path(marker.asset_path)) != marker.asset_sha256
    ):
        raise ValueError("probe registration does not match archive and exact asset")
    registration = PoseMarkerRegistration(
        marker_id=marker.marker_id, marker_size_m=marker.marker_size_m,
        dictionary=marker.dictionary, marked_asset_sha256=marker.asset_sha256,
    )
    reference = diag.load_frame(episode / "component/frames/post-cloud")
    planning = diag.read_json(episode / "planning/planning-stage-02.json")
    grounding = planning["attempts"][-1]["draft"]["observation_evidence"]
    tracker = diag.ArchivedReferenceTracker(reference, grounding)
    return marker, registration, tracker


def camera_axes(position, aim):
    backward = position - aim
    backward /= np.linalg.norm(backward)
    right = np.cross([0, 1, 0], backward)
    right /= np.linalg.norm(right)
    up = np.cross(backward, right)
    return np.column_stack((right, -up, -backward))


def preregister(path):
    family, registration, tracker = context(ARCHIVE)
    observation = diag.load_frame(ORIGIN)
    marker = detect_pose_marker(observation, registration, corner_refinement="SUBPIX")
    assert marker.status == "OBSERVED"
    measured_rotation = np.asarray(marker.rotation_marker_to_world).reshape(3, 3)
    bearing, object_rotation, offset_world, horizontal = proposal_basis(
        measured_rotation, family.marker_to_object,
    )
    center = np.asarray(marker.marker_center_world_m)
    marker_corners = np.array([
        center + measured_rotation @ np.array([x, y, 0]) * family.marker_size_m
        for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))
    ])
    region = tracker.destination
    region_corners = np.array([
        [x, y, region["center"][2]] for x in (region["min"][0], region["max"][0])
        for y in (region["min"][1], region["max"][1])
    ])
    features = np.vstack((marker_corners, region_corners))
    aim = (features.max(axis=0) + features.min(axis=0)) / 2
    intrinsics = observation.intrinsics
    fx, fy, cx, cy = intrinsics
    bounds = np.array([observation.width - 1 - MARGIN, observation.height - 1 - MARGIN])
    slots = []
    for azimuth in AZIMUTHS:
        angle = np.deg2rad(azimuth)
        direction = np.array([
            bearing[0] * np.cos(angle) - bearing[1] * np.sin(angle),
            bearing[0] * np.sin(angle) + bearing[1] * np.cos(angle),
        ])
        for height in HEIGHTS:
            distance = (height - aim[2]) * np.tan(np.deg2rad(ANGLE))
            position = np.r_[aim[:2] + direction * distance, height]
            camera = (features - position) @ camera_axes(position, aim)
            reason = None
            if not (-0.1 <= position[0] <= 0.8 and -0.5 <= position[1] <= 0.5
                    and 0.6 <= position[2] <= 2):
                reason = "camera_position_outside_development_workspace"
            elif np.any(camera[:, 2] <= 0):
                reason = "measured_features_behind_camera"
            pixels = camera[:, :2] / camera[:, 2, None] * [fx, fy] + [cx, cy]
            marker_px = pixels[:4]
            sides_px = np.linalg.norm(np.roll(marker_px, -1, axis=0) - marker_px, axis=1)
            side_px = float(sides_px.min())
            if reason is None and (np.any(pixels < MARGIN) or np.any(pixels > bounds)):
                reason = "measured_features_outside_framing_margin"
            if reason is None and side_px < 8:
                reason = "predicted_marker_shortest_side_below_detection_minimum"
            slots.append({
                "slot": len(slots) + 1,
                "preflight": "BLOCKED" if reason else "ELIGIBLE",
                "preflight_reason": reason,
                "azimuth_relative_deg": azimuth,
                "camera_height_m": height,
                "angle_off_vertical_deg": ANGLE,
                "camera_position_m": position.tolist(),
                "camera_look_at_m": aim.tolist(),
                "projected_pixels": pixels.tolist(),
                "projected_marker_min_side_px": side_px,
            })
    binding = {
        "scope": "OFFLINE_PREREGISTERED_CAMERA_COVERAGE",
        "direction_lineage": "registered_object_center_to_marker_displacement",
        "accepted_archive_path": str(ORIGIN),
        "accepted_archive_observation": observation.evidence(),
        "accepted_archive_pair_sha256": {name: diag.sha(ORIGIN / name) for name in (
            "rgb.png", "depth.f32", "valid_mask.u8", "observation.json",
        )},
        "marker_family": family.family_id,
        "marker_asset_sha256": family.asset_sha256,
        "marker_registration_sha256": registration.digest(),
        "marker_to_object": list(family.marker_to_object),
        "marker_center_world_m": center.tolist(),
        "measured_marker_to_world_rotation": measured_rotation.tolist(),
        "derived_object_to_world_rotation": object_rotation.tolist(),
        "outward_world_m": offset_world.tolist(),
        "world_horizontal_offset_m": horizontal,
        "bearing_xy": bearing.tolist(),
        "bearing_degrees": float(np.degrees(np.arctan2(bearing[1], bearing[0]))),
        "region_corners_world_m": region_corners.tolist(),
        "position_limits_m": [[-0.1, 0.8], [-0.5, 0.5], [0.6, 2]],
        "framing_margin_px": MARGIN,
        "slots": slots,
    }
    with path.open("x") as handle:
        handle.write(json.dumps(binding, indent=2, allow_nan=False) + "\n")


def render_frozen(backend, snapshot, preregistration, output):
    """Use a cloned simulator data snapshot after all reconstruction control has closed."""
    started = perf_counter()
    frozen, common_rng = snapshot
    model = backend._model
    assert model is not None and backend._camera is not None
    camera_id = model.camera("rgbd").id
    model_position = model.cam_pos[camera_id].copy()
    model_rotation = model.cam_quat[camera_id].copy()
    frozen_hash = backend._camera._physics_state_hash(frozen)
    _, registration, tracker = context(output.parent)
    accepted = output.parent / "component/servo-frames/step-05/sample-0104"
    archived_matches = {
        name: diag.sha(accepted / name) == preregistration["accepted_archive_pair_sha256"][name]
        for name in ("rgb.png", "depth.f32", "valid_mask.u8")
    }
    assert all(archived_matches.values()), archived_matches
    slots = []
    output.mkdir(exist_ok=False)
    ordinal = 0
    try:
        for slot in preregistration["slots"]:
            if slot["preflight"] != "ELIGIBLE":
                slots.append(slot | {"result": "BLOCKED", "capture_ordinal": None})
                continue
            elapsed = perf_counter() - started
            if elapsed >= 120:
                raise TimeoutError("offline view probe wall budget exhausted")
            capture_started = perf_counter()
            data = copy(frozen)
            position = np.array(slot["camera_position_m"])
            aim = np.array(slot["camera_look_at_m"])
            optical = camera_axes(position, aim)
            model.cam_pos[camera_id] = position
            backend._mujoco.mju_mat2Quat(
                model.cam_quat[camera_id], (optical @ np.diag([1, -1, -1])).ravel(),
            )
            backend._mujoco.mj_camlight(model, data)
            rng = np.random.default_rng()
            rng.bit_generator.state = deepcopy(common_rng)
            frame = backend._camera.capture(
                data, rng=rng, noise_std_m=backend._sensor_noise_std_m,
                scene_id=backend._scenario.scenario_id, episode_id=backend._episode_id,
            )
            ordinal += 1
            assert backend._camera._physics_state_hash(data) == frozen_hash
            assert frame.sim_time_s == SIM_TIME_S
            directory = output / f"slot-{slot['slot']:02d}"
            save_servo_frame(
                observation_from_sensor_frame(frame, source="mujoco_camera", png_compress_level=0),
                directory,
            )
            diagnostic = diag.describe_frame(directory, tracker, registration, output)
            passed = (
                diagnostic["marker_status"] == "OBSERVED"
                and diagnostic["strict_region_rejection"] is None
            )
            slots.append(slot | {
                "result": "VALID" if passed else "REJECTED",
                "capture_ordinal": ordinal,
                "shared_rng_before": True,
                "rng_after": rng.bit_generator.state,
                "elapsed_s": perf_counter() - capture_started,
                "diagnostic": diagnostic,
            })
    finally:
        model.cam_pos[camera_id] = model_position
        model.cam_quat[camera_id] = model_rotation
    assert len(slots) == 8 and ordinal <= 8
    result = {
        "scope": "OFFLINE_FROZEN_MUJOCO_CURRENT_VIEW_COVERAGE",
        "physics_step": PHYSICS_STEP,
        "sim_time_s": SIM_TIME_S,
        "frozen_physics_state_sha256": frozen_hash,
        "common_rng_before_each_candidate": common_rng,
        "depth_noise_std_m": backend._sensor_noise_std_m,
        "reconstructed_accepted_archive_pair_matches": archived_matches,
        "reconstructed_accepted_observation": diag.load_frame(accepted).evidence(),
        "candidate_captures": ordinal,
        "elapsed_s": perf_counter() - started,
        "slots": slots,
    }
    with (output / "probe-result.json").open("x") as handle:
        handle.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preregistration", type=Path)
    preregister(parser.parse_args().preregistration)
