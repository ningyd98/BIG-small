"""Opt-in worker reconstruction followed by the preregistered offline probe."""

import os
from copy import copy, deepcopy
from pathlib import Path

from probe_current_views import PHYSICS_STEP, diag, render_frozen
from tests.test_native_servo_region_replay import run_archived_native_protocol

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def test_reconstruct_and_probe_frozen_state(tmp_path, monkeypatch):
    destination = Path(os.environ["BIGSMALL_NATIVE_SERVO_REPLAY_DIR"]).resolve()
    preregistration = diag.read_json(destination.parent / "preregistration.json")
    probe_output = destination / "offline-probe"
    captures = []
    normal_capture = MuJoCoPhysicsBackend.capture_sensor_frame
    normal_shutdown = MuJoCoPhysicsBackend.shutdown

    def capture_at_boundary(self):
        frame = normal_capture(self)
        if self.total_physics_steps == PHYSICS_STEP:
            assert len(captures) < 3
            captures.append((copy(self._data), deepcopy(self._rng.bit_generator.state)))
        return frame

    def shutdown_and_probe(self):
        try:
            if self._data is not None and self.total_physics_steps == PHYSICS_STEP:
                episode = diag.read_json(destination / "component/episode.json")
                assert episode["executed_actions"] == 5
                assert episode["terminal_reason"] == "CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED"
                assert episode["actions"][-1]["visual_servo"]["terminal_reason"].endswith(
                    "region_missing_color_not_explained_by_foreground"
                )
                assert len(captures) == 3
                assert self.estop_engaged and len(self.command_records) > 0
                restore_hash = self._camera._physics_state_hash(self._data)
                commands_before = len(self.command_records)
                render_frozen(self, captures[-1], preregistration, probe_output)
                assert self._camera._physics_state_hash(self._data) == restore_hash
                assert len(self.command_records) == commands_before
        finally:
            normal_shutdown(self)

    monkeypatch.setattr(MuJoCoPhysicsBackend, "capture_sensor_frame", capture_at_boundary)
    monkeypatch.setattr(MuJoCoPhysicsBackend, "shutdown", shutdown_and_probe)
    result = run_archived_native_protocol(tmp_path, monkeypatch)
    assert result["worker_status"] == "FAILED" and result["physics_steps"] == PHYSICS_STEP
    report = diag.read_json(probe_output / "probe-result.json")
    assert report["elapsed_s"] < 120
    assert len(report["slots"]) == 8
