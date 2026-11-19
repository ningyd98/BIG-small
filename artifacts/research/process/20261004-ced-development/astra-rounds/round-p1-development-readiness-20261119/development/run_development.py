"""Single-owner research runner around the installed, normal development Harness CLI."""

from __future__ import annotations

import argparse
import fcntl
import importlib
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from development_plan import (
    OLD_RAW,
    OLD_ROUND,
    RAW,
    REPO,
    ROUND,
    SLOT_BUDGET,
    bind_source,
    canonical,
    digest,
    git,
    make_assignments,
    require,
    score_outcomes,
    sha,
)

from cloud_edge_robot_arm.harness.checkout import OVERLAY, native_source_bindings, verify_checkout
from cloud_edge_robot_arm.harness.config import load_config, strict_json
from cloud_edge_robot_arm.harness.evidence import EpisodeExpectation
from cloud_edge_robot_arm.vision.molmo_pointing import _verify_assets

OWNER = RAW / "p1-live-development-20261119"
LIVE_PLAN = ROUND.parent / "round-p1-live-development-window-20261119/plan.json"
LIVE_PLAN_SHA = "a7cf88628f72183b9bd5b3c4d9ab07061338b685538b92ecb142ef6711a894ff"
LIVE_REFRESH = ROUND.parent / "round-p1-live-b0-input-refresh-20261119/plan.json"
LIVE_REFRESH_SHA = "56c0127c710b61e532de8f00b733390f17c9f507fc6f8cef53b94081f42f065f"
MODEL_FREE_BYTES = 60 * 1024**3
IDENTITY_MESSAGE = "servo initial target/registered marker identity unavailable"


def legacy_readers():
    # These helpers take explicit paths and data. The old launch or owner is never called.
    sys.path.insert(0, str(OLD_ROUND))
    try:
        return importlib.import_module("run_fresh"), importlib.import_module("verify_fresh")
    finally:
        sys.path.remove(str(OLD_ROUND))


def read(path):
    return strict_json(path.read_bytes())


def persist(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@contextmanager
def exclusive_owner(root=OWNER):
    require(root.resolve() == root, "canonical owner location is redirected")
    lock = root / "owner.lock"
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, mode=0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield descriptor
    finally:
        os.close(descriptor)


def verify_live_plan():
    require(sha(LIVE_PLAN) == LIVE_PLAN_SHA, "Astra live plan differs")
    plan = read(LIVE_PLAN)
    require(sha(LIVE_PLAN.with_suffix(".md")) == plan["plan_md_sha256"], "live Markdown differs")
    require(sha(LIVE_REFRESH) == LIVE_REFRESH_SHA, "Astra live input refresh differs")
    refresh = read(LIVE_REFRESH)
    require(
        sha(LIVE_REFRESH.with_suffix(".md")) == refresh["plan_md_sha256"],
        "live refresh Markdown differs",
    )
    require(refresh["original_plan_sha256"] == LIVE_PLAN_SHA, "live refresh base differs")
    expected = plan["inputs_sha256"]
    replacements = refresh["replacements"]
    require(
        len(replacements) == 2
        and refresh["unchanged_13_sha256"]
        == {
            path: digest_value
            for path, digest_value in expected.items()
            if path not in replacements
        },
        "approved refresh does not conserve the original 13 inputs",
    )
    for path, replacement in replacements.items():
        require(expected[path] == replacement["before"], "refresh baseline changed")
        source = subprocess.check_output(
            ["git", "-C", REPO, "show", f"{refresh['git_witness']}:{path}"]
        )
        require(
            digest(source) == replacement["after"] == sha(REPO / path),
            f"refreshed Git witness or bytes differ: {path}",
        )
        if path == "configs/research/ced_selection.yaml":
            unchanged_roles = [
                line
                for line in source.splitlines(keepends=True)
                if line.startswith(b"role_probe: ")
            ]
            require(len(unchanged_roles) == 1, "B0 role_probe witness is ambiguous")
            original = source.replace(unchanged_roles[0], b"role_probe: null\n", 1)
            require(
                digest(original) == replacement["before"], "original B0 YAML cannot be restored"
            )
    for name, value in (
        refresh["unchanged_13_sha256"] | refresh["additional_witnesses_sha256"]
    ).items():
        require(sha(REPO / name) == value, f"planned input bytes changed: {name}")
    return {
        "live_plan_sha256": LIVE_PLAN_SHA,
        "input_refresh_sha256": LIVE_REFRESH_SHA,
        "refreshed_input_count": len(replacements),
        "unchanged_input_count": len(refresh["unchanged_13_sha256"]),
        "planning_input_git_witness": refresh["git_witness"],
    }


def capacity(resources, root=OWNER):
    model = Path(resources["--model-directory"])
    old_usage = archive_blocks(OLD_RAW / "native")
    actual = archive_blocks(root / "native")
    return {
        "model_fs_device": model.stat().st_dev,
        "output_fs_device": root.stat().st_dev,
        "model_fs_free_bytes": shutil.disk_usage(model).free,
        "output_fs_free_bytes": shutil.disk_usage(root).free,
        "production_model_min_free_bytes": MODEL_FREE_BYTES,
        "old_four_native_allocated_bytes": old_usage,
        "new_native_allocated_bytes": actual,
    }


def archive_blocks(root):
    total = 0
    visited = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        stat = path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity not in visited:
            visited.add(identity)
            total += 512 * stat.st_blocks
    return total


def run_env(*, launching=False):
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "OPENAI_BASE_URL"}
    }
    env.update(
        {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
    )
    if launching:
        env["MUJOCO_GL"] = "egl"
    else:
        env["CUDA_VISIBLE_DEVICES"] = ""
    return env


def installed_json(command, root):
    raw = subprocess.check_output(command, cwd=root, env=run_env())
    value = strict_json(raw)
    require(isinstance(value, dict), "preflight did not return a JSON object")
    return value


def registered_slots(allocation):
    development = allocation["development"]
    repeats = allocation["repeats_1802"]
    slots = development + repeats
    require(len(development) == 20 and len(repeats) == 2, "registered cohort sizes differ")
    require(len({slot["assignment_id"] for slot in slots}) == 22, "assignment identities collide")
    require(
        len({slot["run_instance_id"] for slot in slots}) == 22, "run instance identities collide"
    )
    main_expected, repeats_expected = make_assignments()
    for slot, expected in zip(slots, main_expected + repeats_expected, strict=True):
        require(
            all(slot[key] == item for key, item in expected.items())
            and slot["config"] == expected["assignment_id"] + ".json",
            "registered seed, pose, budget, order or output path differs",
        )
    return slots


def stage(args):
    """Prepare exact installed roles and poses. This subcommand never launches native work."""
    planning = verify_live_plan()
    source = args.source_checkout.resolve(strict=True)
    data = read(args.allocation)
    binding = bind_source(source, data["source"]["product_commit"])
    require(binding == data["source"], "allocated product binding differs")
    require(sha(args.acceptance) == args.acceptance_sha256, "worker acceptance receipt differs")
    runner, _ = legacy_readers()
    resources = runner._resources(args.resources_from, read(OLD_ROUND / "preallocation.json"))
    require(not os.path.lexists(OWNER), "a canonical batch owner is already frozen")
    root = Path(tempfile.mkdtemp(prefix=OWNER.name + "-prepare-", dir=OWNER.parent))
    with exclusive_owner(root):
        for name in ("native", "receipts", "verification", "configs"):
            (root / name).mkdir(exist_ok=False)
        slots = registered_slots(data)
        paths = git(source, "ls-files", "--", *runner.PRODUCTION_PATHS).splitlines()
        sources = {path: sha(source / path) for path in paths}
        receipt = runner._verify_installed_wheel(args.cli, args.wheel, sources)
        asset = Path(resources["--asset-manifest"])
        _verify_assets(Path(resources["--model-directory"]), asset)
        asset_sha = sha(asset)
        cpu = installed_json(
            [
                resources["--native-python"],
                "-I",
                "-B",
                str(source / OVERLAY),
                "--preflight",
            ],
            root,
        )
        require(
            cpu["status"] == "IMPORT_AND_CPU_ABI_PASS"
            and cpu["cuda_initialized"] is False
            and all(cpu[key] == 0 for key in ("model_loads", "generation_calls", "paid_calls")),
            "CPU overlay readiness did not prove zero calls",
        )
        persist(root / "verification/native-cpu.json", cpu)
        for slot in slots:
            path = args.allocation.parent / slot["config"]
            require(sha(path) == slot["config_sha256"], "allocation config bytes differ")
            saved = root / "configs" / slot["config"]
            saved.write_bytes(path.read_bytes())
            config = load_config(saved)
            require(config.fingerprint() == slot["config_fingerprint"], "config model differs")
            validated = installed_json([str(args.cli), "validate", "--config", str(saved)], root)
            persist(root / "verification" / (slot["assignment_id"] + "-validate.json"), validated)
            slot["role_binding_sha256"] = runner._role_config(root, resources, config, asset_sha)
        config = load_config(root / "configs" / slots[0]["config"])
        selected = verify_checkout(source, config)
        native = native_source_bindings(selected)
        private_freeze = {
            "schema": "bigsmall.development.live-owner.v1",
            "source": str(source),
            "commit": binding["product_commit"],
            "tree": binding["product_tree"],
            "owner": str(OWNER),
            "cli": str(args.cli),
            "owner_runner_sha256": sha(Path(__file__)),
            "allocation_reader_sha256": sha(Path(__file__).with_name("development_plan.py")),
            "allocation_sha256": sha(args.allocation),
            "allocation": data,
            "planning_verification": planning,
            "accepted_worker_verification_sha256": args.acceptance_sha256,
            "checkout_selected_files": selected.files,
            "product_sources": sources,
            "overlay_sha256": native["overlay"]["sha256"],
            "asset_manifest_sha256": asset_sha,
            "native_python_sha256": sha(Path(resources["--native-python"])),
            "resources": resources,
            "capacity_before_run": capacity(resources, root),
            **receipt,
        }
        persist(root / "freeze.json", private_freeze)
        root.rename(OWNER)
        parent = os.open(OWNER.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    print(sha(OWNER / "freeze.json"), flush=True)


def freeze_at(digest_value):
    path = OWNER / "freeze.json"
    require(sha(path) == digest_value, "live owner freeze SHA differs")
    freeze = read(path)
    require(
        freeze["owner"] == str(OWNER)
        and freeze["owner_runner_sha256"] == sha(Path(__file__))
        and freeze["allocation_reader_sha256"]
        == sha(Path(__file__).with_name("development_plan.py")),
        "existing owner or launch source differs",
    )
    return freeze


def bound_slot(slot, freeze_sha):
    return {
        "id": slot["assignment_id"],
        "seed": slot["runtime_seed"],
        "instance": slot["run_instance_id"],
        "freeze_sha256": freeze_sha,
        "config_sha256": slot["config_sha256"],
        "attempt": 1,
        "model_budget": SLOT_BUDGET,
    }


def slot_paths(root, slot):
    identity = slot["assignment_id"]
    receipts = root / "receipts"
    paths = {kind: receipts / f"{identity}.{kind}" for kind in ("stdout", "stderr")}
    paths.update((kind, receipts / f"{identity}.{kind}.json") for kind in ("begin", "end", "audit"))
    paths["episode"] = root / slot["native_output"]
    return paths


def claim_presence(paths):
    seen = {key for key, path in paths.items() if os.path.lexists(path)}
    if not seen:
        return "NOT_EXECUTED"
    require("begin" in seen, "slot contains native bytes without a BEGIN")
    if "audit" in seen:
        require({"end", "stdout", "stderr", "episode"}.issubset(seen), "audited slot is incomplete")
        return "AUDITED"
    return "ENDED_UNVERIFIED" if "end" in seen else "STARTED_UNRESOLVED"


def readiness(freeze, slot):
    source = Path(freeze["source"])
    require(
        bind_source(source, freeze["commit"]) == freeze["allocation"]["source"],
        "product Git provenance drift",
    )
    resources = freeze["resources"]
    require(
        sha(Path(freeze["cli"])) == freeze["installed_launcher_sha256"]
        and sha(Path(resources["--native-python"])) == freeze["native_python_sha256"]
        and sha(Path(resources["--asset-manifest"])) == freeze["asset_manifest_sha256"],
        "launcher/runtime/model artifact drift",
    )
    space = capacity(resources)
    require(
        space["model_fs_free_bytes"] >= MODEL_FREE_BYTES,
        f"production model volume has {space['model_fs_free_bytes']} bytes, requires 60 GiB",
    )
    runner, _ = legacy_readers()
    config = load_config(OWNER / "configs" / slot["config"])
    require(sha(OWNER / "configs" / slot["config"]) == slot["config_sha256"], "slot config drift")
    require(
        runner._role_config(OWNER, resources, config, freeze["asset_manifest_sha256"])
        == slot["role_binding_sha256"],
        "active slot role binding drift",
    )
    runner._verify_gpu_release(Path(resources["--gpu-lock"]))
    return space


def replay_known_identity(case, result, episode, assignment, reader):
    reason = episode.get("exception") or {}
    if result["terminal_reason"] != "ValueError":
        return False
    if not (
        reason.get("type") == "ValueError"
        and reason.get("message") == IDENTITY_MESSAGE
        and reason.get("phase") == "SERVO_INITIALIZATION"
        and reason.get("step_id") == "step-01"
        and reason.get("skill") == "MOVE_ABOVE"
        and not episode.get("secondary_exceptions")
        and any(
            item["file"] == "src/cloud_edge_robot_arm/vision/servo.py"
            and item["function"] == "__init__"
            for item in reason.get("traceback", [])
        )
    ):
        return False
    reader.check_initialization_prefix(result, episode, case.json("component/commands.json"))
    from cloud_edge_robot_arm.vision.servo import measure_registered_marker_grasp

    planned = case.json("planning/planning-stage-02.json")["attempts"][0]["draft"][
        "observation_evidence"
    ]
    frame = reader.read_frame(
        case.root, case.files, "component/frames/post-cloud", result["episode_id"]
    )
    reader._frame_calibration(frame)
    require(planned["checksum_sha256"] == frame.checksum_sha256, "identity source frame drift")
    grasp, estimate = measure_registered_marker_grasp(frame, assignment["marker_family_id"])
    require(
        grasp is not None and estimate.status == "OBSERVED", "marker identity evidence unavailable"
    )
    distance = math.dist(grasp, [planned["resolved_top_grasp_tcp"][axis] for axis in "xyz"])
    require(distance > 0.01, "archived frame did not reproduce the original 10 mm identity limit")
    return {"difference_m": distance}


def terminal_attempt(case, job):
    raw = case.read("runtime.db")
    path = case.root / "runtime.db"
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
        jobs = db.execute(
            "SELECT job_id, seed, status, attempt, max_attempts, completed_at, source_tree_hash "
            "FROM simulation_jobs"
        ).fetchall()
        attempts = db.execute(
            "SELECT job_id, attempt, result, ended_at FROM simulation_job_attempts"
        ).fetchall()
        leases = db.execute("SELECT job_id, released_at FROM simulation_job_leases").fetchall()
    require(
        len(jobs) == len(attempts) == len(leases) == 1 and path.read_bytes() == raw,
        "runtime DB does not bind one unchanged attempt and lease",
    )
    identifier, seed, status, attempt, limit, completed, source = jobs[0]
    require(
        (identifier, seed, status, attempt, limit, source)
        == (job["job_id"], job["seed"], job["status"], 1, 1, job["source_tree_hash"])
        and bool(completed)
        and attempts[0][:3] == (identifier, 1, status)
        and bool(attempts[0][3])
        and leases[0][0] == identifier
        and bool(leases[0][1]),
        "runtime did not terminate and release the lease under the original attempt bound",
    )
    return {"status": status, "attempt": 1, "lease_released": True}


def audit_originals(freeze, slot, freeze_sha, paths):
    runner, reader = legacy_readers()
    binding = bound_slot(slot, freeze_sha)
    begin, end, launch = (read(paths[key]) for key in ("begin", "end", "stdout"))
    require(
        all(begin[key] == end[key] == value for key, value in binding.items())
        and end["begin_sha256"] == sha(paths["begin"])
        and all(end[key + "_sha256"] == sha(paths[key]) for key in ("stdout", "stderr")),
        "launch claim or wrapper logs differ",
    )
    config = load_config(OWNER / "configs" / slot["config"])
    source = verify_checkout(Path(freeze["source"]), config)
    require(
        launch["source"]["git_revision"] == freeze["commit"]
        and launch["source"]["files"] == source.files == freeze["checkout_selected_files"]
        and launch["planned_configuration_sha256"] == config.fingerprint()
        and launch["model_asset_manifest_sha256"] == freeze["asset_manifest_sha256"],
        "wrapper configuration or product binding differs",
    )
    native = launch["native_python"]
    require(
        native["status"] == "READY_TO_DELEGATE"
        and native["executable_sha256"] == freeze["native_python_sha256"]
        and native["registered_overlay"]["sha256"] == freeze["overlay_sha256"]
        and native["r545_admission"]["status"] == "IMPORT_AND_CPU_ABI_PASS",
        "wrapper native interpreter or overlay binding differs",
    )
    summary, case = reader.read_index(
        paths["episode"], expected=EpisodeExpectation(source, config, True)
    )
    require(
        launch["evidence"]["manifest_sha256"] == summary["manifest_sha256"],
        "independent archive and wrapper manifest differ",
    )
    result, episode, job, assignment = (
        case.json(name)
        for name in (
            "result.json",
            "component/episode.json",
            "worker/job.json",
            "scene-assignment.json",
        )
    )
    role = case.json("role-binding.json")
    require(
        case.json("worker/runtime_job.json") == job
        and result["episode_id"] == episode["episode_id"]
        and result["job_id"] == job["job_id"]
        and result["worker_status"] == job["status"]
        and job["seed"] == slot["runtime_seed"]
        and job["attempt"] == 1
        and job["hardware_write_operations"] == []
        and job["real_controller_contacted"] is False
        and job["hardware_motion_observed"] is False
        and job["source_tree_hash"] == role["bundle_hash"]
        and result["source_snapshot_status"] == "COMPLETE"
        and result["changed_source_paths"] == []
        and launch["status"] == result["status"]
        and launch["episode"] == summary["episode"],
        "worker/archive/wrapper terminal bindings differ",
    )
    applied = case.json("component/scene-application.json")
    require(applied == episode["scene_application"], "applied pose records disagree")
    pose = reader.check_pose(slot["scene"], config, assignment, applied)
    source_count = reader.check_sources(
        role, case.json("source-hashes.json"), freeze["product_sources"], slot
    )
    counters = reader.check_model_evidence(case, result, freeze)
    physical = reader.check_component(case, result, episode)
    backend_exit = terminal_attempt(case, job)
    matched_identity = replay_known_identity(case, result, episode, assignment, reader)
    row = {
        "audit_status": "VERIFIED",
        "component_success": result["component_success"],
        "terminal_reason": result["terminal_reason"],
        "returncode": end["returncode"],
        **{
            k: launch[k]
            for k in ("wrapper_exit_code", "episode_exit_code", "signal", "wrapper_stop_reason")
        },
        **physical,
    }
    conclusive = runner._contained_stops(row) or (
        bool(matched_identity)
        and row["physical"]["safety_violation"] is False
        and row["signal"] is None
        and row["wrapper_stop_reason"] is None
        and all(row[k] == 2 for k in ("returncode", "wrapper_exit_code", "episode_exit_code"))
    )
    ledger = [
        {k: item.get(k) for k in ("request_id", "monetary_cost", "currency", "status")}
        for item in case.json("costs.json")["requests"]
        if item["is_cloud_model"] is True
    ]
    return {
        **row,
        "recognized_terminal": conclusive,
        "applied_pose": pose,
        "independent_physical_success": physical["physical"]["success"],
        "job_id": job["job_id"],
        "episode_id": result["episode_id"],
        "terminal_attempt": backend_exit,
        "manifest_sha256": summary["manifest_sha256"],
        "manifest_files": summary["file_count"],
        "begin_sha256": sha(paths["begin"]),
        "end_sha256": sha(paths["end"]),
        "source_files_checked": source_count,
        "observed_counters": counters,
        "ledger": ledger,
        "worker_exception": episode.get("exception"),
        "identity_readback": matched_identity,
    }


def launch_slot(freeze, slot, freeze_sha, descriptor):
    paths = slot_paths(OWNER, slot)
    require(claim_presence(paths) == "NOT_EXECUTED", "existing BEGIN is irrevocable")
    space = readiness(freeze, slot)
    binding = bound_slot(slot, freeze_sha)
    persist(paths["begin"], binding | {"started_at": datetime.now(UTC).isoformat(), "space": space})
    print(f"BEGIN {slot['assignment_id']} seed={slot['runtime_seed']}", flush=True)
    flags = [item for pair in freeze["resources"].items() for item in pair]
    command = [
        freeze["cli"],
        "run-simulation",
        "--config",
        str(OWNER / "configs" / slot["config"]),
        "--source-checkout",
        freeze["source"],
        *flags,
        "--allow-paid",
        "--output",
        str(paths["episode"]),
    ]
    with paths["stdout"].open("xb") as stdout, paths["stderr"].open("xb") as stderr:
        done = subprocess.run(
            command,
            cwd=OWNER,
            env=run_env(launching=True),
            stdout=stdout,
            stderr=stderr,
            pass_fds=(descriptor,),
            check=False,
        )
        os.fsync(stdout.fileno())
        os.fsync(stderr.fileno())
    persist(
        paths["end"],
        binding
        | {
            "finished_at": datetime.now(UTC).isoformat(),
            "returncode": done.returncode,
            "begin_sha256": sha(paths["begin"]),
            "stdout_sha256": sha(paths["stdout"]),
            "stderr_sha256": sha(paths["stderr"]),
            "space": capacity(freeze["resources"]),
        },
    )
    try:
        row = audit_originals(freeze, slot, freeze_sha, paths)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        persist(
            paths["audit"].with_suffix(".unresolved.json"),
            {
                "original_end_sha256": sha(paths["end"]),
                "error_type": type(exc).__name__,
                "message": str(exc),
                "status": "STARTED_UNRESOLVED",
            },
        )
        raise
    persist(paths["audit"], row)
    print(
        f"END {slot['assignment_id']} {row['terminal_reason']} "
        f"physical={row['independent_physical_success']} exit={done.returncode}",
        flush=True,
    )
    require(row["recognized_terminal"], "unexpected terminal retained; stop before next BEGIN")


def completed_row(slot, audit, evidence_sha):
    return {
        "assignment_id": slot["assignment_id"],
        "run_instance_id": slot["run_instance_id"],
        "pose_seed": slot["pose_seed"],
        "status": "AUDITED",
        "component_completed": audit["component_success"],
        "independent_physical_success": audit["independent_physical_success"],
        "audit_sha256": evidence_sha,
    }


def bill_totals(originals):
    invoices = {}
    missing = 0
    for row in originals.values():
        for item in row["ledger"]:
            currency, amount = item["currency"], item["monetary_cost"]
            if currency is None or amount is None:
                missing += 1
                continue
            invoices[currency] = invoices.get(currency, Decimal(0)) + Decimal(str(amount))
    return {
        "settled_reported_amount_by_currency": {k: str(v) for k, v in invoices.items()} or None,
        "cloud_entries_without_amount_and_currency_pair": missing,
    }


def independent_report(freeze, freeze_sha):
    records = []
    originals = {}
    slots = registered_slots(freeze["allocation"])
    for slot in slots:
        paths = slot_paths(OWNER, slot)
        status = claim_presence(paths)
        if status in {"ENDED_UNVERIFIED", "AUDITED"}:
            try:
                audit = audit_originals(freeze, slot, freeze_sha, paths)
            except (KeyError, TypeError, ValueError, OSError):
                status = "STARTED_UNRESOLVED"
            else:
                if status == "AUDITED":
                    require(read(paths["audit"]) == audit, "independent audit differs from prior")
                records.append(completed_row(slot, audit, digest(canonical(audit))))
                originals[slot["assignment_id"]] = audit
                continue
        records.append(
            {
                "assignment_id": slot["assignment_id"],
                "run_instance_id": slot["run_instance_id"],
                "pose_seed": slot["pose_seed"],
                "status": status,
                "component_completed": None,
                "independent_physical_success": None,
                "audit_sha256": None,
            }
        )
    closed = len(originals) == len(slots)
    jobs = {row["job_id"] for row in originals.values()}
    episodes = {row["episode_id"] for row in originals.values()}
    require(len(jobs) == len(episodes) == len(originals), "trial raw identities were reused")
    cloud_requests = [row["request_id"] for audit in originals.values() for row in audit["ledger"]]
    require(
        all(cloud_requests) and len(set(cloud_requests)) == len(cloud_requests),
        "actual cloud dispatch IDs are absent or reused",
    )
    return {
        "freeze_sha256": freeze_sha,
        "batch_statistics": score_outcomes(freeze["allocation"], records, closed=closed),
        "statuses": records,
        "individual_audits": originals,
        "cloud_requests": sum(
            row["observed_counters"]["cloud_requests"] for row in originals.values()
        ),
        "local_generations": sum(
            row["observed_counters"]["local_generations"] for row in originals.values()
        ),
        "model_loads": sum(row["observed_counters"]["model_loads"] for row in originals.values()),
        "unresolved_cost_may_be_present": any(x["status"] == "STARTED_UNRESOLVED" for x in records),
        "billing": bill_totals(originals),
        "dispatch_retries": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True, dest="command")
    prepare = commands.add_parser("stage")
    for name in ("allocation", "source-checkout", "acceptance", "cli", "wheel", "resources-from"):
        prepare.add_argument("--" + name, type=Path, required=True)
    prepare.add_argument("--acceptance-sha256", required=True)
    dispatch = commands.add_parser("launch")
    dispatch.add_argument("--freeze-sha256", required=True)
    dispatch.add_argument("--remaining", action="store_true")
    readback = commands.add_parser("audit")
    readback.add_argument("--freeze-sha256", required=True)
    readback.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "stage":
        stage(args)
        return
    with exclusive_owner() as descriptor:
        freeze = freeze_at(args.freeze_sha256)
        if args.command == "audit":
            persist(args.output, independent_report(freeze, args.freeze_sha256))
            return
        for slot in registered_slots(freeze["allocation"]):
            paths = slot_paths(OWNER, slot)
            status = claim_presence(paths)
            if status == "AUDITED":
                saved = read(paths["audit"])
                audit = audit_originals(freeze, slot, args.freeze_sha256, paths)
                require(saved == audit, "prior finished trial audit changed")
                require(audit["recognized_terminal"], "a prior trial requires bounded review")
                continue
            require(status == "NOT_EXECUTED", "a previous BEGIN is unresolved and cannot rerun")
            launch_slot(freeze, slot, args.freeze_sha256, descriptor)
            if not args.remaining:
                break


if __name__ == "__main__":
    main()
