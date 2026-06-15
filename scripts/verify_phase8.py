#!/usr/bin/env python3
"""Phase 8 acceptance verification.

This script runs executable checks for the reproducible experiment framework.
It does not merely scan files.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.experiments.batch_runner import run_suite  # noqa: E402
from cloud_edge_robot_arm.experiments.models import (  # noqa: E402
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    ResultStatus,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.profiles import get_network_profile  # noqa: E402
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner  # noqa: E402
from cloud_edge_robot_arm.simulation.clock import VirtualClock  # noqa: E402
from cloud_edge_robot_arm.simulation.network import NetworkMessage, NetworkSimulator  # noqa: E402


def _config(tmp: Path, scenario_id: str, mode: ExperimentMode) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"verify-{scenario_id.lower()}-{mode.value.lower()}",
        scenario_id=scenario_id,
        mode=mode,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp,
    )


def check_imports() -> None:
    import cloud_edge_robot_arm.experiments.artifacts  # noqa: F401
    import cloud_edge_robot_arm.experiments.batch_runner  # noqa: F401
    import cloud_edge_robot_arm.experiments.runner  # noqa: F401
    import cloud_edge_robot_arm.simulation.clock  # noqa: F401
    import cloud_edge_robot_arm.simulation.network  # noqa: F401


def check_virtual_clock() -> None:
    clock = VirtualClock()
    observed: list[str] = []
    clock.schedule(10, lambda: observed.append("b"), priority=1)
    clock.schedule(10, lambda: observed.append("a"), priority=0)
    clock.run_until_idle()
    assert observed == ["a", "b"]


def check_network_faults() -> None:
    clock = VirtualClock()
    network = NetworkSimulator(
        profile=get_network_profile(NetworkProfileName.GOOD),
        seed=1,
        clock=clock,
    )
    delivered: list[str] = []
    network.send(
        NetworkMessage(message_id="m1", channel="edge-cloud", payload_size_bytes=32),
        lambda msg: delivered.append(msg.message_id),
    )
    clock.run_until_idle()
    assert delivered == ["m1"]
    assert network.uploaded_bytes == 32


def check_mode_smoke(mode: ExperimentMode) -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        result = ExperimentRunner(_config(Path(tmp_s), "S01_NORMAL_STATIC", mode)).run_once()
        assert result.result_status == ResultStatus.SUCCESS
        assert result.simulated_collision_count == 0


def check_dynamic_and_outage() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        moved = ExperimentRunner(
            _config(Path(tmp_s) / "moved", "S02_TARGET_MOVED", ExperimentMode.AUTO)
        ).run_once()
        outage = ExperimentRunner(
            _config(Path(tmp_s) / "outage", "S08_NETWORK_OUTAGE", ExperimentMode.AUTO)
        ).run_once()
        assert moved.result_status in {ResultStatus.SUCCESS, ResultStatus.NEEDS_OBSERVATION}
        assert outage.recovery_latency_ms is not None


def check_command_rejections() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), "S10_STALE_DUPLICATE_REORDERED_COMMAND", ExperimentMode.AUTO)
        ).run()
        result = execution.result
        statuses = {
            str(event.payload.get("status", ""))
            for event in execution.events
            if event.event_type == "command_ack" and event.payload.get("accepted") is False
        }
        assert {
            "REJECTED_EXPIRED",
            "REJECTED_DUPLICATE",
            "REJECTED_IDEMPOTENCY_CONFLICT",
            "REJECTED_STALE_SEQUENCE",
            "REJECTED_STALE_PLAN",
            "REJECTED_SCENE_MISMATCH",
        }.issubset(statuses)
        assert result.stale_command_rejection_count >= 1
        assert result.duplicate_command_rejection_count >= 1
        assert result.reordered_command_rejection_count >= 1


def check_skill_cache_ablation() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        config = _config(Path(tmp_s), "S11_SKILL_CACHE_HIT", ExperimentMode.AUTO).model_copy(
            update={"cache_policy": CachePolicy.NO_CACHE_REUSE}
        )
        result = ExperimentRunner(config).run_once()
        assert result.cache_hit_count == 0
        assert result.cache_miss_count >= 1


def check_emergency_stop() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        result = ExperimentRunner(
            _config(Path(tmp_s), "S14_EMERGENCY_STOP", ExperimentMode.AUTO)
        ).run_once()
        assert result.result_status == ResultStatus.SAFETY_STOPPED
        assert result.emergency_stop_count >= 1


def check_sqlite_restart() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        result = ExperimentRunner(
            _config(Path(tmp_s), "S15_SQLITE_RESTART_DURING_RUN", ExperimentMode.AUTO)
        ).run_once()
        assert result.repeated_completed_step_count == 0
        assert result.invariant_violations == []


def check_reproducibility() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        first = ExperimentRunner(
            _config(Path(tmp_s) / "a", "S08_NETWORK_OUTAGE", ExperimentMode.AUTO)
        ).run()
        second = ExperimentRunner(
            _config(Path(tmp_s) / "b", "S08_NETWORK_OUTAGE", ExperimentMode.AUTO)
        ).run()
        assert first.result.result_hash == second.result.result_hash


def check_artifacts() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        output = Path(tmp_s)
        summary = run_suite("smoke", output_dir=output, seeds=[0], network_names=["NORMAL"])
        assert summary.run_count > 0
        manifest = json.loads((output / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest["git_sha"]
        assert (output / "raw_runs.jsonl").read_text(encoding="utf-8").strip()
        assert (output / "events.jsonl").read_text(encoding="utf-8").strip()
        assert (output / "summary.csv").exists()
        assert (output / "summary.json").exists()
        assert (output / "report.md").exists()


def check_full_suite_start() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        output = Path(tmp_s)
        summary = run_suite("full", output_dir=output, seeds=[0], network_names=["GOOD"])
        assert summary.run_count > 0
        assert (output / "run_manifest.json").exists()
        assert (output / "summary.json").exists()


def check_pytest_phase8() -> None:
    test_files = sorted(
        str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_phase8_*.py")
    )
    subprocess.run(
        [sys.executable, "-m", "pytest", *test_files, "-q"],
        cwd=ROOT,
        check=True,
    )


def check_phase3_to_phase7_regression() -> None:
    for script in (
        "verify_phase3.py",
        "verify_phase3_1.py",
        "verify_phase3_2.py",
        "verify_phase4.py",
        "verify_phase5.py",
        "verify_phase6.py",
        "verify_phase6_2.py",
        "verify_phase7.py",
    ):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)


def report(index: int, name: str, func: Callable[[], None]) -> bool:
    try:
        func()
    except Exception as exc:
        print(f"failed {index}. {name}: {type(exc).__name__}: {exc}", flush=True)
        return False
    print(f"passed {index}. {name}", flush=True)
    return True


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("Phase 8 modules import", check_imports),
        ("virtual clock determinism", check_virtual_clock),
        ("network fault injection", check_network_faults),
        ("PCSC smoke experiment", lambda: check_mode_smoke(ExperimentMode.PCSC)),
        ("ETEAC smoke experiment", lambda: check_mode_smoke(ExperimentMode.ETEAC)),
        ("AUTO smoke experiment", lambda: check_mode_smoke(ExperimentMode.AUTO)),
        ("target moved and network outage scenarios", check_dynamic_and_outage),
        ("stale duplicate reordered command scenario", check_command_rejections),
        ("Skill Cache ablation scenario", check_skill_cache_ablation),
        ("emergency stop scenario", check_emergency_stop),
        ("SQLite restart scenario", check_sqlite_restart),
        ("reproducibility test", check_reproducibility),
        ("experiment artifact integrity", check_artifacts),
        ("full suite start", check_full_suite_start),
        ("pytest Phase 8 tests", check_pytest_phase8),
        ("Phase 3-7 regression", check_phase3_to_phase7_regression),
    ]
    passed = sum(
        1 for index, (name, func) in enumerate(checks, start=1) if report(index, name, func)
    )
    success = passed == len(checks)
    print(f"{passed}/{len(checks)} checks passed", flush=True)
    print(f"success={str(success).lower()}", flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
