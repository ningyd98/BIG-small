"""Fixed versus bounded two-view feedback on newly allocated development placements."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation import dynamic_vision as runtime
from scripts.graduation import proposal_translated as translated
from scripts.graduation import proposal_translated_cases as prior
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write
from scripts.graduation.proposal_terminal_visibility import VIEWS, slots

from cloud_edge_robot_arm.research.sol_molmo_components import _check_component_camera_sample
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.servo import RECOVERABLE_CAMERA_VIEW_ERRORS

RELEASE = "proposal-terminal-switch-development-20261124"
SCOPE = {"MOVE_ABOVE", "APPROACH"}
SOURCE = "scripts/graduation/proposal_terminal_visibility_switch.py"
SCORER = "scripts/graduation/proposal_terminal_visibility_score.py"


def other_view(view):
    if view not in VIEWS:
        raise ValueError("unknown registered view")
    return next(x for x in VIEWS if x != view)


def view_spec(view):
    pos = translated.POSITION[view]
    return pos, (pos[0], pos[1], 0.04)


def move(backend, view, step, sim, cursor):
    _check_component_camera_sample(backend, step, sim, cursor)
    position, aim = view_spec(view)
    backend.set_camera_position(position, look_at_m=aim)
    return _check_component_camera_sample(backend, step, sim, cursor, camera_move=(position, aim))


def check_attempts(frames, step, sim, registers):
    if not 1 <= len(frames) <= 2:
        raise ValueError("only one alternate capture is registered")
    main = frames[0][0]
    ids = set()
    last = None
    episode = frames[0][2].episode_id
    for i, (view, read_step, f) in enumerate(frames):
        expected = main if i == 0 else other_view(main)
        if (
            read_step != step
            or f.sim_time_s != sim
            or f.episode_id != episode
            or view != expected
            or f.frame_id in ids
            or last is not None
            and f.captured_at <= last
        ):
            raise ValueError("foreign or duplicate camera, step, time, or frame")
        runtime.validate_camera(f, registers[view])
        ids.add(f.frame_id)
        last = f.captured_at


def deadline(start):
    elapsed = time.perf_counter() - start
    if elapsed > 0.1:
        raise ValueError("bounded camera sample exceeded original 100 ms")
    return elapsed


def preflight(raw, observations, observed_sha):
    visible = pinned(observations, observed_sha)
    a = pinned(raw / "observation-allocation.json", visible["allocation_sha256"])
    dest = raw / "switch-preflight"
    dest.mkdir()
    registers = a["geometry"]
    probes = {}
    if visible["physical_visibility_prerequisite"]:
        backend = MuJoCoPhysicsBackend()
        catalog = runtime.inventory()
        try:
            backend.initialize(translated.config({"geometry": registers["nominal"]}, 24112700))
            backend.reset(
                runtime.PhysicalScenarioConfig(
                    scenario_id="TERMINAL_TWO_REGISTERED_VERTICAL",
                    seed=24112700,
                    object_pose=runtime.Pose(x=0.45, y=0, z=0.035),
                    object_yaw_rad=0.0,
                )
            )

            def acquire(view):
                f = runtime.observation_from_sensor_frame(
                    backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
                )
                runtime.validate_camera(f, registers[view])
                return f

            for view in VIEWS:
                step = backend.total_physics_steps
                sim = backend.get_sim_time()
                cursor = move(backend, view, step, sim, len(backend._command_records))
                initial = acquire(view)
                fpath = dest / (view + "-binding.json")
                write(fpath, initial.model_dump(mode="json"))
                try:
                    runtime.bootstrap_registered_collection_tracker_v2(
                        initial,
                        NativeGeometryRegistration(registers[view]),
                        source_root=ROOT,
                        source_hashes=catalog,
                        nominal_policy=runtime.registered_nominal_region_policy_v1(catalog),
                    )
                    bound = True
                    reason = None
                except ValueError as exc:
                    bound = False
                    reason = str(exc)
                start = time.perf_counter()
                frames = [(view, step, acquire(view))]
                other = other_view(view)
                cursor = move(backend, other, step, sim, cursor)
                frames.append((other, step, acquire(other)))
                check_attempts(frames, step, sim, registers)
                cursor = move(backend, view, step, sim, cursor)
                _check_component_camera_sample(backend, step, sim, cursor)
                dt = time.perf_counter() - start
                files = []
                for i, (_, _, f) in enumerate(frames):
                    fp = dest / f"{view}-roundtrip-{i}.json"
                    write(fp, f.model_dump(mode="json"))
                    files.append(sha(fp))
                probes[view] = {
                    "registered": bound,
                    "reason": reason,
                    "neutral_step": step,
                    "sim_time_s": sim,
                    "binding_sha256": sha(fpath),
                    "roundtrip_frame_sha256": files,
                    "elapsed_s": dt,
                    "two_fresh_views_and_return_within_100ms": dt <= 0.1,
                    "cursor": cursor,
                }
            write(dest / "commands.json", backend.command_records)
        finally:
            backend.shutdown()
    ok = (
        visible["physical_visibility_prerequisite"]
        and all(
            v["registered"] and v["two_fresh_views_and_return_within_100ms"]
            for v in probes.values()
        )
        and set(probes) == set(VIEWS)
    )
    result = {
        "schema": "proposal.visibility.switch-preflight.v1",
        "observation_sha256": observed_sha,
        "eligible": ok,
        "probes": probes,
        "eligible_original_trajectories": visible["complementary_original_trajectories"],
        "new_development_slots": slots(),
        "real_motion_at_preflight": 0,
        "formal_claims": 0,
    }
    write(dest / "preflight.json", result)
    return result


def issue(raw, obs, oh, output):
    result = preflight(raw, obs, oh)
    if not result["eligible"]:
        write(
            output,
            {**result, "cases": [{**r, "status": "NOT_RUN_QUALIFICATION_FAILED"} for r in slots()]},
        )
        return
    vis = pinned(obs, oh)
    a = pinned(raw / "observation-allocation.json", vis["allocation_sha256"])
    original = ROOT / a["episodes"]
    previous = pinned(original / "allocation.json", a["master_sha256"])
    t = previous["cases"][0]
    template = pinned(original / t["allocation_file"], t["allocation_sha256"])
    sources = {
        **template["sources_sha256"],
        **a["sources_sha256"],
        SOURCE: sha(ROOT / SOURCE),
        SCORER: sha(ROOT / SCORER),
    }
    check_sources({"sources_sha256": sources})
    if shutil.disk_usage(raw).free < 4 * 2**31:
        raise ValueError("insufficient evidence storage")
    root = raw / "episodes"
    root.mkdir()
    catalog = runtime.inventory()
    arc = runtime.bind_catalog(root, catalog, template["geometry"]["asset_path"])
    if runtime.digest(catalog) != template["component_catalog_sha256"]:
        raise ValueError("product source generation changed")
    cases = []
    issued = datetime.now(UTC).isoformat()
    for row in slots():
        base = root / row["id"]
        base.mkdir()
        case = {
            **template["case"],
            **row,
            "visual_id": RELEASE + "/" + row["id"],
            "visual_seed": row["seed"],
            "release": RELEASE,
            "private_output": row["id"] + "/instance",
        }
        alloc = {
            **template,
            "schema": "proposal.terminal-switch.case.v1",
            "case": case,
            "geometry": a["geometry"][row["view"]],
            "registered_views": a["geometry"],
            "sources_sha256": sources,
            "catalog": arc,
            "issued_at": issued,
            "plan_sha256": a["plan_sha256"],
            "preflight_probes_sha256": sha(raw / "switch-preflight/preflight.json"),
            "origin_template_sha256": t["allocation_sha256"],
            "selection_sha256": oh,
        }
        f = base / "allocation.json"
        write(f, alloc)
        cases.append(
            {**row, "allocation_sha256": sha(f), "allocation_file": row["id"] + "/allocation.json"}
        )
    manifest = {
        "schema": "proposal.terminal-switch.batch.v1",
        "release": RELEASE,
        "issued_at": issued,
        "eligible": True,
        "sources_sha256": sources,
        "observation_result_sha256": oh,
        "plan_sha256": a["plan_sha256"],
        "registered_views": a["geometry"],
        "source_catalog": arc,
        "real_probe": result["probes"],
        "preflight_sha256": sha(raw / "switch-preflight/preflight.json"),
        "cases": cases,
        "formal_claims": 0,
        "model_calls": 0,
        "hardware_actions": 0,
        "extra_views_per_sample": 1,
        "task_retries": 0,
    }
    write(root / "allocation.json", manifest)
    write(output, manifest)


def master(raw, p, h):
    m = pinned(p, h)
    if (
        sha(raw / "episodes/allocation.json") != h
        or m["release"] != RELEASE
        or m["eligible"] is not True
    ):
        raise ValueError("foreign or ineligible batch")
    if any(
        any(r[k] != v for k, v in ref.items())
        or r["allocation_file"] != r["id"] + "/allocation.json"
        for r, ref in zip(m["cases"], slots(), strict=True)
    ):
        raise ValueError("case allocation mismatch")
    check_sources(m)
    return m


class BoundedEpisode(prior.TranslatedEpisode):
    def camera_feedback(self, provider, contract, step, started, previous):
        self.active()
        before = time.perf_counter()
        self.feedback_started = before
        home = self.case["view"]
        alternate = other_view(home)
        registers = self.alloc["registered_views"]
        now = self.backend.total_physics_steps
        sim = self.backend.get_sim_time()
        cursor = len(self.backend._command_records)
        initial_cursor = cursor
        frames = []
        at = home
        reason = None
        accepted = None

        def acquire(attempt):
            if attempt != len(frames) or attempt > 1:
                raise ValueError("exceeded registered extra view")
            _check_component_camera_sample(self.backend, now, sim, cursor)
            label = step.skill.value + ("/feedback" if attempt == 0 else "/feedback_reobserve")
            obs = runtime.observation_from_sensor_frame(
                self.backend.capture_sensor_frame(), source="mujoco_camera", png_compress_level=1
            )
            self.frames.append((now, label, obs))
            self.record_role(label, obs, True)
            frames.append((at, self.backend.total_physics_steps, obs))
            check_attempts(frames, now, sim, registers)
            deadline(before)
            return obs

        def change(pos, aim, why):
            nonlocal cursor, at, reason
            if (
                reason is not None
                or at != home
                or (tuple(pos), tuple(aim)) != view_spec(alternate)
                or why not in RECOVERABLE_CAMERA_VIEW_ERRORS
            ):
                raise ValueError("unregistered switch reason, pose or count")
            cursor = move(self.backend, alternate, now, sim, cursor)
            at = alternate
            reason = why

        error = None
        try:
            measured = provider.update_with_camera_views(
                acquire, change, [view_spec(alternate)], allow_marker_depth_reobserve=False
            )
            accepted = provider.last_observation
            if (
                accepted is not frames[-1][2]
                and accepted.checksum_sha256 != frames[-1][2].checksum_sha256
            ):
                raise ValueError("servo accepted a different observation")
            dynamic = step.model_copy(
                update={"parameters": {**step.parameters, "target_pose": measured.model_dump()}},
                deep=True,
            )
            updated = contract.model_copy(
                update={
                    "steps": [dynamic if s.step_id == step.step_id else s for s in contract.steps]
                },
                deep=True,
            )
            verdict = self.check_shield(accepted, "FEEDBACK", updated, dynamic, started, None)
            if not verdict["allowed"] or not verdict["unmodified"]:
                raise runtime.ComponentStopped("dynamic research Shield rejected or limited")
            self.active()
            return runtime.MotionTarget(measured, previous.orientation_wxyz)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if at != home:
                cursor = move(self.backend, home, now, sim, cursor)
            _check_component_camera_sample(self.backend, now, sim, cursor)
            elapsed = time.perf_counter() - before
            self.audit.append(
                {
                    "phase": "bounded_camera_sample",
                    "skill": step.skill.value,
                    "step": now,
                    "sim_time_s": sim,
                    "reason": reason,
                    "accepted_frame_id": accepted.frame_id if accepted is not None else None,
                    "views": [v for v, _, _ in frames],
                    "frame_ids": [f.frame_id for _, _, f in frames],
                    "checksums": [f.checksum_sha256 for _, _, f in frames],
                    "first_cursor": initial_cursor,
                    "end_cursor": cursor,
                    "elapsed_s": elapsed,
                    "error": error,
                    "timely": elapsed <= 0.1,
                    "returned_to_starting_view": True,
                }
            )
            deadline(before)

    def execute(self, index):
        action = self.report["actions"][index]
        name = action["skill"]
        if self.case["method"] != "bounded" or name not in SCOPE:
            return super().execute(index)
        self.pending_dispatch = None
        self.pending_binding = None
        self.action_clock = None
        self.action = action
        started = time.monotonic()
        action.update(
            status="ENTERED", entered_step=self.backend.total_physics_steps, dispatched=False
        )
        self.phase = "GROUNDING"
        current = self.capture(name + "/PRE")
        contract, step, binding, _, _ = runtime.registered_collection_step_v2(
            self.original,
            index=index,
            observation=current,
            state=self.robot.get_state(),
            tracker=self.registered,
            lease_source=self.active(),
            evidence_sink=self.audit.append,
        )
        target = step.parameters.get("target_pose")
        if index == 0:
            self.report["candidate"] = {
                "skill": name,
                "frame_id": current.frame_id,
                "checksum_sha256": current.checksum_sha256,
                "target_pose_m": target,
                "binding_sha256": binding.digest(),
            }
        self.phase = "PRE"
        self.admission(current, "PRE", contract, step, binding, started, None)
        self.phase = "SERVO_REFERENCE"
        reference = self.capture(name + "/servo_reference")
        provider = runtime.OpenCVServoFeedback(
            reference,
            self.color,
            self.evidence,
            skill=name,
            initial_target=runtime.Pose.model_validate(target),
            marker_family_id=runtime.SIDE_PREPARE_ONLY_FAMILY,
            verify_mujoco_calibration=True,
        )

        def sample(previous):
            return self.camera_feedback(provider, contract, step, started, previous)

        session = runtime.VisualServoSession(sample, vertical_clearance=None)
        self.active()
        self.phase = "CONTROLLER"
        action["dispatched"] = True
        action["dispatch_step"] = self.backend.total_physics_steps
        try:
            with self.robot.visual_servo(session):
                outcome = self.executor.execute_attempt(contract=contract, step=step, attempt=1)
        finally:
            action["feedback_accepted"] = len(provider.records)
            action["servo_terminal_reason"] = session.terminal_reason
            self.audit.append(
                {
                    "phase": "servo",
                    "skill": name,
                    "control_samples": runtime.plain(session.records),
                    "visual_samples": runtime.plain(provider.records),
                }
            )
        action["controller_return_step"] = self.backend.total_physics_steps
        action["controller_result"] = {
            "success": outcome.success,
            "code": outcome.error_code,
            "details": runtime.plain(outcome.error),
        }
        self.audit.append({"phase": "controller", "receipt": runtime.plain(outcome)})
        if not outcome.success:
            raise runtime.ComponentStopped("controller: " + str(outcome.error_code))
        self.phase = "POST"
        post = self.capture(name + "/POST")
        self.admission(post, "POST", contract, step, binding, started, None)
        action.update(status="PASS", end_step=self.backend.total_physics_steps)


def capture(raw, file, h, id_):
    b = master(raw, file, h)
    dest = raw / "episodes"
    row = next(r for r in b["cases"] if r["id"] == id_)
    a = pinned(dest / row["allocation_file"], row["allocation_sha256"])
    if (
        any(a["case"][k] != v for k, v in slots()[[x["id"] for x in slots()].index(id_)].items())
        or a["case"]["visual_seed"] != row["seed"]
        or a["case"]["visual_id"] != RELEASE + "/" + id_
        or a["registered_views"] != b["registered_views"]
        or a["geometry"] != b["registered_views"][row["view"]]
    ):
        raise ValueError("wrong assigned camera or pose")
    catalog = runtime.inventory()
    archive = b["source_catalog"]
    if catalog != pinned(dest / archive["private_filename"], archive["archived_json_sha256"]):
        raise ValueError("foreign registry")
    directory = dest / id_ / "instance"
    directory.mkdir()
    write(
        directory / "started.json",
        {
            "case": id_,
            "batch_sha256": h,
            "allocation_sha256": row["allocation_sha256"],
            "utc": datetime.now(UTC).isoformat(),
            "attempt": 1,
            "argv": sys.argv,
        },
    )
    episode = BoundedEpisode(directory, a, row["allocation_sha256"], catalog)
    try:
        episode.run()
    except BaseException as exc:
        write(directory / "interrupted.json", {"type": type(exc).__name__, "reason": str(exc)})
        raise
    finally:
        episode.backend.shutdown()
    cap = read(directory / "acquisition-seal.json")
    idx = pinned(directory / "pixel-index.json", cap["index_sha256"])
    reset = prior.readback_reset(row, read(directory / "reset-observed.json"))
    if (
        reset["episode_id"] != idx["episode"]
        or idx["allocation_sha256"] != row["allocation_sha256"]
    ):
        raise ValueError("actual reset or batch mismatch")
    write(
        directory / "receipt.json",
        {
            "reset": reset,
            "case": id_,
            "acquisition_sha256": sha(directory / "acquisition-seal.json"),
            "started_sha256": sha(directory / "started.json"),
            "reset_sha256": sha(directory / "reset-observed.json"),
            "camera_setup_sha256": sha(directory / "camera-setup.json"),
            "batch_sha256": h,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("issue")
    for n in ("raw", "observations", "digest", "output"):
        p.add_argument(n, type=str if n == "digest" else Path)
    p = sub.add_parser("capture")
    for n in ("raw", "allocation", "digest", "case"):
        p.add_argument(n, type=Path if n in ("raw", "allocation") else str)
    a = parser.parse_args()
    if a.cmd == "issue":
        issue(a.raw, a.observations, a.digest, a.output)
    else:
        capture(a.raw, a.allocation, a.digest, a.case)


if __name__ == "__main__":
    main()
