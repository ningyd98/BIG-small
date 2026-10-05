"""研究判定与全分母反例；软件诊断不能冒称正式目标通过。"""

from dataclasses import replace
from importlib import import_module, util

import pytest

from tests.test_research_assignments import scene_pool  # noqa: F401
from tests.test_research_statistics import records


def api(name):
    full = "cloud_edge_robot_arm.research." + name
    assert util.find_spec(full) is not None, "missing production research " + name
    return import_module(full)


def effect(point, lower, upper, p=0.001):
    return api("statistics").EffectEstimate(
        point,
        lower,
        upper,
        p,
        p,
        600,
        "SOFTWARE_ONLY",
        one_sided_lower95=lower,
        one_sided_upper95=upper,
    )


@pytest.mark.parametrize(
    "success_lower,safety_upper,want",
    [(-0.031, 0.009, False), (-0.029, 0.011, False), (-0.029, 0.01, True), (-0.03, 0.009, False)],
)
def test_noninferiority_is_not_failure_to_find_significance(success_lower, safety_upper, want):
    result = api("acceptance").noninferiority_passes(
        effect(0, success_lower, 0.01, p=0.9), effect(0, -0.01, safety_upper, p=0.9)
    )
    assert result is want


def test_point_target_without_interval_excluding_zero_is_not_reliable_gain():
    module = api("acceptance")
    assert module.improvement_status(effect(0.4, -0.01, 0.6), 0.3) == "INSUFFICIENT_EVIDENCE"
    assert module.improvement_status(effect(0.3, 0.01, 0.6), 0.3) == "PASS"
    assert module.improvement_status(effect(0.2, 0.01, 0.6), 0.3) == "FAIL"


def test_penalized_duration_includes_failures():
    rows = records(2)
    rows = [replace(row, duration_penalized_s=120.0, run_status="BLOCKED") for row in rows]
    metrics = api("metrics").compute_research_metrics(rows, (), (), software_only=True)
    assert metrics["methods"]["JOINT"]["assigned_denominator"] == 2
    assert metrics["methods"]["JOINT"]["penalized_duration_p95_s"] == 120.0
    assert metrics["methods"]["JOINT"]["recovery_failed_penalty_s"] == 60.0


def test_false_completion_rate_uses_online_done_denominator():
    rows = records(3)
    changed = []
    for row in rows:
        if row.assignment.method_id == "JOINT":
            index = int(row.assignment.group_id[1:])
            changed.append(
                replace(
                    row,
                    outcome=replace(
                        row.outcome, online_reported_complete=index < 2, physical_success=index == 0
                    ),
                )
            )
        else:
            changed.append(row)
    metrics = api("metrics").compute_research_metrics(changed, (), (), software_only=True)
    assert metrics["methods"]["JOINT"]["online_done_denominator"] == 2
    assert metrics["methods"]["JOINT"]["false_completion_rate"] == 0.5
    assert metrics["methods"]["B0"]["false_completion_rate"] is None


def test_remote_judge_is_in_total_cloud_cost():
    from cloud_edge_robot_arm.research.cost_ledger import CostSnapshot

    rows = records(1)
    changed = [
        replace(
            row,
            costs=CostSnapshot(
                model_requests=2,
                cloud_model_requests=2,
                requests_by_role={"JUDGE": 1, "PLANNER": 1},
            ),
        )
        for row in rows
    ]
    metrics = api("metrics").compute_research_metrics(changed, (), (), software_only=True)
    assert metrics["methods"]["JOINT"]["cloud_requests_total"] == 2
    assert metrics["methods"]["JOINT"]["model_requests_by_role"]["JUDGE"] == 1


def test_stall_and_fallback_keep_assignment_denominator():
    rows = records(2)
    changed = [
        replace(
            row,
            run_status="FALLBACK" if row.assignment.group_id == "g0" else "STOP",
            outcome=replace(row.outcome, terminal_reason="NO_PROGRESS"),
        )
        for row in rows
    ]
    metrics = api("metrics").compute_research_metrics(changed, (), (), software_only=True)
    joint = metrics["methods"]["JOINT"]
    assert joint["assigned_denominator"] == 2
    assert joint["fallback_episode_rate"] == 0.5
    assert joint["no_progress_rate"] == 1.0


def test_unknown_conditions_and_fallback_decisions_do_not_use_episode_denominators():
    rows = records(2)
    changed = []
    for row in rows:
        if row.assignment.method_id == "JOINT" and row.assignment.group_id == "g0":
            statuses = ({"status": "UNKNOWN"},) + tuple({"status": "PASS"} for _ in range(99))
            changed.append(replace(row, verification_records=statuses, run_status="FALLBACK"))
        else:
            changed.append(row)
    joint = api("metrics").compute_research_metrics(changed, (), (), software_only=True)["methods"][
        "JOINT"
    ]
    assert joint["unknown_episode_rate"] == joint["fallback_episode_rate"] == 0.5
    # Legacy verdict dictionaries and episode outcomes do not provide verified
    # condition-evaluation / decision-round denominators. Never relabel their ratios.
    assert joint["unknown_condition_rate"] is None
    assert joint["condition_evaluation_denominator"] is None
    assert joint["unknown_condition_status"] == "NOT_RECORDED"
    assert joint["fallback_rate"] is joint["fallback_decision_rate"] is None
    assert joint["decision_round_denominator"] is None
    assert joint["fallback_decision_status"] == "NOT_RECORDED"


@pytest.mark.parametrize(
    "requests,success",
    [
        ((0.2, 0.1, 0.25), (0, -0.04, 0.02)),
        ((0.4, 0.1, 0.6), (-0.5, -0.55, -0.45)),
    ],
)
def test_g2_preserves_definite_target_failure_and_clear_inferiority(requests, success):
    from tests.test_research_assignments import frozen

    metrics = {
        "scope": "SOFTWARE_ONLY",
        "main_paired_group_denominator": 600,
        "effects": {
            "G2_REQUESTS": effect(*requests).__dict__,
            "G2_SUCCESS": effect(*success).__dict__,
            "G2_SAFETY": effect(0, -0.005, 0.005).__dict__,
        },
    }
    verdict = next(
        value
        for value in api("acceptance").evaluate_goals(metrics, frozen([]), software_only=True)
        if value.goal_id == "G2"
    )
    assert verdict.status == "FAIL"


def test_false_rejection_excludes_unknown():
    from cloud_edge_robot_arm.research.runner import run_gate_replay
    from tests.test_fixed_opportunity_replay import opportunities

    values = opportunities()
    metrics = api("metrics").compute_research_metrics(
        (), values, run_gate_replay(values, "JOINT"), software_only=True
    )
    gate = metrics["gate"]["JOINT"]
    assert gate["eligible_valid"] == gate["eligible_invalid"] == 1
    assert gate["oracle_unknown"] == 1
    assert gate["false_rejection"] == 0
    assert gate["false_rejection_rate"] == 0


def test_g3_replay_never_counts_as_task_success():
    from cloud_edge_robot_arm.research.runner import run_gate_replay
    from tests.test_fixed_opportunity_replay import opportunities

    values = opportunities()
    metrics = api("metrics").compute_research_metrics(
        (), values, run_gate_replay(values, "JOINT"), software_only=True
    )
    assert metrics["accepted_physical_success"] == 0
    assert metrics["assignment_denominator"] == 0
    assert metrics["scope"] == "SOFTWARE_ONLY"


def test_default_formal_metrics_fail_closed_without_raw_physics_verifier():
    from cloud_edge_robot_arm.research.models import EvidenceKind

    rows = [
        replace(
            row,
            run_status="COMPLETED",
            provenance=row.provenance.model_copy(
                update={
                    "evidence_kind": EvidenceKind.PHYSICS,
                    "task_success": True,
                    "physics_steps": 100,
                }
            ),
            outcome=replace(
                row.outcome,
                success=True,
                status="SUCCESS",
                failure_reason=None,
                physical_success=True,
                online_reported_complete=True,
            ),
        )
        for row in records(2)
    ]
    metrics = api("metrics").compute_research_metrics(rows, (), ())
    assert metrics["source_validation_status"] == "NOT_CONFIGURED"
    assert metrics["accepted_physical_success"] == 0
    assert metrics["formal_accepted"] is False


def test_zero_safety_metric_retains_positive_cluster_boundary_and_missing_fields():
    metrics = api("metrics").compute_research_metrics(records(2), (), (), software_only=True)
    joint = metrics["methods"]["JOINT"]
    assert joint["safety_zero_event_upper95"] > 0
    assert joint["provider_refusal_rate"] is None
    assert joint["fault_response_p90_s"] is None


def test_metrics_exposes_full_five_primary_holm_family_without_dropping_unrun_goals():
    metrics = api("metrics").compute_research_metrics(records(), (), (), software_only=True)
    primary = metrics["primary_family"]
    assert set(primary["holm_adjusted_p"]) == {
        "G2_REQUESTS",
        "G2_SUCCESS",
        "G2_SAFETY",
        "G3_FALSE_ACCEPT",
        "G4_DURATION",
    }
    assert primary["raw_p"]["G3_FALSE_ACCEPT"] is None
    assert primary["holm_adjusted_p"]["G3_FALSE_ACCEPT"] == 1
    assert (
        metrics["effects"]["G2_REQUESTS"]["adjusted_p_value"]
        == primary["holm_adjusted_p"]["G2_REQUESTS"]
    )


def test_gate_metrics_uses_common_fixed_group_clusters_not_frame_count():
    from cloud_edge_robot_arm.research.runner import run_gate_replay
    from tests.test_fixed_opportunity_replay import opportunities

    values = opportunities()
    replay = run_gate_replay(values, "JOINT") + run_gate_replay(values, "B3")
    metrics = api("metrics").compute_research_metrics((), values, replay, software_only=True)
    assert metrics["fixed_opportunity_group_denominator"] == len(
        {value.group_id for value in values}
    )
    assert metrics["effects"]["G3_FALSE_ACCEPT"]["denominator"] == len(
        {value.group_id for value in values}
    )
    assert metrics["gate"]["JOINT"]["false_acceptance_zero_event_group_upper95"] > 0


def test_analysis_cli_missing_final_is_not_run(tmp_path):
    import json
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_rgbd_research.py",
            "--runs",
            str(tmp_path / "empty"),
            "--protocol",
            str(tmp_path / "absent"),
            "--output",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 3
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["status"] == "NOT_RUN"
    assert all(value["status"] == "NOT_RUN" for value in report["goal_verdicts"])


def test_production_analysis_callable_is_deterministic_and_ignores_stored_commands(tmp_path):
    import json

    module = api("acceptance")
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "command.json").write_text(json.dumps({"cmd": "touch SHOULD_NOT_EXIST"}))
    first = module.analyze_research_runs(runs, tmp_path / "missing-protocol", tmp_path / "first")
    second = module.analyze_research_runs(runs, tmp_path / "missing-protocol", tmp_path / "second")
    assert first == second
    assert first["status"] == "NOT_RUN"
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()
    assert (tmp_path / "first" / "goal_verdicts.csv").read_bytes() == (
        tmp_path / "second" / "goal_verdicts.csv"
    ).read_bytes()
    assert (tmp_path / "first" / "goal_status.svg").read_bytes() == (
        tmp_path / "second" / "goal_status.svg"
    ).read_bytes()


@pytest.mark.parametrize(
    "absolute,false_rejection,reduction,want",
    [
        (0.02, 0.05, 0.5, "PASS"),
        (0.021, 0.01, 0.6, "FAIL"),
        (0.01, 0.051, 0.6, "FAIL"),
        (0.01, 0.01, 0.49, "FAIL"),
    ],
)
def test_g3_thresholds_keep_absolute_rejection_and_relative_gates_separate(
    absolute, false_rejection, reduction, want
):
    assert (
        api("acceptance").g3_status(effect(reduction, 0.1, 0.9), absolute, false_rejection) == want
    )


def test_g4_requires_two_hundred_faults_eighty_percent_and_no_completed_replay():
    module = api("acceptance")
    assert module.g4_status(200, 0.8, effect(0.3, 0.01, 0.6), 0) == "PASS"
    assert module.g4_status(199, 0.9, effect(0.4, 0.01, 0.6), 0) == "INSUFFICIENT_EVIDENCE"
    assert module.g4_status(200, 0.79, effect(0.4, 0.01, 0.6), 0) == "FAIL"
    assert module.g4_status(200, 0.9, effect(0.4, 0.01, 0.6), 1) == "FAIL"


def test_nominal_gate_reports_missing_localization_or_static_evidence():
    module = api("acceptance")
    assert module.g1_status(0.01, 0.9) == "PASS"
    assert module.g1_status(0.01001, 0.95) == "FAIL"
    assert module.g1_status(0.009, 0.899) == "FAIL"
    assert module.g1_status(None, 0.95) == "NOT_RUN"


@pytest.mark.parametrize("tamper", ["omit_failed", "omit_pool", "complete"])
def test_final_analysis_rejects_rehashed_incomplete_coverage(
    scene_pool,  # noqa: F811
    tmp_path,
    tamper,
):
    import json
    from dataclasses import asdict

    from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json, content_digest
    from cloud_edge_robot_arm.research.assignments import build_assignments
    from cloud_edge_robot_arm.research.protocol import FrozenProtocol, ProtocolSpec
    from cloud_edge_robot_arm.research.runner import run_assignment

    methods = ("JOINT", "B0", "B1", "B2", "NO_UNCERTAINTY", "NO_TIME_VALIDITY", "NO_LOCAL_REPAIR")
    spec = ProtocolSpec(
        selected_n=600,
        tcap_s=120,
        pool_hashes={"formal": content_digest(scene_pool)},
        model_snapshot_hash="a" * 64,
        method_hashes={key: content_digest(key) for key in methods},
        initial_protocol_hash="b" * 64,
        opportunity_hash="c" * 64,
        recovery_fault_manifest_hash="d" * 64,
    )
    frozen = FrozenProtocol(
        spec=spec,
        stage="FINAL",
        content_hash=content_digest({"spec": spec.model_dump(mode="json"), "stage": "FINAL"}),
    )
    protocol = tmp_path / "protocol"
    protocol.mkdir()
    (protocol / "protocol.json").write_text(frozen.model_dump_json())
    runs = tmp_path / "runs"
    runs.mkdir()
    assignments = build_assignments(frozen, methods, scene_pool=scene_pool)
    # A producer can recompute a valid manifest hash after deleting failed episodes.
    # The fixed N and actual pool, rather than this self-declared subset, govern coverage.
    selected = assignments[:2] if tamper == "omit_failed" else assignments
    manifest = {
        "schema_version": "ced.assignments.v1",
        "protocol_hash": frozen.content_hash,
        "assignments": [asdict(row) for row in selected],
    }
    manifest["content_hash"] = content_digest(manifest)
    (runs / "assignments.json").write_text(canonical_json(manifest))
    if tamper != "omit_pool":
        (runs / "pools.json").write_text(canonical_json({"formal": scene_pool}))
    # Missing pool must reject before record decoding, so this case needs no large file.
    recorded = selected if tamper == "complete" else selected[:2]
    (runs / "records.jsonl").write_text(
        "\n".join(
            canonical_json(run_assignment(row, frozen).to_payload(protocol=frozen))
            for row in recorded
        )
        + "\n"
    )
    original = (runs / "records.jsonl").read_bytes()
    result = api("acceptance").analyze_research_runs(
        runs, protocol, tmp_path / "out", software_only=True
    )
    saved_metrics = json.loads((tmp_path / "out" / "metrics.json").read_text())
    if tamper == "complete":
        assert result["status"] == "SOFTWARE_ONLY"
        assert saved_metrics["coverage_status"] == "COMPLETE"
        assert saved_metrics["assignment_denominator"] == 4200
        assert saved_metrics["main_paired_group_denominator"] == 600
        assert {row["assigned_denominator"] for row in saved_metrics["methods"].values()} == {600}
        assert {row["penalized_duration_p95_s"] for row in saved_metrics["methods"].values()} == {
            120
        }
        assert saved_metrics["accepted_physical_success"] == 0
        default = api("acceptance").analyze_research_runs(runs, protocol, tmp_path / "formal-out")
        assert default["status"] == "NOT_RUN"
        assert all(row["status"] == "NOT_RUN" for row in default["goal_verdicts"])
    else:
        assert result["status"] == "NOT_RUN"
        assert "coverage" in result["reasons"][0]
        assert saved_metrics["coverage_status"] == "INCOMPLETE"
    assert (runs / "records.jsonl").read_bytes() == original
