"""Align the measured d02 controller windows with the same RGB-D in paired pixel timings."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROUND = Path(__file__).resolve().parent.parent
REPO = next(p for p in ROUND.parents if (p / "pyproject.toml").exists())
D02 = (
    REPO
    / "experiments/results/g1-visibility-pose-repair-20261124"
    / "batches/train-current-grid-01/d02/instance"
)
BASE = "7288cdc81e830f5282eb7d82d49d46d077e2593d0f96480960385463b850b9e9"
CANDIDATE = "c3ca24cf1dc459651bd99dc85a997c36d39108c91d3cf7fb73d35e8071487261"


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(
        gzip.decompress(path.read_bytes()) if path.name.endswith(".gz") else path.read_bytes()
    )


def save(path, value):
    with path.open("x", encoding="utf8") as f:
        json.dump(value, f, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def stats(xs):
    ns = sorted(xs)
    if not ns:
        raise ValueError("empty timing group")

    def quantile(p):
        h = (len(ns) - 1) * p
        a, b = math.floor(h), math.ceil(h)
        return ns[a] + (ns[b] - ns[a]) * (h - a)

    return dict(n=len(ns), p50=quantile(0.50), p95=quantile(0.95), maximum=ns[-1], minimum=ns[0])


def elapsed_utc_ms(start, end):
    return 1000 * (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def native_windows():
    times = ROUND / "native-d02-baseline-times.public.json"
    run = D02 / "run.json"
    pixel_index = D02 / "pixel-index.json"
    audit = D02 / "online-audit.json"
    vision_file = D02 / "online-vision.json"
    table = load(times)
    allrows = load(run)
    idx = load(pixel_index)
    need(
        sha(run) == table["run_sha256"] and sha(audit) == table["source_sha256"],
        "native source digest",
    )
    plan = load(ROUND / "plan.json")["inputs_sha256"]
    for f in (run, pixel_index, audit, vision_file):
        need(sha(f) == plan[f.relative_to(REPO).as_posix()], "source not pinned by the round")
    times_by_step = {
        r["physics_step"]: 1000 * r["sample_and_ik_s"] for r in table["accepted_native_samples"]
    }
    failed = table["failed"]
    need(failed["physics_step"] == 672 and not failed["native_accepted"], "unexpected deadline row")
    times_by_step[672] = failed["time_ms_reported_to_6_decimals_s"]
    vis = load(vision_file)["frames"]
    frame_rows = [r for r in idx["frames"] if r["label"] == "MOVE_ABOVE/feedback"]
    all_roles = allrows["frame_roles"]
    roles = {
        q: {r["frame_id"]: r for r in all_roles if r["label"] == q}
        for q in ("MOVE_ABOVE/feedback", "MOVE_ABOVE/FEEDBACK_Shield")
    }
    need(
        len(frame_rows)
        == len(times_by_step)
        == len(roles["MOVE_ABOVE/feedback"])
        == len(roles["MOVE_ABOVE/FEEDBACK_Shield"])
        == 70,
        "expected 70 distinct native windows",
    )
    result = []
    for row in frame_rows:
        step, identity, digest = row["physics_step"], row["frame_id"], row["checksum_sha256"]
        acquire = roles["MOVE_ABOVE/feedback"][identity]
        shield = roles["MOVE_ABOVE/FEEDBACK_Shield"][identity]
        need(
            acquire["checksum_sha256"] == shield["checksum_sha256"] == digest
            and acquire["physics_step"] == shield["physics_step"] == step
            and acquire["captured_at"] == shield["captured_at"],
            "crossed packet, clock or step",
        )
        need(sha(D02 / row["file"]) == row["file_sha256"], "changed actual RGB-D packet")
        need(
            vis[identity]["callers"] == {"servo_measure": 1}
            and vis[identity]["measurement"]["checksum"] == digest,
            "not the single actual feedback pixel call",
        )
        native_ms = times_by_step[step]
        to_shield = 1000 * shield["elapsed_from_capture_start_s"]
        acq = elapsed_utc_ms(acquire["captured_at"], acquire["checked_at"])
        sensor_role_to_shield_role = elapsed_utc_ms(acquire["checked_at"], shield["checked_at"])
        other = native_ms - to_shield
        need(min(acq, sensor_role_to_shield_role, to_shield, other) > 0, "invalid duration")
        result.append(
            dict(
                file=Path(row["file"]).name,
                frame_id=identity,
                checksum_sha256=digest,
                file_sha256=row["file_sha256"],
                physics_step=step,
                usable_ids=vis[identity]["measurement"]["usable_ids"],
                original_native_window_ms=native_ms,
                original_capture_through_shield_ms=to_shield,
                original_sensor_start_to_validated_rgbd_role_ms=acq,
                original_rgbd_role_to_feedback_shield_role_ms=sensor_role_to_shield_role,
                original_capture_timer_minus_utc_roles_ms=to_shield
                - acq
                - sensor_role_to_shield_role,
                original_native_window_outside_capture_through_shield_ms=other,
            )
        )
    return dict(
        schema="g1.feedback.deadline.native-window-segments.v1",
        scope="original dynamic d02",
        sources_sha256={
            str(f.relative_to(REPO)): sha(f) for f in (times, run, pixel_index, audit, vision_file)
        },
        native_window=(
            "Actual controller sample_and_ik_s plus final rejection rounded to 0.001 milliseconds."
        ),
        capture_through_shield=(
            "Original perf_counter from feedback capture start through the FEEDBACK Shield "
            "role, before the trailing active check and IK."
        ),
        outer_remainder=(
            "Same window subtraction. Includes first active (owner and hard state), "
            "trailing active (owner and hard state), final target checks, native IK and "
            "surrounding Python work."
        ),
        wall_clock_roles=(
            "Actual UTC stamps recorded at MuJoCo camera start, after validated camera "
            "observation, and after the Shield. Acquisition includes rendering and RGB-D "
            "encoding/validation. The interval after acquisition includes provider, "
            "contract copies, Shield and intervening glue. The UTC role checks and "
            "monotonic timer have different endpoints."
        ),
        unsplit_native_stages=[
            "individual lease SQL and hard_state latency",
            "PNG versus Pydantic",
            "contract copy versus Shield",
            "target check versus inverse kinematics",
        ],
        counts=dict(real=70, accepted=69, exceeded=1),
        rows=result,
        statistics_ms={
            k: stats(r[k] for r in result) for k in result[0] if k.startswith("original_")
        },
    )


def budget(native, timings_file, native_file):
    timings = load(timings_file)
    sources = {(r["physics_step"], r["frame_id"], r["checksum_sha256"]): r for r in native["rows"]}
    result = []
    unique = set()
    groups = defaultdict(list)
    for row in timings["samples"]:
        if row["group"] not in ("cycle", "neighbors"):
            continue
        key = (row["physics_step"], row["frame_id"], row["checksum_sha256"])
        need(key in sources, "frame identity, checksum or physics step absent from actual feedback")
        seen = (row["group"], row["worker"], row["repetition"], *key)
        need(seen not in unique, "duplicate paired timing")
        unique.add(seen)
        prior = sources[key]
        need(Path(row["file"]).name == prior["file"], "packet file changed")
        need(
            set(row["order"]) == {"baseline", "candidate"}
            and len(row["order"]) == 2
            and row["baseline_ns"] > 0
            and row["candidate_ns"] > 0,
            "missing paired read",
        )
        old = row["baseline_ns"] / 1e6
        new = row["candidate_ns"] / 1e6
        expected = prior["original_native_window_ms"] + (new - old)
        out = dict(
            group=row["group"],
            worker=row["worker"],
            repetition=row["repetition"],
            order=row["order"],
            file=prior["file"],
            physics_step=key[0],
            frame_id=key[1],
            checksum_sha256=key[2],
            original_native_total_ms=prior["original_native_window_ms"],
            baseline_pixel_ms=old,
            candidate_pixel_ms=new,
            within_frame_pixel_delta_ms=new - old,
            estimated_candidate_total_ms=expected,
        )
        need(expected > 0, "paired estimate excludes more time than the native total")
        result.append(out)
        groups[row["group"]].append(out)
    need(
        len(groups["cycle"]) >= 350 and len(groups["neighbors"]) >= 60,
        "incomplete paired benchmark groups",
    )
    for step, count in Counter(r["physics_step"] for r in groups["cycle"]).items():
        need(
            count >= 5 and step in {r["physics_step"] for r in native["rows"]},
            "expected five repeat cycles per frame",
        )
    need(len(set(r["physics_step"] for r in groups["cycle"])) == 70, "not all 70 dynamic frames")
    per_neighbor = Counter(r["physics_step"] for r in groups["neighbors"])
    need(
        set(per_neighbor) == {664, 672} and min(per_neighbor.values()) >= 30,
        "thirty neighbors repetitions required",
    )
    groups["all"] = result
    groups["0073_all"] = [r for r in result if r["physics_step"] == 672]
    summary = {}
    for label, rows in groups.items():
        a = stats(r["estimated_candidate_total_ms"] for r in rows)
        summary[label] = dict(
            estimated_candidate_total_ms=a,
            baseline_pixel_ms=stats(r["baseline_pixel_ms"] for r in rows),
            candidate_pixel_ms=stats(r["candidate_pixel_ms"] for r in rows),
            maximum_row=max(rows, key=lambda r: r["estimated_candidate_total_ms"]),
            within_budget=a["p95"] <= 80 and a["maximum"] <= 90,
        )
    return dict(
        schema="g1.feedback.deadline.paired-d02-window-budget.v1",
        scope="offline candidate estimate paired to 70 original controller samples",
        baseline_generation=BASE,
        candidate_generation=CANDIDATE,
        native_segments_sha256=sha(native_file),
        pixels_sha256=sha(timings_file),
        instrument_sha256=sha(Path(__file__)),
        method=(
            "Each original sample/IK total is adjusted by the independently timed "
            "candidate-minus-baseline pixel duration for that exact immutable packet, "
            "paired within the same repetition. Quantiles are taken only after per-sample "
            "arithmetic. The same original dynamic sample is reused across timing "
            "replicates."
        ),
        assumptions=(
            "The isolated pixel timing measures the component changed by this candidate. "
            "Nonpixel and live scheduling costs are held at that frame's original value. "
            "Native candidate timings and a new physical motion remain unmeasured here."
        ),
        time_limits_ms={"estimated_p95": 80, "estimated_max": 90, "production_deadline": 100},
        quantiles=(
            "Linear empirical quantile, ordered rank (n-1)*p. Untrimmed samples. Cycle, "
            "neighbors and combined bounds retained."
        ),
        eligible_by_estimate=all(s["within_budget"] for s in summary.values()),
        summary=summary,
        rows=result,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["native", "budget"])
    p.add_argument("output", type=Path)
    p.add_argument("--native", type=Path)
    p.add_argument("--timings", type=Path)
    a = p.parse_args()
    native = native_windows()
    if a.phase == "native":
        data = native
    else:
        need(
            a.native and a.timings and load(a.native) == native, "sealed native inputs are required"
        )
        data = budget(native, a.timings, a.native)
    save(a.output, data)
    print(
        json.dumps(
            {
                "output_sha256": sha(a.output),
                "eligible_by_estimate": data.get("eligible_by_estimate"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
