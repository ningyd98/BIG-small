"""Independently reconstruct the registered optical identity for every original training image."""

import argparse
from pathlib import Path

from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_trials import PRIVATE, read_sealed_score, write_once
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.perception_io import ROOT, pinned, read, sha

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def check_case(batch, case, capture):
    base = ROOT / PRIVATE
    address = base / "batches" / batch["label"] / case["id"]
    score = read_sealed_score(
        address / "independent-score.json", capture["independently_scored"]["score_sha256"]
    )
    raw = address / "instance"
    receipt = pinned(raw / "receipt.json", score["receipt_sha256"])
    allocation = pinned(address / "allocation.json", case["allocation_sha256"])
    scene, episode = native_reset_ids(
        pinned(raw / "reset-observed.json", receipt["reset_sha256"]),
        allocation["case"]["scene_id"],
        receipt["physical_reset"]["episode_id"],
    )
    g = allocation["geometry"]
    tree = base / "builds" / batch["runtime_build_sha256"] / "runtime-source"
    binding = bind_allocation(
        (address / "allocation.json").read_bytes(),
        allocation_sha256=case["allocation_sha256"],
        generation_sha256=sha(tree / "runtime-build.json"),
        calibration_sha256=sha(Path(allocation["calibration_directory"]) / "manifest.json"),
        asset_sha256=sha(tree / g["asset_path"]),
        reset_scene_id=scene,
        reset_episode_id=episode,
    )
    acq = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    index = pinned(raw / "pixel-index.json", acq["index_sha256"])
    local = pinned(raw / "local-clearance.json", score["local_clearance_sha256"])
    entries = {
        r["frame_id"]
        for r in local["rows"]
        if r["evidence"].get("short_motion", {}).get("plan") == "continuous_native_handoff"
        and r["status"] == "CLEAR"
    }
    verified = []
    frames = {}
    for source in index["frames"]:
        path = raw / source["file"]
        assert sha(path) == source["file_sha256"]
        frame = RGBDObservation.model_validate_json(path.read_bytes())
        assert (
            frame.frame_id == source["frame_id"]
            and frame.checksum_sha256 == source["checksum_sha256"]
        )
        marker = measure_frame(frame, g)
        assert binding.matches(frame, marker, g, source["physics_step"])
        assert frame.frame_id not in frames
        frames[frame.frame_id] = source["physics_step"]
        if frame.frame_id in entries:
            reading = rigid_pose(
                frame, marker, g, identity=binding, physics_step=source["physics_step"]
            )
            assert reading is not None
            verified.append(
                dict(frame_id=frame.frame_id, step=source["physics_step"], method=reading["method"])
            )
    assert set(r["frame_id"] for r in verified) == entries and entries
    return dict(
        case=case["id"],
        scene_id=scene,
        episode_id=episode,
        source_receipt_sha256=score["receipt_sha256"],
        checked_allocated_frames=len(frames),
        verified_3d_entries=verified,
        complete_native_stages=score["result"]["verified_posts"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("public_capture", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    summary = read(a.public_capture)
    batch = pinned(
        ROOT / PRIVATE / "batches" / summary["label"] / "allocation.json", summary["batch_sha256"]
    )
    result = [
        check_case(batch, case, capture)
        for case, capture in zip(batch["cases"], summary["cases"], strict=True)
    ]
    write_once(a.output, dict(capture_sha256=sha(a.public_capture), cases=result))
    print(sha(a.output))
