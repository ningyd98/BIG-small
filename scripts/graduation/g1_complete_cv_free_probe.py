"""Verify precontact camera receipts, physical stops and opposing plate edges."""

import argparse
import gzip
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_angle import fixed_wrist_angle
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, _xyz
from scripts.graduation.g1_complete_cv_motion import upper_support
from scripts.graduation.g1_complete_cv_support_domain import (
    descending,
    locate,
    optically_supported,
    state_rows,
)
from scripts.graduation.g1_visibility_vision import measure_frame

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def read(path):
    return json.loads(path.read_bytes())


def optical_edge(root, geometry):
    rows = []
    for label in (
        "optical-control-gpu-01",
        "angle-optical-holdout-01",
        "angle-optical-validation-02",
        "angle-optical-aligned-03",
    ):
        index = root / label / "index.json"
        if not index.exists():
            continue
        for item in read(index)["raw"]:
            if item["kind"] != "yaw":
                continue
            path = index.parent / item["file"]
            if digest(path) != item["file_sha256"]:
                raise ValueError("optical control changed")
            frame = RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))
            marker = measure_frame(frame, geometry)
            angle = fixed_wrist_angle(frame, marker, geometry)
            if not angle or angle["method"] != "one_id_and_opposite_plate_edges":
                continue
            direct = np.asarray(marker["by_id"][str(angle["decoded_id"])]["marker_center_world_m"])
            span = -0.26 if angle["decoded_id"] == 8 else 0.26
            center = np.array(
                item.get("center", [0.45 + item.get("dx", 0.0), item.get("dy", 0.0), 0.035])
            )
            inferred = direct[1] + span * np.sin(np.radians(angle["yaw_deg"]))
            true = center[1] + span / 2 * np.sin(np.radians(item["angle_deg"]))
            rows.append(
                dict(
                    dataset=label,
                    raw_sha256=digest(path),
                    estimate_minus_true_y_m=float(inferred - true),
                )
            )
    return rows


def packets(sub):
    index = {v["frame_id"]: v for v in read(sub / "pixel-index.json")["frames"]}
    for row in read(sub / "local-clearance.json")["rows"]:
        if row["skill"] not in ("MOVE_ABOVE", "APPROACH"):
            continue
        info = index[row["frame_id"]]
        src = sub / info["file"]
        if digest(src) != info["file_sha256"]:
            raise ValueError("camera receipt changed")
        frame = RGBDObservation.model_validate_json(src.read_bytes())
        if frame.checksum_sha256 != row["checksum_sha256"]:
            raise ValueError("camera frame differs from encoder receipt")
        yield row, frame, info["file_sha256"]


def camera_state(check, row, frame):
    marker = measure_frame(frame, check.geometry)
    angle = fixed_wrist_angle(frame, marker, check.geometry)
    if not marker.get("usable") or not angle:
        raise ValueError("source current pose unavailable")
    q, f, dq, df = [
        np.asarray(row["robot"][k])
        for k in (
            "joint_positions_rad",
            "finger_positions_m",
            "joint_velocities_rad_s",
            "finger_velocities_m_s",
        )
    ]
    return (
        (q, f, dq, df),
        marker,
        angle,
        optically_supported(marker, check.geometry, angle, check.model, check.axes, f),
    )


def sequence(check, sub):
    check.stationary_surface = None
    rows = []
    for source, frame, sha in packets(sub):
        (q, f, dq, df), marker, angle, opt = camera_state(check, source, frame)
        c = _xyz(marker["object_center_world_m"])
        r = np.asarray(marker["rotation_object_to_world"]).reshape(3, 3)
        tcp, wrist, _ = check.model.forward(q)
        outcome = check.short_motion(
            q,
            f,
            dq,
            df,
            c,
            r,
            source["skill"],
            check.model.hand_at(tcp, wrist, f),
            True,
            optical=opt,
        )
        if (
            outcome.get("reason") is None
            and check.stationary_surface is None
            and set(marker["usable_ids"]) == {7, 8}
            and opt is not None
        ):
            check.remember_stationary(opt)
        rows.append(
            dict(
                step=source["physics_step"],
                phase=source["phase"],
                skill=source["skill"],
                raw_sha256=sha,
                method=angle["method"],
                outcome=outcome,
            )
        )
    return rows


def independent(check, root, batch):
    result = {}
    for label, phase, slot in (
        ("t01-archived_or_retained", "APPROACH", "cvfix-t01"),
        ("t01-last_valid_fixed_wrist", "APPROACH", "cvfix-t01"),
        ("t02-archived", "MOVE_ABOVE", "cvfix-t02"),
        ("independent-approach-archived", "APPROACH", None),
    ):
        d = root / label
        summary = read(d / "results.json")
        anchors = summary["anchor_to_native_stop_steps"]
        frames = {}
        if slot:
            for row, frame, sha in packets(batch / slot / "instance"):
                if str(row["physics_step"]) in anchors and row["phase"] == "FEEDBACK":
                    frames[row["physics_step"]] = (row, frame, sha)
        answer = []
        with np.load(d / "normal-prefix.npz") as source:
            for st, triggers in anchors.items():
                step = int(st)
                i = source["step"].tolist().index(step)
                q = source["q"][i]
                v = source["qvel"][i]
                c, r = source["centers"][i, 10], source["rotation"][i, 10]
                pad = np.zeros_like(check.support_phases[phase])
                camera_sha = None
                if slot:
                    row, frame, camera_sha = frames[step]
                    robot, marker, angle, receipt = camera_state(check, row, frame)
                    if max(abs(robot[0] - q[:7]).max(), abs(robot[2] - v[:7]).max()) > 1e-9:
                        raise ValueError("original physical and optical clocks differ")
                    c, r, measurement = receipt
                    pad[check.motion.load_start :] = measurement
                state = state_rows(
                    check.motion, q[None, :7], q[None, 7:9], v[None, :7], v[None, 7:9], c[None]
                )[0]
                match = locate(state, check.domain_states[phase])
                dev = check.support_phases[phase]
                if (
                    match is not None
                    and phase == "APPROACH"
                    and descending(state[-3:], check.descent_vrange)
                ):
                    dev = check.descent_support
                zero = np.zeros((len(check.motion.names), 3))
                _, verts = check.motion.envelopes(
                    q[:7],
                    q[7:9],
                    v[:7],
                    v[7:9],
                    c,
                    r,
                    phase,
                    dict(normal=zero, stop=zero),
                    with_vertices=True,
                )
                pred = np.stack(
                    [
                        upper_support(
                            verts[:, j], check.axes, dev[j] + pad[j], check.half_tick[phase][j]
                        )
                        for j in range(len(dev))
                    ]
                )
                worst = np.full_like(pred, np.inf)
                worst_rate = np.full_like(pred, -np.inf)
                uu = []
                for trigger in triggers:
                    path = d / f"stop-{trigger}.npz"
                    uu.append(digest(path))
                    with np.load(path) as z:
                        qj = z["q"]
                        vj = z["qvel"]
                        rot = z["rotation"][:, 10]
                        world = (rot @ vj[:, 12:15, None])[:, :, 0]
                        points, velocity = check.motion.vertex_velocities(
                            qj[:, :7],
                            qj[:, 7:9],
                            vj[:, :7],
                            vj[:, 7:9],
                            z["centers"][:, 10],
                            rot,
                            vj[:, 9:12],
                            world,
                        )
                        # The cubic position is within the convex hull of the four
                        # Bezier control points. Checking them covers every instant.
                        curve = np.concatenate(
                            (
                                points,
                                points[:-1] + velocity[:-1] / 720,
                                points[1:] - velocity[1:] / 720,
                            )
                        )
                        actual = np.stack(
                            [
                                (curve[:, j].reshape(-1, 3) @ check.axes.T).max(0)
                                for j in range(len(dev))
                            ]
                        )
                        worst = np.minimum(worst, pred - actual)
                        rates = 3 * 240 * np.diff(points, axis=0) - velocity[:-1] - velocity[1:]
                        worst_rate = np.maximum(
                            worst_rate,
                            np.stack(
                                [
                                    np.maximum(
                                        (velocity[:, j].reshape(-1, 3) @ check.axes.T).max(0),
                                        (rates[:, j].reshape(-1, 3) @ check.axes.T).max(0),
                                    )
                                    for j in range(len(dev))
                                ]
                            ),
                        )
                # The inner cubic control points define a sufficient, slightly
                # wider test than checking the cubic itself.
                j, k = np.unravel_index(worst.argmin(), worst.shape)
                answer.append(
                    dict(
                        step=step,
                        source_rgbd_sha256=camera_sha,
                        stops=uu,
                        matched_training_reference=match,
                        minimum_continuous_enclosure_m=float(worst[j, k]),
                        limiting_part=check.motion.names[j],
                        axis=check.axes[k].tolist(),
                        minimum_directional_rate_headroom_m_s=float(
                            (check.half_tick[phase] * 480 - worst_rate).min()
                        ),
                    )
                )
        result[label] = answer
    return result


def run(root):
    private = root / "experiments/results/g1-complete-cv-repair-20261125"
    raw = private / "mount-optics-02/capture-gpu/compiled.json.gz"
    geometry = json.loads(gzip.decompress(raw.read_bytes()))["geometry"]
    cal = private / "calibration-gpu-01"
    check = LocalClearance(
        geometry,
        root / geometry["asset_path"],
        cal,
        calibration_sha256=digest(cal / "manifest.json"),
        isolated_scene=True,
    )
    return dict(
        calibration_sha256=check.calibration_sha,
        opposed_edge=optical_edge(private, geometry),
        native_sequences={
            s.parent.name: sequence(check, s)
            for s in sorted((private / "batches/train-full-02").glob("*/instance"))
        },
        independent=independent(
            check,
            root / "experiments/results/g1-braking-envelope-20261125/physical-replay-01",
            private / "batches/train-approach-probe-02",
        ),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    write(args.out, run(Path.cwd()))
