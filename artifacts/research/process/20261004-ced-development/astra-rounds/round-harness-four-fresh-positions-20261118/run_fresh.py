"""Prepare or launch one preregistered development slot through the installed Harness."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verify_fresh import (
    FREEZE_SCHEMA,
    INITIALIZATION_STOP_FREEZE_SHA256,
    INITIALIZATION_STOP_MANIFEST_SHA256,
    INITIALIZATION_STOP_PREDECESSOR,
    INITIALIZATION_STOP_PROOF_SHA256,
    INITIALIZATION_STOP_SUCCESSOR,
    PREALLOCATION_SHA256,
    ROOT,
    ROUND,
    SUCCESSOR_STAGE,
    audit_slot,
    check_slot_directories,
    read,
    read_allocation,
    read_freeze,
    require,
    slot_config_path,
    verify_frozen_sources,
    write_new,
)

from cloud_edge_robot_arm.harness.checkout import (
    OVERLAY,
    native_source_bindings,
    sha256_file,
    verify_checkout,
)
from cloud_edge_robot_arm.harness.config import load_config
from cloud_edge_robot_arm.harness.evidence import verify_evidence
from cloud_edge_robot_arm.research.sol_molmo_single_episode import (
    create_molmo_opencv_bridge,
    scene_assignment,
    selected_sol_service,
)
from cloud_edge_robot_arm.vision.molmo_pointing import _verify_assets
from cloud_edge_robot_arm.vision.role_models import configuration_hash

PRODUCTION_PATHS = ("pyproject.toml", "src", "assets", "configs", "scripts", OVERLAY)
REGISTERED_CHECKOUT = Path("/tmp/bigsmall-harness-v5-verified-20261118")
REGISTERED_RAW_ROOT = Path(
    "/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/"
    "experiments/results/phase9/harness-four-fresh-20261118"
)
DRY_PREPARE_ASSIGNMENT = "verification/dry-prepare/scene-assignment.json"
DRY_PREPARE_ASSIGNMENT_SHA256 = "cef1ca0bdac6ff21cc99325039eb090069e46b707d3b94f4598c4f9269c0381a"
OLD_FREEZE_SHA256 = "41ae9cd2a411a1870b41f347c120371af67228dbe95facabecd21326308ca14e"
OLD_STAGE_ARCHIVE = (
    REGISTERED_RAW_ROOT.parents[3] / "cache/four-fresh-02dbaef9-frozen-stage-20261118"
)
OLD_STAGE_MANIFEST = ROUND.parent / "round-harness-four-v5-refreeze-20261118/old-stage-inputs.json"
OLD_STAGE_MANIFEST_SHA256 = "fd0365e155b0cf2a73f941891f44a06b170b62628d4a2d6bfdbfc1ac22c5e8c7"
SUCCESSOR_COMMIT = "5103e7f483b9fccd40cf2e49d4bd5ef8979f64d2"
SUCCESSOR_WHEEL_SHA256 = "00065493d60e83b9574d1a0530a0a14977ad051053798a271a27f707b1e9bdd2"
V5_CONFIG_PATH = "configs/research/ced_marker_registration_v5.yaml"
V5_CONFIG_SHA256 = "64d111c52a08636ee9b3cdae9f874d4a932ed98d357be7cde501279d088216e9"
RUNTIME_FLAGS = (
    "--native-python",
    "--application-site-packages",
    "--model-control-db",
    "--profile-id",
    "--model-directory",
    "--asset-manifest",
    "--gpu-lock",
)
RECOGNIZED_PROTECTIVE_STOPS = frozenset(
    {
        "COMPONENT_INITIAL_PLANNING_REJECTED",
        "COMPONENT_FRESH_PLANNING_REJECTED",
        "CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED",
    }
)


def _git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=checkout, text=True)


def _environment(*, launch: bool = False) -> dict[str, str]:
    environment = dict(
        os.environ,
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONDONTWRITEBYTECODE="1",
    )
    for key in ("PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        environment.pop(key, None)
    if launch:
        environment.update(
            MUJOCO_GL="egl",
            OMP_NUM_THREADS="1",
            OPENBLAS_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
        )
    else:
        environment["CUDA_VISIBLE_DEVICES"] = ""
    return environment


def _resources(path: Path, allocation: dict[str, Any]) -> dict[str, str]:
    expected = next(
        source
        for source in allocation["sources"]
        if source["root"] == "historical-resource-receipt"
    )
    require(sha256_file(path) == expected["sha256"], "registered launch resource receipt changed")
    arguments = read(path)["argv"]
    selected = {flag: arguments[arguments.index(flag) + 1] for flag in RUNTIME_FLAGS}
    for flag, value in selected.items():
        if flag == "--profile-id":
            continue
        require(Path(value).exists() and os.access(value, os.R_OK), f"resource unavailable {flag}")
    return selected


def _check_free_space(root: Path, model_root: Path) -> dict[str, int]:
    root_free = shutil.disk_usage(root).free
    model_free = shutil.disk_usage(model_root).free
    require(root_free >= 4 * 1024**3, "insufficient local archive space for four raw slots")
    require(model_free >= 60 * 1024**3, "local model resource disk admission would fail")
    return {"archive_available_bytes": root_free, "model_fs_available_bytes": model_free}


def _history_values(value: Any) -> tuple[set[int], set[tuple[float, ...]]]:
    seeds, positions = set(), set()
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            if type(current.get("seed")) is int:
                seeds.add(current["seed"])
            position, yaw = current.get("object_position_m"), current.get("object_yaw_rad")
            if (
                isinstance(position, list)
                and len(position) == 3
                and all(type(item) in {float, int} for item in [*position, yaw])
            ):
                positions.add(tuple(round(item, 6) for item in [*position, yaw]))
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return seeds, positions


def check_history(
    worktrees: tuple[Path, ...],
    slots: list[dict[str, Any]],
    *,
    successor_dry_sha: str | None = None,
) -> dict[str, Any]:
    """Check archived requests and preallocations before the first launch."""
    proposed = {row["seed"] for row in slots}
    poses = {tuple([*row["object_position_m"], row["object_yaw_rad"]]) for row in slots}
    checked = []
    conflicts = []
    distinct = set()
    dry_prepare = None
    dry_path = REGISTERED_RAW_ROOT / DRY_PREPARE_ASSIGNMENT
    new_dry_prepare = None
    new_dry_path = REGISTERED_RAW_ROOT / SUCCESSOR_STAGE / DRY_PREPARE_ASSIGNMENT
    for worktree in worktrees:
        for subdir in ("experiments", "results", "artifacts/research/process"):
            directory = worktree / subdir
            if not directory.is_dir():
                continue
            for name in ("scene-assignment.json", "scene-application.json", "preallocation.json"):
                for path in directory.rglob(name):
                    resolved = path.resolve()
                    if path.absolute() == dry_path:
                        require(
                            resolved == dry_path
                            and sha256_file(path) == DRY_PREPARE_ASSIGNMENT_SHA256,
                            "registered dry-prepare assignment SHA256 or path changed",
                        )
                        dry_prepare = {
                            "path": DRY_PREPARE_ASSIGNMENT,
                            "sha256": DRY_PREPARE_ASSIGNMENT_SHA256,
                        }
                        continue
                    if path.absolute() == new_dry_path and successor_dry_sha is not None:
                        require(
                            resolved == new_dry_path and sha256_file(path) == successor_dry_sha,
                            "registered successor dry-prepare assignment SHA256 or path changed",
                        )
                        new_dry_prepare = {
                            "path": f"{SUCCESSOR_STAGE}/{DRY_PREPARE_ASSIGNMENT}",
                            "sha256": successor_dry_sha,
                        }
                        continue
                    if not resolved.is_relative_to(worktree.resolve()) or resolved in distinct:
                        continue
                    distinct.add(resolved)
                    digest = sha256_file(path)
                    if digest == PREALLOCATION_SHA256:
                        continue
                    seen_seeds, seen_poses = _history_values(read(path))
                    checked.append((str(path), digest))
                    if proposed & seen_seeds or poses & seen_poses:
                        conflicts.append(path.relative_to(worktree).as_posix())
    require(not conflicts, "existing assigned seed or pose separates this batch: " + str(conflicts))
    return {
        "files_checked": len(checked),
        "path_bytes_vector_sha256": hashlib.sha256(
            json.dumps(sorted(checked)).encode(),
        ).hexdigest(),
        "matches": 0,
        "own_dry_prepare": dry_prepare,
        "successor_dry_prepare": new_dry_prepare,
    }


def _verify_installed_wheel(
    cli: Path,
    wheel: Path,
    sources: dict[str, str],
) -> dict[str, Any]:
    python = cli.parent / "python"
    imported = subprocess.check_output(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            "from pathlib import Path; import cloud_edge_robot_arm; "
            "print(Path(cloud_edge_robot_arm.__file__).resolve().parent)",
        ],
        env=_environment(),
        cwd=wheel.parent,
        text=True,
    )
    root = Path(imported.strip())
    require(
        root.is_relative_to(cli.parent.parent.resolve()),
        "installed harness import does not belong to the selected venv",
    )
    checked = 0
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.startswith("cloud_edge_robot_arm/") and name.endswith((".py", ".json")):
                relative = name.removeprefix("cloud_edge_robot_arm/")
                content = archive.read(name)
                require(
                    (root / relative).read_bytes() == content,
                    f"installed wheel bytes differ at {relative}",
                )
                require(
                    hashlib.sha256(content).hexdigest() == sources.get("src/" + name),
                    f"wheel does not match the frozen checkout at {relative}",
                )
                checked += 1
    require(checked > 0, "wheel does not supply installed Harness")
    return {
        "wheel_sha256": sha256_file(wheel),
        "installed_launcher_sha256": sha256_file(cli),
        "installed_python_json_members_verified": checked,
    }


def _command_json(args: list[str], *, cwd: Path) -> dict[str, Any]:
    done = subprocess.run(
        args,
        check=True,
        cwd=cwd,
        env=_environment(),
        capture_output=True,
        text=True,
    )
    result = json.loads(done.stdout)
    require(isinstance(result, dict), "command did not emit a JSON object")
    return result


def _role_config(
    root: Path,
    resources: dict[str, str],
    config: Any,
    model_manifest_sha: str,
) -> str:
    class NoPoints:
        def point(self, *_: Any) -> None:
            raise RuntimeError("model invocation prohibited during freeze")

    service = selected_sol_service(
        Path(resources["--model-control-db"]),
        resources["--profile-id"],
    )
    assignment = scene_assignment(config.seed, config.marker_family, scene_split=config.scene_split)
    assignment.update(
        component_diagnostic=True,
        cloud_vision_fallback=False,
        visual_servo=True,
        camera_position_m=list(config.camera_position_m),
    )
    with tempfile.TemporaryDirectory(prefix="role-contract-", dir=root / "verification") as temp:
        _, binding = create_molmo_opencv_bridge(
            service=service,
            profile_id=resources["--profile-id"],
            points=NoPoints(),
            assignment=assignment,
            output=Path(temp),
            asset_manifest_sha256=model_manifest_sha,
        )
    return configuration_hash(binding.evidence())


def _unclaimed_owner(root: Path) -> None:
    for path in (root / "receipts", root / "native"):
        require(path.resolve() == path and path.is_dir(), "batch occupancy directory unavailable")
        require(not any(path.iterdir()), "batch occupancy exists; refreeze stopped")


def _old_stage_inventory() -> dict[str, Any]:
    require(
        sha256_file(OLD_STAGE_MANIFEST) == OLD_STAGE_MANIFEST_SHA256,
        "old stage manifest SHA changed",
    )
    manifest = read(OLD_STAGE_MANIFEST)
    require(manifest["old_freeze_sha256"] == OLD_FREEZE_SHA256, "old stage freeze differs")
    return manifest["old_stage_files"]


def _check_old_stage(root: Path, inventory: dict[str, Any]) -> None:
    for name, frozen in inventory.items():
        path = root / name
        require(
            path.resolve() == path
            and path.is_relative_to(root)
            and path.stat().st_size == frozen["bytes"]
            and sha256_file(path) == frozen["sha256"],
            f"old stage changed at {name}",
        )


def _old_stage_snapshot(root: Path, inventory: dict[str, Any]) -> None:
    target = OLD_STAGE_ARCHIVE
    if target.exists():
        _check_old_stage(target, inventory)
        require(
            all((target / path).stat().st_mode & 0o222 == 0 for path in inventory),
            "older archive copy is writable",
        )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="old-stage-", dir=target.parent) as temporary:
        snapshot = Path(temporary)
        for name in inventory:
            output = snapshot / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, output)
            output.chmod(0o444)
        _check_old_stage(snapshot, inventory)
        for directory in sorted(
            (item for item in snapshot.rglob("*") if item.is_dir()),
            reverse=True,
        ):
            directory.chmod(0o555)
        snapshot.chmod(0o555)
        snapshot.rename(target)


def _dry_prepare_proof(stage: Path) -> dict[str, str]:
    prepare = stage / "verification/installed-prepare.json"
    entry = stage / "verification/dry-prepare"
    report = read(prepare)
    verified = verify_evidence(entry)
    episode = verified["episode"]
    require(
        report["status"] == episode["status"] == "PREPARED"
        and report["source"]["git_revision"] == SUCCESSOR_COMMIT
        and report["evidence"]["manifest_sha256"] == verified["manifest_sha256"]
        and all(
            type(episode[key]) is int and episode[key] == 0
            for key in (
                "model_calls",
                "model_loads",
                "local_generations",
                "cloud_requests",
                "cloud_request_reservations",
                "executed_actions",
                "physics_steps",
            )
        )
        and episode["hardware_dispatch"] is False,
        "successor dry-prepare did not prove recorded zero model and action use",
    )
    return {
        "assignment_sha256": sha256_file(stage / DRY_PREPARE_ASSIGNMENT),
        "manifest_sha256": verified["manifest_sha256"],
        "prepare_receipt_sha256": sha256_file(prepare),
    }


def _validate_successor_stage(root: Path, expected_sha: str) -> Path:
    staged = root / SUCCESSOR_STAGE / "freeze-receipt.json"
    require(staged.resolve() == staged, "successor freeze file is redirected")
    freeze = read_freeze(staged, expected_sha)
    require(
        freeze["commit"] == SUCCESSOR_COMMIT
        and freeze.get("staging") == SUCCESSOR_STAGE
        and freeze["wheel_sha256"] == SUCCESSOR_WHEEL_SHA256,
        "successor stage differs from the verified product or wheel",
    )
    verify_frozen_sources(REGISTERED_CHECKOUT, freeze)
    require(
        _dry_prepare_proof(staged.parent) == freeze["dry_prepare"],
        "successor dry-prepare evidence differs from freeze",
    )
    for identity, slot in freeze["slots"].items():
        require(
            sha256_file(slot_config_path(root, freeze, identity)) == slot["config_sha256"],
            f"frozen configuration changed for {identity}",
        )
    return staged


def _install_active_freeze(root: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=root, prefix=".pending-freeze-", delete=False) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stream.name, root / "freeze-receipt.json")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _activate_locked(root: Path, expected_sha: str) -> None:
    _unclaimed_owner(root)
    selected = root / "freeze-receipt.json"
    require(sha256_file(selected) == OLD_FREEZE_SHA256, "old freeze is not the active selection")
    inventory = _old_stage_inventory()
    _check_old_stage(root, inventory)
    staged = _validate_successor_stage(root, expected_sha)
    _old_stage_snapshot(root, inventory)
    data = staged.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected_sha, "successor freeze changed at cutover")
    _install_active_freeze(root, data)


def activate(args: argparse.Namespace) -> int:
    checkout = args.checkout.resolve(strict=True)
    root = args.raw_root.resolve(strict=True)
    _require_registered_locations(checkout, root)
    with (root / ".batch-launch.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _activate_locked(root, args.freeze_sha256)
    print(json.dumps({"status": "ACTIVE_SUCCESSOR_FREEZE", "freeze_sha256": args.freeze_sha256}))
    return 0


def prepare(args: argparse.Namespace) -> int:
    checkout = args.checkout.resolve(strict=True)
    owner = args.raw_root.resolve(strict=True)
    _require_registered_locations(checkout, owner)
    with (owner / ".batch-launch.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _prepare_locked(args, checkout, owner)


def _prepare_locked(args: argparse.Namespace, checkout: Path, owner: Path) -> int:
    _unclaimed_owner(owner)
    _check_old_stage(owner, _old_stage_inventory())
    old = read_freeze(owner / "freeze-receipt.json", OLD_FREEZE_SHA256)
    raw_root = owner / SUCCESSOR_STAGE
    require(not raw_root.exists(), "successor staging already exists")
    require(sha256_file(args.wheel) == SUCCESSOR_WHEEL_SHA256, "wrong rebuilt wheel")
    allocation = read_allocation(ROUND / "preallocation.json")
    resources = _resources(args.resources_from, allocation)
    dirty = _git(
        checkout, "status", "--porcelain", "--untracked-files=all", "--", *PRODUCTION_PATHS
    )
    require(not dirty, "production source must be committed before the four-slot freeze")
    commit = _git(checkout, "rev-parse", "HEAD").strip()
    tree = _git(checkout, "rev-parse", "HEAD^{tree}").strip()
    require(commit == SUCCESSOR_COMMIT, "source checkout is not the verified v5 commit")
    files = _git(checkout, "ls-tree", "-r", "--name-only", "-z", commit, "--", *PRODUCTION_PATHS)
    sources = {name: sha256_file(checkout / name) for name in files.split("\0") if name}
    require(
        sources == old["product_sources"] | {V5_CONFIG_PATH: V5_CONFIG_SHA256},
        "new product inventory differs beyond the approved v5 configuration",
    )
    history_roots = tuple(
        dict.fromkeys(
            [*(Path(path) for path in old["history_roots"]), checkout],
        )
    )
    history = check_history(history_roots, allocation["episodes"])
    raw_root.parent.mkdir(parents=True, exist_ok=True)
    space = _check_free_space(raw_root.parent, Path(resources["--model-directory"]))
    raw_root.mkdir(parents=True, exist_ok=False)
    for name in ("configs", "verification"):
        (raw_root / name).mkdir()
    package = _verify_installed_wheel(args.cli, args.wheel, sources)
    config = load_config()
    source = verify_checkout(checkout, config)
    binding = native_source_bindings(source)
    manifest_path = Path(resources["--asset-manifest"])
    asset_sha = sha256_file(manifest_path)
    _verify_assets(Path(resources["--model-directory"]), manifest_path)
    r545 = _command_json(
        [
            resources["--native-python"],
            "-I",
            "-B",
            str(checkout / OVERLAY),
            "--preflight",
        ],
        cwd=raw_root,
    )
    require(
        r545["status"] == "IMPORT_AND_CPU_ABI_PASS"
        and r545["cuda_initialized"] is False
        and all(r545[key] == 0 for key in ("model_loads", "generation_calls", "paid_calls")),
        "R545 did not verify the zero-GPU/zero-model precondition",
    )
    write_new(raw_root / "verification/r545-cpu.json", r545)
    slots = {}
    for slot in allocation["episodes"]:
        identity = slot["id"]
        path = raw_root / "configs" / f"{identity}.json"
        staged = config.model_copy(update={"seed": slot["seed"], "scene_split": "development"})
        write_new(path, staged.model_dump(mode="json"))
        checked = _command_json([str(args.cli), "validate", "--config", str(path)], cwd=raw_root)
        write_new(raw_root / "verification" / f"{identity}-validate.json", checked)
        slots[identity] = {
            "config_sha256": sha256_file(path),
            "configuration_sha256": staged.fingerprint(),
            "role_binding_sha256": _role_config(raw_root, resources, staged, asset_sha),
        }
    path = raw_root / "configs" / f"{next(iter(slots))}.json"
    for command, extra in (
        ("doctor", ["--source-checkout", str(checkout)]),
        (
            "prepare",
            [
                "--source-checkout",
                str(checkout),
                "--output",
                str(raw_root / "verification/dry-prepare"),
            ],
        ),
        ("evidence", []),
    ):
        base = [str(args.cli), command]
        if command == "evidence":
            base.append(str(raw_root / "verification/dry-prepare"))
        else:
            base.extend(["--config", str(path), *extra])
        checked = _command_json(base, cwd=raw_root)
        write_new(raw_root / "verification" / f"installed-{command}.json", checked)
    freeze = {
        "schema": FREEZE_SCHEMA,
        "preallocation_sha256": PREALLOCATION_SHA256,
        "commit": commit,
        "tree": tree,
        "product_sources": sources,
        "checkout_selected_files": source.files,
        "overlay_sha256": binding["overlay"]["sha256"],
        "native_python_sha256": sha256_file(Path(resources["--native-python"])),
        "asset_manifest_sha256": asset_sha,
        "resource_receipt_sha256": sha256_file(args.resources_from),
        "runtime_cpu_receipt_sha256": sha256_file(raw_root / "verification/r545-cpu.json"),
        "space": space,
        "history": history,
        "history_roots": [str(path) for path in history_roots],
        "slots": slots,
        "staging": SUCCESSOR_STAGE,
        "dry_prepare": _dry_prepare_proof(raw_root),
    } | package
    verify_frozen_sources(checkout, freeze)
    receipt = raw_root / "freeze-receipt.json"
    write_new(receipt, freeze)
    print(
        json.dumps(
            {
                "freeze_sha256": sha256_file(receipt),
                "preallocation_sha256": PREALLOCATION_SHA256,
                "commit": commit,
                "tree": tree,
                "product_sources": len(sources),
                "history": history,
                "release": "STAGED_AWAITING_SEPARATE_LAUNCH",
            }
        )
    )
    return 0


def _contained_stops(row: dict[str, Any]) -> bool:
    if (
        row["audit_status"] != "VERIFIED"
        or "signal" not in row
        or "wrapper_stop_reason" not in row
        or row.get("signal") is not None
        or row.get("wrapper_stop_reason") is not None
        or row["physical"]["safety_violation"] is not False
    ):
        return False
    if row["component_success"] is True and row["terminal_reason"] is None:
        expected = 0
    elif (
        row["component_success"] is False and row["terminal_reason"] in RECOGNIZED_PROTECTIVE_STOPS
    ):
        expected = 2
    else:
        return False
    codes = (row.get("returncode"), row.get("wrapper_exit_code"), row.get("episode_exit_code"))
    return all(type(code) is int and code == expected for code in codes)


def _initialization_successor_allowed(row: dict[str, Any], successor: str, freeze_sha: str) -> bool:
    proof = row.get("initialization_stop_proof", {})
    counters = row.get("observed_counters", {})
    return (
        row.get("id") == INITIALIZATION_STOP_PREDECESSOR
        and row.get("seed") == 2026111803
        and successor == INITIALIZATION_STOP_SUCCESSOR
        and freeze_sha == INITIALIZATION_STOP_FREEZE_SHA256
        and row.get("manifest_sha256") == INITIALIZATION_STOP_MANIFEST_SHA256
        and row.get("audit_status") == "VERIFIED"
        and row.get("worker_status") == "FAILED"
        and row.get("job_id") == "job-8d993c966b2942bc"
        and row.get("episode_id") == "9f89e8c7f1ad4f72b5c0890f3df3a41b"
        and row.get("terminal_reason") == "ValueError"
        and row.get("component_success") is False
        and row.get("physical_success") is False
        and row.get("physical", {}).get("safety_violation") is False
        and row.get("attempted_actions") == 1
        and row.get("executed_actions") == 0
        and row.get("command_continuity", {}).get("accepted_joint_targets") == 0
        and all(
            type(row.get(key)) is int and row[key] == 2
            for key in ("returncode", "wrapper_exit_code", "episode_exit_code")
        )
        and "signal" in row
        and row["signal"] is None
        and "wrapper_stop_reason" in row
        and row["wrapper_stop_reason"] is None
        and isinstance(counters, dict)
        and counters.get("cloud_request_reservations") == 1
        and counters.get("cloud_requests") == 1
        and counters.get("local_generations") == 4
        and counters.get("local_generations_completed") == 4
        and counters.get("model_loads") == 1
        and counters.get("usage", {}).get("total_tokens") == 709
        and "billed_cost" in counters
        and counters["billed_cost"] is None
        and proof.get("proof_sha256") == INITIALIZATION_STOP_PROOF_SHA256
        and proof.get("replayed_exception")
        == "servo initial target/registered marker identity unavailable"
        and proof.get("terminal_worker_sqlite")
        == {
            "status": "FAILED",
            "attempt": 1,
            "lease_released": True,
        }
    )


def _verify_gpu_release(lock_path: Path) -> None:
    with lock_path.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        running = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
            text=True,
        )
        require(not running.strip(), "GPU compute occupancy persists after 1803")


def _require_registered_locations(checkout: Path, raw_root: Path) -> None:
    require(
        checkout == REGISTERED_CHECKOUT and raw_root == REGISTERED_RAW_ROOT,
        "checkout and output must be the registered batch locations",
    )


def _launch_locked(args: argparse.Namespace, raw_root: Path, checkout: Path) -> int:
    _require_registered_locations(checkout, raw_root)
    allocation = read_allocation(ROUND / "preallocation.json")
    freeze = read_freeze(raw_root / "freeze-receipt.json", args.freeze_sha256)
    verify_frozen_sources(checkout, freeze)
    require(_git(checkout, "rev-parse", "HEAD").strip() == freeze["commit"], "launch HEAD drift")
    if freeze["commit"] == SUCCESSOR_COMMIT:
        _validate_successor_stage(raw_root, args.freeze_sha256)
    resources = _resources(args.resources_from, allocation)
    _check_free_space(raw_root, Path(resources["--model-directory"]))
    require(
        sha256_file(args.cli) == freeze["installed_launcher_sha256"]
        and sha256_file(Path(resources["--native-python"])) == freeze["native_python_sha256"]
        and sha256_file(Path(resources["--asset-manifest"])) == freeze["asset_manifest_sha256"],
        "launcher/runtime/manifest differs from freeze",
    )
    slots = allocation["episodes"]
    check_slot_directories(raw_root / "native", slots)
    exact_predecessor = False
    used_cloud = used_local = 0
    for slot in slots:
        if slot["seed"] == args.seed:
            break
        previous = audit_slot(raw_root, checkout, freeze, args.freeze_sha256, slot)
        gate = _initialization_successor_allowed(
            previous,
            f"fresh-{args.seed}",
            args.freeze_sha256,
        )
        require(gate or _contained_stops(previous), "preceding slot is unresolved or out of policy")
        exact_predecessor |= gate
        used_cloud += previous["occupancy"]["cloud"]
        used_local += previous["occupancy"]["local"]
    else:
        raise ValueError("unknown slot seed")
    identity = slot["id"]
    cfg = slot_config_path(raw_root, freeze, identity)
    expected = freeze["slots"][identity]
    require(sha256_file(cfg) == expected["config_sha256"], "slot config changed")
    asset_sha = freeze["asset_manifest_sha256"]
    require(
        _role_config(raw_root, resources, load_config(cfg), asset_sha)
        == expected["role_binding_sha256"],
        "current role differs from frozen slot",
    )
    output = raw_root / "native" / identity
    receipts = raw_root / "receipts"
    start_path = receipts / f"{identity}-started.json"
    end_path = receipts / f"{identity}-finished.json"
    stdout = receipts / f"{identity}.stdout"
    stderr = receipts / f"{identity}.stderr"
    require(
        not any(os.path.lexists(path) for path in (output, start_path, end_path, stdout, stderr)),
        "slot already claimed or contains raw evidence",
    )
    require(used_cloud + 1 <= 4 and used_local + 4 <= 16, "batch model budget would be exceeded")
    if exact_predecessor:
        _verify_gpu_release(Path(resources["--gpu-lock"]))
    history_receipt = None
    if slot == slots[0]:
        history = check_history(
            tuple(Path(path) for path in freeze["history_roots"]),
            slots,
            successor_dry_sha=freeze.get("dry_prepare", {}).get("assignment_sha256"),
        )
        history_receipt = raw_root / "verification" / f"prelaunch-history-{time.time_ns()}.json"
        write_new(history_receipt, history)
    binding = {
        "id": identity,
        "seed": slot["seed"],
        "freeze_sha256": args.freeze_sha256,
        "preallocation_sha256": PREALLOCATION_SHA256,
        "config_sha256": expected["config_sha256"],
    }
    command = [
        str(args.cli),
        "run-simulation",
        "--config",
        str(cfg),
        "--source-checkout",
        str(checkout),
        *(item for row in resources.items() for item in row),
        "--allow-paid",
        "--output",
        str(output),
    ]
    started = datetime.now(UTC).isoformat()
    monotonic = time.monotonic()
    write_new(
        start_path,
        binding
        | {
            "started_at": started,
            "attempt": 1,
            "launcher": str(args.cli),
            **(
                {"verified_predecessor_gate": INITIALIZATION_STOP_PROOF_SHA256}
                if exact_predecessor
                else {}
            ),
            "immediate_prelaunch_history_sha256": (
                None if history_receipt is None else sha256_file(history_receipt)
            ),
            "model_quota": {"cloud": 1, "local_generations": 4, "model_loads": 1, "retries": 0},
        },
    )
    print(json.dumps(binding | {"status": "BEGIN", "started_at": started}), flush=True)
    with stdout.open("xb") as output_stream, stderr.open("xb") as error_stream:
        completed = subprocess.run(
            command,
            cwd=raw_root,
            env=_environment(launch=True),
            stdout=output_stream,
            stderr=error_stream,
            check=False,
        )
    finished = datetime.now(UTC).isoformat()
    write_new(
        end_path,
        binding
        | {
            "started_sha256": sha256_file(start_path),
            "finished_at": finished,
            "wall_s": time.monotonic() - monotonic,
            "returncode": completed.returncode,
            "stdout_sha256": sha256_file(stdout),
            "stderr_sha256": sha256_file(stderr),
        },
    )
    try:
        row = audit_slot(raw_root, checkout, freeze, args.freeze_sha256, slot)
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        row = binding | {"audit_status": "AUDIT_REJECTED", "reason": str(exc)}
    write_new(raw_root / "verification" / f"{identity}.json", row)
    print(
        json.dumps(
            {
                key: row.get(key)
                for key in (
                    "id",
                    "audit_status",
                    "worker_status",
                    "physical_success",
                    "terminal_reason",
                    "reason",
                )
            }
        ),
        flush=True,
    )
    return 0 if _contained_stops(row) else 2


def launch(args: argparse.Namespace) -> int:
    require(args.allow_paid, "explicit --allow-paid is required for a preregistered slot")
    root = args.raw_root.resolve(strict=True)
    with (root / ".batch-launch.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _launch_locked(args, root, args.checkout.resolve(strict=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, function in (("prepare", prepare), ("launch", launch)):
        sub = subparsers.add_parser(name)
        sub.set_defaults(operation=function)
        sub.add_argument("--checkout", type=Path, default=ROOT)
        sub.add_argument("--raw-root", type=Path, required=True)
        sub.add_argument("--cli", type=Path, required=True)
        sub.add_argument("--resources-from", type=Path, required=True)
    prepare_parser = subparsers.choices["prepare"]
    prepare_parser.add_argument("--wheel", type=Path, required=True)
    launch_parser = subparsers.choices["launch"]
    launch_parser.add_argument("--seed", type=int, required=True)
    launch_parser.add_argument("--freeze-sha256", required=True)
    launch_parser.add_argument("--allow-paid", action="store_true")
    selection = subparsers.add_parser("activate")
    selection.set_defaults(operation=activate)
    selection.add_argument("--checkout", type=Path, default=REGISTERED_CHECKOUT)
    selection.add_argument("--raw-root", type=Path, required=True)
    selection.add_argument("--freeze-sha256", required=True)
    args = parser.parse_args()
    return int(args.operation(args))


if __name__ == "__main__":
    raise SystemExit(main())
