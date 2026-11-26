"""Cold-check covered-view decisions directly using the unchanged project predicate."""
import argparse
import itertools
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from scripts.graduation.g1_complete_cv_clearance import BAND, _covers
from registered_volume import VIEWS, preflight, read, require, sha, write


def grid(low, high):
    cuts = tuple((a, (a+b)/2, b) for a, b in zip(low, high, strict=True))
    return [np.array(list(itertools.product(*(axis[i:i+2] for axis, i in zip(cuts, idx, strict=True)))))
            for idx in itertools.product(range(2), repeat=3)]


def audit_current_clearance(archive, plan, cases):
    t01, t02 = (cases[key] for key in ("t01", "t02"))
    require(t01["status"] == "CLEAR" and t01["short_motion"]["reason"] is None
            and t02["reason"] == "unregistered_near_surface" and not t02["visited_bodies"],
            "current unchanged-gate contrast did not reproduce")
    profile_dir = Path("scripts/graduation")
    regional = read(profile_dir / "g1_complete_cv_source_motion_profile.json")
    general = read(profile_dir / "g1_complete_cv_payload_profile.json")
    motion = t01["short_motion"]
    require(motion["registered_source_speed_class"] == "0.075", "wrong source class")
    special = regional["classes"][motion["registered_source_speed_class"]]
    general_class = general["phases"]["LIFT"]["classes"][motion["speed_class"]]
    require(special["windows"] == motion["registered_source_windows"], "wrong source reference")

    calibration = Path(plan["roots"]["cv"]) / "calibration-gpu-01"
    manifest = read(calibration / "manifest.json")
    maps = [(row["camera"], np.load(calibration / row["depth_file"], allow_pickle=False))
            for row in [manifest["maps"][name] for name in VIEWS]]
    assets = [name for name in plan["sha256"] if name.endswith(".xml")]
    require(len(assets) == 1, "missing frozen table asset")
    table = ElementTree.parse(assets[0]).find(".//geom[@name='table']")
    floor = float(table.attrib["pos"].split()[2]) + float(table.attrib["size"].split()[2])
    frozen = read(archive / "enclosures.json")["by_frame"][t01["frame"]]
    require([row["body"] for row in frozen] == regional["parts"], "unverified or reordered solid")
    native_t01 = next(row["current"] for row in read(archive / "t01.json")["rows"]
                      if row["frame"] == t01["frame"])
    allow_workpiece = native_t01["source_table_support"]["qualified"]
    require(allow_workpiece, "source support authorization absent")
    pads = {}
    for body, row in enumerate(frozen):
        name = row["body"]
        vertices = np.asarray(row["world_vertices_m"])
        local_pad = np.asarray(row["world_pad_m"])
        low = vertices.min(axis=0) - local_pad[1::2]
        high = vertices.max(axis=0) + local_pad[0::2]
        require(np.array_equal(low, row["low_m"]) and np.array_equal(high, row["high_m"])
                and row["callback_pad_m"] == [0, 0, 0], "wrong envelope source")
        points = np.array(list(itertools.product(*zip(low, high, strict=True))))
        bottom_contact = name == "object_geom"
        if bottom_contact:
            points[:, 2] = np.maximum(points[:, 2], floor)
        require(row["original_callback"] and any(
            _covers(points, camera, depth, 2*BAND if bottom_contact else 0)
            for camera, depth in maps
        ), f"unchanged volume predicate did not cover {name}")
        if name in motion["finger_table_lower_m"]:
            source_pad = np.array(special["world"][body]) * 1.25 + 0.0005
            broad_pad = np.array(general_class["world"][body]) * 1.25 + 0.0005
            require(np.array_equal(source_pad, local_pad), "source profile does not reproduce pad")
            new_gap = vertices[:, 2].min() - floor - source_pad[5]
            old_gap = vertices[:, 2].min() - floor - broad_pad[5]
            require(new_gap == motion["finger_table_lower_m"][name], "finger/table gap mismatch")
            pads[name] = {"qualified_source_gap_m": float(new_gap),
                          "same_pose_generic_gap_m": float(old_gap),
                          "source_down_pad_m": float(source_pad[5]),
                          "generic_down_pad_m": float(broad_pad[5])}
    t02_rows = [row for row in read(archive / "t02.json")["rows"] if row["phase"] == "LIFT/feedback"]
    first = next(row for row in t02_rows if row["current"]["status"] != "CLEAR")
    return {
        "t01_current_enclosures_covered": len(frozen),
        "t01_finger_projection_lower_bounds": pads,
        "t02_first_archived_feedback_refusal": {
            "step": first["step"], "reason": first["current"]["reason"],
            "observer_reason": first["current"]["payload_observation"]["evidence"].get("reason"),
        },
    }


def audit(archive, result):
    plan, _, _ = preflight()
    payload = read(result)
    require(payload["seal_sha256"] == sha(archive / "sealed.json"), "wrong acquisition digest")
    for name, digest in read(archive / "sealed.json").items():
        require(sha(archive / name) == digest, f"frozen archive drift {name}")
    for name, case in payload["cases"].items():
        source = next(row for row in read(archive / f"{name}.json")["rows"] if row["frame"] == case["frame"])
        require(source["step"] == case["step"], f"wrong source frame {name}")
        for key in ("reason", "status"):
            require(case[key] == source["current"][key], f"inconsistent {name} {key}")
    summary = {"comparison_sha256": sha(result), "baseline_reproduced": payload["baseline_reproduced"],
               "same_view": None, "checked_boxes": 0}
    if not payload["baseline_reproduced"]:
        require("candidate" not in payload, "candidate attempted after baseline drift")
        return summary | audit_current_clearance(archive, plan, payload["cases"])

    candidate = payload["candidate"]
    require(candidate["body"] == "left_finger_geom", "wrong covered body")
    cases = payload["cases"]
    require(cases["t02"]["reason"] == "unregistered_near_surface" and not cases["t02"]["visited_bodies"],
            "near-surface refusal passed into volume check")
    boxes = grid(candidate["low_m"], candidate["high_m"])
    source = next(row for row in read(archive / "enclosures.json")["by_frame"][cases["t01"]["frame"]]
                  if row["body"] == candidate["body"])
    require(not source["original_callback"] and
            candidate["low_m"] == source["low_m"] and candidate["high_m"] == source["high_m"],
            "proposed decomposition changes the registered original enclosure")
    all_corners = {tuple(p) for box in boxes for p in box}
    require(set(itertools.product(*zip(candidate["low_m"], candidate["high_m"]))) <= all_corners,
            "missing original corner")
    totals = {}
    calibration = Path(plan["roots"]["cv"]) / "calibration-gpu-01"
    manifest = read(calibration / "manifest.json")
    for name in VIEWS:
        registered = manifest["maps"][name]
        depth = np.load(calibration / registered["depth_file"], allow_pickle=False)
        # A non-finite return cannot supply a distance lower bound.
        clean_depth = np.where(np.isfinite(depth) & (depth > 0), depth, 0)
        expected = candidate["views"][name]
        require(_covers(np.array(source["query_corners_m"]), registered["camera"], depth, 0)
                == expected["whole"]["original"], "original envelope mismatch")
        cells = [_covers(box, registered["camera"], clean_depth, 0) for box in boxes]
        require(cells == [item["valid_coverage"] for item in expected["children"]],
                f"subcell coverage mismatch for {name}")
        totals[name] = sum(cells)
    choose = next((name for name in VIEWS if totals[name] == 8), None)
    require(choose == candidate["covered_view"], "same-view criterion mismatch")
    return summary | {"same_view": choose, "checked_boxes": 16, "passing_subcells": totals}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("raw", type=Path)
    cli.add_argument("result", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    write(args.output, audit(args.raw, args.result))
