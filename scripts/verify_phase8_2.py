#!/usr/bin/env python3
"""Phase 8.2 故障交错和敏感性验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。

Phase 8.2 acceptance verification.

The checks execute the experiment harness and fail if the added Phase 8.2
signals collapse to identical or synthetic values."""

from __future__ import annotations

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
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner  # noqa: E402

EXPECTED_CRASH_POINTS = {
    "C1_ACTIVE_CONTRACT_SAVED",
    "C2_RISK_SNAPSHOT_SAVED",
    "C3_AUTO_DECISION_SAVED",
    "C4_TRANSITION_PREPARED_BEFORE_COMMIT",
    "C5_REPLAN_SAVED_BEFORE_CAS_APPLY",
    "C6_CAS_APPLIED_BEFORE_ACK",
    "C7_EXECUTION_RECORD_SAVED_BEFORE_STATISTICS",
    "C8_OUTBOX_CLAIMED_BEFORE_ACK",
    "C9_CHECKPOINT_UPDATED_BEFORE_NEXT_STEP",
}


def _config(
    tmp: Path,
    *,
    scenario_id: str,
    mode: ExperimentMode,
    network: NetworkProfileName = NetworkProfileName.NORMAL,
    seed: int = 0,
    supervision_period_ms: int = 300,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=(
            f"verify82-{scenario_id.lower()}-{mode.value.lower()}-"
            f"{network.value.lower()}-{seed}-{supervision_period_ms}"
        ),
        scenario_id=scenario_id,
        mode=mode,
        seed=seed,
        repetitions=1,
        network_profile=network,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=supervision_period_ms,
        timeout_ms=30_000,
        artifact_dir=tmp,
    )


def check_phase82_pytest() -> None:
    test_files = sorted(
        str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_phase8_2_*.py")
    )
    subprocess.run([sys.executable, "-m", "pytest", *test_files, "-q"], cwd=ROOT, check=True)


def check_pcsc_periodic_ticks() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), scenario_id="S01_NORMAL_STATIC", mode=ExperimentMode.PCSC)
        ).run()
        ticks = [event for event in execution.events if event.event_type == "pcsc_tick"]
        assert len(ticks) >= 2
        assert execution.result.supervisory_decision_count == len(ticks)


def check_real_fault_detection_latency() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), scenario_id="S02_TARGET_MOVED", mode=ExperimentMode.PCSC)
        ).run()
        injected_at = next(
            event.virtual_time_ms
            for event in execution.events
            if event.event_type == "fault_injected"
        )
        detected_at = next(
            event.virtual_time_ms
            for event in execution.events
            if event.event_type == "fault_detected"
        )
        assert detected_at > injected_at
        assert execution.result.fault_detection_latency_ms == detected_at - injected_at


def check_multi_crash_coverage() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(
                Path(tmp_s), scenario_id="S15_SQLITE_RESTART_DURING_RUN", mode=ExperimentMode.AUTO
            )
        ).run()
        recovered = {
            str(event.payload.get("crash_point"))
            for event in execution.events
            if event.event_type == "sqlite_restart_recovered"
        }
        assert EXPECTED_CRASH_POINTS.issubset(recovered)
        assert len(recovered) >= len(EXPECTED_CRASH_POINTS)
        assert execution.result.repeated_completed_step_count == 0


def check_sensitivity_guards() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        summary = run_suite(
            "full",
            output_dir=Path(tmp_s),
            seeds=[0, 1],
            network_names=["GOOD", "SEVERE"],
        )
        guard = summary.summary["validity_guard"]
        assert isinstance(guard, dict)
        assert guard["modes_not_identical"]
        assert guard["networks_not_identical"]
        assert guard["seeds_not_identical"]
        assert guard["fault_detection_latency_not_all_zero"]
        assert guard["pcsc_multi_tick_present"]


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
        ("pytest Phase 8.2 tests", check_phase82_pytest),
        ("PCSC periodic tick closure", check_pcsc_periodic_ticks),
        ("real fault detection latency", check_real_fault_detection_latency),
        ("multi-crash coverage", check_multi_crash_coverage),
        ("experiment sensitivity guards", check_sensitivity_guards),
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
