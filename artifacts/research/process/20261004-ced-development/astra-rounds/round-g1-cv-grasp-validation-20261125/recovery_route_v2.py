"""Time the amended sweep on two native acquisitions in the parent qualification only."""

from __future__ import annotations

import argparse
import importlib
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

from recovery_boundary import Boundary, Refused
from recovery_native import FROZEN, OLD, PLAN, RAW, ROUND, WORK, Rig, bind_scene, native, trials
from scripts.graduation.perception_io import pinned, sha, write

SUPPLEMENT = ROUND.parent / "round-g1-cv-sweep-route-binding-20261125"
SURFACE = ROUND.parent / "round-g1-general-cv-grasp-20261125"
SUPPLEMENT_SHA = "3548bacb98e5b4196d0ef84e2f31f1c5c49e09a5581455231180e3aa947a1e9c"
V1_SHA = "91c16370bad162c902cd797b4d16517f180f56a9424132613126cb55ef2b31a5"
RUN = RAW / "correctedroute1"
FILES = {
    SUPPLEMENT
    / "route_screen.py": "370f5558af232813ef9d6f20d55cbe23cf833001226b5e0e1c4ae75e8f110fbe",
    SUPPLEMENT
    / "route_geometry.py": "02482108e6a9ea9391b47733b7d742f2d67488e4c917967286d7121589f20362",
    SUPPLEMENT
    / "route_forces.py": "3937019888b63c924f6a8154bb21c2458ca1ee640d50496a972a04163b7210e1",
    ROUND / "sweep_geometry.py": "d81939371f565f39b8274e01d19a6df9780ad1313fa2910edd231e856805cb57",
    ROUND / "sweep_depth.py": "694b0937ceaaa85bcfa43226758d3f2700e1eeb57f29a380afb628e79aab2abb",
    ROUND / "sweep_evaluate.py": "83d0658cb7bfb533f071e1822c66f8dd9185670a79962e98330809fec2f3ae99",
    ROUND / "sweep_start.py": "b3556405b58950224f585a7af156e40de3eb99c64ebe78f11b287c67eee14e2c",
    ROUND / "sweep_replay.py": "22e4b5771516346fdf4fda86b37a2552ed57651940f6547683f7b3080becf502",
    SURFACE
    / "surface_pilot.py": "0f92c4cef4d8b2e9908ee2e21303da78d2a47df94b248e0aefe549c2e42f38b1",
}


def elapsed_windows(times):
    ordered = [
        times[k]
        for k in (
            "action_start",
            "first_start",
            "selected_start",
            "screen_start",
            "screen_end",
            "decision_end",
        )
    ]
    if not all(type(v) is int for v in ordered) or ordered != sorted(ordered):
        raise ValueError("invalid monotonic native decision chronology")
    action, first, selected, screen, finish, decision = ordered
    return dict(
        action_wall_ms=(decision - action) / 1e6,
        initial_capture_to_decision_ms=(decision - first) / 1e6,
        selected_capture_to_decision_ms=(decision - selected) / 1e6,
        initial_capture_to_screen_end_ms=(finish - first) / 1e6,
        selected_capture_to_screen_end_ms=(finish - selected) / 1e6,
        pure_screen_ms=(finish - screen) / 1e6,
    )


def load_screen(folder, *, create):
    source = folder / "source"
    if create:
        source.mkdir()
    sys.path.insert(0, str(source / SUPPLEMENT.name))
    for path, expected in FILES.items():
        target = source / path.parent.name / path.name
        if create:
            assert sha(path) == expected, path
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(path, target)
        assert sha(target) == expected, target
    module = importlib.import_module("route_screen")
    for path in FILES:
        loaded = Path(sys.modules[path.stem].__file__).resolve()
        assert loaded == source / path.parent.name / path.name, loaded
    inventory = {str(path.relative_to(WORK)): h for path, h in FILES.items()}
    for name in (
        "scripts.graduation.g1_visibility_vision",
        "scripts.graduation.g1_visibility_grid",
        "scripts.graduation.g1_dual_observer",
        "cloud_edge_robot_arm.vision.observations",
        "cloud_edge_robot_arm.vision.servo",
        "cloud_edge_robot_arm.simulation.mujoco.visual_servo",
        "cloud_edge_robot_arm.simulation.mujoco.skill_robot",
    ):
        file = Path(sys.modules[name].__file__).resolve()
        assert file.is_relative_to(FROZEN), file
        inventory[str(file.relative_to(WORK))] = sha(file)
    return module.screen_frame, inventory


def probe(rig, name, screen):
    rig.begin_case(name)
    row = rig.case_row
    times = {"action_start": round(rig.started * 1e9)}
    gate = Boundary(rig.key, rig.granted_end, time.monotonic, rig.identity)
    times["first_start"] = time.monotonic_ns()
    times["selected_start"] = times["first_start"]
    initial = rig.acquire(name + "/initial", "no-marker" if name == "full_recovery" else "both")
    row["initial_native_acquisition"] = initial.frame.frame_id

    def acquire_again():
        times["selected_start"] = time.monotonic_ns()
        return rig.acquire(name + "/reobserve")

    def rescreen(event):
        times["screen_start"] = time.monotonic_ns()
        result = screen(
            event.frame,
            rig.ep.geometry,
            FROZEN / rig.ep.geometry["asset_path"],
            robot_measurement=rig.robot_frames[event.frame.frame_id],
        )
        times["screen_end"] = time.monotonic_ns()
        row["sweep"] = result
        if result["selected"] is None:
            raise Refused("current sweep has no executable CLEAR")
        rig.identity()
        if time.monotonic() >= rig.granted_end:
            raise Refused("original action deadline exhausted during full sweep")
        checked = rig.stages(event, selected_table=result)
        if time.monotonic_ns() - times["selected_start"] > 100_000_000:
            raise Refused("whole current capture/screen/IK exceeds original 100 ms")
        return checked

    refusal = None
    try:
        gate.read(
            initial,
            previous=rig.previous,
            validate=rig.validate,
            measure=rig.measure,
            hold=rig.hold,
            stationary=rig.rest,
            capture=acquire_again,
            admit=rescreen,
        )
    except Exception as exc:
        times["decision_end"] = time.monotonic_ns()
        refusal = dict(
            type=type(exc).__name__,
            reason=str(exc),
            origin=traceback.extract_tb(exc.__traceback__)[-1].name,
        )
    else:
        times["decision_end"] = time.monotonic_ns()
    end = times["decision_end"] / 1e9
    native_events = [
        e
        for e in rig.operations[row["operations_before"] :]
        if e["kind"] == "CAPTURE" and e["phase"] == "END"
    ]
    row.update(
        status=gate.status,
        recaptures_attempted=gate.recapture_count,
        refusal=refusal,
        second_request_refusal=None,
        finished_monotonic=end,
        elapsed_wall_s=end - rig.started,
        remaining_original_action_s=rig.granted_end - end,
        physics_end=rig.backend.total_physics_steps,
        commands=native.plain(rig.backend.command_records[row["command_origin"] :]),
        acquisitions=len(rig.events) - row["events_before"],
        actual_skill_dispatches=0,
        native_captures=[e["frame_id"] for e in native_events],
        monotonic_ns=times,
        acquisition_full_window_ms=(times["decision_end"] - times["first_start"]) / 1e6,
    )
    if "screen_end" in times:
        row["windows_ms"] = elapsed_windows(times)
        row["sweep_timing"] = {
            "from_initial_capture_ms": row["windows_ms"]["initial_capture_to_screen_end_ms"],
            "from_selected_capture_ms": row["windows_ms"]["selected_capture_to_screen_end_ms"],
            "native_sample_and_ik_limit_ms": 100.0,
        }
    if "sweep" not in row:
        raise RuntimeError("native qualification did not reach the requested live sweep")


def main():
    parser = argparse.ArgumentParser()
    parser.parse_args()
    pinned(ROUND / "recovery-readback-v1.public.json", V1_SHA)
    for file, digest, key in (
        (ROUND / "plan.json", PLAN, "inputs_sha256"),
        (SUPPLEMENT / "plan.json", SUPPLEMENT_SHA, "input_sha256"),
    ):
        for name, expected in pinned(file, digest)[key].items():
            assert sha(WORK / name) == expected, name
    with trials.device(OLD):
        RUN.mkdir()
        screen, inventory = load_screen(RUN, create=True)
        write(RUN / "dependency-sha256.json", inventory)
        # The earlier reader verifies these selected module hashes against each emitted table.
        write(
            RUN / "screen-sources.json",
            {p.name: h for p, h in FILES.items() if p.parent == SUPPLEMENT},
        )
        for name in (
            "recovery_route_v2.py",
            "recovery_native.py",
            "recovery_boundary.py",
            "test_recovery_route_v2.py",
        ):
            shutil.copyfile(ROUND / name, RUN / "source" / name)
        rig = Rig(RUN)
        with bind_scene(rig.scene):
            try:
                rig.initialize()
                with (
                    rig.backend.observe_operation_boundaries(rig.operation),
                    rig.backend.observe_physics_steps(rig.guard_step),
                    rig.backend.sensor_capture_on_demand(),
                ):
                    rig.backend.step(8)
                    for case in ("full_normal", "full_recovery"):
                        probe(rig, case, screen)
                assert not rig.backend.operation_observer_failures
            except BaseException:
                write(RUN / "exception.json", {"traceback": traceback.format_exc()})
                raise
            finally:
                rig.close()
    write(
        RUN / "run-context.json",
        dict(
            parent_plan_sha256=PLAN,
            supplemental_geometry_plan_sha256=SUPPLEMENT_SHA,
            clock="time.monotonic_ns",
            clock_resolution_s=time.get_clock_info("monotonic").resolution,
            python=platform.python_version(),
            timing_environment="shared machine, original exclusive EGL lock",
            prior_controls_sha256=V1_SHA,
        ),
    )


if __name__ == "__main__":
    main()
