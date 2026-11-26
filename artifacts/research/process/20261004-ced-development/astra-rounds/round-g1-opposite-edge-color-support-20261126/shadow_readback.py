"""Two-process readback for one enrolled shadow candidate, with a separate label reader."""
import argparse
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import sys

import cv2
import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation.g1_complete_cv_handoff_optics import CALIBRATION
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.perception_io import sha
from shadow_edges import controls, pose_readback

HERE = Path(__file__).resolve().parent
ROOT = Path.cwd().resolve()
sys.path[:0] = [
    str(HERE.parent / "round-g1-continuous-payload-observation-20261125"),
    str(HERE.parent / "round-g1-release-camera-ab-20261126"),
]
from read_dense_payload import bind_fixture
from read_pose_coverage import native_marker, ratios


def read(path):
    return json.loads(path.read_bytes())


def pin(path, expected):
    path = path.resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or sha(path) != expected:
        raise ValueError(f"input SHA256 differs: {path}")
    return path


def write(path, data):
    with path.open("x") as output:
        json.dump(data, output, allow_nan=False, sort_keys=True, indent=2)
        output.write("\n")


PLAN = read(HERE / "plan.json")
CV = ROOT / PLAN["cv_root"]
AB = ROOT / PLAN["ab_root"]
OUT = ROOT / PLAN["exclusive_output"]
VAL_REL = "payload-optics-01/payload-val-04"
T02_REL = "batches/train-full-04/cvfix-t02"
CAL_REL = "calibration-gpu-01"
GENER = PLAN["marker_generation"]
RUNTIME = CV / "builds" / GENER / "runtime-source"
ASSET = "35f50ef8d18a13828541226552678b8ac3fcff4d597794957332f65eb623e1b6"


def cv_pin(rel):
    return pin(CV / rel, PLAN["cv_sha256"][rel])


def ab_pin(rel):
    return pin(AB / rel, PLAN["ab_sha256"][rel])


def checked_packet(path, digest):
    blob = pin(path, digest).read_bytes()
    return RGBDObservation.model_validate_json(gzip.decompress(blob) if path.suffix == ".gz" else blob)


def bound(allocation_path, scene, episode):
    allocation = read(allocation_path)
    if allocation["case"]["scene_id"] != scene:
        raise ValueError("allocation scene differs from native reset")
    identity = bind_allocation(
        allocation_path.read_bytes(), allocation_sha256=sha(allocation_path),
        generation_sha256=GENER, calibration_sha256=PLAN["cv_sha256"][CAL_REL + "/manifest.json"],
        asset_sha256=ASSET, reset_scene_id=scene, reset_episode_id=episode,
    )
    geometry = allocation["geometry"]
    pin(ROOT / geometry["asset_path"], ASSET)
    return identity, geometry


def exposure_metadata():
    packets, bindings = {}, {}
    selectors = PLAN["t02_frames_sha256"]
    reset_path = cv_pin(T02_REL + "/instance/reset-observed.json")
    reset = read(reset_path)
    begin, end = reset
    scene = begin["parameters"]["requested"]["scenario_id"]
    episode = end["episode_id"]
    native_reset_ids(reset, scene, episode)
    bindings["t02"] = (cv_pin(T02_REL + "/allocation.json"), scene, episode)
    index_path = cv_pin(T02_REL + "/instance/pixel-index.json")
    for row in read(index_path)["frames"]:
        tick = str(row["physics_step"])
        if row["label"] == "LIFT/feedback" and tick in selectors:
            assert row["file_sha256"] == selectors[tick]
            add_packet(packets, "t02/" + tick, index_path.parent, row["file"], row, row["physics_step"], "t02")

    index_path = cv_pin(VAL_REL + "/index.json")
    index = read(index_path)
    allocation_path = cv_pin(VAL_REL + "/allocation.json")
    reset_path = cv_pin(VAL_REL + "/reset.json")
    reset = read(reset_path)
    assert index["reset_sha256"] == sha(reset_path)
    assert reset["allocation_sha256"] == index["allocation_sha256"] == sha(allocation_path)
    bindings["val04"] = (allocation_path, reset["scene_id"], reset["episode_id"])
    for row in index["rows"]:
        stamp = row["robot"]
        add_packet(packets, "val04/" + row["file"], index_path.parent, row["file"],
                   dict(stamp, file_sha256=row["file_sha256"]), stamp["physics_step"], "val04")

    static_sources = read(ab_pin("source-slots.json"))
    cap_seal = read(ab_pin("capture-seal.json"))
    reg_sha = PLAN["code_and_evidence_sha256"]["../round-g1-release-camera-ab-20261126/experiment-registration.json"]
    assert sha(pin(AB / "registration.json", reg_sha)) == cap_seal["registration_sha256"]
    for arm in ("A", "B"):
        index_path = ab_pin(f"{arm}/index.json")
        index = read(index_path)
        assert index["registration_sha256"] == cap_seal["registration_sha256"]
        assert cap_seal["sealed_sha256"][f"{arm}/index.json"] == sha(index_path)
        for case, entry in index["cases"].items():
            key = f"{arm}/{case}"
            reset_path = pin(index_path.parent / case / "native-resets.json", entry["reset_sha256"])
            bindings[key] = (reset_path, case, entry["episode_id"])
        for key, row in index["rows"].items():
            stamp = row["robot"]
            source = static_sources[key]
            assert row["source_tick"] == source["source_tick"] == stamp["physics_step"]
            assert row["new_episode"] == bindings[key.rsplit("/", 1)[0]][2]
            add_packet(packets, key, index_path.parent, row["packet"], row, row["source_tick"],
                       key.rsplit("/", 1)[0], native_time=source["source_time_s"])
    assert Counter(k.split("/")[0] for k in packets) == {"t02": 4, "A": 9, "B": 9, "val04": 99}
    return packets, bindings


def add_packet(packets, key, directory, filename, row, tick, binding, native_time=None):
    path = (directory / filename).resolve()
    if key in packets or not path.is_relative_to(directory.resolve()):
        raise ValueError("duplicate or escaping packet")
    packets[key] = {
        "path": path.relative_to(ROOT).as_posix(), "sha256": row["file_sha256"], "step": tick,
        "frame_id": row["frame_id"], "checksum": row["checksum_sha256"],
        "binding": binding, "source_time_s": native_time,
    }


def seal_registration():
    for name, expected in PLAN["code_and_evidence_sha256"].items():
        pin((HERE if name.startswith("../") else ROOT) / name, expected)
    for item in ("input-manifest.json", "source-slots.json", "capture-seal.json"):
        ab_pin(item)
    packets, _ = exposure_metadata()
    for entry in packets.values():
        pin(ROOT / entry["path"], entry["sha256"])
    assert controls()
    OUT.mkdir(parents=True, exist_ok=False)
    write(OUT / "registration.json", {
        "plan_sha256": sha(HERE / "plan.json"), "plan_doc_sha256": sha(HERE / "plan.md"),
        "reader_sha256": sha(Path(__file__)), "shadow_module_sha256": sha(HERE / "shadow_edges.py"),
        "packets": packets, "controls_passed": True, "numpy_version": np.__version__, "cv2_version": cv2.__version__,
    })


def registration(expected):
    data = read(pin(OUT / "registration.json", expected))
    assert data["reader_sha256"] == sha(Path(__file__))
    assert data["shadow_module_sha256"] == sha(HERE / "shadow_edges.py")
    assert data["plan_sha256"] == sha(HERE / "plan.json")
    return data


def predict(expected, destination):
    reg = registration(expected)
    packets, bindings = exposure_metadata()
    assert reg["packets"] == packets
    cal_path = cv_pin(CAL_REL + "/manifest.json")
    table_path = cv_pin(CAL_REL + "/table.npy")
    allocation_files = {entry[0].resolve() for entry in bindings.values()}
    allow = allocation_files | {ROOT / entry["path"] for entry in packets.values()} | {
        CV / "batches/train-full-04/allocation.json", CV / T02_REL / "allocation.json",
        RUNTIME / "runtime-build.json", RUNTIME / "scripts/graduation/g1_visibility_vision.py",
        cal_path, table_path, destination.resolve(),
    }
    private = ROOT / "experiments/results"

    def deny_labels(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(private) and path not in allow:
                raise PermissionError("read outside registered input scope")

    sys.addaudithook(deny_labels)
    try:
        (CV / VAL_REL / "offline-labels.json").open("rb").close()
    except PermissionError:
        pass
    else:
        raise ValueError("prediction label isolation failed")
    data = read(cal_path)
    assert data["maps"]["table"]["depth_sha256"] == sha(table_path)
    table = np.load(table_path, allow_pickle=False)
    camera = data["primary_camera"]
    assert table.shape == (camera["height"], camera["width"])
    cv2.setNumThreads(1)
    detector, marker_sha = native_marker(GENER)
    assert marker_sha == PLAN["marker_sha256"]
    bound_identities = {}
    for key, (path, scene, episode) in bindings.items():
        if key in ("t02", "val04"):
            bound_identities[key] = bound(path, scene, episode)
        else:
            bound_identities[key] = bind_fixture(path.parent, {"id": scene, "episode_id": episode})
    rows = {}
    for key, entry in packets.items():
        frame = checked_packet(ROOT / entry["path"], entry["sha256"])
        identity, geometry = bound_identities[entry["binding"]]
        marker = detector(frame, geometry)
        step = entry["step"]
        assert frame.frame_id == entry["frame_id"] and frame.checksum_sha256 == entry["checksum"]
        assert frame.model_dump(mode="json", include=set(camera)) == camera
        assert identity.matches(frame, marker, geometry, step)
        if entry["source_time_s"] is not None:
            assert frame.sim_time_s == entry["source_time_s"]
        old, candidate, edges, status = pose_readback(
            frame, marker, geometry, identity, step, table, negative=(key == "t02/2112"),
        )
        rows[key] = dict(frame_id=frame.frame_id, checksum=frame.checksum_sha256, step=step,
                         old_pose=old, shadow_pose=candidate, edges=edges, status=status)
    write(destination, {"input_registration_sha256": expected, "marker_sha256": marker_sha,
                        "label_access_denied": True, "rows": rows})


def score(expected, pred_sha, destination):
    from release_camera_ab_inputs import verify_inputs

    reg = registration(expected)
    first = pin(OUT / "predictions-first.json", pred_sha)
    second = pin(OUT / "predictions-second.json", pred_sha)
    assert first.read_bytes() == second.read_bytes()
    prediction = read(first)
    assert prediction["input_registration_sha256"] == expected and prediction["label_access_denied"]
    assert prediction["rows"].keys() == reg["packets"].keys()

    val = read(cv_pin(VAL_REL + "/offline-labels.json"))["physical"]
    t02 = read(cv_pin(T02_REL + "/instance/offline-truth.json"))["samples"]
    stop = pin(CV / T02_REL / "instance/local-clearance.json",
               "bd1431c399239e3867659965b62b913177d7497559cff173f37e8b1eaecf8559")
    unknown, = [row for row in read(stop)["rows"] if row["physics_step"] == 2112]
    assert unknown["reason"] == "unregistered_near_surface" and unknown["status"] == "BLOCKED"
    _, ab, _ = verify_inputs()
    assert set(ab) == {key for key in reg["packets"] if key.startswith(("A/", "B/"))}

    labels = {f"val04/{row['file']}": row for row in val}
    for row in t02:
        key = f"t02/{row['physics_step']}"
        if key in reg["packets"]:
            labels[key] = dict(
                center_m=row["object_geom_position_m"],
                rotation=np.asarray(row["object_geom_rotation_row_major"]).reshape(3, 3).tolist(),
            )
    for key, source in ab.items():
        center, rotation = source["row"]["geom"]["object_geom"]
        labels[key] = dict(center_m=center, rotation=rotation)

    rows, counts = {}, {}
    for key, record in prediction["rows"].items():
        entry = reg["packets"][key]
        assert [entry["frame_id"], entry["checksum"], entry["step"]] == [
            record["frame_id"], record["checksum"], record["step"],
        ]
        domain = counts.setdefault(key.split("/")[0], Counter())
        domain["frames"] += 1
        old = record["old_pose"]
        candidate = record["shadow_pose"]
        if old:
            assert candidate is None
            domain["original_qualified"] += 1
        if candidate:
            domain["shadow_candidates"] += 1
            profile = CALIBRATION[candidate["method"]]
            reference = dict(
                candidate, rotation=candidate["rotation_object_to_world"], center_m=candidate["center_world_m"],
                anchor_error_object_m=profile["anchor"], basis_error_object=profile["basis"],
            )
            numeric = ratios(reference, labels[key])
            numeric["within_old_box_and_corner_diagnostic"] = (
                numeric["current_valid_bounds"] and numeric["cube_corner_ratio"] <= 1
            )
            if not numeric["within_old_box_and_corner_diagnostic"]:
                domain["candidate_outside_old_diagnostic_bounds"] += 1
        else:
            numeric = None
        if key.startswith("t02/") or candidate or record["edges"]:
            rows[key] = {
                "status": record["status"], "edges": record["edges"],
                "original_method": old["method"] if old else None,
                "shadow_method": candidate["method"] if candidate else None, "old_bounds_diagnostic": numeric,
            }
    assert rows["t02/2112"]["status"] == "excluded_unknown_near"
    write(destination, dict(
        input_registration_sha256=expected, predictions_sha256=pred_sha, counts=counts,
        rows=rows, t02_later_original_stop=unknown["reason"], registered_pose_changed=False,
        new_authority=False, prior_disclosed_val04_single_marker_undercoverage=19,
        new_runs=PLAN["permissions"],
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("register", "predict", "score"))
    parser.add_argument("registration_sha256", nargs="?")
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.mode == "register":
        seal_registration()
    elif args.mode == "predict":
        assert args.argument in ("first", "second")
        predict(args.registration_sha256, OUT / f"predictions-{args.argument}.json")
    else:
        score(args.registration_sha256, args.argument, OUT / "offline-score.json")
