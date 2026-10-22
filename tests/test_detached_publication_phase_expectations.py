"""R307 exact detached-summary phase expectations; doubles prove no live authority."""

import copy
import json

import pytest

from tests.test_operational_runtime_closure import _b_t2_detached_read


class _ReadOnlyRepository:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def read_local_publication(self, run_id):
        assert run_id == "fixture-run"
        return copy.deepcopy(self.rows)


def test_detached_summary_phase_contract():
    # Catches substring matching, unconditional target-presence expectations,
    # ignored SQL columns/phases, or detached summaries asserting live authority.
    target = "commit-seam:0"
    metadata = {"write_disposition": "HISTORICAL_ONLY", "confirmation_state": "UNKNOWN",
                "accepted": False, "live_authority": False}
    sql = {
        "operation_id": target, "operation_sha256": "a" * 64, "job_id": "fixture-job",
        "attempt": 1, "lease_id": "fixture-lease", "epoch": "fixture-epoch",
        "generation": 2, "row_revision": 3, "phase": "COMPLETE",
        "event_record_hash": "b" * 64, "event_receipt_hash": "c" * 64,
        "job_receipt_hash": "d" * 64, "payload_json": '{"source":"fixture"}',
    }
    unrelated = {**sql, **metadata, "operation_id": "setup-operation",
                 "payload_json": json.dumps({"operation_id": target})}
    prefix = {**sql, **metadata, "operation_id": target + ":different"}
    # The two independent EVENT_COMMITTED entries represent job/EVENT_COMMITTED
    # and event/COMPLETE; the last COMPLETE entry represents the live-owner case.
    phases = (None, "EVENT_COMMITTED", "EVENT_COMMITTED", "COMPLETE", "COMPLETE")
    for phase in phases:
        independent = [] if phase is None else [{**sql, "phase": phase}]
        target_rows = [{**row, **metadata} for row in independent]
        summary = [unrelated, prefix, *target_rows]
        repo = _ReadOnlyRepository(summary)
        before = copy.deepcopy(independent)
        returned = _b_t2_detached_read(
            repo, "fixture-run", target,
            expected_job_phase=phase, expected_job_rows=independent,
        )
        assert returned == summary
        assert independent == before
        returned[0]["payload_json"] = "caller mutation"
        returned.append({"caller_only": True})
        assert repo.read_local_publication("fixture-run") == summary

    good = {**sql, **metadata}
    invalid = [
        ([], "COMPLETE", [sql]),                         # missing target
        ([good, good], "COMPLETE", [sql]),               # duplicate target
        ([{**good, "phase": "EVENT_COMMITTED"}], "COMPLETE", [sql]),
        ([{**good, "operation_sha256": "e" * 64}], "COMPLETE", [sql]),
        ([good], None, []),                             # fabricated absent receipt
        ([], "COMPLETE", []),                           # no independent SQL row
        ([good], "COMPLETE", [sql, sql]),                # duplicate SQL target
        ([good], "COMPLETE", [{**sql, "operation_id": "other"}]),
        ([good], "PENDING", [sql]),                     # unsupported job phase
        ({target: good}, "COMPLETE", [sql]),             # wrong API shape
        ([123], "COMPLETE", [sql]),                     # wrong row shape
        ([unrelated, prefix], "COMPLETE", [sql]),        # nested/prefix ID cannot match
        ([{**good, "extra_column": "unobserved"}], "COMPLETE", [sql]),
        ([{key: value for key, value in good.items() if key != "job_id"}],
         "COMPLETE", [sql]),
    ]
    for summary, phase, independent in invalid:
        with pytest.raises(AssertionError):
            _b_t2_detached_read(
                _ReadOnlyRepository(summary), "fixture-run", target,
                expected_job_phase=phase, expected_job_rows=independent,
            )

    wrong_flags = [
        ("write_disposition", "NEW_COMMIT"),
        ("confirmation_state", "CONFIRMED"),
        ("accepted", True), ("accepted", 0),
        ("live_authority", True), ("live_authority", 0),
    ]
    for key, bad_value in wrong_flags:
        # An unrelated row must also be historical: checking only the target
        # would incorrectly allow authority elsewhere in the same summary.
        with pytest.raises(AssertionError):
            _b_t2_detached_read(
                _ReadOnlyRepository([{**unrelated, key: bad_value}, good]),
                "fixture-run", target, expected_job_phase="COMPLETE", expected_job_rows=[sql],
            )
    for key in metadata:
        missing = {name: value for name, value in good.items() if name != key}
        with pytest.raises(AssertionError):
            _b_t2_detached_read(
                _ReadOnlyRepository([missing]), "fixture-run", target,
                expected_job_phase="COMPLETE", expected_job_rows=[sql],
            )
    for forbidden in (
        {"write_disposition": "NEW_COMMIT"}, {"authorizes_effect": True},
        {"new_commit": True}, {"live_authority": True},
    ):
        with pytest.raises(AssertionError):
            _b_t2_detached_read(
                _ReadOnlyRepository([{**unrelated, "nested": [forbidden]}, good]),
                "fixture-run", target, expected_job_phase="COMPLETE", expected_job_rows=[sql],
            )
