"""Acquire single-attempt development trajectories using the G1 registered eight-skill worker."""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation import g1_visibility_runtime as build
from scripts.graduation.g1_formal_runtime import bind_scene, require
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

STAGES = [
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
]
RELEASE = "g1-visibility-pose-repair-20261124"
FIELDS = ("id", "seed", "reset_fixture_center_m", "yaw_rad")


def placements_from_old(repo):
    plan = read(repo / build.PREVIOUS / "plan.json")
    return pinned(repo / build.DEVELOPMENT, plan["input_sha256"][build.DEVELOPMENT.as_posix()])[
        "cases"
    ]


def training_placements(names, old):
    require(names and len(set(names)) == len(names), "empty or duplicate training placement")
    result = []
    lookup = {row["id"]: row for row in old if row["arm"] == "dual"}
    for name in names:
        require(
            re.fullmatch(r"d0[1-4]", name) and name + "-dual" in lookup,
            "a historical dual development placement is required",
        )
        row = lookup[name + "-dual"]
        result.append({**{k: row[k] for k in FIELDS}, "id": name})
    return checked_placements(result, "training")


def checked_placements(rows, scope):
    valid = ("training", "evaluation")
    require(scope in valid and rows, "invalid development assignment")
    if scope == "evaluation":
        require(
            [r["id"] for r in rows] == [f"e{i:02d}" for i in range(1, 5)],
            "four prospectively ordered development placements required",
        )
    for row in rows:
        xyz = row["reset_fixture_center_m"]
        require(
            set(row) == set(FIELDS)
            and re.fullmatch(r"[de]0[1-4]", row["id"])
            and type(row["seed"]) is int
            and row["seed"] >= 0
            and isinstance(xyz, list)
            and len(xyz) == 3
            and all(type(v) in (float, int) and math.isfinite(v) for v in (*xyz, row["yaw_rad"]))
            and xyz[2] == 0.035,
            "invalid static development placement",
        )
    for key in ("id", "seed", "reset_fixture_center_m"):
        values = [tuple(r[key]) if key == "reset_fixture_center_m" else r[key] for r in rows]
        require(len(set(values)) == len(rows), "duplicate placement, identity or seed")
    return rows


def training_success(row):
    physical = row.get("independent_physical_outcome", {})
    windows = row.get("registered_windows", {})
    return (
        row.get("evidence_status") == "SCORED"
        and row.get("verified_posts") == 8
        and row.get("dispatched") == 8
        and all(
            row.get(key) is True
            for key in (
                "online_success",
                "physical_success",
                "joint_success",
                "both_windows_qualified",
            )
        )
        and physical.get("success") is True
        and physical.get("safety_assessment") == "SCOPED_NO_VIOLATION"
        and physical.get("measured_lift_m", 0) >= 0.05
        and physical.get("hold_s", 0) >= 0.5
        and physical.get("placed_stable_s", 0) >= 1
        and all(windows.get(k, {}).get("qualified") is True for k in ("lift", "release"))
        and row.get("contacts", {}).get("bilateral_cube_steps", 0) > 0
        and row.get("hand_contacts", {}).get("board_or_support_hand_or_finger_steps") == []
    )


def reserve_attempt(path, fields):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(fields, stream, sort_keys=True, allow_nan=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return sha(path)


@contextmanager
def device(private):
    require(os.environ.get("MUJOCO_GL") == "egl", "registered MuJoCo EGL is required")
    with (private / "egl.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def batch_path(private, label):
    require(
        label == "evaluation" or re.fullmatch(r"train-[a-z0-9][a-z0-9-]{0,40}", label),
        "use evaluation or a new train- batch label",
    )
    directory = private / "batches" / label
    require(directory.resolve() == directory, "development batch path traverses a symbolic link")
    return directory


def template(repo, lock):
    from scripts.graduation import g1_dual_trials as dual

    old = repo / build.PARENT / "trials"
    table = pinned(
        old / "allocation.json", sha(repo / build.PREVIOUS / "trial-allocation.public.json")
    )
    first = next(row for row in table["cases"] if row["arm"] == "dual")
    previous = pinned(old / first["allocation_file"], first["allocation_sha256"])
    old_geometry = previous["geometry"]
    geometry = dual.runtime.geometry_registration(marker_family_id=first["family"])
    descriptors = [g["development_dual"] for g in (old_geometry, geometry)]
    variable = {"development_sources_sha256", "development_source_generation"}
    require(
        {k: v for k, v in old_geometry.items() if k != "development_dual"}
        == {k: v for k, v in geometry.items() if k != "development_dual"}
        and {k: v for k, v in descriptors[0].items() if k not in variable}
        == {k: v for k, v in descriptors[1].items() if k not in variable}
        and first["asset_sha256"] == geometry["pose_marker"]["marked_asset_sha256"]
        and previous["case"]["visual_stages_in_order"] == STAGES
        and geometry["camera"]["calibration_version"] == "f33940579c533afe",
        "physical geometry, camera, eight-stage intent or asset drift",
    )
    baseline = pinned(
        old / previous["catalog"]["private_filename"], previous["catalog"]["archived_json_sha256"]
    )
    names = set(baseline) | set(lock["additional_files_sha256"])
    full = {name: lock["runtime_files_sha256"][name] for name in sorted(names)}
    require(
        all(full.get(k) == v for k, v in descriptors[1]["development_sources_sha256"].items()),
        "runtime source catalog does not bind the active observer",
    )
    return first, {**previous, "geometry": geometry}, full


def qualified_preflight_pose(repo):
    file = build.ROUNDS / "round-g1-first-refusal-dual-marker-20261124/zero-step-probes.public.json"
    prior = pinned(repo / file, "e8d1cbee3e655bfb8eb2daa54ed4236fa738e312ef9e2ce7b7cbc91773931c55")
    (witness,) = [
        r for r in prior["results"] if r["kind"] == "both" and r["pose"] == "preregistered-0"
    ]
    require(
        witness["path_success"] is True
        and witness["usable_ids"] == [7, 8]
        and witness["pose_xyzyaw"] == [0.45, 0, 0.035, 0]
        and witness["seed"] == 24113040,
        "qualification source does not establish this historical both-marker pose",
    )
    return witness


def obscured_packet(base):
    import base64
    import io

    from PIL import Image

    blank = io.BytesIO()
    Image.new("RGB", (base.width, base.height), (127, 127, 127)).save(blank, format="PNG")
    return type(base).model_validate(
        {
            **base.model_dump(),
            "frame_id": "dev-full-occlusion-" + base.frame_id,
            "observation_id": "",
            "checksum_sha256": "",
            "rgb_png_base64": base64.b64encode(blank.getvalue()).decode("ascii"),
        }
    )


def diagnostic_case(scene, kind, seed):
    from scripts.graduation.g1_formal_trials import identities

    from cloud_edge_robot_arm.vision.worker_owner import _identity_string

    require(kind in {"positive", "full-occlusion"}, "foreign diagnostic condition")
    visual = scene + "/" + kind
    ids = identities(visual)
    release = "g1-visibility-preflight-20261124"
    for value in (ids["run_id"], ids["plan_id"], ids["task_id"], release + "-worker"):
        _identity_string(value)
    return {**ids, "visual_id": visual, "visual_seed": seed, "scene_id": scene, "release": release}


def diagnostic_owner_software(directory, scene, full, generation):
    import sqlite3
    from contextlib import closing
    from dataclasses import asdict

    from scripts.graduation import dynamic_vision as runtime
    from scripts.graduation import g1_dual_probe as probe

    directory.mkdir()
    rows = []
    for kind in ("positive", "full-occlusion"):
        case = diagnostic_case(scene, kind, 24113040)
        path = directory / kind
        path.mkdir()
        allocation = dict(
            case=case,
            baseline=build.BASE,
            runtime_build_sha256=generation,
            component_catalog_sha256=runtime.digest(full),
            intent_descriptor={"type": "software owner identity", "stages": ["MOVE_ABOVE"]},
        )
        write(path / "allocation.json", allocation)
        owner = runtime.Owner(path, allocation, sha(path / "allocation.json"))
        live = owner.current()
        key = dict(
            episode_id="development-software-identity-only", robot_id="native-collection-panda"
        )
        identity = live.identity(**key, task_id=case["task_id"], plan_id=case["plan_id"])
        _, invalid = probe.result_of(
            lambda live=live, key=key, case=case: live.identity(
                **key, task_id=case["visual_id"] + ":task", plan_id=case["visual_id"] + ":plan"
            )
        )
        require(invalid is not None, "old slash task/plan identity unexpectedly accepted")
        closed = owner.close(kind == "positive")
        with closing(
            sqlite3.connect(
                (path / "development-worker.db").resolve().as_uri() + "?mode=ro&immutable=1",
                uri=True,
            )
        ) as db:
            db.row_factory = sqlite3.Row
            (job,) = db.execute("select * from simulation_jobs")
            (attempt,) = db.execute("select * from simulation_job_attempts")
            (lease,) = db.execute("select * from simulation_job_leases")
        require(
            job["job_id"] == live.job_id == attempt["job_id"] == lease["job_id"]
            and job["run_id"] == case["run_id"] == live.run_id == attempt["run_id"]
            and job["lease_id"] == lease["lease_id"] == live.lease_id
            and lease["worker_id"] == attempt["worker_id"] == case["release"] + "-worker"
            and job["batch_id"] == job["manifest_id"] == case["release"]
            and job["scenario_id"] == scene
            and json.loads(job["manifest_json"])
            == {k: case[k] for k in ("visual_id", "scene_id", "task_id", "plan_id")}
            and attempt["attempt"] == live.attempt == 1
            and lease["released_at"]
            and job["status"]
            == attempt["result"]
            == closed["final_job_status"]
            == ("SUCCEEDED" if kind == "positive" else "FAILED"),
            "software owner/lease readback",
        )
        rows.append(
            dict(
                kind=kind,
                case=case,
                lease=live.to_payload(),
                identity=asdict(identity),
                old_task_plan_refusal=invalid,
                close=closed,
                released_at=lease["released_at"],
                sqlite_sha256=sha(path / "development-worker.db"),
            )
        )
    require(
        len({r["lease"]["job_id"] for r in rows}) == 2
        and len({r["lease"]["lease_id"] for r in rows}) == 2,
        "software owners overlap",
    )
    write(
        directory / "readback.json",
        dict(
            scope="software-only", rows=rows, physics_steps=0, camera_captures=0, backend_commands=0
        ),
    )
    return sha(directory / "readback.json")


def occlusion_control(directory, kind, registration, full, pose, generation, scene):
    """Acquire fresh zero-step packets for the registered target and first hold sample."""
    import base64
    import io
    import time
    import traceback
    from datetime import timedelta

    import numpy as np
    from PIL import Image
    from scripts.graduation import dynamic_vision as runtime
    from scripts.graduation import g1_dual_observer as observer
    from scripts.graduation import g1_dual_probe as probe
    from scripts.graduation import g1_dual_trials as dual

    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import MuJoCoVisualServoController

    directory.mkdir()
    geometry = registration.to_payload()
    allocation = dict(
        case=diagnostic_case(scene, kind, pose["seed"]),
        baseline=build.BASE,
        component_catalog_sha256=runtime.digest(full),
        intent_descriptor={"type": "zero-step development observation", "stages": ["MOVE_ABOVE"]},
        runtime_build_sha256=generation,
        pose=pose["pose_xyzyaw"],
        source="historical qualification",
    )
    write(directory / "allocation.json", allocation)
    owner = runtime.Owner(directory, allocation, sha(directory / "allocation.json"))
    backend = runtime.MuJoCoPhysicsBackend()
    packets, timings, detail = {}, {}, {}

    def acquire(label):
        start = time.perf_counter()
        obs = probe.capture(backend, "both", segmented=False)
        packets[label] = obs
        timings[label] = {
            "physics_step": backend.total_physics_steps,
            "sim_time_s": obs.sim_time_s,
            "captured_at": obs.captured_at.isoformat(),
            "frame_id": obs.frame_id,
            "checksum_sha256": obs.checksum_sha256,
            "capture_ms": 1000 * (time.perf_counter() - start),
        }
        return obs

    complete = False
    try:
        backend.initialize(probe.config({"geometry": geometry}, pose["seed"]))
        compiled = dual.mass_properties(backend._model)
        x, y, z, yaw = pose["pose_xyzyaw"]
        scenario = runtime.PhysicalScenarioConfig(
            scenario_id=scene,
            seed=pose["seed"],
            object_pose=runtime.Pose(x=x, y=y, z=z),
            object_yaw_rad=yaw,
        )
        scenario = dual.bind_scenario_mass(scenario, probe.asset.BODY_MASS_KG, compiled["mass_kg"])
        backend.reset(scenario)
        detail.update(
            requested=runtime.plain(scenario),
            compiled=compiled,
            after_reset=dual.mass_properties(backend._model),
        )
        require(
            all(
                np.allclose(compiled[k], detail["after_reset"][k], atol=1e-12, rtol=0)
                for k in compiled
            ),
            "zero-step reset changed mass or inertia",
        )
        state = runtime.MuJoCoSkillRobot(backend).get_state()
        bootstrap = acquire("bootstrap")
        color, grounding = runtime.bootstrap_collection_tracker(bootstrap, geometry)
        lease = owner.current()
        original = runtime.build_collection_contract_v2(
            assignment=allocation["case"],
            current_owner={
                "task_id": allocation["case"]["task_id"],
                "plan_id": allocation["case"]["plan_id"],
                "issued_at": lease.acquired_at,
                "deadline_at": lease.acquired_at + timedelta(hours=1),
                "role_sha256": runtime.digest(allocation["intent_descriptor"]),
                "lease": lease,
            },
            geometry=geometry,
            source_hashes=full,
            observation=bootstrap,
            protocol_settings={"timeout_basis": "physics_steps"},
        )
        initial = acquire("initial-target")
        initial_tracker = probe.registered_tracker(initial, registration, full)
        target, _, initial_audit = probe.target(owner, original, initial_tracker, initial, state)
        detail.update(original_sha256=original.digest(), initial_registered_target=initial_audit)
        reference = acquire("servo-reference")
        endpoint = runtime.Pose.model_validate(target)
        previous = runtime.MotionTarget(state.tcp_pose, _DOWNWARD)
        common = dict(
            marker_family_id=registration.marker_family_id, verify_mujoco_calibration=True
        )
        moving = runtime.OpenCVServoFeedback(
            reference, color, grounding, skill="MOVE_ABOVE", initial_target=endpoint, **common
        )
        lifting = runtime.OpenCVServoFeedback(
            reference, color, grounding, skill="LIFT", initial_target=state.tcp_pose, **common
        )
        returned_hold_target = None

        def hold_sample(prior):
            nonlocal returned_hold_target
            returned_hold_target = runtime.MotionTarget(
                lifting.update(current), prior.orientation_wxyz
            )
            return returned_hold_target

        session = runtime.VisualServoSession(hold_sample)
        monitor = MuJoCoVisualServoController(backend)
        before = len(backend.command_records)
        base = acquire("current")
        current = obscured_packet(base) if kind == "full-occlusion" else base
        packets["tested"] = current
        # The clock starts at capture. Run the two native current-frame checks before file I/O.
        hold_begin = time.perf_counter()
        _, hold_refusal = probe.result_of(lambda: monitor.monitor_hold(previous, session))
        hold_elapsed = time.perf_counter() - hold_begin
        move_begin = time.perf_counter()
        revised, move_refusal = probe.result_of(lambda: moving.update(current))
        move_elapsed = time.perf_counter() - move_begin

        target_stage = "bootstrap_registered_collection_tracker_v2"
        target_origin = None
        try:
            tracker = probe.registered_tracker(current, registration, full)
            target_stage = "registered_collection_step_v2"
            assigned = probe.target(owner, original, tracker, current, state)
            target_refusal = None
        except ValueError as error:
            assigned, target_refusal = None, str(error)
            origin = traceback.extract_tb(error.__traceback__)[-1]
            target_origin = dict(
                file=Path(origin.filename).name,
                function=origin.name,
                line=origin.lineno,
                statement=origin.line,
            )

        measured = observer.measure_frame(current, geometry)
        base_measured = observer.measure_frame(base, geometry) if base is not current else measured
        commands = runtime.plain(backend.command_records[before:])
        validated_fields = (
            "captured_at",
            "sim_time_s",
            "depth_float32_base64",
            "valid_mask_base64",
            "width",
            "height",
            "intrinsics",
            "camera_to_world",
            "calibration_version",
            "episode_id",
            "scene_id",
            "source",
        )
        unchanged_fields = {k: getattr(current, k) == getattr(base, k) for k in validated_fields}
        with Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))) as image:
            pixels = np.asarray(image.convert("RGB"), dtype=int)
        green = (
            (pixels[:, :, 1] > pixels[:, :, 0])
            & (pixels[:, :, 1] > pixels[:, :, 2])
            & (np.ptp(pixels, axis=2) > 35)
        )
        raw_markers = {
            "observed_ids": base_measured["observed_ids"],
            "usable_ids": base_measured["usable_ids"],
            "selected_id": base_measured["selected_id"],
        }
        delta = (
            math.dist([getattr(endpoint, a) for a in "xyz"], [getattr(revised, a) for a in "xyz"])
            if revised is not None
            else None
        )
        detail.update(
            scene=scene,
            episode=bootstrap.episode_id,
            kind=kind,
            source_step=0,
            capture_clock="current source clock at acquisition",
            mask="uniform RGB (127,127,127) retaining original depth and capture clock"
            if base is not current
            else None,
            current_vs_base=unchanged_fields,
            tested_rgb_min=int(pixels.min()),
            tested_rgb_max=int(pixels.max()),
            tested_green_pixels=int(np.count_nonzero(green)),
            base_measurement=base_measured,
            base_markers=raw_markers,
            measured=measured,
            target_stage=target_stage,
            target_refusal=target_refusal,
            target_exception_origin=target_origin,
            current_registered_target=runtime.plain(assigned),
            moving_initial=runtime.plain(endpoint),
            moving_current=runtime.plain(revised),
            moving_delta_m=delta,
            move_refusal=move_refusal,
            move_elapsed_ms=1000 * move_elapsed,
            move_feedback=runtime.plain(moving.records),
            hold_target_source="post-reset MuJoCoSkillRobot.get_state().tcp_pose with _DOWNWARD",
            initial_hold_target=runtime.plain(previous),
            returned_hold_target=runtime.plain(returned_hold_target),
            hold_refusal=hold_refusal,
            hold_elapsed_ms=1000 * hold_elapsed,
            current_servo=runtime.plain(lifting.records),
            controller=runtime.plain(session.records),
            terminal_reason=session.terminal_reason,
            command_count_before=before,
            backend_commands=commands,
            integration_steps=backend.total_physics_steps,
        )
        # Store acquired packets and both native results before evaluating this condition.
        packet_hashes = {}
        for key, packet in packets.items():
            file = directory / (key + ".rgbd.json")
            write(file, packet.model_dump(mode="json"))
            packet_hashes[key] = sha(file)
        detail["packet_files_sha256"] = packet_hashes
        checks = dict(
            captured_at_zero=(
                backend.total_physics_steps == before == 0
                and all(o.sim_time_s == 0 for o in packets.values())
            ),
            unique_acquisitions=len({r.frame_id for k, r in packets.items() if k != "tested"}) == 4,
            bound_acquisitions=all(
                o.episode_id == bootstrap.episode_id
                and o.scene_id == scene
                and o.calibration_version == "f33940579c533afe"
                for o in packets.values()
            ),
            unaltered_source=all(unchanged_fields.values()),
            base_visible=(
                base_measured["usable"]
                and raw_markers["observed_ids"] == raw_markers["usable_ids"] == [7, 8]
                and raw_markers["selected_id"] == 7
                and 0 <= base_measured["target_disagreement_m"] <= 0.01
            ),
        )
        if kind == "positive":
            target_frame = assigned[2] if assigned is not None else {}
            checks.update(
                positive_measurement=measured["usable"]
                and measured["usable_ids"] == [7, 8]
                and measured["selected_id"] == 7,
                registered=(
                    target_refusal is None
                    and target_frame.get("observation_id") == current.frame_id
                    and target_frame.get("checksum_sha256") == current.checksum_sha256
                ),
                same_current_feedback=(
                    len(moving.records) == len(lifting.records) == 1
                    and all(
                        r[0]["observation_id"] == current.frame_id
                        and r[0]["checksum_sha256"] == current.checksum_sha256
                        for r in (moving.records, lifting.records)
                    )
                ),
                registered_moving=(
                    move_refusal is None and delta is not None and delta <= moving.max_frame_delta_m
                ),
                fixed_lift_target=returned_hold_target == previous
                and hold_refusal is session.terminal_reason is None,
                one_hold_sample=len(session.records) == 1 and session.records[0]["phase"] == "HOLD",
                no_commands=not commands,
            )
        else:
            native_marker_error = "servo registered marker geometry unavailable"
            marker_origin = (
                target_refusal
                == "initial registered geometry unavailable: known_marker_not_observed"
                and target_origin is not None
                and target_origin["file"] == "registered_object_tracking.py"
                and target_origin["function"] == "__init__"
            )
            color_origin = (
                target_refusal == "unique registered green region unavailable"
                and target_origin is not None
                and target_origin["file"] == "native_collection_grounding.py"
                and target_origin["function"] == "collection_bootstrap_evidence"
                and detail["tested_green_pixels"] == 0
            )
            checks.update(
                uniformly_covered=detail["tested_rgb_min"] == detail["tested_rgb_max"] == 127
                and current.frame_id != base.frame_id
                and current.checksum_sha256 != base.checksum_sha256,
                missing_markers=(
                    not measured["observed_ids"]
                    and not measured["usable_ids"]
                    and not measured["usable"]
                    and measured["selected_id"] is None
                    and measured["reason"] == "known_marker_not_observed"
                    and measured["grasp_world_m"] is None
                ),
                registered_visual_refusal=(
                    assigned is None
                    and target_stage == "bootstrap_registered_collection_tracker_v2"
                    and (marker_origin or color_origin)
                ),
                same_visual_feedback_refusal=(
                    hold_refusal == move_refusal == native_marker_error
                    and session.terminal_reason == "ValueError:" + native_marker_error
                    and revised is returned_hold_target is None
                    and not lifting.records
                    and not moving.records
                    and not session.records
                ),
                protective_hold_only=(
                    len(commands) == 1
                    and commands[0]["type"] == "hold_current_joints"
                    and commands[0]["accepted"] is True
                ),
            )
        detail["checks"] = checks
        write(directory / "sample-evidence.json", {**detail, "acquisitions": timings})
        require(
            all(checks.values()),
            kind
            + " diagnostic checks failed: "
            + ", ".join(k for k, passed in checks.items() if not passed),
        )
        complete = True
    except BaseException:
        write(directory / "interrupt.json", {"traceback": traceback.format_exc()})
        raise
    finally:
        detail["integration_steps"] = backend.total_physics_steps
        detail["all_commands"] = runtime.plain(backend.command_records)
        detail["worker"] = owner.close(complete)
        for key, packet in packets.items():
            file = directory / (key + ".rgbd.json")
            if not file.exists():
                write(file, packet.model_dump(mode="json"))
        write(directory / "trace.json", {**detail, "acquisitions": timings})
        backend.shutdown()
    return {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file()}


def preflight(repo, private, generation, lock):
    import tempfile

    from scripts.graduation import g1_dual_observer as observer
    from scripts.graduation import g1_dual_probe as probe
    from scripts.graduation import g1_dual_trials as dual
    from scripts.graduation import g1_formal_trials as formal

    first, old, full = template(repo, lock)
    geometry = old["geometry"]
    registration = dual.NativeGeometryRegistration(geometry)
    registration.validate_asset(ROOT)
    witness = qualified_preflight_pose(repo)
    spec = build.ROUNDS / "round-g1-visibility-live-preflight-20261124/plan.json"
    supplemental_sha = "4ac1991bdfcc99bcd326562c5cdd9e63ca393755449409d629941fa8354c8525"
    supplemental = pinned(repo / spec, supplemental_sha)
    require(
        sha(repo / spec.with_suffix(".md")) == supplemental["plan_md_sha256"],
        "changed supplemental Astra plan",
    )
    # These two explicitly modified inputs were verified against the old worktree before RED.
    # The input runner is also verified byte-for-byte in the retained failed generation.
    for name, digest in supplemental["inputs_sha256"].items():
        if name not in {build.RUNNER, "tests/test_graduation_g1_visibility_trials.py"}:
            require(sha(repo / name) == digest, "changed preflight source: " + name)
    identity_path = build.ROUNDS / "round-g1-visibility-preflight-identity-20261124/plan.json"
    identity_sha = "15b2674b646c147409886201718eddde2f18a311fb83485a2ffdb03059c409ff"
    identity_plan = pinned(repo / identity_path, identity_sha)
    require(
        sha(repo / identity_path.with_suffix(".md")) == identity_plan["plan_md_sha256"],
        "changed Astra identity plan",
    )
    for name, digest in identity_plan["inputs_sha256"].items():
        if name not in {build.RUNNER, "tests/test_graduation_g1_visibility_trials.py"}:
            require(sha(repo / name) == digest, "changed identity preflight source: " + name)
    hold_path = build.ROUNDS / "round-g1-visibility-preflight-hold-20261124/plan.json"
    hold_sha = "61024890eb60d7b7223764f818b8c09985d08f5ca431eef29f6c088a5802a43c"
    hold_plan = pinned(repo / hold_path, hold_sha)
    require(
        sha(repo / hold_path.with_suffix(".md")) == hold_plan["plan_md_sha256"],
        "changed Astra hold plan",
    )
    for name, digest in hold_plan["inputs_sha256"].items():
        if name not in {build.RUNNER, "tests/test_graduation_g1_visibility_trials.py"}:
            require(sha(repo / name) == digest, "changed hold diagnosis source: " + name)
    historical = build.check_history(repo, read(repo / build.PLAN))
    folder = private / "builds" / generation
    directory = Path(tempfile.mkdtemp(prefix="zero-step-", dir=folder))
    scene = RELEASE + "/" + directory.name + "-qualification"
    raw = repo / build.PARENT / "trials" / first["id"] / "instance"
    index = read(raw / "pixel-index.json")
    boot_row = next(r for r in index["frames"] if r["label"] == "bootstrap")
    boot = dual.vision.frame_from_row(raw, boot_row, index["episode"], first["scene_id"], geometry)
    with bind_scene(first["scene_id"]):
        archived = observer.measure_frame(boot, geometry)
        _, stale = probe.result_of(
            lambda: dual.runtime.bootstrap_collection_tracker(boot, geometry)
        )
    require(
        stale == "initial acquisition unavailable: capture_time_not_fresh",
        "historical acquisition did not reject its real stale clock",
    )
    with bind_scene("foreign-qualification"):
        require(
            observer.measure_frame(boot, geometry)["reason"] == "registered_scene_mismatch",
            "foreign scene was not refused",
        )
    write(
        directory / "historical.json",
        dict(
            rgbd_file_sha256=boot_row["file_sha256"],
            original_step=boot_row["physics_step"],
            original_time=boot.captured_at.isoformat(),
            measurement=archived,
            live_refusal=stale,
            use="offline read and stale negative",
        ),
    )
    versions = dict(
        python=sys.version,
        mujoco=dual.runtime.mujoco.__version__,
        opencv=dual.runtime.cv2.__version__,
        numpy=dual.runtime.np.__version__,
        pillow=dual.runtime.PIL.__version__,
    )
    previous_imports = read(raw / "imports.json")
    require(
        versions == previous_imports["versions"]
        and sha(Path(sys.executable)) == previous_imports["executable_sha256"],
        "original interpreter or core runtime dependencies differ",
    )
    software_sha = diagnostic_owner_software(directory / "software", scene, full, generation)
    from scripts.graduation import g1_formal_runtime as scene_binding

    require(
        observer.expected_scene is scene_binding.expected_scene
        and scene_binding.expected_scene("unbound") == "unbound"
        and archived["usable_ids"] == [7, 8],
        "offline registration context drift",
    )
    with device(private), bind_scene(scene):
        compiled = formal.ready_device({"dual": (first, old, full)}, 16 * 2**30, private)
        probes = {
            kind: occlusion_control(
                directory / kind, kind, registration, full, witness, generation, scene
            )
            for kind in ("positive", "full-occlusion")
        }
    require(historical == build.check_history(repo, read(repo / build.PLAN)), "frozen data changed")
    write(
        directory / "seal.json",
        {"cases": probes, "historical_sha256": sha(directory / "historical.json")},
    )
    path = folder / "preflight.json"
    data = dict(
        schema="g1.visibility.development-preflight.v2",
        eligible=True,
        plan_sha256=build.PLAN_SHA,
        preflight_plan_sha256=supplemental_sha,
        identity_plan_sha256=identity_sha,
        hold_plan_sha256=hold_sha,
        software_owner_sha256=software_sha,
        runtime_build_sha256=generation,
        history=historical,
        compiled=compiled,
        versions=versions,
        qualification_pose=witness["pose_xyzyaw"],
        qualification_seed=witness["seed"],
        full_occlusion_probe_sha256=probes["full-occlusion"]["trace.json"],
        positive_probe_sha256=probes["positive"]["trace.json"],
        probe_seal_sha256=sha(directory / "seal.json"),
        full_occlusion_directory=directory.name,
        available_bytes=shutil.disk_usage(private).free,
        interpreter_sha256=sha(Path(sys.executable)),
        imported_project_files=dual.g1_mount_trials.project_imports(lock),
        calibration=geometry["camera"],
        physics_steps=0,
        motion_commands=0,
        hold_commands=1,
        diagnostic_resets=2,
        development_trials=0,
        formal_claims=0,
        hardware_actions=0,
    )
    if not path.exists():
        write(path, data)
    require(read(path)["runtime_build_sha256"] == generation, "foreign preflight")
    return sha(path)


def release_gate(repo, path, expected, lock):
    gate = pinned(path, expected)
    require(
        gate["schema"] == "g1.visibility.offline-release.v1"
        and gate["eligible"] is True
        and gate["plan_sha256"] == build.PLAN_SHA
        and gate["historical_frames"] == 778
        and gate["first_refusals_recovered"] == 8
        and gate["false_positive_controls"] == 0
        and gate["detector_files_sha256"] == lock["detector_files_sha256"]
        and gate["input_artifacts_sha256"],
        "offline and negative control release not qualified",
    )
    for name, h in gate["input_artifacts_sha256"].items():
        require(sha(repo / name) == h, "changed offline release evidence: " + name)
    return gate


def check_training_score(private, generation, path, expected):
    report = pinned(path, expected)
    location = path.resolve()
    require(
        location == batch_path(private, location.parent.name) / "score.json"
        and report["schema"] == "g1.visibility.development-score.v1"
        and report["scope"] == "training"
        and report["runtime_build_sha256"] == generation
        and report["plan_sha256"] == build.PLAN_SHA
        and any(training_success(row) for row in report["cases"]),
        "candidate lacks an independently successful training run",
    )
    evidence = location.parent
    for name, file in (
        ("allocation_sha256", "allocation.json"),
        ("acquisition_sha256", "acquisition.json"),
        ("pixel_index_sha256", "scoring/pixels/index.json"),
    ):
        require(report[name] == sha(evidence / file), "training score has foreign source evidence")
    for key, paths in (
        ("blind_seals_sha256", ["blind-one/seal.json", "blind-two/seal.json"]),
        ("score_passes_sha256", ["score-one.json", "score-two.json"]),
    ):
        require(
            report[key] == [sha(evidence / "scoring" / item) for item in paths]
            and len(set(report[key])) == 1,
            "training score lacks two matching independent reads",
        )
    require(
        report["cases"] == read(evidence / "scoring/score-one.json")["cases"],
        "training cases differ from independent scores",
    )
    return report


def issue(repo, private, generation, lock, args):
    from scripts.graduation import g1_dual_trials as dual
    from scripts.graduation.g1_formal_trials import identities

    training = args.command == "issue-training"
    scope = "training" if training else "evaluation"
    label = args.batch if training else "evaluation"
    directory = batch_path(private, label)
    require(
        (not training or label.startswith("train-")) and not directory.exists(),
        "development batch has already been issued",
    )
    pre = private / "builds" / generation / "preflight.json"
    require(read(pre)["runtime_build_sha256"] == generation, "preflight generation differs")
    gate = release_gate(repo, args.gate, args.gate_sha, lock)
    first, previous, full = template(repo, lock)
    extras = {}
    if training:
        rows = training_placements(args.groups, placements_from_old(repo))
    else:
        selection = pinned(args.selection, args.selection_sha)
        require(
            selection["schema"] == "g1.visibility.evaluation-selection.v1"
            and selection["runtime_build_sha256"] == generation
            and re.fullmatch("[0-9a-f]{64}", selection["sampling_rule_sha256"]),
            "development selection and candidate differ",
        )
        check_training_score(
            private, generation, args.training_score, selection["training_score_sha256"]
        )
        rows = checked_placements(selection["placements"], "evaluation")
        extras = {k: selection[k] for k in ("sampling_rule_sha256", "training_score_sha256")}
        extras["selection_sha256"] = args.selection_sha
    release = RELEASE + "-" + label
    directory.mkdir(parents=True)
    reserve_attempt(directory / "gate.json", gate)
    inventory = directory / "source-inventory.json"
    write(inventory, full)
    if not training:
        shutil.copyfile(args.selection, directory / "selection.json")
    catalog = dict(
        private_filename=inventory.name,
        archived_json_sha256=sha(inventory),
        product_compact_sorted_utf8_sha256=dual.native.digest(full),
        count=len(full),
    )
    cases = []
    for slot, placement in enumerate(rows, 1):
        visual = release + "/" + placement["id"]
        row = {
            **placement,
            "group": placement["id"],
            "slot": slot,
            "visual_id": visual,
            "arm": "dual",
            "view": "nominal",
            **identities(visual),
            **{
                k: first[k]
                for k in ("family", "asset_path", "asset_sha256", "physical_object_mass_kg")
            },
        }
        case = {
            **row,
            "visual_seed": row["seed"],
            "release": release,
            "mount": "dual",
            "claim_scope": scope,
            "attempts": 1,
            "private_output": row["id"] + "/instance",
            "visual_stages_in_order": STAGES,
            "settle": 120,
            "physics_dt_s": "1/240",
            "max_skill_calls": 8,
            "hardware_actions": 0,
            "task_model_calls": 0,
        }
        allocation = dict(
            schema="g1.visibility.development-case.v1",
            scope=scope,
            baseline=build.BASE,
            plan_sha256=build.PLAN_SHA,
            case=case,
            asset_sha256=row["asset_sha256"],
            geometry=previous["geometry"],
            catalog=catalog,
            sources_sha256=full,
            component_catalog_sha256=dual.runtime.digest(full),
            runtime_build_sha256=generation,
            intent_descriptor=dict(
                type="registered development intentions", stages=STAGES, model_calls=0
            ),
            selected_entry=previous["selected_entry"],
            capture_grid=previous["capture_grid"],
            method_template_sha256=first["allocation_sha256"],
        )
        case_dir = directory / row["id"]
        case_dir.mkdir()
        file = case_dir / "allocation.json"
        write(file, allocation)
        cases.append(
            {
                **row,
                "allocation_file": file.relative_to(directory).as_posix(),
                "allocation_sha256": sha(file),
            }
        )
    batch = dict(
        schema="g1.visibility.development-allocation.v1",
        scope=scope,
        plan_sha256=build.PLAN_SHA,
        runtime_build_sha256=generation,
        preflight_sha256=sha(pre),
        gate_source_sha256=args.gate_sha,
        gate_sha256=sha(directory / "gate.json"),
        release=release,
        label=label,
        attempts_per_slot=1,
        issued_at=datetime.now(UTC).isoformat(),
        catalog=catalog,
        cases=cases,
        scorer_files_sha256=lock["scorer_files_sha256"],
        hardware_actions=0,
        formal_claims=0,
        **extras,
    )
    write(directory / "allocation.json", batch)
    return sha(directory / "allocation.json")


def batch_context(private, generation, label, digest):
    directory = batch_path(private, label)
    batch = pinned(directory / "allocation.json", digest)
    require(
        batch["schema"] == "g1.visibility.development-allocation.v1"
        and batch["label"] == label
        and batch["release"] == RELEASE + "-" + label
        and batch["runtime_build_sha256"] == generation
        and batch["plan_sha256"] == build.PLAN_SHA
        and batch["attempts_per_slot"] == 1
        and batch["scope"] == ("evaluation" if label == "evaluation" else "training"),
        "foreign development allocation",
    )
    checked_placements([{k: r[k] for k in FIELDS} for r in batch["cases"]], batch["scope"])
    return directory, batch


def load_case(directory, batch, row):
    from scripts.graduation import g1_dual_trials as dual

    require(row["allocation_file"] == row["id"] + "/allocation.json", "foreign case source path")
    data = pinned(directory / row["allocation_file"], row["allocation_sha256"])
    case = data["case"]
    require(
        case["visual_stages_in_order"] == data["intent_descriptor"]["stages"] == STAGES
        and all(
            case[k] == v
            for k, v in row.items()
            if k not in {"allocation_file", "allocation_sha256"}
        )
        and data["runtime_build_sha256"] == batch["runtime_build_sha256"]
        and case["visual_id"] == case["scene_id"] == batch["release"] + "/" + row["id"]
        and case["release"] == batch["release"]
        and case["visual_seed"] == row["seed"]
        and data["scope"] == case["claim_scope"] == batch["scope"]
        and data["catalog"] == batch["catalog"]
        and data["geometry"] == dual.runtime.geometry_registration(marker_family_id=row["family"]),
        "crossed case, geometry, identity or eight-skill intention",
    )
    cat = data["catalog"]
    source = pinned(directory / cat["private_filename"], cat["archived_json_sha256"])
    require(
        source == data["sources_sha256"]
        and dual.runtime.digest(source) == data["component_catalog_sha256"]
        and dual.native.digest(source) == cat["product_compact_sorted_utf8_sha256"]
        and all(sha(ROOT / name) == h for name, h in source.items()),
        "runtime source catalog changed",
    )
    return data, source


def capture(repo, private, generation, lock, directory, batch, h, case_id):
    from scripts.graduation import g1_dual_trials as dual

    row = next((r for r in batch["cases"] if r["id"] == case_id), None)
    require(row is not None, "unallocated development case")
    release_gate(repo, directory / "gate.json", batch["gate_sha256"], lock)
    owned = None
    instance = directory / case_id / "instance"

    def reserve():
        nonlocal owned
        owned = reserve_attempt(
            directory / case_id / "attempt.json",
            dict(
                id=case_id,
                slot=row["slot"],
                scope=batch["scope"],
                attempt=1,
                release=batch["release"],
                runtime_build_sha256=generation,
                allocation_sha256=h,
                claimed_at=datetime.now(UTC).isoformat(),
                pid=os.getpid(),
            ),
        )
        return owned

    with device(private), bind_scene(row["scene_id"]), build.log_measurements() as measured:
        try:
            dual.g1_mount_trials.capture(
                repo / build.PLAN,
                directory,
                h,
                case_id,
                context=lambda *_: (batch, lock),
                case_reader=load_case,
                episode_factory=dual.episode_with_registered_mass,
                before_start=reserve,
            )
        finally:
            if owned and instance.is_dir():
                path = instance / "online-vision.json"
                write(
                    path,
                    dict(
                        attempt_sha256=owned,
                        source_files_sha256=lock["detector_files_sha256"],
                        frames=measured,
                    ),
                )
                write(
                    instance / "online-vision-seal.json",
                    dict(
                        online_vision_sha256=sha(path),
                        attempt_sha256=owned,
                        acquisition_sha256=sha(instance / "acquisition-seal.json")
                        if (instance / "acquisition-seal.json").is_file()
                        else None,
                    ),
                )
    return sha(instance / "receipt.json")


def audit(private, generation, directory, batch, h, allow_partial):
    from scripts.graduation import g1_dual_trials as dual

    cases = []
    for row in batch["cases"]:
        data, _ = load_case(directory, batch, row)
        case_dir = directory / row["id"]
        instance = case_dir / "instance"
        if not (instance / "receipt.json").exists():
            require(
                allow_partial or (instance / "interrupted.json").is_file(),
                "development slot has no terminal receipt",
            )
            evidence = "INTERRUPTED" if (case_dir / "attempt.json").exists() else "UNRUN"
            cases.append(
                {
                    "id": row["id"],
                    "acquired": False,
                    "evidence_status": evidence,
                    "attempt_sha256": sha(case_dir / "attempt.json")
                    if evidence == "INTERRUPTED"
                    else None,
                }
            )
            continue
        result = dual.audit_one(instance, row, data, h)
        started = read(instance / "started.json")
        attempt_file = case_dir / "attempt.json"
        attempt = pinned(attempt_file, result["claim_sha256"])
        run, index = read(instance / "run.json"), read(instance / "pixel-index.json")
        truth = read(instance / "offline-truth.json")
        require(
            attempt["scope"] == batch["scope"]
            and attempt["runtime_build_sha256"] == generation
            and attempt["allocation_sha256"] == h
            and attempt["id"] == row["id"]
            and started["case"] == row["id"]
            and started["attempt"] == 1
            and started["egl_lock"] == str(private / "egl.lock")
            and attempt["claimed_at"] <= started["start_utc"] <= result["worker"]["acquired_at"]
            and run["development_identity"]
            == {k: row[k] for k in ("scene_id", "visual_id", "task_id", "plan_id")}
            and row["scene_id"]
            == index["scene"]
            == truth["scene"]
            == result["physical_reset"]["scenario"]
            and result["worker"]["run_id"] == row["run_id"],
            "crossed development worker, reset or attempt",
        )
        logged = read(instance / "online-vision-seal.json")
        live = pinned(instance / "online-vision.json", logged["online_vision_sha256"])
        require(
            logged["attempt_sha256"] == live["attempt_sha256"] == result["claim_sha256"]
            and logged["acquisition_sha256"] == result["capture_sha256"],
            "foreign live observer log",
        )
        actual = {f["frame_id"]: f["checksum_sha256"] for f in index["frames"]}
        require(
            all(
                actual.get(key) == v["measurement"]["checksum"] and v["callers"]
                for key, v in live["frames"].items()
            ),
            "live observer measured a foreign frame",
        )
        cases.append(
            {
                **result,
                "id": row["id"],
                "online_vision_sha256": logged["online_vision_sha256"],
                "attempt_sha256": sha(attempt_file),
            }
        )
    completed = [r for r in cases if r["acquired"]]
    for identities in (
        [r["worker"][k] for r in completed] for k in ("job_id", "run_id", "lease_id")
    ):
        require(len(set(identities)) == len(completed), "development worker or lease reused")
    require(
        len({r["physical_reset"]["episode_id"] for r in completed}) == len(completed)
        and all(
            a["worker"]["released_at"] < b["worker"]["acquired_at"]
            for a, b in zip(completed, completed[1:], strict=False)
        ),
        "shared reset or overlapping lease",
    )
    result = dict(
        schema="g1.visibility.development-acquisition.v1",
        scope=batch["scope"],
        runtime_build_sha256=generation,
        plan_sha256=build.PLAN_SHA,
        allocation_sha256=h,
        cases=cases,
        actual_episodes=len(completed),
        formal_claims=0,
        hardware_actions=0,
    )
    path = directory / "acquisition.json"
    if path.exists():
        require(read(path) == result, "acquisition changed after sealing")
    else:
        write(path, result)
    return sha(path)


def score_inputs(directory, batch, h):
    acquisition = read(directory / "acquisition.json")
    require(
        acquisition["runtime_build_sha256"] == batch["runtime_build_sha256"]
        and acquisition["allocation_sha256"] == h
        and acquisition["scope"] == batch["scope"],
        "foreign acquisition",
    )
    entries = []
    for row, observed in zip(batch["cases"], acquisition["cases"], strict=True):
        require(observed["id"] == row["id"], "acquisition order differs from allocation")
        data, _ = load_case(directory, batch, row)
        entries.append((row, data, observed, directory / row["id"] / "instance"))
    return entries


def matches_online(packet, measured):
    if packet["checksum_sha256"] != measured["checksum"] or any(
        packet[k] != measured[k]
        for k in ("usable", "observed_ids", "usable_ids", "selected_id", "reason")
    ):
        return False
    if not measured["usable"]:
        return packet["tcp_m"] is None and measured["grasp_world_m"] is None
    return len(packet["tcp_m"]) == len(measured["grasp_world_m"]) == 3 and all(
        math.isclose(left, right, rel_tol=0, abs_tol=1e-10)
        for left, right in zip(packet["tcp_m"], measured["grasp_world_m"], strict=True)
    )


def joined_scores(directory, batch, h, blind, output):
    from scripts.graduation import g1_dual_batch_score as scorer

    seal = read(blind / "seal.json")
    require(
        seal["index_sha256"] == sha(directory / "scoring/pixels/index.json"), "foreign blind input"
    )
    cases, all_pixels = [], []
    for row, data, observed, raw in score_inputs(directory, batch, h):
        if not observed["acquired"]:
            cases.append(
                {
                    **row,
                    "acquired": False,
                    "evidence_status": observed["evidence_status"],
                    "joint_success": None,
                }
            )
            continue
        with bind_scene(row["scene_id"]):
            entry, _, frames = scorer.score_case(
                row, data, observed, raw, ROOT, blind, seal, expected_scene=row["scene_id"]
            )
        live = pinned(raw / "online-vision.json", observed["online_vision_sha256"])["frames"]
        lookup = {f["frame_id"]: f for f in frames}
        for frame_id, trace in live.items():
            packet = lookup[frame_id]
            measured = trace["measurement"]
            require(matches_online(packet, measured), "blind and live measurements disagree")
        receipt = pinned(raw / "receipt.json", observed["receipt_sha256"])
        entry.update(
            evidence_status="SCORED",
            scene_id=row["scene_id"],
            attempt_sha256=observed["attempt_sha256"],
            hand_contacts=observed["hand_contacts"],
            worker_db_sha256=receipt["worker"]["sqlite_sha256"],
            backend_command_count=receipt["backend_command_count"],
            full_commands_sha256=receipt["full_commands_sha256"],
            online_vision_sha256=observed["online_vision_sha256"],
        )
        cases.append(entry)
        all_pixels.extend(frames)
    result = dict(
        cases=cases,
        successes=sum(training_success(r) for r in cases),
        allocated=len(cases),
        unknown=sum(r["evidence_status"] != "SCORED" for r in cases),
        overall_pixels=scorer.coverage(all_pixels),
    )
    write(output, result)


def score(repo, generation, directory, batch, h):
    from scripts.graduation import g1_dual_batch_score as scorer

    area = directory / "scoring"
    cases = score_inputs(directory, batch, h)
    area.mkdir(exist_ok=True)
    index = area / "pixels/index.json"
    if not index.exists():
        scorer.package(cases, area / "pixels", registered_scene=True)
    blind_paths = [area / "blind-one", area / "blind-two"]
    for path in blind_paths:
        if not (path / "seal.json").is_file():
            scorer.blind_reader(ROOT, index, path)
    seals = [sha(path / "seal.json") for path in blind_paths]
    require(seals[0] == seals[1], "independent pixel seals disagree")
    for blind in blind_paths:
        seal = read(blind / "seal.json")
        require(
            seal["index_sha256"] == sha(index)
            and all(sha(blind / (k + ".json")) == v for k, v in seal["packets"].items()),
            "blind seal differs from packets",
        )
    outputs = [area / "score-one.json", area / "score-two.json"]
    for blind, output in zip(blind_paths, outputs, strict=True):
        if not output.exists():
            args = [
                sys.executable,
                "-B",
                "-m",
                "scripts.graduation.g1_visibility_trials",
                "--repo",
                str(repo),
                "join",
                generation,
                batch["label"],
                h,
                blind.name,
                output.name,
            ]
            proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            log = output.with_suffix(".process.json")
            if proc.returncode or not log.exists():
                write(
                    log
                    if not log.exists()
                    else log.with_name(log.stem + "-" + str(os.getpid()) + ".json"),
                    dict(argv=args, status=proc.returncode, stdout=proc.stdout, stderr=proc.stderr),
                )
            require(proc.returncode == 0, "independent scoring process failed; see " + str(log))
    scored = [sha(path) for path in outputs]
    require(scored[0] == scored[1], "independent trajectory and pixel scores disagree")
    result = dict(
        schema="g1.visibility.development-score.v1",
        scope=batch["scope"],
        plan_sha256=build.PLAN_SHA,
        runtime_build_sha256=generation,
        allocation_sha256=h,
        acquisition_sha256=sha(directory / "acquisition.json"),
        pixel_index_sha256=sha(index),
        blind_seals_sha256=seals,
        blind_process_receipts_sha256=[sha(p.with_suffix(".process.json")) for p in blind_paths],
        score_passes_sha256=scored,
        score_process_receipts_sha256=[sha(p.with_suffix(".process.json")) for p in outputs],
        **read(outputs[0]),
    )
    path = directory / "score.json"
    if path.exists():
        require(read(path) == result, "existing final score differs from sealed reads")
    else:
        write(path, result)
    return sha(path)


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--repo", type=Path, default=ROOT)
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    for cmd in (
        "preflight",
        "issue-training",
        "issue-evaluation",
        "capture",
        "audit",
        "score",
        "join",
    ):
        p = commands.add_parser(cmd)
        p.add_argument("generation", help="SHA256 printed by prepare")
        if cmd.startswith("issue-"):
            p.add_argument("--gate", required=True, type=Path)
            p.add_argument("--gate-sha", required=True)
            if cmd == "issue-training":
                p.add_argument("batch", help="unique train- label")
                p.add_argument("groups", nargs="+", choices=["d01", "d02", "d03", "d04"])
            else:
                p.add_argument("selection", type=Path)
                p.add_argument("selection_sha")
                p.add_argument("training_score", type=Path)
        elif cmd != "preflight":
            p.add_argument("batch")
            p.add_argument("allocation_sha")
            if cmd == "capture":
                p.add_argument("case")
            if cmd == "audit":
                p.add_argument("--finalize-partial", action="store_true")
            if cmd == "join":
                p.add_argument("blind", choices=["blind-one", "blind-two"])
                p.add_argument("output", choices=["score-one.json", "score-two.json"])
    return cli


def main():
    args = parser().parse_args()
    repo = args.repo.resolve()
    _, private = build.context(repo)
    if args.command == "prepare":
        print(build.prepare(repo))
        return
    # Resolve caller-provided files before switching into the isolated source tree.
    for key in ("gate", "selection", "training_score"):
        path = getattr(args, key, None)
        if path is not None:
            setattr(args, key, path.resolve())
    # Reconstruct argv with absolute paths; all other arguments are opaque content hashes and IDs.
    argv = sys.argv[1:]
    if "--repo" in argv:
        i = argv.index("--repo")
        argv = argv[:i] + argv[i + 2 :]
    if ROOT != build.source_root(private, args.generation):
        values = list(argv)
        for i, value in enumerate(values):
            if any(
                getattr(args, k, None) is not None and Path(value).resolve() == getattr(args, k)
                for k in ("gate", "selection", "training_score")
            ):
                values[i] = str(Path(value).resolve())
        build.isolated(repo, private, args.generation, values)
    _, lock = build.verify_build(private, args.generation)
    require(
        Path.cwd() == ROOT == build.source_root(private, args.generation),
        "use the frozen development entry",
    )
    if args.command == "preflight":
        result = preflight(repo, private, args.generation, lock)
    elif args.command.startswith("issue-"):
        result = issue(repo, private, args.generation, lock, args)
    else:
        directory, batch = batch_context(private, args.generation, args.batch, args.allocation_sha)
        if args.command == "capture":
            result = capture(
                repo,
                private,
                args.generation,
                lock,
                directory,
                batch,
                args.allocation_sha,
                args.case,
            )
        elif args.command == "audit":
            result = audit(
                private,
                args.generation,
                directory,
                batch,
                args.allocation_sha,
                args.finalize_partial,
            )
        elif args.command == "join":
            joined_scores(
                directory,
                batch,
                args.allocation_sha,
                directory / "scoring" / args.blind,
                directory / "scoring" / args.output,
            )
            return
        else:
            result = score(repo, args.generation, directory, batch, args.allocation_sha)
    print(result)


if __name__ == "__main__":
    main()
