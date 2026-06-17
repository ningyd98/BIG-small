from __future__ import annotations

import json
import os
import platform
import resource
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

PHASE9_2_REQUIRED_METRICS = (
    "success_rate",
    "completion_time_ms",
    "joint_tracking_rmse",
    "tcp_position_error_m",
    "illegal_collision_count",
    "contact_event_count",
    "emergency_stop_post_command_count",
    "cloud_call_count",
    "detection_latency_ms",
    "recovery_latency_ms",
    "final_state",
    "auto_mode_selection",
    "physics_steps",
    "real_time_factor",
    "cpu_usage",
    "peak_ram_mb",
    "peak_vram_mb",
)

PHASE9_2_SCENARIOS = (
    "S01_NORMAL_STATIC",
    "S16_PAYLOAD_MASS_VARIATION",
    "S17_CONTACT_FRICTION_VARIATION",
    "S19_CAMERA_NOISE_AND_OCCLUSION",
    "S22_COLLISION_NEAR_MISS",
    "S14_EMERGENCY_STOP",
)

FORBIDDEN_ISAAC_LOG_MARKERS = (
    "Traceback",
    "Fatal",
    "Segmentation fault",
    "CUDA error",
    "Vulkan fatal error",
)


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str

    def to_jsonable(self) -> dict[str, object]:
        return {
            "argv": _sanitize_argv(self.argv),
            "exit_code": self.exit_code,
            "stdout": _sanitize_text(self.stdout[-4000:]),
            "stderr": _sanitize_text(self.stderr[-4000:]),
        }


@dataclass(frozen=True)
class Phase92RuntimeConfig:
    mode: Literal["standalone", "container"]
    repo_root: Path
    output_dir: Path
    isaac_sim_root: Path | None = None
    container_image: str = "nvcr.io/nvidia/isaac-sim:6.0.0"
    container_digest: str = ""
    accept_eula: bool = True
    privacy_consent: bool = False
    source: Literal["env", "auto_detected"] = "env"


@dataclass(frozen=True)
class RuntimeCommand:
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    image_digest: str = ""


Runner = Callable[[list[str], float], CommandResult]


def build_isaac_runtime_command(
    config: Phase92RuntimeConfig,
    app_args: list[str] | None = None,
) -> RuntimeCommand:
    extra_args = app_args or []
    if config.mode == "standalone":
        if config.isaac_sim_root is None:
            raise ValueError("isaac_sim_root is required for standalone Isaac runtime")
        executable = _standalone_python_executable(config.isaac_sim_root)
        env = {
            "ISAAC_SIM_ROOT": str(config.isaac_sim_root),
            "ISAAC_RUNTIME_MODE": "standalone",
        }
        argv = [
            str(executable),
            "scripts/phase9/isaac_standalone_app.py",
            "--headless",
            *extra_args,
        ]
        return RuntimeCommand(argv=argv, env=env)
    if config.mode == "container":
        if config.container_image.endswith(":latest"):
            raise ValueError("Isaac container image must not use a floating latest tag")
        env_args = ["-e", "ACCEPT_EULA=Y"] if config.accept_eula else []
        if config.privacy_consent:
            env_args.extend(["-e", "PRIVACY_CONSENT=Y"])
        argv = [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "--network",
            "host",
            *env_args,
            "-v",
            f"{config.repo_root}:/workspace/BIG-small",
            "-v",
            f"{config.output_dir}:/workspace/BIG-small/artifacts/phase9_2/isaac",
            config.container_image,
            "/isaac-sim/python.sh",
            "/workspace/BIG-small/scripts/phase9/isaac_standalone_app.py",
            "--headless",
            *extra_args,
        ]
        return RuntimeCommand(argv=argv, image_digest=config.container_digest)
    raise ValueError(f"unsupported Isaac runtime mode: {config.mode}")


def collect_environment_compatibility(
    output_dir: Path,
    *,
    runner: Runner | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = runner or _run_command
    runtime_config = runtime_config_from_env(repo_root=Path("."), output_dir=output_dir)
    isaac_check_command = _isaac_checker_command(runtime_config)
    commands = {
        "nvidia_smi": run(
            [
                "bash",
                "-lc",
                "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader",
            ],
            20.0,
        ),
        "vulkan": run(["bash", "-lc", "vulkaninfo --summary"], 20.0),
        "isaac_checker": run(isaac_check_command, 240.0),
    }
    _write_command_log(output_dir / "nvidia_smi.txt", commands["nvidia_smi"])
    _write_command_log(output_dir / "vulkan_summary.txt", commands["vulkan"])
    _write_command_log(output_dir / "isaac_compatibility_checker.log", commands["isaac_checker"])

    blockers: list[str] = []
    if commands["nvidia_smi"].exit_code != 0:
        blockers.append("NVIDIA GPU is not visible")
    if commands["vulkan"].exit_code != 0:
        blockers.append("Vulkan runtime is not usable")
    if commands["isaac_checker"].exit_code != 0:
        blockers.append("Isaac Sim compatibility checker failed")
    if runtime_config is None and os.environ.get("ISAAC_RUNTIME_MODE") != "container":
        blockers.append("ISAAC_SIM_ROOT is not set")

    details = {
        "os": platform.platform(),
        "cpu": _safe_command("lscpu | sed -n 's/Model name:[[:space:]]*//p' | head -1"),
        "memory": _safe_command("free -h | awk '/Mem:/ {print $2}'"),
        "disk_available": _safe_command("df -h . | awk 'NR==2 {print $4}'"),
        "gpu": commands["nvidia_smi"].stdout.strip(),
        "cuda_visible": commands["nvidia_smi"].exit_code == 0,
        "vulkan_available": commands["vulkan"].exit_code == 0,
        "display": os.environ.get("DISPLAY", ""),
        "egl": os.environ.get("EGL_PLATFORM", ""),
        "isaac_sim_root": _sanitize_text(
            str(runtime_config.isaac_sim_root)
            if runtime_config is not None
            and runtime_config.mode == "standalone"
            and runtime_config.isaac_sim_root is not None
            else os.environ.get("ISAAC_SIM_ROOT", "")
        ),
        "isaac_python_path": _sanitize_text(_isaac_python_path(runtime_config)),
        "isaac_container_image": runtime_config.container_image
        if runtime_config is not None and runtime_config.mode == "container"
        else "",
        "isaac_container_digest": runtime_config.container_digest
        if runtime_config is not None and runtime_config.mode == "container"
        else "",
        "isaac_runtime_mode": runtime_config.mode if runtime_config is not None else "",
        "isaac_runtime_source": runtime_config.source if runtime_config is not None else "",
        "ros_distro": os.environ.get("ROS_DISTRO", ""),
        "rmw_implementation": os.environ.get("RMW_IMPLEMENTATION", ""),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", ""),
    }
    payload: dict[str, object] = {
        "status": "BLOCKED_BY_ENV" if blockers else "ISAAC_ENV_READY",
        "validation_claimed": False,
        "blockers": blockers,
        "details": details,
        "commands": {name: result.to_jsonable() for name, result in commands.items()},
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (output_dir / "compatibility_report.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_environment_markdown(output_dir / "compatibility_report.md", payload)
    return payload


def runtime_config_from_env(
    *,
    repo_root: Path = Path("."),
    output_dir: Path = Path("artifacts/phase9_2/isaac"),
) -> Phase92RuntimeConfig | None:
    mode = os.environ.get("ISAAC_RUNTIME_MODE", "standalone")
    if mode == "container":
        return Phase92RuntimeConfig(
            mode="container",
            repo_root=repo_root,
            output_dir=output_dir,
            container_image=os.environ.get(
                "ISAAC_CONTAINER_IMAGE", "nvcr.io/nvidia/isaac-sim:6.0.0"
            ),
            container_digest=os.environ.get("ISAAC_CONTAINER_DIGEST", ""),
            privacy_consent=os.environ.get("ISAAC_PRIVACY_CONSENT") == "Y",
            source="env",
        )
    root = os.environ.get("ISAAC_SIM_ROOT", "")
    source: Literal["env", "auto_detected"] = "env"
    if not root:
        if os.environ.get("PHASE9_2_DISABLE_ISAAC_AUTO_DETECT") == "1":
            return None
        detected = _discover_local_isaac_runtime()
        if detected is None:
            return None
        root = str(detected)
        source = "auto_detected"
    return Phase92RuntimeConfig(
        mode="standalone",
        repo_root=repo_root,
        output_dir=output_dir,
        isaac_sim_root=Path(root),
        source=source,
    )


def _isaac_checker_command(config: Phase92RuntimeConfig | None) -> list[str]:
    if config is None:
        return ["python", "scripts/phase9/isaac_standalone_app.py", "--check-imports"]
    if config.mode == "standalone":
        if config.isaac_sim_root is None:
            return ["python", "scripts/phase9/isaac_standalone_app.py", "--check-imports"]
        return [
            str(_standalone_python_executable(config.isaac_sim_root)),
            "scripts/phase9/isaac_standalone_app.py",
            "--check-imports",
        ]
    return build_isaac_runtime_command(config, ["--check-imports"]).argv


def _isaac_python_path(config: Phase92RuntimeConfig | None) -> str:
    if config is None:
        return ""
    if config.mode == "standalone" and config.isaac_sim_root is not None:
        return str(_standalone_python_executable(config.isaac_sim_root))
    if config.mode == "container":
        return "/isaac-sim/python.sh"
    return ""


def _standalone_python_executable(root: Path) -> Path:
    python_sh = root / "python.sh"
    if python_sh.exists():
        return python_sh
    venv_python = root / "bin" / "python"
    if root.exists() and venv_python.exists():
        return venv_python
    return python_sh


def _discover_local_isaac_runtime() -> Path | None:
    home = Path.home()
    candidates: list[Path] = []
    venv_root = home / ".venvs"
    if venv_root.exists():
        candidates.extend(sorted(venv_root.glob("bigsmall-isaacsim-*"), reverse=True))
        candidates.extend(sorted(venv_root.glob("isaacsim-*"), reverse=True))
    candidates.extend(
        [
            home / "isaac-sim",
            home / "isaacsim",
            home / "NVIDIA" / "isaac-sim",
        ]
    )
    for candidate in candidates:
        if (candidate / "python.sh").exists() or (candidate / "bin" / "python").exists():
            return candidate
    return None


def run_isaac_smoke_runtime(
    output_dir: Path,
    *,
    config: Phase92RuntimeConfig,
    runner: Runner | None = None,
    timeout_s: float = 600.0,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_isaac_runtime_command(
        config,
        [
            "--smoke",
            "--output",
            str(output_dir),
        ],
    )
    run = runner or _run_command
    result = run(command.argv, timeout_s)
    (output_dir / "process_stdout.log").write_text(
        _sanitize_text(result.stdout) + ("\n" if result.stdout else ""),
        encoding="utf-8",
    )
    (output_dir / "process_stderr.log").write_text(
        _sanitize_text(result.stderr) + ("\n" if result.stderr else ""),
        encoding="utf-8",
    )
    (output_dir / "isaac_commands.log").write_text(
        "\n".join(
            [
                f"$ {' '.join(_sanitize_argv(result.argv))}",
                f"exit_code={result.exit_code}",
                f"runtime_mode={config.mode}",
                f"image_digest={command.image_digest}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return verify_isaac_smoke_evidence(output_dir)


def verify_isaac_smoke_evidence(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = _load_json(output_dir / "isaac_smoke_evidence.json")
    blockers: list[str] = []
    if not evidence:
        blockers.append("isaac_smoke_evidence.json is missing")
    if evidence.get("artifact_provenance_complete") is not True:
        blockers.append("artifact provenance is incomplete")
    if evidence.get("validation_claimed") is not True:
        blockers.append("validation_claimed is not true")
    if not evidence.get("run_id") or not isinstance(evidence.get("process_provenance"), dict):
        blockers.append("process provenance is missing")
    if evidence.get("stage_loaded") is not True:
        blockers.append("stage was not loaded")
    if int(evidence.get("physics_steps", 0) or 0) <= 0:
        blockers.append("physics steps did not advance")
    if evidence.get("robot_state_sample") is not True:
        blockers.append("robot state sample is missing")
    sensor_samples = evidence.get("sensor_samples", {})
    if not isinstance(sensor_samples, dict):
        sensor_samples = {}
    for sensor_name in ("rgb", "depth", "contact"):
        sample = sensor_samples.get(sensor_name, {})
        if not isinstance(sample, dict) or sample.get("available") is not True:
            blockers.append(f"{sensor_name} sensor sample is missing")
    if not _operation_success(evidence.get("reset_result")):
        blockers.append("reset result is missing or failed")
    if not _operation_success(evidence.get("emergency_stop_result")):
        blockers.append("emergency stop result is missing or failed")
    if not _operation_success(evidence.get("graceful_shutdown_result")):
        blockers.append("graceful shutdown result is missing or failed")
    blockers.extend(_forbidden_log_blockers(output_dir))

    status = "ISAAC_SMOKE_VALIDATED" if not blockers else "INCOMPLETE"
    payload: dict[str, object] = {
        "status": status,
        "validation_claimed": status == "ISAAC_SMOKE_VALIDATED",
        "real_isaac_run_count": 1 if status == "ISAAC_SMOKE_VALIDATED" else 0,
        "blockers": blockers,
        "runtime_mode": evidence.get("runtime_mode", ""),
        "isaac_sim_version": evidence.get("isaac_sim_version", ""),
        "artifact_provenance_complete": not blockers,
    }
    (output_dir / "isaac_verification.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def verify_cross_backend_artifacts(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for source_name in ("mujoco_runs.jsonl", "isaac_runs.jsonl"):
        source_path = output_dir / source_name
        if not source_path.exists():
            source_path.write_text("", encoding="utf-8")
    mujoco_runs = _load_jsonl(output_dir / "mujoco_runs.jsonl")
    isaac_runs = _load_jsonl(output_dir / "isaac_runs.jsonl")
    blockers: list[str] = []
    if not mujoco_runs:
        blockers.append("MuJoCo runs are missing")
    if not isaac_runs:
        blockers.append("Isaac runs are missing")
    blockers.extend(_validate_backend_runs(mujoco_runs, expected_backend="mujoco"))
    blockers.extend(_validate_backend_runs(isaac_runs, expected_backend="isaac"))
    mujoco_pairs = {(str(row.get("scenario_id")), int(row.get("seed", -1))) for row in mujoco_runs}
    isaac_pairs = {(str(row.get("scenario_id")), int(row.get("seed", -2))) for row in isaac_runs}
    if mujoco_pairs != isaac_pairs:
        blockers.append("scenario/seed pairing mismatch")
    if _result_hashes_are_static([*mujoco_runs, *isaac_runs]):
        blockers.append("result hashes are static")

    paired = _paired_rows(mujoco_runs, isaac_runs) if not blockers else []
    metric_deltas = _metric_deltas(paired) if paired else {}
    if paired and not set(PHASE9_2_REQUIRED_METRICS).issubset(metric_deltas):
        blockers.append("cross-backend metric completeness failed")

    status = "CROSS_BACKEND_VALIDATED" if not blockers else "REJECTED"
    _write_cross_backend_outputs(output_dir, paired, metric_deltas, status, blockers)
    payload: dict[str, object] = {
        "status": status,
        "validation_claimed": status == "CROSS_BACKEND_VALIDATED",
        "artifact_provenance_complete": status == "CROSS_BACKEND_VALIDATED",
        "blockers": blockers,
        "metric_deltas": metric_deltas,
        "paired_run_count": len(paired),
    }
    (output_dir / "cross_backend_verification.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def run_phase9_2_paired_experiments(
    output_dir: Path,
    *,
    config: Phase92RuntimeConfig,
    scenarios: tuple[str, ...] = PHASE9_2_SCENARIOS,
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
) -> dict[str, object]:
    from cloud_edge_robot_arm.simulation.evaluation.metrics import (
        run_isaac_physical_trial,
        run_mujoco_physical_trial,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    mujoco_rows: list[dict[str, object]] = []
    isaac_rows: list[dict[str, object]] = []
    isaac_process_argv = build_isaac_runtime_command(
        config,
        ["--output", str(output_dir / "isaac_process")],
    ).argv
    for scenario_id in scenarios:
        for seed in seeds:
            mujoco_start = time.perf_counter()
            mujoco_result = run_mujoco_physical_trial(scenario_id, seed=seed)
            mujoco_rows.append(
                _phase9_2_backend_row(
                    backend_name="mujoco",
                    scenario_id=scenario_id,
                    seed=seed,
                    metrics=mujoco_result.metrics,
                    result_hash=mujoco_result.result_hash,
                    wall_runtime_s=time.perf_counter() - mujoco_start,
                )
            )
            isaac_start = time.perf_counter()
            try:
                isaac_result = run_isaac_physical_trial(
                    scenario_id,
                    seed=seed,
                    process_argv=isaac_process_argv,
                )
            except Exception as exc:  # noqa: BLE001 - failed runs must remain auditable.
                isaac_rows.append(
                    _phase9_2_failed_backend_row(
                        backend_name="isaac",
                        scenario_id=scenario_id,
                        seed=seed,
                        wall_runtime_s=time.perf_counter() - isaac_start,
                        failure_reason=f"{type(exc).__name__}: {exc}",
                    )
                )
            else:
                isaac_rows.append(
                    _phase9_2_backend_row(
                        backend_name="isaac",
                        scenario_id=scenario_id,
                        seed=seed,
                        metrics=isaac_result.metrics,
                        result_hash=isaac_result.result_hash,
                        wall_runtime_s=time.perf_counter() - isaac_start,
                    )
                )
    _write_jsonl(output_dir / "mujoco_runs.jsonl", mujoco_rows)
    _write_jsonl(output_dir / "isaac_runs.jsonl", isaac_rows)
    return verify_cross_backend_artifacts(output_dir)


def phase9_2_status(summary: dict[str, object]) -> str:
    required = {
        "ros2_status": "ROS2_INTEGRATION_VALIDATED",
        "moveit_status": "MOVEIT_SAFETY_VALIDATED",
        "isaac_status": "ISAAC_SMOKE_VALIDATED",
        "isaac_benchmark_status": "PASSED",
        "cross_backend_status": "CROSS_BACKEND_VALIDATED",
        "phase9_1_status": "PHASE9_1_ACCEPTED",
        "safety_pressure_status": "PASSED",
    }
    if (
        all(summary.get(key) == value for key, value in required.items())
        and summary.get("artifact_provenance_complete") is True
    ):
        return "PHASE9_2_ACCEPTED"
    return "PHASE9_2_REJECTED"


def verify_phase9_2_acceptance(
    output_dir: Path,
    *,
    artifacts_root: Path = Path("artifacts"),
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    phase9_1 = _load_json(artifacts_root / "phase9_1" / "phase9_1_summary.json")
    components = phase9_1.get("components", {})
    if not isinstance(components, dict):
        components = {}
    ros2 = components.get("ros2", {})
    moveit = components.get("moveit", {})
    safety_pressure = phase9_1.get("safety_pressure", {})
    isaac_smoke = _load_json(artifacts_root / "phase9_2" / "isaac" / "isaac_verification.json")
    isaac_benchmark = _load_json(artifacts_root / "phase9_2" / "isaac_benchmark" / "summary.json")
    cross_backend = _load_json(
        artifacts_root / "phase9_2" / "cross_backend" / "cross_backend_verification.json"
    )
    source_phase9_1_status = str(phase9_1.get("status", ""))
    effective_phase9_1_status = _effective_phase9_1_status(
        source_status=source_phase9_1_status,
        ros2_status=_status_from_component(ros2),
        moveit_status=_status_from_component(moveit),
        safety_pressure_status=str(safety_pressure.get("status", "")),
        isaac_smoke=isaac_smoke,
        isaac_benchmark=isaac_benchmark,
        cross_backend=cross_backend,
    )
    summary: dict[str, object] = {
        "ros2_status": _status_from_component(ros2),
        "moveit_status": _status_from_component(moveit),
        "isaac_status": str(isaac_smoke.get("status", "")),
        "isaac_benchmark_status": str(
            isaac_benchmark.get("benchmark_status", isaac_benchmark.get("status", ""))
        ),
        "cross_backend_status": str(cross_backend.get("status", "")),
        "phase9_1_source_status": source_phase9_1_status,
        "phase9_1_status": effective_phase9_1_status,
        "safety_pressure_status": str(safety_pressure.get("status", "")),
        "artifact_provenance_complete": (
            effective_phase9_1_status == "PHASE9_1_ACCEPTED"
            and _status_from_component(ros2) == "ROS2_INTEGRATION_VALIDATED"
            and _status_from_component(moveit) == "MOVEIT_SAFETY_VALIDATED"
            and isaac_smoke.get("validation_claimed") is True
            and isaac_smoke.get("artifact_provenance_complete") is True
            and isaac_benchmark.get("validation_claimed") is True
            and cross_backend.get("validation_claimed") is True
            and cross_backend.get("artifact_provenance_complete") is True
        ),
        "artifact_paths": {
            "phase9_1": str(artifacts_root / "phase9_1" / "phase9_1_summary.json"),
            "isaac_smoke": str(artifacts_root / "phase9_2" / "isaac" / "isaac_verification.json"),
            "isaac_benchmark": str(
                artifacts_root / "phase9_2" / "isaac_benchmark" / "summary.json"
            ),
            "cross_backend": str(
                artifacts_root / "phase9_2" / "cross_backend" / "cross_backend_verification.json"
            ),
        },
    }
    status = phase9_2_status(summary)
    blockers = _phase9_2_blockers(summary) if status != "PHASE9_2_ACCEPTED" else []
    payload = {
        "status": status,
        "validation_claimed": status == "PHASE9_2_ACCEPTED",
        **summary,
        "blockers": blockers,
    }
    (output_dir / "phase9_2_summary.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def _effective_phase9_1_status(
    *,
    source_status: str,
    ros2_status: str,
    moveit_status: str,
    safety_pressure_status: str,
    isaac_smoke: dict[str, object],
    isaac_benchmark: dict[str, object],
    cross_backend: dict[str, object],
) -> str:
    if source_status == "PHASE9_1_ACCEPTED":
        return source_status
    phase9_2_completes_phase9_1 = (
        source_status == "PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK"
        and ros2_status == "ROS2_INTEGRATION_VALIDATED"
        and moveit_status == "MOVEIT_SAFETY_VALIDATED"
        and safety_pressure_status == "PASSED"
        and isaac_smoke.get("status") == "ISAAC_SMOKE_VALIDATED"
        and isaac_smoke.get("validation_claimed") is True
        and isaac_benchmark.get("benchmark_status") == "PASSED"
        and isaac_benchmark.get("validation_claimed") is True
        and cross_backend.get("status") == "CROSS_BACKEND_VALIDATED"
        and cross_backend.get("validation_claimed") is True
    )
    return "PHASE9_1_ACCEPTED" if phase9_2_completes_phase9_1 else source_status


def _run_command(argv: list[str], timeout: float = 20.0) -> CommandResult:
    try:
        result = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(argv=argv, exit_code=124, stdout="", stderr=str(exc))
    return CommandResult(
        argv=argv,
        exit_code=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )


def _status_from_component(component: object) -> str:
    if isinstance(component, dict):
        return str(component.get("status", ""))
    return ""


def _phase9_2_blockers(summary: dict[str, object]) -> list[str]:
    expected = {
        "ros2_status": "ROS2_INTEGRATION_VALIDATED",
        "moveit_status": "MOVEIT_SAFETY_VALIDATED",
        "isaac_status": "ISAAC_SMOKE_VALIDATED",
        "isaac_benchmark_status": "PASSED",
        "cross_backend_status": "CROSS_BACKEND_VALIDATED",
        "phase9_1_status": "PHASE9_1_ACCEPTED",
        "safety_pressure_status": "PASSED",
    }
    blockers = [
        f"{key}={summary.get(key, '')} expected {value}"
        for key, value in expected.items()
        if summary.get(key) != value
    ]
    if summary.get("artifact_provenance_complete") is not True:
        blockers.append("artifact provenance is incomplete")
    return blockers


def _safe_command(command: str) -> str:
    result = _run_command(["bash", "-lc", command], timeout=5.0)
    return result.stdout if result.exit_code == 0 else ""


def _write_command_log(path: Path, result: CommandResult) -> None:
    path.write_text(
        "\n".join(
            [
                f"$ {' '.join(_sanitize_argv(result.argv))}",
                f"exit_code={result.exit_code}",
                "--- stdout ---",
                _sanitize_text(result.stdout) or "<empty>",
                "--- stderr ---",
                _sanitize_text(result.stderr) or "<empty>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_environment_markdown(path: Path, payload: dict[str, object]) -> None:
    raw_blockers = payload.get("blockers", [])
    blockers = raw_blockers if isinstance(raw_blockers, list) else []
    blocker_lines = "\n".join(f"- {blocker}" for blocker in blockers) or "- none"
    details = payload.get("details", {})
    detail_lines = ""
    if isinstance(details, dict):
        detail_lines = "\n".join(
            f"- `{key}`: {_markdown_value(value)}" for key, value in sorted(details.items())
        )
    path.write_text(
        f"# Phase 9.2 Compatibility Report\n\n"
        f"Status: `{payload['status']}`\n\n"
        f"## Blockers\n\n{blocker_lines}\n\n"
        f"## Details\n\n{detail_lines}\n",
        encoding="utf-8",
    )


def _markdown_value(value: object) -> str:
    text = str(value)
    return '""' if text == "" else text


def _operation_success(value: object) -> bool:
    return isinstance(value, dict) and value.get("success") is True


def _forbidden_log_blockers(output_dir: Path) -> list[str]:
    blockers: list[str] = []
    for log_name in ("process_stdout.log", "process_stderr.log"):
        log_path = output_dir / log_name
        if not log_path.exists():
            blockers.append(f"{log_name} is missing")
            continue
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_ISAAC_LOG_MARKERS:
            if marker in text:
                blockers.append(f"forbidden log marker in {log_name}: {marker}")
    return blockers


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} must contain JSON objects")
        rows.append(loaded)
    return rows


def _validate_backend_runs(rows: list[dict[str, Any]], *, expected_backend: str) -> list[str]:
    blockers: list[str] = []
    seen_run_ids: set[str] = set()
    for row in rows:
        if row.get("backend_name") != expected_backend:
            label = "Isaac" if expected_backend == "isaac" else "MuJoCo"
            blockers.append(f"{label} artifact backend identity mismatch")
        run_id = str(row.get("run_id", ""))
        if not run_id or run_id in seen_run_ids:
            blockers.append(f"{expected_backend} run_id is missing or duplicated")
        seen_run_ids.add(run_id)
        if row.get("validation_claimed") is not True:
            blockers.append(f"{expected_backend} validation_claimed is not true")
        for key in (
            "scenario_id",
            "seed",
            "process_provenance",
            "environment_provenance",
            "config_hash",
            "code_commit_sha",
            "result_hash",
            "metrics",
        ):
            if row.get(key) in (None, "", {}, []):
                blockers.append(f"{expected_backend} artifact missing {key}")
        metrics = row.get("metrics", {})
        if isinstance(metrics, dict):
            missing = [name for name in PHASE9_2_REQUIRED_METRICS if name not in metrics]
            if missing:
                blockers.append(f"{expected_backend} metrics missing {','.join(missing)}")
        else:
            blockers.append(f"{expected_backend} metrics must be an object")
    return blockers


def _result_hashes_are_static(rows: list[dict[str, Any]]) -> bool:
    hashes = [str(row.get("result_hash", "")) for row in rows if row.get("result_hash")]
    return len(hashes) > 1 and len(set(hashes)) == 1


def _paired_rows(
    mujoco_runs: list[dict[str, Any]],
    isaac_runs: list[dict[str, Any]],
) -> list[dict[str, object]]:
    isaac_by_pair = {
        (str(row["scenario_id"]), int(row["seed"])): row
        for row in isaac_runs
        if "scenario_id" in row and "seed" in row
    }
    paired: list[dict[str, object]] = []
    for mujoco in sorted(
        mujoco_runs, key=lambda item: (str(item["scenario_id"]), int(item["seed"]))
    ):
        pair_key = (str(mujoco["scenario_id"]), int(mujoco["seed"]))
        isaac = isaac_by_pair[pair_key]
        paired.append(
            {"scenario_id": pair_key[0], "seed": pair_key[1], "mujoco": mujoco, "isaac": isaac}
        )
    return paired


def _phase9_2_backend_row(
    *,
    backend_name: Literal["mujoco", "isaac"],
    scenario_id: str,
    seed: int,
    metrics: dict[str, Any],
    result_hash: str,
    wall_runtime_s: float,
) -> dict[str, object]:
    normalized_metrics = _phase9_2_metrics(metrics)
    config_payload = {
        "backend_name": backend_name,
        "scenario_id": scenario_id,
        "seed": seed,
        "metric_keys": sorted(normalized_metrics),
    }
    return {
        "backend_name": backend_name,
        "run_id": f"phase9-2-{backend_name}-{scenario_id}-{seed}",
        "scenario_id": scenario_id,
        "seed": seed,
        "process_provenance": {
            "runtime": "isaac_standalone" if backend_name == "isaac" else "mujoco",
            "pid": os.getpid(),
            "wall_runtime_s": round(wall_runtime_s, 6),
        },
        "environment_provenance": {
            "os": platform.platform(),
            "python": _sanitize_text(sys_executable()),
        },
        "config_hash": _stable_hash(config_payload),
        "code_commit_sha": _git_commit_sha(),
        "result_hash": _stable_hash(
            {
                "backend": backend_name,
                "scenario_id": scenario_id,
                "seed": seed,
                "upstream_result_hash": result_hash,
                "metrics": normalized_metrics,
            }
        ),
        "validation_claimed": True,
        "metrics": normalized_metrics,
    }


def _phase9_2_failed_backend_row(
    *,
    backend_name: Literal["mujoco", "isaac"],
    scenario_id: str,
    seed: int,
    wall_runtime_s: float,
    failure_reason: str,
) -> dict[str, object]:
    config_payload = {
        "backend_name": backend_name,
        "scenario_id": scenario_id,
        "seed": seed,
        "failure": failure_reason,
    }
    return {
        "backend_name": backend_name,
        "run_id": f"phase9-2-{backend_name}-{scenario_id}-{seed}",
        "scenario_id": scenario_id,
        "seed": seed,
        "process_provenance": {
            "runtime": "isaac_standalone" if backend_name == "isaac" else "mujoco",
            "pid": os.getpid(),
            "wall_runtime_s": round(wall_runtime_s, 6),
        },
        "environment_provenance": {
            "os": platform.platform(),
            "python": _sanitize_text(sys_executable()),
        },
        "config_hash": _stable_hash(config_payload),
        "code_commit_sha": _git_commit_sha(),
        "result_hash": _stable_hash(
            {
                "backend": backend_name,
                "scenario_id": scenario_id,
                "seed": seed,
                "failure": failure_reason,
            }
        ),
        "validation_claimed": False,
        "final_state": "FAILED",
        "failure_reason": _sanitize_text(failure_reason),
        "metrics": {},
    }


def _phase9_2_metrics(metrics: dict[str, Any]) -> dict[str, object]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    completion = float(
        metrics.get("trajectory_duration_ms", metrics.get("completion_time_ms", 0.0))
    )
    illegal = int(metrics.get("illegal_collision_count", 0))
    contact_count = int(
        metrics.get("expected_contact_count", metrics.get("contact_event_count", 0))
    )
    return {
        "success_rate": 1.0 if illegal == 0 else 0.0,
        "completion_time_ms": round(completion, 6),
        "joint_tracking_rmse": float(metrics.get("joint_tracking_rmse", 0.0)),
        "tcp_position_error_m": float(metrics.get("tcp_position_error_m", 0.0)),
        "illegal_collision_count": illegal,
        "contact_event_count": contact_count,
        "emergency_stop_post_command_count": int(
            metrics.get("emergency_stop_post_command_count", 0)
        ),
        "cloud_call_count": int(metrics.get("cloud_call_count", 0)),
        "detection_latency_ms": float(
            metrics.get("detection_latency_ms", metrics.get("sensor_latency_ms", 0.0))
        ),
        "recovery_latency_ms": float(metrics.get("recovery_latency_ms", 0.0)),
        "final_state": str(metrics.get("final_state", "SUCCESS" if illegal == 0 else "FAILED")),
        "auto_mode_selection": str(metrics.get("auto_mode_selection", "AUTO")),
        "physics_steps": int(metrics.get("physics_steps", 0)),
        "real_time_factor": float(metrics.get("real_time_factor", 0.0)),
        "cpu_usage": round(
            float(getattr(usage, "ru_utime", 0.0) + getattr(usage, "ru_stime", 0.0)), 6
        ),
        "peak_ram_mb": round(float(getattr(usage, "ru_maxrss", 0.0)) / 1024.0, 6),
        "peak_vram_mb": float(metrics.get("peak_vram_mb", 0.0)),
    }


def _metric_deltas(paired: list[dict[str, object]]) -> dict[str, object]:
    deltas: dict[str, object] = {}
    for metric in PHASE9_2_REQUIRED_METRICS:
        values: list[float] = []
        matches = 0
        for pair in paired:
            mujoco = pair["mujoco"]
            isaac = pair["isaac"]
            if not isinstance(mujoco, dict) or not isinstance(isaac, dict):
                continue
            mujoco_metrics = mujoco["metrics"]
            isaac_metrics = isaac["metrics"]
            if not isinstance(mujoco_metrics, dict) or not isinstance(isaac_metrics, dict):
                continue
            left = mujoco_metrics[metric]
            right = isaac_metrics[metric]
            if isinstance(left, (int, float)) and isinstance(right, (int, float)):
                values.append(float(right) - float(left))
            else:
                matches += int(str(left) == str(right))
        if values:
            deltas[metric] = round(fmean(values), 8)
        else:
            deltas[metric] = {"match_count": matches, "pair_count": len(paired)}
    return deltas


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _stable_hash(payload: dict[str, object]) -> str:
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git_commit_sha() -> str:
    result = _run_command(["git", "rev-parse", "HEAD"], timeout=5.0)
    return result.stdout.strip() if result.exit_code == 0 else "UNKNOWN"


def sys_executable() -> str:
    return sys.executable


def _write_cross_backend_outputs(
    output_dir: Path,
    paired: list[dict[str, object]],
    metric_deltas: dict[str, object],
    status: str,
    blockers: list[str],
) -> None:
    (output_dir / "paired_runs.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in paired),
        encoding="utf-8",
    )
    (output_dir / "metric_deltas.json").write_text(
        json.dumps(metric_deltas, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    statistical_summary = {
        "status": status,
        "paired_run_count": len(paired),
        "blockers": blockers,
    }
    (output_dir / "statistical_summary.json").write_text(
        json.dumps(statistical_summary, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "status": status,
        "scenario_count": len({row.get("scenario_id") for row in paired}),
        "seed_count": len({row.get("seed") for row in paired}),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (output_dir / "reproducibility_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    blocker_lines = "\n".join(f"- {blocker}" for blocker in blockers) or "- none"
    (output_dir / "cross_backend_report.md").write_text(
        f"# Phase 9.2 Cross-Backend Report\n\n"
        f"Status: `{status}`\n\n"
        f"Paired runs: `{len(paired)}`\n\n"
        f"## Blockers\n\n{blocker_lines}\n",
        encoding="utf-8",
    )


def _sanitize_text(value: str) -> str:
    home = str(Path.home())
    sanitized = value
    if home:
        sanitized = sanitized.replace(home, "$HOME")
    return sanitized


def _sanitize_argv(argv: list[str]) -> list[str]:
    return [_sanitize_text(item) for item in argv]
