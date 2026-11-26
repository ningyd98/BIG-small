"""Replay original held observation against six already captured native lift prefixes."""

import argparse
import json
import os
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

import cv2
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation import g1_complete_cv_payload_observation as observer
from scripts.graduation.dynamic_vision import plain
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
CAPTURE_ROUND = HERE.parent / "round-g1-lift-natural-native-20261126"
sys.path.insert(0, str(CAPTURE_ROUND))
import read_lift as source  # noqa: E402

root, reader, require = source.root, source.reader, source.require
OUT = source.RAW / "original-relation-01"
PLAN = reader.read(HERE / "plan.json")


def inputs():
    locations = {"capture": source.CAPTURE, "readback": source.OUTPUT, "native": root}
    for alias, digest in PLAN["pins"].items():
        kind, name = alias.split("/", 1)
        reader.pin(locations[kind] / name, digest)
    require(
        not observer._profile()["single_id8_red_print"]["enabled"],
        "original optical authority configuration changed",
    )
    seal, active = source.preflight()
    cases, _ = source.source_metadata(seal, active)
    packets = {}
    for name in cases:
        receipt = reader.read(active[f"{name}/sensor-receipt.json"])
        rows = reader.read(active[f"{name}/rgbd-index.json"])["rows"]
        before, after = rows[:2]
        require(
            [(r["skill"], r["phase"]) for r in (before, after)]
            == [("GRASP", "PRE"), ("GRASP", "POST")],
            f"missing native GRASP provenance: {name}",
        )
        grasp = next(a for a in receipt["actions"] if a["skill"] == "GRASP")
        require(
            grasp["success"]
            and after["robot"]["previous_native_successful_skill"] == "GRASP"
            and after["robot"]["previous_native_return_step"]
            == grasp["return_step"]
            == after["robot"]["physics_step"]
            and after["robot"]["last_accepted_gripper_open"] is False,
            f"no native GRASP return at positive history control: {name}",
        )
        for entry in rows:
            robot = entry["robot"]
            key = f"{name}/{entry['file']}"
            require(
                key not in packets
                and entry["file_sha256"] == seal["sealed_sha256"][key]
                and robot["sim_time_s"] == robot["camera_encoder_sim_time_s"],
                f"native encoder boundary differs: {key}",
            )
            packets[key] = robot | {"sha256": entry["file_sha256"]}
    require(
        len(cases) == PLAN["slots"] and len(packets) == PLAN["feedback"] + PLAN["grasp_frames"],
        "sealed denominator differs",
    )
    return cases, packets


def register():
    cases, packets = inputs()
    OUT.mkdir(exist_ok=False, parents=True)
    reader.write(
        OUT / "registration.json",
        {
            "cases": cases,
            "packets": packets,
            "script_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
            "capture_seal_sha256": PLAN["pins"]["capture/capture-seal.json"],
        },
    )


def registered(expected):
    file = OUT / "registration.json"
    data = reader.read(reader.pin(file, expected))
    require(
        data["script_sha256"] == sha(Path(__file__))
        and data["plan_sha256"] == sha(HERE / "plan.json"),
        "offline entry differed",
    )
    return data


def predict(reg_sha, name):
    reg = registered(reg_sha)
    outfile = OUT / f"predictions-{name}.json"
    allow = {source.CAPTURE / k for k in reg["packets"]}
    allow.update(source.CAPTURE / c / "native-resets.json" for c in reg["cases"])
    allow.update(
        (
            outfile,
            reader.RUNTIME / "runtime-build.json",
            reader.RUNTIME / "scripts/graduation/g1_visibility_vision.py",
            reader.CV / "batches/train-full-04/allocation.json",
            reader.CV / reader.T02_REL / "allocation.json",
        )
    )

    def deny_labels(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(root / "experiments/results") and path not in allow:
                raise PermissionError("outside original optical inputs")

    sys.addaudithook(deny_labels)
    for path in (
        source.CAPTURE / next(iter(reg["cases"])) / "offline-physics.json",
        source.OUTPUT / "predictions-first.json",
    ):
        try:
            path.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("isolated reader accessed truth or old predictions")

    cv2.setNumThreads(1)
    measure, marker_sha = reader.native_marker(source.PLAN["optical_generation"])
    require(marker_sha == reader.PLAN["marker_sha256"], "wrong optical build")
    observed = {}
    data = {}
    for key, robot in reg["packets"].items():
        slot = key.split("/")[0]
        if slot not in data:
            identity, geometry = source.dense.bind_fixture(
                source.CAPTURE / slot, reg["cases"][slot]
            )
            data[slot] = identity, geometry, {}
        identity, geometry, history = data[slot]
        frame = reader.checked_packet(source.CAPTURE / key, robot["sha256"])
        tick = robot["physics_step"]
        marker = measure(frame, geometry)
        require(
            frame.frame_id == robot["frame_id"]
            and frame.checksum_sha256 == robot["checksum_sha256"]
            and frame.sim_time_s == robot["camera_encoder_sim_time_s"]
            and identity.matches(frame, marker, geometry, tick),
            "source shutter mismatch",
        )
        a = optics.rigid_pose(frame, marker, geometry, identity=identity, physics_step=tick)
        step_before = history.get("last_step")
        result = observer.payload_observation(
            frame,
            marker,
            geometry,
            robot,
            robot["skill"],
            robot["phase"],
            identity=identity,
            physics_step=tick,
            optical=a,
            history=history,
        )
        if robot["phase"] == "POST":
            negative = observer.payload_observation(
                frame,
                marker,
                geometry,
                dict(robot, checksum_sha256="0" * 64),
                robot["skill"],
                robot["phase"],
                identity=identity,
                physics_step=tick,
                optical=a,
                history=deepcopy(history),
            )
            require(
                negative["relation"] == "unknown"
                and negative["evidence"]["reason"] == "unbound_current_frame_or_exposure",
                "old checksum negative control accepted",
            )
        observed[key] = {
            "step": tick,
            "frame": frame.frame_id,
            "checksum": frame.checksum_sha256,
            "skill": robot["skill"],
            "phase": robot["phase"],
            "physical_step_delta": tick - step_before if step_before is not None else None,
            "held_history_step": (history.get("recent_held") or {}).get("step"),
            "result": plain(result),
        }
    reader.write(
        outfile, {"registration_sha256": reg_sha, "label_access_denied": True, "rows": observed}
    )


def score(reg_sha, prediction_sha):
    reg = registered(reg_sha)
    first, second = (
        reader.pin(OUT / f"predictions-{n}.json", prediction_sha).read_bytes()
        for n in ("first", "second")
    )
    require(first == second, "original pose/relationship predictions differ")
    p = json.loads(first)
    require(
        p["label_access_denied"]
        and p["registration_sha256"] == reg_sha
        and set(p["rows"]) == set(reg["packets"]),
        "wrong prediction binding",
    )
    prior = reader.read(
        reader.pin(
            source.OUTPUT / "predictions-first.json",
            PLAN["pins"]["readback/predictions-first.json"],
        )
    )["predictions"]
    seal = reader.read(source.CAPTURE / "capture-seal.json")
    labels = {}
    for slot in reg["cases"]:
        path = f"{slot}/offline-physics.json"
        for label in reader.read(reader.pin(source.CAPTURE / path, seal["sealed_sha256"][path]))[
            "frame_labels"
        ]:
            require(label["frame_id"] not in labels, "reused physical label")
            labels[label["frame_id"]] = label
    summary, detail = {}, {}
    for slot, receipt in reg["cases"].items():
        summary[slot] = {
            "counts": Counter(),
            "terminal": receipt["termination"],
            "grasp_post": None,
            "first_feedback_divergence": None,
        }
    for key, record in p["rows"].items():
        slot = key.split("/")[0]
        q = summary[slot]
        result = record["result"]
        label = labels[record["frame"]]
        require(
            record["checksum"] == label["checksum_sha256"]
            and record["step"] == label["physics_step"],
            "unbound physical label",
        )
        live_contact = {frozenset(pair) for pair in label["touching"]}
        bilateral = all(
            frozenset((f, "object_geom")) in live_contact
            for f in ("left_finger_geom", "right_finger_geom")
        )
        if record["skill"] == "GRASP":
            if record["phase"] == "POST":
                q["grasp_post"] = {
                    "relation": result["relation"],
                    "step": record["step"],
                    "held_history_step": record["held_history_step"],
                    "physical_bilateral_contact": bilateral,
                }
            continue
        pose = result["pose"]
        require(
            (pose["method"] if pose else None) == prior[key]["original_method"],
            "classifier changed original optical result",
        )
        error = reader.ratios(pose, label) if pose else None
        adequate = bool(error and error["current_valid_bounds"] and error["cube_corner_ratio"] <= 1)
        held = result["relation"] == "held"
        counts = q["counts"]
        counts["feedback"] += 1
        counts["original_pose_in_bounds"] += adequate
        counts["physical_bilateral"] += bilateral
        counts["original_optical_held"] += held
        counts["jointly_satisfied"] += adequate and held and bilateral
        counts["held_vs_contact_false_positive"] += held and not bilateral
        counts["held_vs_contact_false_negative"] += bilateral and not held
        row = {
            "step": record["step"],
            "adequate": adequate,
            "held": held,
            "bilateral": bilateral,
            "error_ratios": error,
            "edge_method": prior[key]["original_method"],
        }
        detail[key] = row
        if not (adequate and held and bilateral) and q["first_feedback_divergence"] is None:
            q["first_feedback_divergence"] = dict(
                row,
                reason=result["evidence"].get("reason"),
                gaps_m=result["evidence"].get("actual_inner_face_gaps_m"),
            )
    require(len(detail) == PLAN["feedback"], "feedback denominator changed")
    complete = sorted(
        slot
        for slot, record in summary.items()
        if record["counts"]["feedback"] == record["counts"]["jointly_satisfied"] == 80
    )
    reader.write(
        OUT / "readback.json",
        {
            "registration_sha256": reg_sha,
            "prediction_sha256": prediction_sha,
            "slots": summary,
            "all_80_jointly_satisfied": complete,
            "per_feedback": detail,
            "online": False,
            "limits": PLAN["new"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("register", "predict", "score"))
    parser.add_argument("registration_sha", nargs="?")
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        register()
    elif args.mode == "predict":
        require(args.argument in ("first", "second"), "unregistered cold predictor")
        predict(args.registration_sha, args.argument)
    else:
        score(args.registration_sha, args.argument)
