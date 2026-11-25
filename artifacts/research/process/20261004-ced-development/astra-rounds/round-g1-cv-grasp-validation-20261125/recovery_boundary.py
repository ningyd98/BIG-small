"""One stationary recapture at an unissued G1 skill boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations


class Refused(ValueError):
    """A terminal qualification refusal for this boundary."""


@dataclass(frozen=True)
class Acquisition:
    number: int
    started: float
    finished: float
    step: int
    frame: object


def require_new(previous, current):
    old, new = previous.frame, current.frame
    if (
        current.number <= previous.number
        or current.started <= previous.finished
        or current.finished < current.started
        or current.step < previous.step
        or new.sim_time_s < old.sim_time_s
        or new.captured_at <= old.captured_at
        or new.frame_id == old.frame_id
        or new.checksum_sha256 == old.checksum_sha256
    ):
        raise Refused("repeated or nonmonotonic native acquisition")
    fields = (
        "scene_id",
        "episode_id",
        "source",
        "intrinsics",
        "camera_to_world",
        "calibration_version",
    )
    if any(getattr(new, key) != getattr(old, key) for key in fields):
        raise Refused("camera, calibration or scene identity changed")


@dataclass(frozen=True)
class StillSample:
    step: int
    sim_time_s: float
    joint_velocities: tuple
    tcp: tuple
    quaternion: tuple


def still_sample(step, sim_time, velocities, tcp, quaternion):
    return StillSample(step, sim_time, tuple(velocities), tuple(tcp), tuple(quaternion))


def check_stationary(rows):
    """Three live joint/TCP reads, one native 30 Hz period apart at 240 Hz."""
    if len(rows) != 3 or not all(
        b.step - a.step == 8 and math.isclose(b.sim_time_s - a.sim_time_s, 1 / 30, abs_tol=1e-9)
        for a, b in zip(rows[:-1], rows[1:], strict=True)
    ):
        raise Refused("three distinct native stationarity samples required")
    for row in rows:
        if (
            len(row.joint_velocities) != 7
            or len(row.tcp) != 3
            or len(row.quaternion) != 4
            or not all(math.isfinite(x) for x in (*row.joint_velocities, *row.tcp, *row.quaternion))
            or abs(math.hypot(*row.quaternion) - 1) > 1e-6
        ):
            raise Refused("invalid stationary telemetry")
    speed = max(abs(v) for row in rows for v in row.joint_velocities)
    dist = max(math.dist(a.tcp, b.tcp) for a, b in combinations(rows, 2))

    def angle(a, b):
        dot = abs(sum(x * y for x, y in zip(a.quaternion, b.quaternion, strict=True)))
        return math.degrees(2 * math.acos(min(1.0, dot)))

    angle_deg = max(angle(a, b) for a, b in combinations(rows, 2))
    # Existing native Cartesian entry and visual servo settlement limits.
    if speed > 0.02 or dist > 0.005 or angle_deg > 5:
        raise Refused("arm joints or TCP not settled")
    return {
        "max_arm_velocity_rad_s": speed,
        "max_tcp_displacement_m": dist,
        "max_tcp_rotation_deg": angle_deg,
        "sample_steps": [r.step for r in rows],
    }


class Boundary:
    """Single use. The caller owns native capture, geometry, Shield and action clock."""

    def __init__(self, identity, deadline, clock, active):
        self.identity = identity
        self.deadline = deadline
        self.clock = clock
        self.active = active
        self.status = "READY"
        self.recapture_count = 0

    def guard(self):
        if self.active() != self.identity:
            raise Refused("original task/lease/generation/command identity changed")
        if self.clock() >= self.deadline:
            raise Refused("original action deadline exhausted")

    def read(self, first, *, previous, validate, measure, hold, stationary, capture, admit):
        if self.status != "READY":
            raise Refused("boundary already consumed")
        self.status = "RUNNING"
        try:
            self.guard()
            validate(first)
            require_new(previous, first)
            observed = measure(first)
            if not observed["usable"]:
                if (
                    observed["reason"] != "known_marker_not_observed"
                    or observed["observed_ids"]
                    or observed["usable_ids"]
                    or observed["selected_id"] is not None
                ):
                    raise Refused(observed["reason"] or "ambiguous current measurement")
                self.guard()
                hold()
                stationary()
                self.guard()
                self.recapture_count = 1
                second = capture()
                validate(second)
                require_new(first, second)
                current = measure(second)
                if not current["usable"]:
                    raise Refused(current["reason"] or "new measurement unusable")
                first = second
            self.guard()
            result = admit(first)
            self.guard()
        except BaseException:
            self.status = "REFUSED"
            raise
        self.status = "ADMITTED"
        return result
