"""Run one independent r593 episode with the original registration frame handoff."""

from __future__ import annotations

import argparse
import os
import shutil
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import mujoco
from scripts.graduation import dynamic_vision as r1
from scripts.graduation.perception_io import ROOT, check_sources, pinned, read, sha, write

from cloud_edge_robot_arm.edge.runtime.skill_executor import StepExecutionResult
from cloud_edge_robot_arm.research.native_collection_grounding import bootstrap_collection_tracker
from cloud_edge_robot_arm.vision.native_completion_horizon import (
    controller_window_error_v2,
    registered_teacher_horizon_v2,
)


def absolute_step(value):
    if type(value) is not int or value < 0:
        raise ValueError("nonnegative exact absolute physics step required")
    return value


def action_identity(contract, step):
    return (
        contract.task_id,
        contract.plan_version,
        contract.command_seq,
        step.step_id,
        step.skill.value,
    )


@dataclass
class ActionClock:
    identity: tuple
    episode: str
    binding: str
    source_id: str
    source_sha256: str
    origin: int
    dispatched: bool = False
    last_feedback: int | None = None
    returned: int | None = None

    def __post_init__(self):
        absolute_step(self.origin)

    def position(self, phase, now, identity, episode):
        now = absolute_step(now)
        if identity != self.identity or episode != self.episode or now < self.origin:
            raise ValueError("action origin identity or sequence mismatch")
        if phase == "PRE":
            if self.dispatched or now != self.origin:
                raise ValueError("PRE must precede dispatch at origin")
        elif phase == "FEEDBACK":
            if (
                not self.dispatched
                or self.returned is not None
                or (self.last_feedback is not None and now <= self.last_feedback)
            ):
                raise ValueError("feedback precedes dispatch or fails to advance")
            self.last_feedback = now
        elif phase == "POST":
            if not self.dispatched or self.returned is None or now < self.returned:
                raise ValueError("POST precedes controller return")
        else:
            raise ValueError("unknown action clock phase")
        return now - self.origin

    def dispatch(self, now, identity, episode, binding, source_id, source_sha256):
        self.position("PRE", now, identity, episode)
        if (binding, source_id, source_sha256) != (
            self.binding,
            self.source_id,
            self.source_sha256,
        ):
            raise ValueError("wrong dispatch binding or source")
        self.dispatched = True

    def returned_at(self, now, identity):
        now = absolute_step(now)
        if (
            identity != self.identity
            or not self.dispatched
            or self.returned is not None
            or (now < (self.last_feedback if self.last_feedback is not None else self.origin))
        ):
            raise ValueError("invalid controller return identity or clock")
        self.returned = now
        return now - self.origin


def command_evidence(rows, ep, origin, end, first_seq):
    previous = absolute_step(origin)
    absolute_step(end)
    result = []
    for expected, row in enumerate(rows, first_seq):
        required = {"type", "accepted", "reason", "command_seq", "episode_id", "physics_step"}
        if not required.issubset(row):
            raise ValueError("command record missing original fields")
        current = absolute_step(row["physics_step"])
        if (
            row["episode_id"] != ep
            or type(row["command_seq"]) is not int
            or row["command_seq"] != expected
            or not previous <= current <= end
            or type(row["accepted"]) is not bool
            or not isinstance(row["reason"], str)
            or not isinstance(row["type"], str)
            or not row["type"]
        ):
            raise ValueError("command record wrong episode, step, sequence or type")
        result.append({k: row[k] for k in sorted(required)})
        previous = current
    return result


class RecordedExecutor:
    def __init__(self, episode, executor):
        self.episode, self.executor = episode, executor

    def execute_attempt(self, *, contract, step, attempt):
        e = self.episode
        clock = e.action_clock
        frame = e.stage_source()
        e.active()
        if (
            e.pending_dispatch is None
            or e.pending_dispatch[0] is not frame
            or (not frame.captured_at <= datetime.now(UTC) < e.pending_dispatch[1])
        ):
            raise r1.ComponentStopped("expired or replaced source at executor dispatch")
        if attempt != 1 or e.action["dispatch_step"] != e.backend.total_physics_steps:
            raise ValueError("executor dispatch differs from live origin")
        clock.dispatch(
            e.backend.total_physics_steps,
            action_identity(contract, step),
            frame.episode_id,
            e.pending_binding,
            frame.frame_id,
            frame.checksum_sha256,
        )
        e.action["executor_entered"] = True
        before = len(e.backend.command_records)
        try:
            receipt = self.executor.execute_attempt(contract=contract, step=step, attempt=attempt)
        finally:
            writes = command_evidence(
                e.backend.command_records[before:],
                clock.episode,
                clock.origin,
                e.backend.total_physics_steps,
                before + 1,
            )
            e.audit.append(
                {
                    "phase": "actual_command_records",
                    "skill": step.skill.value,
                    "first_seq": before + 1,
                    "rows": writes,
                }
            )
            e.action["command_records"] = len(writes)
            e.action["accepted_command_types"] = dict(
                Counter(str(row["type"]) for row in writes if row["accepted"])
            )
            e.action["backend_return_step"] = e.backend.total_physics_steps
        if type(receipt) is not StepExecutionResult or (
            receipt.task_id,
            receipt.step_id,
            receipt.skill,
            receipt.attempt,
        ) != (contract.task_id, step.step_id, step.skill.value, attempt):
            raise ValueError("controller return identity differs from actual dispatch")
        elapsed = clock.returned_at(e.backend.total_physics_steps, action_identity(contract, step))
        details = receipt.action_result.details if receipt.action_result is not None else {}
        horizon = registered_teacher_horizon_v2(step.skill.value, step.timeout_ms)
        reason = controller_window_error_v2(horizon, elapsed, details)
        e.action["return_evidence"] = {
            "absolute_step": clock.returned,
            "elapsed_steps": elapsed,
            "action_result_present": receipt.action_result is not None,
            "success": receipt.success,
            "error_code": receipt.error_code,
            "original_window_error": reason,
            "controller_deadline_steps": horizon.controller_deadline_steps,
            "terminal_steps": horizon.terminal_steps,
            "hold_s": details.get("contact_hold_s"),
        }
        e.audit.append({"phase": "actual_executor_return", "receipt": r1.plain(receipt)})
        if receipt.success:
            if reason:
                raise r1.ComponentStopped("controller window: " + reason)
            tail = {"LIFT": 120, "RELEASE": 240}.get(step.skill.value, 0)
            if elapsed + tail > horizon.terminal_steps:
                raise r1.ComponentStopped("development dwell would exceed original terminal")
        return receipt


class GuardedClockEpisode(r1.Episode):
    """Retain the actual source frame across registered PRE, POST and the next PRE."""

    def __init__(self, *args):
        super().__init__(*args)
        self.current = None
        self.pending_dispatch = None
        self.feedback_started = None
        self.action_clock = None
        self.pending_binding = None
        self.executor = RecordedExecutor(self, self.executor)
        self.context_rows = []
        self.report["action_clock_contexts"] = self.context_rows
        self.roles = []
        self.report["frame_roles"] = self.roles
        self.report["grounding_contracts"] = []

    def record_role(self, label, frame, acquisition):
        step = self.backend.total_physics_steps
        self.roles.append(
            {
                "label": label,
                "physics_step": step,
                "frame_id": frame.frame_id,
                "checksum_sha256": frame.checksum_sha256,
                "episode_id": frame.episode_id,
                "sim_time_s": frame.sim_time_s,
                "captured_at": frame.captured_at.isoformat(),
                "acquired_for_this_role": acquisition,
                "checked_at": datetime.now(UTC).isoformat(),
            }
        )
        return frame

    def stage_source(self):
        if self.current is None:
            raise ValueError("stage entrance requires registration handoff")
        step, frame = self.current
        if (
            self.backend.total_physics_steps != step
            or frame.episode_id != self.original.identity.episode_id
        ):
            raise ValueError("stage entrance differs from retained terminal step/episode")
        return frame

    def capture(self, label):
        name, _, role = label.partition("/")
        if role == "PRE":
            return self.record_role(label, self.stage_source(), False)
        if role == "POST":
            now = self.backend.total_physics_steps
            last_step, last_role, last_frame = self.frames[-1]
            if self.current[0] == now:
                frame = self.stage_source()
                fresh = False
            elif last_step == now and last_role.startswith(name + "/dwell-"):
                frame = last_frame
                fresh = False
            else:
                frame = super().capture(label)
                fresh = True
            self.current = (now, frame)
            return self.record_role(label, frame, fresh)
        if role == "feedback":
            self.feedback_started = time.perf_counter()
        frame = super().capture(label)
        return self.record_role(label, frame, True)

    def bootstrap(self):
        super().bootstrap()
        step, label, handoff = self.frames[-1]
        if label != "registration-handoff" or step != self.backend.total_physics_steps:
            raise ValueError("missing original registered handoff")
        self.color, self.evidence = bootstrap_collection_tracker(handoff, self.geometry)
        self.current = (step, handoff)
        self.report["dispatch_reference"] = {
            "physics_step": step,
            "frame_id": handoff.frame_id,
            "checksum_sha256": handoff.checksum_sha256,
            "target_pixel": self.evidence["original_pixel_target"],
            "destination_pixel": self.evidence["original_pixel_destination"],
            "top_grasp_tcp_m": self.evidence["resolved_top_grasp_tcp"],
        }
        self.audit.append({"phase": "r2_original_contract", "original": self.original.to_payload()})
        self.record_role("color_reference", handoff, False)
        self.record_role("registered_reference", handoff, False)

    def admission(self, obs, phase, contract, step, binding, started, clearance):
        if obs is not self.stage_source():
            raise ValueError("ordinary conditions require the retained source frame")
        skill = step.skill.value
        self.record_role(skill + "/" + phase + "_conditions", obs, False)
        if phase == "PRE":
            if self.action_clock is not None:
                raise ValueError("cannot replace an open action clock")
            self.pending_binding = binding.digest()
            self.action_clock = ActionClock(
                action_identity(contract, step),
                obs.episode_id,
                self.pending_binding,
                obs.frame_id,
                obs.checksum_sha256,
                self.backend.total_physics_steps,
            )
            self.report["grounding_contracts"].append(
                {
                    "skill": skill,
                    "frame_id": obs.frame_id,
                    "checksum_sha256": obs.checksum_sha256,
                    "binding_sha256": binding.digest(),
                    "valid_until": binding.valid_until.isoformat(),
                }
            )
        if self.action_clock is None or self.action_clock.binding != binding.digest():
            raise ValueError("condition binding differs from the issued action")
        super().admission(obs, phase, contract, step, binding, started, clearance)
        if phase == "PRE":
            self.pending_dispatch = (obs, binding.valid_until)

    def active(self):
        lease = super().active()
        if (
            self.action_clock is not None
            and self.action_clock.returned is not None
            and self.phase == "CONTROLLER"
            and self.action["skill"] in {"LIFT", "RELEASE"}
        ):
            terminal = self.action["return_evidence"]["terminal_steps"]
            if self.backend.total_physics_steps + 8 > self.action_clock.origin + terminal:
                raise r1.ComponentStopped(
                    "next development dwell step would exceed original terminal"
                )
        if self.pending_dispatch and self.action and not self.action.get("dispatched"):
            frame, expiry = self.pending_dispatch
            if (
                frame is not self.stage_source()
                or not frame.captured_at <= datetime.now(UTC) < expiry
            ):
                raise r1.ComponentStopped("registered dispatch source changed or expired")
            self.record_role(self.action["skill"] + "/dispatch_source_recheck", frame, False)
        return lease

    def check_shield(self, obs, phase, contract, step, started, clearance):
        clock = self.action_clock
        if clock is None:
            raise ValueError("Shield requires a bound action clock")
        current = self.backend.total_physics_steps
        relative = clock.position(phase, current, action_identity(contract, step), obs.episode_id)
        self.context_rows.append(
            {
                "phase": phase,
                "skill": step.skill.value,
                "step_id": step.step_id,
                "task_id": contract.task_id,
                "plan_version": contract.plan_version,
                "command_seq": contract.command_seq,
                "episode": obs.episode_id,
                "binding_sha256": clock.binding,
                "origin": clock.origin,
                "absolute": current,
                "relative": relative,
                "frame_id": obs.frame_id,
                "checksum_sha256": obs.checksum_sha256,
            }
        )
        now = datetime.now(UTC)
        velocity = float(step.parameters.get("tcp_velocity", 0))
        context = self.shield.context_builder.build(
            contract=contract,
            step=step,
            robot_state=self.robot.get_state(),
            scene_version=contract.scene_version,
            resolved_parameters=dict(step.parameters),
            scene_updated_at=obs.captured_at,
            telemetry_timestamp=now,
            wall_clock_now=now,
            step_started_at_mono=started,
            task_started_at_mono=self.owner.begin,
            monotonic_now=time.monotonic(),
            physics_step=relative,
            requested_joint_velocities=[
                *map(abs, self.backend.get_joint_state().velocities),
                velocity / 0.3,
            ],
            requested_velocity=velocity,
            requested_acceleration=float(step.parameters.get("acceleration", 0)),
            vertical_clearance=clearance,
            expected_holding_object_id="object"
            if step.skill.value in {"LIFT", "MOVE_TO_REGION", "PLACE"}
            else None,
        )
        fn = self.shield.post_check if phase == "POST" else self.shield.pre_check
        verdict = fn(context)
        details = r1.plain(verdict)
        self.audit.append(
            {
                "phase": phase,
                "step_id": step.step_id,
                "frame_id": obs.frame_id,
                "target_pose": step.parameters.get("target_pose"),
                "shield": details,
            }
        )
        result = {
            "allowed": verdict.allowed,
            "unmodified": verdict.limited_parameters in (None, step.parameters),
            "result": details,
        }

        self.record_role(step.skill.value + "/" + phase + "_Shield", obs, False)
        if phase == "FEEDBACK" and self.feedback_started is not None:
            self.roles[-1]["elapsed_from_capture_start_s"] = (
                time.perf_counter() - self.feedback_started
            )
        return result

    def execute(self, index):
        self.pending_dispatch = None
        self.pending_binding = None
        self.action_clock = None
        return super().execute(index)


R1_ROUND = "round-graduation-dynamic-qualification-20261123"


def allocate(plan, raw, out):
    from OpenGL import GL

    if os.environ.get("MUJOCO_GL") != "egl" or shutil.disk_usage(raw).free < 2**30:
        raise ValueError("preallocated EGL/free space unavailable")
    if (raw / "instance").exists() or out.exists():
        raise ValueError("r2 allocation already taken")
    previous = plan.parent.parent / R1_ROUND / "allocation-vision.public.json"
    old = pinned(previous, "2db14d49d4fb6715828511d511c82c6153a320a920a233a1d4654ede31ea2cd8")
    frozen = read(plan)
    supplement = plan.parent.parent / "round-graduation-guarded-physics-context-20261123"
    preflight_plan = plan.parent.parent / "round-graduation-guarded-preflight-repair-20261123"
    specific = frozen["allocation"]
    case = {
        **specific,
        "visual_seed": specific["seed"],
        "visual_stages_in_order": old["case"]["visual_stages_in_order"],
    }
    context = mujoco.GLContext(320, 240)
    try:
        context.make_current()
        renderer = GL.glGetString(GL.GL_RENDERER).decode()
    finally:
        context.free()
    catalog = r1.inventory()
    archive = r1.bind_catalog(raw, catalog, old["geometry"]["asset_path"])
    if (
        archive["product_compact_sorted_utf8_sha256"]
        != old["catalog"]["product_compact_sorted_utf8_sha256"]
    ):
        raise ValueError("frozen component source generation changed")
    names = [
        *old["sources_sha256"],
        "scripts/graduation/guarded_clock.py",
        "scripts/graduation/guarded_clock_score.py",
        "tests/test_graduation_guarded_clock.py",
    ]
    if (
        case["visual_id"] == old["case"]["visual_id"]
        or case["visual_seed"] == old["case"]["visual_seed"]
    ):
        raise ValueError("r2 requires a distinct release and seed")
    write(
        out,
        {
            "schema": "graduation.guarded-clock-r2.allocation.v1",
            "issued_at": datetime.now(UTC).isoformat(),
            "plan_sha256": sha(plan),
            "preflight_repair_plan_sha256": sha(preflight_plan / "plan.json"),
            "preflight_repair_plan_md_sha256": sha(preflight_plan / "plan.md"),
            "previous_preflight_source_sha256": sha(
                raw / "before-receipt-adapter-fix/snapshot.json"
            ),
            "physics_context_plan_sha256": sha(supplement / "plan.json"),
            "physics_context_plan_md_sha256": sha(supplement / "plan.md"),
            "old_adapter_snapshot_sha256": sha(raw / "before-physics-context/snapshot.json"),
            "missing_context_fixture_sha256": sha(raw / "shield-preflight-failure.json"),
            "plan_md_sha256": sha(plan.with_name("plan.md")),
            "baseline": frozen["baseline"],
            "archive_parent": frozen["archive_parent"],
            "r1_allocation_sha256": sha(previous),
            "case": case,
            "sources_sha256": {n: sha(ROOT / n) for n in names},
            "geometry": old["geometry"],
            "asset_sha256": old["asset_sha256"],
            "catalog": archive,
            "source_archival_checks_sha256": sha(raw / "archive-check.json"),
            "component_catalog_sha256": r1.digest(catalog),
            "intent_descriptor": old["intent_descriptor"],
            "expected_red_sha256": sha(raw / "expected-old-schedule-red.log"),
            "software_receipt_sha256": sha(raw / "software-receipt.json"),
            "selected_entry": old["selected_entry"],
            "runtime": {
                **old["runtime"],
                "free_bytes": shutil.disk_usage(raw).free,
                "egl_renderer": renderer,
            },
            "clock_preflight": old["clock_preflight"],
            "capture_grid": {
                **old["capture_grid"],
                "explicit_frames": (
                    "Reset, bootstrap and a separate handoff. Reuse stage source for PRE. "
                    "Fresh servo reference and feedback on original deadlines. Eight-step dwell "
                    "cadence. One terminal stage source for POST and the following PRE."
                ),
                "ordinary_clock": "New frame IDs require advancing UTC and simulation time",
                "servo_clock": "First feedback may share reference step, later samples advance",
            },
            "private_root": raw.name,
            "issued_instances": 1,
            "ingested_r1_frames": 0,
            "development_retries": 0,
            "model_calls": 0,
            "hardware_actions": 0,
            "native_claims": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("allocate")
    new.add_argument("plan", type=Path)
    new.add_argument("raw", type=Path)
    new.add_argument("output", type=Path)
    run = sub.add_parser("run")
    run.add_argument("allocation", type=Path)
    run.add_argument("sha256")
    run.add_argument("raw", type=Path)
    a = parser.parse_args()
    if a.command == "allocate":
        allocate(a.plan, a.raw, a.output)
        return
    alloc = pinned(a.allocation, a.sha256)
    check_sources(alloc)
    catalog = r1.inventory()
    archived = pinned(
        a.raw / alloc["catalog"]["private_filename"], alloc["catalog"]["archived_json_sha256"]
    )
    if catalog != archived or os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError("catalog or EGL mismatch")
    destination = a.raw / "instance"
    destination.mkdir()
    GuardedClockEpisode(destination, alloc, a.sha256, catalog).run()


if __name__ == "__main__":
    main()
