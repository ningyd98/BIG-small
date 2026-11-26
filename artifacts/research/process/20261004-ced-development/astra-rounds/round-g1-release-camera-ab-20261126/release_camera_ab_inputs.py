"""Read and verify the sealed inputs for the G1 RELEASE camera comparison."""

import gzip
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np

from scripts.graduation.perception_io import read, sha
from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
PLAN = read(HERE / "plan.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expand(name):
    while "{" in name:
        name = re.sub(r"\{([A-Z]+)\}", lambda m: PLAN["roots"][m[1]], name)
    path = ROOT / name
    require(path.resolve().is_relative_to(ROOT), f"input leaves worktree: {name}")
    return path


def inside(folder, name):
    path = folder / name
    require(path.resolve().is_relative_to(folder.resolve()), f"input leaves {folder.name}")
    return path


def canonical(data):
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def create(path, data):
    with path.open("xb") as stream:
        stream.write(data)


def write(path, data):
    create(path, canonical(data))


def packet(path):
    return RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))


def source_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Existing independent release geometry and optical readers.
sys.path[:0] = [str(expand("{O}")), str(expand("{P}"))]


def slot_key(arm, cid, tick):
    return f"{arm}/{cid}/{tick}"


def ordered_keys(arm):
    return [slot_key(arm, case["id"], tick) for case in PLAN["cases"] for tick in case["ticks"]]


def originals():
    manifest = ROOT / "experiments/results/g1-formal-paired-20261124/originals-manifest.json"
    tag = "642b48f85b742cbc76994c069bfeaf8f02a6caa219c9802bd93ca2895b347490"
    require(sha(manifest) == tag, "frozen formal originals manifest changed")
    files = read(manifest)["files"]
    size = 0
    for name, entry in files.items():
        path = inside(manifest.parent, name)
        require(sha(path) == (entry if isinstance(entry, str) else entry["sha256"]), name)
        size += path.stat().st_size
    require((len(files), size) == (919, 487_931_885), "wrong frozen formal inventory")
    return {"count": len(files), "bytes": size, "manifest_sha256": tag}


def verify_inputs():
    from release_clearance_probe import design, enrolled
    from read_dense_payload import bind_fixture

    manifest = {}

    def pin(path, expected):
        name = path.relative_to(ROOT).as_posix()
        require(path.resolve().is_relative_to(ROOT) and path.is_file(), f"missing input: {name}")
        require(sha(path) == expected, f"SHA256 mismatch: {name}")
        manifest[name] = expected
        return path

    for name, expected in PLAN["verified_input_sha256"].items():
        pin(expand(name), expected)
    for tag, size in (("M", 591), ("D", 608)):
        runtime = expand("{" + tag + "}")
        files = read(runtime / "runtime-build.json")["runtime_files_sha256"]
        require(len(files) == size, f"wrong native {tag} file count")
        for name, expected in files.items():
            pin(inside(runtime, name), expected)
    terminal = source_module("sealed_rebound", expand("{T}/terminal_rebound.py"))
    previous = read(expand("{T}/plan.json"))
    for name, expected in previous["runtime_inputs_sha256"].items():
        path = inside(expand("{M}"), name)
        if path.is_dir():
            entries = [p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()]
            require(terminal.tree_digest(path, entries) == expected, "Panda asset tree changed")
        else:
            pin(path, expected)

    optical_plan, extension = design()
    older = expand("{F}")
    require(ROOT / optical_plan["input_root"] == older, "older optical root changed")
    for name, expected in optical_plan["input_sha256"].items():
        pin(inside(older, name), expected)
    calibration = expand("{G}/calibration-gpu-01/manifest.json")
    cal = read(calibration)
    for record in cal["frames"]:
        pin(inside(calibration.parent, record["file"]), record["sha256"])
    for record in cal["maps"].values():
        pin(inside(calibration.parent, record["depth_file"]), record["depth_sha256"])
    native = PLAN["native_protocol"]
    require(
        cal["depth_sigma_m"] == native["depth_sigma_m"]
        and cal["renderer"]["renderer"] == native["renderer"]
        and cal["renderer"]["version"] == native["gl_version"]
        and cal["primary_camera"]["intrinsics"] == native["intrinsics"]
        and cal["primary_camera"]["calibration_version"] == native["calibration_version"],
        "calibration protocol differs",
    )

    old_shadow = read(expand("experiments/results/g1-release-optical-separation-20261125/shadow-fit-01/predictions.json"))
    rebound = read(expand("{T}/terminal-rebound.public.json"))
    slots = {}
    for case, registered in zip(previous["cases"], PLAN["cases"], strict=True):
        cid = case["id"]
        require(
            (cid, case["open_tick"], case["arm_open_seq"], case["seed"]) ==
            (registered["id"], registered["open_tick"], registered["terminal_seq"], registered["original_physics_seed"]),
            f"case schedule mismatch: {cid}",
        )
        folder = older / "physical-03" / cid
        for filename, expected in zip(previous["fit_file_order"], case["file_sha256"], strict=True):
            pin(inside(folder, filename), expected)
        _, raw_receipt, original_commands, enrolled_rows = enrolled(cid, optical_plan, extension)
        identity, geometry = bind_fixture(folder, raw_receipt)
        require(geometry["camera"] == cal["primary_camera"], f"fixture camera changed: {cid}")
        shadow_rows = old_shadow["cases"][cid]["records"]
        require(len(shadow_rows) == len(enrolled_rows) == 33, f"bad historical release denominator: {cid}")
        by_name = {}
        historic_labels = {r["frame_id"]: r for r in read(folder / "offline-physics.json")["frame_labels"]}
        for (item, previous_record), prediction in zip(enrolled_rows, shadow_rows, strict=True):
            path = pin(inside(folder, item["file"]), item["file_sha256"])
            frame = packet(path)
            robot = item["robot"]
            label = historic_labels[frame.frame_id]
            step = robot["physics_step"]
            require(
                frame.scene_id == identity.scene_id and frame.episode_id == identity.episode_id
                and frame.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
                and frame.frame_id == robot["frame_id"] == prediction["frame_id"] == previous_record["frame_id"]
                and frame.checksum_sha256 == robot["checksum_sha256"] == label["checksum_sha256"] == prediction["checksum_sha256"]
                and step == label["physics_step"] == prediction["step"]
                and prediction["qualified_pose_method"] is None
                and prediction["revised_per_corner_intervals_m"] is None,
                f"original frame/prediction/pose label mismatch: {cid} {path.name}",
            )
            by_name[path.name] = (item, path, frame, label, prediction)

        receipts = []
        for arm, family in (("A", "baselines"), ("B", "counterfactuals")):
            facts = rebound[family][cid]
            receipt_file, receipt, trace, rows = terminal.load_trace(case, arm)
            pin(receipt_file, facts["receipt_sha256"])
            pin(trace, facts["trace_sha256"])
            require(receipt["trace_sha256"] == facts["trace_sha256"], f"source trace seal: {arm} {cid}")
            receipts.append(receipt)
            if arm == "A" and cid == "dense-fit-01":
                cold = read(expand("{X}/inherited-A01-cold-review.json"))
                require(facts["failed_process_raw_reused"] and cold, "A01 inherited review is missing")
            command = receipt["applied_terminal_commands"][-1]
            original_command, = [
                c for c in original_commands if c["command_seq"] == registered["terminal_seq"][-1]
            ]
            require(
                command["accepted"] and original_command["accepted"] and command["target_open"]
                and original_command["target_open"] and command["episode_id"] != raw_receipt["episode_id"],
                f"original OPEN source not verified: {arm} {cid}",
            )
            for tick, name, offset in zip(registered["ticks"], registered["archive_A"], (240, 360, 480), strict=True):
                item, path, frame, label, prediction = by_name[name]
                row = rows[tick]
                require(
                    tick == registered["open_tick"] + offset == row["tick"] == item["robot"]["physics_step"]
                    and item["phase"] == "DWELL" and item["dwell_tick"] == offset - 240
                    and row["time_s"] == frame.sim_time_s
                    and row["open_command"] is True, f"wrong release boundary: {arm} {cid} {tick}",
                )
                source = {
                    "arm": arm, "case": cid, "source_tick": tick, "offset": offset,
                    "source_time_s": row["time_s"], "source_trace_sha256": facts["trace_sha256"],
                    "source_receipt_sha256": facts["receipt_sha256"],
                    "source_replay_episode": command["episode_id"],
                    "historical_fit_episode": raw_receipt["episode_id"],
                    "historical_A_frame": frame.frame_id,
                    "source_open": command,
                }
                key = slot_key(arm, cid, tick)
                slots[key] = {
                    "source": source, "row": row, "size": receipt["half_extents_m"],
                    "reset": read(folder / "native-resets.json")[0]["parameters"]["requested"],
                    "archive_A": path, "archive_encoder": item["robot"],
                    "archive_label": label, "archive_prediction": prediction,
                }
                if arm == "A":
                    require(
                        np.linalg.norm(np.asarray(row["geom"]["object_geom"][0]) - label["center_m"]) <= 1e-9
                        and np.linalg.norm(np.asarray(row["geom"]["object_geom"][1]) - label["rotation"]) <= 1e-9,
                        f"A object pose differs from original exposure: {key}",
                    )
        require(
            receipts[0]["precommand_state"] == receipts[1]["precommand_state"]
            and receipts[0]["precommand_state"] == rebound["baselines"][cid]["precommand_state"]
            and receipts[1]["precommand_state"] == rebound["counterfactuals"][cid]["precommand_state"],
            f"{cid}: pair did not share pre-OPEN physical and controller state",
        )

    require(list(sorted(slots)) == ordered_keys("A") + ordered_keys("B"), "registered 18 slots miscounted")
    return manifest, slots, cal


def sha_data(raw):
    return hashlib.sha256(raw).hexdigest()


def checked_json(path, expected):
    data = path.read_bytes()
    require(sha_data(data) == expected, f"changed sealed file {path.name}")
    return json.loads(data)
