"""Read archived camera/encoder decisions and independently verify two historical collisions."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, _xyz
from scripts.graduation.g1_complete_cv_geometry import Model, box_gap
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, upper_support
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _read(path):
    return json.loads(path.read_bytes())


def original_camera_steps(instance, monitor):
    manifest = instance / "local-clearance.json"
    index = _read(instance / "pixel-index.json")["frames"]
    result = []
    for row in _read(manifest)["rows"]:
        if row["phase"] != "FEEDBACK" or row["physics_step"] not in (1112, 1120, 1128, 1136):
            continue
        info = next(r for r in index if r["frame_id"] == row["frame_id"])
        raw = instance / info["file"]
        if digest(raw) != info["file_sha256"]:
            raise ValueError("captured frame bytes differ")
        frame = RGBDObservation.model_validate_json(raw.read_bytes())
        observed = measure_frame(frame, monitor.geometry)
        center = _xyz(observed["object_center_world_m"])
        rot = np.array(observed["rotation_object_to_world"]).reshape(3, 3)
        q, f, dq, df = [
            np.array(row["robot"][k])
            for k in (
                "joint_positions_rad",
                "finger_positions_m",
                "joint_velocities_rad_s",
                "finger_velocities_m_s",
            )
        ]
        tcp, wrist, _ = monitor.model.forward(q)
        robot = monitor.model.hand_at(tcp, wrist, f)
        check = monitor.short_motion(q, f, dq, df, center, rot, row["skill"], robot, True)
        result.append(
            dict(
                step=row["physics_step"],
                source_frame=info,
                center_m=center.tolist(),
                tcp_m=tcp.tolist(),
                source_motion=row["evidence"]["short_motion"],
                repaired_motion=check,
                decision_source_sha256=digest(manifest),
            )
        )
    return result


def historic_sweeps(root, monitor):
    records = []
    for mm, label, collision_step, pair in (
        (115, "train-radial15-timing-01", 1221, ["right_finger_geom", "g1_dual_id8_plate"]),
        (130, "train-radial30-contact-d02-02", 1228, ["left_finger_geom", "g1_dual_id7_crossbar"]),
    ):
        folder = root / "experiments/results/g1-visibility-pose-repair-20261124/batches" / label
        raw = folder / "d02/instance/offline-truth.json"
        samples = _read(raw)["samples"]
        asset = (
            root
            / "assets/robots/franka_panda"
            / f"scene_g1_development_dual_id7_y{mm}_id8_x{mm}_low_bracket_v3.xml"
        )
        if pair not in samples[collision_step]["contact_pairs"]:
            raise ValueError("historical contact oracle does not corroborate inspected pair")
        g = MotionGeometry(Model(asset))
        body, carrier = map(g.names.index, pair)
        events = []
        # Never install a new assembly's calibration on an old runtime. These independent
        # offline physical data test whether the tighter separation proof invents a gap.
        for i in (collision_step - 8, collision_step - 1, collision_step):
            row = samples[i]
            q, f, dq, df, c, r = [
                np.asarray(row[k])
                for k in (
                    "joint_positions_rad",
                    "finger_positions_m",
                    "joint_velocities_rad_s",
                    "finger_velocities_m_s",
                    "object_geom_position_m",
                    "object_geom_rotation_row_major",
                )
            ]
            r = r.reshape(3, 3)
            zero = np.zeros((len(g.names), 3))
            _, v = g.envelopes(
                q, f, dq, df, c, r, "APPROACH", dict(normal=zero, stop=zero), with_vertices=True
            )
            pad = monitor.support_phases["APPROACH"]
            a = upper_support(v[:, body], monitor.axes, pad[body])
            b = upper_support(v[:, carrier], monitor.axes, pad[carrier])
            projected = -b[monitor.opposite] - a
            tcp, wrist, _ = g.model.forward(q)
            hand = g.model.hand_at(tcp, wrist, f)
            workpiece = [part.placed(c, r) for part in g.model.object]
            actual = box_gap(hand[body - g.hand_start], workpiece[carrier - g.load_start])
            events.append(
                dict(
                    step=i,
                    actual_gap_m=actual,
                    actual_contacts=row["contact_pairs"],
                    signed_8tick_stop_pair_gap_m=float(projected.max()),
                )
            )
        records.append(
            dict(
                assembly_mm=mm,
                pair=pair,
                raw_sha256=digest(raw),
                assembly_sha256=digest(asset),
                events=events,
            )
        )
    return records


def run(root, private):
    src = root / "scripts/graduation"
    compiled = private / "mount-optics-02/capture-gpu/compiled.json.gz"
    cal = private / "calibration-gpu-01"
    geometry = json.loads(gzip.decompress(compiled.read_bytes()))["geometry"]
    checker = LocalClearance(
        geometry,
        root / geometry["asset_path"],
        cal,
        calibration_sha256=digest(cal / "manifest.json"),
        isolated_scene=True,
    )
    return dict(
        closed_loop_camera=original_camera_steps(
            private / "batches/train-approach-probe-02/cvfix-t01/instance", checker
        ),
        archived_contacts=historic_sweeps(root, checker),
        native_calibration_sha256=checker.calibration_sha,
        assets={
            p.name: digest(p)
            for p in (
                src / "g1_complete_cv_clearance.py",
                src / "g1_complete_cv_motion.py",
                src / "g1_complete_cv_motion_profile.json",
                src / "g1_complete_cv_support_profile.json",
                src / "g1_complete_cv_motion_fit.py",
                src / "g1_complete_cv_support_probe.py",
            )
        },
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--private", type=Path, required=True)
    args = ap.parse_args()
    write(args.out, run(Path.cwd(), args.private))
