"""Compare two directional clearance estimates on the enrolled RELEASE exposures."""

import argparse
import base64
import gzip
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from read_dense_payload import SOURCE, bind_fixture
from read_pose_coverage import native_marker
from scripts.graduation import g1_complete_cv_payload_observation as observer
from scripts.graduation.g1_complete_cv_calibrate import axial
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_handoff_optics import (
    directional_error,
    measured_pose,
    rigid_pose,
)
from scripts.graduation.g1_complete_trials import PRIVATE
from scripts.graduation.perception_io import ROOT, pinned, sha, write

from cloud_edge_robot_arm.vision.observations import RGBDObservation

HERE = Path(__file__).resolve().parent
PLAN = "2399f6d5d1ead64dd7314f23d96f5b767e9732e3d3ec2b18b2f67632b71a1ca4"
ADDENDUM = "aa4fa4c4771bf5b2027b981b54352178f170153063a3c58f58d3be43d2486120"
GAP_LIMIT_M = 0.00025
MIN_FINGER_M = 0.035
MAX_MS = 100
CASES = ("dense-fit-01", "dense-fit-02", "dense-fit-03")
SIGNS = observer.SIGNS


def design():
    plan = pinned(HERE / "plan.json", PLAN)
    extension = pinned(HERE / "plan-addendum.json", ADDENDUM)
    source = ROOT / "scripts/graduation"
    parent_round = HERE.parent / "round-g1-continuous-payload-observation-20261125"
    assembly = ROOT / plan["asset"]
    runtime = ROOT / PRIVATE / "builds" / SOURCE / "runtime-source"
    batch = ROOT / PRIVATE / "batches/train-full-04"
    paths = {
        assembly.name: assembly,
        "sealed_runtime/g1_visibility_vision.py": runtime
        / "scripts/graduation/g1_visibility_vision.py",
        "read_pose_coverage.py": parent_round / "read_pose_coverage.py",
        "read_dense_payload.py": parent_round / "read_dense_payload.py",
    }
    for name, expected in extension["source_sha256"].items():
        if sha(paths.get(name, source / name)) != expected:
            raise ValueError(f"registered source changed: {name}")
    bindings = extension["bind_fixture_lineage"]
    allocation = pinned(batch / "cvfix-t02/allocation.json", bindings["cvfix-t02/allocation.json"])
    pinned(batch / "allocation.json", bindings["train-full-04/allocation.json"])
    pinned(runtime / "runtime-build.json", bindings["runtime_build_pin"])
    if SOURCE != bindings["runtime_build_pin"] or (
        allocation["calibration_sha256"] != bindings["allocation_calibration_pin"]
    ):
        raise ValueError("release replay calibration or build changed")
    if observer._profile()["single_id8_red_print"]["enabled"]:
        raise ValueError("failed single-marker certificate is ineligible")
    return plan, extension


def enrolled(case, plan, extension):
    root = ROOT / plan["input_root"]
    remote = f"physical-03/{case}"
    folder = root / remote
    paths = plan["input_sha256"]
    baseline_name = f"{case}-prediction-02.json"
    baseline = pinned(root / baseline_name, paths[baseline_name])
    index = pinned(folder / "rgbd-index.json", paths[f"{remote}/rgbd-index.json"])
    receipt = pinned(folder / "sensor-receipt.json", paths[f"{remote}/sensor-receipt.json"])
    commands = pinned(folder / "native-commands.json", paths[f"{remote}/native-commands.json"])
    if (
        receipt["episode_id"] != index["episode_id"]
        or receipt["index_sha256"] != paths[f"{remote}/rgbd-index.json"]
        or sha(folder / "native-resets.json")
        != extension["bind_fixture_lineage"]["native_resets_sha256_fit_01_02_03"][CASES.index(case)]
    ):
        raise ValueError(f"release index was not bound to the original reset: {case}")

    rows = [item for item in index["rows"] if item["skill"] == "RELEASE"]
    old = [item for item in baseline["records"] if item["skill"] == "RELEASE"]
    manifest = {item["file"]: item["file_sha256"] for item in rows}
    digest = hashlib.sha256(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    if (
        len(rows) != 33
        or len(manifest) != 33
        or len(old) != 33
        or (digest != extension["release_map_sha256_supplied"][case])
    ):
        raise ValueError(f"release exposure manifest changed: {case}")
    for item, previous in zip(rows, old, strict=True):
        sample = item["robot"]
        if (
            len(Path(item["file"]).parts) != 1
            or baseline["source_sha256"][item["file"]] != item["file_sha256"]
            or item["phase"] != previous["phase"]
            or item["dwell_tick"] != previous["dwell_tick"]
            or sample["frame_id"] != previous["frame_id"]
            or sample["checksum_sha256"] != previous["checksum_sha256"]
            or sample["physics_step"] != previous["step"]
        ):
            raise ValueError(f"original shadow prediction cannot be joined: {case}")
    return folder, receipt, commands, list(zip(rows, old, strict=True))


def hand_geometry(model, sample):
    joints = np.asarray(sample["camera_joint_positions_rad"])
    fingers = np.asarray(sample["camera_finger_positions_m"])
    if (
        joints.shape != (7,)
        or fingers.shape != (2,)
        or not np.isfinite(np.r_[joints, fingers]).all()
    ):
        raise ValueError("missing synchronized native encoder geometry")
    tcp, rotation, _ = model.forward(joints)
    outward = np.array([rotation[:, 1], -rotation[:, 1]])
    pads = model.hand_at(tcp, rotation, fingers)[1:]
    planes = [
        axis @ pad.c - abs(axis @ pad.r) @ pad.h for axis, pad in zip(outward, pads, strict=True)
    ]
    return tcp, outward, np.asarray(planes), fingers


def per_corner_intervals(pose, model, axes, planes):
    corners = model.object[0].c + SIGNS * model.object[0].h
    particles = corners @ np.asarray(pose["rotation"]).T + pose["center_m"]
    revised, old, ranges = [], [], []
    for axis, inner_face in zip(axes, planes, strict=True):
        projections = particles @ axis
        errors = directional_error(pose, corners, axis)
        opposite_errors = directional_error(pose, corners, -axis)
        lower_extent = np.max(projections - errors)
        upper_extent = np.max(projections + errors)
        lower_gap, upper_gap = inner_face - upper_extent, inner_face - lower_extent
        revised.append([float(lower_gap), float(upper_gap)])
        baseline = inner_face - projections.max()
        old.append([float(baseline - max(errors)), float(baseline + max(errors))])
        ranges.append(
            [
                float(lower_extent + np.max(-projections - opposite_errors)),
                float(upper_extent + np.max(-projections + opposite_errors)),
            ]
        )
    return np.asarray(revised), np.asarray(old), np.asarray(ranges)


def red_top_diagnostic(frame, marker, geometry, proposal, model, axes, planes, widths):
    if proposal is None:
        return None
    depth = axial(frame)
    rgb = cv2.imdecode(
        np.frombuffer(base64.b64decode(frame.rgb_png_base64), np.uint8), cv2.IMREAD_COLOR
    )
    if rgb is None:
        return None
    rgb = rgb[:, :, ::-1]
    refined, face = observer.red_face_pose(frame, marker, geometry, rgb, depth, proposal)
    if refined is None or face is None:
        return None
    center = np.asarray(proposal["center_world_m"])
    rotation = np.asarray(proposal["rotation_object_to_world"])
    x, y = observer._window(frame, center + rotation[:, 2] * 0.035, 16)
    world = observer._cloud(frame, x, y, depth)
    local = (world - center) @ rotation
    r, g, b = rgb[y, x].astype(float).transpose(2, 0, 1)
    selected = (
        (r > 1.25 * g + 7)
        & (r > 1.25 * b + 7)
        & (abs(local[:, :, :2]).max(axis=2) < 0.042)
        & (abs(local[:, :, 2] - 0.035) < observer.BAND)
    )
    points = world[selected]
    if len(points) != face["red_top_samples"] or not len(points) or not np.isfinite(points).all():
        return None
    smallest_width = 2 * float(model.object[0].h.min())
    largest_width = 2 * float(np.linalg.norm(model.object[0].h))
    results = []
    for i, (axis, inner_face) in enumerate(zip(axes, planes, strict=True)):
        values = points @ axis
        lo, hi = float(values.min()), float(values.max())
        span = hi - lo
        width_lo, width_hi = widths[i] if widths is not None else (smallest_width, largest_width)
        width_lo = max(width_lo, smallest_width, span)
        width_hi = min(width_hi, largest_width)
        if span > width_hi or width_lo > width_hi:
            return None
        results.append(
            {
                "minimum_sample_m": lo,
                "maximum_sample_m": hi,
                "projected_sample_span_m": span,
                "box_width_interval_m": [float(width_lo), float(width_hi)],
                "edge_ambiguity_at_maximum_width_m": float(width_hi - span),
                "optimistic_fixed_width_gap_lower_m": float(inner_face - (lo + width_lo)),
                "zero_error_all_width_gap_lower_m": float(inner_face - (lo + width_hi)),
            }
        )
    return {
        "top_associated_samples": len(points),
        "side_samples": face["red_side_samples"],
        "visible_top_strip_edges": len(face["exposed_top_rim_lines_world_m"]),
        "independent_orientation_bound": widths is not None,
        "assumption": "Registered red association and exact pixels/depth. Diagnostic only.",
        "by_outward_axis": results,
    }


def latest_measured_gripper(commands, sample, episode):
    bound = sample["native_last_command_seq"]
    relevant = [
        row
        for row in commands
        if row["type"] == "gripper"
        and row["accepted"]
        and row["physics_step"] <= sample["physics_step"]
        and row["command_seq"] <= bound
    ]
    command = max(relevant, key=lambda row: row["command_seq"])
    if (
        command["episode_id"] != episode
        or command["physics_step"] != sample["last_accepted_gripper_command_step"]
        or command["target_open"] is not sample["last_accepted_gripper_open"]
    ):
        raise ValueError("exposure motion record and actual gripper command differ")
    return command


def row_eligible(intervals, open_accepted, fingers, support):
    return bool(
        open_accepted
        and min(fingers) > MIN_FINGER_M
        and support
        and intervals is not None
        and np.min(intervals[:, 0]) > GAP_LIMIT_M
    )


def frame_gate(frame, marker, geometry, sample, identity):
    return bool(
        identity.matches(frame, marker, geometry, sample["physics_step"])
        and frame.frame_id == sample["frame_id"]
        and frame.checksum_sha256 == sample["checksum_sha256"]
        and frame.sim_time_s == sample["sim_time_s"] == sample["camera_encoder_sim_time_s"]
    )


def chain_append(window, record, seen):
    step = record["step"]
    frame_id = record["frame_id"]
    tick = record["dwell_tick"]
    if frame_id in seen:
        window.clear()
        return 0
    seen.add(frame_id)
    if (
        not record["eligible"]
        or record["probe_processing_ms"] > MAX_MS
        or type(tick) is not int
        or not 0 <= tick <= 240
        or tick % 8 != 0
    ):
        window.clear()
        return 0
    if window and (step - window[-1]["step"] != 8 or tick - window[-1]["dwell_tick"] != 8):
        window.clear()
    cert = record["support_pose"]
    window.append(
        {
            "step": step,
            "frame_id": frame_id,
            "dwell_tick": tick,
            "center_m": cert["center_m"],
            "rotation": cert["rotation"],
            "bottom_m": cert["bottom_m"],
        }
    )
    return len(window)


def chain_controls():
    sample = {
        "eligible": True,
        "probe_processing_ms": 1.0,
        "support_pose": {
            "center_m": [0.2, 0.25, 0.035],
            "rotation": np.eye(3).tolist(),
            "bottom_m": 0.0,
        },
    }
    window, seen = [], set()
    first = dict(sample, step=400, dwell_tick=0, frame_id="first")
    assert chain_append(window, first, seen) == 1
    repeated = chain_append(window, first, seen) == 0
    second = dict(sample, step=408, dwell_tick=8, frame_id="second")
    chain_append(window, second, seen)
    gap = dict(sample, step=424, dwell_tick=24, frame_id="gap")
    missing_exposure = chain_append(window, gap, seen) == 1
    expired = dict(sample, step=432, dwell_tick=32, frame_id="expired", probe_processing_ms=100.01)
    over_deadline = chain_append(window, expired, seen) == 0
    return dict(
        repeated_frame_rejected=repeated,
        missing_frame_broke_chain=missing_exposure,
        expired_feedback_rejected=over_deadline,
    )


def predict_case(case, folder, rows, receipt, commands, measure, model):
    identity, geometry = bind_fixture(folder, receipt)
    previous_history, window, seen = {}, [], set()
    controls, predictions = None, []
    for item, previous in rows:
        path = folder / item["file"]
        if sha(path) != item["file_sha256"]:
            raise ValueError(f"raw release packet changed: {case} {path.name}")
        started = time.perf_counter_ns()
        frame = RGBDObservation.model_validate_json(gzip.decompress(path.read_bytes()))
        sample = item["robot"]
        step, phase = sample["physics_step"], item["phase"]
        marker = measure(frame, geometry)
        if not frame_gate(frame, marker, geometry, sample, identity):
            raise ValueError(f"release packet and encoder bindings differ: {case} {step}")
        command = latest_measured_gripper(commands, sample, receipt["episode_id"])
        _, axes, planes, fingers = hand_geometry(model, sample)
        pose = rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
        old = observer.payload_observation(
            frame,
            marker,
            geometry,
            sample,
            "RELEASE",
            phase,
            identity=identity,
            physics_step=step,
            optical=pose,
            history=previous_history,
        )
        intervals, old_intervals, widths = (
            per_corner_intervals(pose, model, axes, planes) if pose else (None, None, None)
        )
        support = bool(old["evidence"].get("observed_support_and_rim", False))
        support_pose = (
            {
                "center_m": pose["center_m"],
                "rotation": pose["rotation"],
                "bottom_m": old["evidence"]["nominal_cube_bottom_m"],
            }
            if pose and support
            else None
        )
        eligible = row_eligible(intervals, command["target_open"], fingers, support)
        if (
            type(sample["previous_native_return_step"]) is not int
            or not 0 <= sample["previous_native_return_step"] <= step
            or sample["previous_native_successful_skill"] != "RELEASE"
        ):
            eligible = False
        proposal = pose or measured_pose(frame, marker, geometry)
        red = red_top_diagnostic(frame, marker, geometry, proposal, model, axes, planes, widths)
        processing = (time.perf_counter_ns() - started) / 1e6
        reasons = []
        if pose is None:
            reasons.append("no_current_independently_qualified_pose")
        if not support:
            reasons.append("current_support_or_rim_unproven")
        if not command["target_open"] or min(fingers) <= MIN_FINGER_M:
            reasons.append("current_opening_unproven")
        if intervals is not None and np.min(intervals[:, 0]) <= GAP_LIMIT_M:
            reasons.append("two_pad_clearance_lower_bound_not_proven")
        if not eligible and not reasons:
            reasons.append("prior_release_return_not_bound")
        if processing > MAX_MS:
            reasons.append("offline_probe_over_100_ms")
        record = {
            "step": step,
            "frame_id": frame.frame_id,
            "checksum_sha256": frame.checksum_sha256,
            "phase": phase,
            "dwell_tick": item["dwell_tick"],
            "raw_file_sha256": sha(path),
            "episode_id": frame.episode_id,
            "calibration_version": frame.calibration_version,
            "probe_processing_ms": processing,
            "gripper_open": command["target_open"],
            "gripper_command_seq": command["command_seq"],
            "fingers_m": fingers.tolist(),
            "support_pose": support_pose,
            "eligible": eligible and processing <= MAX_MS,
            "reason_codes": reasons,
            "qualified_pose_method": pose["method"] if pose else None,
            "unqualified_proposal_method": proposal["method"] if proposal and not pose else None,
            "registered_rim_lower_gaps_diagnostic_m": old["evidence"].get(
                "lower_transverse_gap_current_rims_m"
            ),
            "rim_interval_intersected": False,
            "old_global_error_intervals_m": old_intervals.tolist() if pose else None,
            "revised_per_corner_intervals_m": intervals.tolist() if pose else None,
            "historical_shadow": {
                name: previous["result"]["evidence"].get(name)
                for name in (
                    "observed_support_and_rim",
                    "observed_two_finger_separation",
                    "stable_observation_count",
                    "reason",
                )
            },
            "red_optimistic_only": red,
        }
        if phase == "DWELL":
            record["complete_chain_count"] = chain_append(window, record, seen)
            record["full_shadow_stable"] = len(window) == 31 and observer.stable_support(window)
        predictions.append(record)
        if controls is None:
            controls = {
                **chain_controls(),
                "wrong_calibration_rejected": not frame_gate(
                    frame, marker, geometry, sample, replace(identity, calibration_version="wrong")
                ),
                "stale_encoder_time_rejected": not frame_gate(
                    frame,
                    marker,
                    geometry,
                    {**sample, "camera_encoder_sim_time_s": sample["sim_time_s"] - 1 / 240},
                    identity,
                ),
                "wrong_packet_id_rejected": not frame_gate(
                    frame,
                    marker,
                    geometry,
                    {**sample, "frame_id": "foreign"},
                    identity,
                ),
                "closed_command_rejected": not row_eligible(
                    np.ones((2, 2)),
                    False,
                    [0.039, 0.039],
                    True,
                ),
                "threshold_equality_rejected": not row_eligible(
                    np.repeat([[GAP_LIMIT_M, 1.0]], 2, axis=0),
                    True,
                    [0.039, 0.039],
                    True,
                ),
            }
    if not all(controls.values()):
        raise ValueError(f"release metadata negative control was accepted: {case}")
    return {"records": predictions, "metadata_negative_controls": controls}


def no_labels(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        name = args[0].decode() if isinstance(args[0], bytes) else args[0]
        if any(
            key in name
            for key in (
                "offline-physics.json",
                "offline-labels.json",
                "dense-check-",
                "cvfix-e01",
                "cvfix-e02",
            )
        ):
            raise PermissionError("archived labels and held-out rows are unavailable to prediction")


def predict(plan, extension, path):
    sys.addaudithook(no_labels)
    cv2.setNumThreads(1)
    measure, detector = native_marker(SOURCE)
    model = Model(ROOT / plan["asset"])
    cases = {}
    for case in CASES:
        folder, receipt, commands, rows = enrolled(case, plan, extension)
        cases[case] = predict_case(case, folder, rows, receipt, commands, measure, model)
    write(
        path,
        {
            "plan_sha256": PLAN,
            "addendum_sha256": ADDENDUM,
            "label_access": "denied_by_audit_hook",
            "detector_sha256": detector,
            "script_sha256": sha(Path(__file__)),
            "cases": cases,
        },
    )


def exact_gaps(model, sample, label):
    tcp, axes, planes, _ = hand_geometry(model, sample)
    local = model.object[0].c + SIGNS * model.object[0].h
    points = local @ np.asarray(label["rotation"]).T + label["center_m"]
    return planes - (points @ axes.T).max(axis=0), tcp


def measure_score(case, predictions, rows, physical, model):
    labels = {r["frame_id"]: r for r in physical["frame_labels"]}
    scored, motion = [], {}
    for (item, _), row in zip(rows, predictions, strict=True):
        sample = item["robot"]
        label = labels[row["frame_id"]]
        if (
            sample["frame_id"] != row["frame_id"]
            or sample["physics_step"] != row["step"]
            or label["physics_step"] != row["step"]
            or sample["checksum_sha256"] != row["checksum_sha256"]
            or label["checksum_sha256"] != row["checksum_sha256"]
            or item["file_sha256"] != row["raw_file_sha256"]
        ):
            raise ValueError(f"optical and offline release results are not co-exposure: {case}")
        gap, tcp = exact_gaps(model, sample, label)
        touches = label["touching"]
        table_only = bool(touches) and all(
            set(pair) == {"table", "object_geom"} for pair in touches
        )
        dwell = row["phase"] == "DWELL"
        if row["phase"] == "PRE" or (dwell and row["dwell_tick"] == 0):
            motion[row["phase"]] = (np.asarray(label["center_m"]), tcp)
        estimates = row["revised_per_corner_intervals_m"]
        undercoverage = []
        if estimates is not None:
            bounds = np.asarray(estimates)
            undercoverage = np.nonzero((gap < bounds[:, 0] - 1e-10) | (gap > bounds[:, 1] + 1e-10))[
                0
            ].tolist()
        scored.append(
            {
                "frame_id": row["frame_id"],
                "step": row["step"],
                "phase": row["phase"],
                "true_two_pad_gap_m": gap.tolist(),
                "true_table_only_contact": table_only,
                "issued_interval_undercoverage_jaws": undercoverage,
                "false_eligible": bool(
                    row["eligible"]
                    and (not table_only or np.min(gap) <= GAP_LIMIT_M or not row["gripper_open"])
                ),
                "missed_actual_two_pad_clearance": bool(
                    dwell and table_only and min(gap) > GAP_LIMIT_M and not row["eligible"]
                ),
            }
        )
    pre_object, pre_tcp = motion["PRE"]
    first_object, first_tcp = motion["DWELL"]
    return scored, {
        "object_delta_xyz_mm": (1000 * (first_object - pre_object)).tolist(),
        "tcp_delta_xyz_mm": (1000 * (first_tcp - pre_tcp)).tolist(),
    }


def range_report(rows, scores):
    observed = [r for r in rows if r["revised_per_corner_intervals_m"] is not None]
    minima = [
        (pair[0], row["frame_id"], jaw)
        for row in observed
        for jaw, pair in enumerate(row["revised_per_corner_intervals_m"])
    ]
    lower_gain = [
        new[0] - old[0]
        for row in observed
        for new, old in zip(
            row["revised_per_corner_intervals_m"], row["old_global_error_intervals_m"], strict=True
        )
    ]
    crossings = sum(
        old[0] <= GAP_LIMIT_M < new[0]
        for row in observed
        for new, old in zip(
            row["revised_per_corner_intervals_m"], row["old_global_error_intervals_m"], strict=True
        )
    )
    optimum_red = [
        min(
            side["optimistic_fixed_width_gap_lower_m"]
            for side in row["red_optimistic_only"]["by_outward_axis"]
        )
        for row in rows
        if row["red_optimistic_only"]
    ]
    support = [bool(r["support_pose"]) for r in rows]
    return {
        "frames": len(rows),
        "qualified_pose_frames": len(observed),
        "pose_methods": dict(Counter(r["qualified_pose_method"] or "unqualified" for r in rows)),
        "current_support_and_rim_frames": sum(support),
        "eligible_shadow_frames": sum(r["eligible"] for r in rows),
        "available_revised_minimum_m": min(minima) if minima else None,
        "full_set_revised_minimum_m": min(minima) if len(observed) == len(rows) else None,
        "maximum_per_side_lower_gain_m": max(lower_gain) if lower_gain else None,
        "per_side_lower_crossings": crossings,
        "positive_red_association_diagnostic_frames": len(optimum_red),
        "optimistic_minimum_width_passes": sum(x > GAP_LIMIT_M for x in optimum_red),
        "true_gap_minimum_m": float(min(min(s["true_two_pad_gap_m"]) for s in scores)),
        "table_only_contact_frames": sum(s["true_table_only_contact"] for s in scores),
        "coverage_failure_frames": sum(
            bool(s["issued_interval_undercoverage_jaws"]) for s in scores
        ),
        "false_eligible_frames": sum(s["false_eligible"] for s in scores),
        "missed_actual_two_pad_clearance": sum(
            s["missed_actual_two_pad_clearance"] for s in scores
        ),
        "max_probe_processing_ms": max(r["probe_processing_ms"] for r in rows),
        "processing_over_100ms": sum(r["probe_processing_ms"] > MAX_MS for r in rows),
    }


def score(plan, extension, file, sealed_digest, output):
    raw = pinned(file, sealed_digest)
    if (raw["plan_sha256"], raw["addendum_sha256"], raw["script_sha256"]) != (
        PLAN,
        ADDENDUM,
        sha(Path(__file__)),
    ) or raw["label_access"] != "denied_by_audit_hook":
        raise ValueError("unsealed or misbound release predictions")
    model = Model(ROOT / plan["asset"])
    cases = {}
    for case in CASES:
        folder, receipt, _, rows = enrolled(case, plan, extension)
        rel = f"physical-03/{case}/offline-physics.json"
        physical = pinned(folder / "offline-physics.json", plan["input_sha256"][rel])
        prediction = raw["cases"][case]
        predicted = prediction["records"]
        if any(row["episode_id"] != receipt["episode_id"] for row in predicted):
            raise ValueError("episode identity crossed release readback")
        scored, movement = measure_score(case, predicted, rows, physical, model)
        dwell = [r for r in predicted if r["phase"] == "DWELL"]
        labels = [r for r in scored if r["phase"] == "DWELL"]
        cases[case] = {
            "all_release": range_report(predicted, scored),
            "dwell": range_report(dwell, labels),
            "maximum_dwell_chain": max(row["complete_chain_count"] for row in dwell),
            "full_dwell_shadow_stable": sum(row["full_shadow_stable"] for row in dwell),
            "preopen_to_first_dwell": movement,
            "offline_frame_scores": scored,
            "metadata_negative_controls": prediction["metadata_negative_controls"],
        }
    write(
        output,
        {
            "schema": "g1.release-geometry.shadow-fit.v1",
            "prediction_sha256": sealed_digest,
            "plan_sha256": PLAN,
            "addendum_sha256": ADDENDUM,
            "cases": cases,
            "native_end_to_end_deadline_verified": False,
            "online_qualification": False,
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("predict", "score"))
    cli.add_argument("path", type=Path)
    cli.add_argument("--frozen-prediction", type=Path)
    cli.add_argument("--prediction-sha256")
    args = cli.parse_args()
    plan, extension = design()
    if args.mode == "predict":
        predict(plan, extension, args.path)
    else:
        score(plan, extension, args.frozen_prediction, args.prediction_sha256, args.path)
