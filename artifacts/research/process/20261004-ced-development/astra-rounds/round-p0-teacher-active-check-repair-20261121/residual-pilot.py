"""Time the attachment round trip separately from capture, validation and writing."""

import argparse
import base64
import binascii
import hashlib
import json
import statistics
import time
from pathlib import Path

from cloud_edge_robot_arm.research.native_calibration_collection import canonical


def sha(data):
    return hashlib.sha256(data).hexdigest()


def roundtrip(value, emit, prepared=None):
    if prepared is not None and value == prepared[0]:
        emit(prepared[1])
    else:
        raw = base64.b64decode(value, validate=True)
        emit(raw)
        if base64.b64encode(raw).decode("ascii") != value:
            emit(value.encode())
            raise ValueError("noncanonical encoded field retained but not qualified")
    return sha(value.encode())


def control(value, cache):
    def trace(prepared):
        emitted = []
        try:
            out = roundtrip(value, emitted.append, prepared)
        except (binascii.Error, ValueError) as error:
            out = (type(error), str(error))
        return emitted, out

    assert trace(None) == trace(cache)


def samples(root, inventory):
    by_bucket = {"boundary": [], "action": [], "hold": [], "implicit": []}
    indices = range(1, 3386)
    for index in indices:
        name = f"frames/acquisition-{index}/source-frame.json"
        source = json.loads((root / name).read_bytes())
        capture = source["capture_source"]
        role, step = capture["role"], capture["physics_step"]
        if role == "REGISTERED_ACTION_BOUNDARY":
            by_bucket["boundary"].append((name, step))
        elif role == "IMPLICIT_SENSOR_CACHE_UPDATE":
            by_bucket["implicit"].append((name, step))
        elif role == "REGISTERED_PER_PHYSICS_STEP" and 120 < step <= 845:
            by_bucket["action"].append((name, step))
        elif role == "REGISTERED_PER_PHYSICS_STEP" and 845 < step <= 2040:
            by_bucket["hold"].append((name, step))
    rows, receipt = [], []
    for role, group in by_bucket.items():
        count = {"boundary": 3, "action": 11, "hold": 11, "implicit": 11}[role]
        for index in range(count):
            name, step = group[index * (len(group) - 1) // (count - 1)]
            source = json.loads(verified(root, inventory, name))
            payload = dict(source["frame"]["observation_payload"])
            row = []
            for key, filename in source["encoded_fields"].items():
                raw = verified(root, inventory, filename)
                value = base64.b64encode(raw).decode("ascii")
                assert sha(value.encode()) == source["encoded_string_sha256"][key]
                assert sha(raw) == source["frame"]["file_hashes"][filename]
                payload[key] = value
                # The copy simulates a fresh payload object with exact text.
                row.append((value.encode().decode("ascii"), (value, raw)))
            assert sha(canonical(payload)) == source["observation_payload_sha256"]
            rows.append(row)
            receipt.append({"source": name, "bucket": role, "step": step,
                            "payload_sha256": source["observation_payload_sha256"]})
    return rows, receipt


def verified(root, inventory, name):
    raw = (root / name).read_bytes()
    assert inventory[name] == {"bytes": len(raw), "sha256": sha(raw)}
    return raw


def measure(rows, protocol, order):
    results = {}
    limit = json.loads(protocol)["settings"]["raw_bytes"]
    for mode in order:
        start = time.perf_counter_ns()
        totals = []
        for row in rows:
            for value, prepared in row:
                emitted = []
                string_sha = roundtrip(value, emitted.append, prepared if mode == "B" else None)
                totals.append((sha(emitted[0]), string_sha))
        attach_ns = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        bytes_total = 0
        for row in rows:
            for _ in range(len(row) + 2):  # encoded attachments + instances + source metadata
                bytes_total += (
                    json.loads(protocol)["settings"]["raw_bytes"] if mode == "A" else limit
                )
        policy_ns = time.perf_counter_ns() - start
        results[mode] = (attach_ns, policy_ns, totals, bytes_total)
    assert results["A"][2:] == results["B"][2:]
    return {mode: {"attachments_ns": item[0], "budget_lookup_ns": item[1]}
            for mode, item in results.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("originals", type=Path)
    args = parser.parse_args()
    root = args.originals
    inv = (root / "inventory.json").read_bytes()
    original_protocol = (root.parents[1] / "protocol.json").read_bytes()
    protocol = canonical(json.loads(original_protocol)["recipe"])
    attachments, source_rows = samples(root, json.loads(inv)["files"])
    for text in ("YQ==", "YR==", "YQ=!", "Yg=="):
        control(text, ("YQ==", b"a"))
    pairs = [measure(attachments, protocol, order) for order in ("AB", "BA", "BA", "AB")]
    count = len(attachments)
    print(json.dumps({
        "inventory_sha256": sha(inv),
        "release_protocol_sha256": sha(original_protocol),
        "canonical_recipe_sha256": sha(protocol),
        "canonical_recipe_bytes": len(protocol),
        "number_of_frames": count,
        "number_of_sampled_attachments": sum(map(len, attachments)),
        "sampled_frames": source_rows,
        "paired_raw_ns": pairs,
        "median_attachment_saving_ns_per_frame": statistics.median(
            (p["A"]["attachments_ns"] - p["B"]["attachments_ns"]) / count for p in pairs
        ),
        "median_policy_saving_ns_per_frame": statistics.median(
            (p["A"]["budget_lookup_ns"] - p["B"]["budget_lookup_ns"]) / count for p in pairs
        ),
        "scope": "CPU_ONLY_PURE_COMPUTATION_EXCLUDES_CAPTURE_MODEL_AND_WRITE",
        "fallback_cases": 4,
    }, indent=2))


if __name__ == "__main__":
    main()
