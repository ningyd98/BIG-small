"""Cold-read actual native PRE images and continuous drive states at two archived training cases."""

import argparse
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_clearance import LocalClearance
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.g1_visibility_vision import measure_frame
from scripts.graduation.perception_io import pinned, read, sha

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def cold_replay(repo):
    full = repo / "experiments/results/g1-complete-cv-repair-20261125"
    physical = repo / "experiments/results/g1-skill-handoff-20261125/physical-capture-01"
    batch = full / "batches/train-full-02"
    spec = read(batch / "allocation.json")
    rows = []
    for slot in spec["cases"]:
        cid = slot["id"]
        case = batch / cid
        config = pinned(case / "allocation.json", slot["allocation_sha256"])
        geometry = config["geometry"]
        raw = case / "instance"
        local = pinned(
            raw / "local-clearance.json",
            read(raw / "local-clearance-seal.json")["local_clearance_sha256"],
        )
        index = {p["frame_id"]: p for p in read(raw / "pixel-index.json")["frames"]}
        trace = read(physical / cid.rsplit("-", 1)[1] / "handoffs.json")
        cal = LocalClearance(
            geometry,
            full
            / "builds"
            / spec["runtime_build_sha256"]
            / "runtime-source"
            / geometry["asset_path"],
            Path(spec["calibration_directory"]),
            calibration_sha256=spec["calibration_sha256"],
            isolated_scene=True,
        )
        try:
            for h in trace:
                step, skill = h["start_step"], h["incoming"]
                matches = [
                    r
                    for r in local["rows"]
                    if r["skill"] == skill and r["phase"] == "PRE" and r["physics_step"] == step
                ]
                if not matches:
                    continue
                (row,) = matches
                frame_row = index[row["frame_id"]]
                fn = raw / frame_row["file"]
                assert sha(fn) == frame_row["file_sha256"]
                frame = RGBDObservation.model_validate_json(fn.read_bytes())
                mr = row["robot"].copy()
                a = h["actual_active_commands"]
                # Match the complete native command prefix before reconstructing its entry.
                assert np.array_equal(a["q"][:7], mr["joint_positions_rad"])
                assert np.array_equal(a["qvel"][:7], mr["joint_velocities_rad_s"])
                assert np.array_equal(a["q"][7:9], mr["finger_positions_m"])
                assert np.array_equal(a["qvel"][7:9], mr["finger_velocities_m_s"])
                seq = a["last_accepted_native_arm_command"]["command_seq"]
                mr["handoff"] = dict(
                    source_skill=h["outgoing"],
                    destination_skill=skill,
                    prior_end_step=step,
                    entry_step=step,
                    current_step=step,
                    entry_command_seq=seq,
                    last_command_seq=seq,
                    entry_frame_id=frame.frame_id,
                    entry_checksum_sha256=frame.checksum_sha256,
                    entry_joint_positions_rad=a["q"][:7],
                    entry_joint_velocities_rad_s=a["qvel"][:7],
                    entry_finger_positions_m=a["q"][7:9],
                    entry_finger_velocities_m_s=a["qvel"][7:9],
                    entry_target_rad=a["ctrl"][:7],
                    entry_finger_target_m=a["ctrl"][7:9],
                    effective_joint_target_rad=a["ctrl"][:7],
                    effective_finger_target_m=a["ctrl"][7:9],
                    entry_effective_arm_goal_rad=a["command_q"],
                    entry_gripper_open=a["command_open"],
                    entry_native_arm_velocity_rad_s=a["native_sent_arm_velocity_rad_s"],
                )
                m = measure_frame(frame, geometry)
                current = cal.check(frame, m, mr, skill, row["target_xyz"], _DOWNWARD, phase="PRE")
                rows.append(
                    dict(
                        case=cid,
                        skill=skill,
                        step=step,
                        frame_id=frame.frame_id,
                        frame_sha256=frame_row["file_sha256"],
                        original=row["reason"],
                        status=current["status"],
                        reason=current["reason"],
                        motion=current.get("short_motion"),
                    )
                )
        finally:
            cal.close()
    return dict(mode="cold native frame and exact continuous command prefix", commands=0, rows=rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    write_once(a.out, cold_replay(a.repo.resolve()))
    print(sha(a.out))
