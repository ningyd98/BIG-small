"""Recalculate measured labels, then challenge the frozen labeler with derived corruptions."""

from __future__ import annotations

import argparse
import base64
import json
import math
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.research.protocol_evidence import _label
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def safe_path(states):
    allowed = [
        {"left_finger_geom", "object_geom"},
        {"right_finger_geom", "object_geom"},
        {"table", "object_geom"},
    ]
    allowed.extend({"table", f"dataset_distractor_{i}_geom"} for i in range(3))
    for row in states:
        tcp = row["tcp_position_m"]
        if (
            row["estop_engaged"]
            or any(set(pair) not in allowed for pair in row["contact_pairs"])
            or math.hypot(*tcp[:2]) > 0.85
            or not (0 <= tcp[2] <= 1.2)
            or any(abs(v) > 3 for v in row["joint_velocities_rad_s"])
            or any(d < -0.001 for _, _, d in row["self_collision_distances_m"])
            or any(
                not lo - 0.0001 <= p <= hi + 0.0001
                for p, (lo, hi) in zip(
                    row["joint_positions_rad"] + row["finger_positions_m"],
                    row["joint_ranges_rad"] + row["finger_ranges_m"],
                    strict=True,
                )
            )
        ):
            return False
    return True


def challenge(source, directory, assignment, rules):
    negative = {}
    for name in (
        "wrong_target",
        "wrong_submit_time",
        "missing_actuator",
        "wrong_rgb",
        "wrong_render_hash",
    ):
        dest = directory / name
        shutil.copytree(source, dest)
        if name == "wrong_rgb":
            target = dest / "rgb.png"
            with target.open("r+b") as f:
                f.write(b"salt")
        elif name == "missing_actuator":
            target = dest / "actuator-provenance.json"
            value = read(target)
            value["steps"].pop()
            target.write_text(json.dumps(value))
        else:
            target = dest / "capture.json"
            value = read(target)
            if name == "wrong_target":
                value["action_spec"]["target_position_m"][1] += 0.1
            elif name == "wrong_submit_time":
                value["submitted_at_s"] += 0.2
            else:
                value["pass_state_hashes"][0] = "0" * 64
            target.write_text(json.dumps(value))
        status, proof, _ = _label(dest, assignment, rules)
        require(
            status == "UNKNOWN" and proof["unknown_reason"], "corrupted data still received a label"
        )
        negative[name] = {
            "label": status,
            "reason": proof["unknown_reason"],
            "changed_file": target.name,
            "original_sha256": sha(source / target.name),
            "changed_sha256": sha(target),
        }
    return negative


def verify(raw, alloc_file, alloc_sha, result_file, result_sha, out):
    alloc = pinned(alloc_file, alloc_sha)
    result = pinned(result_file, result_sha)
    require(result["allocation_sha256"] == alloc_sha, "result allocation")
    results = []
    for case, row in zip(alloc["cases"], result["rows"], strict=True):
        c = case["id"]
        root = raw / c
        seal = read(root / "acquisition-seal.json")
        require(
            seal["case_id"] == c == row["id"] and seal["allocation_sha256"] == alloc_sha,
            "source identity",
        )
        source = root / "oracle"
        hashes = pinned(root / "oracle-seal.json", seal["oracle"])["files"]
        require(all(sha(source / n) == v for n, v in hashes.items()), "original oracle changed")
        states = read(source / "physical-observations.json")
        controls = read(source / "actuator-provenance.json")["steps"]
        capture = read(source / "capture.json")
        (action,) = read(source / "candidate-actions.json")
        commands = read(source / "commands.json")
        require(
            len(states) == len(controls) + 1 == row["physical_states"]
            and all(
                i == s["physics_step"] and s["episode_id"] == row["episode"]
                for i, s in enumerate(states)
            )
            and all(
                i == k["physics_step"] and k["sim_time_s"] == states[i - 1]["sim_time_s"]
                for i, k in enumerate(controls, 1)
            )
            and all(
                i == k["backend_record"]["command_seq"] and k["action_id"] == action["action_id"]
                for i, k in enumerate(commands, 1)
            ),
            "dense states, actuator and commands",
        )
        require(
            all(len(s["self_collision_distances_m"]) == 33 for s in states),
            "incomplete collision scope",
        )
        t = states[-1]["sim_time_s"] - capture["captured_at_s"]
        obs = RGBDObservation.model_validate(read(source / "observation.json"))
        mapping = [int(k) for k, v in capture["instance_labels"].items() if v == "object_geom"]
        require(len(mapping) == 1 and mapping[0] == capture["object_instance_id"], "instance map")
        mask = np.load(source / "instances.npy", allow_pickle=False) == mapping[0]
        depth = np.load(source / "depth.npy", allow_pickle=False)
        require(
            depth.tobytes() == base64.b64decode(obs.depth_float32_base64), "optical depth mismatch"
        )
        visible = int(mask.sum())
        frac = np.count_nonzero(mask & (depth > 0) & (depth < 10)) / visible if visible else 0
        ds = (
            states[action["start_step"]]["sim_time_s"]
            - states[capture["physics_step"]]["sim_time_s"]
        )
        residual = (
            np.asarray(states[-1]["tcp_position_m"]) - alloc["candidate"]["target_position_m"]
        )
        require(
            action["action_type"] == action["result"]["action_type"] == "MOVE_TCP"
            and action["result"]["success"]
            and np.array_equal(residual, row["terminal_tcp_minus_target_m"])
            and np.all(abs(residual) <= 0.005)
            and t <= 8
            and action["start_step"] == 120 + case["waiting_steps"]
            and ds == row["ages"]["sim_s"],
            "bounded terminal and original timestamp",
        )
        measured = (
            "UNKNOWN"
            if visible < 4 or frac < 0.5
            else ("VALID" if ds <= 0.25 and safe_path(states) else "INVALID")
        )
        require(
            measured == row["oracle"]
            and row["typed_execution"] == "VERIFIED"
            and all(v == capture["physics_state_hash"] for v in capture["pass_state_hashes"]),
            "raw scenario label differs",
        )
        start = datetime.fromisoformat(action["result"]["started_at"])
        measured_age = (start - obs.captured_at).total_seconds()
        require(
            measured_age >= row["ages"]["wall_s"] and abs(measured_age - row["ages"]["wall_s"]) < 1,
            "controller entry age inconsistent with recorded dispatch",
        )
        results.append(
            {
                "id": c,
                "matching_label": measured,
                "valid_depth_fraction": frac,
                "target_pixels": visible,
                "checked_collision_pairs": 33,
                "native_command_count": len(commands),
                "capture_to_controller_entry_utc_s": measured_age,
                "maximum_axis_error_m": float(np.max(np.abs(residual))),
            }
        )
    source = raw / alloc["cases"][0]["id"] / "oracle"
    control_dir = raw / "derived-corruptions"
    control_dir.mkdir()
    rules = read(
        ROOT
        / "artifacts/research/process/20261004-ced-development/t8-real-raw-development"
        / "verified-development/evidence-rules.json"
    )
    negative = challenge(source, control_dir, alloc["source_assignment"], rules)
    require(
        all(
            sha(source / n) == v
            for n, v in read(source.parent / "oracle-seal.json")["files"].items()
        ),
        "derived negative controls modified an original",
    )
    write(
        out,
        {
            "schema": "graduation.fixed-opportunity-verification.v1",
            "status": "PASS",
            "allocation_sha256": alloc_sha,
            "results_sha256": result_sha,
            "script_sha256": sha(Path(__file__)),
            "cases": results,
            "controls_from_first_registered_case": negative,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for n in ("raw", "allocation", "allocation_sha", "results", "results_sha", "output"):
        p.add_argument(n, type=str if n.endswith("_sha") else Path)
    a = p.parse_args()
    verify(a.raw, a.allocation, a.allocation_sha, a.results, a.results_sha, a.output)
