"""One registered original Q replay with isolated reference resource reuse."""

import argparse
import os
from contextlib import ExitStack, contextmanager
from time import perf_counter_ns
from unittest.mock import patch

import cv2
from latency_components import INTEGRATION_FIELD, EpisodeRobotReference, integration_sha256
from preflight_latency import HERE, PLAN, ROOT, source, verify_inputs

OUT = ROOT / PLAN["output"]
NATIVE = OUT / "native-01"


def verified_preflight():
    verify_inputs()
    path = OUT / "cold-preflight.json"
    data = source.read(path)
    source.require(
        data["plan_sha256"] == source.sha(HERE / "plan.json")
        and all(source.sha(HERE / name) == hash_ for name, hash_ in data["source_sha256"].items())
        and data["q_replay"]["all_science_fields_equal"]
        and data["lift"]["original_refusal_and_command_ledger_equal"]
        and data["integration_states"]["identical_pairs"] == 10
        and data["native_camera_requests"] == data["native_physics_steps"] == 0,
        "semantic preflight absent or not tied to the live candidate",
    )
    return source.sha(path)


def profile_call(original, name, records):
    def measured(*args, **kwargs):
        t0 = perf_counter_ns()
        try:
            return original(*args, **kwargs)
        finally:
            records.append({"name": name, "start_ns": t0, "end_ns": perf_counter_ns()})

    return measured


def live():
    preflight = verified_preflight()
    source.require(
        not NATIVE.exists() and not (OUT / "registration.json").exists(), "attempt consumed"
    )
    source.require(
        os.environ.get("MUJOCO_GL") == os.environ.get("PYOPENGL_PLATFORM") == "egl", "EGL required"
    )
    source.store(
        OUT / "registration.json",
        {
            "plan_sha256": source.sha(HERE / "plan.json"),
            "extra_program_sha256": source.sha(HERE / "live_compare.py"),
            "preflight_sha256": preflight,
            "limits": PLAN["limits"],
            "thread_configuration": {
                name: os.environ.get(name)
                for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MUJOCO_GL")
            },
            "cpu_affinity": sorted(os.sched_getaffinity(0)),
            "retreat_dispatch": False,
        },
    )
    records = []
    owner = EpisodeRobotReference()
    base_configure, base_device, base_cert = (
        source.configure,
        source.native.device,
        source.certificate,
    )
    base_detector = source.dwell.optics.sealed_optics

    def configure():
        args = base_configure()
        terminal = args[0][0]
        original = terminal.integration_digest

        def scoped_digest(backend, mj):
            if backend.total_physics_steps == source.STEPS["common"]:
                return original(backend, mj)
            return {INTEGRATION_FIELD: integration_sha256(backend, mj)}

        terminal.integration_digest = profile_call(scoped_digest, "integration_identity", records)
        return args

    @contextmanager
    def device(private):
        with base_device(private):
            try:
                yield
            finally:
                owner.close()

    def certificate(observable, isolation):
        cert = base_cert(observable, isolation)
        owner.attach(cert)
        return cert

    def detector():
        return profile_call(base_detector(), "current_marker", records)

    instrument = [
        (source.native.MuJoCoRGBDCamera, "_capture", "native_rgbd"),
        (source.native, "observation_from_sensor_frame", "packet_encoding"),
        (source, "check_slot", "clock_and_encoder_witness"),
        (source, "audit_frame", "local_preview_including_borrower_close"),
        (source, "entry_check", "complete_local_gate"),
        (source.clearance.LocalClearance, "observe_payload_frame", "current_pose_and_history"),
        (source.clearance.LocalClearance, "changed_surfaces", "surface_attribution"),
        (source.clearance, "handoff_motion", "handoff_and_volume"),
        (source.clearance.RobotDepthReference, "project", "new_reference_projection"),
        (source.clearance.LocalClearance, "close", "diagnostic_certificate_close"),
    ]
    complete = False
    try:
        with ExitStack() as patches:
            patches.enter_context(patch.object(source, "OUT", NATIVE))
            patches.enter_context(
                patch.object(source, "PLAN", source.PLAN | {"baseline": PLAN["baseline"]})
            )
            patches.enter_context(patch.object(source, "configure", configure))
            patches.enter_context(patch.object(source.native, "device", device))
            patches.enter_context(patch.object(source, "certificate", certificate))
            patches.enter_context(patch.object(source.dwell.optics, "sealed_optics", detector))
            for obj, method, name in instrument:
                wrapper = profile_call(getattr(obj, method), name, records)
                patches.enter_context(patch.object(obj, method, wrapper))
            source.live()
        source.require(owner.closed and owner.projections == 2, "reference lifetime did not close")
        complete = True
    finally:
        source.store(
            OUT / "timing.json",
            {
                "complete": complete,
                "calls": records,
                "resource_startup_ms": owner.startup_ms,
                "resource_close_ms": owner.close_ms,
                "actual_robot_reference_projections": owner.projections,
                "capture_seal_sha256": (
                    source.sha(NATIVE / "capture-seal.json")
                    if (NATIVE / "capture-seal.json").is_file()
                    else None
                ),
            },
        )


def cold():
    verified_preflight()
    source.require(source.read(OUT / "timing.json")["complete"], "incomplete native timing trial")
    with patch.object(source, "OUT", NATIVE):
        source.cold(OUT / "native-readback.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("live", "cold"))
    args = parser.parse_args()
    cv2.setNumThreads(1)
    if args.mode == "live":
        live()
    else:
        cold()


if __name__ == "__main__":
    main()
