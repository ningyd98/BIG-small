"""Reject transplanted claims and inconsistent SQLite accounting without EGL."""

from pathlib import Path

import pytest
from read_active_checks_retest import (
    ASSIGNMENT,
    OWNER,
    PARENT_SHA,
    physical_reader,
    sqlite_accounting,
)


def test_fixed_assignment_and_parent_bind_claim(tmp_path):
    reader = physical_reader()
    release = tmp_path / OWNER / "release"
    release.mkdir(parents=True)
    protocol = dict(
        schema_version=reader.SCHEMA,
        scope=reader.SCOPE,
        assignment_id=ASSIGNMENT,
        seed=11920067,
        qualification_credit=0,
        step_wall_budget_ns=8_000_000_000,
        png_compress_level=1,
        first_action="MOVE_ABOVE",
        step_wall_budget_kind="ORIGINAL_POST_STEP_TIMEOUT",
        parent_source_freeze_sha256=PARENT_SHA,
        registration_directory=str(release),
        output=str(release / "run"),
        recipe=dict(
            scope=reader.SCOPE,
            released_assignments=[],
            assignments=[dict(assignment_id=ASSIGNMENT, seed=11920067)],
            settings=dict(png_compress_level=1),
            actions=[
                dict(skill="MOVE_ABOVE", original_timeout_ms=8000, horizon=dict(total_steps=1920)),
            ],
            role=dict(model_requests=0),
        ),
    )
    digest = reader.digest(protocol)
    claim = dict(
        assignment_id=ASSIGNMENT,
        scope=reader.SCOPE,
        seed=11920067,
        registration_sha256=digest,
        output=str(release / "run"),
    )
    assert reader.registration(protocol, claim, release) == digest
    with pytest.raises(ValueError, match="claim does not bind"):
        reader.registration(
            protocol, dict(claim, assignment_id="native-dev-whole-action-20261120-0001"), release
        )
    with pytest.raises(ValueError, match="foreign or changed"):
        reader.registration(dict(protocol, parent_source_freeze_sha256="0" * 64), claim, release)
    with pytest.raises(ValueError, match="directory differs"):
        reader.registration(protocol, claim, Path("/foreign"))


def test_sqlite_accounting_is_joined_to_timing_spans():
    receipt = dict(
        mode="UTC_LEGACY_VETO",
        reads_attempted=8,
        reads_completed=8,
        readonly_snapshots=8,
        read_wall_ns=220,
        action_reads_attempted=6,
        action_reads_completed=6,
        action_read_wall_ns=200,
    )
    timing = dict(span_count_by_label=dict(sqlite=8, owner_check=8))
    require = physical_reader().require
    assert sqlite_accounting(receipt, timing, require)["recorded_sqlite_spans"] == 8
    with pytest.raises(ValueError, match="original check spans"):
        sqlite_accounting(receipt, dict(span_count_by_label=dict(sqlite=7, owner_check=8)), require)
    with pytest.raises(ValueError, match="original check spans"):
        sqlite_accounting(dict(receipt, readonly_snapshots=7), timing, require)
    with pytest.raises(ValueError, match="invalid checkpoint counts"):
        sqlite_accounting(dict(receipt, reads_attempted=True), timing, require)
