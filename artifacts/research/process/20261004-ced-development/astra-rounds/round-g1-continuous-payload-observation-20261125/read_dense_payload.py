"""Two-process payload shadow scoring on native diagnostic exposures and physical labels."""

import argparse
import gzip
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import cv2
from read_pose_coverage import native_marker, ratios
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_cv_payload_observation import (
    frozen_red_geometry,
    payload_observation,
)
from scripts.graduation.g1_complete_trials import PRIVATE, write_once
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.perception_io import ROOT, pinned, read, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation

SOURCE = "816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb"


def bind_fixture(folder, receipt):
    template = ROOT / PRIVATE / "batches/train-full-04/cvfix-t02/allocation.json"
    allocation = pinned(
        template,
        next(
            row["allocation_sha256"]
            for row in read(template.parents[1] / "allocation.json")["cases"]
            if row["id"] == "cvfix-t02"
        ),
    )
    scene = f"g1.continuous-payload/{receipt['id']}"
    bound, episode = native_reset_ids(
        read(folder / "native-resets.json"), scene, receipt["episode_id"]
    )
    allocation["case"].update(scene_id=bound)
    data = json.dumps(allocation, sort_keys=True).encode()
    identity = bind_allocation(
        data,
        allocation_sha256=hashlib.sha256(data).hexdigest(),
        generation_sha256=SOURCE,
        calibration_sha256=allocation["calibration_sha256"],
        asset_sha256=sha(ROOT / allocation["geometry"]["asset_path"]),
        reset_scene_id=bound,
        reset_episode_id=episode,
    )
    return identity, allocation["geometry"]


def predict(folder, output, runtime):
    receipt = read(folder / "sensor-receipt.json")
    index = pinned(folder / "rgbd-index.json", receipt["index_sha256"])
    identity, geometry = bind_fixture(folder, receipt)
    red_geometry = frozen_red_geometry(runtime, ROOT / geometry["asset_path"]) if runtime else None
    measure, detector = native_marker(SOURCE)
    catalog = {
        name: sha(folder / name)
        for name in (
            "native-resets.json",
            "native-commands.json",
            "sensor-receipt.json",
            "rgbd-index.json",
        )
    }
    from scripts.graduation import g1_complete_cv_payload_observation as observer

    history, records = {}, []
    seen, prior_step = set(), -1
    for source in index["rows"]:
        path = folder / source["file"]
        assert source["file_sha256"] == sha(path)
        catalog[path.name] = source["file_sha256"]
        frame = RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))
        assert frame.frame_id not in seen
        seen.add(frame.frame_id)
        sample = source["robot"]
        stage, role, step = source["skill"], source["phase"], sample["physics_step"]
        assert frame.frame_id == sample["frame_id"] and step >= prior_step
        prior_step = step
        start = time.perf_counter_ns()
        marker = measure(frame, geometry)
        current = rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
        observation = payload_observation(
            frame,
            marker,
            geometry,
            sample,
            stage,
            role,
            identity=identity,
            physics_step=step,
            optical=current,
            history=history,
            red_geometry=red_geometry,
        )
        records.append(
            dict(
                frame_id=frame.frame_id,
                checksum_sha256=frame.checksum_sha256,
                step=step,
                skill=stage,
                phase=role,
                dwell_tick=source["dwell_tick"],
                processing_ms=(time.perf_counter_ns() - start) / 1e6,
                result=plain(observation),
            )
        )
    write_once(
        output,
        dict(
            id=receipt["id"],
            detector_sha256=detector,
            observer_sha256=sha(Path(observer.__file__)),
            current_profile_sha256=sha(
                Path(observer.__file__).with_name("g1_complete_cv_relation_profile.json")
            ),
            print_runtime_sha256=sha(runtime / "runtime-build.json") if runtime else None,
            source_sha256=catalog,
            records=records,
            physics_labels_read=False,
        ),
    )


def score(folder, output, sealed):
    observed = pinned(sealed, sha(sealed))
    physical = read(folder / "offline-physics.json")
    receipt = pinned(
        folder / "sensor-receipt.json", observed["source_sha256"]["sensor-receipt.json"]
    )
    exposure_answers = []
    for row, label in zip(observed["records"], physical["frame_labels"], strict=True):
        assert (
            row["frame_id"] == label["frame_id"]
            and row["checksum_sha256"] == label["checksum_sha256"]
        )
        assert row["step"] == label["physics_step"]
        result = row["result"]
        contacts = {tuple(p) for p in label["touching"]}
        truth = {
            ("left_finger_geom", "object_geom"),
            ("object_geom", "right_finger_geom"),
        } <= contacts
        table = ("object_geom", "table") in contacts
        pose = result["pose"]
        evidence = result["evidence"]
        at_release = row["skill"] in {"RELEASE", "RETREAT"}
        applicable = row["skill"] in {"LIFT", "MOVE_TO_REGION", "PLACE"}
        if not pose:
            pose_check = "abstained"
        else:
            parts = ratios(pose, label)
            pose_check = "covered" if parts["current_valid_bounds"] else "outside"
        exposure_answers.append(
            dict(
                frame_id=row["frame_id"],
                step=row["step"],
                skill=row["skill"],
                phase=row["phase"],
                dwell_tick=row["dwell_tick"],
                measured_pose=pose_check,
                method=pose["method"] if pose else None,
                relation=result["relation"],
                real_bilateral=truth,
                real_table=table,
                published_support=evidence.get("observed_support_and_rim"),
                predicted_hold_when_absent=result["relation"] == "held" and not truth,
                unknown_despite_bilateral=applicable and truth and result["relation"] != "held",
                predicted_separated_when_contact=at_release
                and truth
                and result["relation"] == "supported_and_separated",
                false_stable=result["relation"] == "supported_and_separated" and not table,
                reason=evidence.get("reason"),
                rgbd_ms=row["processing_ms"],
            )
        )
    by_stage = {}
    for stage in sorted({r["skill"] for r in exposure_answers}):
        rows = [r for r in exposure_answers if r["skill"] == stage]
        by_stage[stage] = dict(
            receipts=len(rows),
            observed=Counter(r["relation"] for r in rows),
            pose=Counter(r["measured_pose"] for r in rows),
            true_bilateral=sum(r["real_bilateral"] for r in rows),
            held_missing_due=sum(r["unknown_despite_bilateral"] for r in rows),
            pose_errors_at=Counter(r["method"] for r in rows if r["measured_pose"] == "outside"),
            full_shadow_ms_over=max((r["rgbd_ms"] for r in rows), default=0),
        )
    anomalies = {
        key: sum(r[key] for r in exposure_answers)
        for key in (
            "predicted_hold_when_absent",
            "predicted_separated_when_contact",
            "false_stable",
        )
    }
    bad_steps = sum(bool(row[3]) for row in physical["dense"])
    summary = dict(
        id=receipt["id"],
        stage_by_stage=by_stage,
        anomalies=anomalies,
        raw_physics_sha256=sha(folder / "offline-physics.json"),
        source_prediction_sha256=sha(sealed),
        original_controller_posts=sum(a["success"] for a in receipt["actions"]),
        forbidden_steps=bad_steps,
        max_capture_and_native_ik_ms=max(
            [m for a in receipt["actions"] for m in a["native_capture_and_ik_ms"]], default=None
        ),
        exposure_answers=exposure_answers,
    )
    write_once(output, summary)
    print(receipt["id"], anomalies, by_stage, flush=True)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("folder", type=Path)
    args.add_argument("prediction", type=Path)
    args.add_argument("--score", type=Path)
    args.add_argument("--print-runtime", type=Path)
    opt = args.parse_args()
    cv2.setNumThreads(1)
    if opt.score is None:
        predict(opt.folder, opt.prediction, opt.print_runtime)
    else:
        score(opt.folder, opt.score, opt.prediction)
