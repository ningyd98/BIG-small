"""Join paired pixel timings to the actual G1 radial d02 controller samples."""

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

ROUND = Path(__file__).resolve().parent
ROOT = next(p for p in ROUND.parents if (p / "pyproject.toml").is_file())
PLAN = "567e992a68593aecb32e73a3c3cd5bd9dc4a73d2c8ef2adb5146b91abc944171"
BASE = "36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf"
INSTANCE = (
    ROOT
    / "experiments/results/g1-visibility-pose-repair-20261124"
    / "batches/train-radial15-01/d02/instance"
)
LIMITS = dict(estimated_p95=80, estimated_max=90, pixel_p95=35, pixel_max=45)


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def dump(path, obj):
    with path.open("xb") as stream:
        data = (
            json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n"
        ).encode()
        stream.write(gzip.compress(data, mtime=0) if path.suffix == ".gz" else data)


def rel(path):
    return str(path.relative_to(ROOT))


def ms(a, b):
    return 1000 * (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def stats(values):
    a = np.asarray(list(values), dtype=float)
    require(len(a) and np.isfinite(a).all(), "expected finite observations")
    return dict(
        n=len(a),
        p50=float(np.percentile(a, 50)),
        p95=float(np.percentile(a, 95)),
        maximum=float(max(a)),
    )


def native():
    require(sha(ROUND / "plan.json") == PLAN, "changed timing plan")
    pins = load(ROUND / "plan.json")["inputs_sha256"]
    names = ["run.json", "pixel-index.json", "online-audit.json", "online-vision.json"]
    for name in names:
        require(sha(INSTANCE / name) == pins[rel(INSTANCE / name)], "archived source changed")
    run, index, audit, vision = [load(INSTANCE / name) for name in names]
    roles = {(r["label"], r["frame_id"]): r for r in run["frame_roles"]}
    valid = {
        (part["skill"], sample["physics_step"]): 1000 * sample["sample_and_ik_s"]
        for part in audit
        if part.get("phase") == "servo"
        for sample in part["control_samples"]
    }
    end = run["stop"]
    stopkey = end["skill"], end["physics_step"]
    stop_action = next(a for a in run["actions"] if a["skill"] == end["skill"])
    error = re.fullmatch(
        r"ValueError:visual servo sample/IK deadline exceeded \(([0-9.]+)s\)",
        stop_action["servo_terminal_reason"],
    )
    require(
        error and len(valid) == 122 and stopkey not in valid,
        "terminal exception must be counted separately",
    )
    valid[stopkey] = 1000 * float(error.group(1))
    rows = []
    for f in index["frames"]:
        if not f["label"].endswith("/feedback"):
            continue
        skill = f["label"].split("/")[0]
        key = skill, f["physics_step"]
        i, digest = f["frame_id"], f["checksum_sha256"]
        a, sh = roles[(f["label"], i)], roles[(skill + "/FEEDBACK_Shield", i)]
        require(
            a["checksum_sha256"] == sh["checksum_sha256"] == digest
            and a["physics_step"] == sh["physics_step"] == key[1],
            "feedback/shield identity",
        )
        require(
            sha(INSTANCE / f["file"]) == f["file_sha256"] and a["captured_at"] == sh["captured_at"],
            "raw frame or capture mismatch",
        )
        obs = vision["frames"][i]
        require(
            obs["callers"] == {"servo_measure": 1} and obs["measurement"]["checksum"] == digest,
            "feedback source/call multiplicity",
        )
        to_shield = 1000 * sh["elapsed_from_capture_start_s"]
        row = dict(
            skill=skill,
            physics_step=key[1],
            file=f["file"],
            frame_id=i,
            checksum_sha256=digest,
            file_sha256=f["file_sha256"],
            observed_ids=obs["measurement"]["observed_ids"],
            observed_usable=obs["measurement"]["usable"],
            original_total_ms=valid[key],
            rejected_by_deadline=key == stopkey,
            camera_start_to_acquired_ms=ms(a["captured_at"], a["checked_at"]),
            acquired_to_shield_ms=ms(a["checked_at"], sh["checked_at"]),
            capture_through_shield_ms=to_shield,
            remainder_outside_capture_and_shield_ms=valid[key] - to_shield,
        )
        rows.append(row)
    require(
        len(rows) == len({r["frame_id"] for r in rows}) == len(valid) == 123,
        "missing a controller feedback",
    )
    require(len(set(r["physics_step"] for r in rows)) == 122, "original phase boundary")
    return dict(
        schema="g1.visibility.radial-native-window-segments.v1",
        generation=BASE,
        inputs_sha256={rel(INSTANCE / k): pins[rel(INSTANCE / k)] for k in names},
        measured_completed=122,
        measured_terminal_exceptions=1,
        reported_in_exception_ms=valid[stopkey],
        rows=rows,
        statistics={k: stats(r[k] for r in rows) for k in rows[0] if k.endswith("_ms")},
    )


def budget(timing_path, rows_path, result_path):
    segments = ROUND / "native-window-segments.public.json"
    saved = load(segments)
    require(saved == native(), "native rows are not the sealed controller record")
    inputs = {r["frame_id"]: r for r in saved["rows"]}
    raw = load(timing_path)
    out, seen = [], set()
    repeat = defaultdict(Counter)
    for v in raw["samples"]:
        group = v["group"]
        if group not in ("cycle", "neighbors"):
            continue
        key = v["frame_id"]
        src = inputs[key]
        require(
            v["physics_step"] == src["physics_step"]
            and v["checksum_sha256"] == src["checksum_sha256"]
            and Path(v["file"]).name == Path(src["file"]).name,
            "timing for another observation",
        )
        if "file_sha256" in v:
            require(v["file_sha256"] == src["file_sha256"], "replay file SHA changed")
        require(
            len(v["order"]) == 2 and set(v["order"]) == {"baseline", "candidate"},
            "unpaired measurement",
        )
        token = (group, v["worker"], v["repetition"], key)
        require(token not in seen, "duplicate observation")
        seen.add(token)
        repeat[group][key] += 1
        a, b = v["baseline_ns"] / 1e6, v["candidate_ns"] / 1e6
        estimate = src["original_total_ms"] + b - a
        require(min(estimate, a, b) > 0, "invalid paired timing")
        out.append(
            dict(
                group=group,
                worker=v["worker"],
                repetition=v["repetition"],
                file=src["file"],
                frame_id=key,
                physics_step=src["physics_step"],
                checksum_sha256=src["checksum_sha256"],
                original_native_ms=src["original_total_ms"],
                baseline_pixel_ms=a,
                candidate_pixel_ms=b,
                estimated_ms=estimate,
            )
        )
    require(
        set(repeat["cycle"]) == set(inputs) and min(repeat["cycle"].values()) >= 5,
        "each of the 123 feedback frames requires five independent cycles",
    )
    for key in inputs:
        require(
            len({r["worker"] for r in out if r["group"] == "cycle" and r["frame_id"] == key}) >= 5,
            "five distinct timing workers required",
        )
    targets = {r["frame_id"] for r in inputs.values() if r["physics_step"] in (1080, 1088)}
    require(
        set(repeat["neighbors"]) == targets and min(repeat["neighbors"].values()) >= 30,
        "missing a targeted repetition",
    )
    groups = {g: [r for r in out if r["group"] == g] for g in ("cycle", "neighbors")}
    groups["all"] = out
    summary = {
        g: {
            k: stats(r[k] for r in rows)
            for k in (
                "original_native_ms",
                "baseline_pixel_ms",
                "candidate_pixel_ms",
                "estimated_ms",
            )
        }
        for g, rows in groups.items()
    }
    passed = all(
        s["estimated_ms"]["p95"] <= LIMITS["estimated_p95"]
        and s["estimated_ms"]["maximum"] <= LIMITS["estimated_max"]
        and s["candidate_pixel_ms"]["p95"] <= LIMITS["pixel_p95"]
        and s["candidate_pixel_ms"]["maximum"] <= LIMITS["pixel_max"]
        for s in summary.values()
    )
    dump(rows_path, dict(schema="g1.visibility.radial-paired-window-rows.v1", rows=out))
    files = {
        f"scripts/graduation/g1_visibility_{s}.py": sha(
            ROOT / f"scripts/graduation/g1_visibility_{s}.py"
        )
        for s in ("grid", "vision")
    }
    # The pixel timing producer pins its candidate source bytes. Check them independently.
    candidate_sources = raw.get("candidate_detector_files_sha256") or raw.get(
        "candidate_detector_sha256"
    )
    require(candidate_sources == files, "timed candidate source differs from current detector")
    s = summary["all"]
    artifacts = [
        ROUND / "plan.json",
        Path(__file__).resolve(),
        segments,
        timing_path,
        rows_path,
        *[ROOT / n for n in saved["inputs_sha256"]],
    ]
    result = dict(
        schema="g1.visibility.radial-paired-window-budget.v1",
        eligible=passed,
        baseline_generation=BASE,
        detector_files_sha256=files,
        input_artifacts_sha256={rel(x): sha(x) for x in artifacts},
        original_native_windows=123,
        distinct_steps=122,
        samples_sha256=sha(timing_path),
        estimated_p95_ms=s["estimated_ms"]["p95"],
        estimated_max_ms=s["estimated_ms"]["maximum"],
        pixel_p95_ms=s["candidate_pixel_ms"]["p95"],
        pixel_max_ms=s["candidate_pixel_ms"]["maximum"],
        limits_ms=LIMITS,
        groups=summary,
        slowest_estimated=max(out, key=lambda r: r["estimated_ms"]),
        method=(
            "Original native window plus the candidate-minus-baseline pixel duration measured "
            "on that same packet. Live scheduling and dynamics require a new run."
        ),
    )
    dump(result_path, result)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=("native", "budget"))
    a = p.parse_args()
    if a.phase == "native":
        dump(ROUND / "native-window-segments.public.json", native())
    else:
        result = budget(
            ROUND / "pixel-timing-samples.public.json.gz",
            ROUND / "paired-window-rows.public.json.gz",
            ROUND / "paired-budget.public.json",
        )
        print(
            {
                k: result[k]
                for k in (
                    "eligible",
                    "estimated_p95_ms",
                    "estimated_max_ms",
                    "pixel_p95_ms",
                    "pixel_max_ms",
                )
            }
        )
