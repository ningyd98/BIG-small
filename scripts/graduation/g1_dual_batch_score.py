"""Join independent RGB-D measurements with commands and physics from eight development slots."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from scripts.graduation import dynamic_vision_score as vision
from scripts.graduation import g1_mount_score as mount
from scripts.graduation import proposal_scoring as physics
from scripts.graduation.guarded_clock_score import stop_cause
from scripts.graduation.perception_io import pinned, read, sha, write

PLAN = "85666eed1724a2c2280690de8ec55d35fe79b3d636982e35dd366d48e6534885"
ARMS = ("original", "dual")
KEYS = ("file_sha256", "checksum_sha256", "physics_step", "frame_id")
LABELS = ("none", "only7", "only8", "both")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def contact_counts(records, supports):
    counts = Counter()
    contacts = Counter()
    first_steps = {}
    final_pairs = []
    fingers = {"left_finger_geom", "right_finger_geom"}
    for index, record in enumerate(records):
        cube, support, other = set(), set(), set()
        for geom1, geom2 in sorted({tuple(sorted(p)) for p in record["contact_pairs"]}):
            pair = {geom1, geom2}
            if pair & supports or ("object_geom" in pair and pair & fingers):
                label = geom1 + "/" + geom2
                contacts[label] += 1
                first_steps.setdefault(label, record.get("physics_step", index))
                if index == len(records) - 1:
                    final_pairs.append(label)
            if "object_geom" in pair:
                cube |= pair & fingers
            if pair & supports:
                support |= fingers & pair
                other |= pair - supports - fingers
        counts["left_finger_cube_steps"] += "left_finger_geom" in cube
        counts["right_finger_cube_steps"] += "right_finger_geom" in cube
        counts["bilateral_cube_steps"] += cube == fingers
        counts["any_finger_support_steps"] += bool(support)
        counts["support_contact_without_bilateral_cube_steps"] += bool(support) and cube != fingers
        counts["support_with_other_geom_steps"] += bool(other)
    return {
        **counts,
        "physics_samples": len(records),
        "support_geoms": sorted(supports),
        "pair_step_counts": dict(contacts),
        "first_contact_step": first_steps,
        "terminal_structural_or_cube_finger_contacts": final_pairs,
    }


def quantile90(values):
    return float(np.quantile(values, 0.9)) if values else None


def coverage(rows):
    valid = [r for r in rows if r["usable"]]
    classes = {(): "none", (7,): "only7", (8,): "only8", (7, 8): "both"}
    patterns = {k: [] for k in LABELS}
    for row in rows:
        patterns[classes[tuple(sorted(row["usable_ids"]))]].append(row)
    return {
        "frames": len(rows),
        "usable": len(valid),
        "fraction": len(valid) / len(rows) if rows else None,
        "top_p90_mm": quantile90([r["top_error_mm"] for r in valid]),
        "individual_marker": {
            i: {
                "observed_frames": sum(int(i) in r["observed_ids"] for r in rows),
                "valid_frames": sum(i in r["per_id"] for r in rows),
                "top_p90_mm": quantile90(
                    [r["per_id"][i]["top_error_mm"] for r in rows if i in r["per_id"]]
                ),
                "selected_frames": sum(r["selected_id"] == int(i) for r in valid),
            }
            for i in ("7", "8")
        },
        "usable_marker_combinations": {
            k: {
                "frames": len(items),
                "selected_frames": sum(r["usable"] for r in items),
                "top_p90_mm": quantile90([r["top_error_mm"] for r in items if r["usable"]]),
            }
            for k, items in patterns.items()
        },
        "rejections": dict(Counter(r["reason"] for r in rows if not r["usable"])),
    }


def source_package(private, public):
    plan = pinned(public / "plan.json", PLAN)
    require(sha(public / "plan.md") == plan["plan_md_sha256"], "changed Astra plan")
    raw = private / "trials"
    batch_sha = sha(public / "trial-allocation.public.json")
    batch = pinned(raw / "allocation.json", batch_sha)
    acquisition = pinned(raw / "acquisition.json", sha(public / "trial-acquisition.public.json"))
    require(
        batch["plan_sha256"] == PLAN
        and batch["baseline"] == plan["baseline"]
        and batch["selection_sha256"] == sha(public / "refusal-decision.public.json")
        and batch["gate"]["cross_readback_sha256"] == sha(public / "cross-readback.public.json")
        and batch["runtime_build_sha256"] == sha(public / "runtime-build.public.json")
        and batch["attempts_per_slot"] == 1
        and acquisition["allocation_sha256"] == batch_sha
        and len(batch["cases"]) == len(acquisition["cases"]) == 8,
        "unsealed allocation or acquisition",
    )
    cases = []
    for spec, row, observed in zip(
        plan["slots"], batch["cases"], acquisition["cases"], strict=True
    ):
        require(
            all(row[k] == v for k, v in spec.items())
            and row["id"] == observed["id"]
            and row["allocation_file"] == row["id"] + "/allocation.json",
            "crossed case",
        )
        alloc = pinned(raw / row["allocation_file"], row["allocation_sha256"])
        require(
            all(alloc["case"][k] == v for k, v in spec.items())
            and alloc["case"]["visual_stages_in_order"] == plan["stage_order"]
            and alloc["case"]["visual_seed"] == row["seed"]
            and alloc["asset_sha256"] == row["asset_sha256"]
            and alloc["geometry"] == batch["geometries"][row["family"]],
            "allocation geometry or seed mismatch",
        )
        cases.append((row, alloc, observed, raw / row["id"] / "instance"))
    return plan, batch_sha, cases


def package(cases, folder):
    folder.mkdir()
    bundles = {}
    for row, allocation, observed, raw in cases:
        if not observed["acquired"]:
            continue
        token = read(raw / "acquisition-seal.json")["index_sha256"]
        index = pinned(raw / "pixel-index.json", token)
        require(
            index["allocation_sha256"] == row["allocation_sha256"] and token not in bundles,
            "foreign pixels",
        )
        dest = folder / token
        dest.mkdir()
        frames = []
        for i, source in enumerate(index["frames"]):
            name = f"{i:04d}.json"
            require(
                source["file"] == "frames/" + name
                and sha(raw / source["file"]) == source["file_sha256"],
                "unsealed original RGB-D packet",
            )
            os.link(raw / source["file"], dest / name)
            frames.append({"file": name, **{k: source[k] for k in KEYS}})
        bundles[token] = {
            "episode": index["episode"],
            "scene": index["scene"],
            "mode": row["arm"],
            "geometry": allocation["geometry"],
            "frames": frames,
        }
    index_path = folder / "index.json"
    write(index_path, bundles)
    return index_path


def blind_reader(tree, index, output):
    program = Path(__file__).resolve().with_name("g1_dual_pixel_readback.py")
    args = [sys.executable, str(program), str(index), sha(index), str(output)]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(tree), str(tree / "src")]))
    result = subprocess.run(args, cwd=tree, env=env, capture_output=True, text=True)
    write(
        output.with_suffix(".process.json"),
        {
            "argv": args,
            "cwd": str(tree),
            "input_sha256": sha(index),
            "reader_sha256": sha(program),
            "status": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode:
        raise RuntimeError(f"blind worker exited {result.returncode} ({output.name})")
    return pinned(output / "seal.json", sha(output / "seal.json"))


def pixel_errors(packets, sources, states):
    joined = {}
    for pixel, source in zip(packets, sources, strict=True):
        require(
            all(pixel[k] == source[k] for k in KEYS) and source["frame_id"] not in joined,
            "blind observation differs from original step, file, identity or checksum",
        )
        s = states[source["physics_step"]]
        actual = s["object_geom_position_m"]
        vertical = np.array(s["object_geom_rotation_row_major"]).reshape(3, 3)[:, 2]
        top = actual + vertical * s["object_half_extent_m"][2]

        def distance(point, truth_top=top):
            return float(1000 * np.linalg.norm(np.subtract(truth_top, point)))

        per_id = {
            i: {**m, "top_error_mm": distance(m["top_m"])} for i, m in pixel["per_id"].items()
        }
        joined[source["frame_id"]] = {
            **source,
            **pixel,
            "sim_time_s": pixel["time"],
            "per_id": per_id,
            "top_error_mm": distance(pixel["top_m"]) if pixel["usable"] else None,
        }
    return joined


def online_targets(run, audit, frames, geometry, fetch):
    from cloud_edge_robot_arm.research.native_collection_grounding import (
        bootstrap_collection_tracker,
    )
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    stages = {s["skill"]: s for s in run["actions"]}
    roles = {r["label"]: r["frame_id"] for r in run["frame_roles"]}
    tracker, targets, previews = None, [], []
    for row in audit:
        preview = row.get("preview")
        if preview and (track := preview["track"]) is not None:
            source = frames[track["observation_id"]]
            require(
                track["observation_checksum_sha256"] == source["checksum_sha256"]
                and track["camera_to_world"] == geometry["camera"]["camera_to_world"]
                and track["calibration_version"] == geometry["camera"]["calibration_version"]
                and track["asset_sha256"] == geometry["pose_marker"]["marked_asset_sha256"]
                and track["marker_family_id"] == geometry["marker_family"],
                "online preview foreign RGB-D, asset or camera",
            )
            if preview["status"] == "DERIVED":
                selected = source["per_id"][str(source["selected_id"])]
                estimate = track["geometry"]["marker_estimate"]
                require(
                    estimate["observed_marker_ids"] == source["observed_ids"]
                    and estimate["observation_id"] == source["frame_id"]
                    and estimate["observation_checksum_sha256"] == source["checksum_sha256"],
                    "online pose refers to a different decoded marker or source",
                )
                mount.equal_point(
                    preview["object_center_world_m"], selected["center_m"], "wrong preview centre"
                )
                mount.equal_point(
                    preview["grasp_tcp_world_m"], selected["tcp_m"], "wrong registered grasp"
                )
                previews.append(
                    float(
                        1000
                        * np.linalg.norm(
                            np.subtract(selected["tcp_m"], preview["grasp_tcp_world_m"])
                        )
                    )
                )
        if row.get("phase") != "servo":
            continue
        skill = row["skill"]
        stage = stages[skill]
        accepted = row["visual_samples"]
        require(len(accepted) == stage.get("feedback_accepted", 0), "missing accepted servo record")
        if not accepted:
            continue
        command = next(
            r["target_pose"]
            for r in audit
            if r.get("phase") == "PRE"
            and "shield" in r
            and r.get("frame_id") == stage["pre"]["frame_id"]
            and r["step_id"] == f"step-{1 + list(stages).index(skill)}"
        )
        initial = np.array([command[k] for k in "xyz"])
        ref = frames[roles[skill + "/servo_reference"]]
        if skill in {"MOVE_TO_REGION", "PLACE"}:
            if tracker is None:
                tracker, _ = bootstrap_collection_tracker(fetch(roles["color_reference"]), geometry)
            region, _ = measure_servo_region(fetch(ref["frame_id"]), tracker)
            require(region is not None, "missing measured reference region")
        for sample in accepted:
            f = frames[sample["observation_id"]]
            require(
                f["label"] == skill + "/feedback"
                and sample["ground_truth_used_for_control"] is False
                and sample["target_source"] == "CURRENT_REGISTERED_MARKER_DEVELOPMENT_ESTIMATE"
                and sample["calibration_version"] == geometry["camera"]["calibration_version"]
                and sample["camera_to_world"] == geometry["camera"]["camera_to_world"]
                and all(f[k] == sample[k] for k in ("checksum_sha256", "captured_at", "sim_time_s"))
                and f["usable"],
                "accepted servo frame identity or vision binding differs",
            )
            if "development_dual" in geometry:
                chosen = sample["development_dual_marker"]
                require(
                    chosen["frame_id"] == f["frame_id"]
                    and chosen["checksum"] == f["checksum_sha256"]
                    and chosen["asset_sha256"] == geometry["pose_marker"]["marked_asset_sha256"]
                    and chosen["registration_id"] == geometry["registration_id"]
                    and all(
                        chosen[k] == f[k] for k in ("selected_id", "observed_ids", "usable_ids")
                    ),
                    "online marker arbitration differs from independent RGB-D measurement",
                )
                mount.equal_point(chosen["grasp_world_m"], f["tcp_m"], "wrong recorded servo grasp")
            expected = initial.copy()
            if skill in {"MOVE_ABOVE", "APPROACH"}:
                expected += np.subtract(f["tcp_m"], ref["tcp_m"])
            elif skill in {"MOVE_TO_REGION", "PLACE"}:
                now, _ = measure_servo_region(fetch(f["frame_id"]), tracker)
                require(now is not None, "missing live destination from raw pixels")
                expected += np.subtract(now["center"], region["center"])
            target = [sample["target_pose"][k] for k in "xyz"]
            mount.equal_point(
                target, expected, "servo endpoint differs from the current RGB-D and intent"
            )
            targets.append(float(1000 * np.linalg.norm(expected - target)))
    return {
        "checked_preview_poses": len(previews),
        "max_preview_residual_mm": max(previews, default=None),
        "checked_servo_endpoints": len(targets),
        "max_servo_residual_mm": max(targets, default=None),
    }


def score_case(case, allocation, observed, raw, tree, output, blind_seal):
    header = {
        k: case[k]
        for k in (
            "id",
            "group",
            "arm",
            "seed",
            "reset_fixture_center_m",
            "yaw_rad",
            "slot",
            "asset_sha256",
            "allocation_sha256",
        )
    }
    if not observed["acquired"]:
        pinned(raw / "interrupted.json", observed["interruption_sha256"])
        return {**header, "acquired": False, "interruption": observed["interrupted"]}, {}, []
    receipt = pinned(raw / "receipt.json", observed["receipt_sha256"])
    seal = pinned(raw / "acquisition-seal.json", receipt["capture_sha256"])
    tok = seal["index_sha256"]
    index = pinned(raw / "pixel-index.json", tok)
    truth = pinned(raw / "offline-truth.json", seal["truth_sha256"])
    run = pinned(raw / "run.json", seal["run_sha256"])
    audit = pinned(raw / "online-audit.json", seal["audit_sha256"])
    require(
        index["allocation_sha256"]
        == truth["allocation_sha256"]
        == receipt["allocation_sha256"]
        == case["allocation_sha256"]
        and index["episode"] == truth["episode"] == receipt["physical_reset"]["episode_id"]
        and index["scene"] == "S01_NORMAL_STATIC",
        "foreign real run",
    )
    states = vision.checked_steps(
        truth["samples"], index["episode"], case["asset_sha256"], truth["asset_sha256"]
    )
    yaw = case["yaw_rad"]
    s, c = math.sin(yaw), math.cos(yaw)
    mount.equal_point(
        states[0]["object_geom_position_m"],
        case["reset_fixture_center_m"],
        "wrong independent reset",
    )
    mount.equal_point(
        states[0]["object_geom_rotation_row_major"],
        [c, -s, 0, s, c, 0, 0, 0, 1],
        "wrong independent rotation",
    )
    episode = index["episode"]
    geometry = allocation["geometry"]
    require(
        index["frames"][0]["physics_step"] == 0
        and index["frames"][-1]["physics_step"] == max(states),
        "reset or terminal endpoint absent",
    )
    packets = pinned(output / (tok + ".json"), blind_seal["packets"][tok])
    frames = pixel_errors(packets, index["frames"], states)
    stages = run["actions"]
    order = allocation["case"]["visual_stages_in_order"]
    require(
        [r["skill"] for r in stages] == order, "registered eight intents differ from original run"
    )
    by_stage = mount.role_sources(run["frame_roles"], list(frames.values()), order, episode)
    clocks = mount.check_clocks(run, audit, frames, episode)
    commands = mount.command_readback(stages, audit, episode)
    require(
        commands == receipt["action_commands"]
        and receipt["actual_physics_steps"] == max(states)
        and receipt["captured_frames"] == len(frames),
        "measured commands, steps or frames differ from receipt",
    )
    physics.check_audit(stages, audit)
    passed = physics.score_admissions(stages, {k: r["checksum_sha256"] for k, r in frames.items()})
    lease = run["lease_summary"]
    require(lease["attempt"] == 1 and lease["lease_released"] is True, "unreleased or repeated run")
    online = passed == len(order) and "stop" not in run and lease["final_job_status"] == "SUCCEEDED"
    samples = [
        physics.sample_physical_observation(physics.PhysicsStepObservation(**r), physics.CRITERIA)
        for r in truth["samples"]
    ]
    outcome = physics.evaluate_evidence(samples, physics.CRITERIA)
    outcome_record = json.loads(json.dumps(asdict(outcome), allow_nan=False))
    wins = physics.registered_windows(samples, {s["skill"]: s for s in stages})
    both = all(item["qualified"] for item in wins.values())
    phys = outcome.success and both
    require(
        observed["registered_windows"] == wins
        and observed["independent_physical_outcome"] == outcome_record,
        "acquisition audit and independent physics readback differ",
    )
    xml = tree / case["asset_path"]
    require(sha(xml) == case["asset_sha256"], "foreign physical asset")
    obj = ElementTree.parse(xml).find(".//body[@name='object']")
    supports = {
        g.attrib["name"]
        for g in obj.findall("geom")
        if g.get("name") != "object_geom"
        and (int(g.get("contype", 1)) or int(g.get("conaffinity", 1)))
    }
    contacts = contact_counts(truth["samples"], supports)

    def fetch(frame_id):
        return vision.frame_from_row(raw, frames[frame_id], episode, index["scene"], geometry)

    targets = online_targets(run, audit, frames, geometry, fetch)
    phases = {
        s["skill"]: {
            "status": s["status"],
            "entered_step": s.get("entered_step"),
            "end_step": s.get("end_step"),
            "feedback_accepted": s.get("feedback_accepted"),
            "dispatched": bool(s.get("executor_entered")),
            "servo_terminal_reason": s.get("servo_terminal_reason"),
            "clock": clocks[s["skill"]],
            "sampling": mount.phase_sampling(
                s, [frames[f]["physics_step"] for f in by_stage[s["skill"]]]
            ),
            "pixels": coverage([frames[f] for f in by_stage[s["skill"]]]),
        }
        for s in stages
    }
    stop = run.get("stop", {})
    terminal = None
    if stop and stop.get("skill") in order:
        skill = stop["skill"]
        feedback = [p for p in frames.values() if p["label"] == skill + "/feedback"]
        n = phases[skill]["feedback_accepted"]
        if n is not None and len(feedback) == n + 1:
            f = feedback[-1]
            require(
                f["physics_step"] == stop["physics_step"],
                "final feedback and controller stop differ",
            )
            terminal = {
                k: f[k]
                for k in (
                    "frame_id",
                    "checksum_sha256",
                    "physics_step",
                    "usable",
                    "reason",
                    "selected_id",
                    "observed_ids",
                    "usable_ids",
                )
            }
    summary = {
        **header,
        "acquired": True,
        "episode": episode,
        "capture_seal_sha256": sha(raw / "acquisition-seal.json"),
        "truth_sha256": seal["truth_sha256"],
        "original_receipt_sha256": observed["receipt_sha256"],
        "blind_set_sha256": blind_seal["packets"][tok],
        "physics_steps": max(states),
        "dense_samples": len(samples),
        "frames": len(frames),
        "dispatched": len(commands),
        "accepted_joint_targets": sum(
            r["accepted_command_types"].get("joint_target", 0) for r in commands
        ),
        "verified_posts": passed,
        "stop": stop_cause(run, audit),
        "first_unaccepted_feedback": terminal,
        "safe_stop_succeeded": run.get("safe_stop", {}).get("success"),
        "phases": phases,
        "contacts": contacts,
        "registered_windows": wins,
        "independent_physical_outcome": outcome_record,
        "online_success": online,
        "physical_success": phys,
        "both_windows_qualified": both,
        "joint_success": online and phys and outcome.safety_assessment == "SCOPED_NO_VIOLATION",
        "target_readback": targets,
        "overall_pixels": coverage(list(frames.values())),
    }
    per_stage = {skill: [frames[f] for f in ids] for skill, ids in by_stage.items()}
    return summary, per_stage, list(frames.values())


def rate_summary(rows):
    # Original paired estimator names its experimental arm "selected".
    def names(obj):
        if isinstance(obj, dict):
            return {("dual" if k == "selected" else k): names(v) for k, v in obj.items()}
        return obj

    compatible = [
        {**row, "arm": "selected" if row["arm"] == "dual" else "original"} for row in rows
    ]
    results = {}
    for metric in mount.METRICS:
        rates, paired = mount.outcomes(compatible, metric)
        results[metric] = {"by_arm": names(rates), "paired": names(paired)}
    return results


def score(source, tree, output, seal):
    plan, batch_sha, cases = source
    rows, by_arm = [], {a: {s: [] for s in ["all_frames", *plan["stage_order"]]} for a in ARMS}
    for spec, alloc, observed, raw in cases:
        observed_case, by_stage, frames = score_case(spec, alloc, observed, raw, tree, output, seal)
        rows.append(observed_case)
        group = by_arm[spec["arm"]]
        group["all_frames"].extend(frames)
        for skill, items in by_stage.items():
            group[skill].extend(items)
    common = {
        "plan_sha256": PLAN,
        "allocation_sha256": batch_sha,
        "raw_frame_count": seal["n_frames"],
        "attempts_per_allocated_slot": 1,
        "formal_claims": 0,
        "formal_simulations": 0,
    }
    paired = {
        **common,
        "schema": "g1.dual-marker.paired-development-outcomes.v1",
        "cases": rows,
        "metrics": rate_summary(rows),
    }
    visibility = {
        **common,
        "schema": "g1.dual-marker.stage-and-id-coverage.v1",
        "definition": (
            "Unique source acquisitions per stage, including logged role reuse. "
            "Each original packet is counted once in all_frames. "
            "Error is conditional on usable frames."
        ),
        "by_arm": {
            arm: {stage: coverage(items) for stage, items in groups.items()}
            for arm, groups in by_arm.items()
        },
    }
    return paired, visibility


def main(private, public):
    private, public = private.resolve(), public.resolve()
    tree = private / "runtime-source"
    source = source_package(private, public)
    folder = private / "scoring"
    folder.mkdir()
    index = package(source[2], folder / "packets")
    one, two = folder / "blind-one", folder / "blind-two"
    a, b = (blind_reader(tree, index, p) for p in (one, two))
    require(
        a == b
        and sha(one / "seal.json") == sha(two / "seal.json")
        and a["index_sha256"] == sha(index),
        "two independent pixel decoder processes disagree",
    )
    results = score(source, tree, one, a)
    require(
        results == score(source_package(private, public), tree, two, b),
        "independent score reread changed",
    )
    for name, obj in zip(
        ("paired-results.public.json", "live-visibility.public.json"), results, strict=True
    ):
        write(public / name, obj)
    write(
        public / "scoring-verification.public.json",
        {
            "plan_sha256": PLAN,
            "allocation_sha256": source[1],
            "acquisition_sha256": sha(public / "trial-acquisition.public.json"),
            "anonymous_index_sha256": sha(index),
            "identical_blind_seals_sha256": sha(one / "seal.json"),
            "matched_packets": a["n_frames"],
            "fresh_process_count": 2,
            "readbacks_equal": True,
            "blind_receipt_sha256": [sha(p.with_suffix(".process.json")) for p in (one, two)],
            "independent_score_source_sha256": sha(Path(__file__)),
            "blind_reader_source_sha256": sha(
                Path(__file__).with_name("g1_dual_pixel_readback.py")
            ),
            "result_sha256": {
                name: sha(public / name)
                for name in ("paired-results.public.json", "live-visibility.public.json")
            },
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("private", type=Path)
    cli.add_argument("public", type=Path)
    args = cli.parse_args()
    main(args.private, args.public)
