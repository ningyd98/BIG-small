"""Synthetic resource math never supplies real pilot or physical acceptance."""

from __future__ import annotations

import importlib

import pytest


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.resource_plan")


def amount(wall=10.0, storage=100, requests=1, money=0.2):
    return {
        "wall_s": wall,
        "storage_bytes": storage,
        "cloud_model_requests": requests,
        "application_bytes": 20,
        "monetary_cost": money,
    }


def measurements():
    return {
        "successful_wall_s": [10.0, 100.0],
        "successful_storage_bytes": [100, 1000],
        "successful_requests": [1, 10],
        "successful_application_bytes": [20, 200],
        "successful_monetary_costs": [0.2, 2.0],
        "selection_sunk": amount(4800, 48000, 480, 96),
        "foundation_sunk": amount(12000, 12000, 120, 24),
        "current_disk": {"total_bytes": 65000, "raw_bytes": 60000, "archive_bytes": 5000},
        "auxiliary": {key: amount() for key in api().AUXILIARY_PHASES},
        "opportunity_count": 3000,
        "initialization_in_complete_path": True,
    }


def ceilings():
    return {
        "wall_s": 1.0e10,
        "storage_bytes": 10**15,
        "cloud_model_requests": 10**9,
        "monetary_cost": 1.0e9,
    }


def test_complete_success_p99_drives_tcap_and_fixed_full_method_terms():
    plan = api().estimate_resource_terms(measurements(), formal_n=600, declared_ceilings=ceilings())
    assert plan["scope"] == "SOFTWARE_ONLY" and plan["available"] is False
    assert plan["actual_research_status"] == "NOT_RUN" and plan["physical_acceptance"] is False
    assert plan["successful_p99_wall_s"] == pytest.approx(99.1)
    assert plan["tcap_s"] == 200 and plan["rcap_s"] == 60
    assert plan["terms"]["power"]["episodes"] == 120 * 7
    assert plan["terms"]["formal_chosen"]["episodes"] == 600 * 7
    assert plan["terms"]["formal_worst"]["episodes"] == 2400 * 7
    assert plan["terms"]["g4"]["episodes"] == 200 * 2
    assert plan["terms"]["g4"]["amount"]["wall_s"] == 200 * 2 * 60
    assert plan["terms"]["g3_rules"]["opportunities"] == 3000
    assert plan["terms"]["g3_rules"]["rule_passes"] == 6000
    assert plan["reserve_rule"]["fraction"] == 0.2


def test_failed_shortcuts_and_missing_success_cannot_compile_resource_plan():
    data = measurements()
    data["successful_wall_s"] = []
    with pytest.raises(ValueError, match="successful"):
        api().estimate_resource_terms(data, declared_ceilings=ceilings())
    data = measurements()
    data["successful_wall_s"] = [float("nan")]
    with pytest.raises(ValueError):
        api().estimate_resource_terms(data, declared_ceilings=ceilings())


@pytest.mark.parametrize("durations,expected", [([1.0], 120), ([61.0], 130), ([1000.0], 600)])
def test_successful_tcap_clamps_and_ceiling(durations, expected):
    data = measurements()
    data.update(
        successful_wall_s=durations,
        successful_storage_bytes=[100],
        successful_requests=[1],
        successful_application_bytes=[20],
        successful_monetary_costs=[0.2],
    )
    assert api().estimate_resource_terms(data, declared_ceilings=ceilings())["tcap_s"] == expected


def test_unknown_calibration_or_fees_remain_incomplete():
    data = measurements()
    data["auxiliary"].pop("calibration")
    data["successful_monetary_costs"][0] = None
    plan = api().estimate_resource_terms(data, declared_ceilings=ceilings())
    assert plan["budget_status"] == "INCOMPLETE"
    assert "calibration" in plan["unknown_components"]
    assert plan["totals"]["worst"]["monetary_cost"] is None


def test_absent_ceiling_unavailable_and_exceeded_quota_explicit():
    data = measurements()
    assert api().estimate_resource_terms(data)["budget_status"] == "UNAVAILABLE"
    limits = ceilings()
    limits["cloud_model_requests"] = 1
    plan = api().estimate_resource_terms(data, declared_ceilings=limits)
    assert plan["budget_status"] == "EXCEEDS_DECLARED_CEILINGS"
    assert plan["ceiling_checks"]["worst"]["cloud_model_requests"] is False


def test_unknown_formal_n_never_selects_n_and_worst_scenario_keeps_current_storage():
    plan = api().estimate_resource_terms(measurements(), declared_ceilings=ceilings())
    assert plan["formal_n"] is None and plan["terms"]["formal_chosen"] is None
    assert plan["totals"]["chosen"] is None
    assert plan["totals"]["worst"]["storage_bytes"] > 65000
    assert plan["totals"]["worst"]["wall_s"] >= 2400 * 7 * 200


def test_strict_reader_missing_actual_source_is_unavailable(tmp_path):
    result = api().compile_resource_plan(tmp_path, declared_ceilings=ceilings())
    assert result["available"] is False and result["budget_status"] == "UNAVAILABLE"
    assert result["actual_research_status"] == "NOT_RUN" and result["physical_acceptance"] is False


def request_fixture(tmp_path, missing_fee=False):
    import hashlib
    import json

    rows, wire = [], []
    for index, (role, status) in enumerate(
        zip(
            ("PLANNER", "SUPERVISOR", "REPLANNER", "JUDGE"),
            ("SUCCESS", "ERROR", "TIMEOUT", "CANCELLED"),
            strict=True,
        )
    ):
        request, response = f"SOFTWARE_ONLY-request-{index}".encode(), b"response"
        sent, received = f"request-{index}.raw", f"response-{index}.raw"
        (tmp_path / sent).write_bytes(request)
        (tmp_path / received).write_bytes(response)
        rows.append(
            {
                "request_id": f"r{index}",
                "sent_at": "2026-10-04T00:00:00Z",
                "finished_at": "2026-10-04T00:00:01Z",
                "is_cloud_model": True,
                "model_role": role,
                "deployment": "CLOUD",
                "provider_location": "REMOTE_SERVICE",
                "provider_version": "a" * 64,
                "status": status,
                "serialized_sent_bytes": len(request),
                "serialized_received_bytes": len(response),
                "monetary_cost": None if missing_fee and index == 0 else 0.5,
            }
        )
        wire.append(
            {
                "request_id": f"r{index}",
                "request_path": sent,
                "response_path": received,
                "request_sha256": hashlib.sha256(request).hexdigest(),
                "response_sha256": hashlib.sha256(response).hexdigest(),
            }
        )
    (tmp_path / "requests.json").write_text(json.dumps(rows))
    (tmp_path / "wire.json").write_text(json.dumps(wire))
    return rows, wire


def test_all_roles_retries_errors_and_actual_wire_are_counted(tmp_path):
    rows, _ = request_fixture(tmp_path)
    result = api()._read_request_costs(tmp_path, "requests.json", "wire.json")
    assert result["cloud_model_requests"] == 4 and result["model_requests"] == 4
    assert result["requests_by_role"] == dict.fromkeys(
        ("PLANNER", "SUPERVISOR", "REPLANNER", "JUDGE"), 1
    )
    assert result["application_bytes"] == sum(
        row["serialized_sent_bytes"] + row["serialized_received_bytes"] for row in rows
    )
    assert result["monetary_cost"] == 2.0


@pytest.mark.parametrize("damage", ["wire", "identity", "missing", "inflight"])
def test_cost_reader_rejects_rehashed_actual_count_and_wire_drift(tmp_path, damage):
    import json

    rows, wire = request_fixture(tmp_path)
    if damage == "wire":
        (tmp_path / "request-0.raw").write_bytes(b"truncated")
    elif damage == "identity":
        wire[0]["request_id"] = "foreign"
    elif damage == "missing":
        wire.pop()
    else:
        rows[0].update(status="IN_FLIGHT", finished_at=None)
    (tmp_path / "requests.json").write_text(json.dumps(rows))
    (tmp_path / "wire.json").write_text(json.dumps(wire))
    with pytest.raises(ValueError):
        api()._read_request_costs(tmp_path, "requests.json", "wire.json")


def test_missing_billing_remains_unknown_and_empty_requests_need_proof(tmp_path):
    import json

    request_fixture(tmp_path, missing_fee=True)
    assert (
        api()._read_request_costs(tmp_path, "requests.json", "wire.json")["monetary_cost"] is None
    )
    (tmp_path / "requests.json").write_text(json.dumps([]))
    (tmp_path / "wire.json").write_text(json.dumps([]))
    result = api()._read_request_costs(tmp_path, "requests.json", "wire.json")
    assert result["cloud_model_requests"] is None and result["monetary_cost"] is None


def test_current_cloud_resource_costs_cannot_use_another_provider_version(tmp_path):
    request_fixture(tmp_path)
    with pytest.raises(ValueError, match="provider"):
        api()._read_request_costs(
            tmp_path, "requests.json", "wire.json", expected_provider_version="b" * 64
        )


@pytest.mark.parametrize("damage", ["empty_stale_hash", "absent_stale_hash", "absent_unmarked"])
def test_zero_byte_or_absent_response_never_skips_original_sha(tmp_path, damage):
    import json

    rows, wire = request_fixture(tmp_path)
    rows[1]["serialized_received_bytes"] = 0
    if damage == "empty_stale_hash":
        (tmp_path / wire[1]["response_path"]).write_bytes(b"")
    else:
        wire[1]["response_path"] = None
        if damage == "absent_stale_hash":
            wire[1]["response_present"] = False
        else:
            wire[1]["response_sha256"] = None
    (tmp_path / "requests.json").write_text(json.dumps(rows))
    (tmp_path / "wire.json").write_text(json.dumps(wire))
    with pytest.raises(ValueError, match="response|wire"):
        api()._read_request_costs(tmp_path, "requests.json", "wire.json")


@pytest.mark.parametrize("present", [True, False])
def test_empty_response_and_no_response_have_distinct_valid_sources(tmp_path, present):
    import hashlib
    import json

    rows, wire = request_fixture(tmp_path)
    rows[1]["serialized_received_bytes"] = 0
    wire[1]["response_present"] = present
    if present:
        (tmp_path / wire[1]["response_path"]).write_bytes(b"")
        wire[1]["response_sha256"] = hashlib.sha256(b"").hexdigest()
    else:
        wire[1].update(response_path=None, response_sha256=None)
    (tmp_path / "requests.json").write_text(json.dumps(rows))
    (tmp_path / "wire.json").write_text(json.dumps(wire))
    result = api()._read_request_costs(tmp_path, "requests.json", "wire.json")
    assert result["original_attempts"] == 4 and result["requests_by_role"]["SUPERVISOR"] == 1


def test_whole_tree_measures_raw_archives_and_rejects_symlinks(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "source").mkdir()
    (tmp_path / "raw/data.bin").write_bytes(b"12345")
    (tmp_path / "source/code.py").write_bytes(b"123")
    (tmp_path / "other.json").write_bytes(b"{}")
    (tmp_path / "resource-plan.json").write_bytes(b"compiler receipt excluded from own inputs")
    result = api()._tree_sizes(tmp_path)
    assert result["total_bytes"] == 10 and result["raw_bytes"] == 5 and result["archive_bytes"] == 3
    (tmp_path / "raw/link").symlink_to(tmp_path / "other.json")
    with pytest.raises(ValueError):
        api()._tree_sizes(tmp_path)


def phase_fixture(tmp_path, monkeypatch):
    import hashlib
    import json
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    source = Path("collector.py")
    source.write_text("# SOFTWARE_ONLY fixture for source-cost parser verification")
    monkeypatch.setattr(api(), "stage_source_paths", lambda: [source])
    root = tmp_path / "phase"
    (root / "source").mkdir(parents=True)
    (root / "source/collector.py").write_bytes(source.read_bytes())
    rows, _ = request_fixture(root)
    clocks = [
        {"event": "START", "run_id": "fixture", "monotonic_s": 1.0},
        {"event": "FINISH", "run_id": "fixture", "monotonic_s": 4.0},
    ]
    (root / "clock.json").write_text(json.dumps(clocks))
    (root / "phase.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.resource-phase.v1",
                "scope": "REAL_RUNTIME",
                "phase": "g3_rules",
                "role_bundle_hash": "b" * 64,
                "run_id": "fixture",
                "source_hashes": {"collector.py": hashlib.sha256(source.read_bytes()).hexdigest()},
                "clock_path": "clock.json",
                "requests_path": "requests.json",
                "wire_path": "wire.json",
                "coverage": {"opportunity_ids": ["o1", "o2"], "methods": ["JOINT", "B3"]},
                "local_execution_proof": None,
            }
        )
    )
    return root, rows


def test_source_qualified_phase_recomputes_clock_bytes_and_full_opportunity_coverage(
    tmp_path, monkeypatch
):
    root, _ = phase_fixture(tmp_path, monkeypatch)
    result = api()._read_resource_phase(root, "g3_rules", "b" * 64, ["o1", "o2"])
    assert result["wall_s"] == 3.0 and result["cloud_model_requests"] == 4
    assert result["storage_bytes"] > 0


@pytest.mark.parametrize("damage", ["source", "clock", "coverage", "role", "software"])
def test_auxiliary_phase_cannot_relabel_or_drop_raw_sources(tmp_path, monkeypatch, damage):
    import json

    root, _ = phase_fixture(tmp_path, monkeypatch)
    payload = json.loads((root / "phase.json").read_text())
    if damage == "source":
        payload["source_hashes"] = {}
    elif damage == "clock":
        (root / "clock.json").write_text(
            json.dumps(
                [
                    {"event": "START", "run_id": "fixture", "monotonic_s": 5.0},
                    {"event": "FINISH", "run_id": "fixture", "monotonic_s": 4.0},
                ]
            )
        )
    elif damage == "coverage":
        payload["coverage"]["opportunity_ids"] = ["o1"]
    elif damage == "role":
        payload["role_bundle_hash"] = "c" * 64
    else:
        payload["scope"] = "SOFTWARE_ONLY"
    (root / "phase.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        api()._read_resource_phase(root, "g3_rules", "b" * 64, ["o1", "o2"])


def test_empty_auxiliary_requests_without_local_execution_proof_remain_unknown(
    tmp_path, monkeypatch
):
    root, _ = phase_fixture(tmp_path, monkeypatch)
    (root / "requests.json").write_text("[]")
    (root / "wire.json").write_text("[]")
    result = api()._read_resource_phase(root, "g3_rules", "b" * 64, ["o1", "o2"])
    assert result["cloud_model_requests"] is None and result["monetary_cost"] is None


def test_bare_local_trace_cannot_claim_no_model_path_from_arbitrary_source(tmp_path, monkeypatch):
    import json

    root, _ = phase_fixture(tmp_path, monkeypatch)
    record = json.loads((root / "phase.json").read_text())
    record.update(
        phase="source_verification",
        local_execution_proof={
            "schema_version": "ced.local-cost-proof.v1",
            "events_path": "local.json",
        },
    )
    events = [
        {"event": "START", "run_id": "fixture"},
        {
            "event": "LOCAL_OPERATION",
            "run_id": "fixture",
            "phase": "source_verification",
            "source_path": "collector.py",
            "source_sha256": record["source_hashes"]["collector.py"],
            "operation": "LOCAL_SOURCE_PROCESSING",
        },
        {"event": "FINISH", "run_id": "fixture"},
    ]
    (root / "local.json").write_text(json.dumps(events))
    (root / "phase.json").write_text(json.dumps(record))
    (root / "requests.json").write_text("[]")
    (root / "wire.json").write_text("[]")
    with pytest.raises(ValueError, match="local|source|clock"):
        api()._read_resource_phase(root, "source_verification", "b" * 64, ["o1", "o2"])


def test_zero_request_rule_proof_recomputes_full_fixed_clocks_and_both_methods(tmp_path):
    import json
    from dataclasses import asdict
    from pathlib import Path

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
    from cloud_edge_robot_arm.research.assignments import _json
    from cloud_edge_robot_arm.research.protocol import file_hash
    from cloud_edge_robot_arm.research.runner import run_gate_replay
    from tests.test_fixed_opportunity_replay import opportunities

    values = opportunities()
    ids = [value.opportunity_id for value in values]
    raw = [_json(value) for value in values]
    (tmp_path / "opportunities.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.opportunity-set.v1",
                "opportunities": raw,
                "content_hash": content_digest(raw),
            }
        )
    )
    records = [asdict(row) for method in ("JOINT", "B3") for row in run_gate_replay(values, method)]
    (tmp_path / "records.json").write_text(json.dumps(records))
    source = "src/cloud_edge_robot_arm/edge/evidence/opportunities.py"
    clock = [
        {"event": "START", "run_id": "SOFTWARE_ONLY", "monotonic_s": 1.0},
        {"event": "FINISH", "run_id": "SOFTWARE_ONLY", "monotonic_s": 4.0},
    ]
    events = [
        clock[0],
        *[
            {
                "event": "LOCAL_OPERATION",
                "run_id": "SOFTWARE_ONLY",
                "phase": "g3_rules",
                "source_path": source,
                "source_sha256": file_hash(Path(source)),
                "function": "replay_opportunities",
                "monotonic_s": 2.0,
                "opportunity_id": identity,
                "method_id": method,
            }
            for identity in ids
            for method in ("JOINT", "B3")
        ],
        clock[-1],
    ]
    (tmp_path / "clock.json").write_text(json.dumps(clock))
    (tmp_path / "events.json").write_text(json.dumps(events))
    record = {
        "phase": "g3_rules",
        "run_id": "SOFTWARE_ONLY",
        "clock_path": "clock.json",
        "source_hashes": {source: file_hash(Path(source))},
        "local_execution_proof": {
            "schema_version": "ced.local-cost-proof.v1",
            "events_path": "events.json",
            "opportunities_path": "opportunities.json",
            "records_path": "records.json",
        },
    }
    assert api()._local_request_proof(tmp_path, record, ids) is True
    with pytest.raises(ValueError):
        api()._local_request_proof(tmp_path, record, ids[:-1])


def test_persisted_resource_flag_cannot_replace_independent_recompilation(tmp_path, monkeypatch):
    import json

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

    plan = {
        "scope": "SOURCE_RESOURCE_DIAGNOSTIC",
        "available": True,
        "budget_status": "WITHIN_DECLARED_CEILINGS",
        "physical_acceptance": False,
        "actual_research_status": "NOT_RUN",
        "tcap_s": 120,
    }
    plan["content_hash"] = content_digest(plan)
    (tmp_path / "resource-inputs.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.resource-inputs.v1",
                "formal_n": None,
                "declared_ceilings": ceilings(),
            }
        )
    )
    (tmp_path / "resource-plan.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.resource-plan-receipt.v1",
                "plan": plan,
                "content_hash": content_digest(plan),
            }
        )
    )
    monkeypatch.setattr(
        api(),
        "compile_resource_plan",
        lambda *a, **k: {
            "available": False,
            "budget_status": "UNAVAILABLE",
            "scope": "SOURCE_RESOURCE_DIAGNOSTIC",
        },
    )
    with pytest.raises(ValueError, match="resource"):
        api().verify_resource_plan_receipt(tmp_path)


def test_software_only_budget_math_cannot_become_initial_resource_receipt(tmp_path, monkeypatch):
    import json

    from cloud_edge_robot_arm.datasets.rgbd.models import content_digest

    plan = api().estimate_resource_terms(measurements(), declared_ceilings=ceilings())
    plan["content_hash"] = content_digest(plan)
    (tmp_path / "resource-inputs.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.resource-inputs.v1",
                "formal_n": None,
                "declared_ceilings": ceilings(),
            }
        )
    )
    (tmp_path / "resource-plan.json").write_text(
        json.dumps(
            {
                "schema_version": "ced.resource-plan-receipt.v1",
                "plan": plan,
                "content_hash": content_digest(plan),
            }
        )
    )
    monkeypatch.setattr(api(), "compile_resource_plan", lambda *a, **k: plan)
    with pytest.raises(ValueError):
        api().verify_resource_plan_receipt(tmp_path)


def test_compiler_seam_retains_all_sunk_failures_but_uses_complete_success_costs(
    tmp_path, monkeypatch
):
    # Only numerical orchestration is verified: the independent physical auditor
    # and already-tested cost readers are explicitly replaced. No real source passed.
    import json

    from cloud_edge_robot_arm.research import freeze_evidence

    pools = {"foundation": [{"scene": {"group_id": "SOFTWARE_ONLY-research"}}]}
    base = {
        "available": True,
        "errors": [],
        "pools": pools,
        "role_bundle_hash": "b" * 64,
        "cloud_model_snapshot_hash": "a" * 64,
        "selected_period_s": 2.0,
        "evidence_hash": "c" * 64,
    }
    foundation_rows = [
        {
            "assignment_id": f"foundation-{i}",
            "scope": "REAL_RUNTIME",
            "success": i == 0,
            "wall_duration_s": 100.0 if i == 0 else 0.001,
        }
        for i in range(120)
    ]
    selection_rows = [
        {
            "assignment_id": f"selection-{i}",
            "scope": "REAL_RUNTIME",
            "success": False,
            "wall_duration_s": 0.001,
        }
        for i in range(480)
    ]
    monkeypatch.setattr(
        freeze_evidence,
        "audit_ced_pilot_stage",
        lambda root, stage: {
            **base,
            "cases": foundation_rows if stage == "foundation" else selection_rows,
        },
    )
    monkeypatch.setattr(
        api(),
        "_case_measurement",
        lambda root, row, **kwargs: {
            **amount(row["wall_duration_s"]),
            "requests_by_role": {"PLANNER": 1},
        },
    )
    monkeypatch.setattr(
        api(),
        "_read_resource_phase",
        lambda *args, **kwargs: {**amount(), "coverage": {"group_ids": ["SOFTWARE_ONLY-aux"]}},
    )
    (tmp_path / "selection-evidence").mkdir()
    (tmp_path / "protocol-evidence").mkdir()
    ids = [f"o{i}" for i in range(3001)]
    (tmp_path / "protocol-evidence/opportunities.json").write_text(
        json.dumps([{"seed": {"opportunity_id": identity}} for identity in ids])
    )
    auxiliary = tmp_path / "resource-evidence"
    for phase in api().AUXILIARY_PHASES:
        (auxiliary / phase).mkdir(parents=True)
    result = api().compile_resource_plan(
        tmp_path, declared_ceilings=ceilings(), auxiliary_cost_evidence=auxiliary
    )
    assert result["budget_status"] == "WITHIN_DECLARED_CEILINGS" and result["available"] is True
    assert result["actual_research_status"] == "NOT_RUN" and result["physical_acceptance"] is False
    assert result["tcap_s"] == 200 and result["successful_originals"] == 1
    assert result["original_denominators"] == {"selection": 480, "foundation": 120}
    assert result["terms"]["foundation_sunk"]["amount"]["wall_s"] == pytest.approx(100.119)
    assert result["terms"]["g3_rules"]["opportunities"] == 3001
