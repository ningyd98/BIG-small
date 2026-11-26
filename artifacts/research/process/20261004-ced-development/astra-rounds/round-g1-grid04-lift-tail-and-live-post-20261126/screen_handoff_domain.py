"""Check necessary frozen LIFT matching conditions without pixels or integration."""

import argparse
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
import qualify_tail as tail
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    GROUPS,
    SCALES,
    direction_compatible,
    state_features,
    target_compatible,
    tcp_directions,
)
from scripts.graduation.perception_io import read, sha, write

PLAN = read(Path(__file__).with_name("handoff-plan.json"))


def check(reader):
    for p, expected in PLAN["input_sha256"].items():
        tail.require(sha(tail.ROOT / p) == expected, f"handoff input differs: {p}")
    tail.checked_inputs()
    mid = tail.earlier.OUT / "native" / "normal.json"
    earlier_receipt = read(tail.earlier.OUT / "reader-1.json")
    tail.require(sha(mid) == earlier_receipt["normal_sha256"], "midcourse raw drift")
    first = read(mid)
    dest = tail.OUT / "native"
    status = read(dest / "result.json")
    motion = {row["tick"]: row for row in first}
    motion.update({int(k): row for k, row in read(dest / "motion.json").items()})
    held = {int(k): row for k, row in read(dest / "retained_hold.json").items()}
    bridge = tail.earlier.module(tail.earlier.source("original/screen_braking.py"))
    mechanical = MotionGeometry(Model(bridge.ASSET))
    _, gate = tail.earlier.prepare_profiles(mechanical)
    stage = gate.data["LIFT"]
    refs = stage["references"]
    rates, drives = stage["vectors"]
    start = motion[tail.ENTRY]
    pos = np.array([*start["tcp"][:2], tail.earlier.PLAN["original_unchanged_grounded_z_m"]])
    q = np.array(start["q"])
    entry_tcp = mechanical.poses(q[:7][None], q[7:9][None])[2][0]
    known = sum(GROUPS[:6])
    split_at = np.cumsum(GROUPS[:6])[:-1]

    def audit(item, phase):
        tick = item["tick"]
        joints, rate, drive = (np.array(item[k])[None, :] for k in ("q", "dq", "ctrl"))
        # Placeholder object terms have zero influence on all retained columns or directions.
        probe = state_features(mechanical, joints, rate, drive, np.zeros((1, 3)), np.eye(3)[None])
        measured = mechanical.poses(joints[:, :7], joints[:, 7:9])[2][0]
        tcp_rate, tcp_drive = tcp_directions(mechanical, probe)
        allowed_rate = direction_compatible(tcp_rate[0], rates, 0.0025)
        allowed_drive = direction_compatible(tcp_drive[0], drives, 0.00025)
        eligible = allowed_rate & allowed_drive
        scaled = abs(refs[:, :known] - probe[0, :known]) / SCALES[:known]
        parts = np.column_stack([s.max(axis=1) for s in np.split(scaled, split_at, axis=1)])
        distance = (parts**2).sum(axis=1)
        best = float(distance[eligible].min()) if eligible.any() else None
        compatible_target = target_compatible(
            "LIFT", pos, measured, entry_tcp, mechanical.model.region
        )
        speed = float(abs(rate[0, :7]).max())
        speed_limit = float(abs(refs[:, 7:14]).max()) + 0.002
        reasons = []
        if not compatible_target:
            reasons.append("command_outside_registered_payload_path")
        if speed > speed_limit:
            reasons.append("payload_speed_outside_qualified_range")
        if best is None:
            reasons.append("no_eligible_frozen_rate_and_drive_direction")
        elif best > 1:
            reasons.append("known_robot_groups_exhaust_training_domain")
        return {
            "tick": tick,
            "phase": phase,
            "reasons": reasons,
            "n_eligible": int(eligible.sum()),
            "n_eligible_rate": int(allowed_rate.sum()),
            "n_eligible_drive": int(allowed_drive.sum()),
            "min_known_squared_distance": best,
            "n_eligible_with_robot_groups": int((eligible & (distance <= 1)).sum()),
            "joint_speed_rad_s": speed,
            "tcp_rate_m_s": tcp_rate[0].tolist(),
            "tcp_drive_m": tcp_drive[0].tolist(),
        }

    schedule = [
        (motion[k], "motion")
        for k in range(
            PLAN["first_divergent_feedback"],
            status["last_motion_feedback_tick"] + 1,
            tail.V,
        )
    ]
    schedule.append((held[PLAN["handoff_tick"]], "hold_entry"))
    schedule.extend((held[k], "retained_hold") for k in status["hold_feedback_candidate_ticks"])
    rows = [audit(item, phase) for item, phase in schedule]
    failed = [item for item in rows if item["reasons"]]
    result = {
        "checks": rows,
        "windows": len(rows),
        "necessary_rejections": len(failed),
        "first_no_possible_match": failed[0] if failed else None,
        "handoff": next(row for row in rows if row["phase"] == "hold_entry"),
        "egl_gate": "CPU_NECESSARY_DOMAIN_REJECTED" if failed else "NECESSARY_DOMAIN_NOT_REFUTED",
        "report_sha256": {
            name: sha(dest / name) for name in ("motion.json", "retained_hold.json", "result.json")
        },
        "plan_sha256": sha(Path(__file__).with_name("handoff-plan.json")),
        "reader_sha256": sha(Path(__file__)),
        "cpu_integrations": 0,
        "exposures": 0,
        "online_admission": False,
    }
    write(tail.OUT / f"handoff-prefilter-{reader}.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    with patch.multiple(
        mujoco,
        mj_step=tail.earlier.deny,
        mj_step1=tail.earlier.deny,
        mj_step2=tail.earlier.deny,
        Renderer=tail.earlier.deny,
        mjr_render=tail.earlier.deny,
    ):
        check(args.reader)
