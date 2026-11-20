"""Compare sealed physical values and sensor channels for two measured development actions."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_originals(run: Path) -> tuple[dict, dict, str]:
    directory = run / "originals"
    inventory_raw = (directory / "inventory.json").read_bytes()
    digest = hashlib.sha256(inventory_raw).hexdigest()
    lifecycle = json.loads((run / "collection-result.json").read_bytes())
    if digest != lifecycle["lifecycle_links"]["originals/inventory.json"]:
        raise ValueError("inventory does not match lifecycle")
    items = json.loads(inventory_raw)["files"]
    raw = (directory / "partial-originals.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != items["partial-originals.json"]["sha256"]:
        raise ValueError("unsealed physical originals")
    return json.loads(raw), items, digest


def physical_value(payload: dict[str, Any]) -> str:
    values = {key: value for key, value in payload.items() if key != "episode_id"}
    return json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False)


def channels(raw: dict, entries: dict) -> dict[tuple, dict[str, str]]:
    files: dict[str, dict[str, str]] = defaultdict(dict)
    for name, entry in entries.items():
        parts = name.split("/")
        if (
            len(parts) == 3
            and parts[0] == "frames"
            and parts[2]
            in {
                "rgb.png",
                "depth.f32",
                "instances.i32",
                "mask.u8",
            }
        ):
            files[parts[1]][parts[2]] = entry["sha256"]
    result = {}
    seen: Counter[tuple] = Counter()
    for event in raw["operational_events"]:
        aid = event["acquisition_id"]
        if not aid:
            continue
        role = raw["capture_source_roles"][str(event["operation_id"])]
        key = event["begin_step"], event["end_step"], role["role"]
        seen[key] += 1
        if "rgb.png" not in files[aid] or "depth.f32" not in files[aid]:
            raise ValueError("incomplete recorded frame")
        result[(*key, seen[key])] = files[aid]
    if len(result) != len(raw["allocated_frames"]):
        raise ValueError("allocated frames do not match observation keys")
    return result


def compare(before: Path, after: Path) -> dict:
    old, first_files, first_hash = read_originals(before)
    new, second_files, second_hash = read_originals(after)
    a = {row["physics_step"]: row for row in old["physics"]}
    b = {row["physics_step"]: row for row in new["physics"]}
    physics: dict[str, dict] = {}
    for name in ("control_payload", "post_state_payload"):
        different = [
            k
            for k in sorted(a.keys() & b.keys())
            if physical_value(a[k][name]) != physical_value(b[k][name])
        ]
        physics[name] = {
            "matching_steps": len(a.keys() & b.keys()) - len(different),
            "first_differing_step": different[0] if different else None,
        }
    first = channels(old, first_files)
    second = channels(new, second_files)
    mismatched = [k for k in sorted(first.keys() & second.keys()) if first[k] != second[k]]
    count = Counter(name for values in first.values() for name in values)
    return {
        "inventory_sha256": [first_hash, second_hash],
        "physics_count": [len(a), len(b)],
        "unmatched_physics_steps": len(a.keys() ^ b.keys()),
        "physical_payloads": physics,
        "excluded_physical_field": "episode_id (new worker/episode identity)",
        "capture_key": ["begin_step", "end_step", "source_role", "ordinal_within_key"],
        "capture_count": [len(first), len(second)],
        "unmatched_acquisition_keys": len(first.keys() ^ second.keys()),
        "same_channel_bytes_all_present_modalities": len(first.keys() & second.keys())
        - len(mismatched),
        "first_different_capture_key": mismatched[0] if mismatched else None,
        "first_run_recorded_channel_files": dict(sorted(count.items())),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.before, args.after), sort_keys=True, indent=2))
