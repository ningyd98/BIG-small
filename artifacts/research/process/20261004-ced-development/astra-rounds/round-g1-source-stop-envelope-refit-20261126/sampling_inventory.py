"""Reproduce the legacy raw radius fit and count eligible source windows before new stops."""

import argparse
from pathlib import Path

import numpy as np
from precheck_expansion import HERE, PANDA, PLAN, REPO, ROOTS, require, source
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, support_axes
from scripts.graduation.g1_complete_cv_payload import SPEED_CLASSES, object_matrix
from scripts.graduation.g1_complete_cv_payload_fit import measurements
from scripts.graduation.perception_io import pinned, read, sha, write

REG = read(HERE / "sampling-inventory-registration.json")
OUT = ROOTS["output"]
INDEX = REG["inputs"]


def legacy(model):
    motion = MotionGeometry(model)
    directions = support_axes()
    profile = read(source("runtime/scripts/graduation/g1_complete_cv_source_motion_profile.json"))
    root = REPO / REG["raw_roots"]["legacy"]
    axis = {}
    hash_files = {}
    per_case = {}
    for case, h in profile["sources"].items():
        p = root / case
        idx = pinned(p / "index.json", h)
        require(
            idx["case"] == case
            and idx["role"] == "train"
            and idx["xml_sha256"] == profile["asset_sha256"],
            "legacy fit identity",
        )
        accepted = []
        for row in idx["phases"]["LIFT"]:
            file = p / row["file"]
            require(
                file.resolve().is_relative_to(p.resolve()) and sha(file) == row["sha256"],
                "legacy native stop bytes differ",
            )
            hash_files[str(file.relative_to(root))] = row["sha256"]
            with np.load(file, allow_pickle=False) as raw:
                q = raw["q"][0, 0]
            bottom = q[11] - abs(object_matrix(q[None])[0, 2]) @ model.object[0].h
            if not -0.001 <= bottom <= 0.025:
                continue
            world, _, speed, forbidden, _ = measurements(motion, file, directions)
            require(not forbidden, "original training includes a forbidden contact")
            accepted.append(row["step"])
            for key in ("all", *(str(k) for k in SPEED_CLASSES if speed <= k)):
                group = axis.setdefault(
                    key, {"world": np.zeros_like(world), "windows": 0, "sources": set()}
                )
                group["world"] = np.maximum(group["world"], world)
                group["windows"] += 1
                group["sources"].add(case)
        per_case[case] = accepted
    rebuilt = {
        name: {
            "world": (np.ceil(row["world"] * 1e8) / 1e8).tolist(),
            "windows": row["windows"],
            "sources": sorted(row["sources"]),
        }
        for name, row in axis.items()
        if len(row["sources"]) >= 2
    }
    require(rebuilt == profile["classes"], "legacy source profile did not reproduce")
    return {
        "classification": "original_numeric_fit_reproduced",
        "old_window_counts": {k: v["windows"] for k, v in rebuilt.items()},
        "legacy_window_ticks": per_case,
        "legacy_stops_sha256": hash_files,
        "old_window_current_optical_source_permission": "not recorded in the legacy stop index",
    }


def truth(case):
    if case == "t01":
        return {
            r["physics_step"]: r
            for r in pinned(ROOTS[case] / "offline-truth.json", INDEX["t01_truth"])["samples"]
        }
    index = read(source(f"{case}/rgbd-index.json"))
    records = {
        r["robot"]["frame_id"]: r["robot"]
        for r in index["rows"]
        if r["skill"] == "LIFT" and r["phase"] == "FEEDBACK"
    }
    matched = {}
    for row in pinned(ROOTS[case] / "offline-physics.json", INDEX[case + "_truth"])["frame_labels"]:
        robot = records.get(row["frame_id"])
        if robot is None:
            continue
        require(
            robot["physics_step"] == row["physics_step"]
            and robot["checksum_sha256"] == row["checksum_sha256"],
            "old frame identity changed",
        )
        matched[row["physics_step"]] = row
    return matched


def inventory(model, phase_zero):
    t01root = REPO / REG["raw_roots"]["t01_stops"]
    t01record = pinned(t01root / "result.json", INDEX["t01_stop_manifest"])
    grid04 = read(source("midRaw/reader-1.json"))["all_file_sha256"]
    result = {}
    for case, rows in phase_zero["candidate_source_frames_by_original_permission"].items():
        poses = truth(case)
        enrolled = []
        end = REG["original_source_normal_end_inclusive"][case]
        triggers = set()
        for tick, klass in rows:
            p = poses[tick]
            if case == "t01":
                bottom = p["object_bottom_z_m"]
            else:
                bottom = p["center_m"][2] - abs(np.asarray(p["rotation"])[2]) @ model.object[0].h
            if not -0.001 <= bottom <= 0.025:
                continue
            delays = [n for n in PLAN["fit_split"]["required_delays"] if tick + n <= end]
            triggers.update(tick + n for n in delays)
            enrolled.append(
                {
                    "tick": tick,
                    "original_selected_class": klass,
                    "bottom_m": float(bottom),
                    "verified_old_command_delay_indices": delays,
                }
            )
        reuse = {}
        for trigger in sorted(triggers):
            if case == "t01":
                file = f"{trigger}-after_integration.npz"
                expected = t01record["branches"].get(file)
                p = t01root / file
            elif case == "grid04":
                file = f"stops/stop-{trigger}.npz"
                expected = grid04.get(file)
                p = ROOTS["midRaw"] / file
            else:
                continue
            if expected:
                require(sha(p) == expected, "changed reusable stop trace")
                reuse[str(trigger)] = expected
        missing = sorted(triggers - {int(n) for n in reuse})
        result[case] = {
            "enrolled_windows": enrolled,
            "distinct_triggers": len(triggers),
            "reusable_stop_state_bytes_sha256": reuse,
            "new_stop_triggers_needed": missing,
            "missing_trigger_count": len(missing),
            "planned_new_stop_integrations": 240 * len(missing),
        }
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("reader", choices=("inventory-1", "inventory-2"))
    args = cli.parse_args()
    require(sha(HERE / "plan.json") == REG["original_plan_sha256"], "wrong phase parent")
    require(
        sha(ROOTS["runtime"] / "scripts/graduation/g1_complete_cv_payload_fit.py")
        == INDEX["old_fitter"],
        "legacy fitter drift",
    )
    stage = pinned(OUT / "reader-1.json", INDEX["phase_zero_readback"])
    require(sha(OUT / "reader-2.json") == INDEX["phase_zero_readback"], "stage zero readers differ")
    model = Model(source("runtime/" + PANDA))
    write(
        OUT / (args.reader + ".json"),
        {
            "legacy": legacy(model),
            "inventory": inventory(model, stage),
            "new_integrations": 0,
            "new_stop_outcomes_opened_from_challenge": 0,
            "registration_sha256": sha(HERE / "sampling-inventory-registration.json"),
            "source_sha256": sha(Path(__file__)),
        },
    )
