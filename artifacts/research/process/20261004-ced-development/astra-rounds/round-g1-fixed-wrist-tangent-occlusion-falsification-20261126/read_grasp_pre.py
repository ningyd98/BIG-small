"""Rebuild the frozen grid-04 closure evidence and one conditional tangent pose."""

import gzip
import hashlib
import inspect
import json
from pathlib import Path

import numpy as np
from scripts.graduation import (
    g1_complete_cv_angle,
    g1_complete_cv_geometry,
    g1_complete_cv_optical_identity,
    g1_visibility_vision,
)

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def main():
    plan = read(HERE / "plan.json")
    archive = ROOT / plan["grasp_archive"]
    generation = plan["runtime_manifest_sha256"]
    runtime = (
        ROOT
        / "experiments/results/g1-complete-cv-repair-20261125/builds"
        / generation
        / "runtime-source"
    )
    manifest = runtime / "runtime-build.json"
    require(sha(manifest) == generation, "frozen runtime manifest changed")
    source_map = read(manifest)["runtime_files_sha256"]
    for directory, key in (
        (archive, "grasp_archive_sha256"),
        (runtime, "runtime_relative_source_sha256"),
        (HERE.parent, "round_sources_relative_to_astra_rounds_sha256"),
    ):
        for item, expected in plan[key].items():
            require(sha(directory / item) == expected, f"changed registered input: {item}")
    for module in (
        g1_complete_cv_angle,
        g1_complete_cv_geometry,
        g1_complete_cv_optical_identity,
        g1_visibility_vision,
    ):
        source = Path(inspect.getsourcefile(module)).resolve()
        relative = source.relative_to(runtime.resolve()).as_posix()
        require(sha(source) == source_map[relative], f"changed imported source: {relative}")
    registration = archive / "optical-registration.json"
    allocation = read(registration)
    geometry = allocation["geometry"]
    index = read(archive / "rgbd-index.json")
    tick = plan["grasp_pre_tick"]
    (item,) = [
        row
        for row in index["rows"]
        if (row["skill"], row["phase"], row["robot"]["physics_step"]) == ("GRASP", "PRE", tick)
    ]
    (gate,) = [
        row
        for row in read(archive / "clearance-gate.json")["checks"]
        if (row["skill"], row["phase"], row["step"]) == ("GRASP", "PRE", tick)
    ]
    robot = item["robot"]
    raw = archive / item["file"]
    require(raw.name == "0000.json.gz" and sha(raw) == item["file_sha256"], "wrong archive image")
    frame = RGBDObservation.model_validate_json(gzip.decompress(raw.read_bytes()))
    require(
        frame.frame_id == robot["frame_id"] == gate["frame_id"]
        and frame.checksum_sha256 == robot["checksum_sha256"] == gate["checksum_sha256"]
        and frame.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
        and robot["native_last_command_seq"] == gate["native_last_command_seq"],
        "mismatched original exposure and measured arm",
    )
    identity = g1_complete_cv_optical_identity.bind_allocation(
        registration.read_bytes(),
        allocation_sha256=plan["grasp_archive_sha256"]["optical-registration.json"],
        generation_sha256=generation,
        calibration_sha256=allocation["calibration_sha256"],
        asset_sha256=allocation["asset_sha256"],
        reset_scene_id=index["scene_id"],
        reset_episode_id=index["episode_id"],
    )
    marker = g1_visibility_vision.measure_frame(frame, geometry)
    require(identity.matches(frame, marker, geometry, tick), "frozen pose bind failed")
    asset = runtime / geometry["asset_path"]
    require(sha(asset) == allocation["asset_sha256"], "assembly drift")
    model = g1_complete_cv_geometry.Model(asset)
    tcp, wrist, _ = model.forward(robot["joint_positions_rad"])
    fingers = np.asarray(robot["finger_positions_m"])
    center = np.asarray(marker["object_center_world_m"])
    rotation = np.asarray(marker["rotation_object_to_world"]).reshape(3, 3)

    def closure(position):
        return g1_complete_cv_angle.grasp_readiness(
            frame, marker, geometry, center, rotation, position, wrist, fingers, closure=True
        )

    angle, patch, reason = closure(tcp)
    expected = gate["current"]
    domain = patch["bilateral_contact_domain"]
    require(
        reason is None
        and angle == expected["grasp_angle"]
        and patch == expected["grasp_patch"]
        and patch["previous_center_height_gate"] is False
        and patch["passes"] is True
        and domain["design_sha256"] == plan["contact_design_sha256"]
        and domain["passes"] is True,
        "frozen zero-offset grasp control failed",
    )
    # Match the registered fixed tool direction in route_screen and the low/high
    # formula in route_geometry; the world-Z tilt component is kept for inspection.
    yaw = np.arctan2(rotation[1, 0], rotation[0, 0])
    cs, sn = np.cos(yaw), np.sin(yaw)
    upright = np.array([[cs, -sn, 0], [sn, cs, 0], [0, 0, 1]])
    axis = np.array([0.0, 1.0, 0.0])
    tangent = np.array([axis[1], -axis[0], 0.0])
    delta = rotation @ (upright.T @ tangent * (plan["candidate_mm"] / 1000))
    center_command = np.asarray(expected["commanded_target_xyz_m"])
    nominal = center_command + delta
    high = nominal.copy()
    high[2] = max(0.160, nominal[2] + 0.100)
    _, candidate, candidate_reason = closure(tcp + delta)
    print(
        json.dumps(
            {
                "frame_id": frame.frame_id,
                "step": tick,
                "camera_calibration": frame.calibration_version,
                "zero_offset_matches_archived_gate": True,
                "measured_tcp_m": tcp.tolist(),
                "original_command_tcp_m": center_command.tolist(),
                "original_angle_upper_deg": angle["upper_error_deg"],
                "original_contact_domain": domain,
                "measured_fingers_m": fingers.tolist(),
                "candidate_mm": plan["candidate_mm"],
                "world_delta_m": delta.tolist(),
                "candidate_reference_low_m": nominal.tolist(),
                "candidate_reference_high_m": high.tolist(),
                "conditional_candidate_tcp_m": (tcp + delta).tolist(),
                "conditional_contact_domain": candidate["bilateral_contact_domain"],
                "conditional_grasp_reason": candidate_reason,
                "candidate_actual_reach_and_visibility": "UNVERIFIED",
                "additional_integration_steps": 0,
                "additional_exposures": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
