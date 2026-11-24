"""Time the registered MOVE_ABOVE callback and native inverse-kinematics branch at step zero.

The timing-only executor ends at the original deadline check. It never passes a command to
SkillExecutor. Run the external instrument inside each immutable development source tree.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import fcntl
import gzip
import hashlib
import inspect
import json
import math
import os
import re
import subprocess
import sys
import textwrap
import time
import traceback
from pathlib import Path
from unittest.mock import patch

BASE = "7288cdc81e830f5282eb7d82d49d46d077e2593d0f96480960385463b850b9e9"
PROJECT = Path("experiments/results/g1-visibility-pose-repair-20261124")
CONTROLLER_SHA = "71218ee666b8b90772cc9e3a03bab93c45c57d3ae6017c8ec734e9dd3fb13ff8"
SCRIPT = Path(__file__).resolve()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with path.open("x", encoding="utf8") as out:
        json.dump(data, out, allow_nan=False, ensure_ascii=False, sort_keys=True, indent=2)
        out.write("\n")


def emit(value):
    print(json.dumps(value, allow_nan=False), flush=True)


def stats(values):
    ordered = sorted(values)

    def percentile(q):
        ix = (len(ordered) - 1) * q
        low, high = math.floor(ix), math.ceil(ix)
        return ordered[low] + (ordered[high] - ordered[low]) * (ix - low)

    return {"n": len(ordered), "p50": percentile(0.5), "p95": percentile(0.95), "max": ordered[-1]}


def original_controller_window(module):
    file = Path(inspect.getfile(module.MuJoCoVisualServoController))
    assert sha(file) == CONTROLLER_SHA
    source = file.read_text()
    lines = source.splitlines(keepends=True)
    # The exact contiguous block begins before session.sample and ends after the unmodified
    # deadline rejection. The disjoint solve check, pose-error accounting and motion follow it.
    (node,) = [
        n
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.If) and ast.unparse(n.test) == "elapsed >= next_vision"
    ]
    start = node.body[0]
    (stop,) = [
        n
        for n in node.body
        if isinstance(n, ast.If)
        and ast.unparse(n.test) == "latency > session.config.max_sample_latency_s"
    ]
    fragment = textwrap.dedent("".join(lines[start.lineno - 1 : stop.end_lineno]))
    assert fragment.startswith(
        "sampled_at = time.perf_counter()\ncurrent = session.sample(current)"
    )
    assert (
        "_inverse_kinematics(" in fragment
        and ".step(" not in fragment
        and ".apply_" not in fragment
    )
    code = compile(fragment, str(file), "exec")
    signature = {
        "source": str(file.relative_to(Path.cwd())),
        "source_sha256": sha(file),
        "first_line": start.lineno,
        "last_line": stop.end_lineno,
        "fragment_sha256": hashlib.sha256(fragment.encode()).hexdigest(),
    }
    return code, signature


class Instrument:
    def __init__(self):
        self.current = None

    def timed(self, name, original):
        def call(*args, **kwargs):
            row = self.current
            if row is None:
                return original(*args, **kwargs)
            start = time.perf_counter_ns()
            try:
                return original(*args, **kwargs)
            finally:
                row.setdefault(name, []).append(time.perf_counter_ns() - start)

        return call

    def wrap(self, stack, obj, attr, key):
        stack.enter_context(patch.object(obj, attr, self.timed(key, getattr(obj, attr))))


class SampleEnded(Exception):
    """Ends a diagnostic receipt without dispatching an actuator or advancing the clock."""


class ObservationTerminal:
    def __init__(self, episode, timer, controller_code, visual):
        self.episode, self.timer = episode, timer
        self.code, self.visual = controller_code, visual
        self.result = None

    def execute_attempt(self, *, contract, step, attempt):

        from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MotionTarget
        from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

        ep, visual = self.episode, self.visual
        assert attempt == 1 and step.skill.value == "MOVE_ABOVE" and ep.action_clock.dispatched
        session = ep.robot._visual_servo_session
        assert session is not None and session.vertical_clearance is None
        initial = type(ep.robot.get_state().tcp_pose).model_validate(step.parameters["target_pose"])
        target = MotionTarget(initial, _DOWNWARD)
        controller = visual.MuJoCoVisualServoController(ep.backend)
        orig = controller._validate_target(target)
        # MOVE_ABOVE uses the unconstrained IK branch, see MuJoCoSkillRobot._move.
        local = dict(
            self=controller,
            session=session,
            target=target,
            current=target,
            initial=orig,
            previous=orig.copy(),
            path=None,
            reference=None,
            site=ep.backend._model.site("tcp").id,
        )
        row = {}
        msg = None
        with contextlib.ExitStack() as wrap:
            self.timer.wrap(wrap, type(contract), "model_copy", "contract_copy")
            self.timer.wrap(wrap, type(step), "model_copy", "step_copy")
            self.timer.wrap(wrap, controller, "_validate_target", "target_validation")
            self.timer.wrap(wrap, controller.kinematics, "_inverse_kinematics", "native_ik")
            self.timer.current = row
            try:
                exec(self.code, vars(visual), local)
            except ValueError as exc:
                msg = str(exc)
                if not re.fullmatch(r"visual servo sample/IK deadline exceeded \(\d+\.\d+s\)", msg):
                    raise
            finally:
                self.timer.current = None

        assert "solved" in local and local["solved"] is not None and len(row["native_ik"]) == 1
        assert len(row["lease"]) == len(row["hard_state"]) == len(row["active"]) == 2
        assert all(
            len(row[k]) == 1
            for k in (
                "capture",
                "sensor",
                "rgbd_encode_validate",
                "provider",
                "step_copy",
                "contract_copy",
                "shield",
                "target_validation",
            )
        )
        fixed = [
            "active",
            "capture",
            "provider",
            "step_copy",
            "contract_copy",
            "shield",
            "native_ik",
        ]
        ns = local["latency"] * 1e9
        self.result = {
            "total_ms": ns / 1e6,
            "deadline_refusal": msg,
            "reached_native_ik": True,
            "ik_joint_positions_rad": local["solved"].tolist(),
            "measured_target_m": local["current"].position.model_dump(),
            "milliseconds": {k: [x / 1e6 for x in items] for k, items in row.items()},
            "window_less_provider_ms": (ns - sum(row["provider"])) / 1e6,
            "window_less_pure_vision_ms": (ns - sum(row["pure_vision"])) / 1e6,
            "target_checks_and_callback_glue_ms": (ns - sum(sum(row[k]) for k in fixed)) / 1e6,
            "window_before_ik_ms": (ns - sum(row["native_ik"])) / 1e6,
            "genuine_shield": ep.audit[-1],
        }
        assert self.result["genuine_shield"]["phase"] == "FEEDBACK"
        assert self.result["genuine_shield"]["shield"]["decision"] == "ALLOW"
        raise SampleEnded()


def worker(args):
    import numpy as np
    from PIL import Image
    from scripts.graduation import dynamic_vision as native
    from scripts.graduation import g1_dual_probe as probe
    from scripts.graduation import g1_dual_trials as dual
    from scripts.graduation import g1_visibility_grid as grid
    from scripts.graduation import g1_visibility_runtime as build
    from scripts.graduation import g1_visibility_trials as trials
    from scripts.graduation import g1_visibility_vision as vision
    from scripts.graduation.g1_formal_runtime import bind_scene

    from cloud_edge_robot_arm.simulation.mujoco import visual_servo as visual
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    repo, output = args.repo, args.output
    source, lock = build.verify_build(repo / PROJECT, args.generation)
    assert Path.cwd() == source
    assert (
        sha(inspect.getfile(native))
        == "1c0a069f578e3107c473566db4fb607b3bfab919e6df4faa157aa84dd503665e"
    )
    assert os.environ["MUJOCO_GL"] == "egl"
    first, old, catalog = trials.template(repo, lock)
    pose = trials.qualified_preflight_pose(repo)
    assert pose["pose_xyzyaw"] == [0.45, 0, 0.035, 0] and first["arm"] == "dual"
    output.mkdir()
    scene = "g1-deadline-qualification/" + output.parent.name + "/" + args.label
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
        "runtime_build_sha256": args.generation,
        "scope": "diagnostic zero step timing",
        "component_catalog_sha256": native.digest(catalog),
    }
    write(output / "allocation.json", alloc)
    ep = dual.episode_with_registered_mass(output, alloc, sha(output / "allocation.json"), catalog)
    complete = False
    rows = []
    try:
        controller_code, signature = original_controller_window(visual)
        timer = Instrument()
        terminal = ObservationTerminal(ep, timer, controller_code, visual)
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
        assert not ep.backend.command_records and ep.backend.total_physics_steps == 0

        # Sensor shutdown after every native on-demand scope can render one unscored frame.
        # Retain the camera packets that actually enter registration, PRE, and each timed callback.
        def state_signature():
            data = ep.backend._data
            return hashlib.sha256(
                data.qpos.tobytes() + data.qvel.tobytes() + np.asarray(data.time).tobytes()
            ).hexdigest()

        state = state_signature()
        with (
            bind_scene(scene),
            build.log_measurements() as measured,
            contextlib.ExitStack() as stack,
        ):
            for obj, attr, key in (
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
                timer.wrap(stack, obj, attr, key)
            if hasattr(grid, "_verify"):
                timer.wrap(stack, grid, "_verify", "grid_refinement")
            original_validate = RGBDObservation.model_validate

            def validate(cls, *a, **kwargs):
                return timer.timed("rgbd_model_validate", original_validate)(*a, **kwargs)

            stack.enter_context(
                patch.object(RGBDObservation, "model_validate", classmethod(validate))
            )
            emit({"ready": True, "generation": args.generation, "controller": signature})
            for message in sys.stdin:
                sample_id = message.strip()
                if sample_id == "close":
                    complete = True
                    break
                assert re.fullmatch(r"[0-9]{3}", sample_id)
                folder = output / sample_id
                folder.mkdir()
                stage = len(ep.frames)
                ep.pending_dispatch = ep.action_clock = ep.action = None
                ep.phase = "BOOTSTRAP"
                ep.bootstrap()
                try:
                    # This is the actual registered R2 action-clock entrance and FEEDBACK closure.
                    # Its innermost executor is the no-command observation terminal above.
                    with ep.backend.sensor_capture_on_demand():
                        ep.execute(0)
                except SampleEnded:
                    pass
                else:
                    raise RuntimeError("diagnostic terminal was not visited")
                assert ep.backend.total_physics_steps == 0 and not ep.backend.command_records
                assert state == state_signature()
                before_pre = ep.report["actions"][0]["pre"]
                assert all(v["status"] == "PASS" for v in before_pre["conditions"])
                assert before_pre["shield"]["allowed"] and before_pre["shield"]["unmodified"]
                sample = terminal.result
                captures = []
                for _, role, frame in ep.frames[stage:]:
                    coded = frame.model_dump_json().encode()
                    path = folder / (str(len(captures)) + ".rgbd.json.gz")
                    with path.open("xb") as out:
                        out.write(gzip.compress(coded, compresslevel=1, mtime=0))
                    captures.append(
                        dict(
                            role=role,
                            frame_id=frame.frame_id,
                            checksum=frame.checksum_sha256,
                            file=path.name,
                            file_sha256=sha(path),
                            captured_at=frame.captured_at.isoformat(),
                            calibration=frame.calibration_version,
                            original_sim_time=frame.sim_time_s,
                        )
                    )
                current = ep.frames[-1][2]
                assert ep.frames[-1][1] == "MOVE_ABOVE/feedback"
                obs = measured[current.frame_id]
                assert obs["callers"] == {"servo_measure": 1} and obs["measurement"]["usable"]
                sample.update(
                    sample=sample_id,
                    generation=args.generation,
                    cold_session=sample_id == "000",
                    frame_id=current.frame_id,
                    checksum=current.checksum_sha256,
                    current_observer=obs,
                    captures=captures,
                    native_pre=before_pre,
                    clock_epoch=ep.context_rows[-1],
                    phys_state_sha=state,
                    physics_steps=ep.backend.total_physics_steps,
                    actual_command_records=ep.backend.command_records,
                )
                write(folder / "sample.json", sample)
                rows.append(
                    {
                        "sample": sample_id,
                        "sha256": sha(folder / "sample.json"),
                        "total_ms": sample["total_ms"],
                        "current_vision_ms": sum(sample["milliseconds"]["pure_vision"]),
                    }
                )
                emit(rows[-1])
    except BaseException:
        write(
            output / "failure.json",
            dict(
                traceback=traceback.format_exc(),
                rows=rows,
                frames=[
                    dict(role=k, frame_id=f.frame_id, checksum=f.checksum_sha256, step=s)
                    for s, k, f in ep.frames
                ],
                phase=ep.phase,
                last_actions=ep.report["actions"][:1],
                commands=ep.backend.command_records,
                physics_steps=ep.backend.total_physics_steps,
            ),
        )
        raise
    finally:
        closed = ep.owner.close(complete)
        write(
            output / "receipt.json",
            dict(
                complete=complete,
                rows=rows,
                owner=closed,
                final_physics_steps=ep.backend.total_physics_steps,
                final_command_records=ep.backend.command_records,
            ),
        )
        ep.backend.shutdown()


def launch(args):
    import shutil

    private = args.repo / PROJECT
    args.output.mkdir()
    assert shutil.disk_usage(private).free >= 16 * 2**30
    commands = {}
    sign = {}
    rows = []
    order = {}
    with contextlib.ExitStack() as stack:
        for name in ("feedback-deadline-performance.lock", "egl.lock"):
            lock = stack.enter_context((private / name).open("a"))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        procs = {}
        for label, generation in (("baseline", BASE), ("candidate", args.candidate)):
            if generation is None:
                continue
            tree = private / "builds" / generation / "runtime-source"
            assert sha(tree / "runtime-build.json") == generation
            command = [
                sys.executable,
                "-B",
                "-c",
                "import runpy,sys;runpy.run_path(sys.argv.pop(1),run_name='__main__')",
                str(SCRIPT),
                "worker",
                str(args.repo),
                str(args.output / label),
                generation,
                label,
            ]
            commands[label] = command
            p = subprocess.Popen(
                command,
                cwd=tree,
                env={
                    **os.environ,
                    "MUJOCO_GL": "egl",
                    "PYTHONPATH": os.pathsep.join(map(str, (tree, tree / "src"))),
                },
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stack.enter_context((args.output / (label + ".stderr")).open("x")),
                text=True,
                bufsize=1,
            )
            procs[label] = p
            received = p.stdout.readline()
            if not received:
                raise RuntimeError(label + " worker startup failed")
            sign[label] = json.loads(received)
            assert sign[label]["ready"]
        try:
            for index in range(args.count):
                names = list(procs) if index % 2 == 0 else list(procs)[::-1]
                order[index] = names
                for label in names:
                    proc = procs[label]
                    proc.stdin.write(f"{index:03d}\n")
                    proc.stdin.flush()
                    line = proc.stdout.readline()
                    if not line:
                        raise RuntimeError(label + " sample failed; see preserved receipt")
                    rows.append({"label": label, **json.loads(line)})
        finally:
            for proc in procs.values():
                if proc.poll() is None:
                    proc.stdin.write("close\n")
                    proc.stdin.flush()
                proc.stdin.close()
                proc.wait()
        assert all(p.returncode == 0 for p in procs.values())
    summary = {}
    for label in procs:
        samples = [
            json.loads((args.output / label / r["sample"] / "sample.json").read_text())
            for r in rows
            if r["label"] == label
        ]
        for name, subset in (("all", samples), ("cold", samples[:1]), ("warm", samples[1:])):
            if not subset:
                continue
            stages = {
                k: stats([sum(s["milliseconds"].get(k, [])) for s in subset])
                for k in sorted({k for s in subset for k in s["milliseconds"]})
            }
            entry = {
                k: stats([s[k] for s in subset])
                for k in (
                    "total_ms",
                    "window_less_provider_ms",
                    "window_less_pure_vision_ms",
                    "target_checks_and_callback_glue_ms",
                )
            }
            entry["component_ms"] = stages
            entry["native_over_100ms"] = sum(s["deadline_refusal"] is not None for s in subset)
            entry["budget_pass"] = entry["total_ms"]["p95"] <= 80 and entry["total_ms"]["max"] <= 90
            summary.setdefault(label, {})[name] = entry
    write(
        args.output / "summary.json",
        dict(
            scope="independent zero-physics-step registration and native sample window",
            script_sha256=sha(SCRIPT),
            interpreter_sha256=sha(sys.executable),
            commands=commands,
            ready=sign,
            rows=rows,
            sample_order=order,
            results=summary,
            cpus=sorted(os.sched_getaffinity(0)),
            load=os.getloadavg(),
            actual_d02_step672=False,
            actuator_commands=0,
            physics_steps=0,
        ),
    )
    print(json.dumps({label: data["all"]["total_ms"] for label, data in summary.items()}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="kind", required=True)
    for name in ("run", "worker"):
        q = sub.add_parser(name)
        q.add_argument("repo", type=lambda x: Path(x).resolve())
        q.add_argument("output", type=lambda x: Path(x).resolve())
        if name == "run":
            q.add_argument("--candidate")
            q.add_argument("--count", type=int, default=12)
        else:
            q.add_argument("generation")
            q.add_argument("label")
    args = p.parse_args()
    if args.kind == "run":
        assert 1 <= args.count <= 50
        launch(args)
    else:
        worker(args)


if __name__ == "__main__":
    main()
