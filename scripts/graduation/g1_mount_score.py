"""Blind-pixel, action-clock and physical readback of the four paired G1 placements."""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scripts.graduation import g1_mount_score_blind as blind
from scripts.graduation import proposal_scoring
from scripts.graduation.g1_mount_trials import command_readback
from scripts.graduation.guarded_clock_score import source_ledger
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.proposal_translated_cases import exact_discordance_interval

from cloud_edge_robot_arm.experiments.statistics import wilson_interval

ARMS = ("original", "selected")
PHASES = ("APPROACH", "GRASP", "LIFT")
METRICS = ("online_success", "physical_success", "both_windows_qualified", "joint_success")
PLAN_SHA = "62e4c93a03f37fcb1ebd20ac660c09837c225f2b9651960701725c742914bef7"


def equal_point(actual, expected, description):
    if not np.allclose(actual, expected, atol=1e-10, rtol=0):
        raise ValueError(description)


def residuals(packet, state, geometry):
    estimate = packet["estimate"]
    if estimate["object_top_center_world_m"] is None:
        if packet["servo_grasp_world_m"] is not None:
            raise ValueError("servo grasp lacks a registered pose")
        return dict(center_mm=None, top_mm=None, tcp_mm=None)
    depth = estimate["marker_center_optical_depth_m"]
    if (
        estimate["status"] != "OBSERVED"
        or estimate["ids"] != [7]
        or depth is None
        or not 0 < depth < math.inf
        or packet["subpix_depth_patches"] != 5
    ):
        raise ValueError("top-center score lacks unique ID7 or measured positive optical depth")
    rotation = np.asarray(estimate["rotation_to_world"]).reshape(3, 3)
    attach = np.asarray(geometry["marker_to_object"]).reshape(4, 4)[:3, 3]
    object_tcp = np.asarray(geometry["object_to_tcp"]).reshape(4, 4)[:3, 3]
    center = np.asarray(estimate["marker_center_world_m"]) - rotation @ attach
    top = center + rotation[:, 2] * geometry["object_half_extent_m"][2]
    tcp = center + rotation @ object_tcp
    equal_point(
        estimate["object_center_world_m"], center, "estimated center is not bound to the marker"
    )
    equal_point(
        estimate["object_top_center_world_m"], top, "estimated top is not bound to the object"
    )
    grasp = packet["servo_grasp_world_m"]
    if grasp is not None:
        equal_point(grasp, tcp, "servo grasp differs from the registered object-to-TCP transform")
    actual = np.asarray(state["object_geom_position_m"])
    actual_rot = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
    truth_top = actual + actual_rot[:, 2] * state["object_half_extent_m"][2]
    truth_tcp = actual + actual_rot @ object_tcp
    return {
        "center_mm": float(1000 * np.linalg.norm(actual - center)),
        "top_mm": float(1000 * np.linalg.norm(truth_top - top)),
        "tcp_mm": float(1000 * np.linalg.norm(truth_tcp - tcp)),
    }


def role_sources(roles, frames, order, episode):
    by_skill = source_ledger(roles, frames, order)
    packets = {r["frame_id"]: r for r in frames}
    for role in roles:
        f = packets[role["frame_id"]]
        if (
            role["episode_id"] != episode
            or role["captured_at"] != f["captured_at"]
            or role["sim_time_s"] != f["sim_time_s"]
            or datetime.fromisoformat(role["checked_at"]) < datetime.fromisoformat(f["captured_at"])
        ):
            raise ValueError("role episode or clock differs from the actual acquisition")
    return by_skill


def phase_sampling(stage, steps):
    ticks = sorted(set(steps))
    start, end = stage.get("entered_step"), stage.get("end_step")
    dispatched = stage.get("executor_entered") is True
    origin = stage.get("dispatch_step") if dispatched else None
    returned = stage.get("backend_return_step") if dispatched else None
    if ticks and (start is None or end is None or ticks[0] < start or ticks[-1] > end):
        raise ValueError("phase consumed a frame outside the recorded stage")
    controller_end = returned if returned is not None else end
    movement = [i for i in ticks if dispatched and origin <= i <= controller_end]
    start_seen = origin in movement if dispatched else None
    end_seen = controller_end in movement if dispatched else None
    interior = [i for i in movement if origin < i < controller_end]
    covered = sorted({origin, *movement, controller_end}) if dispatched else []
    gaps = np.diff(ticks).tolist()
    if start is None:
        sampling = "NOT_REACHED"
    elif not dispatched:
        sampling = "ENTERED_NO_DISPATCH"
    elif not movement:
        sampling = "NO_FRAME"
    elif origin == controller_end:
        sampling = "ZERO_DURATION"
    elif not (start_seen and end_seen):
        sampling = "MISSING_CONTROLLER_ENDPOINT"
    elif not interior:
        sampling = "ENDPOINTS_ONLY"
    else:
        sampling = "SAMPLED_INTERIOR"
    return {
        "sampling": sampling,
        "entered_step": start,
        "dispatch_step": origin,
        "backend_return_step": returned,
        "action_end_step": end,
        "distinct_steps": len(ticks),
        "first_observed_step": min(ticks, default=None),
        "last_observed_step": max(ticks, default=None),
        "distinct_controller_sample_steps": len(movement),
        "controller_interior_steps": len(interior),
        "controller_start_observed": start_seen,
        "controller_end_observed": end_seen,
        "controller_return_recorded": stage.get("return_evidence") is not None,
        "max_gap_sim_s": max(gaps) / 240 if gaps else None,
        "max_unsampled_interval_steps": max(np.diff(covered).tolist(), default=None),
    }


def pixel_summary(rows):
    n = len(rows)
    count = sum(r["top_mm"] is not None for r in rows)
    depths = [r["optical_depth_m"] for r in rows if r["optical_depth_m"] is not None]
    out = {
        "frames": n,
        "id7": sum(r["id7"] for r in rows),
        "five_positive_depth_patches": sum(r["depth_patches"] == 5 for r in rows),
        "pose_valid": count,
        "pose_fraction": count / n if n else None,
        "default_pose_valid": sum(r["default_observed"] for r in rows),
        "servo_grasp_valid": sum(r["servo_usable"] for r in rows),
        "servo_grasp_fraction": sum(r["servo_usable"] for r in rows) / n if n else None,
        "pose_rejections": dict(Counter(r["pose_reason"] for r in rows if r["top_mm"] is None)),
        "servo_rejections": dict(Counter(r["servo_reason"] for r in rows if not r["servo_usable"])),
        "marker_center_optical_depth_range_m": [min(depths), max(depths)] if depths else None,
    }
    for name in ("center", "top", "tcp"):
        values = [r[name + "_mm"] for r in rows if r[name + "_mm"] is not None]
        out[name + "_p90_mm"] = float(np.quantile(values, 0.9)) if values else None
    return out


def outcomes(rows, metric):
    pairs = {}
    for row in rows:
        pair = pairs.setdefault(row["group"], {})
        arm = row["arm"]
        if arm not in ARMS or arm in pair:
            raise ValueError("duplicate or foreign paired arm")
        value = row.get(metric) if row["acquired"] else None
        if value is not None and type(value) is not bool:
            raise ValueError("expected Boolean allocated outcome or unknown")
        pair[arm] = value
    if len(pairs) != 4 or any(set(pair) != set(ARMS) for pair in pairs.values()):
        raise ValueError("paired design requires four groups and both prespecified arms")
    rates = {}
    for arm in ARMS:
        values = [p[arm] for p in pairs.values()]
        pos, neg, unknown = values.count(True), values.count(False), values.count(None)
        rates[arm] = {
            "allocated": 4,
            "successes": pos,
            "known_failures": neg,
            "unknown": unknown,
            "rate": pos / 4 if not unknown else None,
            "allocation_rate_bounds": [pos / 4, (pos + unknown) / 4],
            "wilson95": list(wilson_interval(pos, 4)) if not unknown else None,
        }
    complete = [p for p in pairs.values() if None not in p.values()]
    positive = sum(p == {"original": False, "selected": True} for p in complete)
    negative = sum(p == {"original": True, "selected": False} for p in complete)
    delta = [0, 0]
    for pair in pairs.values():
        base, treatment = pair["original"], pair["selected"]
        delta[0] += int(treatment or False) - int(True if base is None else base)
        delta[1] += int(True if treatment is None else treatment) - int(base or False)
    ci = None
    if len(complete) == 4:
        plus = exact_discordance_interval(positive, 4)
        minus = exact_discordance_interval(negative, 4)
        ci = [max(-1.0, plus[0] - minus[1]), min(1.0, plus[1] - minus[0])]
    return rates, {
        "outcomes": pairs,
        "complete_pairs": len(complete),
        "gains": positive,
        "losses": negative,
        "allocation_difference_bounds": [d / 4 for d in delta],
        "paired_success_difference": (positive - negative) / 4 if len(complete) == 4 else None,
        "conservative_difference_ci95": ci,
        "ci_method": "Bonferroni simultaneous exact binomial intervals for each discordance",
    }


def check_clocks(run, audit, frames, episode):
    stages = {r["skill"]: r for r in run["actions"]}
    contracts = {r["skill"]: r for r in run["grounding_contracts"]}
    clock = run["action_clock_contexts"]
    checks = [r for r in audit if "shield" in r and r["phase"] in {"PRE", "POST", "FEEDBACK"}]
    if len(checks) != len(clock):
        raise ValueError("clock count differs from original Shield records")
    summary = {name: {} for name in stages}
    last = {}
    for c, verdict in zip(clock, checks, strict=True):
        name, phase = c["skill"], c["phase"]
        s, frame = stages[name], frames[c["frame_id"]]
        if (
            c["episode"] != episode
            or c["origin"] != s["entered_step"]
            or c["absolute"] != frame["physics_step"]
            or c["checksum_sha256"] != frame["checksum_sha256"]
            or c["relative"] != c["absolute"] - c["origin"]
            or c["relative"] < 0
            or c["binding_sha256"] != contracts[name]["binding_sha256"]
            or (phase, c["frame_id"], c["step_id"])
            != (verdict["phase"], verdict["frame_id"], verdict["step_id"])
            or (phase == "PRE" and c["relative"] != 0)
            or (phase in {"FEEDBACK", "POST"} and c["origin"] != s.get("dispatch_step"))
            or (phase == "POST" and c["absolute"] < s["backend_return_step"])
            or (phase == "FEEDBACK" and c["absolute"] <= last.get(name, -1))
        ):
            raise ValueError("action clock identity, phase or step differs from source and Shield")
        if phase == "FEEDBACK":
            last[name] = c["absolute"]
        shield = verdict["shield"]
        allowed = shield["allowed"] is True and shield["limited_parameters"] in (
            None,
            shield["original_parameters"],
        )
        summary_row = summary[name].setdefault(
            phase, {"calls": 0, "interventions": 0, "limiting_rules": []}
        )
        summary_row["calls"] += 1
        if not allowed:
            summary_row["interventions"] += 1
            summary_row["limiting_rules"].append(shield["limiting_rule"] or shield["decision"])
    return summary


def pack_case(root, raw, allocation_sha, geometry):
    blind.checked_geometry(geometry)
    token = read(raw / "acquisition-seal.json")["index_sha256"]
    index = pinned(raw / "pixel-index.json", token)
    if index["allocation_sha256"] != allocation_sha:
        raise ValueError("foreign acquisition allocation")
    bundle = {
        "episode": index["episode"],
        "scene": index["scene"],
        "geometry": geometry,
        "frames": [],
    }
    directory = root / token
    directory.mkdir()
    for i, row in enumerate(index["frames"]):
        name = f"{i:04d}.json"
        if row["file"] != "frames/" + name:
            raise ValueError("packet index path differs from original ordinal")
        os.link(raw / row["file"], directory / name)
        packet = {k: row[k] for k in ("file_sha256", "checksum_sha256", "physics_step", "frame_id")}
        bundle["frames"].append({**packet, "file": name})
    return token, bundle


def blind_process(index, out, receipt):
    args = [
        sys.executable,
        "-m",
        "scripts.graduation.g1_mount_score_blind",
        str(index.resolve()),
        sha(index),
        str(out.resolve()),
    ]
    begin = datetime.now(UTC).isoformat()
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "src")]))
    result = subprocess.run(
        args, cwd=ROOT, env=environment, capture_output=True, text=True, check=False
    )
    write(
        receipt,
        {
            "command": args,
            "started_utc": begin,
            "finished_utc": datetime.now(UTC).isoformat(),
            "cwd": str(ROOT),
            "PYTHONPATH": environment["PYTHONPATH"],
            "return_code": result.returncode,
            "stderr": result.stderr,
            "stdout": result.stdout,
            "reader_sha256": sha(Path(blind.__file__)),
        },
    )
    if result.returncode:
        raise RuntimeError(f"blind packet reader exited {result.returncode}; see {receipt}")


def join_packet_sources(raw, token, output):
    seal = read(output / "seal.json")
    decisions = pinned(output / (token + ".json"), seal["decisions_sha256"][token])
    source = pinned(raw / "pixel-index.json", token)
    if read(raw / "acquisition-seal.json")["index_sha256"] != token or decisions["token"] != token:
        raise ValueError("blind packet set belongs to a different acquisition")
    joined = []
    for row, packet in zip(source["frames"], decisions["packets"], strict=True):
        if any(
            packet[k] != row[k]
            for k in ("frame_id", "checksum_sha256", "physics_step", "file_sha256")
        ):
            raise ValueError("blind packet differs from original step or bytes")
        joined.append({**row, **packet})
    write(raw / "decisions.json", {"index_sha256": token, "decisions": joined})
    write(
        raw / "decision-seal.json",
        {
            "sha256": sha(raw / "decisions.json"),
            "acquisition_sha256": sha(raw / "acquisition-seal.json"),
            "blind_seal_sha256": sha(output / "seal.json"),
            "blind_set_sha256": seal["decisions_sha256"][token],
        },
    )


def check_preview(preview, packet, geometry, episode):
    track = preview["track"]
    if (
        track["observation_id"] != packet["frame_id"]
        or track["observation_checksum_sha256"] != packet["checksum_sha256"]
        or track["episode_id"] != episode
        or track["marker_family_id"] != geometry["marker_family"]
        or track["asset_sha256"] != geometry["pose_marker"]["marked_asset_sha256"]
        or track["camera_to_world"] != geometry["camera"]["camera_to_world"]
        or track["calibration_version"] != geometry["camera"]["calibration_version"]
    ):
        raise ValueError("online preview has foreign packet, asset or camera provenance")
    if preview["status"] != "DERIVED":
        return None
    e = packet["estimate"]
    if e["status"] != "OBSERVED":
        raise ValueError("online preview is missing an independent registered pose")
    center = np.asarray(e["object_center_world_m"])
    rot = np.asarray(e["rotation_to_world"]).reshape(3, 3)
    tcp = center + rot @ np.asarray(geometry["object_to_tcp"]).reshape(4, 4)[:3, 3]
    equal_point(
        preview["object_center_world_m"], center, "online object center differs from pixel pose"
    )
    equal_point(
        preview["rotation_object_to_world"],
        e["rotation_to_world"],
        "online object rotation differs",
    )
    equal_point(
        preview["grasp_tcp_world_m"], tcp, "online grasp differs from the independent object TCP"
    )
    return float(1000 * np.linalg.norm(tcp - preview["grasp_tcp_world_m"]))


def preview_counterfactuals(preview, packet, geometry, state, episode):
    valid = check_preview(preview, packet, geometry, episode)
    if valid is None:
        return None
    estimate = packet["estimate"]
    rotation = np.asarray(estimate["rotation_to_world"]).reshape(3, 3)
    marker = np.asarray(estimate["marker_center_world_m"])
    contact = np.asarray(geometry["object_to_tcp"]).reshape(4, 4)[:3, 3]
    true_center = np.asarray(state["object_geom_position_m"])
    truth_rotation = np.asarray(state["object_geom_rotation_row_major"]).reshape(3, 3)
    truth_tcp = true_center + truth_rotation @ contact
    true_top = true_center + truth_rotation[:, 2] * state["object_half_extent_m"][2]
    actual = np.asarray(preview["grasp_tcp_world_m"])
    side = np.asarray(geometry["marker_to_object"]).reshape(4, 4)[:3, 3]
    wrong = np.array([0.1, 0.0, side[2]]) if side[0] == 0 else np.array([0.0, 0.1, side[2]])
    alternative = marker - rotation @ wrong + rotation @ contact
    controls = {}
    for name, target in (
        ("marker_center_as_grasp", marker),
        ("wrong_attachment_as_grasp", alternative),
    ):
        try:
            check_preview(
                {**preview, "grasp_tcp_world_m": target.tolist()}, packet, geometry, episode
            )
        except ValueError as exc:
            if "grasp" not in str(exc):
                raise
            controls[name] = {
                "rejected": True,
                "error_to_true_grasp_mm": float(1000 * np.linalg.norm(target - truth_tcp)),
            }
        else:
            raise ValueError("incorrect target passed the independent registered grasp check")
    default = packet["default"]
    default_errors = None
    if default["status"] == "OBSERVED" and default["ids"] == [7]:
        default_center = np.asarray(default["object_center_world_m"])
        default_tcp = (
            default_center + np.asarray(default["rotation_to_world"]).reshape(3, 3) @ contact
        )
        default_errors = {
            "center_mm": float(1000 * np.linalg.norm(default_center - true_center)),
            "top_mm": float(1000 * np.linalg.norm(default["object_top_center_world_m"] - true_top)),
            "grasp_mm": float(1000 * np.linalg.norm(default_tcp - truth_tcp)),
        }
    return {
        "frame_id": packet["frame_id"],
        "online_grasp_error_mm": float(1000 * np.linalg.norm(actual - truth_tcp)),
        "online_center_error_mm": float(
            1000 * np.linalg.norm(preview["object_center_world_m"] - true_center)
        ),
        "online_top_error_mm": float(
            1000 * np.linalg.norm(estimate["object_top_center_world_m"] - true_top)
        ),
        "comparison_to_default_corner_model_mm": default_errors,
        "negative_controls": controls,
    }


def online_geometry(run, audit, packets, geometry, episode, states):
    by_role = {r["label"]: r for r in packets.values() if r["label"].endswith("/servo_reference")}
    stages = {s["skill"]: s for s in run["actions"]}
    previews, feedback, errors, handoff = [], 0, [], None
    controls = {}
    for row in audit:
        if "requirements" in row and "preview" in row:
            preview = row["preview"]
            if preview["track"] is None:
                if preview["status"] == "DERIVED":
                    raise ValueError("online registered pose lacks source tracker")
                continue
            source = packets[preview["track"]["observation_id"]]
            error = check_preview(preview, source, geometry, episode)
            if error is not None:
                previews.append(error)
                if source["frame_id"] not in controls:
                    controls[source["frame_id"]] = preview_counterfactuals(
                        preview, source, geometry, states[source["physics_step"]], episode
                    )
        if row.get("phase") != "servo":
            continue
        skill = row["skill"]
        s = stages[skill]
        if len(row["visual_samples"]) != s["feedback_accepted"]:
            raise ValueError("servo visual records differ from accepted count")
        if not row["visual_samples"]:
            continue
        origin = next(
            r["target_pose"]
            for r in audit
            if r.get("phase") == "PRE"
            and r.get("frame_id") == s["pre"]["frame_id"]
            and "shield" in r
            and r["step_id"] == f"step-{1 + list(stages).index(skill)}"
        )
        fixed = np.array([origin[k] for k in "xyz"])
        ref = packets[by_role[skill + "/servo_reference"]["frame_id"]]
        for sample in row["visual_samples"]:
            f = packets[sample["observation_id"]]
            if (
                f["label"] != skill + "/feedback"
                or f["checksum_sha256"] != sample["checksum_sha256"]
                or f["captured_at"] != sample["captured_at"]
                or f["sim_time_s"] != sample["sim_time_s"]
                or sample["camera_to_world"] != geometry["camera"]["camera_to_world"]
                or sample["calibration_version"] != geometry["camera"]["calibration_version"]
                or sample["ground_truth_used_for_control"] is not False
                or sample["target_source"] != "CURRENT_REGISTERED_MARKER_DEVELOPMENT_ESTIMATE"
                or f["servo_grasp_world_m"] is None
            ):
                raise ValueError("accepted servo feedback differs from independent RGB-D packet")
            target = [sample["target_pose"][k] for k in "xyz"]
            expected = None
            if skill in ("MOVE_ABOVE", "APPROACH"):
                expected = fixed + np.subtract(f["servo_grasp_world_m"], ref["servo_grasp_world_m"])
            if skill in ("LIFT", "RETREAT"):
                expected = fixed
            if expected is not None:
                equal_point(
                    target,
                    expected,
                    "commanded endpoint differs from original skill and pixel grasp",
                )
                errors.append(float(1000 * np.linalg.norm(expected - target)))
            feedback += 1
    if reference := run.get("dispatch_reference"):
        packet = packets[reference["frame_id"]]
        if (
            packet["checksum_sha256"] != reference["checksum_sha256"]
            or packet["label"] != "registration-handoff"
        ):
            raise ValueError("dispatch handoff differs from retained RGB-D frame")
        grasp = packet["servo_grasp_world_m"]
        if grasp is not None:
            color = np.array([reference["top_grasp_tcp_m"][k] for k in "xyz"])
            handoff = {
                "color_bootstrap_to_pixel_grasp_mm": float(1000 * np.linalg.norm(color - grasp)),
                "color_bootstrap_to_marker_center_mm": float(
                    1000 * np.linalg.norm(color - packet["estimate"]["marker_center_world_m"])
                ),
            }
    return {
        "registered_pre_or_post_poses": len(previews),
        "max_registered_pose_tcp_residual_mm": max(previews, default=None),
        "unique_registered_preview_frames": len(controls),
        "true_grasp_checks": list(controls.values()),
        "accepted_servo_packets": feedback,
        "numeric_servo_endpoints_checked": len(errors),
        "max_servo_endpoint_residual_mm": max(errors, default=None),
        "dispatch_reference": handoff,
    }


def stage_admission(stage, name):
    check = stage.get(name)
    if check is None:
        return None
    return {
        "frame_id": check["frame_id"],
        "conditions": check["conditions"],
        "shield_allowed": check["shield"]["allowed"],
        "shield_unmodified": check["shield"]["unmodified"],
        "shield_decision": check["shield"]["result"]["decision"],
    }


def frame_measurements(packets, states, geometry):
    out = {}
    for packet in packets:
        estimate = packet["estimate"]
        out[packet["frame_id"]] = {
            **{
                k: packet[k]
                for k in (
                    "frame_id",
                    "checksum_sha256",
                    "physics_step",
                    "label",
                    "sim_time_s",
                    "captured_at",
                )
            },
            **residuals(packet, states[packet["physics_step"]], geometry),
            "id7": estimate["ids"] == [7],
            "pose_reason": estimate["reason"],
            "depth_patches": packet["subpix_depth_patches"],
            "optical_depth_m": estimate["marker_center_optical_depth_m"],
            "default_observed": packet["default"]["status"] == "OBSERVED",
            "servo_usable": packet["servo_grasp_world_m"] is not None,
            "servo_reason": packet["servo_reason"],
        }
    return out


def phase_details(run, measures, by_stage, clock, stop):
    stages, details = {}, {}
    for s in run["actions"]:
        skill = s["skill"]
        rows = [measures[f] for f in by_stage[skill]]
        info = {
            "recorded_status": s["status"],
            **phase_sampling(s, [r["physics_step"] for r in rows]),
            "dispatched": s.get("executor_entered") is True,
            "dispatch_requested": s.get("dispatched") is True,
            "return_evidence": s.get("return_evidence"),
            "pre": stage_admission(s, "pre"),
            "post": stage_admission(s, "post"),
            "shield": clock[skill],
            "stop": stop if stop and stop.get("skill") == skill else None,
            "servo_terminal_reason": s.get("servo_terminal_reason"),
        }
        if skill not in PHASES:
            stages[skill] = info
            continue
        times = [datetime.fromisoformat(r["captured_at"]) for r in rows]
        if times != sorted(times):
            raise ValueError("captured order differs from stage consumption")
        wall_gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:], strict=False)]
        detail = {
            **info,
            "acquired_for_this_stage": sum(r["label"].startswith(skill + "/") for r in rows),
            "roles": dict(
                Counter(
                    r["label"].split("/", 1)[1]
                    for r in run["frame_roles"]
                    if r["label"].startswith(skill + "/")
                )
            ),
            "first_capture_utc": times[0].isoformat() if times else None,
            "last_capture_utc": times[-1].isoformat() if times else None,
            "max_gap_wall_s": max(wall_gaps, default=None),
            "visibility": pixel_summary(rows),
        }
        details[skill] = detail
        stages[skill] = info
    return stages, details


def checked_batch(private, public):
    plan = pinned(public / "plan.json", PLAN_SHA)
    path = public / "trial-allocation.public.json"
    h = sha(path)
    batch = pinned(private / "trials/allocation.json", h)
    if (
        batch["schema"] != "g1.development.marker-mount.paired-allocation.v1"
        or batch["plan_sha256"] != PLAN_SHA
        or sha(public / "plan.md") != plan["plan_md_sha256"]
        or sha(public / "selection.public.json") != batch["selection_sha256"]
        or batch["baseline"] != plan["baseline"]
        or batch["attempts_per_slot"] != 1
        or len(batch["cases"]) != len(plan["slots"])
        or len(plan["slots"]) != 8
    ):
        raise ValueError("foreign batch, selection, plan or denominator")
    mounts = {m["id"]: m for m in plan["mounts"]}
    for i, (row, slot) in enumerate(zip(batch["cases"], plan["slots"], strict=True), 1):
        mount = mounts["original" if slot["arm"] == "original" else batch["selected_mount"]]
        if (
            any(row[k] != v for k, v in slot.items())
            or row["slot"] != i
            or row["allocation_file"] != row["id"] + "/allocation.json"
            or (row["family"], row["mount"], row["asset_sha256"], row["asset_path"])
            != (mount["family"], mount["id"], mount["asset_sha256"], mount["asset_path"])
        ):
            raise ValueError("case order, registered slot or installation differs from G1 plan")
        a = pinned(private / "trials" / row["allocation_file"], row["allocation_sha256"])
        g = blind.checked_geometry(a["geometry"])
        if (
            g["marker_family"] != mount["family"]
            or g["pose_marker"]["marked_asset_sha256"] != row["asset_sha256"]
            or np.asarray(g["marker_to_object"]).reshape(4, 4)[:3, 3].tolist()
            != mount["object_T_marker_translation_m"]
            or a["asset_sha256"] != row["asset_sha256"]
            or a["case"]["visual_stages_in_order"] != plan["stage_order"]
            or a["selection_sha256"] != batch["selection_sha256"]
            or a["runtime_build_sha256"] != batch["runtime_build_sha256"]
            or any(a["case"][k] != v for k, v in slot.items())
        ):
            raise ValueError(
                "private case geometry, SHA or eight intentions differ from allocation"
            )
    return batch, h


def pixels(private, batch):
    inputs = private / "scoring-blind-input"
    out = private / "scoring-blind-output"
    inputs.mkdir()
    mapping, bundles = {}, {}
    for case in batch["cases"]:
        alloc = private / "trials" / case["allocation_file"]
        raw = alloc.parent / "instance"
        if not (raw / "acquisition-seal.json").exists():
            continue
        a = pinned(alloc, case["allocation_sha256"])
        token, bundle = pack_case(inputs, raw, case["allocation_sha256"], a["geometry"])
        bundles[token] = bundle
        mapping[raw] = token
    write(inputs / "index.json", bundles)
    blind_process(inputs / "index.json", out, private / "scoring-pixel-process.json")
    for raw, token in mapping.items():
        join_packet_sources(raw, token, out)


def first_feedback_refusal(run, audit, packets):
    stop = run.get("stop")
    if (
        not stop
        or stop["phase"] != "CONTROLLER"
        or stop["reason"] != "controller: VISUAL_SERVO_REJECTED"
    ):
        return None
    skill = stop["skill"]
    stage = next(s for s in run["actions"] if s["skill"] == skill)
    events = [r for r in audit if r.get("phase") == "servo" and r["skill"] == skill]
    if len(events) != 1:
        raise ValueError("missing or duplicate raw servo sample audit")
    accepted = events[0]["visual_samples"]
    frames = [p for p in packets.values() if p["label"] == skill + "/feedback"]
    for pixel, measured in zip(frames[: len(accepted)], accepted, strict=True):
        if (pixel["frame_id"], pixel["checksum_sha256"]) != (
            measured["observation_id"],
            measured["checksum_sha256"],
        ):
            raise ValueError("actual accepted servo sample is not the original feedback packet")
    if len(frames) not in (len(accepted), len(accepted) + 1):
        raise ValueError(
            "feedback stream contains multiple unidentified samples after last acceptance"
        )
    pre = packets[stage["pre"]["frame_id"]]
    (terminal,) = [p for p in packets.values() if p["label"] == "terminal"]
    if (
        pre["checksum_sha256"] != stage["pre"]["checksum_sha256"]
        or terminal["physics_step"] != stop["physics_step"]
    ):
        raise ValueError("wrong PRE handoff or terminal capture for stopped action")
    rejected = frames[-1] if len(frames) > len(accepted) else None
    if rejected is not None and (
        rejected["physics_step"] != stop["physics_step"]
        or rejected["frame_id"] == terminal["frame_id"]
    ):
        raise ValueError("rejected feedback is not a distinct observation at original stop step")

    def describe(packet):
        if packet is None:
            return None
        estimate = packet["estimate"]
        return {
            **{
                k: packet[k]
                for k in (
                    "frame_id",
                    "checksum_sha256",
                    "label",
                    "physics_step",
                    "sim_time_s",
                    "captured_at",
                )
            },
            "subpix_ids": estimate["ids"],
            "subpix_status": estimate["status"],
            "subpix_reason": estimate["reason"],
            "positive_optical_depth_patches": packet["subpix_depth_patches"],
            "marker_optical_depth_m": estimate["marker_center_optical_depth_m"],
            "grasp_usable": packet["servo_grasp_world_m"] is not None,
        }

    return {
        "actual_servo_terminal_reason": stage.get("servo_terminal_reason"),
        "pre_admission_source": describe(pre),
        "previous_accepted_feedback": describe(frames[len(accepted) - 1]) if accepted else None,
        "rejected_feedback": describe(rejected),
        "separate_terminal_capture": describe(terminal),
    }


def score_core(case, alloc, raw):
    base, errors_m = proposal_scoring.read_case(case, alloc, raw)
    a = pinned(alloc, case["allocation_sha256"])
    g = blind.checked_geometry(a["geometry"])
    sign = read(raw / "decision-seal.json")
    seal = pinned(raw / "acquisition-seal.json", sign["acquisition_sha256"])
    rows = pinned(raw / "decisions.json", sign["sha256"])["decisions"]
    run = pinned(raw / "run.json", seal["run_sha256"])
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
    states = {r["physics_step"]: r for r in truth["samples"]}
    packets = {r["frame_id"]: r for r in rows}
    measures = frame_measurements(rows, states, g)
    by_stage = role_sources(
        run["frame_roles"], rows, a["case"]["visual_stages_in_order"], base["episode"]
    )
    clocks = check_clocks(run, audit, packets, base["episode"])
    actions, phases = phase_details(run, measures, by_stage, clocks, run.get("stop"))
    commands = command_readback(run["actions"], audit, base["episode"])
    checked_geometry = online_geometry(run, audit, packets, g, base["episode"], states)
    interventions = sum(
        phase["interventions"] for action in clocks.values() for phase in action.values()
    )
    if base["online_success"] and interventions:
        raise ValueError("successful online result includes a Shield intervention")
    vis = pixel_summary(list(measures.values()))
    if (
        vis["frames"] != base["coverage"]["acquired"]
        or vis["pose_valid"] != len(errors_m)
        or (
            errors_m
            and not math.isclose(
                vis["top_p90_mm"],
                base["coverage"]["conditional_top_center_p90_mm"],
                rel_tol=1e-12,
                abs_tol=1e-10,
            )
        )
    ):
        raise ValueError("standalone 3D residual disagrees with registered proposal scorer")
    safe = run.get("safe_stop")
    if safe is not None and not (
        safe["success"] and safe["state_after"]["estop_engaged"] and safe["state_after"]["stopped"]
    ):
        raise ValueError("terminal safe stop was not acknowledged in robot state")
    outcome = base["independent_physical_outcome"].copy()
    outcome["self_collision_pairs_checked"] = len(outcome.pop("self_collision_checked_pairs"))
    outcome["safety_events"] = list(outcome["safety_events"])
    both_windows = all(
        w["status"] == "COMPLETE" and w["qualified"] for w in base["windows"].values()
    )
    for name, expected in (("lift", 121), ("release", 241)):
        window = base["windows"][name]
        if window["status"] == "COMPLETE" and window["actual_samples"] != expected:
            raise ValueError("incorrect independent physical dwell length")
    if base["physical_success"] != (outcome["success"] and both_windows):
        raise ValueError("physical task outcome differs from complete registered windows")
    case_report = {
        **{
            k: base[k]
            for k in (
                "acquired",
                "episode",
                "actual_physics_steps",
                "physics_samples",
                "verified_posts",
                "dispatched_actions",
                "online_success",
                "physical_success",
                "joint_success",
                "windows",
                "stage_status",
            )
        },
        "independent_physical_outcome": outcome,
        "both_windows_qualified": both_windows,
        "visibility": vis,
        "online_pixel_binding": checked_geometry,
        "safety": {
            "shield_interventions": interventions,
            "engaged_terminal_estop": safe is not None,
            "assessment_during_observed_steps": outcome["safety_assessment"],
            "events": outcome["safety_events"],
            "first_step": 0,
            "last_step": max(states),
        },
        "stop": run.get("stop"),
        "stop_kind": base["stop"]["kind"],
        "first_feedback_refusal": first_feedback_refusal(run, audit, packets),
        "originals": {
            **seal,
            "acquisition_sha256": sign["acquisition_sha256"],
            "decisions_sha256": sign["sha256"],
            "blind_set_sha256": sign["blind_set_sha256"],
        },
        "actions": {
            name: {
                k: info[k]
                for k in (
                    "recorded_status",
                    "entered_step",
                    "dispatch_step",
                    "backend_return_step",
                    "action_end_step",
                )
            }
            for name, info in actions.items()
        },
    }
    evidence = {
        "frames": list(measures.values()),
        "frame_ids_by_action": by_stage,
        "role_ledger": run["frame_roles"],
        "stages": actions,
        "commands": commands,
    }
    return case_report, phases, evidence


def check_blind_join(raw, output):
    sign = read(raw / "decision-seal.json")
    blind_seal = pinned(output / "seal.json", sign["blind_seal_sha256"])
    acquisition = pinned(raw / "acquisition-seal.json", sign["acquisition_sha256"])
    token = acquisition["index_sha256"]
    src = pinned(raw / "pixel-index.json", token)
    decision = pinned(raw / "decisions.json", sign["sha256"])
    if (
        blind_seal["decisions_sha256"][token] != sign["blind_set_sha256"]
        or decision["index_sha256"] != token
    ):
        raise ValueError("unblinded estimates do not belong to original blind seal")
    independent = pinned(output / (token + ".json"), sign["blind_set_sha256"])
    if independent["token"] != token or any(
        actual != {**original, **pixel}
        or any(
            original[k] != pixel[k]
            for k in ("physics_step", "checksum_sha256", "frame_id", "file_sha256")
        )
        for original, pixel, actual in zip(
            src["frames"], independent["packets"], decision["decisions"], strict=True
        )
    ):
        raise ValueError("post-seal role join changed pixel decisions")
    filenames = {r["file"] for r in src["frames"]}
    actual = {p.relative_to(raw).as_posix() for p in (raw / "frames").iterdir() if p.is_file()}
    if actual != filenames or len(filenames) != len(src["frames"]):
        raise ValueError("missing, duplicate or unindexed acquisition packet")


def aggregate_phase(rows, phases, samples):
    out = {}
    for arm in ARMS:
        cases = [r for r in rows if r["arm"] == arm]
        out[arm] = {}
        for name in PHASES:
            known = [phases[r["id"]][name] for r in cases if r["acquired"]]
            frames = [p for r in cases if r["acquired"] for p in samples[r["id"]][name]]
            out[arm][name] = {
                "allocated": len(cases),
                "unacquired": len(cases) - len(known),
                "not_reached": sum(s["sampling"] == "NOT_REACHED" for s in known),
                "entered": sum(s["entered_step"] is not None for s in known),
                "pre_observed": sum(s["pre"] is not None for s in known),
                "actually_dispatched": sum(s["dispatched"] for s in known),
                "controller_return": sum(s["controller_return_recorded"] for s in known),
                "return_success": sum(
                    bool((s["return_evidence"] or {}).get("success")) for s in known
                ),
                "post_observed": sum(s["post"] is not None for s in known),
                "passed": sum(s["recorded_status"] == "PASS" for s in known),
                "sampling_patterns": dict(Counter(s["sampling"] for s in known)),
                "distinct_episode_frames": pixel_summary(frames),
            }
    return out


def score(private, public, batch, batch_sha, directory):
    from scripts.graduation.g1_mount_trials import captured_evidence

    directory.mkdir()
    rows, phases, phase_samples, frames_by_arm = [], {}, {}, {a: [] for a in ARMS}
    packets, jobs, leases, episodes = set(), set(), set(), set()
    last_worker_release = None
    detail_files = {}
    for case in batch["cases"]:
        alloc = private / "trials" / case["allocation_file"]
        raw = alloc.parent / "instance"
        basic = {
            k: case[k]
            for k in (
                "id",
                "arm",
                "slot",
                "mount",
                "family",
                "group",
                "seed",
                "yaw_rad",
                "reset_fixture_center_m",
                "allocation_sha256",
            )
        }
        if not (raw / "acquisition-seal.json").is_file() or not (raw / "receipt.json").is_file():
            rows.append(
                {
                    **basic,
                    "acquired": False,
                    "status": "UNKNOWN_ACQUISITION",
                    "started": (raw / "started.json").exists(),
                    "interrupted": (raw / "interrupted.json").exists(),
                }
            )
            phases[case["id"]] = {name: {"sampling": "UNKNOWN_ACQUISITION"} for name in PHASES}
            continue
        a = pinned(alloc, case["allocation_sha256"])
        rec = read(raw / "receipt.json")
        verified = captured_evidence(raw, case, a)
        if rec["batch_sha256"] != batch_sha or any(rec[k] != val for k, val in verified.items()):
            raise ValueError("native acquisition differs from original case receipt")
        clock = verified["worker"]
        start = pinned(raw / "started.json", verified["started_sha256"])
        if (
            start["slot"] != case["slot"]
            or start["case"] != case["id"]
            or start["attempt"] != 1
            or start["batch_sha256"] != batch_sha
            or start["allocation_sha256"] != case["allocation_sha256"]
            or (last_worker_release is not None and clock["acquired_at"] <= last_worker_release)
        ):
            raise ValueError("case chronology, source or real allocation order differs")
        last_worker_release = clock["released_at"]
        check_blind_join(raw, private / "scoring-blind-output")
        result, per_phase, detailed = score_core(case, alloc, raw)
        ids = {r["frame_id"] for r in detailed["frames"]}
        if (
            ids & packets
            or clock["job_id"] in jobs
            or clock["lease_id"] in leases
            or result["episode"] in episodes
            or result["episode"] != verified["physical_reset"]["episode_id"]
        ):
            raise ValueError("foreign or repeated frame, reset, episode, worker job or lease")
        packets.update(ids)
        episodes.add(result["episode"])
        jobs.add(clock["job_id"])
        leases.add(clock["lease_id"])
        if result["dispatched_actions"] != len(verified["action_commands"]):
            raise ValueError("registered scorer and raw executor readback disagree")
        rows.append(
            {
                **basic,
                **result,
                "job_id": clock["job_id"],
                "sqlite_sha256": clock["sqlite_sha256"],
                "receipt_sha256": sha(raw / "receipt.json"),
            }
        )
        phases[case["id"]] = per_phase
        frames_by_arm[case["arm"]].extend(detailed["frames"])
        measurements = {r["frame_id"]: r for r in detailed["frames"]}
        phase_samples[case["id"]] = {
            name: [measurements[key] for key in detailed["frame_ids_by_action"][name]]
            for name in PHASES
        }
        evidence = directory / (case["id"] + ".json")
        write(evidence, detailed)
        detail_files[evidence.name] = sha(evidence)
    by_arm = {}
    paired = {}
    for metric in METRICS:
        rates, paired[metric] = outcomes(rows, metric)
        for arm in ARMS:
            by_arm.setdefault(arm, {})[metric] = rates[arm]
    for arm in ARMS:
        known = [r for r in rows if r["arm"] == arm and r["acquired"]]
        by_arm[arm].update(
            {
                "acquired": len(known),
                "visibility": pixel_summary(frames_by_arm[arm]),
                "with_shield_intervention": sum(
                    r["safety"]["shield_interventions"] > 0 for r in known
                ),
                "terminal_estops": sum(r["safety"]["engaged_terminal_estop"] for r in known),
                "observed_physical_safety": dict(
                    Counter(r["safety"]["assessment_during_observed_steps"] for r in known)
                ),
            }
        )
    common = {
        "plan_sha256": PLAN_SHA,
        "allocation_sha256": batch_sha,
        "selection_sha256": batch["selection_sha256"],
        "blind_output_seal_sha256": sha(private / "scoring-blind-output/seal.json"),
        "analysis_unit": (
            "four reset placements per arm, paired by group; no rerenders or T5 packets"
        ),
        "scope": "PAIRED_DEVELOPMENT_EPISODES",
        "formal_claims": 0,
        "formal_simulations": 0,
        "hardware_actions": 0,
        "task_model_calls": 0,
    }
    return {
        **common,
        "schema": "g1.marker-mount.paired-results.v1",
        "by_arm": by_arm,
        "paired": paired,
        "cases": rows,
        "physical_definition": (
            "Independent dense evaluator success and qualified complete 121-sample "
            "LIFT and 241-sample RELEASE windows."
        ),
        "online_definition": (
            "Eight registered skills with PRE, actual dispatch, controller RETURN and "
            "POST, passing conditions and unmodified Shield."
        ),
        "joint_definition": (
            "Online and independent physical success with scoped safety through "
            "observed physics steps."
        ),
        "error_definition": (
            "3-D Euclidean error to the true object top center on unique SUBPIX ID7 "
            "poses with five positive depth patches. Quantiles pool valid packets "
            "within arm."
        ),
    }, {
        **common,
        "schema": "g1.marker-mount.online-phase-visibility.v1",
        "by_arm": aggregate_phase(rows, phases, phase_samples),
        "cases": phases,
        "denominator": (
            "Within a skill, unique RGB-D frame IDs consumed by any of its actual "
            "roles. Boundary packets can belong to adjacent skills. Separate "
            "same-step acquisitions retain distinct identities."
        ),
        "sampling": (
            "Controller endpoint coverage uses dispatch through backend return or "
            "recorded stop. Dwell samples after return contribute separately to "
            "whole-stage visibility. Missing stage ratios and quantiles are null."
        ),
        "private_detail_sha256": detail_files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pixels", "score", "verify"))
    parser.add_argument("private", type=Path)
    parser.add_argument("public", type=Path)
    args = parser.parse_args()
    private, public = args.private.resolve(), args.public.resolve()
    batch, digest = checked_batch(private, public)
    started = datetime.now(UTC).isoformat()
    if args.mode == "pixels":
        pixels(private, batch)
    else:
        paired = public / "paired-results.public.json"
        phases = public / "phase-visibility.public.json"
        if args.mode == "verify":
            inputs = private / "scoring-blind-input/index.json"
            repeat = private / "scoring-blind-repeat"
            blind_process(inputs, repeat, private / "scoring-pixel-repeat-process.json")
            if read(repeat / "seal.json") != read(private / "scoring-blind-output/seal.json"):
                raise ValueError("independent pixel decisions differ on second read")
        results, visibility = score(
            private, public, batch, digest, private / ("scoring-" + args.mode + "-details")
        )
        if args.mode == "score":
            write(paired, results)
            write(phases, visibility)
        else:
            if results != read(paired) or visibility != read(phases):
                raise ValueError(
                    "second whole-task or phase readback differs from published results"
                )
            receipts = {
                r["id"]: {
                    **r["originals"],
                    "receipt_sha256": r["receipt_sha256"],
                    "sqlite_sha256": r["sqlite_sha256"],
                }
                for r in results["cases"]
                if r["acquired"]
            }
            write(
                public / "scoring-verification.public.json",
                {
                    "schema": "g1.marker-mount.independent-score-verification.v1",
                    "plan_sha256": PLAN_SHA,
                    "allocation_sha256": digest,
                    "paired_results_sha256": sha(paired),
                    "phase_visibility_sha256": sha(phases),
                    "input_placements": 4,
                    "retained_slots": len(batch["cases"]),
                    "repeated_cases": len(receipts),
                    "repeat_blind_seal_sha256": sha(repeat / "seal.json"),
                    "independently_read_unique_packets": read(repeat / "seal.json")["packet_count"],
                    "repeated_private_detail_sha256": visibility["private_detail_sha256"],
                    "by_case": receipts,
                    "scorer_sha256": sha(Path(__file__)),
                    "reader_sha256": sha(Path(blind.__file__)),
                    "original_scorer_sha256": sha(Path(proposal_scoring.__file__)),
                    "pixel_process_receipt_sha256": sha(private / "scoring-pixel-process.json"),
                    "repeat_pixel_process_receipt_sha256": sha(
                        private / "scoring-pixel-repeat-process.json"
                    ),
                    "formal_claims": 0,
                    "formal_simulations": 0,
                },
            )
    write(
        private / ("scoring-invocation-" + args.mode + ".json"),
        {
            "mode": args.mode,
            "argv": [sys.executable, *sys.argv],
            "started_utc": started,
            "finished_utc": datetime.now(UTC).isoformat(),
            "source_root": str(ROOT),
            "module_files": {
                str(Path(module.__file__).resolve()): sha(Path(module.__file__))
                for module in (sys.modules[__name__], blind, proposal_scoring)
            },
        },
    )


if __name__ == "__main__":
    main()
