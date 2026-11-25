"""Score the static fit images using the prior candidate intervals and separate labels."""

import argparse
import base64
import gzip
import importlib.util
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_complete_cv_handoff_optics import measured_pose
from scripts.graduation.g1_complete_cv_payload_observation import red_face_pose
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PEER = HERE.parent / "round-g1-continuous-payload-observation-20261125"
RAW = ROOT / "experiments/results/g1-print-pose-uncertainty-20261125/native-static-fit-01"
BASE = ROOT / "experiments/results/g1-complete-cv-repair-20261125"
ACQUISITION = "ed7cf303a5708505373a687815b422611b95ef4d6b8a83f6c9508b68b525b085"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def predict():
    acquisition = pinned(RAW / "acquisition.json", ACQUISITION)
    generation = acquisition["generation"]
    tree = BASE / "builds" / generation / "runtime-source"
    lock = pinned(tree / "runtime-build.json", generation)
    detector = "scripts/graduation/g1_visibility_vision.py"
    assert sha(tree / detector) == lock["runtime_files_sha256"][detector]
    measure = load(tree / detector, "actual_original_vision").measure_frame
    design = pinned(
        HERE / "diagnostic-registration.json",
        "3a3f129013e34997b4a6eac173c7a9afef57703639ad3a4253912c5b946e54e9",
    )
    source = PEER / "red-ink-fit.py"
    assert sha(source) == design["input_sha256"][source.relative_to(ROOT).as_posix()]
    ink = load(source, "sealed_grid_metric")
    geometry = read(BASE / "batches/train-full-04/cvfix-t01/allocation.json")["geometry"]
    records = []
    for row in acquisition["raw_rows"]:
        path = RAW / row["file"]
        assert sha(path) == row["sha256"]
        decoded = gzip.decompress(path.read_bytes())
        frame = RGBDObservation.model_validate_json(decoded)
        assert frame.frame_id == row["frame_id"] and frame.checksum_sha256 == row["checksum_sha256"]
        marker = measure(frame, geometry)
        pose = measured_pose(frame, marker, geometry)
        rec = dict(source=row, ids=marker["usable_ids"], method=pose["method"] if pose else None)
        if pose and pose["method"] == "id8":
            rgb = cv2.imdecode(np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), 1)
            raw, _ = red_face_pose(frame, marker, geometry, rgb[:, :, ::-1], axial(frame))
            if raw:

                def trace(call, event, output, raw=raw, rec=rec):
                    if (
                        call.f_code is ink.metric.__code__
                        and event == "return"
                        and output is not None
                    ):
                        accepted = ink.GRID[call.f_locals["supported"]]
                        yaw = np.rad2deg(accepted[:, 0])
                        anchor = np.asarray(raw["rotation_object_to_world"])
                        angle = float(np.rad2deg(np.arctan2(anchor[1, 0], anchor[0, 0])))
                        near_boundary = bool(
                            np.any(abs(yaw) > 2.99) or np.any(abs(accepted[:, 1:]) > 0.00149)
                        )
                        width = float(np.ptp(yaw) + 0.2)
                        rec["single_print_candidates"] = dict(
                            width_deg=width,
                            absolute_bounds_deg=[
                                float(yaw.min() + angle - 0.1),
                                float(yaw.max() + angle + 0.1),
                            ],
                            touches_search_boundary=near_boundary,
                            strong=bool(
                                width <= 1
                                and not near_boundary
                                and output["gray_pixels"] >= 180
                                and output["red_pixels"] >= 24
                            ),
                        )
                    return trace

                sys.settrace(trace)
                try:
                    ink.metric(
                        frame.model_dump(mode="json"),
                        dict(
                            raw,
                            rotation=raw["rotation_object_to_world"],
                            center_m=raw["center_world_m"],
                        ),
                    )
                finally:
                    sys.settrace(None)
        records.append(rec)
    write_once(
        RAW / "candidate-replay.json",
        dict(acquisition_sha256=ACQUISITION, records=records, truth_read=False),
    )


def score():
    pred = read(RAW / "candidate-replay.json")
    truth = read(RAW / "offline-labels.json")
    methods, bounds = Counter(), []
    for row, label in zip(pred["records"], truth, strict=True):
        assert row["source"]["frame_id"] == label["frame_id"]
        methods[row["method"] or "no_pose"] += 1
        if "single_print_candidates" in row:
            z = row["single_print_candidates"]
            lo, hi = z["absolute_bounds_deg"]
            bounds.append(
                dict(
                    z,
                    group=row["source"]["group"],
                    frame_id=label["frame_id"],
                    yaw_in_reported_range=bool(lo <= label["yaw_deg"] <= hi),
                )
            )
    result = dict(
        acquisition_sha256=ACQUISITION,
        pose_methods=methods,
        static_fit_frames=len(truth),
        qualified_angle_rows=sum(z["strong"] for z in bounds),
        candidate_rows=bounds,
        heldout_static_acquisitions=0,
        formal_simulations=0,
        physical_advances=0,
        acquisition_file_sha256=sha(RAW / "acquisition.json"),
        prediction_sha256=sha(RAW / "candidate-replay.json"),
        truth_sha256=sha(RAW / "offline-labels.json"),
    )
    write_once(HERE / "native-static-fit.public.json", result)
    print(dict(methods), len(bounds), result["qualified_angle_rows"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("part", choices=("predict", "score"))
    cv2.setNumThreads(1)
    (predict if parser.parse_args().part == "predict" else score)()
