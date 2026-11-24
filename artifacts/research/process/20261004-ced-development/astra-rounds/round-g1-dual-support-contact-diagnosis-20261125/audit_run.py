"""Read the original training capture, its two blind reads and its two independent scores."""

import argparse
from collections import Counter
from pathlib import Path

from scripts.graduation.perception_io import pinned, read, sha, write


def inspect(directory):
    raw = directory / "d02/instance"
    score = read(directory / "score.json")
    (case,) = score["cases"]
    allocation = pinned(directory / "allocation.json", score["allocation_sha256"])
    receipt = pinned(raw / "receipt.json", case["original_receipt_sha256"])
    claim = pinned(directory / "d02/attempt.json", receipt["claim_sha256"])
    assert (
        receipt["batch_sha256"] == claim["allocation_sha256"] == sha(directory / "allocation.json")
    )
    assert (
        claim["runtime_build_sha256"]
        == allocation["runtime_build_sha256"]
        == score["runtime_build_sha256"]
    )
    assert receipt["worker"]["sqlite_sha256"] == sha(raw / "development-worker.db")
    assert receipt["worker"]["released_at"] and receipt["worker"]["final_status"] == "FAILED"

    seal = pinned(raw / "acquisition-seal.json", case["capture_seal_sha256"])
    run = pinned(raw / "run.json", seal["run_sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])["samples"]
    frames = pinned(raw / "pixel-index.json", seal["index_sha256"])["frames"]
    online = pinned(raw / "online-vision.json", case["online_vision_sha256"])["frames"]
    commands = pinned(raw / "backend-commands.json", case["full_commands_sha256"])
    sources = Counter()
    first_contacts = {}
    for index, step in enumerate(truth):
        assert step["physics_step"] == index
        for pair in step["contact_pairs"]:
            name = " / ".join(pair)
            sources[name] += 1
            first_contacts.setdefault(name, index)
    assert first_contacts == {
        "table / object_geom": 0,
        "left_finger_geom / g1_dual_id7_crossbar": 1228,
    }
    assert sources["left_finger_geom / g1_dual_id7_crossbar"] == 3
    assert truth[-1]["gripper_open"] and truth[-2]["gripper_open"]
    assert run["stop"]["physics_step"] == 1228 and run["safe_stop"]["success"] is True
    assert [c["type"] for c in commands[-3:]] == [
        "hold_current_joints",
        "hold_current_joints",
        "emergency_stop",
    ]
    assert all(c["accepted"] and c["physics_step"] == 1228 for c in commands[-3:])
    assert commands[-4]["type"] == "joint_target" and commands[-4]["physics_step"] == 1226

    seals = score["blind_seals_sha256"]
    assert len(seals) == 2 and seals[0] == seals[1]
    blind_rows = None
    for suffix, digest in zip(("one", "two"), seals, strict=True):
        location = directory / f"scoring/blind-{suffix}"
        blind_index = pinned(location / "seal.json", digest)
        assert blind_index["n_frames"] == len(frames)
        ((key, packet_sha),) = blind_index["packets"].items()
        rows = pinned(location / (key + ".json"), packet_sha)
        if blind_rows is not None:
            assert rows == blind_rows
        blind_rows = rows
    scores = score["score_passes_sha256"]
    assert len(scores) == 2 and scores[0] == scores[1]
    for suffix, digest in zip(("one", "two"), scores, strict=True):
        assert pinned(directory / f"scoring/score-{suffix}.json", digest)["cases"] == [case]
    by_id = {entry["frame_id"]: entry for entry in blind_rows}
    total_bytes = 0
    feedback = []
    for frame in frames:
        path = raw / frame["file"]
        packet = pinned(path, frame["file_sha256"])
        total_bytes += path.stat().st_size
        source_id = packet["frame_id"]
        row = by_id[source_id]
        assert row["file_sha256"] == frame["file_sha256"]
        assert row["checksum_sha256"] == frame["checksum_sha256"] == packet["checksum_sha256"]
        assert row["usable_ids"] == [7, 8] and row["selected_id"] == 7
        if frame["label"] == "terminal":
            assert source_id not in online
            continue
        measurement = online[source_id]["measurement"]
        assert measurement["checksum"] == row["checksum_sha256"]
        assert (
            measurement["usable_ids"] == row["usable_ids"]
            and measurement["selected_id"] == row["selected_id"]
        )
        if frame["label"] == "APPROACH/feedback":
            feedback.append(
                dict(
                    step=frame["physics_step"],
                    packet=frame["file"],
                    sha256=frame["file_sha256"],
                    usable_ids=row["usable_ids"],
                )
            )
    assert len(by_id) == len(frames) == 147 and len(online) == 146
    assert [row["step"] for row in feedback[-8:]] == list(range(1168, 1225, 8))
    return dict(
        schema="g1.visibility.support-contact.original-run-read.v1",
        generation=score["runtime_build_sha256"],
        allocation_sha256=score["allocation_sha256"],
        claim_sha256=receipt["claim_sha256"],
        receipt_sha256=case["original_receipt_sha256"],
        database_sha256=receipt["worker"]["sqlite_sha256"],
        worker_final_status=receipt["worker"]["final_status"],
        status_sequence=receipt["worker"]["status_sequence"],
        lease_released=bool(receipt["worker"]["released_at"]),
        physics_samples=len(truth),
        contact_point_counts=sources,
        first_physics_step_by_pair=first_contacts,
        last_four_commands=[
            {key: c[key] for key in ("type", "physics_step", "command_seq", "accepted")}
            for c in commands[-4:]
        ],
        safe_stop=run["safe_stop"]["success"],
        rgbd_packets=len(frames),
        rgbd_bytes=total_bytes,
        actual_online_measurements=len(online),
        terminal_used_by_controller=False,
        last_eight_feedback=feedback[-8:],
        terminal_packet=frames[-1],
        dual_read_frames=len(by_id),
        pixel_seals_sha256=seals,
        score_passes_sha256=scores,
        independent_outcome=case["independent_physical_outcome"]["status"],
        measured_lift_m=case["independent_physical_outcome"]["measured_lift_m"],
        joint_success=case["joint_success"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    write(args.output, inspect(args.batch))
    print(sha(args.output))
