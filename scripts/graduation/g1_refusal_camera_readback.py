"""Read the sealed stationary camera log and compare every packet to native calibration."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def require(condition):
    if not condition:
        raise ValueError("archived camera record, capture identity, calibration or clock mismatch")


def check_record(command, row, sequence, last):
    pre, after = row["before"], row["after_normal"]
    camera = {
        "position_m": [0.35, 0.0, 1.4],
        "quaternion_wxyz": [1.0, 0.0, 0.0, 0.0],
        "fovy_deg": 50.0,
        "world_body_id": 0,
        "mode": 0,
    }
    require(
        pre == last and after == row["after_hidden"] and pre["camera"] == after["camera"] == camera
    )
    require(
        pre["physics_step"] == after["physics_step"] == 0
        and pre["episode_id"] == after["episode_id"]
    )
    require(
        (pre["record_count"], pre["next_seq"], after["record_count"], after["next_seq"])
        == (sequence - 1, sequence, sequence, sequence + 1)
    )
    require(after["sim_time_s"] == row["expected_source_time_s"])
    expected = dict(
        type="camera_position",
        accepted=True,
        reason="development_camera_translation",
        after_emergency_stop=False,
        sim_time_s=pre["sim_time_s"],
        episode_id=pre["episode_id"],
        physics_step=0,
        command_seq=sequence,
        position_m=[0.35, 0, 1.4],
    )
    require(
        command == expected
        and type(command["accepted"]) is bool
        and type(command["after_emergency_stop"]) is bool
    )


def verify(plan_file, supplement, raw, output):
    p = pinned(plan_file, "85666eed1724a2c2280690de8ec55d35fe79b3d636982e35dd366d48e6534885")
    sub = pinned(supplement, "d46c9cb334281ed6ef1eb34dc457165f80511a6327c2cdfbff5e8c41b17395e4")
    for name, digest in p["input_sha256"].items():
        require(sha(ROOT / name) == digest)
    for name, digest in sub["input_sha256"].items():
        path = (
            raw.parent / "cross-capture-failed-source.py"
            if name == "scripts/graduation/g1_refusal_capture.py"
            else ROOT / name
        )
        require(sha(path) == digest)
    for name, h in sub["failed_inputs_relative_to_private"].items():
        require(sha(raw.parent / name) == h)
    decision = read(plan_file.parent / "refusal-decision.public.json")
    cap = pinned(raw / "capture-seal.json", decision["capture_seal_sha256"])
    seal = read(raw / "decision-seal.json")
    src = pinned(raw / "source-seal.json", seal["source_seal_sha256"])
    require(
        src["capture_sha256"] == decision["capture_seal_sha256"]
        and src["audit_plan_sha256"] == sha(supplement)
    )
    logged = pinned(raw / "camera-commands.json", src["camera_commands_sha256"])["mounts"]
    frames = pinned(raw / "pixels/index.json", cap["index_sha256"])["frames"]
    roles = pinned(raw / "roles.json", cap["roles_sha256"])["roles"]
    require(
        set(logged) == {"X", "Y"}
        and len(frames) == len(roles) == 88
        and set(frames) == {r["key"] for r in roles.values()}
    )
    mounts = {}
    for side, session in logged.items():
        boundaries = session["boundaries"]
        commands = session["records"]
        last = session["initial"]
        require(
            len(boundaries) == len(commands) == 16
            and last["record_count"] == 0
            and last["physics_step"] == 0
        )
        seen = 0
        for case in p["source_cases"]:
            alloc = pinned(
                ROOT / p["prior_private"] / "trials" / case["case"] / "allocation.json",
                case["allocation_sha256"],
            )
            camera = alloc["geometry"]["camera"]
            for i, (role, hist) in enumerate(
                [("previous", "previous_accepted_feedback"), ("refused", "rejected_feedback")]
            ):
                anchor = case["original_feedback"][hist]
                b = boundaries[seen]
                c = commands[seen]
                check_record(c, b, seen + 1, last)
                last = b["after_hidden"]
                seen += 1
                require(
                    (b["case"], b["time_role"], b["seed"], b["expected_source_time_s"])
                    == (case["case"], role, case["paired_noise_seeds"][i], anchor["sim_time_s"])
                )
                pair = []
                for mode in ("normal", "hand_hidden"):
                    r = roles[f"{case['case']}/{role}/{side}/{mode}"]
                    row = frames[r["key"]]
                    f = RGBDObservation.model_validate(
                        pinned(raw / "pixels" / row["file"], row["sha256"])
                    )
                    require(
                        r["source_state_sha256"] == anchor["source_state_canonical_sha256"]
                        and r["seed"] == b["seed"]
                        and (f.sim_time_s, f.frame_id, f.checksum_sha256)
                        == (b["expected_source_time_s"], r["frame_id"], r["checksum"])
                        and f.episode_id == r["episode"]
                        and r["mount_side"] == side
                        and r["condition"] == mode
                    )
                    observed = {k: getattr(f, k) for k in camera}
                    observed["camera_to_world"] = list(f.camera_to_world)
                    observed["intrinsics"] = list(f.intrinsics)
                    require(observed == camera)
                    pair.append(r)
                require(
                    pair[0]["state_sha256"] == pair[1]["state_sha256"]
                    and pair[0]["frame_id"] != pair[1]["frame_id"]
                )
        mounts[side] = dict(
            complete_commands=len(commands),
            calibration_verified_packets=2 * seen,
            actual_physics_steps=last["physics_step"],
            motion_dispatches=0,
            hidden_commands=0,
            pre_restore_camera_timestamps_verified=seen,
            post_restore_frame_timestamps_verified=2 * seen,
        )
    write(
        output,
        dict(
            schema="g1.first-refusal-camera-audit.readback.v1",
            supplement_plan_sha256=sha(supplement),
            parent_plan_sha256=sha(plan_file),
            failed_manifest_sha256=sha(raw.parent / "cross-capture-failure-manifest.json"),
            failed_files_rehashed=len(sub["failed_inputs_relative_to_private"]),
            parent_inputs_rehashed=len(p["input_sha256"]),
            supplement_inputs_rehashed=len(sub["input_sha256"]),
            capture_seal_sha256=sha(raw / "capture-seal.json"),
            camera_audit_sha256=src["camera_commands_sha256"],
            paired_decision_sha256=sha(plan_file.parent / "refusal-decision.public.json"),
            independent_verifier_sha256=sha(Path(__file__)),
            mounts=mounts,
            failed_packet_contribution=0,
            previous_capture=dict(
                actual_archived_packets=24,
                new_normal=16,
                new_hand_hidden=16,
                segmentations=32,
                sealed=False,
            ),
            verified_capture=dict(
                actual_archived_packets=24,
                new_normal=32,
                new_hand_hidden=32,
                segmentations=64,
                sealed=True,
            ),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for a in ("plan", "supplement", "raw", "output"):
        parser.add_argument(a, type=Path)
    args = parser.parse_args()
    verify(args.plan, args.supplement, args.raw, args.output)


if __name__ == "__main__":
    main()
