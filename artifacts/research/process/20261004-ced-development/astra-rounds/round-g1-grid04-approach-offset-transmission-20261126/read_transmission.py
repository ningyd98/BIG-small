"""Read original paired APPROACH transmission and the one registered CPU comparison."""

import argparse
from pathlib import Path

import mujoco
import numpy as np
from compare_approach import HERE, PLAN, ROOT, read, require, sha, validate, write


def archived_pair():
    published = (
        HERE.parent
        / "round-g1-grasp-approach-selection-20261125/paired-selection-results.public.json"
    )
    require(
        sha(published) == PLAN["round_input_sha256"][published.relative_to(HERE.parent).as_posix()],
        "archived pair catalog changed",
    )
    study = read(published)
    catalog = study["sources_sha256"]
    archive = (
        ROOT / "experiments/results/g1-grasp-approach-selection-20261125/physical-selection-01"
    )
    placements, cases = [], []

    def series(case, identity):
        directory = archive / "courses" / case / identity
        result = directory / "result.json"
        require(
            sha(result) == catalog[result.relative_to(ROOT).as_posix()], "unpinned course result"
        )
        data = read(result)
        require(
            (data["case"], data["candidate"]["id"]) == (case, identity),
            "wrong archived course",
        )
        raw = directory / "series.npz"
        require(sha(raw) == data["series_sha256"], "unpinned course arrays")
        with np.load(raw, allow_pickle=False) as fields:
            steps = fields["step"]
            require(
                steps[0] == data["source_return_step"] and (np.diff(steps) == 1).all(),
                "not a contiguous approach course",
            )
            stage = fields["stage"]
            tcp, centre, obj, wrist = (
                fields["tcp"],
                fields["cube"],
                fields["rot"],
                fields["wrist"],
            )
            origin = [int(steps[0]), *fields["q"][0].tolist(), *fields["qvel"][0].tolist()]
            position = {}
            for command in data["actions"]:
                label = command["stage"]
                if label not in {"APPROACH", "GRASP"} or command["success"] is not True:
                    continue
                j = int(command["end"] - steps[0])
                require(int(steps[j]) == command["end"] and stage[j] == label, "wrong return row")
                position[label] = {
                    "step": int(steps[j]),
                    "measured_tcp_m": tcp[j].tolist(),
                    "object_in_wrist_m": (wrist[j].T @ (centre[j] - tcp[j])).tolist(),
                    "object_to_wrist_R": (wrist[j].T @ obj[j]).tolist(),
                    "bilateral_contact": bool((fields["contact_count"][j, :2] > 0).all()),
                }
            return data, origin, position

    for report in study["rows"]:
        case = report["placement"]
        placements.append(case)
        geometry_path = archive / "prefix" / case / "measured-input.json"
        require(
            sha(geometry_path) == catalog[geometry_path.relative_to(ROOT).as_posix()],
            "unpinned original grasp axes",
        )
        rotation = np.asarray(read(geometry_path)["rotation"]).reshape(3, 3)
        tangent = rotation[:, 1]
        for candidate in report["results"]:
            height, suffix = candidate.split("_t")
            if suffix == "+0":
                continue
            central = height + "_t+0"
            require(central in report["results"], "missing same-height paired centre")
            left, common, a = series(case, central)
            right, shifted, b = series(case, candidate)
            require(
                common == shifted
                and left["source_pixel_file_sha256"] == right["source_pixel_file_sha256"],
                "not one shared original MOVE_ABOVE state and pixel source",
            )
            change = np.subtract(right["actual_approach_target"], left["actual_approach_target"])
            require(
                np.linalg.norm(change - tangent * int(suffix) / 1000) <= 1e-10, "bad tangent axis"
            )
            actual = None
            if "APPROACH" in a and "APPROACH" in b:
                actual = float(
                    1000
                    * tangent
                    @ np.subtract(b["APPROACH"]["measured_tcp_m"], a["APPROACH"]["measured_tcp_m"])
                )
            cases.append(
                {
                    "case": case,
                    "A": central,
                    "B": candidate,
                    "command_tangent_mm": int(suffix),
                    "achieved_tangent_mm": actual,
                    "A_returns": a,
                    "B_returns": b,
                    "first_errors": [left["terminal_error"], right["terminal_error"]],
                }
            )
    require(len(placements) == len(set(placements)) == 12, "wrong original placement denominator")
    valid = [x for x in cases if x["achieved_tangent_mm"] is not None]
    return {
        "pairs": len(cases),
        "paired_approach_returns": len(valid),
        "same_direction_approach_returns": sum(
            x["command_tangent_mm"] * x["achieved_tangent_mm"] > 0 for x in valid
        ),
        "absolute_achieved_mm_range": [
            min(abs(x["achieved_tangent_mm"]) for x in valid),
            max(abs(x["achieved_tangent_mm"]) for x in valid),
        ],
        "placements": placements,
        "rows": cases,
    }


def independent_readback(root):
    receipt = read(root / "receipt.json")
    for name, expected in receipt["sha256"].items():
        require(sha(root / name) == expected, "unsealed CPU result")
    A, B = (read(root / name) for name in ("A.json", "B.json"))
    for arm in (A, B):
        start, stop = arm["start_step"], arm["end_step"]
        require(
            start == 872
            and [x["step"] for x in arm["states"]] == list(range(start, stop + 1))
            and [x["step"] for x in arm["applied"]] == list(range(start + 1, stop + 1)),
            "shifted or missing state/drive",
        )
        require(
            all(x["type"] in {"joint_target", "hold_current_joints"} for x in arm["commands"])
            and [x["command_seq"] for x in arm["commands"]]
            == list(range(153, 153 + len(arm["commands"]))),
            "inconsistent native command scope",
        )
    require(
        receipt["A_archive_checks_passed"]
        and A["success"]
        and A["end_step"] == 1280
        and A["states"][0] == B["states"][0]
        and receipt["raw_steps"] == A["end_step"] + B["end_step"] - 872
        and receipt["raw_steps"] <= PLAN["total_CPU_integration_limit"]
        and receipt["render_calls"] == 0,
        "wrong underived starting state or runtime",
    )
    require(
        np.allclose(
            np.subtract(B["target"], A["target"]), PLAN["B_offset_xyz_m"], atol=1e-14, rtol=0.0
        ),
        "wrong single candidate",
    )
    asset, _, _, frame, _, _ = validate()
    require(
        A["states"][-1]["tcp"] == frame["tcp_position_m"]
        and A["states"][-1]["q"][:7] == frame["joint_positions_rad"],
        "original A terminal measurements differ",
    )
    model = mujoco.MjModel.from_xml_path(str(asset))
    for arm in (A, B):
        data = mujoco.MjData(model)
        terminal = arm["states"][-1]
        data.qpos[:] = terminal["q"]
        data.qvel[:] = terminal["dq"]
        mujoco.mj_kinematics(model, data)
        require(
            np.linalg.norm(data.site("tcp").xpos - terminal["tcp"]) < 0.0001,
            "terminal position disagrees with independent joint FK",
        )

    def first_difference(key, value, point):
        for a, b in zip(A[key], B[key], strict=False):
            require(a[point] == b[point], "invalid common comparison clock")
            if a[value] != b[value]:
                return a[point]
        return None

    a, b = (x["states"][-1] for x in (A, B))
    common = next(s for s in B["states"] if s["step"] == min(a["step"], b["step"]))
    common_a = next(s for s in A["states"] if s["step"] == common["step"])
    angle = float(
        np.degrees(
            np.arccos(np.clip((np.trace(np.asarray(a["wrist"]).T @ b["wrist"]) - 1) / 2, -1, 1))
        )
    )
    return {
        "first_different_target_sequence": first_difference(
            "commands", "target_positions_rad", "command_seq"
        ),
        "first_different_target_tick": first_difference(
            "commands", "target_positions_rad", "physics_step"
        ),
        "first_different_drive_tick": first_difference("applied", "ctrl", "step"),
        "first_different_TCP_tick": first_difference("states", "tcp", "step"),
        "terminal_A_tick": A["end_step"],
        "terminal_B_tick": B["end_step"],
        "terminal_B_success": B["success"],
        "terminal_B_error": B["error_code"],
        "terminal_TCP_A_m": a["tcp"],
        "terminal_TCP_B_m": b["tcp"],
        "terminal_actual_difference_mm": (1000 * np.subtract(b["tcp"], a["tcp"])).tolist(),
        "last_shared_clock_tick": common["step"],
        "last_shared_clock_difference_mm": (
            1000 * np.subtract(common["tcp"], common_a["tcp"])
        ).tolist(),
        "terminal_tracking_residual_A_mm": (1000 * np.subtract(a["tcp"], A["target"])).tolist(),
        "terminal_tracking_residual_B_mm": (1000 * np.subtract(b["tcp"], B["target"])).tolist(),
        "terminal_wrist_angle_deg": angle,
        "terminal_fingers_A_m": a["fingers"],
        "terminal_fingers_B_m": b["fingers"],
        "complete_candidate_grasp_and_lift_status": "UNVERIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--raw", type=Path)
    args = parser.parse_args()
    answer = archived_pair() if args.raw is None else independent_readback(args.raw)
    write(args.output, answer)


if __name__ == "__main__":
    main()
