"""Read the calibration controls, original preflight and archived forbidden contacts."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest
from scripts.graduation.g1_complete_cv_clearance import LocalClearance
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_visibility_trials import device
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def read(path):
    return json.loads(path.read_bytes())


def baseline_contacts(root):
    rows = []
    for mm, label, step in [
        (115, "train-radial15-timing-01", 1221),
        (130, "train-radial30-contact-d02-02", 1228),
    ]:
        xml = (
            root
            / "assets/robots/franka_panda"
            / f"scene_g1_development_dual_id7_y{mm}_id8_x{mm}_low_bracket_v3.xml"
        )
        file = (
            root
            / "experiments/results/g1-visibility-pose-repair-20261124/batches"
            / label
            / "d02/instance/offline-truth.json"
        )
        model = Model(xml)
        samples = read(file)["samples"]
        for i in (step - 1, step):
            st = samples[i]
            tcp, rot, _ = model.forward(st["joint_positions_rad"])
            parts = model.hand_at(tcp, rot, st["finger_positions_m"])
            object_rot = np.asarray(st["object_geom_rotation_row_major"]).reshape(3, 3)
            rows.append(
                dict(
                    mount_mm=mm,
                    step=i,
                    **model.hand_gaps(parts, st["object_geom_position_m"], object_rot, True),
                    actual_pairs=st["contact_pairs"],
                    raw_sha256=digest(file),
                    assembly_sha256=digest(xml),
                )
            )
    return rows


def controls(root, cal, compiled, preflight, optical=None, replays=None):
    geometry = json.loads(gzip.decompress(compiled.read_bytes()))["geometry"]
    lock = root / "experiments/results/g1-visibility-pose-repair-20261124"
    register = dict(calibration_sha256=digest(cal / "manifest.json"), isolated_scene=True)
    results = {}

    def check(key, frame, robot, skill="MOVE_ABOVE"):
        marker = measure_frame(frame, geometry)
        instance = LocalClearance(geometry, root / geometry["asset_path"], cal, **register)
        try:
            results[key] = instance.check(
                frame, marker, robot, skill, [0.45, 0, 0.16], _DOWNWARD, phase="PRE"
            )
        finally:
            instance.close()
        return marker

    with device(lock):
        for role in ("positive", "foreign"):
            frame = RGBDObservation.model_validate_json((cal / f"{role}-0.rgbd.json").read_bytes())
            robot = read(cal / f"{role}.robot.json")
            # The diagnostic initializes qvel=0 and never calls mj_step. Early
            # diagnostic packets saved positions only; this fact applies only
            # to this registered zero-time camera fixture.
            if frame.sim_time_s == 0 and read(cal / "manifest.json")["physics_steps"] == 0:
                robot.setdefault("joint_velocities_rad_s", [0.0] * 7)
                robot.setdefault("finger_velocities_m_s", [0.0] * 2)
            check(role, frame, robot)
            if role == "positive":
                wrong = frame.model_dump()
                wrong.update(calibration_version="foreign-calibration", checksum_sha256="")
                check("wrong_calibration", RGBDObservation.model_validate(wrong), robot)
        if optical:
            pin = next(r for r in read(optical / "index.json")["raw"] if r["kind"] == "pin")
            raw = optical / pin["file"]
            if digest(raw) != pin["file_sha256"]:
                raise ValueError("physical edge obstacle raw changed")
            frame = RGBDObservation.model_validate_json(gzip.decompress(raw.read_bytes()))
            robot = dict(
                frame_id=frame.frame_id,
                checksum_sha256=frame.checksum_sha256,
                sim_time_s=frame.sim_time_s,
                joint_positions_rad=pin["q"],
                finger_positions_m=pin["fingers"],
                joint_velocities_rad_s=[0.0] * 7,
                finger_velocities_m_s=[0.0] * 2,
            )
            check("physical_pin_at_arm_silhouette", frame, robot)
        if preflight:
            rec = read(preflight / "local-clearance.json")["rows"][0]
            index = read(preflight / "pixel-index.json")["frames"]
            fi = next(row for row in index if row["frame_id"] == rec["frame_id"])
            frame = RGBDObservation.model_validate_json((preflight / fi["file"]).read_bytes())
            if fi["file_sha256"] != digest(preflight / fi["file"]):
                raise ValueError("preflight original changed")
            check("stopped_preflight", frame, rec["robot"])
    summary = {}
    if replays:
        for case, rows in read(replays).items():
            samples = [r["outcome"]["check_ms"] for r in rows[1:]]
            final = rows[-1]
            summary[case] = dict(
                physical_replay_source_sha256=digest(replays),
                frames=len(rows),
                hot_samples=len(samples),
                hot_min_ms=min(samples),
                hot_median_ms=float(np.median(samples)),
                hot_max_ms=max(samples),
                first_check_with_graphics_initialization_ms=rows[0]["outcome"]["check_ms"],
                all_clear=all(r["outcome"]["status"] == "CLEAR" for r in rows),
                maximum_joint_replay_difference_rad=max(r["q_replay_max_rad"] for r in rows),
                previous_refusal_step=final["step"],
                observed_and_predicted_optical_z_m=final["old_pixels"],
            )
    return dict(
        current=results,
        archived_contacts=baseline_contacts(root),
        dynamic_replays=summary,
        calibration_sha256=register["calibration_sha256"],
        calibration_renderer=read(cal / "manifest.json").get("renderer"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--compiled", type=Path, required=True)
    p.add_argument("--preflight", type=Path)
    p.add_argument("--optical", type=Path)
    p.add_argument("--replays", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    data = controls(Path.cwd(), a.calibration, a.compiled, a.preflight, a.optical, a.replays)
    with a.out.open("x") as stream:
        json.dump(data, stream, allow_nan=False, sort_keys=True, indent=2)
        stream.write("\n")
    print({k: (v["status"], v["reason"], v["check_ms"]) for k, v in data["current"].items()})
