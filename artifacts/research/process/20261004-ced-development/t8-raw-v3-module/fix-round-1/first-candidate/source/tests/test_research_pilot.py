"""Pilot statistics retain all assignments and never invent a baseline."""

import pytest

from cloud_edge_robot_arm.research.pilot import PilotReport, derive_tcap


@pytest.mark.parametrize("durations,expected", [([63], 130), ([20], 120), ([400], 600)])
def test_tcap_rounds_and_clamps(durations, expected):
    assert derive_tcap(durations) == expected


def test_no_b0_success_blocks_tcap_freeze():
    with pytest.raises(ValueError, match="B0"):
        derive_tcap([])


def test_p99_uses_all_successes_not_maximum():
    assert derive_tcap([20] * 100 + [600]) == 120


def test_pilot_report_keeps_blocked_and_unexecuted_assignments():
    report = PilotReport(assigned=120, records=[{"success": False, "blocked": True}])
    assert report.summary()["assigned"] == 120
    assert report.summary()["success_rate_all_assigned"] == 0
    assert report.summary()["unrecorded"] == 119
    assert report.summary()["freeze_ready"] is False


@pytest.mark.parametrize("succeeded", [5, 120])
def test_complete_batch_cannot_claim_freeze_before_independent_evidence(succeeded):
    report = PilotReport(assigned=120, records=[
        {"success": index < succeeded, "blocked": False} for index in range(120)
    ])
    summary = report.summary()
    assert summary["unrecorded"] == 0
    assert summary["succeeded"] == succeeded
    # Even a perfect summary does not prove snapshots, fault traces or provenance.
    assert summary["freeze_ready"] is False
    assert summary["tcap_derivable"] is True


def test_freeze_cli_rejects_incomplete_or_non_b0_pilot(tmp_path):
    import json

    from scripts.freeze_rgbd_protocol import initial_spec_from_pilot

    (tmp_path / "summary.json").write_text(json.dumps({"assigned": 120, "recorded": 120,
        "succeeded": 1, "method_id": "T7_SMOKE", "freeze_ready": True}))
    with pytest.raises(ValueError, match="B0"):
        initial_spec_from_pilot(tmp_path)


def test_final_cost_publications_include_late_response_bytes(tmp_path):
    import json
    from datetime import UTC, datetime

    from scripts.run_rgbd_pilot import publish_final_costs

    from cloud_edge_robot_arm.research.cost_ledger import CostLedger, RequestCost

    ledger = CostLedger()
    now = datetime.now(UTC)
    request = RequestCost(request_id="late", sent_at=now, finished_at=None,
        is_cloud_model=True, model_role="SUPERVISOR", deployment="CLOUD",
        provider_location="LOCAL_HOST", provider_version="fixture", status="IN_FLIGHT",
        serialized_sent_bytes=100, serialized_received_bytes=0)
    ledger.record_request(request)
    report = PilotReport(assigned=1, records=[{"assignment_id": "case-1",
                                            "costs": ledger.snapshot().model_dump()}])
    ledger.record_request(request.model_copy(update={"finished_at": datetime.now(UTC),
                         "status": "SUCCESS", "serialized_received_bytes": 40}))
    directory = tmp_path / "case-1"
    directory.mkdir()
    assert publish_final_costs(report, [(ledger, directory)], settle_timeout_s=.1) == 0
    final = json.loads((directory / "costs.json").read_text())
    published = json.loads((directory / "case-result.json").read_text())
    assert report.records[0]["costs"]["application_bytes"] == 140
    assert published["costs"] == final["summary"] == report.records[0]["costs"]


def test_forged_ready_summary_without_raw_evidence_is_rejected(tmp_path):
    import json

    from scripts.freeze_rgbd_protocol import initial_spec_from_pilot

    (tmp_path / "summary.json").write_text(json.dumps({"method_id": "B0", "assigned": 120,
        "recorded": 120, "freeze_ready": True, "protocol_snapshot_complete": True,
        "tcap_s": 120, "baseline_feasibility": "FEASIBLE"}))
    with pytest.raises(OSError):
        initial_spec_from_pilot(tmp_path)
