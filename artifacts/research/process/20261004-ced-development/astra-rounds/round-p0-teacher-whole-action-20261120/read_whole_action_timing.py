"""Independently reconstruct same-thread timing from sealed real action originals."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

_LABELS = (
    "pre_start",
    "pre_end",
    "dispatch",
    "executor_return",
    "controller_return",
    "hold_begin",
    "hold_end",
    "terminal_capture_begin",
    "terminal_capture_end",
    "post_context",
    "post_evaluated",
    "action_exit",
)
_FIELDS = ("seq", "parent", "label", "start_ns", "end_ns", "operation_id", "acquisition_id")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _marks(timing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    previous = -1
    for row in timing["marks"]:
        label, instant, step = row["label"], row["ns"], row["physics_step"]
        require(label not in result, f"duplicate timing mark {label}")
        require(_int(instant) and instant >= previous, "non-monotonic timing marks")
        require(step is None or _int(step), "invalid timing mark physics step")
        result[label] = row
        previous = instant
    action = [label for label in result if label in _LABELS]
    require(action == sorted(action, key=_LABELS.index), "action phase marks are out of order")
    return result


def _leaves(spans: list[Any], raw: dict[str, Any]) -> list[tuple[str, int, int]]:
    operations = {
        (row["operation_id"], row["kind"].lower())
        for row in raw.get("backend_operation_ledger", [])
    }
    acquisitions = {
        row["acquisition_id"]: row["operation_id"]
        for row in raw.get("operational_events", [])
        if row["acquisition_id"] is not None
    }
    stack: list[dict[str, Any]] = []
    leaves = []
    current = 0

    def close() -> None:
        nonlocal current
        row = stack.pop()
        leaves.append((row["label"], current, row["end_ns"]))
        current = row["end_ns"]

    for seq, row in enumerate(spans, 1):
        require(set(row) == set(_FIELDS) and row["seq"] == seq, "invalid timing span sequence")
        start, end, label = row["start_ns"], row["end_ns"], row["label"]
        require(_int(start) and _int(end) and current <= start <= end, "invalid span clock")
        require(isinstance(label, str) and bool(label), "missing span category")
        while stack and stack[-1]["seq"] != row["parent"] and stack[-1]["end_ns"] <= start:
            close()
        require(
            row["parent"] == (stack[-1]["seq"] if stack else None)
            and (not stack or end <= stack[-1]["end_ns"])
            and start >= current,
            "invalid same-thread nesting or overlapping sibling spans",
        )
        op, acquisition = row["operation_id"], row["acquisition_id"]
        require(op is None or _int(op), "invalid span operation ID")
        if label.startswith("backend_"):
            require((op, label.removeprefix("backend_")) in operations, "unjoined backend timing")
        if acquisition is not None:
            require(
                op is not None and acquisitions.get(acquisition) == op,
                "unjoined acquisition timing",
            )
        if stack:
            leaves.append((stack[-1]["label"], current, start))
        current = start
        stack.append(row)
    while stack:
        close()
    return leaves


def _coverage(leaves: list[tuple[str, int, int]], start: int, end: int) -> dict[str, Any]:
    by_label: Counter[str] = Counter()
    for label, lo, hi in leaves:
        overlap = min(hi, end) - max(lo, start)
        if overlap > 0:
            by_label[label] += overlap
    wall = end - start
    residual = wall - sum(by_label.values())
    require(wall >= 0 and residual >= 0, "timing accounts exceed wall clock")
    if residual:
        by_label["other"] += residual
    return {"wall_ns": wall, "exclusive_ns": dict(by_label)}


def _join_receipt(marks: dict[str, Any], raw: dict[str, Any], post: Any, spans: list[Any]) -> None:
    receipts = raw.get("horizons", [])
    require(len(receipts) <= 1, "more than one original horizon receipt")
    if not receipts:
        require(post is None, "POST without original horizon receipt")
        return
    receipt = receipts[0]
    require(receipt["skill"] == "MOVE_ABOVE", "foreign action receipt")
    if "dispatch" in marks:
        require(
            marks["dispatch"]["physics_step"] == receipt["dispatch_step"],
            "dispatch disagrees with original horizon receipt",
        )
    returned = receipt["controller_return_step"]
    if returned is not None:
        require(
            marks["controller_return"]["physics_step"] == returned
            and marks["executor_return"]["physics_step"] == returned,
            "controller timings disagree with original horizon receipt",
        )
    if "hold_begin" in marks:
        require(marks["hold_begin"]["physics_step"] == returned, "HOLD starts on a foreign step")
    if "hold_end" in marks:
        require(
            marks["hold_end"]["physics_step"] == receipt["terminal_step"],
            "HOLD end disagrees with original horizon receipt",
        )
    if post is None:
        return
    terminal = receipt["terminal_step"]
    require(
        receipt["complete"] is True and terminal - receipt["dispatch_step"] == 1920,
        "POST lacks the complete registered 1920-step horizon",
    )
    require(
        all(label in marks for label in _LABELS if label not in {"post_evaluated"})
        and all(
            marks[label]["physics_step"] == terminal
            for label in ("terminal_capture_begin", "terminal_capture_end")
        ),
        "POST lacks complete phase timing or terminal physics joins",
    )
    dispatch = receipt["dispatch_step"]
    physics_operations = {
        int(row["physics_interval_id"].removeprefix("operation-"))
        for row in raw["physics"]
        if dispatch < row["physics_step"] <= terminal
    }
    start = marks["dispatch"]["ns"]
    end = marks["hold_end"]["ns"]
    native_step_spans = [
        row["operation_id"]
        for row in spans
        if row["label"] == "mj_step" and start <= row["start_ns"] <= row["end_ns"] <= end
    ]
    require(
        len(native_step_spans) == len(physics_operations) == 1920
        and set(native_step_spans) == physics_operations,
        "complete action timing does not cover every original native physics step",
    )
    require(
        any(
            row["acquisition_id"] == receipt["terminal_acquisition_id"]
            and row["begin_step"] == row["end_step"] == terminal
            for row in raw["operational_events"]
        ),
        "terminal timing has no original terminal acquisition",
    )


def read_timing(timing: dict[str, Any], raw: dict[str, Any], pre: Any, post: Any) -> dict[str, Any]:
    require(
        timing["schema_version"] == "native.whole-action.timing.v1"
        and timing["clock"] == "monotonic_ns"
        and _int(timing["thread_id"]),
        "foreign timing evidence schema or clock",
    )
    marks = _marks(timing)
    spans = timing["spans"]
    leaves = _leaves(spans, raw)
    _join_receipt(marks, raw, post, spans)
    report: dict[str, Any] = dict(
        timing_thread_id=timing["thread_id"],
        reached_original_post=post is not None,
        post_evaluation_return_observed="post_evaluated" in marks,
        raw_span_count=len(spans),
        span_count_by_label=dict(Counter(row["label"] for row in spans)),
        raw_mark_count=len(marks),
        marks=marks,
        action=None,
        phases={},
        post_elapsed_ms=None,
        production_step_timeout_ms=8000,
        minimum_span_clock_calls=len(spans) * 2,
        render_return_includes_gpu_readback=True,
        write_includes_userspace_flush=True,
        physical_disk_sync_measured=False,
    )
    if "pre_start" not in marks:
        require(pre is None and post is None, "missing original PRE timing anchor")
        return report
    start = marks["pre_start"]["ns"]
    if pre is not None:
        require(
            abs(start - round(pre["step_started_at"] * 1e9)) <= 1,
            "timing anchor differs from original Shield PRE",
        )
    if post is not None:
        instant = marks["post_context"]["ns"]
        require(
            pre is not None
            and pre["step_started_at"] == post["step_started_at"]
            and abs(instant - round(post["monotonic_now"] * 1e9)) <= 1,
            "timing differs from original Shield POST or resets the PRE anchor",
        )
        report["post_elapsed_ms"] = (post["monotonic_now"] - post["step_started_at"]) * 1000
    else:
        instant = marks["action_exit"]["ns"]
    report["action"] = _coverage(leaves, start, instant)
    report["action"]["fully_contained_span_count_by_label"] = dict(
        Counter(
            row["label"] for row in spans if start <= row["start_ns"] <= row["end_ns"] <= instant
        )
    )
    report["action"]["positive_intersection_span_count_by_label"] = dict(
        Counter(
            row["label"]
            for row in spans
            if min(row["end_ns"], instant) > max(row["start_ns"], start)
        )
    )
    ordered = [
        label for label in _LABELS if label in marks and start <= marks[label]["ns"] <= instant
    ]
    phases = report["phases"]
    for left, right in zip(ordered, ordered[1:], strict=False):
        phases[f"{left}_to_{right}"] = _coverage(leaves, marks[left]["ns"], marks[right]["ns"])
    if spans:
        preparation = min(start, spans[0]["start_ns"])
        report["instrumented_preparation"] = _coverage(leaves, preparation, start)
        report["body_exit_cleanup_observed_spans"] = _coverage(
            leaves,
            marks["action_exit"]["ns"],
            max(marks["action_exit"]["ns"], max(row["end_ns"] for row in spans)),
        )
    if post is not None:
        report["post_context_to_action_exit"] = _coverage(
            leaves,
            instant,
            marks["action_exit"]["ns"],
        )
    return report


def _guard_timing_checks(
    checks: list[Any], raw: dict[str, Any], trace: dict[str, Any], start: int | None
) -> dict[str, Any]:
    guards = {row["sequence"]: row for row in raw["guard_events"] if "sequence" in row}
    guard_spans = [row for row in trace["spans"] if row["label"] == "guard"]
    by_outcome: Counter[str] = Counter()
    position = 0
    upper = -1
    previous = -1
    previous_sequence = 0
    for check in checks:
        if "diagnostic_authorized_monotonic_ns" not in check and "guard_sequence" not in check:
            continue
        instant, seq = check["diagnostic_authorized_monotonic_ns"], check["guard_sequence"]
        require(
            _int(instant)
            and _int(seq)
            and start is not None
            and instant >= start
            and instant >= previous
            and seq > previous_sequence,
            "original timed owner checks do not have increasing guard sequence and clock",
        )
        while position < len(guard_spans) and guard_spans[position]["start_ns"] <= instant:
            upper = max(upper, guard_spans[position]["end_ns"])
            position += 1
        require(instant <= upper, "original owner timing falls outside all worker guard spans")
        guard = guards[seq]
        require(
            all(guard[key] == value for key, value in check["checkpoint"].items()),
            "timed owner checkpoint differs from native guard original",
        )
        if instant - start >= 8_000_000_000:
            by_outcome[guard["outcome"]] += 1
        previous = instant
        previous_sequence = seq
    return {
        "authorized_clock_checks_at_or_after_original_post_limit": dict(by_outcome),
        "last_timed_check_monotonic_ns": previous if previous >= 0 else None,
        "last_timed_check_guard_sequence": previous_sequence or None,
    }


def _strict_load(path: Path) -> Any:
    return json.loads(path.read_bytes())


def read_run(release: Path) -> dict[str, Any]:
    original = release / "run" / "originals"
    inventory_path = original / "inventory.json"
    inventory_bytes = inventory_path.read_bytes()
    inventory = json.loads(inventory_bytes)
    lifecycle = _strict_load(release / "run" / "collection-result.json")
    require(
        hashlib.sha256(inventory_bytes).hexdigest()
        == lifecycle["lifecycle_links"]["originals/inventory.json"],
        "lifecycle does not seal the timing inventory",
    )
    index = inventory["files"]

    def sealed(name: str, *, optional: bool = False) -> Any:
        path = original / name
        if optional and name not in index and not path.exists():
            return None
        data = path.read_bytes()
        require(
            len(data) == index[name]["bytes"]
            and hashlib.sha256(data).hexdigest() == index[name]["sha256"],
            f"timing original {name} differs from inventory",
        )
        return json.loads(data)

    raw = sealed("partial-originals.json")
    require(raw["source_scope"] == "WHOLE_ACTION_DEVELOPMENT", "foreign evidence scope")
    pre = sealed("shield/step-1-pre-input.json", optional=True)
    post = sealed("shield/step-1-post-input.json", optional=True)
    trace = sealed("whole-action-timing.json")
    result = read_timing(
        trace, raw, pre["context"] if pre else None, post["context"] if post else None
    )
    result["original_worker_guard_timing"] = _guard_timing_checks(
        sealed("active-checks.json"),
        raw,
        trace,
        result["marks"].get("pre_start", {}).get("ns"),
    )
    final = lifecycle["whole_action_diagnostic"]
    exit_mark = result["marks"].get("action_exit", {}).get("ns")
    post_evaluated = sealed("shield/step-1-post-result.json", optional=True)
    if post_evaluated is not None and post_evaluated["result"] is not None:
        require(
            result["post_evaluation_return_observed"]
            and result["marks"]["post_context"]["ns"] == final["post_monotonic_ns"],
            "completed original Shield evaluation lacks joined timing marks",
        )
    cleanup_finished = final["body_cleanup_finished_monotonic_ns"]
    if exit_mark is not None and cleanup_finished is not None:
        require(
            _int(cleanup_finished) and cleanup_finished >= exit_mark,
            "body cleanup timestamp precedes action exit",
        )
        result["body_exit_to_cleanup_finished_ns"] = cleanup_finished - exit_mark
        result["body_cleanup_finished_monotonic_ns"] = cleanup_finished
    result["trace_sha256"] = index["whole-action-timing.json"]["sha256"]
    result["trace_bytes"] = index["whole-action-timing.json"]["bytes"]
    result["timing_original_estimate_bytes_per_span"] = (
        result["trace_bytes"] / result["raw_span_count"] if result["raw_span_count"] else None
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    args = parser.parse_args()
    try:
        report = read_run(args.release)
    except (KeyError, TypeError, ValueError, OSError, IndexError) as exc:
        print(json.dumps({"status": "TIMING_ORIGINALS_REJECTED", "error": str(exc)}))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
