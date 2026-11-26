"""Recover the omitted verified scene scope in the unchanged original score reader."""

import argparse
import inspect
import json
import os
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from scripts.graduation import (
    dynamic_vision,
    dynamic_vision_score,
    g1_clearance_score,
    g1_dual_observer,
    g1_visibility_trials,
)
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.perception_io import pinned, read, sha

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
OUT = REPO / PLAN["output"]
BATCH = REPO / PLAN["batch"]
CASE = PLAN["case"]
require = g1_clearance_score.require


def store(path, result):
    with path.open("x") as output:
        json.dump(result, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")


def prepare():
    for rel, expected in PLAN["input_sha256"].items():
        require(sha(REPO / rel) == expected, f"frozen evidence changed: {rel}")
    batch, tree = g1_clearance_score.batch_inputs(BATCH, [CASE])
    require(
        tree == (REPO / PLAN["runtime_tree"]).resolve()
        and Path.cwd().resolve() == tree
        and Path(inspect.getfile(g1_clearance_score)).resolve().is_relative_to(tree)
        and Path(inspect.getfile(g1_dual_observer)).resolve().is_relative_to(tree)
        and batch["scope"] == "training",
        "unexpected cold runtime or evaluation scope",
    )
    lock = g1_clearance_score.verify_generation(tree, batch["runtime_build_sha256"])
    row, allocation, raw, started = g1_clearance_score.checked_case(BATCH, batch, CASE, tree)
    receipt = pinned(
        raw / "receipt.json", PLAN["input_sha256"][str((raw / "receipt.json").relative_to(REPO))]
    )
    seal = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    index = pinned(raw / "pixel-index.json", seal["index_sha256"])
    scene, episode = native_reset_ids(
        pinned(raw / "reset-observed.json", receipt["reset_sha256"]),
        row["scene_id"],
        receipt["physical_reset"]["episode_id"],
    )
    require(
        scene == allocation["case"]["scene_id"] == row["scene_id"] == index["scene"]
        and index["episode"] == episode
        and started["allocation_sha256"] == receipt["allocation_sha256"] == row["allocation_sha256"]
        and receipt["batch_sha256"] == sha(BATCH / "allocation.json")
        and allocation["runtime_build_sha256"] == batch["runtime_build_sha256"],
        "reset, allocation, receipt or index mismatch",
    )
    return batch, tree, lock, allocation, raw, receipt, index, scene, episode


def diagnose(inputs):
    _, _, _, allocation, raw, _, index, scene, episode = inputs
    cfg = PLAN["diagnostic_frame"]
    (row,) = [item for item in index["frames"] if item["frame_id"] == cfg["id"]]
    require(
        row["file"] == cfg["file"]
        and row["physics_step"] == cfg["step"]
        and row["checksum_sha256"] == cfg["checksum_sha256"],
        "unexpected source diagnostic exposure",
    )
    seal = read(raw / "online-vision-seal.json")
    trace = pinned(raw / "online-vision.json", seal["online_vision_sha256"])
    original = trace["frames"][cfg["id"]]["measurement"]
    first = raw.parent / "independent-readback-3fafpry8/reader-1"
    blind = read(first / "blind/seal.json")
    anon = pinned(first / "pixels/index.json", blind["index_sha256"])
    (key,) = blind["packets"]
    require(
        key == sha(raw / "pixel-index.json") and key in anon and blind["n_frames"] == 186,
        "unbound previous blind packet",
    )
    summaries = pinned(first / "blind" / f"{key}.json", blind["packets"][key])
    (summary,) = [item for item in summaries if item["frame_id"] == cfg["id"]]
    require(
        summary["checksum_sha256"] == cfg["checksum_sha256"]
        and summary["file_sha256"] == row["file_sha256"]
        and summary["physics_step"] == cfg["step"],
        "prior blind read differs from receipt exposure",
    )
    geometry = allocation["geometry"]
    frame = dynamic_vision_score.frame_from_row(raw, row, episode, scene, geometry)
    before = g1_dual_observer.measure_frame(frame, geometry)
    with bind_scene(scene + "/wrong-control"):
        wrong = g1_dual_observer.measure_frame(frame, geometry)
    with bind_scene(scene):
        repaired = g1_dual_observer.measure_frame(frame, geometry)
    after = g1_dual_observer.measure_frame(frame, geometry)
    require(
        before["reason"] == wrong["reason"] == "registered_scene_mismatch"
        and after == before
        and g1_visibility_trials.matches_online(summary, original)
        and g1_visibility_trials.matches_online(summary, repaired)
        and repaired["selected_id"] == 8
        and repaired["usable_ids"] == [8],
        "recorded scene diagnostic did not reproduce",
    )
    encoded = [
        json.dumps(dynamic_vision.plain(value), sort_keys=True, allow_nan=False).encode()
        for value in (original, repaired)
    ]
    old, new = map(json.loads, encoded)
    OUT.mkdir(exist_ok=True, parents=True)
    store(
        OUT / "diagnostic.json",
        {
            "without_scope": before["reason"],
            "wrong_scene_control": wrong["reason"],
            "restored_default": after["reason"],
            "registered_scene": scene,
            "frame_file_sha256": sha(raw / row["file"]),
            "checksum_sha256": frame.checksum_sha256,
            "step": row["physics_step"],
            "with_verified_scope": repaired["reason"],
            "matches_frozen_independent_pixel_contract": True,
            "full_online_marker_dictionary_equal": old == new,
            "first_canonical_difference": first_difference(old, new),
            "online_and_recomputed_dictionary_sha256": [
                sha256(value).hexdigest() for value in encoded
            ],
            "plan_sha256": sha(HERE / "plan.json"),
            "plan_md_sha256": sha(HERE / "plan.md"),
            "recovery_program_sha256": sha(Path(__file__)),
        },
    )


def first_difference(old, new, path=""):
    if type(old) is not type(new) or old is None or new is None:
        return (
            None
            if type(old) is type(new)
            else {
                "path": path,
                "types": [type(old).__name__, type(new).__name__],
            }
        )
    if isinstance(old, dict):
        for key in sorted(old.keys() | new.keys()):
            move = f"{path}/{key}"
            if key not in old or key not in new:
                return {"path": move, "presence": [key in old, key in new]}
            found = first_difference(old[key], new[key], move)
            if found:
                return found
    elif isinstance(old, list):
        if len(old) != len(new):
            return {"path": path, "lengths": [len(old), len(new)]}
        for index, (a, b) in enumerate(zip(old, new, strict=True)):
            found = first_difference(a, b, f"{path}/{index}")
            if found:
                return found
    elif old != new:
        return {"path": path, "types": [type(old).__name__, type(new).__name__]}
    return None


def recover(inputs, name):
    batch, tree, lock, allocation, raw, receipt, index, scene, episode = inputs
    diagnostic = read(OUT / "diagnostic.json")
    require(
        diagnostic["matches_frozen_independent_pixel_contract"]
        and diagnostic["registered_scene"] == scene
        and diagnostic["recovery_program_sha256"] == sha(Path(__file__))
        and diagnostic["plan_sha256"] == sha(HERE / "plan.json"),
        "unbound prerequisite diagnosis",
    )
    area = OUT / name
    area.mkdir(exist_ok=False)
    original = g1_clearance_score.replay_payload_pixels
    calls = 0

    def scoped(
        raw_arg, index_arg, allocation_arg, receipt_arg, generation, events, physics, commands
    ):
        nonlocal calls
        require(
            calls == 0
            and raw_arg == raw
            and index_arg == index
            and allocation_arg == allocation
            and receipt_arg == receipt
            and index_arg["episode"] == episode
            and generation == batch["runtime_build_sha256"],
            "replay lost its verified case binding",
        )
        calls += 1
        with bind_scene(scene):
            return original(
                raw_arg,
                index_arg,
                allocation_arg,
                receipt_arg,
                generation,
                events,
                physics,
                commands,
            )

    complete = False
    try:
        with patch.object(g1_clearance_score, "replay_payload_pixels", scoped):
            result = g1_clearance_score.read_slot(BATCH, batch, tree, CASE, area, lock)
        require(calls == 1, "missing or repeated scoped replay")
        store(area / "result.json", result)
        complete = True
    finally:
        store(
            area / "process.json",
            {
                "pid": os.getpid(),
                "complete": complete,
                "binding_calls": calls,
                "original_receipt_sha256": sha(raw / "receipt.json"),
                "frozen_scorer_sha256": sha(Path(inspect.getfile(g1_clearance_score))),
                "recovery_program_sha256": sha(Path(__file__)),
                "diagnostic_sha256": sha(OUT / "diagnostic.json"),
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("diagnose", "reader-1", "reader-2"))
    args = parser.parse_args()
    inputs = prepare()
    if args.mode == "diagnose":
        diagnose(inputs)
    else:
        recover(inputs, args.mode)


if __name__ == "__main__":
    main()
