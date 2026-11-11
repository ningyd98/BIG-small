"""只读核验R558封存原件；历史时间包络不作为在线控制时间。"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import math
import os
import platform
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

HARNESS_SHA256 = "b27df4b4dfc4015e940ca807e6f1e72b56f3058a7b70d4f7268baa8e8df3a262"
SOURCE_COMMIT = "75f5a991fe16549843177a1fa79c76cf1914e741"
ROOT = Path(__file__).resolve().parents[1]


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _stage_interval(start, end):
    """认证同一次已记录stage的两个有序、带时区边界。"""
    for key in (
        "root_id",
        "registry_sha256",
        "group_id",
        "case_id",
        "request_id",
        "op_id",
        "parent_op_id",
        "kind",
        "stage",
        "context",
    ):
        _require(start[key] == end[key], f"stage boundary binding:{key}")
    _require(
        start["phase"] == "start"
        and end["phase"] == "end"
        and end["outcome"] == "error"
        and end["kind"] == "stage"
        and end["stage"] == "tracker",
        "stage boundary phase/type",
    )
    times = [datetime.fromisoformat(e["utc"]) for e in (start, end)]
    _require(
        all(t.tzinfo is not None and t.utcoffset() is not None for t in times),
        "stage timezone missing",
    )
    times = [t.astimezone(UTC) for t in times]
    ticks = [e["monotonic_s"] for e in (start, end)]
    _require(
        all(type(t) in (float, int) and math.isfinite(t) for t in ticks)
        and ticks[0] <= ticks[1]
        and times[0] <= times[1],
        "stage boundary order",
    )
    return tuple(times)


def _tracker_class_at_interval(original, observation, grounding, start, end):
    """仅历史回放使用原绑定检查，两端均有效后执行原构造器和几何。"""
    _require(
        all(t.tzinfo is not None and t.utcoffset() is not None for t in (start, end))
        and start <= end,
        "invalid tracker interval",
    )
    expected_checksum = observation.checksum_sha256
    expected_grounding = _canonical(grounding)

    class HistoricalTracker(original):
        def __init__(self, candidate, geometry):
            _require(candidate.checksum_sha256 == expected_checksum, "tracker observation binding")
            _require(_canonical(geometry) == expected_grounding, "tracker grounding binding")
            super().__init__(candidate, geometry)

        def _binding_reason(self, candidate):
            for boundary in (start, end):
                reason = original._binding_reason_at(self, candidate, boundary)
                if reason:
                    return reason
            return None

    return HistoricalTracker


@contextmanager
def _historical_tracker_refusal_scope(harness, raw_root, registry):
    """独立同步离线作用域；两个临时绑定在任何退出路径恢复。"""
    from cloud_edge_robot_arm.vision import tracking

    original_visual = harness._visual_source
    original_tracker = tracking.OpenCVTargetTracker
    policy = harness._read(harness.REPAIR / "plan.json")["visual_refusal_allowlist"]["tracker"]

    def visual(case, response, observations, opened, ended, parsed):
        candidates = [
            e
            for e in ended.values()
            if e["kind"] == "stage"
            and e["stage"] == "tracker"
            and e["outcome"] == "error"
            and e["error_type"] == policy["exception"]
            and e["error_message"] in policy["exact_messages"]
        ]
        if not candidates:
            return original_visual(case, response, observations, opened, ended, parsed)
        _require(len(candidates) == 1, "multiple tracker replay candidates")
        end = candidates[0]
        start = opened[end["op_id"]]
        recorded = harness._read_events(raw_root, case.case_id)
        _require(start in recorded and end in recorded, "tracker events differ from originals")
        _require(
            end["root_id"] == registry["root_id"] and end["case_id"] == case.case_id,
            "tracker registry/case binding",
        )
        begin, finish = _stage_interval(start, end)
        context = end["context"]
        observation = observations[context["observation_checksum"]]
        tracker = _tracker_class_at_interval(
            original_tracker, observation, context["grounding"], begin, finish
        )
        try:
            tracking.OpenCVTargetTracker = tracker
            return original_visual(case, response, observations, opened, ended, parsed)
        finally:
            tracking.OpenCVTargetTracker = original_tracker

    try:
        harness._visual_source = visual
        yield
    finally:
        harness._visual_source = original_visual
        tracking.OpenCVTargetTracker = original_tracker


def _versions():
    values = {"python": platform.python_version(), "executable": sys.executable}
    for name in (
        "numpy",
        "opencv-python",
        "opencv-python-headless",
        "pydantic",
        "mujoco",
        "Pillow",
    ):
        try:
            values[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            values[name] = None
    return values


def verify_archive(raw_root: Path) -> dict:
    """只读原封存并返回新派生核验，不执行任何在线工作。"""
    harness = importlib.import_module("scripts.probe_molmo_multiscene")
    report = {
        "schema": "molmo.archive-derived.r564.v1",
        "mode": "OFFLINE_RECORDED_STAGE_INTERVAL",
        "original_source_commit": SOURCE_COMMIT,
        "exact_internal_clock_recorded": False,
        "historical_summary": None,
        "case_comparisons": [],
        "derived_summary": {
            "valid_suite": False,
            "all_cases_pass": False,
            "passed_cases": 0,
            "positive_passed": 0,
            "negative_passed": 0,
            "total_cases": 7,
            "evidence_errors": [],
        },
        "actual_calls": {"loads": 0, "generations": 0, "paid": 0, "hardware": 0},
        "runtime": _versions(),
        "derived_verifier": {
            "script_sha256": harness._sha(Path(__file__)),
            "tests_sha256": harness._sha(ROOT / "tests/test_molmo_multiscene_archive.py"),
            "historical_harness_sha256": HARNESS_SHA256,
        },
    }
    try:
        _require(
            harness._sha(Path(harness.__file__)) == HARNESS_SHA256,
            "historical harness source drift",
        )
        raw_root = raw_root.resolve(strict=True)
        registry = harness._read(raw_root / "registry.json")
        harness._registry_check(raw_root, registry)
        report["registry_sha256"] = harness._sha(raw_root / "registry.json")
        report["historical_summary_sha256"] = harness._sha(raw_root / "summary.local.json")
        report["historical_summary"] = harness._read(raw_root / "summary.local.json")
        seals = {}
        # Authenticate the existing file sets and events before scoped replay.
        for group in harness.GROUPS:
            path = raw_root / group / "raw-manifest.local.json"
            harness._manifest_check(
                raw_root,
                registry,
                path,
                harness._identity(raw_root, registry, group),
                harness._group_paths(raw_root, registry, group),
            )
            seals[str(path.relative_to(raw_root))] = harness._sha(path)
            harness._event_check(
                raw_root, registry, group, None, harness._read_events(raw_root, f"_{group}")
            )
        cases = [harness.CaseSpec.read(row) for row in registry["cases"]]
        for case in cases:
            events = harness._read_events(raw_root, case.case_id)
            harness._event_check(raw_root, registry, case.group_id, case, events)
            path = raw_root / case.group_id / case.case_id / harness.CASE_MANIFEST
            harness._manifest_check(
                raw_root,
                registry,
                path,
                harness._identity(raw_root, registry, case.group_id, case),
                harness._case_paths(raw_root, case, events, True),
            )
            seals[str(path.relative_to(raw_root))] = harness._sha(path)
        rows = [harness._read(p) for p in sorted(raw_root.glob("G*/result-*.json"))]
        with _historical_tracker_refusal_scope(harness, raw_root, registry):
            report["derived_summary"] = harness.summarize(registry, rows, root=raw_root)
            for case in cases:
                response = harness.InitialPlanningResponse.model_validate(
                    harness._read(raw_root / case.group_id / case.case_id / "pipeline-return.json")
                )
                stored = harness._read(raw_root / case.group_id / f"result-{case.case_id}.json")
                computed = harness.classify_case(
                    case,
                    response,
                    harness._read_events(raw_root, case.case_id),
                    root=raw_root,
                    registry=registry,
                )
                report["case_comparisons"].append(
                    {
                        "case_id": case.case_id,
                        "matches": stored == computed,
                        "stored_verdict": stored["verdict"],
                        "recomputed_verdict": computed["verdict"],
                    }
                )
        report["original_seal_sha256"] = seals
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        report["derived_summary"].update(valid_suite=False, all_cases_pass=False, passed_cases=0)
        report["derived_summary"]["evidence_errors"].append(f"{type(exc).__name__}:{exc}")
    return report


def main(argv=None) -> int:
    """只向原根之外的全新派生目录写结果，退出码表示证据有效性。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output-new", type=Path, required=True)
    args = parser.parse_args(argv)
    raw_root = args.raw_root.resolve(strict=True)
    output = args.output_new.resolve()
    _require(not output.is_relative_to(raw_root), "derived output must be outside original root")
    output.mkdir(parents=True, exist_ok=False)
    report = verify_archive(raw_root)
    with (output / "report.local.json").open("x") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    summary = report["derived_summary"]
    print(
        json.dumps({key: summary[key] for key in ("valid_suite", "all_cases_pass", "passed_cases")})
    )
    return 0 if summary["valid_suite"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
