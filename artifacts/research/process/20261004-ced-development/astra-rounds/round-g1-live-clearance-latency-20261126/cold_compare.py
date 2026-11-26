"""Replay the original and session-owned Q reference paths on sealed RGB-D."""

import gzip
import sys
from copy import deepcopy
from hashlib import sha256
from time import perf_counter_ns
from unittest.mock import patch

import cv2
import numpy as np
from latency_components import EpisodeRobotReference
from preflight_latency import (
    HERE,
    PLAN,
    ROOT,
    digest_proof,
    projection_proof,
    source,
    verify_inputs,
)

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def lift_stops():
    # First-refusal record and command/clock audit. Source captures do not
    # contain the pixel arrays from the original reference project calls.
    directory = HERE.parent / "round-g1-lift-native-full-clearance-20261126"
    sys.path.insert(0, str(directory))
    try:
        from read_gate import checked_sources, slot_report

        seal = checked_sources()
        frozen = source.read(directory / "full-clearance.public.json")
        readback = ROOT / "experiments/results/g1-lift-native-full-clearance-20261126/readback.json"
        source.require(
            source.sha(readback) == frozen["readback_sha256"], "wrong LIFT readback seal"
        )
        outcomes = source.plain({case: slot_report(case) for case in seal["cases"]})
        source.require(
            outcomes == source.read(readback)["outcomes"],
            "earliest LIFT stop ledger changed",
        )
        return {
            "original_refusal_and_command_ledger_equal": True,
            "original_pixel_reference_rasters_available": False,
            "cases": sorted(outcomes),
        }
    finally:
        sys.path.remove(str(directory))


def cold_compare(original):
    data = source.read(original / "observable.json")
    expected = source.read(original / "cold-primary.json")
    measure = source.dwell.optics.sealed_optics()
    cert = source.certificate(data["reset"], data["isolation"])
    dwell = []
    endpoints = {}
    class_name = source.clearance.RobotDepthReference
    for slot in data["slots"]:
        if slot["role"] == "PRE":
            continue
        payload = gzip.decompress((original / slot["path"]).read_bytes())
        frame = RGBDObservation.model_validate_json(payload)
        packet = slot["robot"]
        marker = measure(frame, cert.geometry)
        if slot["role"].startswith("DWELL"):
            dwell.append(
                source.plain(cert.observe_payload_frame(frame, marker, packet, "RELEASE", "DWELL"))
            )
        if slot["role"] in expected["audits"]:
            endpoints[slot["role"]] = (frame, packet, marker, deepcopy(cert.payload_history))
    cert.close()
    source.require(dwell == expected["dwell"], "sealed history no longer reconstructs")
    references = {}
    for row in data["reference_projections"]:
        source.require(row["kind"] == "robot" and len(row["files"]) == 1, "unexpected reference")
        array = np.load(original / row["files"][0], allow_pickle=False)
        array.setflags(write=False)
        name = row["role"]
        references[name] = row["args_sha256"], array
    active = None
    calls = 0

    def constructor(instance, asset, width, height):
        source.require(
            source.sha(asset) == data["isolation"]["asset_sha256"]
            and (width, height) == (320, 240),
            "unbound sealed reference",
        )

    def project(instance, joints, fingers):
        nonlocal calls
        expected_args, pixels = references[active]
        source.require(
            source.dwell.digest(source.plain((joints, fingers))) == expected_args,
            "sealed reference projected using wrong encoder",
        )
        calls += 1
        return pixels

    def run(role, implementation):
        nonlocal active
        active = role
        frame, packet, marker, history = endpoints[role]
        trial = source.certificate(data["reset"], data["isolation"])
        if implementation == "borrowed":
            owner.attach(trial)
        before = calls
        start = perf_counter_ns()
        result = source.audit_frame(trial, history, refs, frame, marker, packet, role)
        elapsed = (perf_counter_ns() - start) / 1e6
        del result["gate"]["check_ms"]
        source.require(
            result == expected["audits"][role] and calls == before + 1,
            "changed science fields or wrong optical reference projection count",
        )
        return elapsed

    owner = EpisodeRobotReference(class_name)
    refs = SimpleReferenceRoles()
    samples = {name: {role: [] for role in endpoints} for name in ("original", "borrowed")}
    warmups = PLAN["limits"]["cpu_warmups_per_combination"]
    observations = PLAN["limits"]["cpu_observations_per_combination"]
    with (
        patch.object(class_name, "__init__", constructor),
        patch.object(class_name, "project", project),
        patch.object(class_name, "close", lambda _: None),
    ):
        try:
            for i in range(warmups + observations):
                order = ("original", "borrowed") if i % 2 == 0 else ("borrowed", "original")
                for role in endpoints:
                    for implementation in order:
                        sample = run(role, implementation)
                        if i >= warmups:
                            samples[implementation][role].append(sample)
        finally:
            owner.close()
    source.require(calls == 4 * (warmups + observations), "wrong CPU projection replay count")
    slots = data["slots"]
    (last_event,) = [
        event for event in data["events"] if event.get("frame_id") == slots[-2]["robot"]["frame_id"]
    ]
    fresh = endpoints["AUDIT"][0]
    proof = source.read(source.OLD / "exposure-witness.json")["route"]["shots"][-1]
    try:
        source.check_slot(slots[-2], last_event, fresh, proof)
    except ValueError:
        pass
    else:
        raise ValueError("unexpected same-tick foreign exposure acceptance")
    return {
        "31_frame_history_rebuilt": len(dwell),
        "all_science_fields_equal": True,
        "historical_reference_arrays_reused_cpu_only": True,
        "foreign_same_tick_frame_rejected": True,
        "cpu_sample_ms": samples,
        "cpu_reference_calls": calls,
    }


class SimpleReferenceRoles:
    role = None


def main():
    cv2.setNumThreads(1)
    original = verify_inputs()
    output = ROOT / PLAN["output"] / "cold-preflight.json"
    source.require(not output.exists(), "cold evidence destination already used")
    outcome = {
        "plan_sha256": source.sha(HERE / "plan.json"),
        "source_sha256": {
            name: source.sha(HERE / name)
            for name in ("latency_components.py", "preflight_latency.py", "cold_compare.py")
        },
        "integration_states": digest_proof(original),
        "resource_lifetime": projection_proof(original),
        "lift": lift_stops(),
        "q_replay": cold_compare(original),
        "native_camera_requests": 0,
        "native_physics_steps": 0,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    source.store(output, outcome)
    print(sha256(output.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
