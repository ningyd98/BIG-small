"""Run preallocated held-out static placements through the guarded r593 development controller."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import guarded_clock
from scripts.graduation.perception_capture import VIEWS, optical_transform
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import RGBDObservation

POSES = (
    (0.435, -0.010, 0.035, 0.08),
    (0.465, 0.010, 0.035, -0.08),
    (0.442, 0.020, 0.035, -0.12),
    (0.458, -0.020, 0.035, 0.12),
)
RELEASE = "proposal-dev-heldout-20261124"
PARENT_ROUND = "round-graduation-guarded-clock-20261123"
SOURCES = (
    "scripts/graduation/proposal_closed_loop.py",
    "scripts/graduation/perception_capture.py",
    "tests/test_graduation_proposal_closed_loop.py",
)
CAMERA_VIEWS = {"nominal": "axial", "left": "left", "right": "right"}


def allocated_cases(selected_view):
    if selected_view not in CAMERA_VIEWS:
        raise ValueError("unregistered development camera view")
    cases = []
    for index, (x, y, z, yaw) in enumerate(POSES):
        group = f"g{index + 1:02d}"
        views = ["nominal"] if selected_view == "nominal" else ["nominal", selected_view]
        for view in views[:: -1 if index % 2 else 1]:
            cases.append(
                {
                    "id": f"{group}-{view}",
                    "group": group,
                    "view": view,
                    "seed": 24112401 + index,
                    "reset_fixture_center_m": [x, y, z],
                    "yaw_rad": yaw,
                }
            )
    return cases


def register_camera(view, measured, original):
    """Derive the development registration from the real camera and the fixed view request."""
    if view not in CAMERA_VIEWS:
        raise ValueError("unknown development camera")
    nominal = original["camera"]
    if set(measured) != set(nominal) or any(
        measured[key] != nominal[key] for key in ("width", "height", "intrinsics", "source")
    ):
        raise ValueError("camera source, image dimensions or intrinsics changed")
    expected = optical_transform(*VIEWS[CAMERA_VIEWS[view]]).ravel()
    extrinsics = np.asarray(measured["camera_to_world"], dtype=float)
    if extrinsics.shape != (16,) or not np.allclose(expected, extrinsics, rtol=0, atol=1e-12):
        raise ValueError("camera pose does not match the allocated view")
    values = np.r_[measured["intrinsics"], extrinsics].astype("<f8")
    version = hashlib.sha256(values.tobytes()).hexdigest()[:16]
    if (
        measured["calibration_version"] != version
        or (view == "nominal" and measured != nominal)
        or (view != "nominal" and version == nominal["calibration_version"])
    ):
        raise ValueError("camera fingerprint does not bind the measured intrinsics and extrinsics")
    geometry = {**original, "camera": dict(measured)}
    NativeGeometryRegistration(geometry).validate_asset(ROOT)
    return geometry


def executable_view(selected, probes):
    if probes["nominal"]["supported"] is not True:
        raise ValueError("nominal tracker positive control did not register")
    if probes[selected]["supported"] is True:
        return selected
    reasons = {
        "initial registered geometry unavailable: camera_orientation_not_supported",
        "initial registered observation unavailable: camera_orientation_not_supported",
    }
    if probes[selected]["supported"] is not False or probes[selected]["reason"] not in reasons:
        raise ValueError("unexpected original tracker refusal during isolated registration")
    return "nominal"


def pin_probe(path, pins):
    if path.is_symlink() or path.resolve() not in pins:
        raise ValueError("probe path is outside the pinned readback")
    return pinned(path, pins[path.resolve()])


def read_probes(repair, repair_sha, previous, geometries, plan, plan_sha, selection, selection_sha):
    supplement = pinned(repair, repair_sha)
    if sha(repair.with_suffix(".md")) != supplement["plan_md_sha256"]:
        raise ValueError("supplemental plan document changed")
    pins = {(ROOT / p).resolve(): h for p, h in supplement["input_sha256"].items()}
    tracker_path = (
        ROOT / "src/cloud_edge_robot_arm/vision/registered_object_tracking.py"
    ).resolve()
    if (
        pins.get(plan.resolve()) != plan_sha
        or pins.get(selection.resolve()) != selection_sha
        or pins.get(tracker_path) != sha(tracker_path)
        or any(sha(path) != digest for path, digest in pins.items())
        or (previous / "allocation.public.json").exists()
        or any(previous.glob("g*/instance"))
        or any(previous.glob("g*/allocation.json"))
    ):
        raise ValueError("prior allocation state or original plan/tracker/input digest changed")
    failure = pin_probe(previous / "before-allocation-repair/evidence.json", pins)
    if (
        failure["recorded_exit_code"],
        failure["heldout_cases_issued"],
        failure["registered_episodes"],
    ) != (1, 0, 0):
        raise ValueError("heldout release was already issued")
    probes = {}
    for view, geometry in geometries.items():
        folder = previous / "camera-registration" / view
        result_file = folder / "original-result.json"
        frame_file = folder / "original-observation.json"
        result = pin_probe(result_file, pins)
        obs = RGBDObservation.model_validate(pin_probe(frame_file, pins))
        runtime.validate_camera(obs, geometry)
        if (
            result["view"] != view
            or result["camera"] != geometry["camera"]
            or obs.frame_id != result["frame_id"]
            or obs.checksum_sha256 != result["checksum_sha256"]
            or obs.episode_id != result["episode_id"]
            or obs.scene_id != result["scene_id"]
            or obs.scene_id != "PROPOSAL_DEVELOPMENT_CAMERA_PROBE"
            or obs.sim_time_s != 0
            or result["physics_steps"] != 0
            or result["worker_dispatches"] != 0
            or result["illustrative_scene_seed"] != 24112000
            or result["frame_file_sha256"] != pins[frame_file.resolve()]
            or result["supported"] is not (view == "nominal")
            or (view == "nominal" and result["reason"] is not None)
        ):
            raise ValueError("original camera probe frame, clock, scene or verdict binding changed")
        probes[view] = {**result, "original_result_sha256": pins[result_file.resolve()]}
    if len({r["episode_id"] for r in probes.values()}) != len(probes):
        raise ValueError("camera probe episodes must be distinct")
    return probes


def probe_camera(view, expected_geometry, catalog, output):
    """One neutral camera frame, zero physics steps, no worker or control action."""
    output.mkdir()
    backend = MuJoCoPhysicsBackend()
    seed = 24112000
    config = runtime.SimulatorConfig(
        model_path=str(ROOT / expected_geometry["asset_path"]),
        seed=seed,
        physics_dt_s=1 / 240,
        domain_randomization=False,
        render_rgb=True,
        render_depth=True,
    )
    try:
        backend.initialize(config)
        backend.reset(
            runtime.PhysicalScenarioConfig(
                scenario_id="PROPOSAL_DEVELOPMENT_CAMERA_PROBE",
                seed=seed,
                object_pose=runtime.Pose(x=0.45, y=0, z=0.035),
                object_yaw_rad=0.0,
            )
        )
        if view != "nominal":
            position, look_at = VIEWS[CAMERA_VIEWS[view]]
            backend.set_camera_position(position, look_at_m=look_at)
        frame = runtime.observation_from_sensor_frame(
            backend.capture_sensor_frame(),
            source="mujoco_camera",
            png_compress_level=1,
        )
        runtime.validate_camera(frame, expected_geometry)
        supported, reason = True, None
        try:
            runtime.bootstrap_registered_collection_tracker_v2(
                frame,
                NativeGeometryRegistration(expected_geometry),
                source_root=ROOT,
                source_hashes=catalog,
                nominal_policy=runtime.registered_nominal_region_policy_v1(catalog),
            )
        except ValueError as error:
            supported, reason = False, str(error)
        if backend.total_physics_steps != 0:
            raise ValueError("camera registration probe advanced physics")
        write(output / "original-observation.json", frame.model_dump(mode="json"))
        result = {
            "view": view,
            "camera": expected_geometry["camera"],
            "supported": supported,
            "reason": reason,
            "physics_steps": 0,
            "worker_dispatches": 0,
            "scene_id": frame.scene_id,
            "episode_id": frame.episode_id,
            "frame_id": frame.frame_id,
            "checksum_sha256": frame.checksum_sha256,
            "frame_file_sha256": sha(output / "original-observation.json"),
            "setup_commands": backend.command_records,
            "illustrative_scene_seed": seed,
        }
        write(output / "original-result.json", result)
        return result
    finally:
        backend.shutdown()


def readback_reset(case, boundaries):
    """Offline check of the exact requested and observed step-zero input, after the run."""
    if len(boundaries) != 2:
        raise ValueError("reset requires its original BEGIN and END")
    begin, end = boundaries
    if (
        (begin["phase"], end["phase"]) != ("BEGIN", "END")
        or any(
            event["kind"] != "RESET"
            or event["error_type"] is not None
            or event["error"] is not None
            or event["physics_step"] != 0
            for event in boundaries
        )
        or (
            begin["operation_id"] != end["operation_id"] or begin["parameters"] != end["parameters"]
        )
    ):
        raise ValueError("reset events differ in operation, request, step, status or phase")
    request = end["parameters"]["requested"]
    xyz = case["reset_fixture_center_m"]
    yaw = case["yaw_rad"]
    if (
        request["scenario_id"] != "S01_NORMAL_STATIC"
        or type(request["seed"]) is not int
        or request["seed"] != case["seed"]
        or [request["object_pose"][k] for k in "xyz"] != xyz
        or request["object_yaw_rad"] != yaw
    ):
        raise ValueError("reset request differs from preallocated scene, seed or pose")
    state = end["result"]["physics_state"]
    co, si = math.cos(yaw), math.sin(yaw)
    rotation = [co, -si, 0.0, si, co, 0.0, 0.0, 0.0, 1.0]
    if (
        not end["episode_id"]
        or state["episode_id"] != end["episode_id"]
        or state["physics_step"] != 0
        or state["sim_time_s"] != 0
        or end["sim_time_s"] != 0
        or end["result"]["physics_dt_s"] != 1 / 240
        or not np.allclose(state["object_geom_rotation_row_major"], rotation, atol=1e-12, rtol=0)
        or any(
            not np.allclose(state[k], xyz, atol=1e-12, rtol=0)
            for k in ("object_geom_position_m", "object_position_m")
        )
    ):
        raise ValueError("reset physical state or clock differs from preallocated initialization")
    return {
        "episode_id": end["episode_id"],
        "physics_step": 0,
        "scenario": request["scenario_id"],
        "seed": request["seed"],
        "observed_center_m": state["object_geom_position_m"],
        "requested_yaw_rad": yaw,
        "observed_rotation_row_major": state["object_geom_rotation_row_major"],
    }


class RegisteredResetBackend(MuJoCoPhysicsBackend):
    """Retain one original RESET operation and install the allocated fixed view at step zero."""

    def __init__(self, directory, case):
        super().__init__()
        self._case_directory = directory
        self._allocated_view = case["view"]

    def reset(self, scenario):
        boundaries = []

        def record(event):
            if event.kind == "RESET":
                boundaries.append(runtime.plain(event))

        with self.observe_operation_boundaries(record):
            super().reset(scenario)
        write(self._case_directory / "reset-observed.json", boundaries)
        if self._allocated_view != "nominal":
            position, look_at = VIEWS[CAMERA_VIEWS[self._allocated_view]]
            self.set_camera_position(position, look_at_m=look_at)
        write(self._case_directory / "camera-setup.json", self.command_records)


class HeldoutEpisode(guarded_clock.GuardedClockEpisode):
    def __init__(self, directory, allocation, allocation_sha, catalog):
        super().__init__(directory, allocation, allocation_sha, catalog)
        self.backend = RegisteredResetBackend(directory, allocation["case"])
        self.robot = runtime.MuJoCoSkillRobot(self.backend)
        self.executor = guarded_clock.RecordedExecutor(
            self, runtime.SkillExecutor(robot=self.robot, registry=runtime.SkillRegistry.default())
        )


def allocate(plan, plan_sha, selection, selection_sha, repair, repair_sha, previous, raw, output):
    protocol = pinned(plan, plan_sha)
    pinned_md = sha(plan.with_suffix(".md"))
    if pinned_md != protocol["plan_md_sha256"]:
        raise ValueError("plan markdown changed")
    for path, digest in protocol["input_sha256"].items():
        if sha(ROOT / path) != digest:
            raise ValueError(f"plan input changed: {path}")
    parent = plan.parent.parent / PARENT_ROUND / "allocation.public.json"
    template = pinned(parent, protocol["input_sha256"][str(parent.resolve().relative_to(ROOT))])
    decision = pinned(selection, selection_sha)
    visual_selection = decision["selected_view"]
    potential_cases = allocated_cases(visual_selection)
    catalog = runtime.inventory()
    if (
        os.environ.get("MUJOCO_GL") != "egl"
        or raw.exists()
        or output.exists()
        or runtime.digest(catalog) != template["component_catalog_sha256"]
    ):
        raise ValueError("EGL, sealed r593 source generation or exclusive output required")
    budget = len(potential_cases) * 2**31
    free = shutil.disk_usage(raw.parent).free
    if free < budget:
        raise ValueError("insufficient reserved headroom for every assigned trajectory")
    geometries = {
        view: register_camera(view, decision["views"][view]["camera"], template["geometry"])
        for view in {c["view"] for c in potential_cases}
    }
    probes = read_probes(
        repair, repair_sha, previous, geometries, plan, plan_sha, selection, selection_sha
    )
    selected = executable_view(visual_selection, probes)
    cases = allocated_cases(selected)
    raw.mkdir()
    archive = runtime.bind_catalog(raw, catalog, template["geometry"]["asset_path"])
    source_hashes = {**template["sources_sha256"], **{p: sha(ROOT / p) for p in SOURCES}}
    check_sources({"sources_sha256": source_hashes})
    issued = datetime.now(UTC).isoformat()
    published = []
    for row in cases:
        directory = raw / row["id"]
        directory.mkdir()
        case = {
            **template["case"],
            **row,
            "visual_seed": row["seed"],
            "visual_id": RELEASE + "/" + row["id"],
            "release": RELEASE,
            "private_output": row["id"] + "/instance",
        }
        allocation = {
            "schema": "proposal.heldout.development.case.v1",
            "baseline": protocol["baseline"],
            "issued_at": issued,
            "case": case,
            "asset_sha256": template["asset_sha256"],
            "geometry": geometries[row["view"]],
            "capture_grid": template["capture_grid"],
            "selected_entry": template["selected_entry"],
            "intent_descriptor": template["intent_descriptor"],
            "sources_sha256": source_hashes,
            "catalog": archive,
            "component_catalog_sha256": template["component_catalog_sha256"],
            "r1_allocation_sha256": template["r1_allocation_sha256"],
            "software_receipt_sha256": template["software_receipt_sha256"],
            "template_sha256": sha(parent),
            "readback_plan_sha256": repair_sha,
            "plan_sha256": plan_sha,
            "plan_md_sha256": pinned_md,
            "selection_sha256": selection_sha,
            "scope": "DEVELOPMENT_COMPONENT_ONLY",
        }
        destination = directory / "allocation.json"
        write(destination, allocation)
        published.append(
            {
                **row,
                "allocation_file": str(destination.relative_to(raw)),
                "allocation_sha256": sha(destination),
                "camera_configuration_sha256": runtime.digest(geometries[row["view"]]["camera"]),
            }
        )
    summary = {
        "schema": "proposal.heldout.development.allocation.v1",
        "issued_at": issued,
        "baseline": protocol["baseline"],
        "scope": "DEVELOPMENT_COMPONENT_ONLY",
        "release": RELEASE,
        "plan_sha256": plan_sha,
        "plan_md_sha256": pinned_md,
        "template_sha256": sha(parent),
        "readback_plan_sha256": repair_sha,
        "readback_plan_file": str(repair.resolve().relative_to(ROOT)),
        "selection_file": str(selection.resolve().relative_to(ROOT)),
        "selection_sha256": selection_sha,
        "selected_view": selected,
        "offline_selected_view": visual_selection,
        "online_selected_view": selected,
        "offline_selection_same_as_nominal": visual_selection == "nominal",
        "paired_executable_views_coincide": selected == "nominal",
        "selected_oblique_arm_eligible": probes[visual_selection]["supported"],
        "camera_registration_probes": probes,
        "cases": published,
        "source_sha256": source_hashes,
        "asset_sha256": template["asset_sha256"],
        "geometry": geometries,
        "catalog": archive,
        "disk_headroom_bytes": free,
        "reserved_bytes_per_case": 2**31,
        "formal_claims": 0,
        "model_calls": 0,
        "hardware_actions": 0,
        "retries_per_case": 0,
    }
    write(raw / "allocation.public.json", summary)
    write(output, summary)


def capture(manifest, manifest_sha, raw, case_id):
    master = pinned(manifest, manifest_sha)
    if sha(raw / "allocation.public.json") != manifest_sha or os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("foreign allocation root or missing EGL")
    selected = master["selected_view"]
    cases = allocated_cases(selected)
    entries = master["cases"]
    projection = [{k: e[k] for k in cases[0]} for e in entries]
    if projection != cases or case_id not in {r["id"] for r in cases}:
        raise ValueError("incomplete or altered proposal allocation")
    row = next(r for r in entries if r["id"] == case_id)
    if row["allocation_file"] != case_id + "/allocation.json":
        raise ValueError("allocation directory differs from assigned case")
    case_allocation = pinned(raw / row["allocation_file"], row["allocation_sha256"])
    case = case_allocation["case"]
    if any(case[k] != row[k] for k in cases[0]) or case["visual_id"] != RELEASE + "/" + case_id:
        raise ValueError("case parameters or run identity differ from the frozen manifest")
    decision = pinned(ROOT / master["selection_file"], master["selection_sha256"])
    camera = decision["views"][row["view"]]["camera"]
    if (
        case["visual_seed"] != row["seed"]
        or case_allocation["selection_sha256"] != master["selection_sha256"]
        or decision["selected_view"] != master["offline_selected_view"]
        or executable_view(decision["selected_view"], master["camera_registration_probes"])
        != selected
        or case_allocation["geometry"]["camera"] != camera
        or runtime.digest(camera) != row["camera_configuration_sha256"]
    ):
        raise ValueError("case lost its paired seed or immutable camera binding")
    check_sources(case_allocation)
    catalog = runtime.inventory()
    archive = case_allocation["catalog"]
    if catalog != pinned(raw / archive["private_filename"], archive["archived_json_sha256"]):
        raise ValueError("frozen worker source inventory differs")
    directory = raw / case_id / "instance"
    directory.mkdir()
    started = time.monotonic()
    write(
        directory / "started.json",
        {
            "command": sys.argv,
            "start_utc": datetime.now(UTC).isoformat(),
            "case_id": case_id,
            "allocation_sha256": row["allocation_sha256"],
            "master_sha256": manifest_sha,
            "attempt": 1,
        },
    )
    episode = HeldoutEpisode(directory, case_allocation, row["allocation_sha256"], catalog)
    try:
        episode.run()
    except BaseException as error:
        write(
            directory / "interrupted.json",
            {
                "class": type(error).__name__,
                "reason": str(error),
                "wall_s": time.monotonic() - started,
            },
        )
        raise
    finally:
        episode.backend.shutdown()
    boundaries = read(directory / "reset-observed.json")
    reset = readback_reset(row, boundaries)
    seal = read(directory / "acquisition-seal.json")
    index = pinned(directory / "pixel-index.json", seal["index_sha256"])
    run = pinned(directory / "run.json", seal["run_sha256"])
    if (
        index["episode"] != reset["episode_id"]
        or index["allocation_sha256"] != row["allocation_sha256"]
    ):
        raise ValueError("recorded reset episode or frame allocation diverged")
    write(
        directory / "capture-receipt.json",
        {
            "case_id": case_id,
            "view": row["view"],
            "allocation_sha256": row["allocation_sha256"],
            "master_sha256": manifest_sha,
            "physical_reset": reset,
            "reset_observed_sha256": sha(directory / "reset-observed.json"),
            "camera_setup_sha256": sha(directory / "camera-setup.json"),
            "source_seal_sha256": sha(directory / "acquisition-seal.json"),
            "start_receipt_sha256": sha(directory / "started.json"),
            "wall_s": time.monotonic() - started,
            "frames": len(index["frames"]),
            "last_step": index["frames"][-1]["physics_step"],
            "stop": run.get("stop"),
            "stages": [{"skill": a["skill"], "status": a["status"]} for a in run["actions"]],
            "lease": run["lease_summary"],
            "original_data": seal,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("allocate")
    for name in (
        "plan",
        "plan_sha",
        "selection",
        "selection_sha",
        "repair",
        "repair_sha",
        "previous",
        "raw",
        "output",
    ):
        freeze.add_argument(name, type=str if name.endswith("_sha") else Path)
    run = commands.add_parser("capture")
    run.add_argument("manifest", type=Path)
    run.add_argument("manifest_sha")
    run.add_argument("raw", type=Path)
    run.add_argument("case_id")
    args = vars(parser.parse_args())
    if args.pop("command") == "allocate":
        allocate(**args)
    else:
        capture(**args)


if __name__ == "__main__":
    main()
