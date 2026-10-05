"""CPU replay tests: source upcoming-step semantics, no real execution calls."""

from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import json
import os
from functools import lru_cache
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "t7b-continuous-visibility"
BASE_SHA = "19225d13e058cb428b8cf3a99095bde6b46bfd985bcb3290e4824fdd4b0b4e6f"
PREFIX_ERRORS = ("CONTROL/PHYSICS association", "CONTROL/actuator/PHYSICS/acquisition")


@lru_cache
def baseline():
    path = PRIOR / "verify_offline.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASE_SHA
    return load(path, "frozen_upcoming_step_baseline")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rows(directory):
    with gzip.open(directory / "nominal-journal.jsonl.gz", "rt") as stream:
        return [json.loads(line) for line in stream]


def write_rows(directory, records):
    for sequence, row in enumerate(records, 1):
        row["record_seq"] = sequence
    (directory / "nominal-journal.jsonl.gz").write_bytes(
        gzip.compress(b"".join(json.dumps(row).encode() + b"\n" for row in records), mtime=0)
    )


def upcoming_attempt(directory, corruption=None):
    """Reuse the bounded fake trace; change only its incorrect actuator domain."""
    baseline().synthetic_attempt(directory, corruption)
    records = rows(directory)
    for row in records:
        if row["event"] == "ACTUATOR":
            row["source"]["physics_step"] += 1
    write_rows(directory, records)


def verify(directory, output):
    if os.environ.get("UPCOMING_STEP_RED_BASELINE") == "1":
        # The frozen reader writes derived files beside input. Isolate those writes
        # while qualifying its bug against the exact immutable input bytes.
        output.mkdir()
        for name in ("whole-step", "summary.json", "terminal.json", "nominal-journal.jsonl.gz"):
            (output / name).symlink_to((directory / name).resolve())
        return baseline().verify_attempt(output, decode=False)
    reader = load(HERE / "verify_offline.py", "upcoming_step_reader_v2")
    return reader.verify_attempt(directory, output_directory=output, decode=False)


def hashes(directory):
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def assert_authority_closed(report):
    assert report["source_authenticity"] == "UNKNOWN"
    assert report["formal_accepted"] is False
    assert report["native_admission"] == "NOT_PROMOTED"
    assert report["continuous_motion"] == "NOT_CERTIFIED"
    assert report["future_stability"] == "UNAVAILABLE"
    assert report["calibrated_error_bound"] == "UNAVAILABLE"
    assert report["external_utc_uncertainty"] == "UNAVAILABLE"


def test_real_failed_prefix_has_upcoming_step_join_without_false_errors(tmp_path):
    actual = PRIOR / "attempt-1"
    before = hashes(actual)
    report = verify(actual, tmp_path / "derived")
    assert hashes(actual) == before
    assert report["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert (
        report["allocated_steps"],
        report["verified_frames"],
        report["failed_or_missing_frames"],
    ) == (
        11,
        10,
        1,
    )
    assert report["original_action_begins"] == report["original_action_ends"] == 0
    assert report["original_max_sample_gap_s"] == 0.005
    assert report["max_sim_sample_gap_s"] <= 0.005
    assert any("step 10: missing saved acquisition" in error for error in report["failures"])
    assert not [
        error for error in report["failures"] if any(kind in error for kind in PREFIX_ERRORS)
    ]
    assert_authority_closed(report)


def test_minimal_upcoming_step_trace_has_exact_nominal_join(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    upcoming_attempt(source)
    before = hashes(source)
    report = verify(source, tmp_path / "output")
    assert hashes(source) == before
    assert report["integrity_status"] == "VERIFIED", report["failures"]
    assert report["allocated_steps"] == report["verified_frames"] == 3
    assert report["original_action_begins"] == report["original_action_ends"] == 1
    assert_authority_closed(report)


@pytest.mark.parametrize(
    "kind",
    (
        "saved_payload_identity",
        "terminal_episode",
        "terminal_time",
        "action_ownership",
        "acquisition_episode",
        "camera_step",
        "final_physics_time",
        "overlapping_actions",
        "camera_capture_clock",
    ),
)
def test_prior_binding_counterexamples_stay_unavailable(tmp_path, kind):
    source = tmp_path / "input"
    source.mkdir()
    upcoming_attempt(source)
    if kind.startswith("terminal_"):
        path = source / "terminal.json"
        terminal = json.loads(path.read_text())
        key, value = (
            ("episode_id", "unrelated-episode")
            if kind == "terminal_episode"
            else ("final_sim_time_s", 9.0)
        )
        terminal[key] = value
        path.write_text(json.dumps(terminal))
    else:
        rewritten = []
        for row in rows(source):
            if row["event"] == "ACQUISITION_END" and row["physics_step"] == 1:
                if kind == "saved_payload_identity":
                    row["saved"].update(
                        observation_id="unrelated-frame",
                        observation_checksum_sha256="b" * 64,
                        file="frames/unrelated.json.gz",
                    )
                elif kind == "camera_step":
                    for state in ("before_state", "after_state"):
                        row["camera"][state]["physical_step"] = 99
                elif kind == "camera_capture_clock":
                    row["camera"]["capture_monotonic_end_ns"] = row["saved"]["monotonic_end_ns"] + 1
            if (
                row["event"] in {"ACQUISITION_BEGIN", "ACQUISITION_END"}
                and row["physics_step"] == 1
            ):
                if kind == "action_ownership":
                    row["action_ordinal"] = None
                elif kind == "acquisition_episode":
                    row["episode_id"] = "unrelated-episode"
            if (
                kind == "final_physics_time"
                and row["event"] == "OPERATION"
                and row["source"]["kind"] == "PHYSICS"
                and row["source"]["phase"] == "END"
                and row["source"]["physics_step"] == 2
            ):
                row["source"]["result"]["physics_state"]["sim_time_s"] = 9.0
            rewritten.append(row)
            if kind == "overlapping_actions" and row["event"] in {
                "ACTION_BEGIN",
                "ACTION_END",
                "TEACHER_ACTION",
            }:
                duplicate = copy.deepcopy(row)
                duplicate["action_ordinal"] = 2
                duplicate["clock"]["monotonic_before_ns"] = duplicate["clock"]["monotonic_after_ns"]
                rewritten.append(duplicate)
        write_rows(source, rewritten)
        if kind == "overlapping_actions":
            path = source / "summary.json"
            summary = json.loads(path.read_text())
            summary.update(action_begins=2, action_ends=2)
            path.write_text(json.dumps(summary))
    report = verify(source, tmp_path / "output")
    assert report["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert report["failures"]
    assert report["allocated_steps"] == report["verified_frames"] == 3
    assert_authority_closed(report)


@pytest.mark.parametrize(
    "corruption", ("missing_acquisition_begin", "physics_begin", "command_span")
)
def test_missing_original_boundaries_stay_unavailable(tmp_path, corruption):
    source = tmp_path / "input"
    source.mkdir()
    upcoming_attempt(source, corruption)
    report = verify(source, tmp_path / "output")
    assert report["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert report["allocated_steps"] == 3
    assert_authority_closed(report)


def test_preceding_step_actuator_domain_cannot_verify(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    baseline().synthetic_attempt(source)
    report = verify(source, tmp_path / "output")
    assert report["integrity_status"] == "INCOMPLETE_OR_INVALID"
    assert any(any(kind in error for kind in PREFIX_ERRORS) for error in report["failures"])
    assert_authority_closed(report)


@pytest.mark.parametrize("nested", (False, True))
def test_output_cannot_modify_input_directory(tmp_path, nested):
    source = tmp_path / "input"
    source.mkdir()
    upcoming_attempt(source)
    before = hashes(source)
    output = source / "derived" if nested else source
    reader = load(HERE / "verify_offline.py", "output_guard_reader_v2")
    with pytest.raises(ValueError, match="outside input"):
        reader.verify_attempt(source, output_directory=output, decode=False)
    assert hashes(source) == before
