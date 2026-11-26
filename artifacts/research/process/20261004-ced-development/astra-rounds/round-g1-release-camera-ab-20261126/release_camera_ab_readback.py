"""Independent cold reduction of the sealed A/B frame packets and source physics."""

import argparse
import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

from release_camera_ab_inputs import (
    HERE, PLAN, checked_json, expand, inside, ordered_keys, originals, packet, read, require,
    sha, source_module, verify_inputs, write,
)
from release_camera_ab_optics import index_rows, interval_covers
from read_pose_coverage import ratios
from scripts.graduation.g1_complete_worker import native_reset_ids


def mask(frame):
    return np.frombuffer(base64.b64decode(frame.valid_mask_base64), "u1").astype(bool)


def old_a_check(replayed, archived, receipt):
    def image(frame):
        with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as png:
            return np.asarray(png.convert("RGB"))

    def depth(frame):
        return np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").astype(float)

    good = mask(replayed)
    require(
        np.array_equal(image(replayed), image(archived)) and np.array_equal(good, mask(archived))
        and receipt["rgb_equal"] and receipt["valid_mask_equal"],
        "A original image or mask changed",
    )
    delta = (depth(replayed) - depth(archived)) * 1000
    values = delta[good]
    most = int(np.argmax(np.where(good, abs(delta), -np.inf)))
    metrics = dict(
        signed_mean_mm=float(values.mean()), rmse_mm=float(np.sqrt((values**2).mean())),
        p99_abs_mm=float(np.percentile(abs(values), 99)), max_abs_mm=float(abs(delta[most])),
    )
    lim = PLAN["native_protocol"]["A_replay_checks"]
    require(
        abs(metrics["signed_mean_mm"]) <= lim["absolute_mean_depth_difference_max_mm"]
        and metrics["rmse_mm"] <= lim["depth_rmse_max_mm"]
        and metrics["p99_abs_mm"] <= lim["absolute_depth_difference_p99_max_mm"]
        and all(abs(value - receipt[k]) <= 1e-12 for k, value in metrics.items())
        and receipt["max_abs_uv"] == [most % replayed.width, most // replayed.width]
        and receipt["passed"] and receipt["original_pose_rejection_reproduced"],
        "A historical baseline did not cold-read",
    )
    return metrics | {"rgb_and_mask_exact": True, "max_abs_uv": receipt["max_abs_uv"]}


def native_identity(directory, cid, item, expected_reset):
    folder = directory / cid
    reset = checked_json(folder / "native-resets.json", item["reset_sha256"])
    events = read(folder / "native-reset-full.json")
    episode = item["episode_id"]
    native_reset_ids(events, expected_reset["scenario_id"], episode)
    native_reset_ids(reset, expected_reset["scenario_id"], episode)
    require(
        events[0]["parameters"]["requested"] == expected_reset
        and all(a["operation_id"] == b["operation_id"] and a["episode_id"] == b["episode_id"]
                for a, b in zip(reset, events, strict=True))
        and read(folder / "shutdown.json") == {"closed":True, "new_physics_steps":0, "new_control_actions":0},
        "new native reset/shutdown identity differs",
    )
    return episode


def read_slot(root, row, key, result, slot, cal, terminal):
    arm, cid, source_tick = key.split("/")
    tick = int(source_tick)
    source = slot["source"]
    directory = root / arm
    folder = directory / cid
    rgbd = inside(directory, row["packet"])
    require(sha(rgbd) == row["file_sha256"] and row["source"] == source, "packet/source digest mismatch")
    fresh = packet(rgbd)
    req = read(folder / f"{tick}-request.json")
    receipt = read(folder / f"{tick}-receipt.json")
    operations = [item for item in read(folder / "native-operation-events.json") if item.get("frame_id") == fresh.frame_id]
    event, = operations
    require(
        req["rgbd_request"] == 1 and req["source"] == source and req["seed"] == 649300+tick
        and req["new_episode"] == fresh.episode_id == row["new_episode"] == result["new_episode"]
        and fresh.episode_id not in (source["source_replay_episode"], source["historical_fit_episode"])
        and source["historical_A_frame"] != fresh.frame_id == row["frame_id"] == result["frame_id"]
        and fresh.checksum_sha256 == row["checksum_sha256"] == result["checksum_sha256"]
        and source["source_trace_sha256"] == result["source_trace_sha256"]
        and fresh.sim_time_s == row["robot"]["camera_encoder_sim_time_s"] == source["source_time_s"]
        and tick == source["source_tick"] == row["source_tick"] == result["source_tick"]
        and receipt["gl"] == cal["renderer"]
        and receipt["pre_state_sha256"] == receipt["post_state_sha256"]
        and event["pass_state_hashes"] == [receipt["pre_state_sha256"]] * 2
        and event["physics_step"] == event["instance_count"] == 0
        and event["sim_time_s"] == fresh.sim_time_s and event["episode_id"] == fresh.episode_id
        and event["operation_id"] == receipt["native_capture_operation_id"]
        and event["phase"] == "END" and event["kind"] == "CAPTURE" and event["error"] is None
        and receipt["rng_initial_sha256"] == req["initial_rng_sha256"]
        and int(mask(fresh).sum()) == receipt["raw_valid_pixels"]
        and not result["original_gate_qualified"],
        f"native static evidence did not join {key}",
    )
    gaps_m, bottom, inside_region = terminal.gap_and_table(slot["row"], slot["size"])
    physical_issues = terminal.dwell_issues(slot["row"], gaps_m, inside_region)
    cover = interval_covers(result["gaps_m"], np.asarray(gaps_m))
    pose_bounds = ratios(result["pose"], {
        "center_m": slot["row"]["geom"]["object_geom"][0],
        "rotation": slot["row"]["geom"]["object_geom"][1],
    }) if result["pose"] else None
    require(cover is not False and (pose_bounds is None or pose_bounds["current_valid_bounds"]),
            f"issued current bound did not cover original physical state: {key}")
    require(not (result["static_frame_eligible"] and physical_issues), f"static false admission {key}")
    return fresh, {
        "source_step": tick, "after_open_step": source["offset"], "frame_id": fresh.frame_id,
        "rgbd_sha256": row["file_sha256"], "checksum_sha256": fresh.checksum_sha256,
        "source_trace_sha256": source["source_trace_sha256"], "rng_initial_sha256": receipt["rng_initial_sha256"],
        "valid_pixels": receipt["raw_valid_pixels"], "capture_ms": receipt["native_capture_ms"],
        "optical_probe_ms": result["probe_ms"], "observed_ids": result["observed_ids"],
        "usable_ids": result["usable_ids"], "pose_method": result["pose_method"], "unqualified_proposal": result["proposal_method"],
        "opposite_board": result["opposite_board"], "red_top": result["red_top"],
        "optical_guard_reasons": result["reason_codes"], "observed_support_and_rim": result["observed_support_and_rim"],
        "gaps_mm": (np.asarray(result["gaps_m"])*1000).tolist() if result["gaps_m"] is not None else None,
        "physical_pad_gaps_mm": [g*1000 for g in gaps_m], "physical_clearance_bottom_m": bottom,
        "physical_dwell_issues": physical_issues, "physical_inside_target": inside_region,
        "interval_coverage": cover, "pose_bounds": pose_bounds, "static_frame_eligible": result["static_frame_eligible"],
        "original_full_release_gate": False,
    }


def reduction(root):
    seal = read(root / "capture-seal.json")
    reg_hash = seal["registration_sha256"]
    registration = checked_json(root / "registration.json", reg_hash)
    require(
        (seal["exposure_requests"], seal["captured"], seal["new_physics_steps"],
         seal["new_control_actions"], seal["formal_simulations"]) == (18,18,0,0,0)
        and len(list(root.glob("[AB]/*/*-request.json"))) == 18
        and not (root / "failure.json").exists(), "not a complete registered capture",
    )
    for file, expected in registration["plan_files_sha256"].items():
        require(sha(inside(HERE, file)) == expected, "registered plan file changed")
    for file, expected in registration["source_files_sha256"].items():
        require(sha(inside(HERE, file)) == expected, "registered diagnostic source changed")
    bound_files = {
        "input-manifest.json": registration["input_manifest_sha256"],
        "source-slots.json": registration["source_slots_sha256"],
        "historical-controls.json": registration["control_receipt_sha256"],
        "static-pose-preflight.json": registration["restore_preflight_sha256"],
    }
    protected = {key: checked_json(root / key, expected) for key, expected in bound_files.items()}
    sealed = {key: checked_json(inside(root, key), expected) for key, expected in seal["sealed_sha256"].items()}
    manifest, slots, cal = verify_inputs()
    frozen = originals()
    require(
        manifest == protected["input-manifest.json"]
        and frozen == seal["originals_after"] == registration["frozen_formal_originals"], "original frozen sources changed",
    )
    terminal = source_module("independent_release_geometry", expand("{T}/terminal_rebound.py"))
    frame_ids, episodes = set(), set()
    rows, raw_frames = {}, {}
    for arm in ("A", "B"):
        index = sealed[f"{arm}/index.json"]
        predictions = sealed[f"{arm}/predictions.json"]
        require(index["registration_sha256"] == predictions["registration_sha256"] == reg_hash
                and predictions["physical_label_access"] == "denied_by_audit_hook", "index or prediction seal")
        index_rows(index["rows"], arm)
        index_rows(predictions["predictions"], arm)
        for case in PLAN["cases"]:
            cid, ticks = case["id"], case["ticks"]
            episode = native_identity(root / arm, cid, index["cases"][cid], slots[f"{arm}/{cid}/{ticks[0]}"]["reset"])
            require(episode not in episodes, "identity reset produced a reused episode")
            episodes.add(episode)
            for tick in ticks:
                key = f"{arm}/{cid}/{tick}"
                source = protected["source-slots.json"][key]
                entry = index["rows"][key]
                require(source == slots[key]["source"] and entry["new_episode"] == episode, "source slot mismatch")
                frame, observation = read_slot(root, entry, key, predictions["predictions"][key], slots[key], cal, terminal)
                require(frame.frame_id not in frame_ids, "cross-arm repeated frame identity")
                frame_ids.add(frame.frame_id)
                if arm == "A":
                    observation["archive_A_check"] = old_a_check(
                        frame, packet(slots[key]["archive_A"]), sealed["A-baseline.json"][key],
                    )
                rows[key] = observation
                raw_frames[key] = frame

    pairs = {}
    for case in PLAN["cases"]:
        cid = case["id"]
        for tick in case["ticks"]:
            a, b = (f"{arm}/{cid}/{tick}" for arm in ("A", "B"))
            first, second = rows[a], rows[b]
            require(first["rng_initial_sha256"] == second["rng_initial_sha256"], "A/B noise streams differ at entry")
            pairs[f"{cid}/{tick}"] = {
                "absolute_step": tick, "after_open_steps": first["after_open_step"],
                "A": a, "B": b, "valid_mask_exact": bool(np.array_equal(mask(raw_frames[a]), mask(raw_frames[b]))),
                "B_minus_A_physical_pad_gaps_mm": [q-p for p,q in zip(first["physical_pad_gaps_mm"], second["physical_pad_gaps_mm"], strict=True)],
                "B_added_static_current_evidence": second["static_frame_eligible"] and not first["static_frame_eligible"],
                "B_lost_static_current_evidence": first["static_frame_eligible"] and not second["static_frame_eligible"],
            }
    return {
        "registration_sha256": reg_hash, "capture_seal_sha256": sha(root / "capture-seal.json"),
        "input_file_count": len(manifest), "frozen_originals": frozen,
        "population": {"fit_cases": 3, "native_image_requests": 18, "native_frames": 18, "identity_resets": len(episodes),
                       "additional_integrator_steps": 0, "new_actuator_commands": 0, "formal": 0, "heldout": 0},
        "controls": protected["historical-controls.json"],
        "max_restore_position_residual_m": max(a[0] for poses in protected["static-pose-preflight.json"].values() for a in poses.values()),
        "max_restore_rotation_frobenius": max(a[1] for poses in protected["static-pose-preflight.json"].values() for a in poses.values()),
        "rows": rows, "pairs": pairs, "online_qualification": False, "whole_system_completion": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("label", choices=("cold-01", "cold-02"))
    options = parser.parse_args()
    root = expand(PLAN["outputs"]["new_private_root"])
    data = reduction(root)
    out = root / (options.label + ".json")
    write(out, data)
    print(f"{options.label}: {len(data['rows'])} new frames and {len(data['pairs'])} pairs, SHA256 {sha(out)}")
