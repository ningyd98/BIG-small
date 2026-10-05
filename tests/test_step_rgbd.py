"""Software collection regressions; no renderer, physics or admission."""

import gzip
import json
from datetime import UTC, datetime
from importlib import import_module, util

import pytest

from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.vision.observations import (
    RGBDObservation,
    observation_from_sensor_frame,
)


def api():
    assert util.find_spec("cloud_edge_robot_arm.research.step_rgbd") is not None, (
        "whole-step lossless RGB-D recorder is missing"
    )
    return import_module("cloud_edge_robot_arm.research.step_rgbd")


def observation(step, *, episode_id="episode"):
    return observation_from_sensor_frame(
        SensorFrame(
            frame_id=f"frame-{step}",
            sim_time_s=step / 240,
            width=2,
            height=2,
            rgb=bytes([90, 110, 130]) * 4,
            depth=(0.5, 0.6, 0.7, 0.8),
            intrinsics=(2.0, 2.0, 0.5, 0.5),
            camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
            captured_at=datetime.now(UTC),
            episode_id=episode_id,
            scene_id="scene",
            calibration_version="camera-calibration",
            valid_mask=b"\x01" * 4,
        ),
        source="mujoco_camera",
    )


def fixture(tmp_path, *, capture_override=None):
    captured = []

    def capture():
        step = len(captured)
        value = observation(step)
        captured.append(value)
        return value, ("a" * 64,) * 2

    recorder = api().StepRGBDRecorder(
        tmp_path / "series",
        capture_override or capture,
        episode_id="episode",
    )
    return recorder, captured


def record(recorder, step, *, episode_id="episode", sim_time_s=None):
    return recorder.record_step(
        episode_id=episode_id,
        physics_step=step,
        sim_time_s=step / 240 if sim_time_s is None else sim_time_s,
    )


def test_full_horizon_has_lossless_original_frames_and_paired_capture_clocks(tmp_path):
    recorder, captured = fixture(tmp_path)
    for step in range(4):
        row = record(recorder, step)
        restored = RGBDObservation.model_validate_json(
            gzip.decompress((tmp_path / "series" / row["file"]).read_bytes())
        )
        assert restored == captured[-1]
        assert row["monotonic_end_ns"] >= row["monotonic_begin_ns"]
        assert row["observation_checksum_sha256"] == restored.checksum_sha256
    summary = recorder.finish(final_step=3, final_sim_time_s=3 / 240)
    assert summary["status"] == "COMPLETE"
    assert summary["allocated_steps"] == summary["completed_captures"] == 4
    assert summary["continuous_motion"] == "NOT_CERTIFIED"
    assert summary["formal_accepted"] is False


@pytest.mark.parametrize(
    "step,episode,stamp",
    [
        (2, "episode", 2 / 240),
        (1, "other", 1 / 240),
        (1, "episode", 0),
        (1, "episode", 0.1),
        (True, "episode", 1 / 240),
    ],
)
def test_missing_step_wrong_episode_or_original_gap_reject_before_capture(
    tmp_path,
    step,
    episode,
    stamp,
):
    recorder, captured = fixture(tmp_path)
    record(recorder, 0)
    with pytest.raises(ValueError):
        record(recorder, step, episode_id=episode, sim_time_s=stamp)
    assert len(captured) == 1
    with pytest.raises(RuntimeError):
        record(recorder, 1)
    assert len(captured) == 1


@pytest.mark.parametrize("kind", ["pass", "frame_episode", "frame_time"])
def test_mismatched_render_pass_or_original_frame_is_saved_as_failed(tmp_path, kind):
    def capture():
        value = observation(
            1 if kind == "frame_time" else 0,
            episode_id="other" if kind == "frame_episode" else "episode",
        )
        return value, ("a" * 64, ("b" if kind == "pass" else "a") * 64)

    recorder, _ = fixture(tmp_path, capture_override=capture)
    with pytest.raises(ValueError):
        record(recorder, 0)
    events = [
        json.loads(line) for line in (tmp_path / "series/index.jsonl").read_text().splitlines()
    ]
    assert [row["event"] for row in events] == ["BEGIN", "FAILED"]
    summary = recorder.finish(final_step=0, final_sim_time_s=0)
    assert summary["status"] == "INCOMPLETE"
    assert summary["attempted_captures"] == 1 and summary["completed_captures"] == 0


def test_capture_failure_is_retained_and_cannot_be_retried(tmp_path):
    calls = []

    def capture():
        calls.append("called")
        raise OSError("camera failure")

    recorder, _ = fixture(tmp_path, capture_override=capture)
    with pytest.raises(OSError, match="camera failure"):
        record(recorder, 0)
    with pytest.raises(RuntimeError):
        record(recorder, 0)
    assert len(calls) == 1
    summary = recorder.finish(final_step=0, final_sim_time_s=0)
    assert summary["status"] == "INCOMPLETE"
    assert summary["failed_captures"] == 1


@pytest.mark.parametrize("final_step", [1, 3])
def test_declared_short_or_missing_terminal_cannot_complete(tmp_path, final_step):
    recorder, _ = fixture(tmp_path)
    for step in range(3):
        record(recorder, step)
    summary = recorder.finish(final_step=final_step, final_sim_time_s=final_step / 240)
    assert summary["status"] == "INCOMPLETE"


def test_existing_collection_is_never_overwritten(tmp_path):
    fixture(tmp_path)
    with pytest.raises(FileExistsError):
        fixture(tmp_path)


@pytest.mark.parametrize("always_fail", [False, True])
def test_first_journal_error_stops_before_camera_and_cannot_be_retried(tmp_path, always_fail):
    recorder, captured = fixture(tmp_path)
    original = recorder._index

    class FailedJournal:
        failures = 0

        def write(self, value):
            self.failures += 1
            if always_fail or self.failures == 1:
                raise OSError("initial journal failure")
            return original.write(value)

        def flush(self):
            original.flush()

        def close(self):
            original.close()

    recorder._index = FailedJournal()
    with pytest.raises(OSError, match="initial journal failure"):
        record(recorder, 0)
    with pytest.raises(RuntimeError):
        record(recorder, 0)
    assert captured == []
    summary = recorder.finish(final_step=0, final_sim_time_s=0)
    assert summary["status"] == "INCOMPLETE"
    assert summary["capture_calls_started"] == 0
    assert "initial journal failure" in summary["reason"]


def test_original_gap_cannot_be_mutated_after_registration(tmp_path):
    recorder, captured = fixture(tmp_path)
    record(recorder, 0)
    with pytest.raises(AttributeError):
        recorder.max_sample_gap_s = 0.1
    with pytest.raises(ValueError):
        record(recorder, 1, sim_time_s=0.1)
    assert len(captured) == 1


def test_original_episode_cannot_be_mutated_between_frames(tmp_path):
    recorder, _ = fixture(tmp_path)
    record(recorder, 0)
    with pytest.raises(AttributeError):
        recorder.episode_id = "other"
    record(recorder, 1)
    assert recorder.finish(final_step=1, final_sim_time_s=1 / 240)["status"] == "COMPLETE"
