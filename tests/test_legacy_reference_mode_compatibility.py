"""Default-mode compatibility with real owner, source and SQLite lease checks."""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from tests.test_operational_windows import captured, exercise


def test_default_legacy_capture_and_observation_valid(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        assert runtime._operational_owner._startup.mode == "UTC_LEGACY_VETO"
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        assert module._check_reference(reference).status == "VALID"
        assert module._check_observation(observation, "condition", reference=reference) is True
        assert module._check_observation(observation, "condition") is True

    exercise(monkeypatch, tmp_path, run)


def test_default_legacy_observation_forgery_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        for changed in (
            {**reference, "window_id": "not-issued-r406"},
            {**reference, "source_identity": "0" * 64},
        ):
            assert module._check_reference(reference).status == "VALID"
            assert module._check_observation(observation, "condition", reference=reference) is True
            assert module._check_reference(changed).status == "UNKNOWN"
            assert module._check_observation(observation, "condition", reference=changed) is False
        assert module._check_observation(observation, "condition", reference=reference) is True
        assert module._check_observation(observation, "plan", reference=reference) is False
        other = observation.model_copy(update={"observation_id": "not-captured-r406"})
        assert module._check_observation(other, "condition", reference=reference) is False

    exercise(monkeypatch, tmp_path, run)


def test_default_legacy_live_utc_lease_revocation_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, worker, repo, job):
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        assert module._check_reference(reference).status == "VALID"
        assert module._check_observation(observation, "condition", reference=reference) is True
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute(
                "UPDATE simulation_jobs SET lease_expires_at=? WHERE job_id=?",
                ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), job.job_id),
            )
        assert module._check_reference(reference).status == "UNKNOWN"
        assert module._check_observation(observation, "condition", reference=reference) is False

    exercise(monkeypatch, tmp_path, run)


def test_unknown_live_owner_mode_still_rejected(monkeypatch, tmp_path):
    def run(module, runtime, raw, *args):
        observation = captured(runtime)
        reference = module._reference_for_observation(observation, "condition")
        owner = runtime._operational_owner
        original = owner._startup
        assert original.mode == "UTC_LEGACY_VETO"
        assert module._check_reference(reference).status == "VALID"
        assert module._check_observation(observation, "condition", reference=reference) is True
        try:
            owner._startup = replace(original, mode="UNSUPPORTED_R406")
            assert module._check_reference(reference).status == "UNKNOWN"
            assert module._check_observation(observation, "condition", reference=reference) is False
        finally:
            owner._startup = original
        assert module._check_reference(reference).status == "VALID"
        assert module._check_observation(observation, "condition", reference=reference) is True

    exercise(monkeypatch, tmp_path, run)
