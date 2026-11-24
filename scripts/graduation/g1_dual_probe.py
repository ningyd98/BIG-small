"""Probe the registered two-marker tracker, target and servo at zero physics steps."""

from __future__ import annotations

import argparse
import base64
import copy
import sys
import traceback
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import g1_dual_asset as asset
from scripts.graduation import g1_dual_observer as observer
from scripts.graduation import g1_dual_trials as trials
from scripts.graduation import g1_mount_trials
from scripts.graduation.perception_io import ROOT, sha, write
from scripts.graduation.perception_pixels import biased_observation
from scripts.graduation.proposal_translated import STORED_POSES, config

from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame

POSITIVE = ("both", "only-7", "only-8")
NEGATIVE = (
    "no-marker",
    "no-depth",
    "duplicate-id",
    "unknown-id",
    "wrong-asset",
    "wrong-transform",
    "wrong-source",
    "conflict",
    "stale",
    "wrong-scene",
    "wrong-calibration",
)
EXPECTED = {"both": [7, 8], "only-7": [7], "only-8": [8]}


def qualifies(rows):
    if not rows or any(r["physics_steps"] != 0 or r["commands"] != 0 for r in rows):
        return False
    for kind in (*POSITIVE, *NEGATIVE):
        key = "path_success" if kind in POSITIVE else "control_demonstrated"
        if not any(r["kind"] == kind and r[key] is True for r in rows):
            return False
    return True


def visibility_limited(row):
    """Allow a registered alternative pose only when the intended optical stimulus was absent."""
    if "stopped_stage" in row:
        if (
            row["stopped_stage"] == "pixel_bootstrap"
            and row["reason"]
            == "initial RGB-D identity/extent unavailable: target_outer_boundary_depth_unresolved"
        ):
            return True
        return any(
            reason in row["reason"]
            for reason in (
                "known_marker_not_observed",
                "marker_resolution_insufficient",
                "marker_boundary_clipped",
                "marker_depth_not_planar",
                "registered_object_not_upright",
                "dual_marker_grasp_conflict",
                "marker_metric_depth_unavailable",
                "servo initial target/registered marker identity unavailable",
            )
        )
    kind = row["kind"]
    if kind in POSITIVE:
        return (
            row["usable_ids"] != EXPECTED[kind]
            or row["measured_reason"] == "dual_marker_grasp_conflict"
        )
    if kind == "duplicate-id":
        return row["observed_ids"] != [7, 7]
    if kind == "unknown-id":
        return 9 not in row["observed_ids"]
    if kind == "conflict":
        return row["usable_ids"] != [7, 8]
    if kind == "no-depth":
        return not row["observed_ids"]
    return False


@contextmanager
def render_intervention(model, kind):
    """Change only diagnostic print colours and restore them after the acquisition."""
    before = model.geom_rgba.copy()
    try:
        hide = {"only-7": (8,), "only-8": (7,), "no-marker": (7, 8)}.get(kind, ())
        for code in hide:
            prefix = asset.MARKER_PREFIXES[code]
            for name in ("quiet", *(f"r{r}c{c}" for r in range(6) for c in range(6))):
                model.geom_rgba[model.geom(prefix + name).id, 3] = 0
        if kind in {"unknown-id", "duplicate-id"}:
            bits = asset.bits(9 if kind == "unknown-id" else 7)
            for r in range(6):
                for c in range(6):
                    i = model.geom(asset.MARKER_PREFIXES[8] + f"r{r}c{c}").id
                    model.geom_rgba[i, :3] = 0.98 if bits[r, c] else 0.01
        yield
    finally:
        model.geom_rgba[:] = before


def change_packet(base, kind, **fields):
    return RGBDObservation.model_validate(
        {
            **base.model_dump(),
            **fields,
            "frame_id": "dev-" + kind + "-" + base.frame_id,
            "observation_id": "",
            "checksum_sha256": "",
        }
    )


def fault_packet(base, kind, labels, instances):
    if kind == "no-depth":
        return biased_observation(base, None)
    if kind == "stale":
        return change_packet(base, kind, captured_at=base.captured_at - timedelta(seconds=10))
    if kind == "wrong-scene":
        return change_packet(base, kind, scene_id="G1_DIAGNOSTIC_WRONG_SCENE")
    if kind == "wrong-calibration":
        return change_packet(base, kind, calibration_version="g1-intentional-foreign-calibration")
    if kind == "conflict":
        # This deliberate RGB-D corruption belongs exclusively to the diagnostic set.
        ids = [i for i, name in labels.items() if name.startswith(asset.MARKER_PREFIXES[8])]
        region = cv2.dilate(
            np.isin(instances, ids).astype("uint8"), np.ones((5, 5), dtype="uint8")
        ).astype(bool)
        depth = (
            np.frombuffer(base64.b64decode(base.depth_float32_base64), dtype="<f4")
            .copy()
            .reshape(instances.shape)
        )
        depth[region & (depth > 0)] += 0.030
        return change_packet(
            base,
            kind,
            depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
            valid_mask_base64=None,
        )
    return base


def capture(backend, kind, *, segmented):
    with render_intervention(backend._model, kind):
        if segmented:
            sensor, ids, labels, hashes = backend.capture_sensor_frame_with_instances()
            trials.require(
                len(hashes) == 3 and len(set(hashes)) == 1,
                "probe RGB, depth and instance IDs differ in physical state",
            )
        else:
            sensor = backend.capture_sensor_frame()
    obs = observation_from_sensor_frame(sensor, source="mujoco_camera", png_compress_level=1)
    trials.require(
        backend.total_physics_steps == 0 and obs.sim_time_s == 0, "probe advanced physics"
    )
    if not segmented:
        return obs
    instances = np.asarray(ids, dtype="<i2").reshape(obs.height, obs.width)
    return obs, labels, instances, hashes[0]


def mapping(measurement, labels, instances):
    checked = {}
    for code in measurement["usable_ids"]:
        corners = np.array(measurement["by_id"][str(code)]["ordered_corners_px"])
        x, y = np.rint(corners.mean(axis=0)).astype(int)
        name = labels.get(int(instances[y, x]), "")
        checked[str(code)] = {
            "center_pixel": [int(x), int(y)],
            "actual_geometry": name,
            "matches": name.startswith(asset.MARKER_PREFIXES[code]),
        }
    return checked


def protect_sources(kind, geometry, full):
    altered, hashes = copy.deepcopy(geometry), dict(full)
    if kind == "wrong-source":
        hashes[asset.ASSET_PATH] = "0" * 64
    elif kind == "wrong-asset":
        altered["pose_marker"]["marked_asset_sha256"] = "0" * 64
    elif kind == "wrong-transform":
        altered["development_dual"]["markers"]["8"]["object_T_marker"][3] += 0.02
    return altered, hashes


def target(owner, original, tracker, observation, state):
    audit = []
    _, step, binding, _, _ = runtime.registered_collection_step_v2(
        original,
        index=0,
        observation=observation,
        state=state,
        tracker=tracker,
        lease_source=owner.current(),
        evidence_sink=audit.append,
    )
    trials.require(
        len(audit) == 1
        and audit[0]["observation_id"] == observation.frame_id
        and audit[0]["checksum_sha256"] == observation.checksum_sha256,
        "read-only target was derived from a different frame",
    )
    return step.parameters["target_pose"], binding.digest(), audit[0]


def result_of(call):
    try:
        return call(), None
    except ValueError as exc:
        return None, str(exc)


def registered_tracker(frame, registration, full):
    return runtime.bootstrap_registered_collection_tracker_v2(
        frame,
        registration,
        source_root=ROOT,
        source_hashes=full,
        nominal_policy=runtime.registered_nominal_region_policy_v1(full),
    )


def expected_refusal(kind, measurement, servo_error, target_error):
    if not servo_error or not target_error:
        return False
    reason = measurement["reason"]
    if kind == "stale":
        return ("fresh" in servo_error or "reversed" in servo_error) and "fresh" in target_error
    if kind == "wrong-scene":
        return (
            reason == "registered_scene_mismatch"
            and "scene" in servo_error
            and "scene" in target_error
        )
    if kind == "wrong-calibration":
        return (
            reason == "registered_camera_mismatch"
            and "calibration" in servo_error
            and "calibration" in target_error
        )
    if kind == "conflict":
        return (
            reason == "dual_marker_grasp_conflict"
            and measurement["usable_ids"] == [7, 8]
            and measurement["target_disagreement_m"] > asset.AGREEMENT_M
        )
    if kind == "duplicate-id":
        return reason == "duplicate_marker_id" and measurement["observed_ids"] == [7, 7]
    if kind == "unknown-id":
        return reason == "foreign_marker_id" and 9 in measurement["observed_ids"]
    if kind == "no-depth":
        return reason == "marker_metric_depth_unavailable" and not measurement["usable"]
    return (
        kind == "no-marker"
        and not measurement["observed_ids"]
        and reason == "known_marker_not_observed"
    )


def run_control(directory, pose_label, xyz_yaw, seed, kind, geometry, full, build_sha):
    directory.mkdir()
    x, y, z, yaw = xyz_yaw
    identifier = "g1-dual-zero-step/" + directory.name
    allocation = dict(
        baseline=trials.builder.BASE,
        component_catalog_sha256=runtime.digest(full),
        intent_descriptor={"type": "read-only registered target probe", "stages": ["MOVE_ABOVE"]},
        case={"visual_id": identifier, "visual_seed": seed},
        runtime_build_sha256=build_sha,
    )
    write(directory / "probe-allocation.json", allocation)
    owner = runtime.Owner(directory, allocation, sha(directory / "probe-allocation.json"))
    backend = runtime.MuJoCoPhysicsBackend()
    packets, details = {}, {}
    report = dict(
        kind=kind,
        pose=pose_label,
        pose_xyzyaw=list(xyz_yaw),
        seed=seed,
        path_success=False,
        control_demonstrated=False,
    )
    record = {"diagnostic": kind != "both", "diagnostic_condition": kind}
    initial_kind = kind if kind in POSITIVE else "both"
    try:
        backend.initialize(config({"geometry": geometry}, seed))
        compiled = trials.mass_properties(backend._model)
        scenario = runtime.PhysicalScenarioConfig(
            scenario_id=asset.SCENE_ID,
            seed=seed,
            object_pose=runtime.Pose(x=x, y=y, z=z),
            object_yaw_rad=yaw,
        )
        scenario = trials.bind_scenario_mass(scenario, asset.BODY_MASS_KG, compiled["mass_kg"])
        backend.reset(scenario)
        props = trials.mass_properties(backend._model)
        trials.require(
            all(np.allclose(compiled[k], props[k], atol=1e-12, rtol=0) for k in props),
            "probe reset changed registered mass properties",
        )
        details["registered_reset"] = {
            "requested": runtime.plain(scenario),
            "compiled": compiled,
            "reset": props,
        }
        robot = runtime.MuJoCoSkillRobot(backend)
        state = robot.get_state()
        reference = capture(backend, initial_kind, segmented=False)
        packets["bootstrap"] = reference
        geometry_bound, source_bound = protect_sources(kind, geometry, full)
        stage = "registration"
        try:
            reg = NativeGeometryRegistration(geometry_bound)
            reg.validate_asset(ROOT)
            stage = "pixel_bootstrap"
            color, evidence = runtime.bootstrap_collection_tracker(reference, geometry_bound)
            if kind == "wrong-source":
                stage = "registered_tracker_bootstrap"
                registered_tracker(reference, reg, source_bound)
            stage = "original_plan"
            lease = owner.current()
            original = runtime.build_collection_contract_v2(
                assignment=allocation["case"],
                current_owner={
                    "task_id": "g1-readonly-target",
                    "plan_id": "g1-readonly-plan",
                    "issued_at": lease.acquired_at,
                    "deadline_at": lease.acquired_at + timedelta(seconds=3600),
                    "role_sha256": runtime.digest(allocation["intent_descriptor"]),
                    "lease": lease,
                },
                geometry=geometry_bound,
                source_hashes=source_bound,
                observation=reference,
                protocol_settings={"timeout_basis": "physics_steps"},
            )
            stage = "initial_registered_target"
            initial_frame = capture(backend, initial_kind, segmented=False)
            packets["initial-target"] = initial_frame
            tracker = registered_tracker(initial_frame, reg, source_bound)
            initial_target, _, initial_audit = target(
                owner, original, tracker, initial_frame, state
            )
            details["initial_registered_target"] = initial_audit
            stage = "servo_reference"
            servo_reference = capture(backend, initial_kind, segmented=False)
            packets["servo-reference"] = servo_reference
            provider = runtime.OpenCVServoFeedback(
                servo_reference,
                color,
                evidence,
                skill="MOVE_ABOVE",
                initial_target=runtime.Pose.model_validate(initial_target),
                marker_family_id=reg.marker_family_id,
                verify_mujoco_calibration=True,
            )
        except ValueError as exc:
            report.update(stopped_stage=stage, reason=str(exc))
            if kind in {"wrong-asset", "wrong-transform", "wrong-source"}:
                report["control_demonstrated"] = stage == (
                    "registered_tracker_bootstrap" if kind == "wrong-source" else "registration"
                ) and any(
                    term in str(exc).lower()
                    for term in ("source", "asset", "binding", "sha256", "geometry")
                )
        else:
            base, labels, instances, state_hash = capture(backend, kind, segmented=True)
            current = fault_packet(base, kind, labels, instances)
            packets["raw-current"] = base
            packets["tested-current"] = current
            # The same packet goes first to the time-critical servo, then to registered_step_v2.
            servo_target, servo_error = result_of(lambda: provider.update(current))
            # Native tracker chronology permits its own retained same-step handoff. A distinct
            # acquisition may become its next current frame only after physics advances. Bind
            # each static pixel probe's independent tracker to that exact current capture.
            # Foreign scene/clock/calibration controls instead test the pre-existing live context.
            bound_error = None
            if kind not in {"stale", "wrong-scene", "wrong-calibration"}:
                current_tracker, bound_error = result_of(
                    lambda: registered_tracker(current, reg, full)
                )
                if current_tracker is not None:
                    tracker = current_tracker
            registered, target_error = (
                (None, bound_error)
                if bound_error
                else result_of(lambda: target(owner, original, tracker, current, state))
            )
            preview = runtime.registered_collection_grounding_preview_v2(tracker, current, state)
            measured = observer.measure_frame(current, geometry)
            board = mapping(measured, labels, instances)
            label_path = directory / "instance-labels.npy"
            with label_path.open("xb") as stream:
                np.save(stream, instances, allow_pickle=False)
            write(directory / "instance-names.json", {str(k): v for k, v in labels.items()})
            details.update(
                bootstrap_pixel_target=evidence["original_pixel_target"],
                bootstrap_grasp=evidence["resolved_top_grasp_tcp"],
                reference_state=runtime.plain(state),
                original_sha256=original.digest(),
                current_state_sha256=state_hash,
                source_generation=trials.native.digest(full),
                measured=measured,
                board_instance_match=board,
                actual_preview=preview.to_payload(),
                current_registered_bootstrap_error=bound_error,
                current_registered_target=registered[2] if registered else None,
                current_servo_samples=runtime.plain(provider.records),
            )
            truth = backend.current_physics_observation()
            rotation = np.asarray(truth.object_geom_rotation_row_major).reshape(3, 3)
            actual_tcp = (
                np.asarray(truth.object_geom_position_m)
                + rotation @ np.asarray(geometry["object_to_tcp"]).reshape(4, 4)[:3, 3]
            )
            report.update(
                frame_id=current.frame_id,
                checksum=current.checksum_sha256,
                observation_id=current.observation_id,
                usable_ids=measured["usable_ids"],
                observed_ids=measured["observed_ids"],
                selected_id=measured["selected_id"],
                measured_reason=measured["reason"],
                target_disagreement_m=measured["target_disagreement_m"],
                mapping=board,
                bootstrap=True,
                preview_status=preview.status,
                preview_reason=preview.reason,
                current_registered_bootstrap_error=bound_error,
                servo_error=servo_error,
                target_error=target_error,
                initial_target=initial_target,
                servo_target=runtime.plain(servo_target),
                target=registered[0] if registered else None,
                tcp_error_mm=None
                if not measured["usable"]
                else float(
                    1000 * np.linalg.norm(np.asarray(measured["grasp_world_m"]) - actual_tcp)
                ),
            )
            if (
                kind in POSITIVE
                and registered
                and servo_target is not None
                and preview.status == "DERIVED"
            ):
                current_inputs = registered[2]["inputs"]
                require_same = (
                    measured["checksum"]
                    == current.checksum_sha256
                    == current_inputs["observation_checksum_sha256"]
                    and provider.records[-1]["checksum_sha256"] == current.checksum_sha256
                    and current_inputs["asset_sha256"] == asset.ASSET_SHA
                    and measured["usable_ids"] == EXPECTED[kind]
                    and measured["selected_id"] == min(EXPECTED[kind])
                    and all(v["matches"] for v in board.values())
                    and np.allclose(
                        current_inputs["grasp_tcp_world_m"],
                        measured["grasp_world_m"],
                        atol=1e-10,
                        rtol=0,
                    )
                    and np.allclose(
                        preview.grasp_tcp_world_m, measured["grasp_world_m"], atol=1e-10, rtol=0
                    )
                    and np.allclose(
                        [registered[0][k] for k in "xy"],
                        measured["grasp_world_m"][:2],
                        atol=1e-10,
                        rtol=0,
                    )
                )
                report["path_success"] = bool(require_same)
            elif kind in NEGATIVE and preview.status != "DERIVED":
                report["control_demonstrated"] = expected_refusal(
                    kind, measured, servo_error, target_error
                )
        report["physics_steps"] = backend.total_physics_steps
        report["commands"] = len(backend.command_records)
        trials.require(
            report["physics_steps"] == report["commands"] == 0,
            "probe unexpectedly advanced or issued commands",
        )
        report["worker"] = owner.close(True)
    except BaseException:
        write(directory / "interrupted.json", {"traceback": traceback.format_exc()})
        raise
    finally:
        for label, packet in packets.items():
            write(directory / (label + ".json"), packet.model_dump(mode="json"))
        write(directory / "probe-trace.json", {**record, **details})
        backend.shutdown()
    write(directory / "result.json", report)
    files = {p.name: sha(p) for p in directory.iterdir() if p.is_file()}
    write(directory / "seal.json", files)
    return {**report, "private_seal_sha256": sha(directory / "seal.json")}


def run(plan_file, private):
    repository, plan, lock, build_sha, gate = trials.context(plan_file, private)
    dest = private / "probes"
    dest.mkdir()
    imports = g1_mount_trials.project_imports(lock)
    args = trials.registrations(repository, plan, lock)
    desc, geometry, full = args["dual"]
    geometry_check = asset.audit_asset(ROOT)
    write(dest / "compiled-geometry.json", geometry_check)
    write(plan_file.with_name("compiled-geometry.public.json"), geometry_check)
    write(dest / "development-source-inventory.json", full)
    write(dest / "development-geometry.json", geometry)
    rows = []
    required_poses = [("preregistered-" + str(i), p) for i, p in enumerate(plan["zero_step_poses"])]
    fallback = [
        ("previously-registered-translated-" + str(i), list(p)) for i, p in enumerate(STORED_POSES)
    ]
    for index, (label, pose) in enumerate([*required_poses, *fallback]):
        if index >= len(required_poses) and qualifies(rows):
            break
        for kind in (*POSITIVE, *NEGATIVE):
            if index >= len(required_poses):
                ok = "path_success" if kind in POSITIVE else "control_demonstrated"
                earlier = [row for row in rows if row["kind"] == kind]
                if any(row[ok] for row in earlier) or not all(
                    visibility_limited(row) for row in earlier
                ):
                    continue
            directory = dest / (label + "-" + kind)
            row = run_control(
                directory, label, pose, 24113040 + index, kind, geometry, full, build_sha
            )
            rows.append(row)
    checked = {p.relative_to(dest).as_posix(): sha(p) for p in sorted(dest.glob("*/seal.json"))}
    output = dict(
        schema="g1.development.dual-marker.zero-step.v1",
        plan_sha256=trials.PLAN_SHA,
        runtime_build_sha256=build_sha,
        gate=gate,
        results=rows,
        eligible=qualifies(rows),
        attempts_by_control=dict(Counter(r["kind"] for r in rows)),
        physics_steps=sum(r["physics_steps"] for r in rows),
        dispatched_actions=sum(r["commands"] for r in rows),
        private_seal_sha256=checked,
        catalog_sha256=sha(dest / "development-source-inventory.json"),
        geometry=geometry,
        compiled_geometry_sha256=sha(dest / "compiled-geometry.json"),
        asset=desc,
        formal_simulations=0,
        formal_claims=0,
        hardware_actions=0,
        task_model_calls=0,
    )
    write(
        dest / "imports.json",
        dict(
            before=imports,
            after=g1_mount_trials.project_imports(lock),
            argv=sys.orig_argv,
            interpreter=sys.executable,
        ),
    )
    write(dest / "zero-step-probes.json", output)
    write(plan_file.with_name("zero-step-probes.public.json"), output)
    print(f"zero-step controls {len(rows)} eligible={output['eligible']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("private", type=Path)
    args = parser.parse_args()
    with trials.exclusive_egl(args.private.resolve()):
        run(args.plan.resolve(), args.private.resolve())
