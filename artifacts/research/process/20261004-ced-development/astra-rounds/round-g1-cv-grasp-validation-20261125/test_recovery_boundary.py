"""Independent controls for one-shot resensing before a registered PRE is issued."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from recovery_boundary import Acquisition, Boundary, Refused, check_stationary, still_sample


class Fixture:
    def __init__(self):
        self.clock = 10.0
        self.utc = datetime.now(UTC)
        self.key = ("gen", "job", "lease", 1, "task", "plan", 1, "MOVE_ABOVE", "episode")
        self.active_key = self.key
        self.log = []
        self.gate = Boundary(self.key, 11.0, lambda: self.clock, self.active)
        self.previous = self.event(1)
        self.first = self.event(2)
        self.second = self.event(3)
        self.first_measure = self.loss()
        self.next_measure = self.good()
        self.selected = {"offset_mm": 0}
        self.moving = False

    def active(self):
        self.log.append("owner+hard")
        return self.active_key

    def event(self, number):
        frame = SimpleNamespace(
            frame_id=f"f{number}",
            observation_id=f"f{number}",
            checksum_sha256=f"d{number}",
            scene_id="scene",
            episode_id="episode",
            source="mujoco_camera",
            calibration_version="cal",
            camera_to_world=(0.0,) * 16,
            intrinsics=(2.0,) * 4,
            captured_at=self.utc + timedelta(milliseconds=number),
            sim_time_s=number / 240,
        )
        return Acquisition(number, 9.0 + number / 240, 9.003 + number / 240, number, frame)

    @staticmethod
    def loss():
        return {
            "usable": False,
            "reason": "known_marker_not_observed",
            "observed_ids": [],
            "usable_ids": [],
            "selected_id": None,
        }

    @staticmethod
    def good():
        return {
            "usable": True,
            "reason": None,
            "observed_ids": [7, 8],
            "usable_ids": [7, 8],
            "selected_id": 7,
        }

    def perform(self):
        def read(event):
            self.log.append(("measure", event.number))
            return self.first_measure if event is self.first else self.next_measure

        def hold():
            self.log.append("hold")

        def stationary():
            self.log.append("measured_standstill")
            if self.moving:
                raise Refused("arm joints not settled")

        def capture():
            self.log.append("new_camera_capture")
            return self.second

        def fresh(event):
            self.log.append(("native_source_validation", event.number))

        def admit(event):
            self.log.append(("full_admission", event.number))
            if self.selected is None:
                raise Refused("current sweep has no CLEAR")
            return self.selected

        return self.gate.read(
            self.first,
            previous=self.previous,
            validate=fresh,
            measure=read,
            hold=hold,
            stationary=stationary,
            capture=capture,
            admit=admit,
        )


def test_no_loss_uses_one_frame_no_hold_or_recapture():
    f = Fixture()
    f.first_measure = f.good()
    assert f.perform() == f.selected
    assert "hold" not in f.log and "new_camera_capture" not in f.log
    assert ("full_admission", 2) in f.log


def test_only_one_new_camera_acquisition_and_full_admission():
    f = Fixture()
    assert f.perform() == f.selected
    assert (
        f.log.index("hold") < f.log.index("measured_standstill") < f.log.index("new_camera_capture")
    )
    assert f.log.count("new_camera_capture") == 1
    assert ("full_admission", 3) in f.log and ("full_admission", 2) not in f.log
    for label in ("native_source_validation", "measure"):
        assert (label, 2) in f.log and (label, 3) in f.log
    with pytest.raises(Refused, match="already"):
        f.perform()


@pytest.mark.parametrize(
    "why",
    [
        "foreign_marker_id",
        "duplicate_marker_id",
        "dual_marker_grasp_conflict",
        "registered_camera_mismatch",
        "marker_metric_depth_unavailable",
    ],
)
def test_hard_identity_and_depth_refusals_never_recapture(why):
    f = Fixture()
    f.first_measure = {**f.loss(), "reason": why}
    with pytest.raises(Refused, match=why):
        f.perform()
    assert "hold" not in f.log and "new_camera_capture" not in f.log


@pytest.mark.parametrize(
    "fault",
    [
        "still_lost",
        "replay",
        "relabelled_old",
        "changed_pose",
        "wrong_lease",
        "deadline",
        "moving",
        "sweep",
        "hard_collision",
    ],
)
def test_refusals_fail_closed(fault):
    f = Fixture()
    if fault == "still_lost":
        f.next_measure = f.loss()
    if fault == "replay":
        f.second = f.first
    if fault == "relabelled_old":
        f.second.frame.captured_at = f.first.frame.captured_at
    if fault == "changed_pose":
        f.second.frame.camera_to_world = (1.0,) * 16
    if fault == "wrong_lease":
        f.active_key = ("other", *f.key[1:])
    if fault == "deadline":
        f.clock = 11.0
    if fault == "moving":
        f.moving = True
    if fault == "sweep":
        f.selected = None
    if fault == "hard_collision":

        def hard():
            raise RuntimeError("ROBOT_HARD_SAFETY_STOP")

        f.gate.active = hard
    with pytest.raises((Refused, RuntimeError)):
        f.perform()
    assert f.gate.status == "REFUSED"
    assert f.log.count("new_camera_capture") <= 1


def test_stationarity_requires_three_distinct_measured_states_and_velocity_and_attitude():
    rows = [still_sample(i, i / 240, (0,) * 7, (0, 0, 0.30), (1, 0, 0, 0)) for i in (0, 8, 16)]
    assert check_stationary(rows)["max_arm_velocity_rad_s"] == 0
    for bad in (
        [rows[0]] * 3,
        [*rows[:2], replace(rows[2], joint_velocities=(0.021,) * 7)],
        [*rows[:2], replace(rows[2], tcp=(0, 0, 0.306))],
        [*rows[:2], replace(rows[2], quaternion=(0, 1, 0, 0))],
        [*rows[:2], replace(rows[2], joint_velocities=(float("nan"),) * 7)],
    ):
        with pytest.raises(Refused):
            check_stationary(bad)
