"""Verify archives and split optical prediction inputs from physical labels."""

import gzip
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
OUT = ROOT / PLAN["out"]
OPTICAL = OUT / "optical-input.json"
REFERENCE_XML = OUT / "reference-offscreen.xml"
PHYSICAL = OUT / "capture-input.json"
EGL_LOCK = ROOT / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock"
ASSET = ROOT / PLAN["asset"]
NEEDLE_ARCHIVE = ROOT / PLAN["needle_archive"]
SCALE = PLAN["scale"]
WIDTH, HEIGHT = SCALE * PLAN["original_width"], SCALE * PLAN["original_height"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pins():
    for relative, digest in PLAN["sha256"].items():
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT) and sha(path) == digest, f"changed input {relative}")


def seal(path, key):
    declared = read(path / "seal.json")[key]
    require(
        {p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()}
        == set(declared) | {"seal.json"},
        "archive file inventory differs",
    )
    for relative, digest in declared.items():
        item = (path / relative).resolve()
        require(item.is_relative_to(path) and sha(item) == digest, f"changed member {relative}")
    return declared


def optic_job(frame_id, checksum, time_s, robot, pose, pixels):
    rotation = np.asarray(pose["rotation"])
    require(
        frame_id == pose["frame_id"]
        and checksum == pose["checksum_sha256"]
        and rotation.shape == (3, 3)
        and np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-9, rtol=0)
        and abs(np.linalg.det(rotation) - 1.0) < 1e-9
        and np.array_equal(rotation, pose["rotation_object_to_world"])
        and np.asarray(pose["basis_error_object"]).shape == (3, 3)
        and np.asarray(pose["anchor_error_object_m"]).shape == (3,)
        and np.asarray(pose["anchor_object_m"]).shape == (3,)
        and np.asarray(pose["center_m"]).shape == (3,)
        and np.array_equal(pose["center_m"], pose["center_world_m"]),
        "unqualified current optical pose",
    )
    require(
        all(
            np.isfinite(np.ravel(pose[k])).all()
            for k in ("basis_error_object", "anchor_error_object_m", "anchor_object_m", "center_m")
        )
        and (np.asarray(pose["anchor_error_object_m"]) >= 0).all()
        and (np.asarray(pose["basis_error_object"]) >= 0).all()
        and np.isfinite(time_s)
        and robot["camera_encoder_sim_time_s"] == time_s,
        "unqualified local directional bound or exposure time",
    )
    joints, fingers = (
        robot["camera_joint_positions_rad"],
        robot["camera_finger_positions_m"],
    )
    require(
        len(joints) == 7 and len(fingers) == 2 and np.isfinite(joints + fingers).all(),
        "invalid exposure encoders",
    )
    return {
        "key": hashlib.sha256(f"{frame_id}/{checksum}".encode()).hexdigest()[:16],
        "frame_id": frame_id,
        "checksum_sha256": checksum,
        "time_s": time_s,
        "pixels_original_uv": pixels,
        "optical": pose,
        "joints_rad": joints,
        "fingers_m": fingers,
    }


def pair_jobs(folder, spec, camera):
    gate = read(folder / "clearance-gate.json")["checks"]
    index_path = folder / "rgbd-index.json"
    receipt = read(folder / "sensor-receipt.json")
    index = read(index_path)
    labels = read(folder / "offline-physics.json")["frame_labels"]
    previous, refusal = gate[-2:]
    require(
        receipt["id"] == spec["slot"]
        and receipt["index_sha256"] == sha(index_path)
        and receipt["registration_sha256"] == sha(folder.parent / "registration.json")
        and previous["step"] == spec["previous"]
        and previous["status"] == "CLEAR"
        and refusal["step"] == spec["stop"]
        and refusal["status"] == "BLOCKED"
        and refusal["reason"] == "unregistered_near_surface"
        and refusal["current"]["depth"]["unmatched_pixels_uv"] == spec["pixels"]
        and previous["current"]["depth"]["unmatched_pixels_uv"] == [],
        "original STOP/CLEAR pair does not bind",
    )
    mapped = []
    for g in (previous, refusal):
        (r,) = [r for r in index["rows"] if r["robot"]["frame_id"] == g["frame_id"]]
        (truth,) = [lab for lab in labels if lab["frame_id"] == g["frame_id"]]
        packet = r["robot"]
        path = (folder / r["file"]).resolve()
        require(path.parent == folder and sha(path) == r["file_sha256"], "wrong original packet")
        frame = RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))
        observation = g["current"]["payload_observation"]
        require(
            frame.frame_id == g["frame_id"] == packet["frame_id"] == truth["frame_id"]
            and frame.checksum_sha256
            == g["checksum_sha256"]
            == packet["checksum_sha256"]
            == truth["checksum_sha256"]
            and frame.episode_id == index["episode_id"] == receipt["episode_id"]
            and frame.scene_id == index["scene_id"] == receipt["scene_id"]
            and g["skill"] == r["skill"] == "LIFT"
            and g["phase"] == r["phase"] == "FEEDBACK"
            and g["step"] == packet["physics_step"] == truth["physics_step"]
            and frame.sim_time_s == packet["sim_time_s"]
            and abs(frame.sim_time_s - g["step"] / 240.0) < 1e-9
            and frame.model_dump(include=set(camera), mode="json") == camera
            and observation["relation"] == "held",
            "original phase, label, shutter or optical relation differs",
        )
        job = optic_job(
            frame.frame_id,
            frame.checksum_sha256,
            frame.sim_time_s,
            packet,
            observation["pose"],
            spec["pixels"],
        )
        mapped.append(
            (
                job,
                {
                    "key": job["key"],
                    "frame_id": frame.frame_id,
                    "checksum_sha256": frame.checksum_sha256,
                    "archive": spec["archive"],
                    "slot": spec["slot"],
                    "step": g["step"],
                    "original_status": g["status"],
                    "original_reason": g["reason"],
                    "time_s": frame.sim_time_s,
                    "joints_rad": job["joints_rad"],
                    "fingers_m": job["fingers_m"],
                    "world_object_center_m": truth["center_m"],
                    "world_object_rotation": truth["rotation"],
                    "frozen_archive_frame_sha256": r["file_sha256"],
                },
            )
        )
    return mapped


def needle_job(camera):
    optical = read(ROOT / PLAN["needle_optics"])
    frozen = optical["raw"]
    (row,) = [
        row
        for row in read(ROOT / PLAN["t02_clearance"])["rows"]
        if row["frame_id"] == frozen["frame_id"]
    ]
    dense = [
        rec
        for rec in read(NEEDLE_ARCHIVE / "index.json")["frames"]
        if (rec["step"], rec["scale"]) == (2112, SCALE)
    ]
    require(
        len(dense) == 2
        and row["physics_step"] == 2112
        and row["phase"] == "FEEDBACK"
        and row["reason"] == "unregistered_near_surface"
        and row["checksum_sha256"] == frozen["checksum_sha256"]
        and all(
            rec["original_frame_id"] == frozen["frame_id"]
            and rec["original_checksum_sha256"] == frozen["checksum_sha256"]
            and rec["camera_to_world"] == camera["camera_to_world"]
            and rec["source_time_s"] == row["sim_time_s"]
            for rec in dense
        ),
        "needle comparison is not bound to the same historical optical identity",
    )
    return optic_job(
        frozen["frame_id"],
        frozen["checksum_sha256"],
        row["sim_time_s"],
        row["robot"],
        optical["optical"],
        [[171, 122]],
    )


def buffered_xml():
    root = ET.parse(ASSET).getroot()
    visual = root.find("visual")
    if visual is None:
        visual = ET.SubElement(root, "visual")
    global_ = visual.find("global")
    if global_ is None:
        global_ = ET.SubElement(visual, "global")
    global_.set("offwidth", str(WIDTH))
    global_.set("offheight", str(HEIGHT))
    return ET.tostring(root, encoding="utf-8")


def run():
    pins()
    folders = {name: ROOT / relative for name, relative in PLAN["archives"].items()}
    for folder in folders.values():
        members = seal(folder, "sealed_sha256")
        require(
            read(folder / "seal.json")["registration_sha256"] == members["registration.json"],
            "archived source registration differs",
        )
    seal(NEEDLE_ARCHIVE, "members")
    camera = read(folders["original"] / "registration.json")["camera"]
    other = read(folders["slower"] / "registration.json")
    require(
        other["camera"] == camera
        and other["asset_sha256"]
        == read(folders["original"] / "registration.json")["asset_sha256"]
        == sha(ASSET)
        and (camera["width"], camera["height"])
        == (PLAN["original_width"], PLAN["original_height"]),
        "baseline optics or assembly differs",
    )
    jobs, physical = [], []
    for spec in PLAN["pairs"]:
        for optic, actual in pair_jobs(folders[spec["archive"]] / spec["slot"], spec, camera):
            jobs.append(optic)
            actual["seed"] = PLAN["noise_seed_offset"] + len(physical)
            physical.append(actual)
    needle = needle_job(camera)
    jobs.append(needle)
    require(
        len(jobs) == PLAN["max_reference_projections"]
        and len(physical) == PLAN["max_new_captures"]
        and len({j["key"] for j in jobs}) == len(jobs),
        "job/capture registration differs",
    )
    OUT.mkdir(exist_ok=False)
    with REFERENCE_XML.open("xb") as stream:
        stream.write(buffered_xml())
    write(
        OPTICAL,
        {
            "jobs": jobs,
            "camera": camera,
            "plan_sha256": sha(PLAN_PATH),
            "reference_xml_sha256": sha(REFERENCE_XML),
            "assembly_sha256": sha(ASSET),
        },
    )
    write(
        PHYSICAL,
        {
            "jobs": physical,
            "camera": camera,
            "plan_sha256": sha(PLAN_PATH),
            "optical_input_sha256": sha(OPTICAL),
            "needle_key": needle["key"],
        },
    )


if __name__ == "__main__":
    run()
