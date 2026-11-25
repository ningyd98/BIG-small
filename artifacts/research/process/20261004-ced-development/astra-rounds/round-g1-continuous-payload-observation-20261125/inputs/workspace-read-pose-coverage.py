"""Recompute issued optical bounds, then compare with independent physical labels."""

import argparse
import gzip
from collections import Counter
from itertools import product
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_cv_payload_observation import payload_observation
from scripts.graduation.g1_complete_trials import PRIVATE, write_once
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.perception_io import ROOT, pinned, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation

PLAN = "8ced7b85428ea2a57573c1bec5d4e7b8c22e8da76bae5f1367197124b44c94e2"
ARCHIVE = ROOT / PRIVATE / "payload-optics-01" / "payload-val-04"
LABELS = ARCHIVE / "offline-labels.json"


def receive(path, plan):
    return pinned(path, plan["input_sha256"][path.relative_to(ROOT).as_posix()])


def predict(output, plan):
    index = receive(ARCHIVE / "index.json", plan)
    allocation = pinned(ARCHIVE / "allocation.json", index["allocation_sha256"])
    reset = pinned(ARCHIVE / "reset.json", index["reset_sha256"])
    geometry = allocation["geometry"]
    assert reset["allocation_sha256"] == index["allocation_sha256"]
    identity = bind_allocation(
        (ARCHIVE / "allocation.json").read_bytes(),
        allocation_sha256=index["allocation_sha256"],
        generation_sha256=allocation["runtime_build_sha256"],
        calibration_sha256=allocation["calibration_sha256"],
        asset_sha256=sha(ROOT / geometry["asset_path"]),
        reset_scene_id=reset["scene_id"],
        reset_episode_id=reset["episode_id"],
    )
    rows, history = [], {}
    before_dwell = None
    for row in index["rows"]:
        frame_path = ARCHIVE / row["file"]
        assert sha(frame_path) == row["file_sha256"]
        frame = RGBDObservation.model_validate_json(gzip.decompress(frame_path.read_bytes()))
        robot = row["robot"]
        marker = measure_frame(frame, geometry)
        step = robot["physics_step"]
        optical = rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
        # The old bench opened a dwell branch, then restarted at the earlier RETREAT point.
        # Exclude those 31 frames from the original RETREAT history.
        if row["phase"] == "DWELL" and before_dwell is None:
            from copy import deepcopy

            before_dwell = deepcopy(history)
        elif row["skill"] == "RETREAT" and before_dwell is not None:
            history, before_dwell = before_dwell, None
        relation = payload_observation(
            frame,
            marker,
            geometry,
            robot,
            row["skill"],
            row["phase"],
            identity=identity,
            physics_step=step,
            optical=optical,
            history=history,
        )
        rows.append(
            dict(
                file=row["file"],
                frame_id=frame.frame_id,
                checksum_sha256=frame.checksum_sha256,
                step=step,
                phase=row["phase"],
                skill=row["skill"],
                prediction=plain(relation),
            )
        )
    assert not LABELS.samefile(output) if output.exists() else True
    write_once(
        output,
        dict(
            index_sha256=sha(ARCHIVE / "index.json"),
            reader_sha256=sha(Path(__file__)),
            plan_sha256=PLAN,
            contains_physical_labels=False,
            rows=rows,
        ),
    )


def ratios(pose, physical):
    basis, measured = np.asarray(pose["basis_error_object"]), np.asarray(pose["rotation"])
    uncertainty = np.asarray(pose["anchor_error_object_m"])
    expected, real = np.asarray(physical["center_m"]), np.asarray(physical["rotation"])
    lever = np.asarray(pose["anchor_object_m"])
    anchor = np.asarray(pose["anchor_world_m"])
    ea = abs((expected + real @ lever - anchor) @ measured) / uncertainty
    er = abs(measured.T @ real - np.eye(3)) / basis
    corners = np.array(list(product((-0.035, 0.035), repeat=3)))
    local = corners - lever
    assumed = anchor + local @ measured.T
    actual = expected + corners @ real.T
    reach = uncertainty + abs(local) @ basis.T
    errors = abs((actual - assumed) @ measured)
    return dict(
        anchor_ratio=ea.tolist(),
        basis_ratio=er.tolist(),
        cube_corner_ratio=float((errors / reach).max()),
        farthest_cube_corner_error_mm=float(1000 * np.linalg.norm(actual - assumed, axis=1).max()),
        independent_bottom_m=float(actual[:, 2].min()),
        current_valid_bounds=bool(max(ea.max(), er.max()) <= 1),
    )


def audit(input_path, output, plan):
    index = receive(ARCHIVE / "index.json", plan)
    labels = receive(LABELS, plan)["physical"]
    pred = pinned(input_path, sha(input_path))
    assert pred["plan_sha256"] == PLAN and pred["index_sha256"] == sha(ARCHIVE / "index.json")
    rows = []
    for row, physical, source in zip(pred["rows"], labels, index["rows"], strict=True):
        assert row["file"] == physical["file"] == source["file"]
        assert row["checksum_sha256"] == source["robot"]["checksum_sha256"]
        prediction = row["prediction"]
        pose = prediction["pose"]
        proof = ratios(pose, physical) if pose else {}
        contacts = {tuple(pair) for pair in physical["touching"]}
        held = {
            ("left_finger_geom", "object_geom"),
            ("object_geom", "right_finger_geom"),
        } <= contacts
        support = ("object_geom", "table") in contacts
        rows.append(
            dict(
                **{k: v for k, v in row.items() if k != "prediction"},
                **proof,
                method=pose["method"] if pose else None,
                relation=prediction["relation"],
                permits_table=prediction["allow_registered_block_table_contact"],
                both_fingers=held,
                table_contact=support,
                signed_observer_gaps_m=prediction["evidence"].get("actual_inner_face_gaps_m"),
            )
        )
    counts = Counter(
        "abstained"
        if row["method"] is None
        else "bounded"
        if row["current_valid_bounds"]
        else "outside_issued_bounds"
        for row in rows
    )
    outside = [r for r in rows if r.get("current_valid_bounds") is False]
    result = dict(
        counts=counts,
        old_frame_domain="99 sealed diagnostic exposures (already opened)",
        outside_per_stage=Counter(r["skill"] for r in outside),
        max_corner_error_mm=max(r["farthest_cube_corner_error_mm"] for r in outside),
        labels_sha256=sha(LABELS),
        predictions_sha256=sha(input_path),
        rows=rows,
    )
    write_once(output, result)
    print(dict(counts), dict(result["outside_per_stage"]), result["max_corner_error_mm"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predict", type=Path, required=True)
    parser.add_argument("--score", type=Path)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    plan = pinned(Path(__file__).with_name("plan.json"), PLAN)
    if args.score is None:
        predict(args.predict, plan)
    else:
        audit(args.predict, args.score, plan)
