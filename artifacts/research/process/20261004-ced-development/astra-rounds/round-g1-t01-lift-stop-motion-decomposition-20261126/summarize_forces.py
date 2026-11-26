"""Cold read of the sealed paired force buffers."""

import argparse
import math
from pathlib import Path

from scripts.graduation.perception_io import pinned, read, sha, write
from stop_motion_decomposition import HERE, OUT, WINDOW, require


def peak(rows, name):
    magnitude, step, joint, signed = max(
        (abs(value), row.get("stop_tick", row["step"]), j + 1, value)
        for row in rows
        for j, value in enumerate(row[name] or [])
    )
    return {
        "magnitude_nm": magnitude,
        "step": step,
        "joint": joint,
        "signed_nm": signed,
    }


def summarize(trace):
    normal, stopped = trace["normal"], trace["stop"]
    require(
        [r["step"] for r in normal] == list(range(1632, 1849))
        and [r["stop_tick"] for r in stopped] == list(range(241)),
        "paired force-buffer roles differ",
    )
    anchor = normal[WINDOW["step"] - 1632]
    old_hold, new_hold = anchor["arm_ctrl"], stopped[0]["arm_ctrl"]
    return {
        "normal_balance_peak": peak(normal, "arm_cached_force_balance_error_nm"),
        "stop_balance_peak": peak(stopped, "arm_cached_force_balance_error_nm"),
        "normal_coupling_peak": peak(normal, "arm_other_dof_coupling_nm"),
        "normal_estimator_arm_inertia_difference_peak": peak(
            normal, "implemented_estimator_minus_cached_arm_inertia_nm"
        ),
        "estimator_arm_inertia_difference_at_stop_entry": peak(
            [anchor], "implemented_estimator_minus_cached_arm_inertia_nm"
        ),
        "joint_2_position_control_jump_rad": new_hold[1] - old_hold[1],
        "joint_2_recontact_constraint_nm": stopped[24]["arm_constraint_nm"][1],
        "joint_2_stop_entry_constraint_nm": anchor["arm_constraint_nm"][1],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    pair = OUT / "paired"
    seal = read(pair / "seal.json")
    buffers = pinned(pair / "buffers.json", seal["buffers_sha256"])
    require(
        buffers["source_sha256"] == sha(HERE / "read_stop_dynamics.py")
        and buffers["plan_sha256"] == sha(HERE / "plan.json")
        and buffers["cpu_integrations"] == 2544
        and buffers["new_captures"] == buffers["new_live_claims"] == 0,
        "wrong recovered original force bundle",
    )
    result = {k: summarize(v) for k, v in buffers["phases"].items()}
    for row in result.values():
        for key in ("normal_balance_peak", "stop_balance_peak"):
            require(math.isfinite(row[key]["magnitude_nm"]), "nonfinite native balance residual")
    write(
        OUT / f"{args.reader}-forces.json",
        {
            "source_sha256": sha(Path(__file__)),
            "paired_buffers_sha256": seal["buffers_sha256"],
            "result": result,
        },
    )


if __name__ == "__main__":
    main()
