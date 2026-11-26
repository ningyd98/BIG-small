"""Blind release and endpoint handoff prediction, followed by physical closure."""

# ruff: noqa: E402
import argparse
import gzip
import json
import os
import sys
from copy import deepcopy
from functools import partial
from pathlib import Path

import numpy as np
import q_capture as route
from read_pose_coverage import ratios
from release_clearance_probe import frame_gate, hand_geometry, per_corner_intervals
from scripts.graduation import g1_complete_cv_payload_observation as observer
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose

require = route.require
read, sha, store = route.read, route.sha, route.store
HAND = route.handoff
OPT = route.dwell.optics
READER = route.reader
BLIND = route.BLIND
EXACT = route.minimal.exact


def minimal_scope(data):
    EXACT(data, "capture_seal_sha256 observable_reset actions gripper slots")
    reset = data["observable_reset"]
    EXACT(reset, "episode resets")
    require(len(reset["resets"]) == 2, "incomplete RESET identity")
    for event in reset["resets"]:
        EXACT(event, route.minimal.RESET_FIELDS)
        EXACT(event["parameters"], "requested")
        EXACT(event["parameters"]["requested"], "scenario_id")
        if event["phase"] == "BEGIN":
            require(event["result"] is None, "foreign BEGIN content")
        else:
            EXACT(event["result"], "physics_dt_s")
    route.minimal.native_reset_ids(reset["resets"], route.minimal.SCENE, reset["episode"])
    for action in data["actions"]:
        EXACT(action, "return_step skill start_step success")
        for value in action.values():
            route.minimal.values_only(value)
    for command in data["gripper"]:
        EXACT(command, route.minimal.COMMAND + " target_open")
        for value in command.values():
            route.minimal.values_only(value)
    for n, packet in enumerate(data["slots"]):
        EXACT(
            packet,
            "endpoint event exposure_seed_state integration_sha256 path robot role seed sha256",
        )
        require(packet["path"] == f"{n:02d}.json.gz", "unexpected packet path")
        EXACT(packet["robot"], route.minimal.ATTRIBUTES["robot"])
        for value in packet["robot"].values():
            route.minimal.values_only(value)
        EXACT(
            packet["event"],
            "episode_id error error_type explicit_role frame_id instance_count kind operation_id "
            "pass_state_hashes phase physics_step sim_time_s",
        )
        for value in packet["event"].values():
            route.minimal.values_only(value)
        if packet["role"] not in {"PRE", "DWELL-30"}:
            require(packet["endpoint"] is None, "foreign endpoint robot data")
            continue
        source = packet["endpoint"]
        EXACT(
            source,
            "arm_commands command_seq gripper_command physical_robot "
            "registered_actuation robot role",
        )
        require(
            source["role"] == packet["role"] and source["robot"] == packet["robot"],
            "endpoint lost its native frame",
        )
        for k in ("physical_robot", "registered_actuation"):
            EXACT(source[k], route.minimal.ATTRIBUTES[k])
            for value in source[k].values():
                route.minimal.values_only(value)
        for cmd in source["arm_commands"]:
            EXACT(cmd, route.minimal.COMMAND + " applied_target_positions_rad target_positions_rad")
            for value in cmd.values():
                route.minimal.values_only(value)
        EXACT(source["gripper_command"], route.minimal.COMMAND + " target_open")
        for value in source["gripper_command"].values():
            route.minimal.values_only(value)


def authorize_reads(output):
    paths = {
        BLIND / "blind-seal.json",
        BLIND / "input.json",
        *(BLIND / f"{n:02d}.json.gz" for n in range(32)),
        HAND.ALLOCATION,
        HAND.ALLOCATION.parents[1] / "allocation.json",
        HAND.ASSET,
        route.dwell.inputs.expand("{D}/runtime-build.json"),
        route.dwell.inputs.expand("{D}/scripts/graduation/g1_visibility_vision.py"),
        *(HAND.CALIBRATION / p for p in ("manifest.json", "panel-primary.npy", "panel-start.npy")),
        output.resolve(),
    }
    experiments = route.ROOT / "experiments"

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            file = Path(os.fsdecode(args[0])).resolve()
            if file.is_relative_to(experiments) and file not in paths:
                raise PermissionError("outside the original Q frame, camera, and encoder allowlist")

    sys.addaudithook(audit)
    for path in (
        route.SOURCE / "b1/frames.json",
        route.ACQUISITION / "q/native.json",
        route.ACQUISITION / "q/physical.jsonl.gz",
        route.ACQUISITION / "q/observable.json",
        route.PRIVATE / "exposure-witness.json",
    ):
        try:
            path.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("blind process accessed protected truth or historical answers")


def endpoint(frame, measured, item, pose, model, maps):
    source = item["endpoint"]
    require(source is not None, "lacks exact recorded endpoint state")
    label = "RELEASE" if item["role"] == "PRE" else "RETREAT"
    scope = HAND.scope_for_math(label, source, frame)
    metric = HAND.profile_matches(label, scope, pose, model)
    q, dq, f, df = [
        np.asarray(scope[f"entry_{key}"])
        for key in (
            "joint_positions_rad",
            "joint_velocities_rad_s",
            "finger_positions_m",
            "finger_velocities_m_s",
        )
    ]
    original = partial(
        HAND.handoff_motion,
        frame,
        measured,
        scope,
        label,
        "PRE",
        q,
        f,
        dq,
        df,
        None,
        None,
        model,
        optical=pose,
    )
    hint = measured.get("object_center_world_m")
    in_region = hint is not None and np.all(
        abs(np.asarray(hint)[:2] - model.region.c[:2]) <= model.region.h[:2]
    )
    strict = original(volume_check=HAND.volume_callback(model, maps, False))
    conditional = (
        original(volume_check=HAND.volume_callback(model, maps, True)) if in_region else None
    )
    require(
        original(optical=None, volume_check=HAND.volume_callback(model, maps, False))["reason"]
        == "no_current_handoff_pose_interval",
        "original missing-pose handoff negative failed",
    )
    require(
        pose is None
        or metric["matched_reference_indices"]
        or strict["reason"] == "outside_continuous_handoff_state_domain",
        "ranking disagrees with original handoff verdict",
    )
    return {
        "strict": strict,
        "conditional_floor": conditional,
        "domain": metric,
        "source_role": item["role"],
        "online_authorized": False,
    }


def prediction(output):
    authorize_reads(output)
    seal_path = BLIND / "blind-seal.json"
    seal = read(seal_path)
    require(seal["programs_sha256"] == route.programs(), "blind source program changed")
    route.verified_tree(BLIND, seal["members"])
    data = read(BLIND / "input.json")
    minimal_scope(data)
    contaminated = deepcopy(data)
    contaminated["observable_reset"]["resets"][1]["result"]["physics_state"] = {}
    require(OPT.rejected(minimal_scope, contaminated), "RESET truth leakage test failed")
    require(data["capture_seal_sha256"] == seal["acquisition_sha256"], "capture identity drift")
    catalog = data["slots"]
    receipt = {
        "complete": True,
        "actions": data["actions"],
        "gripper": data["gripper"],
        "events": [s["event"] for s in catalog],
    }
    place, release, closed, opened = READER.action_context(receipt, catalog)
    identity, geometry = READER.fixture(data["observable_reset"])
    measure = OPT.sealed_optics()
    model = HAND.Model(HAND.ASSET)
    maps = HAND.calibration_maps()
    delays = HAND.profile_controls()
    controls = READER.sequence_controls(receipt, catalog)
    require(
        not OPT.eligible(
            np.array([[0.00025, 0.001], [0.0003, 0.001]]),
            opened,
            release["return_step"],
            [0.039, 0.039],
            True,
        ),
        "equal clearance threshold was admitted",
    )
    history, results = {}, []
    for item in catalog:
        frame_file = BLIND / item["path"]
        require(sha(frame_file) == item["sha256"], "Q frame byte mismatch")
        is_pre = item["role"] == "PRE"
        robot = item["robot"]
        step = robot["physics_step"]
        frame = route.dwell.inputs.packet(frame_file)
        READER.exposure_event(
            receipt,
            item,
            frame,
            place if is_pre else release,
            closed if is_pre else opened,
            identity,
        )
        marker = measure(frame, geometry)
        require(frame_gate(frame, marker, geometry, robot, identity), "Q frame identity disagrees")
        pose = rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
        current = observer.payload_observation(
            frame,
            marker,
            geometry,
            robot,
            "RELEASE",
            "PRE" if is_pre else "DWELL",
            identity=identity,
            physics_step=step,
            optical=pose,
            history=history,
        )
        _, axes, planes, fingers = hand_geometry(model, robot)
        gaps, _, _ = per_corner_intervals(pose, model, axes, planes) if pose else (None, None, None)
        facts = current["evidence"]
        support = bool(facts.get("observed_support_and_rim"))
        eligible = not is_pre and OPT.eligible(gaps, opened, step, fingers, support)
        why = []
        if pose is None:
            why.append("missing_current_pose")
        if not support:
            why.append("missing_current_support")
        if not is_pre and (min(fingers) <= 0.035 or not OPT.openness(opened, step)):
            why.append("missing_current_open")
        if not is_pre and (gaps is None or float(np.min(gaps[:, 0])) <= 0.00025):
            why.append("strict_dual_clearance_unproven")
        results.append(
            {
                "frame_id": frame.frame_id,
                "tick": step,
                "source_role": item["role"],
                "gaps_m": gaps.tolist() if gaps is not None else None,
                "eligible": eligible,
                "reasons": why,
                "pose": pose,
                "support": support,
                "relation": current["relation"],
                "stable_observation_count": facts.get("stable_observation_count", 0),
                "handoff": None
                if item["endpoint"] is None
                else endpoint(frame, marker, item, pose, model, maps),
            }
        )
    store(
        output,
        {
            "source_blind_sha256": sha(seal_path),
            "delay_controls": delays,
            "sequence_controls": controls,
            "optical": results,
            "online_authorized": False,
        },
    )


def reduction(prediction_path, output):
    capture_hash = route.checked_capture()
    seal = read(BLIND / "blind-seal.json")
    route.verified_tree(BLIND, seal["members"])
    require(
        seal["acquisition_sha256"] == capture_hash and seal["programs_sha256"] == route.programs(),
        "blinded package not from registered Q",
    )
    report = read(prediction_path)
    paired = read(prediction_path.with_name("blind.cold.json"))
    require(
        report == paired and report["source_blind_sha256"] == sha(BLIND / "blind-seal.json"),
        "frozen independent blind predictions disagree",
    )
    proof_path = route.PRIVATE / "exposure-witness.json"
    proof = read(proof_path)
    require(
        proof["complete"]
        and sha(proof_path) == seal["witness_sha256"]
        and proof["source_capture_sha256"] == capture_hash
        and proof["route"]["new_rgbd"] == 0
        and len(proof["route"]["shots"]) == 32,
        "wrong independent exposure proof",
    )
    base = route.ACQUISITION / "q"
    receipt, observed = [read(base / name) for name in ("native.json", "observable.json")]
    catalog = read(base / "frames.json")
    place, release, _, opened = READER.action_context(observed, catalog)
    prior_catalog = read(route.SOURCE / "b1/frames.json")
    for actual, paired in zip(catalog, prior_catalog, strict=True):
        require(
            all(actual[key] == paired[key] for key in ("role", "seed", "exposure_seed_state")),
            "Q camera seed or relative phase changed compared with P",
        )
    terminal = route.dwell.import_terminal()
    sizes = receipt["geom_sizes"]
    opening = opened["physics_step"]
    with gzip.open(base / "physical.jsonl.gz", "rt") as stream:
        rows = [json.loads(line) for line in stream]
    steps = len(rows) - 1
    dense = rows[opening + 240 : opening + 481]
    require(
        steps == opening + 480 == proof["route"]["steps"]
        and len(dense) == 241
        and [row["tick"] for row in rows] == list(range(len(rows))),
        "wrong Q physical window",
    )
    physical = [terminal.gap_and_table(row, sizes) for row in dense]
    require(
        not any(
            terminal.dwell_issues(r, gaps, inside)
            for r, (gaps, _, inside) in zip(dense, physical, strict=True)
        ),
        "Q physical coverage, contacts or separation failed",
    )
    pos, rot = zip(*(row["geom"][terminal.OBJECT] for row in dense), strict=True)
    stable = terminal.stability(
        np.asarray(pos),
        np.asarray(rot),
        np.array([row[1] for row in physical]),
        {
            "norm_of_xyz_peak_to_peak_lte_m": 0.004,
            "max_rotation_frobenius_distance_from_first_lte": 0.042,
            "bottom_peak_to_peak_lte_m": 0.003,
        },
    )
    events = {event["frame_id"]: event for event in observed["events"] if "frame_id" in event}
    results = []
    for frame, prediction, witness in zip(
        catalog, report["optical"], proof["route"]["shots"], strict=True
    ):
        source = frame["robot"]
        route.replay.checked_witness("q", frame, events[source["frame_id"]], witness)
        broken = witness | {"camera_state_sha256": "0" * 64}
        require(
            OPT.rejected(
                route.replay.checked_witness, "q", frame, events[source["frame_id"]], broken
            ),
            "false double pass witness admitted",
        )
        row = rows[prediction["tick"]]
        require(
            row["tick"] == source["physics_step"]
            and row["time_s"] == source["sim_time_s"]
            and prediction["frame_id"] == source["frame_id"],
            "Q physical evidence not linked",
        )
        actual_gaps = terminal.gap_and_table(row, sizes)[0]
        pose = prediction["pose"]
        if pose:
            center, rotation = row["geom"][terminal.OBJECT]
            require(
                ratios(pose, {"center_m": center, "rotation": rotation})["current_valid_bounds"],
                "Q optical pose interval missed independent state",
            )
            require(
                OPT.interval_covers(prediction["gaps_m"], np.asarray(actual_gaps)),
                "Q dual optical gap interval missed physical state",
            )
        results.append(prediction | {"physical_gaps_mm": (np.asarray(actual_gaps) * 1000).tolist()})
    candidates = results[1:]
    count = sum(row["eligible"] for row in candidates)
    gate = (
        count == 31
        and candidates[-1]["relation"] == "supported_and_separated"
        and stable["inside_frozen_limits"]
    )
    retreat = candidates[-1]["handoff"]["strict"]
    final_stop = retreat.get("minimum_gap_m")
    store(
        output,
        {
            "capture_sha256": capture_hash,
            "prediction_sha256": sha(prediction_path),
            "exposure_witness_sha256": sha(proof_path),
            "target_xy_m": route.PLAN["goal_Q_xy_m"],
            "movement_steps": steps,
            "replay_steps": proof["route"]["steps"],
            "native_camera_calls": receipt["statistics"]["returned"],
            "open_tick": opening,
            "place_return_step": place["return_step"],
            "release_return_step": release["return_step"],
            "physical_dwell_states": len(dense),
            "physical_stability": stable,
            "optical_passing_dwell_frames": count,
            "continuous_joint_gate": gate,
            "minimum_clearance_mm": (np.array([g for g, _, _ in physical]).min(0) * 1000).tolist(),
            "max_capture_ms": max(slot["capture_ms"] for slot in catalog),
            "last_retreat_strict_margin_m": final_stop,
            "last_retreat_strict_pass": retreat["reason"] is None
            and final_stop is not None
            and final_stop > 0,
            "pre": results[0],
            "dwell": candidates,
            "retreat_dispatched": 0,
            "formal_trials": 0,
            "online_authorized": False,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("predict", "reduce"))
    parser.add_argument("paths", type=Path, nargs="+")
    args = parser.parse_args()
    route.cv2.setNumThreads(1)
    (prediction if args.mode == "predict" else reduction)(*args.paths)


if __name__ == "__main__":
    main()
