"""Cold optical prediction and physical readback of a sealed B03 experiment."""

# ruff: noqa: E402
import argparse
import gzip
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from native_dwell import (
    OUT,
    PLAN,
    ROOT,
    digest,
    encode,
    import_terminal,
    inputs,
    native,
    optics,
    read,
    require,
    sha,
    store_json,
)
from read_pose_coverage import ratios
from release_clearance_probe import frame_gate, hand_geometry, per_corner_intervals
from replay_exposure import PROOF, RECOVERY, checked_witness
from scripts.graduation import g1_complete_cv_payload_observation as observer
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose
from scripts.graduation.g1_complete_cv_optical_identity import bind_allocation
from scripts.graduation.g1_complete_worker import native_reset_ids

PRIVATE = ROOT / "experiments/results"
ALLOCATION = inputs.expand("{G}/batches/train-full-04/cvfix-t02/allocation.json")
PARENT_ALLOCATION = ALLOCATION.parents[1] / "allocation.json"


def check_window(catalog, pre, returned, opening):
    timing = [slot["robot"]["physics_step"] for slot in catalog]
    sealed_roles = ["PRE", *(f"DWELL-{n:02d}" for n in range(31))]
    require([slot["role"] for slot in catalog] == sealed_roles, "wrong exposure sequence")
    require(
        timing == [opening, *(opening + offset for offset in PLAN["dwell_offsets_after_open"])]
        and returned == opening + 240 == timing[1]
        and pre == opening
        and len({row["robot"]["frame_id"] for row in catalog}) == 32,
        "foreign, duplicate, missing, or mistimed exposure",
    )


def action_context(receipt, catalog):
    actions = receipt["actions"]
    require(receipt["complete"] and all(a["success"] for a in actions), "native action incomplete")
    place, release = actions[-2:]
    require((place["skill"], release["skill"]) == ("PLACE", "RELEASE"), "native returns missing")
    closed, opened = receipt["gripper"][-2:]
    require(
        closed["accepted"]
        and opened["accepted"]
        and closed["target_open"] is False
        and opened["target_open"] is True,
        "observed gripper state lacks real command",
    )
    check_window(catalog, place["return_step"], release["return_step"], opened["physics_step"])
    require(release["start_step"] == opened["physics_step"], "false release return")
    return place, release, closed, opened


def fixture(receipt):
    allocation = inputs.checked_json(
        ALLOCATION,
        next(
            row["allocation_sha256"]
            for row in read(PARENT_ALLOCATION)["cases"]
            if row["id"] == "cvfix-t02"
        ),
    )
    scene = "g1.continuous-payload/dense-fit-03"
    bound, episode = native_reset_ids(receipt["resets"], scene, receipt["episode"])
    allocation["case"]["scene_id"] = bound
    identity = bind_allocation(
        encode(allocation),
        allocation_sha256=digest(allocation),
        generation_sha256=allocation["runtime_build_sha256"],
        calibration_sha256=allocation["calibration_sha256"],
        asset_sha256=sha(native.ASSET),
        reset_scene_id=bound,
        reset_episode_id=episode,
    )
    return identity, allocation["geometry"]


def audit(allowed):
    def block(event, arguments):
        if event == "open" and isinstance(arguments[0], (str, bytes)):
            path = Path(os.fsdecode(arguments[0])).resolve()
            if path.is_relative_to(PRIVATE) and path not in allowed:
                raise PermissionError("outside frozen optical input allowlist")

    sys.addaudithook(block)
    for path in (OUT / "registration.json", OUT / "b0/physical.jsonl.gz", OUT / "b1/native.json"):
        try:
            path.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("physical label barrier failed")


def exposure_event(obs, slot, frame, expected_action, command, identity):
    robot = slot["robot"]
    (event,) = [e for e in obs["events"] if e.get("frame_id") == frame.frame_id]
    require(
        event["explicit_role"] == slot["role"]
        and event["phase"] == "END"
        and event["error"] is None
        and event["instance_count"] == 0
        and len(event["pass_state_hashes"]) == 2
        and event["pass_state_hashes"][0] == event["pass_state_hashes"][1]
        and event["episode_id"] == frame.episode_id == identity.episode_id
        and event["physics_step"] == robot["physics_step"]
        and event["sim_time_s"] == frame.sim_time_s
        and robot["previous_native_successful_skill"] == expected_action["skill"]
        and robot["previous_native_return_step"] == expected_action["return_step"]
        and robot["last_accepted_gripper_open"] == command["target_open"]
        and robot["last_accepted_gripper_command_step"] == command["physics_step"],
        "stale encoder, capture, or incorrect return join",
    )


def sequence_controls(observed, catalog):
    edits = (
        catalog[:-1],
        [catalog[0], catalog[1], catalog[1], *catalog[3:]],
        [catalog[0], catalog[2], catalog[1], *catalog[3:]],
    )
    result = [optics.rejected(action_context, observed, changed) for changed in edits]
    bad = json.loads(encode(observed))
    bad["actions"][-1]["return_step"] += 1
    result.append(optics.rejected(action_context, bad, catalog))
    require(all(result), "wrong cadence, frame duplication, or fake returns escaped")
    return result


def predict(output):
    folders = [OUT / "b0", OUT / "b1"]
    seal_path = OUT / "capture-seal.json"
    seal = read(seal_path)
    seal_sha = sha(seal_path)
    require(seal["complete"], "partial acquisition")
    catalogs = [
        inputs.checked_json(f / "frames.json", seal["members"][f"{f.name}/frames.json"])
        for f in folders
    ]
    audit(
        {
            output.resolve(),
            ALLOCATION,
            PARENT_ALLOCATION,
            inputs.expand("{D}/runtime-build.json"),
            inputs.expand("{D}/scripts/graduation/g1_visibility_vision.py"),
            native.ASSET,
            *(folder / "observable.json" for folder in folders),
            *(
                folder / item["path"]
                for folder, cat in zip(folders, catalogs, strict=True)
                for item in cat
            ),
        }
    )
    measure = optics.sealed_optics()
    visible = {}
    all_ids = set()
    for folder, catalog in zip(folders, catalogs, strict=True):
        observed = inputs.checked_json(
            folder / "observable.json", seal["members"][f"{folder.name}/observable.json"]
        )
        identity, geometry = fixture(observed)
        model = Model(ROOT / geometry["asset_path"])
        place, release, closed, open_command = action_context(observed, catalog)
        controls = sequence_controls(observed, catalog)
        history, predictions = {}, []
        for item in catalog:
            label = item["role"]
            pre = label == "PRE"
            file = folder / item["path"]
            require(
                sha(file) == item["sha256"] == seal["members"][f"{folder.name}/{item['path']}"],
                "sealed packet changed",
            )
            frame = inputs.packet(file)
            robot = item["robot"]
            exposure_event(
                observed,
                item,
                frame,
                place if pre else release,
                closed if pre else open_command,
                identity,
            )
            require(frame.frame_id not in all_ids, "duplicated exposure identity")
            all_ids.add(frame.frame_id)
            marker = measure(frame, geometry)
            step = robot["physics_step"]
            require(
                frame_gate(frame, marker, geometry, robot, identity), "wrong frame/encoder clock"
            )
            if pre:
                stale = robot | {"camera_encoder_sim_time_s": robot["sim_time_s"] - 1 / 240}
                require(
                    not frame_gate(frame, marker, geometry, stale, identity),
                    "stale encoder negative control failure",
                )
            pose = rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
            current = observer.payload_observation(
                frame,
                marker,
                geometry,
                robot,
                "RELEASE",
                "PRE" if pre else "DWELL",
                identity=identity,
                physics_step=step,
                optical=pose,
                history=history,
            )
            _, axes, planes, fingers = hand_geometry(model, robot)
            gaps, _, _ = (
                per_corner_intervals(pose, model, axes, planes) if pose else (None, None, None)
            )
            facts = current["evidence"]
            support = bool(facts.get("observed_support_and_rim"))
            allowed = optics.eligible(gaps, open_command, step, fingers, support) and not pre
            reasons = []
            if pose is None:
                reasons.append("no_current_independently_qualified_pose")
            if not support:
                reasons.append("current_support_or_rim_unproven")
            if not pre and (min(fingers) <= 0.035 or not optics.openness(open_command, step)):
                reasons.append("current_opening_unproven")
            if gaps is not None and float(np.min(gaps[:, 0])) <= 0.00025:
                reasons.append("strict_dual_clearance_unproven")
            predictions.append(
                {
                    "role": label,
                    "frame_id": frame.frame_id,
                    "tick": step,
                    "pose": pose,
                    "support": support,
                    "gap_m": gaps.tolist() if gaps is not None else None,
                    "counts": facts.get("stable_observation_count", 0),
                    "relation": current["relation"],
                    "eligible": allowed,
                    "reasons": reasons,
                    "ids": marker.get("usable_ids", []),
                }
            )
        visible[folder.name] = {
            "episode": identity.episode_id,
            "rows": predictions,
            "negative_controls": controls,
        }
    store_json(
        output,
        {
            "capture_seal_sha256": seal_sha,
            "predictor_sha256": sha(Path(__file__).resolve()),
            "routes": visible,
        },
    )


def reduction(prediction, output):
    seal = read(OUT / "capture-seal.json")
    require(
        seal["complete"] and all(sha(OUT / k) == v for k, v in seal["members"].items()),
        "capture sealed members differ",
    )
    registration = read(OUT / "registration.json")
    require(registration["formal_originals"] == inputs.originals(), "formal originals changed")
    optical = read(prediction)
    require(
        optical["capture_seal_sha256"] == sha(OUT / "capture-seal.json"), "prediction not bound"
    )
    terminal = import_terminal()
    recovery = read(RECOVERY)
    replay = read(PROOF)
    frozen_predictions = {
        value
        for filename, value in recovery["input_sha256"].items()
        if Path(filename).name in {"prediction.primary.json", "prediction.cold.json"}
    }
    require(
        replay["complete"]
        and replay["capture_sha256"] == sha(OUT / "capture-seal.json")
        and replay["plan_sha256"] == sha(RECOVERY)
        and replay["program_sha256"] == sha(Path(__file__).with_name("replay_exposure.py"))
        and sha(prediction) in frozen_predictions,
        "independent exposure replay does not join the frozen blind predictions",
    )
    native_limits = {
        "norm_of_xyz_peak_to_peak_lte_m": 0.004,
        "max_rotation_frobenius_distance_from_first_lte": 0.042,
        "bottom_peak_to_peak_lte_m": 0.003,
    }
    routes = {}
    timing_seed = None
    for name, code in zip(("B", "P"), ("b0", "b1"), strict=True):
        directory = OUT / code
        receipt = read(directory / "native.json")
        catalog = read(directory / "frames.json")
        observed = read(directory / "observable.json")
        place, release, _, opened = action_context(observed, catalog)
        starts = [slot["exposure_seed_state"] for slot in catalog]
        if timing_seed is None:
            timing_seed = starts
        require(starts == timing_seed, "different paired seed at same phase")
        with gzip.open(directory / "physical.jsonl.gz", "rt") as stream:
            rows = [json.loads(line) for line in stream]
        opening = opened["physics_step"]
        dwell = rows[opening + 240 : opening + 481]
        require(
            len(dwell) == 241
            and len(rows) == opening + 481
            and [r["tick"] for r in rows] == list(range(len(rows)))
            and receipt["condition"] == name
            and receipt["complete"],
            "wrong independent dense window",
        )
        sizes = receipt["geom_sizes"]
        physical = [terminal.gap_and_table(row, sizes) for row in dwell]
        require(
            not any(
                terminal.dwell_issues(row, clear, inside)
                for row, (clear, _, inside) in zip(dwell, physical, strict=True)
            ),
            "physical support or clearance failed",
        )
        obj = [row["geom"][terminal.OBJECT] for row in dwell]
        stable = terminal.stability(
            np.array([c for c, _ in obj]),
            np.array([r for _, r in obj]),
            np.array([b for _, b, _ in physical]),
            native_limits,
        )
        require(stable["inside_frozen_limits"], "dense physical stability outside frozen limits")
        predictions = optical["routes"][code]["rows"]
        joint = []
        witness = replay["routes"][code]
        require(
            witness["steps"] == recovery["routes"][code]
            and witness["new_rgbd"] == 0
            and len(witness["shots"]) == 32,
            "incomplete or out-of-budget independent replay",
        )
        exposure_events = {
            event["frame_id"]: event for event in observed["events"] if "frame_id" in event
        }
        for position, (preview, record, closure) in enumerate(
            zip(catalog, predictions, witness["shots"], strict=True)
        ):
            row = rows[record["tick"]]
            robot = preview["robot"]
            require(
                row["tick"] == robot["physics_step"]
                and row["time_s"] == robot["sim_time_s"]
                and record["frame_id"] == robot["frame_id"],
                "physical exposure join failed",
            )
            event = exposure_events[robot["frame_id"]]
            checked_witness(code, preview, event, closure)
            if not position:
                prior_hex = closure["encoder_f64_hex"]
                edited = prior_hex[:-1] + ("1" if prior_hex[-1] != "1" else "0")
                wrong = [
                    closure | {"route": "different_route"},
                    closure | {"tick": closure["tick"] - 1},
                    closure | {"encoder_f64_hex": edited},
                    closure | {"camera_state_sha256": "0" * 64},
                    witness["shots"][1],
                    {},
                ]
                require(
                    all(
                        optics.rejected(checked_witness, code, preview, event, item)
                        for item in wrong
                    ),
                    "replay witness negative control failed",
                )
            gaps = terminal.gap_and_table(row, sizes)[0]
            if record["pose"] is not None:
                center, rotation = row["geom"][terminal.OBJECT]
                bound = ratios(record["pose"], {"center_m": center, "rotation": rotation})
                require(bound["current_valid_bounds"], "optical pose missed physical bound")
                require(
                    optics.interval_covers(record["gap_m"], np.asarray(gaps)),
                    "dual gap intervals missed physical state",
                )
            joint.append(record | {"physical_gaps_mm": (np.asarray(gaps) * 1000).tolist()})
        dwell_result = joint[1:]
        count = sum(r["eligible"] for r in dwell_result)
        routes[name] = {
            "place_return_step": place["return_step"],
            "release_return_step": release["return_step"],
            "native_rgbd": receipt["statistics"]["returned"],
            "native_physics_steps": len(rows) - 1,
            "max_archived_native_numeric_delta": receipt["statistics"][
                "max_original_numeric_delta"
            ],
            "physical_dwell_steps": len(physical),
            "physical_stability": stable,
            "minimum_physical_gaps_mm": (
                np.array([g for g, _, _ in physical]).min(0) * 1000
            ).tolist(),
            "maximum_capture_ms": max(r["capture_ms"] for r in catalog),
            "eligible_dwell_frames": count,
            "optical_contiguous_and_physical_supported": count == 31
            and dwell_result[-1]["relation"] == "supported_and_separated",
            "pre": joint[0],
            "dwell": dwell_result,
        }
    store_json(
        output,
        {
            "schema": "g1.research.b03.dynamic-dwell.reduction.v1",
            "capture_sha256": sha(OUT / "capture-seal.json"),
            "prediction_sha256": sha(prediction),
            "exposure_replay_sha256": sha(PROOF),
            "routes": routes,
            "retreat": 0,
            "online": False,
            "formal_trials": 0,
        },
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("predict", "reduce"))
    p.add_argument("paths", type=Path, nargs="+")
    args = p.parse_args()
    cv2.setNumThreads(1)
    (predict if args.mode == "predict" else reduction)(*args.paths)


if __name__ == "__main__":
    main()
