"""Software-only reviewer probes; no camera, physics, or product edits."""

import hashlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cloud_edge_robot_arm.research.step_rgbd import StepRGBDRecorder
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame


class FailFirstWrite:
    def __init__(self, stream):
        self.stream = stream
        self.once = True

    def write(self, value):
        if self.once:
            self.once = False
            raise OSError("qualified BEGIN journal failure")
        return self.stream.write(value)

    def flush(self):
        return self.stream.flush()

    def close(self):
        return self.stream.close()


def fixture(directory):
    state = {"episode": "episode", "time": 0.0, "calls": 0}

    def capture():
        state["calls"] += 1
        observation = observation_from_sensor_frame(
            SensorFrame(
                frame_id=f"frame-{state['calls']}",
                sim_time_s=state["time"],
                width=2,
                height=2,
                rgb=bytes([90, 110, 130]) * 4,
                depth=(0.5, 0.6, 0.7, 0.8),
                intrinsics=(2.0, 2.0, 0.5, 0.5),
                camera_to_world=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
                captured_at=datetime.now(UTC),
                episode_id=state["episode"],
                scene_id="scene",
                calibration_version="camera-calibration",
                valid_mask=b"\x01" * 4,
            ),
            source="mujoco_camera",
        )
        return observation, ("a" * 64,) * 2

    return StepRGBDRecorder(directory, capture, episode_id="episode"), state


def record(recorder, state, step):
    return recorder.record_step(
        episode_id=state["episode"], physics_step=step, sim_time_s=state["time"]
    )


results = {"scope": "SOFTWARE_ONLY", "rendering_or_physics": False}
source = Path("src/cloud_edge_robot_arm/research/step_rgbd.py")
results["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
with tempfile.TemporaryDirectory(prefix="step-rgbd-independent-") as temporary:
    root = Path(temporary)
    recorder, state = fixture(root / "begin-failure")
    recorder._index = FailFirstWrite(recorder._index)
    try:
        record(recorder, state, 0)
        first_error = None
    except OSError as error:
        first_error = f"{type(error).__name__}: {error}"
    calls_after_failure = state["calls"]
    record(recorder, state, 0)
    summary = recorder.finish(final_step=0, final_sim_time_s=0)
    results["begin_failure"] = {
        "first_error": first_error,
        "camera_calls_after_failure": calls_after_failure,
        "camera_calls_after_retry": state["calls"],
        "journal_events": [json.loads(line)["event"] for line in
                           (root / "begin-failure/index.jsonl").read_text().splitlines()],
        "summary": summary,
    }
    assert first_error and calls_after_failure == 0 and state["calls"] == 1
    assert summary["status"] == "COMPLETE" and summary["failed_captures"] == 1

    recorder, state = fixture(root / "mutable-gap")
    record(recorder, state, 0)
    recorder.max_sample_gap_s = 0.1
    state["time"] = 0.1
    record(recorder, state, 1)
    summary = recorder.finish(final_step=1, final_sim_time_s=0.1)
    results["mutable_gap"] = {"constructed_max_gap": 0.005, "summary": summary}
    assert summary["status"] == "COMPLETE" and summary["max_sim_sample_gap_s"] == 0.1

    recorder, state = fixture(root / "mutable-episode")
    record(recorder, state, 0)
    recorder.episode_id = "other"
    state.update(episode="other", time=1 / 240)
    record(recorder, state, 1)
    summary = recorder.finish(final_step=1, final_sim_time_s=1 / 240)
    events = [json.loads(line) for line in
              (root / "mutable-episode/index.jsonl").read_text().splitlines()]
    results["mutable_episode"] = {
        "constructed_episode": "episode",
        "begin_episode_ids": [event["episode_id"] for event in events if event["event"] == "BEGIN"],
        "summary": summary,
    }
    assert summary["status"] == "COMPLETE"
    assert results["mutable_episode"]["begin_episode_ids"] == ["episode", "other"]

assert results["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
Path(sys.argv[1]).write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps({"qualified": list(results)[3:], "source_sha256": results["source_sha256"]}))
