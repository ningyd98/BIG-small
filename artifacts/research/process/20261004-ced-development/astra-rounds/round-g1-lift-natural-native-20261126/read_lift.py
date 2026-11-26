"""Bind native feedback receipts, then cold-read natural weak edges and physical labels."""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import cv2
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
DENSE = HERE.parent / "round-g1-continuous-payload-observation-20261125"
NATURAL = HERE.parent / "round-g1-rgb-edge-natural-archive-20261126"
sys.path[:0] = [str(NATURAL), str(DENSE)]
import read_dense_payload as dense  # noqa: E402
import read_natural_support as natural  # noqa: E402

root, reader, require, refit = natural.root, natural.reader, natural.require, natural.refit
RAW = root / "experiments/results/g1-lift-natural-native-20261126"
CAPTURE = RAW / "capture-01"
OUTPUT = RAW / "readback-01"
PLAN = reader.read(HERE / "plan.json")


def preflight():
    aliases = {"rounds": HERE.parent, "cv": reader.CV}
    for alias, value in PLAN["pins"].items():
        group, name = alias.split("/", 1)
        reader.pin(aliases[group] / name, value)
    seal = reader.read(CAPTURE / "capture-seal.json")
    active = {}
    for name, digest in seal["sealed_sha256"].items():
        path = (CAPTURE / name).resolve()
        require(path.is_relative_to(CAPTURE), "capture seal path leaves the isolated attempt")
        active[name] = reader.pin(path, digest)
    receipt = reader.read(active["registration.json"])
    require(
        seal["registration_sha256"] == sha(active["registration.json"])
        and receipt["plan_sha256"] == sha(HERE / "plan.json")
        and receipt["driver_sha256"] == sha(HERE / "collect_lift.py"),
        "capture registration or driver differs",
    )
    require(receipt["cases"] == PLAN["cases"], "capture changed registered cases")
    return seal, active


def source_metadata(seal, active):
    cases, frames = {}, {}
    for slot in PLAN["cases"]:
        key = slot["id"]
        receipt = active.get(f"{key}/sensor-receipt.json")
        if receipt is None:
            require(key not in seal["complete_slots"], "completed case has no receipt")
            continue
        record = reader.read(receipt)
        require(
            record["id"] == key
            and record["slot"] == slot
            and record["registration_sha256"] == seal["registration_sha256"],
            "slot binding wrong",
        )
        index_path = active[f"{key}/rgbd-index.json"]
        index = reader.read(index_path)
        require(
            record["index_sha256"] == sha(index_path)
            and index["episode_id"] == record.get("episode_id"),
            "index does not bind reset",
        )
        cases[key] = {
            "id": key,
            "episode_id": record.get("episode_id"),
            "termination": record["termination"],
            "physics_steps": record["physics_steps"],
            "skill_results": record["actions"],
            "camera_calls": len(record["camera_calls"]),
        }
        for source in index["rows"]:
            native = source["robot"]
            if source["skill"] != "LIFT" or source["phase"] != "FEEDBACK":
                continue
            name = f"{key}/{source['file']}"
            require(
                native["skill"] == "LIFT"
                and native["phase"] == "FEEDBACK"
                and native["sim_time_s"] == native["camera_encoder_sim_time_s"]
                and source["file_sha256"] == seal["sealed_sha256"][name]
                and name not in frames,
                "wrong LIFT shutter identity",
            )
            frames[name] = native | {"sha256": source["file_sha256"]}
    for case, receipt in cases.items():
        ticks = [r["physics_step"] for k, r in frames.items() if k.startswith(case + "/")]
        require(
            len(ticks) <= PLAN["max_lift_feedback_per_case"]
            and all(b - a == 8 for a, b in zip(ticks[:-1], ticks[1:], strict=True)),
            f"{case} passed budget or lost the native 8-step spacing",
        )
        receipt["lift_feedback"] = len(ticks)
        require(ticks == sorted(set(ticks)), "feedback step reused")
        if receipt["termination"] == "registered_feedback_cutoff":
            require(
                len(ticks) == PLAN["max_lift_feedback_per_case"]
                and ticks[-1] == receipt["physics_steps"],
                "intentional cutoff lost its final shutter",
            )
    require(
        len({r["frame_id"] for r in frames.values()}) == len(frames),
        "duplicated frame id across controlled resets",
    )
    return cases, frames


def write_registry():
    seal, files = preflight()
    cases, frames = source_metadata(seal, files)
    require(bool(cases), "capture has no recoverable reset receipts")
    OUTPUT.mkdir(parents=True, exist_ok=False)
    reader.write(
        OUTPUT / "registration.json",
        {
            "capture_seal_sha256": sha(CAPTURE / "capture-seal.json"),
            "cases": cases,
            "feedback": frames,
            "driver_sha256": sha(Path(__file__)),
        },
    )


def registry(expected):
    path = OUTPUT / "registration.json"
    reg = reader.read(reader.pin(path, expected))
    require(
        reg["driver_sha256"] == sha(Path(__file__))
        and reg["capture_seal_sha256"] == sha(CAPTURE / "capture-seal.json"),
        "readback no longer addresses the exact captured prefix",
    )
    return reg


def predict(reg_sha, name):
    reg = registry(reg_sha)
    path = OUTPUT / f"predictions-{name}.json"
    allow = {CAPTURE / name for name in reg["feedback"]}
    allow.update(CAPTURE / c / "native-resets.json" for c in reg["cases"])
    allow.update(
        (
            path,
            reader.CV / "batches/train-full-04/allocation.json",
            reader.CV / reader.T02_REL / "allocation.json",
            reader.RUNTIME / "runtime-build.json",
            reader.RUNTIME / "scripts/graduation/g1_visibility_vision.py",
        )
    )

    def deny_labels(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            file = Path(os.fsdecode(args[0])).resolve()
            if file.is_relative_to(root / "experiments/results") and file not in allow:
                raise PermissionError("outside permitted current optical input")

    sys.addaudithook(deny_labels)
    for forbidden in (
        CAPTURE / next(iter(reg["cases"])) / "offline-physics.json",
        natural.OUT / "readback.json",
    ):
        try:
            forbidden.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("active predictor can read physical labels")
    cv2.setNumThreads(1)
    detect, marker_sha = reader.native_marker(PLAN["optical_generation"])
    require(marker_sha == reader.PLAN["marker_sha256"], "native perception generation changed")
    known = {}
    predictions = {}
    for name, robot in reg["feedback"].items():
        slot = name.split("/")[0]
        if slot not in known:
            known[slot] = dense.bind_fixture(CAPTURE / slot, reg["cases"][slot])
        identity, scene = known[slot]
        frame = reader.checked_packet(CAPTURE / name, robot["sha256"])
        tick = robot["physics_step"]
        require(
            frame.frame_id == robot["frame_id"]
            and frame.checksum_sha256 == robot["checksum_sha256"]
            and frame.sim_time_s == robot["sim_time_s"],
            "clock or frame changed since motion",
        )
        marker = detect(frame, scene)
        require(identity.matches(frame, marker, scene, tick), "unbound live feedback")
        predictions[name] = dict(
            natural.match(frame, marker, scene, identity, tick, False),
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            physics_step=tick,
        )
    reader.write(
        path,
        {"registration_sha256": reg_sha, "scoring_input_denied": True, "predictions": predictions},
    )


def score(reg_sha, prediction_sha):
    reg = registry(reg_sha)
    raw = [
        reader.pin(OUTPUT / f"predictions-{tag}.json", prediction_sha).read_bytes()
        for tag in ("first", "second")
    ]
    require(raw[0] == raw[1], "independent native predictions differ")
    prediction = json.loads(raw[0])
    require(
        prediction["registration_sha256"] == reg_sha
        and prediction["scoring_input_denied"]
        and set(prediction["predictions"]) == set(reg["feedback"]),
        "prediction file does not bind the capture",
    )
    seal = reader.read(CAPTURE / "capture-seal.json")
    physical = {}
    for case in reg["cases"]:
        source = f"{case}/offline-physics.json"
        label_file = reader.pin(CAPTURE / source, seal["sealed_sha256"][source])
        for label in reader.read(label_file)["frame_labels"]:
            require(label["frame_id"] not in physical, "reused physical label")
            physical[label["frame_id"]] = label
    counts = {case: Counter() for case in reg["cases"]}
    names, output = set(), {}
    for key, observed in prediction["predictions"].items():
        slot = key.split("/")[0]
        label = physical[observed["frame_id"]]
        require(
            observed["physics_step"] == label["physics_step"]
            and observed["checksum_sha256"] == label["checksum_sha256"],
            "pose and physical label do not share the same shutter",
        )
        status = observed["status"]
        counts[slot]["feedback"] += 1
        candidate = observed["candidate"]
        if not candidate:
            counts[slot][status] += 1
            continue
        metric = None
        if status == "refitted":
            metric = refit.evaluate(candidate["extension"]["point"], label)
            status = "inside" if metric["covered_by_existing_diagnostic_range"] else "outside"
        names.add(slot)
        counts[slot]["natural_matches"] += 1
        counts[slot][status] += 1
        contact = {frozenset(pair) for pair in label["touching"]}
        bilateral = all(
            frozenset((finger, "object_geom")) in contact
            for finger in ("left_finger_geom", "right_finger_geom")
        )
        output[key] = {
            "status": status,
            "step": observed["physics_step"],
            "diagnostic_pose": metric,
            "weak_columns": candidate["weak_columns"],
            "actual_bilateral": bilateral,
            "original_method": observed["original_method"],
        }
    basis = len(names) >= 2 and all(v["status"] == "inside" for v in output.values())
    reader.write(
        OUTPUT / "readback.json",
        {
            "registration_sha256": reg_sha,
            "prediction_sha256": prediction_sha,
            "native_capture_seal_sha256": reg["capture_seal_sha256"],
            "planned_slots": [case["id"] for case in PLAN["cases"]],
            "case_receipts": reg["cases"],
            "counts": counts,
            "natural_matches": output,
            "matching_new_slots": sorted(names),
            "basis_for_next_offline_t02_relationship_plan": basis,
            "online_admission": False,
            "formal": 0,
            "hardware": 0,
            "remote": 0,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("register", "predict", "score"))
    parser.add_argument("registration_sha", nargs="?")
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        write_registry()
    elif args.mode == "predict":
        require(args.argument in ("first", "second"), "unregistered prediction process")
        predict(args.registration_sha, args.argument)
    else:
        score(args.registration_sha, args.argument)
