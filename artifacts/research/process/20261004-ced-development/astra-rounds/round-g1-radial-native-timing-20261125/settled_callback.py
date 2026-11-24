"""Measure a registered visual callback after the original 120 passive reset steps."""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import resource
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image
from scripts.graduation import dynamic_vision as native
from scripts.graduation import g1_dual_probe as probe
from scripts.graduation import g1_dual_trials as dual
from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation import g1_visibility_trials as trials
from scripts.graduation import g1_visibility_vision as vision
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.perception_io import ROOT, sha, write

from cloud_edge_robot_arm.simulation.mujoco import visual_servo as visual
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

HERE = Path(__file__).resolve().parent
PREVIOUS = (
    HERE.parent / "round-g1-visibility-feedback-deadline-20261125/diagnostics/zero_step_feedback.py"
)
assert sha(PREVIOUS) == "9fea08254c7fc37098baa0a099b535a13c2d173d06df3f887791de84c80abe20"
module = importlib.util.spec_from_file_location("registered_window_instrument", PREVIOUS)
instrument = importlib.util.module_from_spec(module)
module.loader.exec_module(instrument)


class BareWindow:
    def __init__(self, ep, code):
        self.ep, self.code = ep, code
        self.result = None

    def execute_attempt(self, *, contract, step, attempt):
        ep = self.ep
        assert attempt == 1 and step.skill.value == "MOVE_ABOVE" and ep.action_clock.dispatched
        session = ep.robot._visual_servo_session
        assert session is not None and session.vertical_clearance is None
        target = MotionTarget(
            type(ep.robot.get_state().tcp_pose).model_validate(step.parameters["target_pose"]),
            _DOWNWARD,
        )
        controller = visual.MuJoCoVisualServoController(ep.backend)
        initial = controller._validate_target(target)
        scope = dict(
            self=controller,
            session=session,
            target=target,
            current=target,
            initial=initial,
            previous=initial.copy(),
            path=None,
            reference=None,
            site=ep.backend._model.site("tcp").id,
        )
        refusal = None
        try:
            exec(self.code, vars(visual), scope)
        except ValueError as exc:
            if "visual servo sample/IK deadline exceeded" not in str(exc):
                raise
            refusal = str(exc)
        assert scope["solved"] is not None and ep.audit[-1]["shield"]["decision"] == "ALLOW"
        self.result = dict(
            total_ms=1000 * scope["latency"], deadline_refusal=refusal, reached_native_ik=True
        )
        raise instrument.SampleEnded()


def signature(backend):
    d = backend._data
    return hashlib.sha256(
        d.qpos.tobytes() + d.qvel.tobytes() + np.asarray(d.time).tobytes()
    ).hexdigest()


def sample(repo, private, generation, output, mode):
    source, lock = build.verify_build(private, generation)
    assert ROOT == source == Path.cwd() and os.environ["MUJOCO_GL"] == "egl"
    _, old, inventory = trials.template(repo, lock)
    pose = trials.qualified_preflight_pose(repo)
    scene = "g1-radial-diagnostic/" + output.parent.name + "/" + mode
    case = {
        **old["case"],
        **trials.diagnostic_case(scene, "positive", pose["seed"]),
        "physical_object_mass_kg": probe.asset.BODY_MASS_KG,
        "view": "nominal",
        "visual_stages_in_order": trials.STAGES,
    }
    alloc = {
        **old,
        "case": case,
        "runtime_build_sha256": generation,
        "scope": "settled callback diagnostic",
        "component_catalog_sha256": native.digest(inventory),
    }
    output.mkdir()
    write(output / "allocation.json", alloc)
    ep = dual.episode_with_registered_mass(
        output, alloc, sha(output / "allocation.json"), inventory
    )
    complete = False
    try:
        code, source_span = instrument.original_controller_window(visual)
        timer = instrument.Instrument()
        terminal = (
            BareWindow(ep, code)
            if mode == "unprofiled"
            else instrument.ObservationTerminal(ep, timer, code, visual)
        )
        ep.executor.executor = terminal
        ep.backend.initialize(probe.config({"geometry": old["geometry"]}, pose["seed"]))
        x, y, z, yaw = pose["pose_xyzyaw"]
        ep.backend.reset(
            native.PhysicalScenarioConfig(
                scenario_id=scene,
                seed=pose["seed"],
                object_pose=native.Pose(x=x, y=y, z=z),
                object_yaw_rad=yaw,
            )
        )
        assert ep.backend.total_physics_steps == 0 and not ep.backend.command_records
        with (
            bind_scene(scene),
            build.log_measurements() as observations,
            contextlib.ExitStack() as stack,
        ):
            ep.capture("reset")
            ep.phase = "SETTLE"
            with ep.backend.sensor_capture_on_demand():
                ep.backend.step(120)
            assert ep.backend.total_physics_steps == 120 and not ep.backend.command_records
            ep.phase = "BOOTSTRAP"
            ep.bootstrap()
            if mode == "instrumented":
                for owner, name, label in (
                    (ep, "active", "active"),
                    (ep.owner, "current", "lease"),
                    (native, "check_component_hard_state", "hard_state"),
                    (ep, "capture", "capture"),
                    (ep.backend, "capture_sensor_frame", "sensor"),
                    (native, "observation_from_sensor_frame", "rgbd_encode_validate"),
                    (Image.Image, "save", "png_encode"),
                    (native.OpenCVServoFeedback, "update", "provider"),
                    (vision, "measure_frame", "pure_vision"),
                    (vision, "find_grids", "find_grids"),
                    (vision, "_plane", "metric_depth"),
                    (ep, "check_shield", "shield"),
                ):
                    timer.wrap(stack, owner, name, label)
            before = signature(ep.backend)
            try:
                with ep.backend.sensor_capture_on_demand():
                    ep.execute(0)
            except instrument.SampleEnded:
                pass
            else:
                raise ValueError("the diagnostic boundary was not reached")
            assert ep.backend.total_physics_steps == 120 and not ep.backend.command_records
            assert before == signature(ep.backend) and terminal.result
            feedback = ep.frames[-1][2]
            assert ep.frames[-1][1] == "MOVE_ABOVE/feedback"
            obs = observations[feedback.frame_id]
            assert obs["measurement"]["usable"] and obs["callers"] == {"servo_measure": 1}
            write(output / "feedback.rgbd.json", feedback.model_dump(mode="json"))
            record = dict(
                generation=generation,
                mode=mode,
                initial_passive_steps=120,
                measured_callback_physics_steps=0,
                motion_commands=0,
                measured_callback_skill="MOVE_ABOVE",
                calibration=feedback.calibration_version,
                frame_id=feedback.frame_id,
                checksum=feedback.checksum_sha256,
                feedback_file_sha256=sha(output / "feedback.rgbd.json"),
                physical_state_before_and_after_sha256=before,
                source_fragment=source_span,
                measurement=terminal.result,
                load=os.getloadavg(),
                thread_cpu_s=time.thread_time(),
                voluntary_context_switches=resource.getrusage(resource.RUSAGE_SELF).ru_nvcsw,
            )
            write(output / "sample.json", record)
            complete = True
            return record
    finally:
        if not complete:
            write(
                output / "failure.json",
                dict(
                    traceback=traceback.format_exc(),
                    phase=ep.phase,
                    physics_steps=ep.backend.total_physics_steps,
                    commands=native.plain(ep.backend.command_records),
                ),
            )
        status = ep.owner.close(complete)
        write(
            output / "receipt.json",
            dict(
                complete=complete,
                owner=status,
                final_physics_steps=ep.backend.total_physics_steps,
                command_count=len(ep.backend.command_records),
            ),
        )
        ep.backend.shutdown()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo", type=Path)
    p.add_argument("generation")
    p.add_argument("output", type=Path)
    args = p.parse_args()
    store = args.repo / "experiments/results/g1-visibility-pose-repair-20261124"
    args.output.mkdir()
    with trials.device(store):
        rows = [
            sample(args.repo, store, args.generation, args.output / mode, mode)
            for mode in ("unprofiled", "instrumented")
        ]
    write(args.output / "summary.json", dict(source_sha256=sha(Path(__file__)), rows=rows))
    print(json.dumps([r["measurement"]["total_ms"] for r in rows]))
