"""Checks for the retained one-attempt held-out acquisition readback."""

import pytest
from scripts.graduation import proposal_closed_loop_audit as audit


def test_every_assigned_case_must_have_a_distinct_episode_and_job():
    cases = [{"id": "g01"}, {"id": "g02"}]
    rows = [
        {"case_id": "g01", "episode_id": "a", "job_id": "ja"},
        {"case_id": "g02", "episode_id": "b", "job_id": "jb"},
    ]
    audit.check_denominator(cases, rows)
    for bad in (
        rows[:1],
        rows[::-1],
        [rows[0], {**rows[1], "episode_id": "a"}],
        [rows[0], {**rows[1], "job_id": "ja"}],
    ):
        with pytest.raises(ValueError, match="denominator"):
            audit.check_denominator(cases, bad)
