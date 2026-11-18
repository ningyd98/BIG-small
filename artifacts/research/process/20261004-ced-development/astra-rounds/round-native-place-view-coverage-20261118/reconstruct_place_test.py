"""Verify the previous PLACE stop and run separately budgeted offline captures."""

import os
from copy import copy, deepcopy
from pathlib import Path

from probe_place_views import STEP, diag, render
from tests.test_native_servo_region_replay import run_archived_native_protocol

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend


def test_reconstruct_frozen_place_probe(tmp_path, monkeypatch):
    root = Path(os.environ["BIGSMALL_NATIVE_SERVO_REPLAY_DIR"]).resolve()
    preregistration = diag.read_json(root.parent / "preregistration.json")
    captures = []
    normal_capture = MuJoCoPhysicsBackend.capture_sensor_frame
    normal_shutdown = MuJoCoPhysicsBackend.shutdown

    def capture_at_boundary(self):
        frame = normal_capture(self)
        if self.total_physics_steps == STEP:
            assert len(captures) < 3
            captures.append((copy(self._data), deepcopy(self._rng.bit_generator.state)))
        return frame

    def shutdown_and_probe(self):
        try:
            if self._data is not None and self.total_physics_steps == STEP:
                episode = diag.read_json(root / "component/episode.json")
                assert episode["executed_actions"] == 6
                assert episode["terminal_reason"] == "CONTROLLER_FAILURE:VISUAL_SERVO_REJECTED"
                assert episode["actions"][-1]["skill"] == "PLACE"
                assert episode["actions"][-1]["visual_servo"]["terminal_reason"].endswith(
                    "region_missing_color_not_explained_by_foreground"
                )
                assert len(captures) == 3 and self.estop_engaged
                state = self._camera._physics_state_hash(self._data)
                command_count = len(self.command_records)
                render(self, *captures[-1], preregistration, root / "offline-probe")
                assert self._camera._physics_state_hash(self._data) == state
                assert len(self.command_records) == command_count
        finally:
            normal_shutdown(self)

    monkeypatch.setattr(MuJoCoPhysicsBackend, "capture_sensor_frame", capture_at_boundary)
    monkeypatch.setattr(MuJoCoPhysicsBackend, "shutdown", shutdown_and_probe)
    result = run_archived_native_protocol(tmp_path, monkeypatch)
    assert result["worker_status"] == "FAILED" and result["physics_steps"] == STEP
    report = diag.read_json(root / "offline-probe/probe-result.json")
    assert report["elapsed_s"] < 120
    assert len(report["slots"]) <= 2
