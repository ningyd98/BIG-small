"""Cold-read an isolated RGB-D attempt without simulation or rendering."""

import argparse
import gzip
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import capture_handoff_live as live
import cv2
import mujoco
from scripts.graduation.g1_complete_cv_handoff import binding_error
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

require = live.REQUIRE


def cold(reader, attempt):
    area = live.tail.OUT / attempt
    seal = read(area / "seal.json")
    declared = seal["sealed_sha256"]
    actual = {p.relative_to(area).as_posix() for p in area.rglob("*") if p.is_file()}
    require(actual == {*declared, "seal.json"}, "unregistered attempt artifacts")
    for name, pin in declared.items():
        raw = (area / name).resolve()
        require(
            raw.is_relative_to(area.resolve()) and sha(raw) == pin,
            f"changed capture member: {name}",
        )
    registration = read(area / "registration.json")
    case = area / live.CASE
    receipt = read(case / "sensor-receipt.json")
    gate = read(case / "clearance-gate.json")
    index = read(case / "rgbd-index.json")
    labels = read(case / "offline-physics.json")["frame_labels"]
    commands = read(case / "native-commands.json")
    reset = read(case / "native-resets.json")
    source = case / "optical-registration.json"
    allocation = read(source)
    geometry = allocation["geometry"]
    identity = bind_allocation(
        source.read_bytes(),
        allocation_sha256=sha(source),
        generation_sha256=allocation["runtime_build_sha256"],
        calibration_sha256=allocation["calibration_sha256"],
        asset_sha256=allocation["asset_sha256"],
        reset_scene_id=receipt["scene_id"],
        reset_episode_id=receipt["episode_id"],
    )
    marker_path = (
        live.HERE.parent / "round-g1-continuous-payload-observation-20261125/read_pose_coverage.py"
    )
    marker_src = live.tail.earlier.module(marker_path)
    detector, detector_hash = marker_src.native_marker(allocation["runtime_build_sha256"])
    cv2.setNumThreads(1)
    require(
        allocation["kind"] == "isolated_g1_skill_optical_registration"
        and registration["complete_owner"] is False
        and gate["owner_post"] is False,
        "isolated fixture gained an owner claim",
    )
    require(
        receipt["termination"] == seal["termination"] and receipt["native_emergency_stop"],
        "attempt missed original protection",
    )
    require(
        len(reset) == 2 and reset[0]["phase"] == "BEGIN" and reset[-1]["phase"] == "END",
        "actual reset count differs",
    )
    require(len(index["rows"]) == len(labels) == len(gate["checks"]), "unlinked acquisition")
    declared_slots = list(zip(index["rows"], labels, gate["checks"], strict=True))
    accepted_feedback, marked, frame_ids = [], [], set()
    verified = []
    for entry, label, row in declared_slots:
        robot = entry["robot"]
        raw = (case / entry["file"]).resolve()
        require(
            raw.is_relative_to(case.resolve()) and sha(raw) == entry["file_sha256"],
            "changed original RGB-D",
        )
        with gzip.open(raw, "rb") as file:
            image = RGBDObservation.model_validate_json(file.read())
        require(
            image.frame_id == robot["frame_id"] == label["frame_id"] == row["frame_id"]
            and image.checksum_sha256
            == robot["checksum_sha256"]
            == label["checksum_sha256"]
            == row["checksum_sha256"]
            and robot["physics_step"] == label["physics_step"] == row["step"]
            and image.sim_time_s == robot["sim_time_s"] == robot["camera_encoder_sim_time_s"]
            and image.frame_id not in frame_ids
            and image.model_dump(mode="json", include=set(geometry["camera"]))
            == geometry["camera"],
            "image, clock, calibration or native evidence order differs",
        )
        require(
            math.isclose(image.sim_time_s, row["step"] / 240, abs_tol=1e-8, rel_tol=0.0),
            "shutter physics clock changed",
        )
        frame_ids.add(image.frame_id)
        marker = detector(image, geometry)
        if marker.get("usable"):
            require(
                identity.matches(image, marker, geometry, row["step"]),
                "cold marker identity mismatch",
            )
        marked.append({"usable": bool(marker.get("usable")), "ids": marker.get("usable_ids", [])})
        status = row["current"].get("status")
        if row["phase"] != "POST":
            exposure = SimpleNamespace(
                frame_id=image.frame_id, checksum_sha256=image.checksum_sha256
            )
            require(
                binding_error(robot["handoff"], row["skill"], row["phase"], exposure) is None,
                "original handoff binding differs",
            )
        if row.get("released_to_boundary"):
            e = gate["native_feedback"][len(accepted_feedback)]
            require(
                row["phase"] == "FEEDBACK"
                and status == "CLEAR"
                and e["physics_step"] == row["step"]
                and e["sample_and_ik_s"] * 1000 == row["sample_ik_ms"] <= 100
                and row["before_next_boundary_ms"]
                == (row["next_boundary_ns"] - row["capture_begin_ns"]) / 1e6
                and row["before_next_boundary_ms"] <= 100
                and row["capture_begin_ns"] <= row["gate_finish_ns"] <= row["next_boundary_ns"],
                "feedback incorrectly released",
            )
            accepted_feedback.append(row)
        if row["phase"] == "POST" and row["skill"] == "LIFT":
            require(
                receipt["actions"][-1].get("success") is True, "LIFT POST before actual success"
            )
        verified.append(
            {
                "skill": row["skill"],
                "phase": row["phase"],
                "role": row["role"],
                "step": row["step"],
                "status": status,
                "relation": row["current"].get("relation"),
                "reason": row["current"].get("reason"),
                "unknown": row["current"].get("depth", {}).get("unknown_pixels"),
                "capture_through_gate_ms": (row["gate_finish_ns"] - row["capture_begin_ns"]) / 1e6,
                "clearance_gate_ms": row["current"].get("check_ms"),
                "boundary_ms": row.get("before_next_boundary_ms"),
            }
        )
    exposures = receipt["camera_calls"]
    for row in verified:
        require(any(e["step"] == row["step"] for e in exposures), "uncounted explicit exposure")
    require(
        len(exposures) <= registration["native_capture_hard_cap"]
        and receipt["physics_steps"] <= live.END
        and all(
            n <= registration["reference_projection_hard_caps"][k]
            for k, n in seal["reference_projection_calls"].items()
        ),
        "native run exceeded registration budget",
    )
    terminal = receipt["actions"][-1]
    late = [
        x["command_seq"]
        for x in commands
        if x.get("accepted")
        and x["type"] in {"joint_target", "gripper"}
        and x["command_seq"] > gate["checks"][-1]["native_last_command_seq"]
    ]
    if terminal["status"] == "STOPPED":
        require(
            not late and commands[-1]["type"] == "emergency_stop", "actuator continued after stop"
        )
    write(
        live.tail.OUT / f"{attempt}-{reader}.json",
        {
            "seal_sha256": sha(area / "seal.json"),
            "driver_sha256": registration["code_sha256"],
            "cold_reader_sha256": sha(Path(__file__)),
            "marker_sha256": detector_hash,
            "exposure_count": len(exposures),
            "framed_checks": len(verified),
            "marker_detections": marked,
            "checks": verified,
            "accepted_feedback_count": len(accepted_feedback),
            "original_handoff_relation_and_camera_verified": True,
            "physics_steps": receipt["physics_steps"],
            "terminal": terminal,
            "termination": receipt["termination"],
            "reference_projection_calls": seal["reference_projection_calls"],
            "after_last_frame_accepted_drive_commands": late,
            "native_emergency_stop": receipt["native_emergency_stop"],
            "real_skill_calls": sum(row["controller_called"] for row in receipt["actions"]),
            "new_integrations": 0,
            "new_exposures": 0,
            "formal": 0,
            "independent_formal": 0,
            "hardware": 0,
            "remote": 0,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("attempt", choices=("isolated-rgbd-01", "isolated-rgbd-02"))
    p.add_argument("reader", choices=("reader-1", "reader-2"))
    args = p.parse_args()
    with patch.multiple(
        mujoco,
        mj_step=live.tail.earlier.deny,
        Renderer=live.tail.earlier.deny,
        mjr_render=live.tail.earlier.deny,
    ):
        cold(args.reader, args.attempt)
