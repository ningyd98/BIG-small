"""Join controller feedback, pixel measurements and same-step states for the eight formal stops."""

from __future__ import annotations

import argparse
import gzip
import json
import math
from collections import Counter
from itertools import pairwise
from pathlib import Path

from scripts.graduation.g1_mount_score import check_clocks
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
FORMAL = ROUNDS / "round-g1-formal-paired-20261124"
ROUND = ROUNDS / "round-g1-formal-failure-observation-20261124"
RAW = ROOT / "experiments/results/g1-formal-paired-20261124"
PLAN_SHA = "31d5db8c1fea5aa9bdccdef8a2ccceac66dabaa5382ad5488ca2d6bc2d5f4767"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_index(rows, key):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"repeated {key}")
    return result


def require_same(left, right, fields):
    require(all(left[k] == right[k] for k in fields), f"foreign source or clock: {fields}")


def last_feedback_pair(feedback, terminal, stop, frozen_refusal):
    before, refused = feedback[-2:]
    require(
        before["accepted"]
        and not refused["accepted"]
        and not refused["usable"]
        and sum(not f["accepted"] for f in feedback) == 1
        and before["skill"] == refused["skill"] == stop["skill"]
        and before["physics_step"] + 8 == refused["physics_step"] == stop["physics_step"]
        and terminal["physics_step"] == stop["physics_step"]
        and len({before["frame_id"], refused["frame_id"], terminal["frame_id"]}) == 3,
        "last accepted, first refused and separate terminal must bind to their actual identities",
    )
    require_same(
        refused,
        frozen_refusal,
        ("frame_id", "checksum_sha256", "physics_step", "reason", "usable_ids"),
    )
    return before, refused


def summarize_states(states, first, last):
    window = [states[i] for i in range(first, last + 1)]
    return {
        "first_step": first,
        "last_step": last,
        "state_samples_inclusive": len(window),
        "elapsed_simulated_ms": 1000 * (window[-1]["sim_time_s"] - window[0]["sim_time_s"]),
        "tcp_travel_mm": 1000
        * sum(math.dist(a["tcp_position_m"], b["tcp_position_m"]) for a, b in pairwise(window)),
        "object_max_displacement_mm_from_start": 1000
        * max(
            math.dist(r["object_geom_position_m"], window[0]["object_geom_position_m"])
            for r in window
        ),
        "finger_range_m": [
            [min(v), max(v)] for v in zip(*(r["finger_positions_m"] for r in window), strict=True)
        ],
    }


def pixel_span(rows):
    spans = []
    for row in rows:
        pattern = (row["skill"], row["usable_ids"], row["usable"])
        if spans and (spans[-1]["skill"], spans[-1]["usable_ids"], spans[-1]["usable"]) == pattern:
            spans[-1]["last_step"] = row["physics_step"]
            spans[-1]["consumed_frames"] += 1
        else:
            spans.append(
                {
                    "skill": row["skill"],
                    "usable_ids": row["usable_ids"],
                    "usable": row["usable"],
                    "first_step": row["physics_step"],
                    "last_step": row["physics_step"],
                    "consumed_frames": 1,
                }
            )
    return spans


def case_timeline(allocation, score, pixels):
    case = allocation["id"]
    folder = RAW / "trials" / case / "instance"
    receipt = pinned(folder / "receipt.json", score["original_receipt_sha256"])
    seal = pinned(folder / "acquisition-seal.json", receipt["capture_sha256"])
    index = pinned(folder / "pixel-index.json", seal["index_sha256"])
    truth = pinned(folder / "offline-truth.json", seal["truth_sha256"])
    run = pinned(folder / "run.json", seal["run_sha256"])
    audit = pinned(folder / "online-audit.json", seal["audit_sha256"])
    episode = score["episode"]
    require(index["episode"] == truth["episode"] == episode, "foreign episode")
    require(index["scene"] == truth["scene"] == allocation["scene_id"], "foreign scene")
    require(
        index["allocation_sha256"] == truth["allocation_sha256"] == allocation["allocation_sha256"],
        "foreign allocation",
    )
    states = unique_index(truth["samples"], "physics_step")
    require(list(states) == list(range(1 + receipt["actual_physics_steps"])), "state gap")
    source = unique_index(index["frames"], "frame_id")
    roles = [r for r in run["frame_roles"] if r["acquired_for_this_role"]]
    require([r["frame_id"] for r in roles] == list(source), "capture order differs from runtime")
    for role in run["frame_roles"]:
        frame = source[role["frame_id"]]
        require_same(frame, role, ("physics_step", "checksum_sha256"))
        require(role["episode_id"] == episode, "foreign captured or reused role")
    clocks = unique_index(
        [c for c in run["action_clock_contexts"] if c["phase"] == "FEEDBACK"], "frame_id"
    )
    shields = unique_index(
        [r for r in audit if r.get("phase") == "FEEDBACK" and "shield" in r], "frame_id"
    )
    check_clocks(run, audit, source, episode)
    samples = unique_index(
        [
            {**s, "skill": r["skill"]}
            for r in audit
            if r.get("phase") == "servo"
            for s in r["visual_samples"]
        ],
        "observation_id",
    )
    require(
        list(samples) == list(clocks) == list(shields), "servo and Shield feedback order differs"
    )
    stages = unique_index(run["actions"], "skill")
    require(run["safe_stop"]["success"] and run["stop"] == receipt["stop"], "foreign safe stop")
    timeline = []
    for f in index["frames"]:
        ident, step = f["frame_id"], f["physics_step"]
        pix = pixels[ident]
        require_same(f, pix, ("frame_id", "checksum_sha256", "file_sha256", "physics_step"))
        require(pix["episode"] == states[step]["episode_id"] == episode, "foreign pixel or state")
        require(pix["mode"] == allocation["arm"], "foreign installation")
        if not f["label"].endswith("/feedback"):
            continue
        skill = f["label"].split("/")[0]
        measured = samples.get(ident)
        clock = clocks.get(ident)
        if measured is not None:
            require(
                measured["skill"] == skill and measured["checksum_sha256"] == f["checksum_sha256"],
                "foreign servo sample",
            )
            require(clock["skill"] == skill and clock["absolute"] == step, "wrong consuming step")
            require(
                clock["command_seq"] > 0
                and shields[ident]["shield"]["allowed"]
                and pix["usable"]
                and measured["target_pose"] == shields[ident]["target_pose"],
                "successful online target, offline pixels or Shield verdict differs",
            )
            if allocation["arm"] == "dual":
                require_same(
                    measured["development_dual_marker"],
                    pix,
                    ("observed_ids", "usable_ids", "selected_id"),
                )
        else:
            require(
                ident not in clocks and not pix["usable"],
                "unconsumed acceptance or missing online sample",
            )
        timeline.append(
            {
                "id": case,
                "episode": episode,
                "skill": skill,
                "accepted": measured is not None,
                **{
                    k: f[k]
                    for k in ("frame_id", "file", "file_sha256", "checksum_sha256", "physics_step")
                },
                **{
                    k: pix[k]
                    for k in ("usable", "reason", "observed_ids", "usable_ids", "selected_id")
                },
                "registered_action_command_seq": clock["command_seq"] if clock else None,
                "shield_step_id": clock["step_id"] if clock else None,
                "tcp_position_m": states[step]["tcp_position_m"],
                "object_center_m": states[step]["object_geom_position_m"],
            }
        )
    require(len(samples) == sum(r["accepted"] for r in timeline), "accepted frame missing")
    for skill in {r["skill"] for r in timeline}:
        stage_rows = [r for r in timeline if r["skill"] == skill]
        require(
            all(b["physics_step"] - a["physics_step"] == 8 for a, b in pairwise(stage_rows)),
            "feedback gap within action",
        )
        require(
            sum(r["accepted"] for r in stage_rows) == stages[skill]["feedback_accepted"],
            "wrong stage denominator",
        )
    (terminal,) = [r for r in index["frames"] if r["label"] == "terminal"]
    before, refused = last_feedback_pair(
        timeline, terminal, run["stop"], score["first_unaccepted_feedback"]
    )
    first, last = before["physics_step"], refused["physics_step"]
    require(
        not any(first < f["physics_step"] < last for f in source.values()),
        "uncounted intervening frame",
    )
    stage_rows = [r for r in timeline if r["skill"] == refused["skill"]]
    registered = [7, 8] if allocation["arm"] == "dual" else [7]
    first_change = next(r for r in timeline if (r["usable_ids"] != registered or not r["usable"]))
    anchors = {
        "first_accepted": next(r for r in timeline if r["accepted"]),
        "first_partial_or_refused": first_change,
        "middle_of_stopping_stage": stage_rows[len(stage_rows) // 2],
        "last_accepted": before,
        "first_refused": refused,
    }
    by_step = Counter(x["physics_step"] for x in source.values())
    summary = {
        "id": case,
        "slot": allocation["slot"],
        "arm": allocation["arm"],
        "group": allocation["group"],
        "object_mass_kg": allocation["physical_object_mass_kg"],
        "start_center_m": allocation["reset_fixture_center_m"],
        "yaw_rad": allocation["yaw_rad"],
        "seed": allocation["seed"],
        "episode": episode,
        "actual_stop": run["stop"],
        "captured_frames": len(source),
        "consumed_feedback": len(timeline),
        "accepted_feedback": len(samples),
        "refused_feedback": len(timeline) - len(samples),
        "capture_steps_with_multiple_frames": {str(s): n for s, n in by_step.items() if n > 1},
        "unmatched_capture_identities": 0,
        "unmatched_feedback_identities": 0,
        "same_step_terminal_frame": {
            k: terminal[k] for k in ("frame_id", "physics_step", "file_sha256")
        },
        "last_two_feedback_boundary_steps": [first, last],
        "intermediate_steps_without_camera": last - first - 1,
        "motion_between_feedback": summarize_states(states, first, last),
        "anchors": {
            role: {k: r[k] for k in ("frame_id", "physics_step", "usable", "usable_ids", "skill")}
            for role, r in anchors.items()
        },
        "runs_of_identical_feedback_pattern": pixel_span(timeline),
    }
    return summary, timeline


def main(pixels_file, output):
    require(not output.resolve().is_relative_to(RAW), "output overlaps frozen evidence")
    plan = pinned(ROUND / "plan.json", PLAN_SHA)

    def formal(name):
        path = FORMAL / (name + ".public.json")
        return pinned(path, plan["inputs_sha256"][str(path.relative_to(ROOT))])

    allocation, scores = formal("trial-allocation"), formal("paired-results")
    seal_file = pixels_file.parent / "pixels-seal.public.json"
    seal = read(seal_file)
    digest = sha(pixels_file)
    require(
        seal["plan_sha256"] == PLAN_SHA
        and seal["sealed_table_file"] == pixels_file.name
        and seal["sealed_table_sha256"] == digest
        and seal["worker_payload_sha256"] == [digest, digest]
        and len(set(seal["separate_pids"])) == 2
        and seal["identical_bytes"],
        "two sealed independent pixel reads are required for the timeline",
    )
    with gzip.open(pixels_file, "rt", encoding="utf8") as f:
        pixels = json.load(f)["frames"]
    summaries, rows = [], []
    for alloc, score in zip(allocation["cases"], scores["cases"], strict=True):
        require_same(alloc, score, ("slot", "id", "arm"))
        summary, feedback = case_timeline(alloc, score, pixels)
        summaries.append(summary)
        rows.extend(feedback)
    require(
        len(pixels) == sum(s["captured_frames"] for s in summaries) == 778,
        "incorrect capture population",
    )
    require(len({r["frame_id"] for r in rows}) == len(rows), "reused frame identity across trials")
    output.mkdir(parents=True, exist_ok=True)
    table = output / "feedback-timeline.public.json.gz"
    payload = {"schema": "g1.formal.failure.feedback.v1", "rows": rows}
    with table.open("xb") as out:
        out.write(
            gzip.compress(
                json.dumps(
                    payload, sort_keys=True, allow_nan=False, separators=(",", ":")
                ).encode(),
                mtime=0,
            )
        )
    write(
        output / "episode-timelines.public.json",
        {
            "schema": "g1.formal.failure.timelines.v1",
            "plan_sha256": PLAN_SHA,
            "pixel_prejoin_seal_sha256": sha(seal_file),
            "pixel_observations_sha256": digest,
            "feedback_table_sha256": sha(table),
            "captured_frames": len(pixels),
            "consumed_feedback_frames": len(rows),
            "accepted_feedback_frames": sum(r["accepted"] for r in rows),
            "terminal_captures": len(summaries),
            "simulated_physics_hz": 240,
            "per_action_feedback_interval_steps": 8,
            "first_partial_or_refused_definition": (
                "First consumed feedback with fewer locally valid markers than installed or an "
                "unusable fused estimate. Single-marker fallback is accepted when available."
            ),
            "cases": summaries,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pixels", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    main(args.pixels, args.output)
