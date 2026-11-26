"""Cold-read coverage of a reduced RGB carrier fit without changing the original certificate."""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "round-g1-t02-depth-bracket-20261126"
sys.path.insert(0, str(PRIOR))
import depth_bracket as previous  # noqa: E402

root, reader, require = previous.ROOT, previous.reader, previous.require
OUT = root / "experiments/results/g1-rgb-edge-reduced-20261126/development-01"
DATA = reader.CV / "payload-optics-01"
PLAN = reader.read(HERE / "plan.json")
GROUPS = PLAN["fit"] + PLAN["disclosed_validation"]
INPUTS = {"prior": PRIOR, "prior_result": previous.OUT, "repo": root, "rounds": HERE.parent}


def pin_inputs():
    for alias, value in PLAN["sha256"].items():
        kind, name = alias.split("/", 1)
        reader.pin(INPUTS[kind] / name, value)


def group_files(group):
    raw = PLAN["case_sha256"][group]
    return dict(zip(PLAN["case_files_order"], raw, strict=True))


def packet_list():
    packets, bindings = reader.exposure_metadata()
    packets = {key: row for key, row in packets.items() if not key.startswith("val04/")}
    del bindings["val04"]
    for group in GROUPS:
        files = group_files(group)
        folder = DATA / group
        allocation = reader.pin(folder / "allocation.json", files["allocation.json"])
        reset = reader.read(reader.pin(folder / "reset.json", files["reset.json"]))
        index = reader.read(reader.pin(folder / "index.json", files["index.json"]))
        require(
            reset["allocation_sha256"] == index["allocation_sha256"] == sha(allocation),
            f"reset/allocation mismatch: {group}",
        )
        require(index["reset_sha256"] == files["reset.json"], f"reset digest mismatch: {group}")
        bindings[group] = (allocation, reset["scene_id"], reset["episode_id"])
        for row in index["rows"]:
            stamp = row["robot"]
            filename = row["file"]
            key = f"{group}/{filename}"
            reader.add_packet(
                packets,
                key,
                folder,
                filename,
                dict(stamp, file_sha256=row["file_sha256"]),
                stamp["physics_step"],
                group,
                native_time=stamp["sim_time_s"],
            )

    path = reader.cv_pin(reader.T02_REL + "/instance/pixel-index.json")
    lift = [row for row in reader.read(path)["frames"] if row["label"] == "LIFT/feedback"]
    steps = [r["physics_step"] for r in lift]
    require(steps == list(range(1504, 2113, 8)), "t02 feedback sequence changed")
    for entry, step in zip(lift, steps, strict=True):
        key = f"t02/{step}"
        if key not in packets:
            reader.add_packet(packets, key, path.parent, entry["file"], entry, step, "t02")
    require(
        Counter(key.split("/")[0] for key in packets) == PLAN["counts"], "packet counts changed"
    )
    require(
        len({r["frame_id"] for r in packets.values()}) == len(packets),
        "source frame is reused across roles or cohorts",
    )
    return dict(sorted(packets.items())), bindings


def registration():
    pin_inputs()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(head == PLAN["head"], "wrong experimental baseline")
    packets, _ = packet_list()
    for r in packets.values():
        reader.pin(root / r["path"], r["sha256"])
    check_geometry_controls()
    OUT.mkdir(parents=True, exist_ok=False)
    reader.write(
        OUT / "registration.json",
        {
            "source_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
            "packets": packets,
            "controls": "passed",
        },
    )


def load_registration(expected):
    record = reader.read(reader.pin(OUT / "registration.json", expected))
    require(
        record["source_sha256"] == sha(Path(__file__))
        and record["plan_sha256"] == sha(HERE / "plan.json"),
        "driver or plan changed since register",
    )
    return record


def consecutive_windows(columns):
    columns = np.asarray(columns)
    if len(columns) < 4:
        return []
    return [
        start
        for start in range(len(columns) - 3)
        if np.array_equal(columns[start : start + 4], columns[start] + np.arange(4))
    ]


def spans(points):
    return (len(points), int(np.ptp(points[:, 0])) if len(points) else 0)


def strong_side(points):
    count, span = spans(points)
    return count >= 5 and span >= 4


def check_geometry_controls():
    require(
        consecutive_windows([9, 10, 11, 12, 13, 15, 16, 17, 18]) == [0, 1, 5],
        "window enumeration lost a valid crop",
    )
    require(not consecutive_windows([9, 10, 12, 13, 15]), "discontinuous crop admitted")
    require(
        not strong_side(np.array([[9, 2], [10, 2], [11, 2], [12, 2]])),
        "weak side accepted as strong",
    )
    require(
        strong_side(np.column_stack((np.arange(9, 14), np.zeros(5)))),
        "strong side rejected at its threshold",
    )


def one_fit(measured, states, rgb, side, columns, kind):
    line, quality = previous.fiducial_fit(states, rgb)
    count_strong, span_strong = spans(rgb[-side])
    matched = (
        count_strong >= PLAN["target_comparison_strong_count"]
        and span_strong >= PLAN["target_comparison_strong_span_px"]
    )
    pose = (
        previous.point_diagnostic(measured, states[side], line[1])
        if quality["same_native_metric_limits"]
        else None
    )
    return {
        "side": side,
        "weak_columns": list(map(int, columns)),
        "kind": kind,
        "strong_columns": count_strong,
        "strong_span_px": span_strong,
        "matches_t02_support": matched,
        "fit": quality,
        "point": pose,
    }


def inspect_packet(frame, marker, scene, identity, step, excluded):
    certified = optics.rigid_pose(frame, marker, scene, identity=identity, physics_step=step)
    result = {"original": certified, "models": []}
    if excluded:
        return dict(result, status="excluded_known_foreign_near_surface")
    if not identity.matches(frame, marker, scene, step) or marker.get("usable_ids") != [8]:
        return dict(result, status="not_bound_current_single_id8")
    measured, states = previous.original_state(frame, marker, scene)
    if measured is None or set(states) != {-1, 1}:
        return dict(result, status="no_registered_two_sided_geometry")
    native, rgb = {}, {}
    for side, state in states.items():
        native[side], rgb[side] = previous.original_pixels(state)
    result["original_support"] = {side: spans(p) for side, p in native.items()}
    models = result["models"]
    for side in (-1, 1):
        if not strong_side(native[-side]):
            continue
        columns = native[side][:, 0]
        if len(columns) == 4 and consecutive_windows(columns):
            models.append(one_fit(measured, states, rgb, side, columns, "natural"))
        elif certified and strong_side(native[side]):
            for start in consecutive_windows(columns):
                stop = start + 4
                reduced = {**rgb, side: rgb[side][start:stop]}
                models.append(
                    one_fit(measured, states, reduced, side, columns[start:stop], "masked")
                )
    return dict(result, status="reduced_fit_diagnostic" if models else "no_eligible_reduced_fit")


def open_inputs(packets, bindings, output):
    camera_path = reader.cv_pin(reader.CAL_REL + "/manifest.json")
    camera = reader.read(camera_path)["primary_camera"]
    allow = {root / row["path"] for row in packets.values()}
    allow.update(entry[0].resolve() for entry in bindings.values())
    allow.update(
        (
            output,
            camera_path,
            reader.RUNTIME / "runtime-build.json",
            reader.RUNTIME / "scripts/graduation/g1_visibility_vision.py",
            reader.CV / "batches/train-full-04/allocation.json",
            reader.CV / reader.T02_REL / "allocation.json",
        )
    )

    def hide_labels(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(root / "experiments/results") and path not in allow:
                raise PermissionError("outside current prediction inputs")

    sys.addaudithook(hide_labels)
    for forbidden in (
        DATA / "fit-a/offline-labels.json",
        DATA / "payload-val-04/offline-labels.json",
        reader.CV / reader.T02_REL / "instance/offline-truth.json",
        DATA / "sealed-left/index.json",
        previous.OUT / "brackets.json",
    ):
        try:
            forbidden.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("predictions can access quarantined prior outcomes or labels")
    detector, marker_sha = reader.native_marker(reader.GENER)
    require(marker_sha == reader.PLAN["marker_sha256"], "detector changed")
    identities = {}
    for key, (path, scene, episode) in bindings.items():
        if key in GROUPS or key == "t02":
            identities[key] = reader.bound(path, scene, episode)
        else:
            identities[key] = reader.bind_fixture(path.parent, {"id": scene, "episode_id": episode})
    return detector, identities, camera


def predict(reg_sha, name):
    registration = load_registration(reg_sha)
    packets, bindings = packet_list()
    require(registration["packets"] == packets, "registration no longer binds prediction inputs")
    output = OUT / f"predictions-{name}.json"
    measure, instances, camera = open_inputs(packets, bindings, output)
    cv2.setNumThreads(1)
    measured = {}
    for key, entry in packets.items():
        identity, scene = instances[entry["binding"]]
        frame = reader.checked_packet(root / entry["path"], entry["sha256"])
        marker = measure(frame, scene)
        step = entry["step"]
        require(
            frame.frame_id == entry["frame_id"]
            and frame.checksum_sha256 == entry["checksum"]
            and frame.model_dump(mode="json", include=set(camera)) == camera
            and identity.matches(frame, marker, scene, step),
            f"frame linkage differs: {key}",
        )
        if entry["source_time_s"] is not None:
            require(frame.sim_time_s == entry["source_time_s"], f"source clock changed: {key}")
        record = inspect_packet(frame, marker, scene, identity, step, key == "t02/2112")
        if key == "t02/1512":
            for variant, tick in (
                (dict(marker, frame_id="foreign"), step),
                (dict(marker, usable_ids=[]), step),
                (marker, step + 8),
            ):
                require(
                    not inspect_packet(frame, variant, scene, identity, tick, False)["models"],
                    "unbound pose candidate admitted",
                )
        measured[key] = {
            "frame_id": frame.frame_id,
            "checksum_sha256": frame.checksum_sha256,
            "physics_step": step,
            **record,
        }
    reader.write(
        output, {"registration_sha256": reg_sha, "label_access_denied": True, "rows": measured}
    )


def physical_labels():
    labels = {}
    for group in GROUPS:
        filename = "offline-labels.json"
        location = DATA / group / filename
        for row in reader.read(reader.pin(location, group_files(group)[filename]))["physical"]:
            key = f"{group}/{row['file']}"
            require(key not in labels, "duplicate trajectory label")
            labels[key] = row
    truth = reader.read(reader.cv_pin(reader.T02_REL + "/instance/offline-truth.json"))
    for row in truth["samples"]:
        step = row["physics_step"]
        if 1504 <= step <= 2112 and step % 8 == 0:
            labels[f"t02/{step}"] = {
                "rotation": np.asarray(row["object_geom_rotation_row_major"]).reshape(3, 3),
                "center_m": row["object_geom_position_m"],
            }
    return labels


def measure_error(point, truth):
    gap = optics.CALIBRATION["id8_opposite_edges"]
    checked = reader.ratios(
        dict(point, anchor_error_object_m=gap["anchor"], basis_error_object=gap["basis"]),
        truth,
    )
    return {
        "anchor_ratio_max": max(checked["anchor_ratio"]),
        "basis_ratio_max": float(np.max(checked["basis_ratio"])),
        "corner_ratio": checked["cube_corner_ratio"],
        "corner_error_mm": checked["farthest_cube_corner_error_mm"],
        "covered_by_existing_diagnostic_range": (
            checked["current_valid_bounds"] and checked["cube_corner_ratio"] <= 1
        ),
    }


def score(registration_hash, expected):
    reg = load_registration(registration_hash)
    outputs = (OUT / "predictions-first.json", OUT / "predictions-second.json")
    first, second = (reader.pin(path, expected).read_bytes() for path in outputs)
    require(first == second, "cold predictions differ")
    result = json.loads(first)
    require(
        result["registration_sha256"] == registration_hash
        and result["label_access_denied"]
        and set(result["rows"]) == set(reg["packets"]),
        "predictions not tied to active register",
    )

    archived = reader.read(previous.OUT / "predictions-first.json")["rows"]
    for key, original in archived.items():
        translated = (
            key.replace("val04/", "payload-val-04/", 1) if key.startswith("val04/") else key
        )
        require(
            result["rows"][translated]["original"] == original["old_pose"],
            f"original candidate certificate changed: {translated}",
        )
    source_rows = result["rows"]
    require(
        all(
            not v["models"] and v["original"] is None
            for key, v in source_rows.items()
            if key.startswith(("A/", "B/"))
        ),
        "RELEASE static negative changed",
    )
    require(
        source_rows["t02/2112"]["status"] == "excluded_known_foreign_near_surface"
        and not source_rows["t02/2112"]["models"],
        "2112 boundary changed",
    )

    truth = physical_labels()
    require(
        set(truth) == {k for k in source_rows if not k.startswith(("A/", "B/"))},
        "label coverage of preregistered traces differs",
    )
    by_packet = {}
    counts = {group: Counter() for group in PLAN["counts"]}
    first_counterexample = None
    natural_episodes, natural_disclosed_episodes = set(), set()
    for key, row in source_rows.items():
        group = key.split("/", 1)[0]
        stat = counts[group]
        stat["frames"] += 1
        stat["original_qualified"] += row["original"] is not None
        for kind in ("masked", "natural"):
            stat[kind + "_source_frames"] += any(model["kind"] == kind for model in row["models"])
        for model in row["models"]:
            kind = model["kind"]
            stat[kind + "_comparisons"] += 1
            matched = model["matches_t02_support"]
            point = model["point"]
            if point is None:
                stat[kind + "_fit_refusals"] += 1
                continue
            metrics = measure_error(point, truth[key])
            covered = metrics["covered_by_existing_diagnostic_range"]
            condition = "covered" if covered else "outside"
            stat[f"{kind}_{condition}"] += 1
            if matched:
                stat[f"{kind}_t02_matched_{condition}"] += 1
            if covered and matched and kind == "natural" and group in GROUPS:
                natural_episodes.add(group)
                if group in PLAN["disclosed_validation"]:
                    natural_disclosed_episodes.add(group)
            detail = {
                "kind": kind,
                "side": model["side"],
                "weak_columns": model["weak_columns"],
                "matches_t02_support": matched,
                "frame": key,
                **metrics,
            }
            if not covered and first_counterexample is None:
                first_counterexample = detail
            by_packet.setdefault(key, []).append(detail)
    target = by_packet.get("t02/1512", [])
    adequate_natural = len(natural_episodes) >= PLAN["min_other_natural_episodes"]
    adequate_disclosed = (
        len(natural_disclosed_episodes) >= PLAN["min_disclosed_validation_natural_episodes"]
    )
    eligible = (
        bool(target)
        and all(x["covered_by_existing_diagnostic_range"] for x in target)
        and first_counterexample is None
        and adequate_natural
        and adequate_disclosed
    )
    reader.write(
        OUT / "readback.json",
        {
            "registration_sha256": registration_hash,
            "prediction_sha256": expected,
            "all_previous_certificates_identical": True,
            "counts": counts,
            "target_1512": target,
            "first_counterexample": first_counterexample,
            "metrics": by_packet,
            "natural_matching_other_episodes": sorted(natural_episodes),
            "natural_matching_disclosed_validation_episodes": sorted(natural_disclosed_episodes),
            "eligible_for_offline_relationship_shadow": eligible,
            "limits": PLAN["limits"],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("register", "predict", "score"))
    parser.add_argument("registration_sha", nargs="?")
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        registration()
    elif args.mode == "predict":
        require(args.argument in ("first", "second"), "prediction run not registered")
        predict(args.registration_sha, args.argument)
    else:
        score(args.registration_sha, args.argument)
