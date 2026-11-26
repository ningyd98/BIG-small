"""Close the timing experiment against the original sealed Q inputs."""

import argparse
import base64
import gzip
import json
from collections import Counter
from io import BytesIO
from statistics import median

import numpy as np
from PIL import Image
from preflight_latency import HERE, PLAN, ROOT, source, verify_inputs

from cloud_edge_robot_arm.vision.observations import RGBDObservation

OUT = ROOT / PLAN["output"]
NATIVE = OUT / "native-01"
VOLATILE = {
    "episode_id",
    "frame_id",
    "checksum_sha256",
    "checksum",
    "observation_id",
    "captured_at",
    "check_ms",
    "capture_to_local_result_ms",
}


def comparable(value):
    if isinstance(value, dict):
        return {k: comparable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [comparable(v) for v in value]
    return value


def packet(folder, row):
    return RGBDObservation.model_validate_json(gzip.decompress((folder / row["path"]).read_bytes()))


def confirm_images(old_root, old, new):
    count = Counter()
    differences = {}
    rgb_key, depth_key, mask_key = ("rgb_png_base64", "depth_float32_base64", "valid_mask_base64")
    marker = source.dwell.optics.sealed_optics()
    old_reset = source.read(old_root / "observable.json")["reset"]
    new_reset = source.read(NATIVE / "observable.json")["reset"]
    old_id, geometry = source.original.reader.fixture(old_reset)
    new_id, new_geometry = source.original.reader.fixture(new_reset)
    source.require(geometry == new_geometry, "confirmed calibration assets changed")
    for before, after in zip(old["slots"], new["slots"], strict=True):
        source.require(
            all(before[k] == after[k] for k in ("role", "seed", "integration_sha256")),
            "source integrated state, role or seed differs",
        )
        left = packet(old_root, before)
        right = packet(NATIVE, after)
        flags = {k: getattr(left, k) == getattr(right, k) for k in (rgb_key, depth_key, mask_key)}
        count.update(k for k, equal in flags.items() if equal)
        if all(flags.values()):
            continue
        source.require(
            before["role"] == "PRE" and flags[depth_key] and flags[mask_key],
            "a timed or history exposure changed its original arrays",
        )
        a, b = (
            np.asarray(Image.open(BytesIO(base64.b64decode(frame.rgb_png_base64))))
            for frame in (left, right)
        )
        ys, xs = np.where(np.any(a != b, axis=2))
        old_marker = marker(left, geometry)
        new_marker = marker(right, geometry)
        source.require(
            comparable(old_marker) == comparable(new_marker)
            and old_id.matches(left, old_marker, geometry, before["robot"]["physics_step"])
            and new_id.matches(right, new_marker, geometry, after["robot"]["physics_step"]),
            "PRE RGB difference changed independent marker or identity result",
        )
        differences["PRE"] = {
            "pixels": [
                dict(uv=[int(x), int(y)], original=a[y, x].tolist(), repeat=b[y, x].tolist())
                for y, x in zip(ys, xs, strict=True)
            ],
            "marker_computation_equal": True,
        }
    return {"rgb": count[rgb_key], "depth": count[depth_key], "mask": count[mask_key]}, differences


def timing_counts(clock, old, current):
    cameras = [span for span in clock["calls"] if span["name"] == "native_rgbd"][-2:]
    gates = [
        span for span in clock["calls"] if span["name"] == "local_preview_including_borrower_close"
    ]
    metrics = {}
    for role, camera, gate in zip(("DWELL-30", "AUDIT"), cameras, gates, strict=True):
        now, old_sample = current["audits"][role], old["audits"][role]
        slot = next(slot for slot in current["slots"] if slot["role"] == role)
        elapsed = now["capture_to_local_result_ms"]
        start, stop = camera["start_ns"], gate["end_ns"]
        spans = [s for s in clock["calls"] if start <= s["start_ns"] < s["end_ns"] <= stop]
        edges = sorted({point for span in spans for point in (span["start_ns"], span["end_ns"])})
        exclusive = Counter()
        for low, high in zip(edges[:-1], edges[1:], strict=True):
            owners = [s for s in spans if s["start_ns"] <= low and high <= s["end_ns"]]
            leaf = min(owners, key=lambda s: s["end_ns"] - s["start_ns"]) if owners else None
            exclusive[leaf["name"] if leaf else "native_boundaries_and_other_work"] += high - low
        source.require(abs(sum(exclusive.values()) / 1e6 - elapsed) < 1, "timing scopes differ")
        metrics[role] = {
            "same_seed_as_previous": slot["seed"],
            "status": now["gate"]["status"],
            "gap_lower_m": now["gate"]["short_motion"]["minimum_gap_m"],
            "original_capture_to_local_ms": old_sample["capture_to_local_result_ms"],
            "candidate_capture_to_local_ms": elapsed,
            "remaining_before_100_ms": 100 - elapsed,
            "candidate_local_gate_ms": now["gate"]["check_ms"],
            "candidate_packet_ms": slot["capture_ms"],
            "exclusive_profile_ms": {name: t / 1e6 for name, t in sorted(exclusive.items())},
        }
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="verify the published bytes in place")
    args = parser.parse_args()
    original = verify_inputs()
    cold = source.read(OUT / "cold-preflight.json")
    clock = source.read(OUT / "timing.json")
    seal = source.read(NATIVE / "capture-seal.json")
    base = source.read(original / "native.json")
    current = source.read(NATIVE / "native.json")
    replay = source.read(OUT / "native-readback.json")
    capture_sha = source.sha(NATIVE / "capture-seal.json")
    source.original.verified_tree(NATIVE, seal["members"])
    source.require(
        clock["complete"]
        and seal["complete"]
        and capture_sha == clock["capture_seal_sha256"] == replay["capture"]
        and current["stats"] == {"camera_requests": 43, "physical_max_error": 0.0}
        and current["slots"][-1]["robot"]["physics_step"] == 5565
        and len(current["slots"]) == len(base["slots"]) == 33
        and current["commands"][-1]["type"] == "gripper"
        and current["commands"][-1]["target_open"]
        and current["commands"][-1]["physics_step"] == 5085
        and clock["actual_robot_reference_projections"] == 2,
        "incomplete or changed native ledger",
    )
    source.require(
        comparable(base["dwell_live"]) == comparable(current["dwell_live"])
        and current["dwell_live"] == replay["dwell"]
        and comparable(base["audits"])
        == comparable(current["audits"])
        == comparable(replay["audits"]),
        "non-timing science fields changed",
    )
    for before, after in zip(
        base["reference_projections"], current["reference_projections"], strict=True
    ):
        source.require(
            before == after
            and before["kind"] == "robot"
            and source.sha(original / before["files"][0]) == source.sha(NATIVE / after["files"][0]),
            "original reference projection changed",
        )
    matches, differences = confirm_images(original, base, current)
    measurements = timing_counts(clock, base, current)
    receipts = {
        name: source.sha(OUT / name)
        for name in (
            "cold-preflight.json",
            "cold-preflight-first-error.txt",
            "postflight-first-errors.txt",
            "registration.json",
            "native-01/capture-seal.json",
            "native-readback.json",
            "timing.json",
        )
    }
    result = {
        "schema": "g1.live-clearance-latency.diagnostic.v1",
        "sha256": receipts,
        "integration_digest_equal_pairs": cold["integration_states"]["identical_pairs"],
        "projection_owner_initialization_ms": clock["resource_startup_ms"],
        "projection_owner_close_ms": clock["resource_close_ms"],
        "reference_projection_arrays_byte_equal": 2,
        "candidate_original_pixel_equality": matches,
        "pixel_differences": differences,
        "semantic_equivalence_to_previous_dwell_and_audits": True,
        "cpu_cold_preflight_observations": 40,
        "cpu_medians_ms": {
            name: {role: median(rows) for role, rows in group.items()}
            for name, group in cold["q_replay"]["cpu_sample_ms"].items()
        },
        "paired_native_timing": measurements,
        "original_lift_stop_audit": cold["lift"],
        "native_physics_steps": 5565,
        "native_camera_requests": 43,
        "native_robot_reference_projections": 2,
        "native_payload_reference_projections": 0,
        "native_isolated_q_episodes": 1,
        "retreat_dispatch": 0,
        "full_live_action_clock_and_ik_qualified": False,
        "whole": 0,
        "formal": 0,
        "independent_formal_scores": 0,
        "remote": 0,
        "hardware": 0,
    }
    output = HERE / "live-clearance-latency.public.json"
    encoded = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if args.verify:
        source.require(output.read_bytes() == encoded, "published derived output differs")
    else:
        with output.open("xb") as stream:
            stream.write(encoded)
    print(source.sha(output))


if __name__ == "__main__":
    main()
