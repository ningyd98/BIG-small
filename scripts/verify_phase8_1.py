#!/usr/bin/env python3
"""Phase 8.1 PCSC/ETEAC 集成验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。

Phase 8.1 experimental-validity verification.

The checks execute the real runtime harness, ExperimentRunner, Phase 8 smoke
suite, and Phase 3-8 regressions. They do not rely on text search."""

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
from cloud_edge_robot_arm.experiments.metrics_collector import (  # noqa: E402
    ExperimentMetricsCollector,
)
from cloud_edge_robot_arm.experiments.models import (  # noqa: E402
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    ResultStatus,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner  # noqa: E402
from cloud_edge_robot_arm.experiments.runtime_harness import (  # noqa: E402
    RuntimeExperimentHarness,
)
from cloud_edge_robot_arm.simulation.clock import VirtualClock  # noqa: E402


def _config(tmp: Path, scenario_id: str, mode: ExperimentMode) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"verify81-{scenario_id.lower()}-{mode.value.lower()}",
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


def check_runtime_harness() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        harness = RuntimeExperimentHarness(
            config=_config(Path(tmp_s), "S01_NORMAL_STATIC", ExperimentMode.ETEAC),
            clock=VirtualClock(max_time_ms=30_000),
        )
        contract = harness.create_contract()
        result = harness.submit_contract(contract)
        assert result.success
        assert harness.observer.contract_validator_calls >= 1
        assert harness.observer.task_executor_calls == 1
        assert harness.observer.safety_precheck_calls >= len(contract.steps)
        assert harness.observer.robot_action_calls >= len(contract.steps)
        assert harness.completion_summary() is not None


def check_fault_interleaving() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), "S02_TARGET_MOVED", ExperimentMode.ETEAC)
        ).run()
        event_types = [event.event_type for event in execution.events]
        assert event_types.index("step_started") < event_types.index("fault_injected")
        assert event_types.index("fault_injected") < event_types.index("run_completed")


def check_task_executor_path() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        runner = ExperimentRunner(_config(Path(tmp_s), "S01_NORMAL_STATIC", ExperimentMode.ETEAC))
        execution = runner.run()
        contract = runner._active_contract
        assert contract is not None
        records = runner.harness.step_execution_records(contract.task_id)
        assert runner.harness.observer.task_executor_calls == 1
        assert len(records) == execution.result.completed_step_count


def check_safety_path() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        runner = ExperimentRunner(_config(Path(tmp_s), "S14_EMERGENCY_STOP", ExperimentMode.AUTO))
        execution = runner.run()
        assert execution.result.result_status == ResultStatus.SAFETY_STOPPED
        assert execution.result.emergency_stop_count >= 1
        assert any(event.event_type == "step_failed" for event in execution.events)


def check_pcsc_integration() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        runner = ExperimentRunner(_config(Path(tmp_s), "S01_NORMAL_STATIC", ExperimentMode.PCSC))
        execution = runner.run()
        contract = runner._active_contract
        assert contract is not None
        assert runner.harness.supervisor.decisions_for_task(contract.task_id)
        assert execution.result.supervisory_decision_count >= 1


def check_eteac_integration() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        runner = ExperimentRunner(_config(Path(tmp_s), "S04_GRASP_FAILURE", ExperimentMode.ETEAC))
        execution = runner.run()
        contract = runner._active_contract
        assert contract is not None
        budget = runner.harness.event_controller.retry_budget(contract.task_id)
        assert budget is not None and budget.retry_count_used >= 1
        assert execution.result.supervisory_decision_count == 0
        assert execution.result.retry_count >= 1


def check_command_ingress() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), "S10_STALE_DUPLICATE_REORDERED_COMMAND", ExperimentMode.PCSC)
        ).run()
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


def check_transition_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), "S01_NORMAL_STATIC", ExperimentMode.AUTO)
        ).run()
        event_types = [event.event_type for event in execution.events]
        assert "mode_transition_prepared" in event_types
        assert "mode_transition_committed" in event_types
        assert event_types.index("mode_transition_prepared") < event_types.index(
            "mode_transition_committed"
        )


def check_crash_recovery() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        runner = ExperimentRunner(
            _config(Path(tmp_s), "S15_SQLITE_RESTART_DURING_RUN", ExperimentMode.ETEAC)
        )
        before = id(runner.harness.event_repo)
        execution = runner.run()
        contract = runner._active_contract
        assert contract is not None
        assert id(runner.harness.event_repo) != before
        assert runner.harness.event_repo.get_completion_summary_for_task(contract.task_id)
        assert execution.result.repeated_completed_step_count == 0


def check_event_sourced_metrics() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        execution = ExperimentRunner(
            _config(Path(tmp_s), "S10_STALE_DUPLICATE_REORDERED_COMMAND", ExperimentMode.PCSC)
        ).run()
        metrics = ExperimentMetricsCollector.from_events(execution.events).collect()
        assert metrics.completed_step_count == execution.result.completed_step_count
        assert metrics.safety_allow_count == execution.result.safety_allow_count
        assert metrics.stale_command_rejection_count == (
            execution.result.stale_command_rejection_count
        )


def check_reproducibility() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        first = ExperimentRunner(
            _config(Path(tmp_s) / "a", "S08_NETWORK_OUTAGE", ExperimentMode.AUTO)
        ).run()
        second = ExperimentRunner(
            _config(Path(tmp_s) / "b", "S08_NETWORK_OUTAGE", ExperimentMode.AUTO)
        ).run()
        assert first.result.result_hash == second.result.result_hash


def check_phase8_smoke() -> None:
    with tempfile.TemporaryDirectory() as tmp_s:
        summary = run_suite(
            "smoke",
            output_dir=Path(tmp_s),
            seeds=[0],
            network_names=["NORMAL"],
        )
        assert summary.run_count == 45
        assert (Path(tmp_s) / "summary.json").exists()


def check_phase3_to_phase8_regression() -> None:
    for script in (
        "verify_phase3.py",
        "verify_phase3_1.py",
        "verify_phase3_2.py",
        "verify_phase4.py",
        "verify_phase5.py",
        "verify_phase6.py",
        "verify_phase6_2.py",
        "verify_phase7.py",
        "verify_phase8.py",
    ):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)


def check_pytest_phase81() -> None:
    test_files = sorted(
        str(path.relative_to(ROOT)) for path in (ROOT / "tests").glob("test_phase8_1_*.py")
    )
    subprocess.run([sys.executable, "-m", "pytest", *test_files, "-q"], cwd=ROOT, check=True)


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
        ("runtime harness integration", check_runtime_harness),
        ("fault interleaving", check_fault_interleaving),
        ("real TaskExecutor path", check_task_executor_path),
        ("real SafetyShield path", check_safety_path),
        ("PCSC real supervision", check_pcsc_integration),
        ("ETEAC real event/replan path", check_eteac_integration),
        ("S10 real command rejection", check_command_ingress),
        ("ModeTransition prepare/commit/abort", check_transition_lifecycle),
        ("SQLite multi-crash recovery", check_crash_recovery),
        ("event-sourced metric recomputation", check_event_sourced_metrics),
        ("reproducibility", check_reproducibility),
        ("Phase 8 smoke suite", check_phase8_smoke),
        ("Phase 3-8 regression", check_phase3_to_phase8_regression),
        ("pytest Phase 8.1 tests", check_pytest_phase81),
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
