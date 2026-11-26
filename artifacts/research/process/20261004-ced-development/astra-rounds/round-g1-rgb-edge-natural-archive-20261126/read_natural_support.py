"""Evaluate frozen RGB plane refinement on natural weak-edge archives."""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
REFIT = HERE.parent / "round-g1-rgb-edge-plane-refit-20261126"
DENSE = HERE.parent / "round-g1-continuous-payload-observation-20261125"
sys.path[:0] = [str(REFIT), str(DENSE)]
import read_dense_payload as dense  # noqa: E402
import read_plane_refit as refit  # noqa: E402

reader, require, root = refit.reader, refit.require, refit.root
core, previous = refit.core, refit.previous
BASE = root / "experiments/results/g1-continuous-payload-observation-20261125"
SOURCE = BASE / "physical-03"
OUT = root / "experiments/results/g1-rgb-edge-natural-archive-20261126/development-01"
PLAN = reader.read(HERE / "plan.json")
OPTICAL_SOURCE = {
    "refit": REFIT,
    "refit_result": refit.OUT,
    "dense": DENSE,
}


def verified_inputs():
    for alias, digest in PLAN["pins"].items():
        kind, name = alias.split("/", 1)
        reader.pin(OPTICAL_SOURCE[kind] / name, digest)


def case_path(case, name):
    return reader.pin(SOURCE / case / name, PLAN["cases"][case]["sha256"][name])


def metadata():
    packets, bindings = reader.exposure_metadata()
    controls = {k: v for k, v in packets.items() if not k.startswith("val04/")}
    bindings = {k: v for k, v in bindings.items() if k != "val04"}
    registration = reader.read(DENSE / "continuous-diagnostic-registration.json")
    slots = {r["id"]: r for label in ("fit", "holdout") for r in registration[label]}
    episodes = {}
    for case in PLAN["cases"]:
        receipt = reader.read(case_path(case, "sensor-receipt.json"))
        index = reader.read(case_path(case, "rgbd-index.json"))
        require(
            receipt["id"] == case
            and receipt["episode_id"] == index["episode_id"]
            and receipt["index_sha256"] == PLAN["cases"][case]["sha256"]["rgbd-index.json"]
            and receipt["registration_sha256"]
            == sha(DENSE / "continuous-diagnostic-registration.json")
            and receipt["asset_sha256"] == registration["native_controller_asset_sha256"],
            f"receipt did not bind registered experiment: {case}",
        )
        steps = [r["robot"]["physics_step"] for r in index["rows"]]
        require(
            len(steps) == PLAN["cases"][case]["count"] and steps == sorted(steps),
            f"wrong source role count or order: {case}",
        )
        episodes[case] = {
            "episode_id": receipt["episode_id"],
            "scene_id": index["scene_id"],
            "physics_seed": slots[case]["physics_seed"],
            "depth_seed": slots[case]["depth_seed"],
            "frame_count": len(steps),
            "physical_steps_reused": len(steps) - len(set(steps)),
        }
        for name, entry in enumerate(index["rows"]):
            stem = f"{name:04}.json.gz"
            require(entry["file"] == stem, f"non-canonical exposure file: {case}")
            robot = entry["robot"]
            key = f"{case}/{stem}"
            require(
                robot["sim_time_s"] == robot["camera_encoder_sim_time_s"],
                f"encoder and exposure clock differ in {key}",
            )
            reader.add_packet(
                controls,
                key,
                SOURCE / case,
                stem,
                dict(robot, file_sha256=entry["file_sha256"]),
                robot["physics_step"],
                case,
                native_time=robot["sim_time_s"],
            )
            controls[key].update(skill=entry["skill"], phase=entry["phase"])
    require(
        len({x["episode_id"] for x in episodes.values()}) == len(PLAN["cases"]),
        "historical episodes reused across seeds",
    )
    require(
        len({x["physics_seed"] for x in episodes.values()}) == len(PLAN["cases"]),
        "history seeds reused across cases",
    )
    require(
        len(controls) == PLAN["frames"] + PLAN["controls"]
        and len({x["frame_id"] for x in controls.values()}) == len(controls),
        "wrong exposure counts or reused frame identity",
    )
    return dict(sorted(controls.items())), episodes, bindings


def register():
    verified_inputs()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    require(head == PLAN["head"], "Astra baseline differs")
    packets, episodes, _ = metadata()
    for case in episodes:
        for file in PLAN["cases"][case]["sha256"]:
            case_path(case, file)
    for entry in packets.values():
        reader.pin(root / entry["path"], entry["sha256"])
    core.check_geometry_controls()
    require(
        PLAN["fixed_strong_columns"] == core.PLAN["target_comparison_strong_count"]
        and PLAN["fixed_strong_span_px"] == core.PLAN["target_comparison_strong_span_px"],
        "original natural support thresholds changed",
    )
    OUT.mkdir(parents=True, exist_ok=False)
    reader.write(
        OUT / "registration.json",
        {
            "driver_sha256": sha(Path(__file__)),
            "plan_sha256": sha(HERE / "plan.json"),
            "episodes": episodes,
            "packets": packets,
        },
    )


def registered(digest):
    record = reader.read(reader.pin(OUT / "registration.json", digest))
    require(
        record["driver_sha256"] == sha(Path(__file__))
        and record["plan_sha256"] == sha(HERE / "plan.json"),
        "acquisition plan or driver differs",
    )
    return record


def match(frame, marker, geometry, identity, tick, excluded):
    old = optics.rigid_pose(frame, marker, geometry, identity=identity, physics_step=tick)
    answer = {"original_method": old["method"] if old else None, "candidate": None}
    if excluded:
        return dict(answer, status="known_unattributed_near_surface")
    if not identity.matches(frame, marker, geometry, tick) or marker.get("usable_ids") != [8]:
        return dict(answer, status="no_bound_single_id8")
    measured, states = previous.original_state(frame, marker, geometry)
    if not measured or set(states) != {-1, 1}:
        return dict(answer, status="no_native_paired_edge_state")
    rgb = {side: previous.original_pixels(states[side])[1] for side in (-1, 1)}
    counts = {side: core.spans(points) for side, points in rgb.items()}
    answer["native_columns_and_span"] = counts
    weak = [side for side, count in counts.items() if count == (4, 3)]
    if len(weak) != 1:
        return dict(answer, status="no_natural_four_column_side")
    (side,) = weak
    count, span = counts[-side]
    if count < PLAN["fixed_strong_columns"] or span < PLAN["fixed_strong_span_px"]:
        return dict(answer, status="opposite_side_below_target_support")
    line = core.one_fit(measured, states, rgb, side, rgb[side][:, 0], "natural")
    require(
        line["matches_t02_support"] and core.consecutive_windows(rgb[side][:, 0]) == [0],
        "natural side does not consist of four consecutive native columns",
    )
    answer["candidate"] = line
    if line["point"] is None:
        return dict(answer, status="original_metric_fit_refused")
    extension = refit.refined(line["point"], states, rgb, marker)
    line["extension"] = extension
    return dict(answer, status=extension["status"])


def optical_inputs(packets, episodes, bindings, output):
    calibration = reader.cv_pin(reader.CAL_REL + "/manifest.json")
    camera = reader.read(calibration)["primary_camera"]
    allow = {root / item["path"] for item in packets.values()}
    allow.update(SOURCE / c / "native-resets.json" for c in episodes)
    allow.update(path.resolve() for path, _, _ in bindings.values())
    allow.update(
        {
            output,
            calibration,
            reader.RUNTIME / "runtime-build.json",
            reader.RUNTIME / "scripts/graduation/g1_visibility_vision.py",
            reader.CV / "batches/train-full-04/allocation.json",
            reader.CV / reader.T02_REL / "allocation.json",
        }
    )

    def deny_labels(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(root / "experiments/results") and path not in allow:
                raise PermissionError("outside isolated current RGB-D inputs")

    sys.addaudithook(deny_labels)
    for blocked in (
        SOURCE / "dense-check-01/offline-physics.json",
        SOURCE / "dense-fit-01/offline-physics.json",
        BASE / "dense-check-01-score-02.json",
        refit.OUT / "predictions-first.json",
        reader.CV / "payload-optics-01/sealed-left/index.json",
    ):
        try:
            blocked.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("input quarantine did not reject prior outcomes")
    measure, detector = reader.native_marker(reader.GENER)
    require(detector == reader.PLAN["marker_sha256"], "optical tool generation changed")
    identities = {
        case: dense.bind_fixture(SOURCE / case, {"id": case, "episode_id": record["episode_id"]})
        for case, record in episodes.items()
    }
    for key, (path, scene, episode) in bindings.items():
        if key == "t02":
            identities[key] = reader.bound(path, scene, episode)
        else:
            identities[key] = reader.bind_fixture(path.parent, {"id": scene, "episode_id": episode})
    return measure, identities, camera


def predict(digest, name):
    reg = registered(digest)
    packets, episodes, bindings = metadata()
    require(reg["packets"] == packets and reg["episodes"] == episodes, "native registry differs")
    output = OUT / f"predictions-{name}.json"
    detector, identities, camera = optical_inputs(packets, episodes, bindings, output)
    cv2.setNumThreads(1)
    rows = {}
    for key, entry in packets.items():
        identity, geometry = identities[entry["binding"]]
        frame = reader.checked_packet(root / entry["path"], entry["sha256"])
        require(
            frame.frame_id == entry["frame_id"]
            and frame.checksum_sha256 == entry["checksum"]
            and frame.model_dump(mode="json", include=set(camera)) == camera
            and (entry["source_time_s"] is None or frame.sim_time_s == entry["source_time_s"]),
            f"native packet and registered exposure differ: {key}",
        )
        tick = entry["step"]
        marker = detector(frame, geometry)
        require(identity.matches(frame, marker, geometry, tick), f"unbound current exposure: {key}")
        result = match(frame, marker, geometry, identity, tick, key == "t02/2112")
        if key == "t02/1512":
            for wrong, off in (
                (dict(marker, episode_id="wrong"), 0),
                (marker, 8),
                (dict(marker, usable_ids=[7]), 0),
            ):
                require(
                    match(frame, wrong, geometry, identity, tick + off, False)["candidate"] is None,
                    "identity or sequence control admitted",
                )
        rows[key] = dict(
            result,
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            physics_step=tick,
            skill=entry.get("skill"),
            phase=entry.get("phase"),
        )
    reader.write(output, {"registration_sha256": digest, "label_access_denied": True, "rows": rows})


def check_controls(rows):
    frozen = reader.read(refit.OUT / "predictions-first.json")["rows"]
    group = {k: v for k, v in rows.items() if k.split("/")[0] not in PLAN["cases"]}
    require(len(group) == PLAN["controls"], "wrong isolated control size")
    for key, current in group.items():
        before = frozen[key]["original"]
        require(
            current["original_method"] == (before["method"] if before else None),
            f"original optical control changed: {key}",
        )
        if key.startswith(("A/", "B/")) or key == "t02/2112":
            require(current["candidate"] is None, f"original exclusion changed: {key}")
    current = rows["t02/1512"]["candidate"]
    (before,) = frozen["t02/1512"]["models"]
    require(current["extension"] == before["extension"], "known natural plane control changed")
    require(
        rows["t02/2112"]["status"] == "known_unattributed_near_surface",
        "2112 original near-surface exclusion was lost",
    )


def checked_score(rows, reg):
    packet_metrics = {}
    totals, stages, methods = {}, {}, {}
    for case, spec in PLAN["cases"].items():
        truth_path = case_path(case, "offline-physics.json")
        truth = reader.read(truth_path)["frame_labels"]
        require(len(truth) == spec["count"], f"physical label count changed: {case}")
        totals[case], stages[case], methods[case] = Counter(), {}, Counter()
        stage, totals_case = stages[case], totals[case]
        last = None
        for position, label in enumerate(truth):
            key = f"{case}/{position:04}.json.gz"
            row, packet = rows[key], reg["packets"][key]
            require(
                row["frame_id"] == label["frame_id"] == packet["frame_id"]
                and row["checksum_sha256"] == label["checksum_sha256"] == packet["checksum"]
                and row["physics_step"] == label["physics_step"] == packet["step"],
                f"optical result and physical label do not refer to the same exposure: {key}",
            )
            role = f"{row['skill']}/{row['phase']}"
            group = stage.setdefault(role, Counter())
            totals_case["frames"] += 1
            group["frames"] += 1
            methods[case][row["original_method"] or "no_current_original_pose"] += 1
            candidate = row["candidate"]
            if candidate is None:
                totals_case[row["status"]] += 1
                last = None
                continue
            tick = row["physics_step"]
            if last is None or (role, tick - 8) != last:
                totals_case["natural_segments"] += 1
            last = (role, tick)
            totals_case["natural_matches"] += 1
            group["natural_matches"] += 1
            contact = {frozenset(pair) for pair in label["touching"]}
            bilateral = all(
                frozenset((finger, "object_geom")) in contact
                for finger in ("left_finger_geom", "right_finger_geom")
            )
            outcome = None
            if row["status"] == "refitted":
                outcome = refit.evaluate(candidate["extension"]["point"], label)
                covered = outcome["covered_by_existing_diagnostic_range"]
                category = "inside" if covered else "outside"
            else:
                category = row["status"]
            totals_case[category] += 1
            group[category] += 1
            totals_case["with_no_native_pose"] += row["original_method"] is None
            group["with_no_native_pose"] += row["original_method"] is None
            group["physical_bilateral_contact"] += bilateral
            packet_metrics[key] = {
                "role": role,
                "step": tick,
                "original_method": row["original_method"],
                "weak_columns": candidate["weak_columns"],
                "weak_side": candidate["side"],
                "strong_columns": candidate["strong_columns"],
                "category": category,
                "physical_bilateral_contact": bilateral,
                "pose_errors": outcome,
            }
    return totals, stages, methods, packet_metrics


def score(reg_sha, prediction_sha):
    verified_inputs()
    reg = registered(reg_sha)
    a, b = (
        reader.pin(OUT / f"predictions-{part}.json", prediction_sha).read_bytes()
        for part in ("first", "second")
    )
    require(a == b, "cold predictions differ")
    predictions = json.loads(a)
    require(
        predictions["registration_sha256"] == reg_sha
        and predictions["label_access_denied"]
        and set(predictions["rows"]) == set(reg["packets"]),
        "prediction registry changed",
    )
    check_controls(predictions["rows"])
    counts, stages, methods, metrics = checked_score(predictions["rows"], reg)
    episodes = sorted(c for c, outcomes in counts.items() if outcomes["natural_matches"] > 0)
    check = [c for c in episodes if c.startswith("dense-check-")]
    lift = sorted(
        c
        for c, roles in stages.items()
        if roles.get("LIFT/FEEDBACK", {}).get("natural_matches", 0) > 0
    )
    all_cover = bool(metrics) and all(v["category"] == "inside" for v in metrics.values())
    basis = (
        all_cover
        and len(episodes) >= PLAN["min_independent_matching_episodes"]
        and len(check) >= PLAN["min_disclosed_check_episodes"]
        and bool(lift)
    )
    reader.write(
        OUT / "readback.json",
        {
            "registry_sha256": reg_sha,
            "predictions_sha256": prediction_sha,
            "episodes": reg["episodes"],
            "counts": counts,
            "stages": stages,
            "original_methods": methods,
            "natural_results": metrics,
            "natural_episodes": episodes,
            "check_episodes": check,
            "lift_feedback_episodes": lift,
            "all_candidates_in_old_diagnostic_limits": all_cover,
            "basis_for_planning_offline_relation_replay": basis,
            "online_authority": False,
            "limits": PLAN["new_counts"],
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
        require(args.argument in ("first", "second"), "unregistered cold process")
        predict(args.registration_sha, args.argument)
    else:
        score(args.registration_sha, args.argument)
