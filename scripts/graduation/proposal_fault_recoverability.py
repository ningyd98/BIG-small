"""Preallocate and measure four offline T5 fault cases on one excluded development scene."""

from __future__ import annotations

import argparse
import fcntl
import math
import os
import shutil
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.graduation.perception_io import ROOT, pinned, read, sha, write
from scripts.graduation.proposal_fault_recoverability_score import (
    audit,
    count_cases,
    require,
)

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec
from cloud_edge_robot_arm.datasets.rgbd.teacher import EpisodeRecorder, run_teacher_episode
from cloud_edge_robot_arm.research.protocol_evidence import RECOVERY_FILES, write_recovery_source
from cloud_edge_robot_arm.research.protocol_generation import (
    GenerationBudget,
    StepSpool,
    wall_deadline,
)
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation.models import PhysicalFault, PhysicalFaultType
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

BASE = Path("artifacts/research/process/20261004-ced-development")
DEV = BASE / "t8-real-raw-development"
OLD = BASE / "astra-repair-execution/R07/producer"
ARCHIVE = OLD / "raw/recovery-0001/attempt-1"
DEV_RULES = DEV / "verified-development/evidence-rules.json"
SCRIPTS = (
    "scripts/graduation/proposal_fault_recoverability.py",
    "scripts/graduation/proposal_fault_recoverability_score.py",
)
CASES = ((1, "NORMAL"), (1, "NO_CONTACT"), (-1, "NO_CONTACT"), (-1, "NORMAL"))


def allocate_cases(cases):
    require(
        [(c["direction"], c["teacher_case"]) for c in cases] == list(CASES),
        "wrong or incomplete case registration",
    )
    return [
        {**c, "ordinal": i, "id": f"proposal-dev-fault-20261124-{i:02d}"}
        for i, c in enumerate(cases, 1)
    ]


def allocate(plan_path, plan_sha, out, raw):
    import mujoco
    from OpenGL import GL

    plan = pinned(plan_path, plan_sha)
    for path, digest in plan["input_sha256"].items():
        require(sha(ROOT / path) == digest, f"frozen input changed: {path}")
    plan_root = plan_path.parent
    require(sha(plan_root / "plan.md") == plan["plan_md_sha256"], "plan text hash mismatch")
    dev = read(ROOT / DEV / "assignment.json")
    original = read(ROOT / ARCHIVE / "execution-plan.json")
    rules_name = OLD / "protocol-final/recipe.json"
    rules = pinned(ROOT / rules_name, original["payload_hashes"]["recipe.json"])
    require(rules == read(ROOT / DEV_RULES), "recovery rules changed across archive inputs")
    require(
        shutil.disk_usage(raw).free
        >= original["budgets"]["min_free_bytes"] + 4 * original["budgets"]["retained_bytes"],
        "free space below reserve",
    )
    require(os.environ.get("MUJOCO_GL") == "egl", "EGL required for actual capture")
    gl_context = mujoco.GLContext(320, 240)
    try:
        gl_context.make_current()
        renderer = GL.glGetString(GL.GL_RENDERER).decode()
    finally:
        gl_context.free()
    write(
        out,
        {
            "schema": "graduation.proposal-fault-development.allocation.v1",
            "created_utc": datetime.now(UTC).isoformat(),
            "plan_sha256": plan_sha,
            "baseline": plan["baseline"],
            "frozen_inputs": plan["input_sha256"],
            "implementation_sha256": {n: sha(ROOT / n) for n in SCRIPTS},
            "cases": allocate_cases(plan["cases"]),
            "source_assignment": dev,
            "config": original["config"],
            "budgets": original["budgets"],
            "settle_steps": original["settle_steps"],
            "original_fault": original["fault"],
            "rules_path": str(rules_name),
            "recipe_sha256": original["payload_hashes"]["recipe.json"],
            "independent_development_scenes": 1,
            "formal_claims": 0,
            "renderer": renderer,
            "mujoco": mujoco.__version__,
            "raw_root_name": raw.name,
            "suite_root_name": raw.parent.name,
            "case_execution": "Fresh reset per case in the listed order",
            "eligibility_scope": "T5 offline teacher following a measured injected defect",
        },
    )


def history(alloc, alloc_sha, out):
    dev_result = read(ROOT / DEV / "verified-development-assessment.json")
    old_result = read(ROOT / ARCHIVE / "result.json")
    old_plan = read(ROOT / ARCHIVE / "execution-plan.json")
    dev_rules = pinned(ROOT / DEV_RULES, alloc["frozen_inputs"][str(DEV_RULES)])
    rules = pinned(ROOT / alloc["rules_path"], alloc["recipe_sha256"])
    rows = []
    for tag, bundle, row, recipe in (
        ("excluded_development", ROOT / DEV / "attempt-1", alloc["source_assignment"], dev_rules),
        ("r07_locked_recovery_pool", ROOT / ARCHIVE / "source", old_plan["row"], rules),
    ):
        for name in RECOVERY_FILES:
            key = str((bundle / name).relative_to(ROOT))
            require(sha(bundle / name) == alloc["frozen_inputs"][key], "archived source differs")
        results = audit(bundle, row, old_plan["fault"], recipe)
        rows.append({"scope": tag, **results})
    write(
        out,
        {
            "schema": "graduation.proposal-fault-history.v1",
            "allocation_sha256": alloc_sha,
            "groups": rows,
            "original_development_proven": dev_result["independent_reaudit"]["recovery_proven"],
            "original_r07_status": old_result["status"],
            "original_r07_attempted": old_result["attempted"],
            "original_r07_unattempted": old_result["unattempted"],
            "original_r07_denominator": old_result["denominator"],
            "formal_online_g4_measured": False,
        },
    )


def run_capture(alloc, case, root):
    from cloud_edge_robot_arm.datasets.rgbd.models import TrajectoryFrame

    scene = SceneSpec.model_validate(alloc["source_assignment"]["scene"])
    budget = GenerationBudget(alloc["budgets"], root)
    journal = StepSpool(root / "step-journal.jsonl")
    states, controls, actions = [], [], []
    recorder = EpisodeRecorder()
    backend = None
    start = None
    errors = []
    began = time.monotonic()

    def record(snapshot):
        if states and states[-1].physics_step == snapshot.physics_step:
            require(states[-1] == snapshot, "same-step snapshot changed")
            return
        states.append(snapshot)
        journal.append("PHYSICS", asdict(snapshot))
        budget.check(snapshot.sim_time_s, 16384 * (len(states) + len(controls)))

    def pre(snapshot):
        controls.append(snapshot)
        journal.append("ACTUATOR_PRE", asdict(snapshot))
        budget.check(snapshot.sim_time_s, 16384 * (len(states) + len(controls)))

    fault = case_fault(alloc, case)
    commands, events = [], []
    try:
        budget.check(0.0, 0)
        with (
            wall_deadline(alloc["budgets"]["wall_s"]),
            MuJoCoCaptureSession(SimulatorConfig(**alloc["config"])) as capture,
        ):
            capture.apply_scene(scene)
            backend = capture._backend
            record(backend.current_physics_observation())
            try:
                with backend.observe_actuator_steps(pre):
                    with backend.observe_physics_steps(record):
                        backend.step(steps=alloc["settle_steps"])
                        budget.fault_start_s = backend.get_sim_time()
                        backend.inject_fault(
                            PhysicalFault(PhysicalFaultType.TARGET_MOTION, fault["parameters"])
                        )
                        cap = (
                            math.ceil(
                                fault["parameters"]["duration_s"] / alloc["config"]["physics_dt_s"]
                            )
                            + 1
                        )
                        for _ in range(cap):
                            if any(
                                v["event"] == "TARGET_MOTION_FINISHED"
                                for v in backend.fault_records
                            ):
                                break
                            backend.step(steps=1)
                        require(
                            any(
                                v["event"] == "TARGET_MOTION_FINISHED"
                                for v in backend.fault_records
                            ),
                            "actual fault failed to finish",
                        )
                    start = backend.total_physics_steps
                    run_teacher_episode(
                        scene,
                        MuJoCoSkillRobot(backend),
                        recorder,
                        case=case["teacher_case"],
                        settle_steps=0,
                        physical_observer=record,
                        action_observer=lambda row: actions.append(dict(row)),
                    )
            finally:
                commands, events = backend.command_records, backend.fault_records
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        journal.close()
    write(
        root / "teacher-frames.json", [frame.model_dump(mode="json") for frame in recorder.frames]
    )
    write(
        root / "unframed-actions.json",
        [action.model_dump(mode="json") for action in recorder.unframed_actions],
    )
    write(root / "action-events.json", actions)
    write(root / "backend-commands.json", commands)
    write(root / "fault-events.json", events)
    require(
        all(isinstance(frame, TrajectoryFrame) for frame in recorder.frames),
        "wrong teacher frame type",
    )
    if states and controls and start is not None:
        try:
            write_recovery_source(
                row=alloc["source_assignment"],
                observations=states,
                action_events=actions,
                backend_commands=commands,
                actuator_steps=controls,
                fault_events=events,
                recovery_start_step=start,
                output=root / "source",
            )
        except Exception as exc:
            errors.append(f"source writer {type(exc).__name__}: {exc}")
    write(
        root / "terminal.json",
        {
            "case": case,
            "fault": fault,
            "errors": errors,
            "actual_wall_s": time.monotonic() - began,
            "frames": len(recorder.frames),
            "unframed": len(recorder.unframed_actions),
            "states": len(states),
            "actuators": len(controls),
            "episode": states[0].episode_id if states else None,
            "teacher_independent_outcome": asdict(recorder.outcome) if recorder.outcome else None,
        },
    )


def case_fault(alloc, case):
    return {
        "fault_type": alloc["original_fault"]["fault_type"],
        "parameters": {
            **alloc["original_fault"]["parameters"],
            "direction_y": float(case["direction"]),
        },
    }


def capture(alloc, alloc_sha, ordinal, raw):
    require(
        raw.name == alloc["raw_root_name"] and raw.parent.name == alloc["suite_root_name"],
        "wrong private root",
    )
    require(os.environ.get("MUJOCO_GL") == "egl", "live capture needs EGL")
    require(1 <= ordinal <= len(alloc["cases"]), "unallocated ordinal")
    case = alloc["cases"][ordinal - 1]
    root = raw / case["id"]
    prior = alloc["cases"][: ordinal - 1]
    require(
        all((raw / c["id"] / "seal.json").is_file() for c in prior),
        "earlier allocated case pending",
    )
    # Share the actual GPU/EGL turn with the other two registered experiments.
    with (raw.parent / "active-egl.lock").open("a") as render_lock:
        fcntl.flock(render_lock.fileno(), fcntl.LOCK_EX)
        root.mkdir()
        write(
            root / "begin.json",
            {
                "case": case,
                "allocation_sha256": alloc_sha,
                "started_utc": datetime.now(UTC).isoformat(),
                "argv": sys.argv[1:],
            },
        )
        run_capture(alloc, case, root)
    files = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob("*")) if p.is_file()}
    size = sum((root / n).stat().st_size for n in files)
    write(
        root / "seal.json",
        {
            "allocation_sha256": alloc_sha,
            "case": case,
            "files": files,
            "bytes": size,
            "retained_budget_met": size <= alloc["budgets"]["retained_bytes"],
        },
    )


def score(alloc, alloc_sha, raw, out):
    rules = pinned(ROOT / alloc["rules_path"], alloc["recipe_sha256"])
    rows = []
    for case in alloc["cases"]:
        root = raw / case["id"]
        seal = read(root / "seal.json")
        require(
            seal["allocation_sha256"] == alloc_sha and seal["case"] == case, "wrong case allocation"
        )
        require(all(sha(root / n) == v for n, v in seal["files"].items()), "sealed file changed")
        terminal = read(root / "terminal.json")
        base = {
            "ordinal": case["ordinal"],
            "case": case["teacher_case"],
            "direction": case["direction"],
            "case_id": case["id"],
            "seal_sha256": sha(root / "seal.json"),
            "retained_bytes": seal["bytes"],
            "teacher_frames": terminal["frames"],
            "teacher_unframed_actions": terminal["unframed"],
            "capture_wall_s_including_source_write": terminal["actual_wall_s"],
            "errors": terminal["errors"],
        }
        if not all((root / "source" / n).is_file() for n in RECOVERY_FILES):
            rows.append({**base, "status": "INCOMPLETE", "episode": terminal["episode"]})
            continue
        result = audit(root / "source", alloc["source_assignment"], case_fault(alloc, case), rules)
        require(terminal["episode"] == result["episode"], "summary foreign to acquired source")
        if terminal["errors"] or not seal["retained_budget_met"]:
            result["status"] = "INCOMPLETE"
        rows.append({**base, **result})
    require(
        len({r["episode"] for r in rows if r["episode"]}) == sum(bool(r["episode"]) for r in rows),
        "repeated acquired episode",
    )
    write(
        out,
        {
            "schema": "graduation.development-fault-pairs.v1",
            "allocation_sha256": alloc_sha,
            "counts": count_cases(rows),
            "distinct_development_scenes": 1,
            "registered_allocations": 4,
            "teacher_cases": rows,
            "original_locked_recovery_pool": {"attempted": 1, "allocated": 200},
            "formal_online_recovery_comparisons": 0,
            "complete_replan_comparisons": 0,
            "formal_claims": 0,
            "provider_calls": 0,
            "robot_hardware_actions": 0,
            "scope": "Offline T5 recovery qualification in MuJoCo",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("allocate")
    new.add_argument("plan", type=Path)
    new.add_argument("plan_sha")
    new.add_argument("raw", type=Path)
    new.add_argument("out", type=Path)
    for name in ("history", "capture", "score"):
        p = commands.add_parser(name)
        p.add_argument("allocation", type=Path)
        p.add_argument("allocation_sha")
        if name != "history":
            p.add_argument("raw", type=Path)
        if name == "capture":
            p.add_argument("ordinal", type=int)
        else:
            p.add_argument("out", type=Path)
    a = parser.parse_args()
    if a.command == "allocate":
        allocate(a.plan, a.plan_sha, a.out, a.raw)
        return
    alloc = pinned(a.allocation, a.allocation_sha)
    require(
        all(
            sha(ROOT / n) == s
            for n, s in {**alloc["implementation_sha256"], **alloc["frozen_inputs"]}.items()
        ),
        "frozen source changed",
    )
    if a.command == "history":
        history(alloc, a.allocation_sha, a.out)
    elif a.command == "capture":
        capture(alloc, a.allocation_sha, a.ordinal, a.raw)
    else:
        score(alloc, a.allocation_sha, a.raw, a.out)


if __name__ == "__main__":
    main()
