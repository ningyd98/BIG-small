"""End-to-end checks on the offline software comparison delivered with the thesis."""

import hashlib
import json
from importlib import import_module, util

import pytest


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    module = "scripts.graduation.decision_replay"
    assert util.find_spec(module), "missing graduation decision replay CLI"
    root = tmp_path_factory.mktemp("decision-replay") / "run"
    import_module(module).run(root)
    return root, json.loads((root / "decisions.public.json").read_bytes())


def test_risk_retains_unpredictable_rows_and_rejects_truth(replay):
    _, report = replay
    risk = report["risk"]
    assert risk["complete"]["split_allocations"] == {
        "train": 8,
        "calibration": 18,
        "selection": 4,
        "test": 2,
    }
    assert risk["complete"]["candidates"][0]["selection_brier"] == 0.25
    assert risk["eight_calibration_groups"]["status"] == "NO_FEASIBLE"
    assert risk["outside_support"]["split_allocations"]["selection"] == 4
    assert risk["outside_support"]["winner"] is None
    assert risk["truth_in_online_features"]["exception"] == "ValueError"


def test_actual_utf8_payloads_and_duplicate_billing(replay):
    root, report = replay
    cost = report["cost"]
    assert len(list(root.glob("payloads/*.json"))) == 3
    measured = 0
    for payload in cost["payloads"]:
        value = (root / payload["file"]).read_bytes()
        assert hashlib.sha256(value).hexdigest() == payload["sha256"]
        assert len(value) == payload["utf8_bytes"]
        measured += len(value)
    assert cost["ledger"]["summary"]["application_bytes"] == measured
    assert [x["sent_attempts_after"] for x in cost["events"]] == [1, 2, 2, 2, 2]
    assert cost["events"][-1]["exception"] == "ValueError"
    assert all(row["monetary_cost"] is None for row in cost["ledger"]["requests"])


def test_decision_and_action_horizon_controls(replay):
    _, report = replay
    choices = {row["case"]: row["action"] for row in report["policy"]}
    assert choices == {
        "low_risk": "CONTINUE",
        "high_risk": "REQUEST_CLOUD",
        "low_transfer_cost": "REQUEST_CLOUD",
        "high_transfer_cost": "CONTINUE",
        "no_accepted_selection": "STOP",
    }
    rows = report["completion_gate"]
    assert [row["joint"]["status"] for row in rows] == ["VALID", "INVALID", "UNKNOWN"]
    assert [row["b3"]["status"] for row in rows] == ["VALID", "VALID", "VALID"]


def test_candidate_scope_and_idempotent_submit_across_restart(replay):
    _, report = replay
    local, full = report["repair"]["paired"]
    assert local["actual_replaced_ids"] == ["verify"]
    assert full["actual_replaced_ids"] == ["verify", "telemetry"]
    for row in (local, full):
        assert row["activation"] == row["after_restart"] == "ACTIVATED"
        assert row["first_gateway_calls"] == ["stage", "resume"]
        assert row["restart_gateway_calls"] == []
        assert row["completed_nonrepeatable_in_pending"] == 0
        assert row["current_step"] == "repair-verify"
        assert row["execution_start_receipt"] is None
        assert row["stale_request"]["status"] == "REJECTED"
    assert local["input_sha256"] == full["input_sha256"]
    alias = report["repair"]["completed_effect_alias"]
    assert alias["status"] == "REJECTED" and alias["exception"] == "ValueError"
    replayed = report["repair"]["proposed_second_release"]
    assert replayed["outcome"] == "PLANNER_FAILED" and replayed["new_steps"] == []


def test_budget_exhausted_and_duplicate_are_distinct_after_restart(replay):
    _, report = replay
    rows = report["retry_budget"]
    assert [row["remaining"] for row in rows] == [2, 2, 1, 0, 0]
    assert [row["reason"] for row in rows] == [
        "OK",
        "EVENT_RETRY_ALREADY_CONSUMED",
        "OK",
        "OK",
        "RETRY_BUDGET_EXHAUSTED",
    ]


def test_rerun_never_rewrites_an_existing_receipt(replay):
    root, _ = replay
    before = (root / "decisions.public.json").read_bytes()
    with pytest.raises(FileExistsError):
        import_module("scripts.graduation.decision_replay").run(root)
    assert (root / "decisions.public.json").read_bytes() == before
