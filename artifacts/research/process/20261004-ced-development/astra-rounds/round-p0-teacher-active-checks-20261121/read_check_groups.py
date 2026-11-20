"""Attribute checkpoint work in a sealed, complete developer action to its actual phases."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from statistics import median
from typing import Any


def read_groups(run: Path) -> dict[str, Any]:
    root = run / "originals"
    lifecycle = json.loads((run / "collection-result.json").read_bytes())
    inventory = (root / "inventory.json").read_bytes()
    inventory_sha = hashlib.sha256(inventory).hexdigest()
    if lifecycle["lifecycle_links"]["originals/inventory.json"] != inventory_sha:
        raise ValueError("original inventory does not match the worker lifecycle")
    files = json.loads(inventory)["files"]

    def sealed(name: str) -> Any:
        raw = (root / name).read_bytes()
        if (
            len(raw) != files[name]["bytes"]
            or hashlib.sha256(raw).hexdigest() != files[name]["sha256"]
        ):
            raise ValueError(f"unmatched original {name}")
        return json.loads(raw)

    timing = sealed("whole-action-timing.json")
    checks = sealed("active-checks.json")
    post = sealed("shield/step-1-post-input.json")["context"]
    marks = {m["label"]: m for m in timing["marks"]}
    start = marks["pre_start"]["ns"]
    end = marks["post_context"]["ns"]
    if (
        abs(round(post["monotonic_now"] * 1e9) - end) > 1
        or abs(round(post["step_started_at"] * 1e9) - start) > 1
    ):
        raise ValueError("phase marks do not match the actual POST clock")
    spans = timing["spans"]
    index = {row["seq"]: row for row in spans}
    sql = {row["parent"]: row for row in spans if row["label"] == "sqlite"}
    owners = [
        r
        for r in spans
        if r["label"] == "owner_check" and start <= r["start_ns"] <= r["end_ns"] <= end
    ]
    if len(sql) != sum(r["label"] == "sqlite" for r in spans):
        raise ValueError("more than one SQLite interval for a parent")

    def summarize(begin: int, finish: int) -> dict[str, Any]:
        sources: Counter[str] = Counter()
        gross = 0
        sqlite = 0
        for row in owners:
            if not begin <= row["start_ns"] <= row["end_ns"] <= finish:
                continue
            child = sql[row["seq"]]
            if not row["start_ns"] <= child["start_ns"] <= child["end_ns"] <= row["end_ns"]:
                raise ValueError("SQLite interval outside its check")
            gross += row["end_ns"] - row["start_ns"]
            sqlite += child["end_ns"] - child["start_ns"]
            parent = row["parent"]
            labels = []
            while parent is not None:
                ancestor = index[parent]
                labels.append(ancestor["label"])
                parent = ancestor["parent"]
            if "guard" in labels:
                source = "execution_guard"
            elif "recorder_boundary" in labels:
                source = "recorder_boundary"
            else:
                source = "other_explicit_check"
            sources[source] += 1

        groups: dict[tuple[Any, ...], list[int]] = defaultdict(list)
        boundary_kind: Counter[str] = Counter()
        for check in checks:
            time_ns = check.get("diagnostic_authorized_monotonic_ns")
            if time_ns is None or not begin <= time_ns <= finish:
                continue
            boundary = check["checkpoint"]
            key = tuple(
                boundary[k] for k in ("episode_id", "operation_id", "kind", "phase", "physics_step")
            )
            groups[key].append(time_ns)
            boundary_kind[boundary["kind"]] += 1
        gaps: dict[str, list[int]] = defaultdict(list)
        for key, timestamps in groups.items():
            for previous, current in pairwise(timestamps):
                if current <= previous:
                    raise ValueError("successive same-key authorizations did not advance")
                gaps[f"{key[2]}/{key[3]}"].append(current - previous)
        return {
            "owner_checks": sum(sources.values()),
            "source_counts": dict(sorted(sources.items())),
            "owner_check_excluding_sqlite_ns": gross - sqlite,
            "sqlite_ns": sqlite,
            "distinct_guard_keys": len(groups),
            "guard_authorizations": sum(boundary_kind.values()),
            "guard_by_kind": dict(sorted(boundary_kind.items())),
            "repeated_guard_key_gaps": {
                key: {
                    "extra_observations": len(v),
                    "min_ns": min(v),
                    "median_ns": median(v),
                    "max_ns": max(v),
                }
                for key, v in sorted(gaps.items())
            },
        }

    phases = {
        "pre_to_post": ("pre_start", "post_context"),
        "controller": ("dispatch", "executor_return"),
        "hold": ("hold_begin", "hold_end"),
    }
    return {
        "assignment": lifecycle["assignment_id"],
        "inventory_file_sha256": inventory_sha,
        "original_trace_sha256": files["whole-action-timing.json"]["sha256"],
        "original_checks_sha256": files["active-checks.json"]["sha256"],
        "guard_key": ["episode_id", "operation_id", "kind", "phase", "physics_step"],
        "phases": {k: summarize(marks[a]["ns"], marks[b]["ns"]) for k, (a, b) in phases.items()},
        "hold_physics_steps": marks["hold_end"]["physics_step"]
        - marks["hold_begin"]["physics_step"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    print(
        json.dumps(read_groups(parser.parse_args().run), sort_keys=True, indent=2, allow_nan=False)
    )
