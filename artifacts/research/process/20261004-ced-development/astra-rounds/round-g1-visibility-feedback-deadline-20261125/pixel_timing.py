"""Alternate the immutable d02 pixels under both observer versions in independent processes.

Run using the project interpreter with -B, passing the worktree and a new output directory.
"""

import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import PIL
import pydantic

PRIVATE = Path("experiments/results/g1-visibility-pose-repair-20261124")
TRIAL = PRIVATE / "batches/train-current-grid-01/d02"
GENERATION = "7288cdc81e830f5282eb7d82d49d46d077e2593d0f96480960385463b850b9e9"
DETECTOR_PATH = Path("scripts/graduation")
BASE_GRID = "facd7520b48c7f7ba82024973507f8e8775913179e35fe5ea8332da4e3648a47"
NEW_GRID = "dba9b870fb73c92b1a19af78b203ccf816c26573d86e3938af4c21f445b0f6fa"
VISION = "2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_sources(repo):
    base = repo / PRIVATE / "builds" / GENERATION / "runtime-source"
    actual = {}
    for name, root, grid_sha in (("baseline", base, BASE_GRID), ("candidate", repo, NEW_GRID)):
        files = {
            p: sha((root / DETECTOR_PATH / p).read_bytes())
            for p in ("g1_visibility_grid.py", "g1_visibility_vision.py")
        }
        if files != {"g1_visibility_grid.py": grid_sha, "g1_visibility_vision.py": VISION}:
            raise ValueError(f"unexpected {name} measurement source")
        actual[name] = files
    return base, actual


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def readers(repo):
    # Both readers use the original runtime's immutable RGB-D validation and PoseMarkerEstimate.
    base, _ = verify_sources(repo)
    sys.path[:0] = [str(base), str(base / "src")]
    from scripts.graduation import g1_visibility_vision as baseline

    key = "scripts.graduation.g1_visibility_grid"
    original = sys.modules[key]
    try:
        sys.modules[key] = module("candidate_grid", repo / DETECTOR_PATH / "g1_visibility_grid.py")
        candidate = module("candidate_vision", repo / DETECTOR_PATH / "g1_visibility_vision.py")
    finally:
        sys.modules[key] = original
    return {"baseline": baseline.measure_frame, "candidate": candidate.measure_frame}


def input_frames(repo):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    archive = repo / TRIAL / "instance"
    geometry = json.loads((archive.parent / "allocation.json").read_bytes())["geometry"]
    index = json.loads((archive / "pixel-index.json").read_bytes())["frames"]
    run = json.loads((archive / "run.json").read_bytes())
    by_id = {row["frame_id"]: row for row in index}
    feedback = [
        by_id[row["frame_id"]] for row in run["action_clock_contexts"] if row["phase"] == "FEEDBACK"
    ]
    if len(feedback) != 70 or len({r["frame_id"] for r in feedback}) != 70:
        raise ValueError("the historical batch must have 70 distinct feedbacks")
    frames = {}
    for row in feedback:
        raw = (archive / row["file"]).read_bytes()
        if sha(raw) != row["file_sha256"]:
            raise ValueError("historical frame file digest differs")
        frame = RGBDObservation.model_validate_json(raw)
        if frame.frame_id != row["frame_id"] or frame.checksum_sha256 != row["checksum_sha256"]:
            raise ValueError("unbound historical frame")
        frames[frame.frame_id] = frame
    if [x["file"] for x in feedback[-2:]] != ["frames/0072.json", "frames/0073.json"]:
        raise ValueError("incorrect neighboring feedbacks")
    return feedback, frames, geometry


def one_worker(repo, worker):
    methods = readers(repo)
    feedback, frames, geometry = input_frames(repo)
    samples = []

    def pair(row, group, rep):
        frame = frames[row["frame_id"]]
        order = list(methods) if (worker + len(samples)) % 2 == 0 else list(methods)[::-1]
        times, outputs = {}, {}
        for name in order:
            started = time.perf_counter_ns()
            value = methods[name](frame, geometry)
            times[name + "_ns"] = time.perf_counter_ns() - started
            outputs[name] = sha(canonical(value))
        if len(set(outputs.values())) != 1:
            raise ValueError(f"non-identical current-frame measurement at {row['file']}")
        samples.append(
            dict(
                worker=worker,
                group=group,
                repetition=rep,
                order=order,
                file=Path(row["file"]).name,
                frame_id=frame.frame_id,
                checksum_sha256=frame.checksum_sha256,
                physics_step=row["physics_step"],
                measurement_sha256=outputs["baseline"],
                **times,
            )
        )

    for row in feedback:
        pair(row, "cycle", worker)
    for rep in range(6):
        for row in feedback[-2:]:
            pair(row, "neighbors", worker * 6 + rep)
    return dict(pid=os.getpid(), load_average=os.getloadavg(), samples=samples)


def quantiles(values):
    return {
        name: float(np.quantile(values, q)) / 1e6
        for name, q in (("p50_ms", 0.50), ("p95_ms", 0.95), ("max_ms", 1))
    }


def statistics(rows):
    result = {"n_per_version": len(rows)}
    for version in ("baseline", "candidate"):
        result[version] = quantiles([r[version + "_ns"] for r in rows])
        worst = max(rows, key=lambda r: r[version + "_ns"])
        result[version]["slowest"] = {
            field: worst[field]
            for field in ("physics_step", "file", "worker", "repetition", "frame_id")
        }
    return result


def hotspots(repo):
    methods = readers(repo)
    feedback, frames, geometry = input_frames(repo)
    reports = {}
    for version, measure in methods.items():
        observer = measure.__globals__
        grid = observer["find_grids"].__globals__
        timings, counts = Counter(), Counter()

        def instrument(namespace, key, timings=timings, counts=counts):
            original = namespace[key]

            def timed(*args, **kwargs):
                started = time.perf_counter_ns()
                value = original(*args, **kwargs)
                elapsed = time.perf_counter_ns() - started
                timings[key] += elapsed
                counts[key] += 1
                if key == "_verify":
                    counts[f"scalar_id_{args[1]}"] += 1
                if key == "_weak_grid_cells":
                    counts["batched_seeds"] += len(args[2])
                    counts["batched_proven_negative"] += len(value)
                if key == "_accept":
                    timings[f"{key}/{args[2]}"] += elapsed
                    counts[f"seeds/{args[2]}"] += len(args[1])
                if key == "_seeds":
                    counts["sampled_hypotheses"] += len(args[0])
                return value

            namespace[key] = timed

        for key in (
            "_seeds",
            "_verify",
            "_weak_grid_cells",
            "_island_seeds",
            "_crossings",
            "_accept",
            "_sample",
        ):
            if key in grid:
                instrument(grid, key)
        instrument(observer, "find_grids")
        instrument(observer, "_plane")
        # Warm both the dictionary descriptors and the immutable sampling geometry.
        for row in feedback[-2:]:
            measure(frames[row["frame_id"]], geometry)
        for row in feedback[-2:]:
            timings.clear()
            counts.clear()
            started = time.perf_counter_ns()
            value = measure(frames[row["frame_id"]], geometry)
            elapsed = time.perf_counter_ns() - started
            reports.setdefault(row["file"], {})[version] = dict(
                observed_ids=value["observed_ids"],
                measurement_sha256=sha(canonical(value)),
                instrumented_total_ms=elapsed / 1e6,
                calls=dict(counts),
                inclusive_ms={k: v / 1e6 for k, v in timings.items()},
            )
    return reports


def main():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("repo", type=Path)
    args.add_argument("output", type=Path)
    args.add_argument("--worker", type=int)
    parsed = args.parse_args()
    repo = parsed.repo.resolve()
    if parsed.worker is not None:
        print(canonical(one_worker(repo, parsed.worker)).decode())
        return
    base, sources = verify_sources(repo)
    parsed.output.mkdir(exist_ok=True)
    sample_file = parsed.output / "pixel-timing-samples.public.json.gz"
    summary_file = parsed.output / "pixel-timing-summary.public.json"
    if sample_file.exists() or summary_file.exists():
        raise FileExistsError("select a fresh measurement output")
    process_results = []
    with (repo / PRIVATE / "feedback-deadline-performance.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for worker in range(5):
            call = [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                str(repo),
                str(parsed.output),
                "--worker",
                str(worker),
            ]
            process = subprocess.run(call, check=True, capture_output=True, text=True)
            process_results.append(json.loads(process.stdout))
        slow_components = hotspots(repo)
        if verify_sources(repo)[1] != sources:
            raise ValueError("source changed during measurement")
    samples = [x for process in process_results for x in process["samples"]]
    cycle = [x for x in samples if x["group"] == "cycle"]
    cold = [process["samples"][0] for process in process_results]
    neighbors = [x for x in samples if x["group"] == "neighbors"]
    groups = {
        "ordered_feedbacks_including_first_call": statistics(cycle),
        "first_call_after_import_per_process": statistics(cold),
        "ordered_feedbacks_after_first_call": statistics([r for r in cycle if r not in cold]),
        "repeated_step_664": statistics([r for r in neighbors if r["physics_step"] == 664]),
        "repeated_step_672": statistics([r for r in neighbors if r["physics_step"] == 672]),
    }
    with sample_file.open("xb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as gz:
            gz.write(canonical({"samples": samples}) + b"\n")
    summary = dict(
        schema="g1.visibility.deadline.paired-pixel-timing.v1",
        runtime_build=base.parent.name,
        input=f"{TRIAL.as_posix()}/instance/pixel-index.json",
        input_sha256=sha((repo / TRIAL / "instance/pixel-index.json").read_bytes()),
        script_sha256=sha(Path(__file__).read_bytes()),
        sources=sources,
        samples_sha256=sha(sample_file.read_bytes()),
        groups=groups,
        observed_slow_frame_components=slow_components,
        component_times="Separate instrumented passes. Component times are inclusive and overlap.",
        measurements_match=len(samples),
        measured="One measure_frame call on a validated full input, including the observer's own "
        "validation, PNG/depth decode, full-image search, metric fit and arbitration. "
        "First call follows process imports. Disk I/O and output hashing are outside timing.",
        environment=dict(
            python=sys.version,
            executable=sys.executable,
            numpy=np.__version__,
            cv2=cv2.__version__,
            opencv_threads=cv2.getNumThreads(),
            pillow=PIL.__version__,
            pydantic=pydantic.__version__,
            platform=platform.platform(),
            cpu_affinity=sorted(os.sched_getaffinity(0)),
            processor=platform.processor(),
            timer=time.get_clock_info("perf_counter").implementation,
        ),
        workers=[{k: v for k, v in r.items() if k != "samples"} for r in process_results],
    )
    with summary_file.open("x") as stream:
        json.dump(summary, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(groups, sort_keys=True))


if __name__ == "__main__":
    main()
