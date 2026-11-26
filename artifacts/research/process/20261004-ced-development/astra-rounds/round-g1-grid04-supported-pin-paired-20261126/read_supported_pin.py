"""Cold-read the sealed grid-04 prefix, archived optics and capture stop."""

import argparse
import base64
import copy
import os
from pathlib import Path

import cv2
import numpy as np
from pin_evidence import (
    HERE,
    ROOT,
    archived_frame,
    canonical,
    inputs,
    read,
    require,
    sha,
    source_module,
    verify_imports,
    verify_sources,
    write,
)
from pin_prefix import (
    ANCHORS,
    archived_samples,
    load_lines,
    prepare,
    same_reset,
    tick_index,
    validate_prefix,
)
from pin_preflight import no_camera_or_step, noise_check, prefix_files
from scripts.graduation.g1_complete_cv_clearance import LocalClearance, depth_changes
from supported_pin import cpu_environment, stamp

from cloud_edge_robot_arm.vision.observations import RGBDObservation

CAPTURE_STOP = "NOT_EXECUTED_RNG_PREFLIGHT_FAILED"


def input_seal(plan):
    output = ROOT / plan["private_output"]
    folder, _ = prefix_files(output)
    preflight = output / "preflight"
    receipt = read(preflight / "receipt.json")
    require(
        receipt["prefix_receipt_sha256"] == sha(folder / "receipt.json")
        and receipt["registration_sha256"] == sha(output / "registration.json"),
        "preflight lineage differs",
    )
    require(
        set(receipt["members_sha256"]) == {p.name for p in preflight.iterdir()} - {"receipt.json"},
        "unknown preflight evidence",
    )
    for name, digest in receipt["members_sha256"].items():
        require(sha(preflight / name) == digest, f"wrong preflight evidence byte hash: {name}")
    return {
        "members_sha256": {
            p.relative_to(output).as_posix(): sha(p)
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
        "round_sources_sha256": {p.name: sha(p) for p in sorted(HERE.glob("*.py"))},
        "formal_simulations": 0,
        "egl_sessions": 0,
        "new_rgbd": 0,
    }


def check_members(seal, output):
    for name, digest in seal["members_sha256"].items():
        member = (output / name).resolve()
        require(
            member.is_relative_to(output.resolve()) and member.is_file() and sha(member) == digest,
            f"sealed member SHA256 differs: {name}",
        )
    for name, digest in seal["round_sources_sha256"].items():
        require(sha(HERE / name) == digest, f"readback source drift: {name}")


def replay_archive(plan, folder, receipt, tools):
    source = validate_prefix(plan, tools)
    approach = tools["approach"]
    (endpoints, phases, commands, controls) = (
        load_lines(folder / f"{name}.jsonl")
        for name in ("endpoints", "phases", "commands", "actuator")
    )
    ticks = tick_index(endpoints, "step", 0, 1520)
    commands_index = tick_index(commands, "command_seq", 1, 236)
    drives = tick_index(controls, "step", 1, 1520)
    phase = tick_index(phases, "seq", 1, 236)
    resets = read(folder / "native-resets.json")
    same_reset(resets, read(source["case"] / "native-resets.json"))
    require(receipt["new_episode"] == resets[-1]["episode_id"], "prefix receipt episode differs")
    require(
        all(row["episode_id"] == receipt["new_episode"] for row in commands),
        "mixed new replay episode",
    )
    require(
        [approach.clean(row) for row in commands]
        == [approach.clean(row) for row in source["commands"]],
        "native command reissues differ",
    )
    for step, original in source["states"].items():
        require(
            {key: ticks[step][key] for key in original} == original,
            f"prefix archived step mismatch {step}",
        )
    for step, original in source["controls"].items():
        require(drives[step] == original, f"prefix archived drive mismatch at {step}")
    for seq, record in commands_index.items():
        before, after = phase[seq]["before"], phase[seq]["after"]
        require(
            before["step"] == after["step"] == record["physics_step"]
            and before["time_s"] == after["time_s"] == record["sim_time_s"]
            and before["last_command_seq"] == seq - 1
            and after["last_command_seq"] == seq
            and before["q"] == after["q"]
            and before["dq"] == after["dq"],
            f"wrong same-tick phase at command {seq}",
        )
        if record["type"] == "gripper":
            require(
                seq == 236
                and before["gripper_open"]
                and not after["gripper_open"]
                and before["ctrl"][7:9] == [0.039, 0.039]
                and after["ctrl"] == before["ctrl"][:7] + [0.0, 0.0]
                and before["phase_sha256"] != after["phase_sha256"],
                "archived immediate close did not write the two finger controls",
            )
        else:
            require(
                before["phase_sha256"] == after["phase_sha256"],
                f"arm target or HOLD wrote integration bytes at command {seq}",
            )
    require(
        phase[152]["after"] == phase[153]["before"] and phase[235]["after"] == phase[236]["before"],
        "HOLD and next command do not share the recorded intermediate phase",
    )
    for filename, (frame, robot, label) in source["samples"].items():
        row = phase[235]["after"] if filename == "0000.json.gz" else ticks[1520]
        geom = row["geometry"]["object_geom"]
        require(
            row["last_command_seq"] == robot["native_last_command_seq"]
            and row["time_s"] == frame.sim_time_s
            and row["q"][:9] == robot["joint_positions_rad"] + robot["finger_positions_m"]
            and row["dq"][:9] == robot["joint_velocities_rad_s"] + robot["finger_velocities_m_s"]
            and geom["center_m"] == label["center_m"]
            and geom["rotation"] == label["rotation"]
            and row["touching"] == sorted(sorted(pair) for pair in label["touching"]),
            f"frozen phase/exposure fields differ: {filename}",
        )
    require(
        phase[152]["after"]["phase_sha256"]
        == plan["prefix"]["compare_872_after_seq152"]["mujoco_integration_sha256"]
        and receipt["anchors"]["872"] == plan["prefix"]["compare_872_after_seq152"]
        and ticks[1520]["phase_sha256"]
        == plan["prefix"]["compare_1520_before_seq237_phase_sha256"],
        "sealed anchor digest differs from original",
    )
    missing = {
        step
        for a, b in plan["prefix"]["new_missing_intervals_inclusive"]
        for step in range(a, b + 1)
    }
    require(missing <= set(ticks) and len(missing) == 1110, "grid-04 endpoint gaps remain")
    require(
        receipt["counts"]["physics_steps"] == len(controls) == 1520
        and receipt["counts"]["endpoints"] == len(endpoints)
        and receipt["counts"]["command_reissues"] == len(commands)
        and receipt["counts"]["resets"] == 1
        and receipt["counts"]["render_or_capture_attempts"] == 0,
        "wrong prefix counters",
    )
    return {
        "covered_missing_endpoints": len(missing),
        "sealed_unique_endpoints": len(endpoints),
        "same_tick_native_command_phases": len(phases),
        "archive_a_exact_endpoints": len(source["states"]),
        "archive_a_exact_actuator_pulses": len(source["controls"]),
        "phase_872_after_152_sha256": phase[152]["after"]["phase_sha256"],
        "phase_1520_before_237_sha256": ticks[1520]["phase_sha256"],
        "counts": receipt["counts"],
    }, endpoints


def geometry_archive(plan, output):
    stored = read(output / "preflight/geometry.json")
    rows = load_lines(output / "preflight/distance-evaluations.jsonl")
    final = {row["tick"] for row in rows if row["representation"] == "final_q_fk"}
    cached = {row["tick"] for row in rows if row["representation"] == "native_cache"}
    require(final == set(range(2385)) and cached == set(range(1521)), "geometry journal coverage")
    tol = plan["pin"]["strict_separation_m_gt"]
    for field, ticks in (("final_q_fk", final), ("native_cache", cached)):
        values = [row for row in rows if row["representation"] == field]
        require(
            len({(row["tick"], row["entity"]) for row in values}) == len(values) == 9 * len(ticks)
            and all(row["sat_margin_m"] > tol for row in values),
            f"geometry journal contains a missing or unsafe endpoint: {field}",
        )
    stop = [
        row
        for row in rows
        if row["representation"] == "original_2384_hold" and row["sat_margin_m"] < -tol
    ]
    original = stored["original_hold_2384"]
    hit_ticks = sorted({row["tick"] for row in stop})
    require(
        len(hit_ticks) == original["overlap_count"] == 162
        and hit_ticks[0] == original["first_overlap"] == 79
        and original["preceding"]["tick"] == 78
        and original["preceding"]["sat_margin_m"] > tol
        and original["witness"]["slack_mm"] > tol * 1000.0,
        "archived HOLD signs differ",
    )
    require(
        sha(output / "preflight/diagnostic-pin.xml") == stored["scene"]["diagnostic_asset_sha256"],
        "wrong unexposed B asset",
    )
    return stored


def archived_optics(plan, tool):
    model, _, rows = tool.load()
    evidence = tool.adjudicate(model, rows)
    outputs = {}
    for shutter in plan["shutters"]:
        tick = shutter["tick"]
        packet = evidence["cases"][tick]
        layers = packet["replayed_original_surface_counts"]
        expected_pixels = [] if tick == 2376 else [[171, 123], [171, 124]]
        require(
            layers["nearer_returns"] == {2376: 2818, 2384: 2819}[tick]
            and layers["unmatched_pixels_uv"] == expected_pixels
            and layers["unknown_pixels"] == shutter["original_unknown_count"]
            and packet["original_status"] == shutter["original_gate"].split("/")[0],
            f"historical current surface gate changed at {tick}",
        )
        native = rows[tick].recorded["current"]
        outputs[str(tick)] = {
            "frame_id": rows[tick].frame.frame_id,
            "optical_pose": rows[tick].pose,
            "status": packet["original_status"],
            "reason": native.get("reason"),
            "layers": layers,
            "pixels": packet["pixels"],
        }
    return model, outputs, evidence["reference_seal_sha256"]


def rejected(call, symptom):
    try:
        call()
    except (KeyError, ValueError) as fault:
        require(symptom in str(fault), f"wrong negative-control failure: {fault}")
        return {"rejected": True, "detail": str(fault)}
    raise ValueError(f"negative control was accepted: {symptom}")


def controls(plan, seal, output, endpoints, optical_model):
    roots = plan["roots"]
    case = ROOT / roots["old"] / roots["case_under_old"]
    episode = plan["prefix"]["old_episode"]
    original_index = read(case / "rgbd-index.json")
    original_labels = read(case / "offline-physics.json")["frame_labels"]

    def negative_row(field, value, message):
        changed = copy.deepcopy(original_index)
        changed["rows"][0]["robot"][field] = value
        return rejected(
            lambda: archived_samples(case, ANCHORS, episode, index=changed),
            message,
        )

    def negative_label(field):
        changed = copy.deepcopy(original_labels)
        changed[0].pop(field)
        return rejected(lambda: archived_samples(case, ANCHORS, episode, labels=changed), field)

    (last,) = [row for row in original_index["rows"] if row["file"] == "0111.json.gz"]
    frame = archived_frame(case / last["file"])
    packet = frame.model_dump()
    rgb = base64.b64decode(frame.rgb_png_base64)
    depth = base64.b64decode(frame.depth_float32_base64)
    mask = base64.b64decode(frame.valid_mask_base64)
    require(
        (rgb, depth, mask)
        == (
            base64.b64decode(packet["rgb_png_base64"]),
            base64.b64decode(packet["depth_float32_base64"]),
            base64.b64decode(packet["valid_mask_base64"]),
        ),
        "self comparison altered a channel",
    )
    wrong_depth = np.frombuffer(depth, "<f4").reshape(240, 320).copy()
    wrong_depth[55, 56] = wrong_depth[56, 56]
    require(wrong_depth.tobytes() != depth, "wrong-row depth negative did not perturb bytes")
    tampered = base64.b64encode(wrong_depth.tobytes()).decode()
    frame_bad_sha = {**packet, "checksum_sha256": "1" * 64}
    frame_bad_depth = {**packet, "depth_float32_base64": tampered}
    low = 1.4 - 0.008
    high = 1.4 + 0.008
    measured = np.asarray([low, np.nextafter(low, -np.inf), high, np.nextafter(high, np.inf)])
    near, loss = depth_changes(measured, np.full(4, 1.4), 0.004)
    require(
        near.tolist() == [False, True, False, False]
        and loss.tolist() == [False, False, False, True],
        "8 mm strict near/loss boundary changed",
    )
    calibration = ROOT / roots["calibration"]
    diagnostic_asset = output / "preflight/diagnostic-pin.xml"
    registration = read(case / "optical-registration.json")
    bad_camera = copy.deepcopy(optical_model.geometry)
    bad_camera["camera"]["calibration_version"] = "foreign-calibration"
    bad_seal = copy.deepcopy(seal)
    bad_seal["members_sha256"]["prefix/receipt.json"] = "0" * 64
    return {
        "same_frame_self_compare": {"changed_rgb": 0, "changed_depth_words": 0, "changed_mask": 0},
        "8mm_gate": {"near": near.tolist(), "lost_or_farther": loss.tolist()},
        "original_2376_2384_swap": rejected(
            lambda: archived_samples(
                case, [("0111.json.gz", 2376, 408, "LIFT", "FEEDBACK", "motion")], episode
            ),
            "archived command phase",
        ),
        "foreign_episode": rejected(
            lambda: archived_samples(case, ANCHORS, "foreign"), "camera index identity"
        ),
        "wrong_command_phase": negative_row("native_last_command_seq", 236, "command phase"),
        "wrong_role": negative_row("research_role", "motion", "shutter role"),
        "stale_camera_encoder": negative_row(
            "camera_encoder_sim_time_s", 0.0, "camera encoder clock"
        ),
        "missing_finger_pose": negative_row("camera_finger_positions_m", [], "geometry incomplete"),
        "missing_object_rotation": negative_label("rotation"),
        "reordered_depth_row": rejected(
            lambda: RGBDObservation.model_validate(frame_bad_depth), "checksum"
        ),
        "bad_frame_checksum": rejected(
            lambda: RGBDObservation.model_validate(frame_bad_sha), "checksum"
        ),
        "duplicate_endpoint": rejected(
            lambda: tick_index([endpoints[0], *endpoints], "step", 0, 1520),
            "duplicate, missing or disordered",
        ),
        "missing_endpoint": rejected(
            lambda: tick_index(endpoints[1:], "step", 0, 1520), "duplicate, missing or disordered"
        ),
        "mismatched_seal": rejected(lambda: check_members(bad_seal, output), "member SHA256"),
        "wrong_calibration": rejected(
            lambda: LocalClearance(
                bad_camera,
                optical_model.asset_path,
                calibration,
                calibration_sha256=registration["calibration_sha256"],
                isolated_scene=True,
            ),
            "incorrect asset or camera registration",
        ),
        "B_asset_under_original_certificate": rejected(
            lambda: LocalClearance(
                optical_model.geometry,
                diagnostic_asset,
                calibration,
                calibration_sha256=registration["calibration_sha256"],
                isolated_scene=True,
            ),
            "incorrect asset or camera registration",
        ),
    }


def cold_read(plan, amendment, seal_path, reader):
    cpu_environment(plan)
    output = ROOT / plan["private_output"]
    require(seal_path.resolve() == output / "input-seal.json", "wrong cold-read input")
    seal = read(seal_path)
    start = stamp()
    sources = verify_sources(plan, amendment)
    check_members(seal, output)
    folder, receipt = prefix_files(output)
    tool = source_module(
        HERE.parent / "round-g1-grid04-2384-surface-attribution-20261126/attribute_surface.py"
    )
    verification_tools = prepare(plan)
    verify_imports(plan, sources["sha256"])
    cv2.setNumThreads(1)
    physics_guard, camera_guard, backend_guard = no_camera_or_step()
    with physics_guard, camera_guard, backend_guard:
        prefix, endpoints = replay_archive(plan, folder, receipt, verification_tools)
        geometry = geometry_archive(plan, output)
        pending = read(output / "preflight/requests.json")
        require(
            len(pending) == 4
            and all(not row["requested"] and row["status"] == CAPTURE_STOP for row in pending),
            "wrong unexecuted slot registration",
        )
        expected_rng = read(output / "preflight/rng-first-failure.json")
        provenance = expected_rng.pop("initial_arithmetic_chunk")
        actual_rng = noise_check(plan)
        require(actual_rng == expected_rng, "independent frozen RNG preflight evidence differs")
        optical_model, old_frames, reference = archived_optics(plan, tool)
        negative = controls(plan, seal, output, endpoints, optical_model)

    proof = {
        "input_seal_sha256": sha(seal_path),
        "prefix": prefix,
        "geometry": geometry,
        "frozen_rgbd_surface_readback": old_frames,
        "reference_projection_seal_sha256": reference,
        "first_failures": {
            "source": read(output / "preflight/source-first-failure.json"),
            "startup": read(output / "preflight/startup-first-failure.json"),
            "acquisition": {**actual_rng, "first_read_only_arithmetic_chunk": provenance},
        },
        "unexecuted_slots": pending,
        "controls": negative,
        "independent_readback_counts": {
            "rgbd_requests": 0,
            "reference_renders": 0,
            "native_steps": 0,
            "native_resets": 0,
        },
        "frozen_originals": sources["formal"],
        "formal_simulations": 0,
    }
    path = output / f"readback-{reader}.json"
    write(path, proof)
    write(
        output / f"readback-{reader}.receipt.json",
        {"pid": os.getpid(), "started_utc": start, "ended_utc": stamp(), "sha256": sha(path)},
    )
    print(
        canonical(
            {"sha256": sha(path), "controls": len(negative), "old_frames": sorted(old_frames)}
        ).decode()
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sealed", type=Path, required=True)
    parser.add_argument("--reader", choices=(1, 2), type=int)
    args = parser.parse_args()
    plan, amendment = inputs(args.plan)
    if args.reader is None:
        require(
            args.sealed.resolve() == ROOT / plan["private_output"] / "input-seal.json",
            "unregistered seal output",
        )
        write(args.sealed, input_seal(plan))
    else:
        cold_read(plan, amendment, args.sealed, args.reader)
