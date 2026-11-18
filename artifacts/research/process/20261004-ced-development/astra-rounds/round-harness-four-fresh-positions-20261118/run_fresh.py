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
    PREALLOCATION_SHA256,
    ROOT,
    ROUND,
    audit_slot,
    check_slot_directories,
    read,
    read_allocation,
    read_freeze,
    require,
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
from cloud_edge_robot_arm.research.sol_molmo_single_episode import (
    create_molmo_opencv_bridge,
    scene_assignment,
    selected_sol_service,
)
from cloud_edge_robot_arm.vision.molmo_pointing import _verify_assets
from cloud_edge_robot_arm.vision.role_models import configuration_hash

PRODUCTION_PATHS = ("pyproject.toml", "src", "assets", "configs", "scripts", OVERLAY)
REGISTERED_CHECKOUT = Path("/tmp/bigsmall-harness-verified-20261118")
REGISTERED_RAW_ROOT = Path(
    "/home/ningyd/文档/ChatGPT/BIGsmall/cache/worktrees/harness-candidate-20261118/"
    "experiments/results/phase9/harness-four-fresh-20261118"
)
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
) -> dict[str, Any]:
    """Check archived requests and preallocations before the first launch."""
    proposed = {row["seed"] for row in slots}
    poses = {tuple([*row["object_position_m"], row["object_yaw_rad"]]) for row in slots}
    checked = []
    conflicts = []
    distinct = set()
    for worktree in worktrees:
        for subdir in ("experiments", "results", "artifacts/research/process"):
            directory = worktree / subdir
            if not directory.is_dir():
                continue
            for name in ("scene-assignment.json", "scene-application.json", "preallocation.json"):
                for path in directory.rglob(name):
                    resolved = path.resolve()
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
    }


def _verify_installed_wheel(
    cli: Path, wheel: Path, sources: dict[str, str],
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


def prepare(args: argparse.Namespace) -> int:
    checkout = args.checkout.resolve(strict=True)
    raw_root = args.raw_root.resolve()
    _require_registered_locations(checkout, raw_root)
    require(not raw_root.exists(), "batch root already exists")
    require(
        not any(raw_root.is_relative_to(checkout / path) for path in PRODUCTION_PATHS),
        "batch output overlaps product sources",
    )
    allocation = read_allocation(ROUND / "preallocation.json")
    resources = _resources(args.resources_from, allocation)
    dirty = _git(
        checkout, "status", "--porcelain", "--untracked-files=all", "--", *PRODUCTION_PATHS
    )
    require(not dirty, "production source must be committed before the four-slot freeze")
    commit = _git(checkout, "rev-parse", "HEAD").strip()
    tree = _git(checkout, "rev-parse", "HEAD^{tree}").strip()
    files = _git(checkout, "ls-tree", "-r", "--name-only", "-z", commit, "--", *PRODUCTION_PATHS)
    sources = {name: sha256_file(checkout / name) for name in files.split("\0") if name}
    history_roots = tuple(dict.fromkeys(path.resolve() for path in [checkout, *args.history_root]))
    history = check_history(history_roots, allocation["episodes"])
    raw_root.parent.mkdir(parents=True, exist_ok=True)
    space = _check_free_space(raw_root.parent, Path(resources["--model-directory"]))
    raw_root.mkdir(parents=True, exist_ok=False)
    for name in ("configs", "receipts", "native", "verification"):
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
        row["component_success"] is False
        and row["terminal_reason"] in RECOGNIZED_PROTECTIVE_STOPS
    ):
        expected = 2
    else:
        return False
    codes = (row.get("returncode"), row.get("wrapper_exit_code"), row.get("episode_exit_code"))
    return all(type(code) is int and code == expected for code in codes)


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
    for slot in slots:
        if slot["seed"] == args.seed:
            break
        previous = audit_slot(raw_root, checkout, freeze, args.freeze_sha256, slot)
        require(_contained_stops(previous), "preceding slot is unresolved or out of policy")
    else:
        raise ValueError("unknown slot seed")
    identity = slot["id"]
    cfg = raw_root / "configs" / f"{identity}.json"
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
    history_receipt = None
    if slot == slots[0]:
        history = check_history(tuple(Path(path) for path in freeze["history_roots"]), slots)
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
    prepare_parser.add_argument("--history-root", type=Path, action="append", default=[])
    launch_parser = subparsers.choices["launch"]
    launch_parser.add_argument("--seed", type=int, required=True)
    launch_parser.add_argument("--freeze-sha256", required=True)
    launch_parser.add_argument("--allow-paid", action="store_true")
    args = parser.parse_args()
    return int(args.operation(args))


if __name__ == "__main__":
    raise SystemExit(main())
