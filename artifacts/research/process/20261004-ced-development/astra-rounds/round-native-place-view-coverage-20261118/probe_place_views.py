"""Freeze the failed PLACE state and check two analytically ranked offline views."""

import argparse
import json
import sys
from copy import copy, deepcopy
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import mujoco
import numpy as np

from cloud_edge_robot_arm.research.sol_molmo_components import _current_transport_view_proposals
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from cloud_edge_robot_arm.vision.pose_markers import detect_pose_marker
from cloud_edge_robot_arm.vision.servo import save_servo_frame

previous_round = Path(__file__).resolve().parent.parent / "round-native-view-reference-20261118"
sys.path.insert(0, str(previous_round))
from probe_current_views import camera_axes, context, diag  # noqa: E402

ARCHIVE = Path("experiments/results/phase9/real-harness-20261118/native-view-coverage-replay/green")
ACCEPTED = Path("component/servo-frames/step-06/sample-0013")
STEP = 4328
SIM_TIME = 18.03333333333263
PAIR = ("rgb.png", "depth.f32", "valid_mask.u8")


def save_json(path, data):
    with path.open("x") as handle:
        handle.write(json.dumps(data, indent=2, allow_nan=False) + "\n")


def register(path):
    family, registration, tracker = context(ARCHIVE)
    observation = diag.load_frame(ARCHIVE / ACCEPTED)
    estimate = detect_pose_marker(observation, registration, corner_refinement="SUBPIX")
    episode = diag.read_json(ARCHIVE / "component/episode.json")
    accepted = episode["actions"][5]["visual_servo"]["visual_samples"][-1]
    assert accepted["checksum_sha256"] == observation.checksum_sha256
    assert episode["actions"][5]["visual_servo"]["control_samples"][-1]["physics_step"] == 4320
    feedback = diag.read_json(ARCHIVE / "component/robot-feedback.json")
    proprioception = next(row for row in feedback if row["physics_step"] == 4320)
    model = mujoco.MjModel.from_xml_path(family.asset_path)
    data = mujoco.MjData(model)
    data.qpos[:7] = proprioception["joint_positions_rad"]
    data.qpos[7:9] = proprioception["finger_positions_m"]
    mujoco.mj_forward(model, data)
    planning = diag.read_json(ARCHIVE / "planning/planning-stage-02.json")
    evidence = planning["attempts"][-1]["draft"]["observation_evidence"]
    proposals = _current_transport_view_proposals(
        observation, estimate, tracker, family.family_id,
        SimpleNamespace(_model=model, _data=data), evidence["estimated_object_height_m"],
    )
    ordered = []
    for proposal in proposals["ranked"]:
        position = proposal["camera_position_m"]
        if not any(np.allclose(position, p["camera_position_m"], atol=1e-9, rtol=0)
                   for p in ordered):
            ordered.append(proposal)
        if len(ordered) == 2:
            break
    save_json(path, {
        "scope": "OFFLINE_PREREGISTERED_PLACE_VIEW_COVERAGE",
        "source_path": str(ARCHIVE / ACCEPTED),
        "accepted_frame_sha256": {
            name: diag.sha(ARCHIVE / ACCEPTED / name) for name in (*PAIR, "observation.json")
        },
        "accepted_observation": observation.evidence(),
        "fk_only": {"joint_positions_rad": proprioception["joint_positions_rad"],
                    "finger_positions_m": proprioception["finger_positions_m"]},
        "ranked_proposal": proposals,
        "preregistered": ordered,
    })


def render(backend, frozen, rng_state, preregistration, output):
    started = perf_counter()
    root = output.parent
    reconstructed_matches = {
        name: diag.sha(root / ACCEPTED / name) == preregistration["accepted_frame_sha256"][name]
        for name in PAIR
    }
    assert all(reconstructed_matches.values()), reconstructed_matches
    _, registration, tracker = context(root)
    model = backend._model
    camera_id = model.camera("rgbd").id
    original_position = model.cam_pos[camera_id].copy()
    original_rotation = model.cam_quat[camera_id].copy()
    state_hash = backend._camera._physics_state_hash(frozen)
    output.mkdir(exist_ok=False)
    slots = []
    try:
        for index, proposal in enumerate(preregistration["preregistered"], start=1):
            assert index <= 2 and perf_counter() - started < 120
            began = perf_counter()
            data = copy(frozen)
            position = np.array(proposal["camera_position_m"])
            aim = np.array(proposal["camera_look_at_m"])
            model.cam_pos[camera_id] = position
            optical = camera_axes(position, aim)
            backend._mujoco.mju_mat2Quat(
                model.cam_quat[camera_id], (optical @ np.diag([1, -1, -1])).ravel(),
            )
            backend._mujoco.mj_camlight(model, data)
            rng = np.random.default_rng()
            rng.bit_generator.state = deepcopy(rng_state)
            frame = backend._camera.capture(
                data, rng=rng, noise_std_m=backend._sensor_noise_std_m,
                scene_id=backend._scenario.scenario_id, episode_id=backend._episode_id,
            )
            assert backend._camera._physics_state_hash(data) == state_hash
            assert frame.sim_time_s == SIM_TIME
            destination = output / f"rank-{index:02d}"
            save_servo_frame(
                observation_from_sensor_frame(frame, source="mujoco_camera", png_compress_level=0),
                destination,
            )
            diagnostic = diag.describe_frame(destination, tracker, registration, output)
            valid = (
                diagnostic["marker_status"] == "OBSERVED"
                and diagnostic["strict_region_rejection"] is None
            )
            slots.append(proposal | {
                "capture_ordinal": index, "result": "VALID" if valid else "REJECTED",
                "rng_after": rng.bit_generator.state,
                "elapsed_s": perf_counter() - began, "diagnostic": diagnostic,
            })
    finally:
        model.cam_pos[camera_id] = original_position
        model.cam_quat[camera_id] = original_rotation
    save_json(output / "probe-result.json", {
        "scope": "OFFLINE_FROZEN_PLACE_VIEWS_NO_LIVE_AUTHORITY",
        "physics_step": STEP, "sim_time_s": SIM_TIME, "frozen_state_sha256": state_hash,
        "common_rng_before_each_candidate": rng_state,
        "depth_noise_std_m": backend._sensor_noise_std_m,
        "reconstructed_accepted_frame_matches": reconstructed_matches,
        "reconstructed_accepted_observation": diag.load_frame(root / ACCEPTED).evidence(),
        "elapsed_s": perf_counter() - started, "slots": slots,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preregistered", type=Path)
    register(parser.parse_args().preregistered)
