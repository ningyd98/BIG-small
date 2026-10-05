"""Isolated staged pilot fixtures verify software, never a research freeze."""

import copy
import importlib
import json
from collections import Counter

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import content_digest
from cloud_edge_robot_arm.research.protocol import STRATA, build_scene_pools


def api():
    return importlib.import_module("cloud_edge_robot_arm.research.pilot")


@pytest.fixture(scope="module")
def pools():
    return build_scene_pools(981301, set(), protocol_version="ced.research.v2")


def selection_rows(assignments):
    return [
        {
            "assignment_id": row["assignment_id"],
            "success": True,
            "safety_violation": False,
            "wall_duration_s": 20.0,
            "cloud_requests": {0.5: 10, 1.0: 8, 2.0: 4, 5.0: 3}[row["period_s"]],
            "status": "SUCCESS",
        }
        for row in assignments
    ]


def test_selection_pairs_four_periods_and_full_scene_network(pools):
    rows = api().build_pilot_assignments(pools, "selection", role_bundle_hash="a" * 64)
    assert len(rows) == 480
    assert len({row["group_id"] for row in rows}) == 120
    assert Counter(row["period_s"] for row in rows) == Counter(
        {0.5: 120, 1.0: 120, 2.0: 120, 5.0: 120}
    )
    for period in (0.5, 1.0, 2.0, 5.0):
        assert Counter(row["stratum_id"] for row in rows if row["period_s"] == period) == (
            Counter({stratum: 10 for stratum in STRATA})
        )
    paired = [row for row in rows if row["group_id"] == rows[0]["group_id"]]
    assert len({content_digest(row["base_assignment"]) for row in paired}) == 1
    assert len({content_digest(row["network_schedule"]) for row in paired}) == 1
    assert len({row["physics_seed"] for row in paired}) == 1
    assert rows == api().build_pilot_assignments(pools, "selection", role_bundle_hash="a" * 64)


def test_selection_keeps_all_candidates_and_chooses_fixed_cost_rule(pools):
    assignments = api().build_pilot_assignments(pools, "selection", role_bundle_hash="a" * 64)
    records = selection_rows(assignments)
    # The cheapest candidate fails quality; keep it in the diagnostic curve.
    for row in records:
        if row["assignment_id"].endswith("@5"):
            row["success"] = False
    result = api().choose_b0_period(assignments, records)
    assert result["diagnostic_selected_period_s"] == 2.0
    assert result["selected_period_s"] is None
    assert result["scope"] == "SOFTWARE_ONLY"
    assert result["actual_research_status"] == "NOT_RUN"
    assert len(result["periods"]) == 4
    assert all(row["assigned_denominator"] == 120 for row in result["periods"])


@pytest.mark.parametrize("tamper", ["omit", "duplicate", "foreign", "nonfinite"])
def test_selection_rejects_incomplete_or_invalid_originals(pools, tamper):
    assignments = api().build_pilot_assignments(pools, "selection", role_bundle_hash="a" * 64)
    records = selection_rows(assignments)
    if tamper == "omit":
        records.pop()
    elif tamper == "duplicate":
        records[-1] = records[0]
    elif tamper == "foreign":
        records[-1]["assignment_id"] = "foreign"
    else:
        records[-1]["wall_duration_s"] = float("nan")
    with pytest.raises(ValueError):
        api().choose_b0_period(assignments, records)


def test_no_feasible_period_and_all_failed_denominators(pools):
    assignments = api().build_pilot_assignments(pools, "selection", role_bundle_hash="a" * 64)
    records = selection_rows(assignments)
    for row in records:
        row.update(success=False, status="BLOCKED")
    result = api().choose_b0_period(assignments, records)
    assert result["diagnostic_status"] == "NO_FEASIBLE_BASELINE"
    assert result["diagnostic_selected_period_s"] is None
    assert {row["overall_success_rate"] for row in result["periods"]} == {0.0}


@pytest.mark.parametrize("tamper", ["pool_reuse", "scene_hash", "missing", "period"])
def test_preassignment_rejects_leakage_or_drift(pools, tamper):
    changed = copy.deepcopy(pools)
    kwargs = {}
    if tamper == "pool_reuse":
        changed["foundation"][0] = changed["selection"][0]
    elif tamper == "scene_hash":
        changed["selection"][0]["scene_hash"] = "f" * 64
    elif tamper == "missing":
        changed["selection"].pop()
    else:
        kwargs["period_s"] = 3.0
    with pytest.raises(ValueError):
        api().build_pilot_assignments(changed, "selection", role_bundle_hash="a" * 64, **kwargs)


def test_default_stage_records_every_unexecuted_assignment_without_adapter(pools, tmp_path):
    result = api().run_pilot_stage("selection", pools, tmp_path / "stage")
    assert result["assigned_denominator"] == result["recorded_denominator"] == 480
    assert result["group_denominator"] == 120
    assert result["actual_research_status"] == "NOT_RUN"
    assert result["accepted_success"] == 0 and result["freeze_ready"] is False
    records = json.loads((tmp_path / "stage/results.json").read_text())
    assert len(records) == 480
    assert {row["status"] for row in records} == {"NOT_EXECUTED"}
    with pytest.raises(FileExistsError):
        api().run_pilot_stage("selection", pools, tmp_path / "stage")


def test_software_adapter_cannot_confer_real_selection_or_foundation(pools, tmp_path):
    def fixture(row, directory):
        return {
            "success": True,
            "status": "SUCCESS",
            "safety_violation": False,
            "wall_duration_s": 20.0,
            "cloud_requests": 1,
        }

    with pytest.raises(ValueError, match="SOFTWARE_ONLY"):
        api().run_pilot_stage("selection", pools, tmp_path / "bad", software_adapter=fixture)
    result = api().run_pilot_stage(
        "selection", pools, tmp_path / "software", software_adapter=fixture, software_only=True
    )
    assert result["scope"] == "SOFTWARE_ONLY" and result["accepted_success"] == 0
    assert result["selected_period_s"] is None
    assert result["freeze_ready"] is False and result["actual_research_status"] == "NOT_RUN"
    assert not (tmp_path / "software/protocol.json").exists()


def test_power_stage_preserves_groups_and_declares_unintegrated_methods(pools, tmp_path):
    result = api().run_pilot_stage("power", pools, tmp_path / "power")
    assert result["group_denominator"] == 120
    assert result["assigned_denominator"] is None
    assert result["method_runtime_integrated"] is False
    assert result["actual_research_status"] == "NOT_RUN"


def test_ced_cli_callable_dry_preregisters_without_loading_legacy_or_renderer(
    pools, tmp_path, monkeypatch
):
    import scripts.run_rgbd_pilot as script
    import yaml

    path = tmp_path / "pools.json"
    path.write_text(json.dumps(pools))
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "ced.pilot-config.v1",
                "protocol_version": "ced.research.v2",
                "episodes": 120,
                "seed": 981301,
                "pools_path": str(path),
                "timeout_s": 120.0,
                "role_config": "missing-role-config",
                "role_probe": None,
                "selection_evidence": None,
                "protocol_evidence": None,
                "exclude_datasets": [],
                "exclude_pilots": [],
            }
        )
    )
    calls = []
    monkeypatch.setattr(script, "load_frozen_planner", lambda *a: calls.append("legacy"))
    result = script.run_ced_pilot(config, tmp_path / "dry", "selection")
    assert result["recorded_denominator"] == 480 and calls == []
    assert (
        result["actual_research_status"] == "NOT_RUN" and result["execution_mode"] == "NOT_EXECUTED"
    )


def test_foundation_missing_selection_keeps_groups_without_guessing_period(pools, tmp_path):
    result = api().run_pilot_stage("foundation", pools, tmp_path / "foundation")
    assert result["assigned_denominator"] == 120
    assert result["selected_period_s"] is None
    rows = json.loads((tmp_path / "foundation/assignments.json").read_text())
    assert len(rows) == 120 and all(row["period_s"] is None for row in rows)


def test_frozen_development_exclusions_reject_external_supplied_pool(pools, tmp_path, monkeypatch):
    import scripts.run_rgbd_pilot as script
    import yaml

    from cloud_edge_robot_arm.research.protocol import file_hash

    row = pools["foundation"][0]
    source = tmp_path / "used-assignment.json"
    source.write_text(json.dumps(row))
    payload = {
        "schema_version": "ced.excluded-groups.v1",
        "scope": "DEVELOPMENT_USED",
        "group_ids": [row["scene"]["group_id"]],
        "sources": [{"path": str(source), "sha256": file_hash(source), "kind": "assignment"}],
    }
    inventory = tmp_path / "exclusions.yaml"
    inventory.write_text(yaml.safe_dump({**payload, "content_hash": content_digest(payload)}))
    monkeypatch.setattr(script, "CED_EXCLUSION_INVENTORY", inventory, raising=False)
    supplied = tmp_path / "pools.json"
    supplied.write_text(json.dumps(pools))
    settings = {
        "exclude_datasets": [],
        "exclude_pilots": [],
        "pools_path": str(supplied),
        "seed": 981301,
    }
    with pytest.raises(ValueError, match="previously used"):
        script._ced_pools(settings)
