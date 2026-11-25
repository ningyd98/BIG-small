"""Zero-command developer qualification on a separate, historically registered hardware fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LABEL = "explicitly synthetic CLEAR row for interface qualification only"


def dump(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(path, expected):
    if sha(path) != expected:
        raise ValueError("changed sealed diagnostic bytes: " + path.name)
    return json.loads(path.read_bytes())


def acquire_controls(repo, folder):
    from scripts.graduation import binding as b, dynamic_vision as rt, g1_dual_asset as asset
    from scripts.graduation import g1_dual_observer as observer, g1_dual_probe as probe, g1_dual_trials as dual
    from scripts.graduation import g1_visibility_trials as trials
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_formal_trials import identities
    from scripts.graduation.perception_io import ROOT
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import MuJoCoVisualServoController
    from cloud_edge_robot_arm.vision.owner_registration import _resolved_parameters, RegisteredGroundingFrameInputsV2, RegisteredGroundingPolicyV2

    generation = sha(ROOT / "binding-generation.json")
    files = checked(ROOT / "binding-generation.json", generation)["files"]
    old = repo / "experiments/results/g1-visibility-pose-repair-20261124"
    old_keys = checked(old / "batches/train-radial30-contact-d02-02/source-inventory.json",
                       "643272775723504533b27a6a6443c8624bca8f609d6c60c87af09bd90ec0868d")
    catalog = {k: files[k] for k in {*old_keys, "scripts/graduation/binding.py", "scripts/graduation/binding_score.py",
                                     "scripts/graduation/g1_dual_batch_score.py", "scripts/graduation/g1_dual_pixel_readback.py",
                                     "scripts/graduation/dynamic_vision.py"}}
    fixture = trials.qualified_preflight_pose(repo)
    records = []
    with trials.device(old):
        for mm in (0, 7):
            private = folder / ("offset-" + str(mm))
            private.mkdir()
            scene = "G1_CV_BINDING_DIAGNOSTIC"
            case = {**identities(scene + "/offset-" + str(mm)), "visual_id": scene + "/offset-" + str(mm),
                    "visual_seed": fixture["seed"], "release": "g1-cv-binding-qualification", "scene_id": scene,
                    "visual_stages_in_order": ["MOVE_ABOVE", "APPROACH", "GRASP", "LIFT", "MOVE_TO_REGION", "PLACE", "RELEASE", "RETREAT"]}
            geometry = asset.geometry_descriptor()
            allocation = dict(case=case, geometry=geometry, baseline="40f9cf2da56e7c8e4f4c5ea33dc28c8a3ae4c5d6",
                              runtime_build_sha256=generation, component_catalog_sha256=rt.digest(catalog),
                              intent_descriptor={"type": LABEL, "motion_authority": False})
            dump(private / "allocation.json", allocation)
            event = rt.Episode(private, allocation, sha(private / "allocation.json"), catalog)
            event.action = {}
            observed, observations, roles, actions, checks, control = [], {}, [], [], {}, []
            def capture(label):
                obs = event.capture(label)
                observations[obs.frame_id] = obs
                roles.append({"label": label, "frame_id": obs.frame_id})
                return obs
            def refused(name, operation):
                try:
                    operation()
                except ValueError as exc:
                    checks[name] = str(exc)
                    return
                raise AssertionError("negative accepted: " + name)
            def table_for(frame, frozen, offset):
                measured = observer.measure_frame(frame, geometry)
                if not measured["usable"]:
                    raise ValueError("diagnostic stimulus not observed: " + measured["reason"])
                if frozen is None:
                    rot = np.asarray(measured["rotation_object_to_world"]).reshape(3, 3)
                    yaw = np.arctan2(rot[1, 0], rot[0, 0])
                    delta = (offset * np.array([np.cos(yaw), -np.sin(yaw), 0]) / 1000).tolist()
                else:
                    delta = frozen["offset_object_m"]
                packet = b.frame_identity(frame)
                candidate = f"existing_tool_closure_axis:{offset:+.6f}"
                row = dict(candidate_id=candidate, direction="existing_tool_closure_axis", tangent_mm=offset,
                           offset_object_m=delta, orientation_wxyz=list(_DOWNWARD), clearance="CLEAR",
                           proof_sha256=b.digest({"scope": LABEL, "frame": packet, "offset_mm": offset}))
                return {**packet, "scope": LABEL, "rows": [row]}, candidate
            ok = False
            try:
                with bind_scene(scene):
                    backend = event.backend
                    backend.initialize(probe.config({"geometry": geometry}, fixture["seed"]))
                    mass = dual.mass_properties(backend._model)
                    x, y, z, yaw = fixture["pose_xyzyaw"]
                    scenario = rt.PhysicalScenarioConfig(scenario_id=scene, seed=fixture["seed"],
                                   object_pose=rt.Pose(x=x, y=y, z=z), object_yaw_rad=yaw)
                    backend.reset(dual.bind_scenario_mass(scenario, asset.BODY_MASS_KG, mass["mass_kg"]))
                    # Reset zero-step diagnostics may record CAPTURE_SENSOR_FRAME; this is counted separately.
                    state = event.robot.get_state()
                    boot = capture("color_reference")
                    event.color, event.evidence = rt.bootstrap_collection_tracker(boot, geometry)
                    lease = event.active()
                    original = event.original = rt.build_collection_contract_v2(assignment=case,
                        current_owner=dict(task_id=case["task_id"], plan_id=case["plan_id"], issued_at=lease.acquired_at,
                                           deadline_at=lease.acquired_at + timedelta(hours=1), role_sha256=rt.digest(allocation["intent_descriptor"]), lease=lease),
                        geometry=geometry, source_hashes=catalog, observation=boot,
                        protocol_settings={"timeout_basis": "physics_steps"})
                    initial_attempt = None
                    for index, skill in enumerate(case["visual_stages_in_order"]):
                        event.action = {}
                        frame = capture(skill + "/PRE")
                        table, cid = table_for(frame, initial_attempt.record()["spec"] if initial_attempt else None, mm)
                        lease = event.active()
                        if initial_attempt is None:
                            initial_attempt = b.BoundAttempt.select(original, lease, frame, table, cid, ledger=private / "grasp-binding.sqlite")
                            refused("unregistered_candidate", lambda: b.BoundAttempt.select(original, lease, frame, table, "not-registered", ledger=private / "grasp-binding.sqlite"))
                            foreign_table = dict(table, checksum_sha256=boot.checksum_sha256, frame_id=boot.frame_id)
                            refused("cross_frame", lambda: b.BoundAttempt.select(original, lease, frame, foreign_table, cid, ledger=private / "grasp-binding.sqlite"))
                            changed, other = table_for(frame, None, 14)
                            refused("second_selection", lambda: b.BoundAttempt.select(original, lease, frame, changed, other, ledger=private / "grasp-binding.sqlite"))
                        tracker = event.registered = probe.registered_tracker(frame, event.registration, catalog)
                        contract, step, issued, online, _ = initial_attempt.issue_step(original, index=index, observation=frame,
                                    state=state, tracker=tracker, lease_source=event.active(), table=table, evidence_sink=event.audit.append)
                        issue = event.audit[-1]
                        baseline = _resolved_parameters(original.contract.steps[index], original, online,
                                  RegisteredGroundingFrameInputsV2.from_payload(issue["inputs"]),
                                  RegisteredGroundingPolicyV2.from_payload(issue["policy"]))
                        expectation = rt.registered_expected_conditions_v2(original, issued, "POST")
                        started = time.monotonic()
                        shield = event.check_shield(frame, "PRE", contract, step, started, None)
                        entry = dict(skill=skill, step_id=step.step_id, fixture_only=True, dispatched=False,
                            pre={"frame_id": frame.frame_id}, selected=step.parameters.get("target_pose"),
                            central_recipe=baseline.get("target_pose"), native_binding_sha256=issued.digest(),
                            physical_pre_shield=shield["allowed"], pre_shield_unmodified=shield["unmodified"],
                            original_postconditions=rt.plain(expectation), feedback_accepted=0)
                        if mm == 0 and baseline != step.parameters:
                            raise AssertionError("center compatibility changed")
                        if skill in ("MOVE_ABOVE", "APPROACH", "LIFT", "MOVE_TO_REGION", "PLACE", "RETREAT"):
                            ref = capture(skill + "/servo_reference")
                            provider = b.BoundServoFeedback(initial_attempt, issued, ref, event.color, event.evidence,
                                                          marker_family_id=event.registration.marker_family_id)
                            previous = rt.MotionTarget(rt.Pose.model_validate(step.parameters["target_pose"]), _DOWNWARD)
                            def sample(prior):
                                start = time.perf_counter()
                                curr = capture(skill + "/feedback")
                                measured = provider.update(curr)
                                dynamic = step.model_copy(update={"parameters": {**step.parameters, "target_pose": measured.model_dump()}}, deep=True)
                                changed = contract.model_copy(update={"steps": [dynamic if st.step_id == step.step_id else st for st in contract.steps]}, deep=True)
                                feedback_shield = event.check_shield(curr, "FEEDBACK", changed, dynamic, started, None)
                                motion = provider.motion_target(prior, measured)
                                entry["feedback_shield_allowed"] = feedback_shield["allowed"]
                                entry["feedback_shield_unmodified"] = feedback_shield["unmodified"]
                                entry["capture_to_feedback_ms"] = 1000 * (time.perf_counter() - start)
                                return motion
                            session = rt.VisualServoSession(sample)
                            monitor = MuJoCoVisualServoController(backend)
                            # This read-only controller entry measures pose error even when the tool is far from the target.
                            # Its failure path calls hold_current_joints. Only run it for admitted PRE stages.
                            if skill in ("MOVE_ABOVE", "APPROACH") and shield["allowed"] and shield["unmodified"]:
                                monitor.monitor_hold(previous, session)
                                curr = provider.last_observation
                                pose = provider.records[-1]["target_pose"]
                                begin_ik = time.perf_counter()
                                ik = monitor.kinematics._inverse_kinematics(np.array([pose[k] for k in "xyz"]), np.array(_DOWNWARD), backend._model.site("tcp").id)
                                entry["read_only_ik_ms"] = 1000 * (time.perf_counter() - begin_ik)
                                entry["ik_solution"] = ik is not None
                                entry["sample_plus_ik_ms"] = entry["capture_to_feedback_ms"] + entry["read_only_ik_ms"]
                            else:
                                sample(previous)
                            if index == 0:
                                refused("in_flight_direction_change", lambda: provider.motion_target(rt.MotionTarget(previous.position,(1,0,0,0)), rt.Pose.model_validate(provider.records[-1]["target_pose"])))
                                refused("substituted_measured_endpoint", lambda: provider.motion_target(previous, rt.Pose(x=0.1,y=0.1,z=0.1)))
                            entry["feedback_accepted"] = len(provider.records)
                            control.append(dict(phase="servo", skill=skill, control_samples=rt.plain(session.records), visual_samples=rt.plain(provider.records)))
                        actions.append(entry)
                    observed = rt.plain(backend.command_records)
                    raw = dict(scope=LABEL, independent_zero_step_qualified_fixture=fixture["pose_xyzyaw"], frame_roles=roles, actions=actions,
                         negative_checks=checks, total_physics_steps=backend.total_physics_steps, native_operations=observed,
                         measured_state=state.model_dump(mode="json"), fixture_physical_sample=rt.plain(backend.current_physics_observation()),
                         fixture_original_sha256=original.digest(), generation=generation)
                    present = {command["command"] for command in observed}
                    b.require(not present - {"CAPTURE_SENSOR_FRAME"} and backend.total_physics_steps == 0, "zero-step fixture unexpectedly moved")
                    ok = True
            finally:
                event.backend.shutdown()
                closed = event.owner.close(ok)
                (private / "frames").mkdir()
                paths = {}
                for i, obs in enumerate(observations.values()):
                    path = private / "frames" / f"{i:04d}.json"
                    dump(path, obs.model_dump(mode="json"))
                    paths[obs.frame_id] = dict(file=str(path.relative_to(private)), sha256=sha(path))
                dump(private / "frame-index.json", paths)
                dump(private / "audit.json", rt.plain(event.audit + control))
                dump(private / "owner.json", rt.plain(closed))
                dump(private / "partial.json", dict(actions=actions, negative_checks=checks, raw_operations=rt.plain(observed), complete=ok))
            dump(private / "run.json", raw)
            records.append({k:sha(private / k) for k in ("frame-index.json","audit.json","owner.json","run.json","allocation.json","grasp-binding.sqlite","development-worker.db")})
    dump(folder / "read-input.json", records)


def blind_readback(folder):
    from scripts.graduation import g1_dual_pixel_readback as reader, g1_dual_batch_score as scoring
    from scripts.graduation import g1_formal_runtime, g1_visibility_trials as trials, binding_score as independent
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    result = []
    for mm, manifest in zip((0, 7), json.loads((folder / "read-input.json").read_text()), strict=True):
        base = folder / ("offset-" + str(mm))
        run = checked(base / "run.json", manifest["run.json"])
        alloc = checked(base / "allocation.json", manifest["allocation.json"])
        audit = checked(base / "audit.json", manifest["audit.json"])
        index = checked(base / "frame-index.json", manifest["frame-index.json"])
        frames, packets = {}, {}
        geo = alloc["geometry"]
        with g1_formal_runtime.bind_scene(alloc["case"]["scene_id"]):
            for role in run["frame_roles"]:
                fid = role["frame_id"]
                item = index[fid]
                f = RGBDObservation.model_validate(checked(base / item["file"], item["sha256"]))
                if f.frame_id != fid:
                    raise ValueError("readback frame identity differs")
                packets[fid] = f
                frames[fid] = dict(**reader.dual_read(f, geo), frame_id=fid, checksum_sha256=f.checksum_sha256, captured_at=f.captured_at.isoformat(),
                                  sim_time_s=f.sim_time_s, label=role["label"])
            scored = scoring.online_targets(run, audit, frames, geo, packets.__getitem__)
            issue_count = len(independent.verify_issues(audit, frames))
        contacts = scoring.contact_counts([run["fixture_physical_sample"]], set())
        operations = run["native_operations"]
        result.append(dict(offset_mm=mm, physical_steps=run["total_physics_steps"],
              motion_commands=sum(r["command"] != "CAPTURE_SENSOR_FRAME" for r in operations),
              capture_operations=len(operations), captures=len(packets), prepared_only=issue_count, raw_seals=manifest,
              native_score_readback=scored, scored_grasp_success=trials.training_success(dict(contacts=contacts)),
              negative_checks=run["negative_checks"], actions=run["actions"], scope=run["scope"]))
    return result


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("operation", choices=("prepare","acquire","read"))
    cli.add_argument("repo", type=Path)
    cli.add_argument("folder", type=Path)
    cli.add_argument("out", type=Path, nargs="?")
    args = cli.parse_args()
    if args.operation == "prepare":
        import binding_build
        args.folder.mkdir(parents=True, exist_ok=False)
        binding_build.create(args.repo, args.folder / "runtime-source")
    elif args.operation == "acquire":
        acquire_controls(args.repo, args.folder)
    else:
        dump(args.out, blind_readback(args.folder))


if __name__ == "__main__":
    main()
