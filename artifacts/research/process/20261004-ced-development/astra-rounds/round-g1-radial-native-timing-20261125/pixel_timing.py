"""Pair complete native-frame measurements across two frozen generations in five fresh workers."""

import argparse
import base64
import collections
import fcntl
import gzip
import importlib.util
import io
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import PIL
import pydantic
from PIL import Image
from pixel_seed_profile import DATA, FROZEN, GENERATION, ROUND, TRIAL, canonical, sha

GRID_PATH = "scripts/graduation/g1_visibility_grid.py"
VISION_PATH = "scripts/graduation/g1_visibility_vision.py"
SOURCES = {
    GRID_PATH: "c0e80c0b3b36ad397a4d26146e9dc8c6d2063669dd28244bb9beb29f6b211e69",
    VISION_PATH: "2e98bd0d96e4b8aa58a58b0ef1d959a8b3fde259f3ae7b948eb68ce4ffa6a169",
}
OLD = {
    **SOURCES,
    GRID_PATH: "dba9b870fb73c92b1a19af78b203ccf816c26573d86e3938af4c21f445b0f6fa",
}


def check_files(root, expected):
    for rel, expected_sha in expected.items():
        assert sha((root / rel).read_bytes()) == expected_sha, rel


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def readers(candidate):
    check_files(candidate, SOURCES)
    check_files(FROZEN, OLD)
    sys.path[:0] = [str(FROZEN), str(FROZEN / "src")]
    from scripts.graduation import g1_visibility_vision as baseline

    grid_name = "scripts.graduation.g1_visibility_grid"
    original = sys.modules[grid_name]
    try:
        grid, vision = (candidate / path for path in SOURCES)
        sys.modules[grid_name] = module("candidate_grid", grid)
        new = module("candidate_vision", vision)
    finally:
        sys.modules[grid_name] = original
    return {"baseline": baseline.measure_frame, "candidate": new.measure_frame}


def inputs():
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    directory = TRIAL / "instance"
    run = json.loads((directory / "run.json").read_bytes())
    index = json.loads((directory / "pixel-index.json").read_bytes())["frames"]
    by_id = {r["frame_id"]: r for r in index}
    feedback = [
        by_id[r["frame_id"]] for r in run["action_clock_contexts"] if r["phase"] == "FEEDBACK"
    ]
    assert len(feedback) == len({r["frame_id"] for r in feedback}) == 123
    assert len({r["physics_step"] for r in feedback}) == 122
    assert [x["file"] for x in feedback[-2:]] == ["frames/0127.json", "frames/0128.json"]
    geometry = json.loads((TRIAL / "allocation.json").read_bytes())["geometry"]
    frames = {}
    for row in feedback:
        raw = (directory / row["file"]).read_bytes()
        assert sha(raw) == row["file_sha256"]
        frame = RGBDObservation.model_validate_json(raw)
        assert (frame.frame_id, frame.checksum_sha256) == (row["frame_id"], row["checksum_sha256"])
        frames[frame.frame_id] = frame
    return feedback, frames, geometry


def operating_state():
    def read(path):
        p = Path(path)
        return p.read_text().strip() if p.is_file() else None

    def fields(data, keys):
        return {
            k: v
            for line in data.splitlines()
            if (parts := line.split(maxsplit=1))
            and (k := parts[0].rstrip(":")) in keys
            and len(parts) > 1
            and (v := parts[1])
        }

    return dict(
        utc=time.time(),
        pid=os.getpid(),
        loadavg=read("/proc/loadavg"),
        pressure_cpu=read("/proc/pressure/cpu"),
        pressure_io=read("/proc/pressure/io"),
        proc_stat=fields(read("/proc/stat"), {"ctxt", "procs_running", "procs_blocked", "cpu"}),
        self_io=fields(read("/proc/self/io"), {"read_bytes", "write_bytes", "rchar", "wchar"}),
        affinity=sorted(os.sched_getaffinity(0)),
        nice=os.getpriority(os.PRIO_PROCESS, 0),
    )


def clock_call(fn, frame, geometry):
    before = resource.getrusage(resource.RUSAGE_THREAD)
    cpu = time.thread_time_ns()
    process = time.process_time_ns()
    wall = time.perf_counter_ns()
    value = fn(frame, geometry)
    wall = time.perf_counter_ns() - wall
    process = time.process_time_ns() - process
    cpu = time.thread_time_ns() - cpu
    after = resource.getrusage(resource.RUSAGE_THREAD)
    return value, dict(
        ns=wall,
        thread_cpu_ns=cpu,
        process_cpu_ns=process,
        voluntary_switches=after.ru_nvcsw - before.ru_nvcsw,
        involuntary_switches=after.ru_nivcsw - before.ru_nivcsw,
        minor_faults=after.ru_minflt - before.ru_minflt,
        major_faults=after.ru_majflt - before.ru_majflt,
    )


def worker(candidate, number):
    initial = operating_state()
    methods = readers(candidate)
    feedback, frames, geometry = inputs()
    rows = []

    def pair(row, group, repetition, reverse):
        frame = frames[row["frame_id"]]
        order = list(methods) if not reverse else list(methods)[::-1]
        record = dict(
            worker=number,
            group=group,
            repetition=repetition,
            order=order,
            file=Path(row["file"]).name,
            label=row["label"],
            file_sha256=row["file_sha256"],
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            physics_step=row["physics_step"],
            cpu_load=os.getloadavg(),
        )
        outputs = []
        for version in order:
            value, timing = clock_call(methods[version], frame, geometry)
            outputs.append(sha(canonical(value)))
            record.update({f"{version}_{key}": val for key, val in timing.items()})
        assert outputs[0] == outputs[1], (row["file"], outputs)
        record["measurement_sha256"] = outputs[0]
        rows.append(record)

    # First complete measurement in each fresh process: both detector modules' per-word and
    # grid caches are cold. Later samples see ordinary immutable dictionary/geometry caches.
    pair(feedback[-1], "cold", number, number % 2)
    for index, row in enumerate(feedback):
        pair(row, "cycle", number, (number + index) % 2)
    for rep in range(6):
        for offset, row in enumerate(feedback[-2:]):
            pair(row, "neighbors", number * 6 + rep, (number + rep + offset) % 2)
    return dict(worker=number, before=initial, after=operating_state(), samples=rows)


def payload_components(frame, geometry, measurement):
    """Replicate observer payload statements independently, outside the acceptance sample."""
    t0 = time.perf_counter_ns()
    revalidated = type(frame).model_validate(frame.model_dump())
    t1 = time.perf_counter_ns()
    assert (
        revalidated.model_dump(mode="json", include=set(geometry["camera"])) == geometry["camera"]
    )
    t2 = time.perf_counter_ns()
    with Image.open(io.BytesIO(base64.b64decode(revalidated.rgb_png_base64))) as im:
        gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
    t3 = time.perf_counter_ns()
    depth = np.frombuffer(base64.b64decode(revalidated.depth_float32_base64), dtype="<f4").reshape(
        frame.height, frame.width
    )
    t4 = time.perf_counter_ns()
    encoded = canonical(measurement)
    t5 = time.perf_counter_ns()
    return dict(
        payload_revalidation_ns=t1 - t0,
        camera_check_ns=t2 - t1,
        full_png_gray_decode_ns=t3 - t2,
        full_depth_decode_ns=t4 - t3,
        canonical_evidence_encoding_ns=t5 - t4,
        gray_sha256=sha(gray.tobytes()),
        depth_sha256=sha(depth.tobytes()),
        evidence_sha256=sha(encoded),
    )


def component_profile(candidate):
    # Isolated from the acceptance loop. Traced wrappers overlap within parents.
    methods = readers(candidate)
    feedback, frames, geometry = inputs()
    profiles = {}
    for version, method in methods.items():
        obs = method.__globals__
        grid = obs["find_grids"].__globals__
        wall, count = collections.Counter(), collections.Counter()
        replacements = []

        def wrap(scope, name, count=count, wall=wall, replacements=replacements):
            fn = scope[name]

            def timed(*args, **kwargs):
                t = time.perf_counter_ns()
                result = fn(*args, **kwargs)
                ns = time.perf_counter_ns() - t
                count[name] += 1
                wall[name] += ns
                if name == "_accept":
                    wall[f"_accept/{args[2]}"] += ns
                    count[f"seeds/{args[2]}"] += len(args[1])
                if name == "_weak_grid_cells":
                    count["batch_poses"] += len(args[2])
                    count["proved_negative"] += len(result)
                return result

            replacements.append((scope, name, fn))
            scope[name] = timed

        for name in (
            "_sample",
            "_crossings",
            "_seeds",
            "_verify",
            "_weak_grid_cells",
            "_island_seeds",
            "_contours",
            "_accept",
        ):
            wrap(grid, name)
        for name in ("find_grids", "_plane", "_measure_side"):
            wrap(obs, name)
        for row in feedback[-2:]:
            method(frames[row["frame_id"]], geometry)
        for row in feedback[-2:]:
            key = Path(row["file"]).name
            frame = frames[row["frame_id"]]
            records = []
            for _ in range(3):
                wall.clear()
                count.clear()
                result, clocks = clock_call(method, frame, geometry)
                records.append(
                    dict(
                        **clocks,
                        inclusive_ns=dict(wall),
                        calls=dict(count),
                        measurement_sha256=sha(canonical(result)),
                        standalone_payload=payload_components(frame, geometry, result),
                    )
                )
            profiles.setdefault(key, {})[version] = records
        for scope, key, old in reversed(replacements):
            scope[key] = old
    return profiles


def statistics(rows):
    results = {"n_per_version": len(rows)}
    for version in ("baseline", "candidate"):

        def group(key, version=version):
            ns = [r[f"{version}_{key}"] for r in rows]
            return {
                key: float(np.quantile(ns, q)) / 1e6
                for key, q in (("p50_ms", 0.5), ("p95_ms", 0.95), ("max_ms", 1))
            }

        worst = max(rows, key=lambda r: r[version + "_ns"])
        results[version] = {
            **group("ns"),
            "thread_cpu": group("thread_cpu_ns"),
            "slowest": {
                k: worst[k] for k in ("file", "frame_id", "physics_step", "worker", "repetition")
            },
            "voluntary_switches": sum(r[version + "_voluntary_switches"] for r in rows),
            "involuntary_switches": sum(r[version + "_involuntary_switches"] for r in rows),
        }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_runtime_source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--worker", type=int)
    args = parser.parse_args()
    candidate = args.candidate_runtime_source.resolve()
    manifest = candidate.parent / "pixel-bench-source.json"
    provenance = json.loads(manifest.read_bytes())
    assert provenance["parent"] == GENERATION and provenance["detector_files"] == SOURCES
    assert provenance["physical_qualification"] is False
    if args.worker is not None:
        print(canonical(worker(candidate, args.worker)).decode())
        return
    original_manifest = (FROZEN / "runtime-build.json").read_bytes()
    assert sha(original_manifest) == GENERATION
    files = dict(json.loads(original_manifest)["runtime_files_sha256"], **SOURCES)
    assert len(files) == provenance["source_count"] == 565
    check_files(candidate, files)
    sources = args.output / "pixel-timing-samples.public.json.gz"
    summary = args.output / "pixel-timing-summary.public.json"
    if sources.exists() or summary.exists():
        raise FileExistsError("use an empty output location")
    workers = []
    with (DATA / "feedback-deadline-performance.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for n in range(5):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(Path(__file__).resolve()),
                    str(candidate),
                    str(args.output),
                    "--worker",
                    str(n),
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode:
                raise RuntimeError(proc.stderr)
            workers.append(json.loads(proc.stdout))
        profile = component_profile(candidate)
        check_files(candidate, SOURCES)
        check_files(FROZEN, OLD)
    rows = [r for batch in workers for r in batch.pop("samples")]
    groups = {g: [r for r in rows if r["group"] == g] for g in ("cycle", "cold", "neighbors")}
    assert [len(groups[g]) for g in ("cycle", "cold", "neighbors")] == [615, 5, 60]
    buckets = {g: statistics(v) for g, v in groups.items()}
    for step in (1080, 1088):
        subset = [r for r in groups["neighbors"] if r["physics_step"] == step]
        assert len(subset) == 30
        buckets[f"neighbors_{step}"] = statistics(subset)
    common = dict(
        baseline_generation=GENERATION,
        candidate_diagnostic_source_inventory_sha256=provenance["source_inventory_sha256"],
        candidate_diagnostic_source_manifest_sha256=sha(manifest.read_bytes()),
        candidate_file_table_sha256=sha(canonical(files)),
        baseline_detector_files_sha256=OLD,
        candidate_detector_files_sha256=SOURCES,
        input_index_sha256=sha((TRIAL / "instance/pixel-index.json").read_bytes()),
        script_sha256=sha(Path(__file__).read_bytes()),
        helper_sha256=sha((ROUND / "pixel_seed_profile.py").read_bytes()),
    )
    with sources.open("xb") as f:
        f.write(gzip.compress(canonical({**common, "samples": rows}) + b"\n", mtime=0))
    gates = {
        g: (buckets[g]["candidate"]["p95_ms"] <= 35 and buckets[g]["candidate"]["max_ms"] <= 45)
        for g in ("cycle", "neighbors_1080", "neighbors_1088")
    }
    first_cpu = Path("/proc/cpuinfo").read_text().split("\n\n")[0]
    env = dict(
        python=sys.version,
        interpreter=sys.executable,
        numpy=np.__version__,
        pillow=PIL.__version__,
        pydantic=pydantic.__version__,
        opencv=cv2.__version__,
        opencv_threads=cv2.getNumThreads(),
        platform=platform.platform(),
        cpu_model=next(
            (
                s.split(":", 1)[1].strip()
                for s in first_cpu.splitlines()
                if s.startswith("model name")
            ),
            None,
        ),
        thread_settings={
            k: os.environ.get(k)
            for k in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OPENCV_FOR_THREADS_NUM",
            )
        },
        clock=time.get_clock_info("perf_counter").implementation,
    )
    result = dict(
        **common,
        schema="g1.radial.native.paired-pixels.v1",
        samples_sha256=sha(sources.read_bytes()),
        matches=len(rows),
        groups=buckets,
        gates=gates,
        all_warm_pixel_gates=all(gates.values()),
        workers=workers,
        environment=env,
        components=profile,
        timing_scope="Wall time around one complete measure_frame of a trusted-type packet "
        "including its internal full revalidation, RGB/depth decode, grid candidates, "
        "metric depth and arbitration. Disk/hashing and rendering are outside.",
        method="Five separate processes with default scheduling and library threads. "
        "A separate cold call at 1088 precedes each cycle. Input order follows acquisition "
        "within cycles. Baseline/candidate order alternates. Neighbor repetitions are warm. "
        "Instrumented component measurements are separate and inclusive.",
    )
    with summary.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(
        json.dumps(
            {g: (s["candidate"]["p95_ms"], s["candidate"]["max_ms"]) for g, s in buckets.items()},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
