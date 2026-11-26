"""Run the original isolated G1 path with one episode-owned reference prebuilt."""

import argparse
import importlib
import json
import math
import os
import sys
from pathlib import Path
from threading import get_ident
from time import perf_counter_ns
from unittest.mock import patch

from scripts.graduation import g1_complete_cv_clearance as clearance
from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
from scripts.graduation.perception_io import read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera

HERE = Path(__file__).resolve().parent
ROOT = next(path for path in HERE.parents if (path / ".git").is_file())
PLAN_PATH = HERE / "plan.json"
PLAN = read(PLAN_PATH)
ORIGINAL_SOURCE = HERE.parent / "round-g1-grid04-lift-tail-and-live-post-20261126"
sys.path.insert(0, str(ORIGINAL_SOURCE))
live = importlib.import_module("capture_handoff_live")
NEW_ROOT = ROOT / PLAN["new_root"]
OUT = NEW_ROOT / PLAN["new_attempt"]


def preflight():
    for relative, expected in PLAN["inputs"].items():
        live.REQUIRE(sha(ROOT / relative) == expected, f"changed live reference input: {relative}")
    history = ROOT / PLAN["old_attempt"]
    old = read(history / "seal.json")
    for name, digest in old["sealed_sha256"].items():
        member = (history / name).resolve()
        live.REQUIRE(
            member.is_relative_to(history) and sha(member) == digest, f"old evidence {name}"
        )
    result = read(
        HERE.parent
        / "round-g1-grid04-carried-reference-startup-20261126/carried-startup.public.json"
    )
    for name, digest in result["raw_sha256"].items():
        live.REQUIRE(
            sha(ROOT / result["private_output"] / name) == digest, f"changed sample: {name}"
        )
    limit = float(PLAN["deadline_ms"])
    live.REQUIRE(
        live.clearance_is_accepted("CLEAR", True)
        and not live.clearance_is_accepted("UNKNOWN", True)
        and not live.clearance_is_accepted("BLOCKED", True)
        and not live.clearance_is_accepted("CLEAR", False)
        and live.feedback_is_timely(limit, limit)
        and not live.feedback_is_timely(limit, math.nextafter(limit, math.inf)),
        "unchanged PRE or live deadline predicates differ",
    )
    return live.preflight(expected_head=PLAN["base_commit"])


class ReferenceRun:
    """Scope one reference and an audited stop to the isolated native episode."""

    def __init__(self):
        self.owner_thread = get_ident()
        self.data = {"camera_calls": 0, "robot_projections": 0, "carried_projections": []}
        self.certificate = None
        self.backend = None
        self.current_robot = None
        self.closed = False
        self.allowed = live.clearance_is_accepted
        self.create = clearance.LocalClearance
        self.project_carried = CarriedSurface.project
        self.project_robot = clearance.RobotDepthReference.project
        self.driver = live.scenario_driver
        self.step = MuJoCoPhysicsBackend.step
        self.reset = MuJoCoPhysicsBackend.reset
        self.capture = MuJoCoRGBDCamera._capture
        self.apply = MuJoCoPhysicsBackend.apply_joint_targets

    def require_thread(self):
        live.REQUIRE(get_ident() == self.owner_thread, "reference crossed thread ownership")

    def scoped_reset(self, backend, *args, **kwargs):
        live.REQUIRE(self.backend is None, "second reset forbidden")
        self.backend = backend
        self.data["reset_start_ns"] = perf_counter_ns()
        result = self.reset(backend, *args, **kwargs)
        self.data["reset_finish_ns"] = perf_counter_ns()
        return result

    def scoped_step(self, backend, steps=1):
        if backend.total_physics_steps + steps > PLAN["stop_tick"]:
            raise live.ScopedStop("research stop before post-2384 physics")
        return self.step(backend, steps=steps)

    def scoped_target(self, backend, *args, **kwargs):
        if backend.total_physics_steps >= PLAN["stop_tick"]:
            raise live.ScopedStop("research stop before command at or after 2384")
        self.data.setdefault("first_target_ns", perf_counter_ns())
        return self.apply(backend, *args, **kwargs)

    def scoped_capture(self, camera, data, *args, **kwargs):
        live.REQUIRE(self.data["camera_calls"] < PLAN["sensor_exposures_limit"], "exposure budget")
        self.data["camera_calls"] += 1
        return self.capture(camera, data, *args, **kwargs)

    def scoped_create(self, *args, **kwargs):
        self.require_thread()
        live.REQUIRE(self.certificate is None, "second carried reference forbidden")
        cert = self.create(*args, **kwargs)
        self.certificate = cert
        identity = cert.optical_identity
        live.REQUIRE(
            self.backend.total_physics_steps == 0
            and identity.episode_id == self.backend._episode_id
            and identity.scene_id == self.backend._scenario.scenario_id
            and cert.asset_sha == identity.asset_sha256
            and cert.calibration_sha == identity.calibration_sha256,
            "warmup must bind actual reset, asset and calibration",
        )
        self.data["episode_id"] = identity.episode_id
        self.data["constructor_start_ns"] = perf_counter_ns()
        cert.carried_surface = CarriedSurface(cert.asset_path)
        self.data["constructor_finish_ns"] = perf_counter_ns()
        check, close = cert.check, cert.close

        def check_current(frame, marker, robot, *args, **kwargs):
            self.require_thread()
            live.REQUIRE(frame.episode_id == identity.episode_id, "reference cannot cross episode")
            self.current_robot = robot
            return check(frame, marker, robot, *args, **kwargs)

        def close_once():
            if not self.closed:
                self.require_thread()
                self.closed = True
                start = perf_counter_ns()
                try:
                    close()
                finally:
                    self.data["close_elapsed_ms"] = (perf_counter_ns() - start) / 1e6

        cert.check = check_current
        cert.close = close_once
        return cert

    def scoped_carried(self, model, *args, **kwargs):
        self.require_thread()
        projections = self.data["carried_projections"]
        live.REQUIRE(
            len(projections) < PLAN["carried_reference_projection_limit"]
            and self.current_robot is not None
            and model is self.certificate.carried_surface,
            "reference projection budget or ownership",
        )
        entry = {
            "step": self.current_robot["physics_step"],
            "frame_id": self.current_robot["frame_id"],
            "checksum": self.current_robot["checksum_sha256"],
            "projection_start_ns": perf_counter_ns(),
        }
        projections.append(entry)
        result = self.project_carried(model, *args, **kwargs)
        entry["projection_finish_ns"] = perf_counter_ns()
        return result

    def scoped_robot(self, model, *args, **kwargs):
        live.REQUIRE(
            self.data["robot_projections"] < PLAN["robot_reference_projection_limit"],
            "robot reference projection budget",
        )
        self.data["robot_projections"] += 1
        return self.project_robot(model, *args, **kwargs)

    def allowed_or_cutoff(self, status, clocks_match):
        allowed = self.allowed(status, clocks_match)
        if allowed:
            current = self.current_robot["physics_step"]
            if current >= PLAN["stop_tick"] or self.data["carried_projections"]:
                raise live.ScopedStop(f"research cutoff after preserved frame verdict at {current}")
        return allowed

    def scoped_driver(self, *args):
        call = self.driver(*args)

        def run(*args, **kwargs):
            try:
                return call(*args, **kwargs)
            finally:
                try:
                    if self.certificate is not None and not self.closed:
                        self.certificate.close()
                finally:
                    self.data["closed"] = self.closed
                    write(OUT / "reference-resource.json", self.data)

        return run

    def run(self, context):
        # Bind the unbound dispatch wrapper explicitly. The backend and renderer
        # methods keep their original call signatures and admission checks.
        def backend_reset(backend, *args, **kw):
            return self.scoped_reset(backend, *args, **kw)

        def backend_step(backend, *args, **kw):
            return self.scoped_step(backend, *args, **kw)

        def backend_target(backend, *args, **kw):
            return self.scoped_target(backend, *args, **kw)

        def camera_sample(camera, *args, **kw):
            return self.scoped_capture(camera, *args, **kw)

        def carried_project(reference, *args, **kw):
            return self.scoped_carried(reference, *args, **kw)

        def robot_project(reference, *args, **kw):
            return self.scoped_robot(reference, *args, **kw)

        with (
            patch.multiple(
                live,
                OUT=OUT,
                ISOLATED_ID="grid04-live-carried-prebuild-01",
                clearance_is_accepted=self.allowed_or_cutoff,
                scenario_driver=self.scoped_driver,
            ),
            patch.object(clearance, "LocalClearance", self.scoped_create),
            patch.object(clearance.RobotDepthReference, "project", robot_project),
            patch.object(CarriedSurface, "project", carried_project),
            patch.multiple(
                MuJoCoPhysicsBackend,
                reset=backend_reset,
                step=backend_step,
                apply_joint_targets=backend_target,
            ),
            patch.object(MuJoCoRGBDCamera, "_capture", camera_sample),
        ):
            live.run(
                context,
                second_registration={
                    "plan_sha256": sha(PLAN_PATH),
                    "runner_sha256": sha(Path(__file__)),
                    "old_seal_sha256": sha(ROOT / PLAN["old_attempt"] / "seal.json"),
                    "budgets": {key: val for key, val in PLAN.items() if key.endswith("_limit")},
                },
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "run"))
    args = parser.parse_args()
    if args.mode == "preflight":
        print(json.dumps({"pinned_inputs": bool(preflight()), "reset": 0, "exposures": 0}))
    else:
        live.REQUIRE(
            os.environ["MUJOCO_GL"] == os.environ["PYOPENGL_PLATFORM"] == "egl", "EGL required"
        )
        ReferenceRun().run(preflight())


if __name__ == "__main__":
    main()
