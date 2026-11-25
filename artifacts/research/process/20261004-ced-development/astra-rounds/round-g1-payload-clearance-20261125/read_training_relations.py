"""Measure the new optical relation on the previous two sealed native training traces."""

import argparse
from collections import Counter
from pathlib import Path

from scripts.graduation import dynamic_vision, dynamic_vision_score
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_cv_payload_observation import payload_observation
from scripts.graduation.g1_complete_trials import PRIVATE, write_once
from scripts.graduation.g1_complete_worker import native_reset_ids
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.perception_io import ROOT, pinned, read, sha


def one(case, batch, directory):
    address = directory / case["id"]
    raw = address / "instance"
    allocation = pinned(address / "allocation.json", case["allocation_sha256"])
    score = read(address / "independent-score.json")
    receipt = pinned(raw / "receipt.json", score["receipt_sha256"])
    seal = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    run = pinned(raw / "run.json", seal["run_sha256"])
    index = pinned(raw / "pixel-index.json", seal["index_sha256"])
    local = pinned(raw / "local-clearance.json", score["local_clearance_sha256"])
    commands = pinned(raw / "backend-commands.json", receipt["full_commands_sha256"])
    dense = pinned(raw / "offline-truth.json", seal["truth_sha256"])["samples"]
    g = allocation["geometry"]
    generation = batch["runtime_build_sha256"]
    build = ROOT / PRIVATE / "builds" / generation / "runtime-source"
    geometry_sha = sha(build / g["asset_path"])
    assert geometry_sha == sha(ROOT / g["asset_path"])
    scene, episode = native_reset_ids(
        pinned(raw / "reset-observed.json", receipt["reset_sha256"]),
        index["scene"],
        receipt["physical_reset"]["episode_id"],
    )
    identity = bind_allocation(
        (address / "allocation.json").read_bytes(),
        allocation_sha256=case["allocation_sha256"],
        generation_sha256=sha(build / "runtime-build.json"),
        calibration_sha256=sha(Path(allocation["calibration_directory"]) / "manifest.json"),
        asset_sha256=geometry_sha,
        reset_scene_id=scene,
        reset_episode_id=episode,
    )
    indexed = {s["frame_id"]: s for s in index["frames"]}
    rows = {(s["skill"], s["phase"], s["frame_id"]): s for s in local["rows"]}
    actions = {a["skill"]: a for a in run["actions"]}
    gripper = [a for a in commands if a["type"] == "gripper" and a["accepted"]]
    observations, history = [], {}
    for role in run["frame_roles"]:
        skill, _, phase = role["label"].partition("/")
        if (skill, phase) not in {
            ("GRASP", "PRE"),
            ("GRASP", "POST"),
            ("LIFT", "PRE"),
            ("LIFT", "feedback"),
        }:
            continue
        frame_id = role["frame_id"]
        # Native LIFT PRE retains the preceding GRASP POST exposure and measured state.
        key = (
            ("LIFT", "PRE", frame_id)
            if (skill, phase) == ("GRASP", "POST")
            else (skill, phase.upper(), frame_id)
        )
        original = rows[key]["robot"]
        step = original["physics_step"]
        assert all(
            original[k] == dense[step][k]
            for k in (
                "joint_positions_rad",
                "joint_velocities_rad_s",
                "finger_positions_m",
                "finger_velocities_m_s",
                "tcp_position_m",
                "sim_time_s",
            )
        )
        command = original["handoff"]["last_command_seq"]
        last = next((x for x in reversed(gripper) if x["command_seq"] <= command), {})
        previous = actions["APPROACH" if (skill, phase) == ("GRASP", "PRE") else "GRASP"]
        assert (
            previous["controller_result"]["success"] and previous["controller_return_step"] <= step
        )
        robot = dict(
            original,
            native_last_command_seq=command,
            last_accepted_gripper_open=last.get("target_open"),
            last_accepted_gripper_command_step=last.get("physics_step"),
            previous_native_successful_skill=previous["skill"],
            previous_native_return_step=previous["controller_return_step"],
            previous_native_terminal_step=None
            if (skill, phase) == ("GRASP", "POST")
            else previous["end_step"],
        )
        frame = dynamic_vision_score.frame_from_row(raw, indexed[frame_id], episode, scene, g)
        marker = measure_frame(frame, g)
        optical = rigid_pose(frame, marker, g, identity=identity, physics_step=step)
        relation = payload_observation(
            frame,
            marker,
            g,
            robot,
            skill,
            phase.upper(),
            identity=identity,
            physics_step=step,
            optical=optical,
            history=history,
        )
        observations.append(
            dict(
                label=role["label"],
                frame_id=frame_id,
                physics_step=step,
                checksum_sha256=frame.checksum_sha256,
                evidence=dynamic_vision.plain(relation),
            )
        )
    return dict(
        id=case["id"],
        receipt_sha256=score["receipt_sha256"],
        observations=observations,
        relation_counts=dict(Counter(o["evidence"]["relation"] for o in observations)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = ROOT / PRIVATE / "batches/train-full-04"
    a = pinned(
        root / "allocation.json", "d17477969ba8db8ffa0972eb14096130e3cf2550d62e45c3f2a307ea1c1f5fdf"
    )
    files = [
        Path(__file__),
        *[
            ROOT / "scripts/graduation" / name
            for name in (
                "g1_complete_cv_payload_observation.py",
                "g1_complete_cv_relation_profile.json",
                "g1_complete_cv_handoff_optics.py",
                "g1_complete_cv_optical_identity.py",
                "g1_visibility_vision.py",
            )
        ],
    ]
    sources = {f.relative_to(ROOT).as_posix(): sha(f) for f in files}
    results = [one(case, a, root) for case in a["cases"]]
    assert all(sha(ROOT / f) == v for f, v in sources.items()), (
        "reader sources changed during measurement"
    )
    write_once(
        args.output,
        dict(
            reader_sources_sha256=sources,
            sources="sealed train-full-04, no dispatch",
            results=results,
        ),
    )
    for result in results:
        print(result["id"], len(result["observations"]), result["relation_counts"])
