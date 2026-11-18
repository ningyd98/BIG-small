"""Exercise the review's capture callback faults on actual fixed-02 RGBD."""

import inspect
import sys
from datetime import datetime
from pathlib import Path

import pytest

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "round-native-place-view-coverage-20261118"))
from probe_place_views import context, diag  # noqa: E402

RAW = Path("experiments/results/phase9/real-harness-20261118/native/fixed-02")


class RecordedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.captured_at


@pytest.mark.parametrize("fault", [None, "wrong_cam_advanced", "wrong_yaw", "advanced", "reverse",
                                    "reused_id", "same_view", "forged_calibration",
                                    "old_calibration", "bigendian"])
def test_real_fixed02_recovery_requires_bound_pose_time_and_calibration(monkeypatch, fault):
    import hashlib
    import struct

    family, _, tracker = context(RAW)
    evidence = diag.read_json(RAW/"planning/planning-stage-02.json")["attempts"][0][
        "draft"
    ]["observation_evidence"]
    episode = diag.read_json(RAW/"component/episode.json")
    is_place = fault in {None, "forged_calibration", "old_calibration", "bigendian"}
    step, names = (
        ("step-06", ("sample-0014-view-02", "sample-0015", "sample-0015-view-01"))
        if is_place else ("step-05", ("sample-0104", "sample-0105", "sample-0105-view-02"))
    )
    folder = RAW/"component/servo-frames"/step
    reference, first, good = (diag.load_frame(folder/name) for name in names)
    action = next(a for a in episode["actions"] if a["step_id"] == step)
    xyz = tuple(good.camera_to_world[i] for i in (3, 7, 11))
    aim = next(tuple(a["look_at_m"]) for a in episode["camera_adjustments"]
               if tuple(a.get("position_m", ())) == xyz)
    if fault == "wrong_cam_advanced":
        expected = diag.load_frame(folder/"sample-0105-view-01")
        xyz = tuple(expected.camera_to_world[i] for i in (3, 7, 11))
        aim = next(tuple(a["look_at_m"]) for a in episode["camera_adjustments"]
                   if tuple(a.get("position_m", ())) == xyz)
    view = xyz, aim
    modified = good
    edits = {}
    if fault == "wrong_cam_advanced":
        modified = diag.load_frame(folder/"sample-0106")
    elif fault == "wrong_yaw":
        view = xyz, (aim[0] + 0.03, *aim[1:])
    elif fault == "advanced":
        edits["sim_time_s"] = first.sim_time_s + 1 / 30
    elif fault == "reverse":
        edits["sim_time_s"] = first.sim_time_s - 1 / 240
    elif fault == "reused_id":
        edits.update(frame_id=first.frame_id, observation_id=first.observation_id)
    elif fault == "same_view":
        modified = first
        edits.update(frame_id=good.frame_id, observation_id=good.observation_id)
    elif fault == "forged_calibration":
        edits["calibration_version"] = "1111111111111111"
    elif fault == "old_calibration":
        edits["calibration_version"] = reference.calibration_version
    elif fault == "bigendian":
        edits["calibration_version"] = hashlib.sha256(struct.pack(
            ">20d", *good.intrinsics, *good.camera_to_world,
        )).hexdigest()[:16]
    if edits:
        modified = RGBDObservation.model_validate(
            modified.model_dump() | edits | {"checksum_sha256": ""},
        )
    RecordedClock.captured_at = reference.captured_at
    monkeypatch.setattr("cloud_edge_robot_arm.vision.servo.datetime", RecordedClock)
    opts = {}
    if "verify_mujoco_calibration" in inspect.signature(OpenCVServoFeedback).parameters:
        opts["verify_mujoco_calibration"] = True
    provider = OpenCVServoFeedback(
        reference, tracker, evidence, skill=action["skill"],
        initial_target=Pose(**action["resolved_step"]["parameters"]["target_pose"]),
        marker_family_id=family.family_id, **opts,
    )

    def capture(attempt):
        frame = (first, modified)[attempt]
        RecordedClock.captured_at = frame.captured_at
        return frame

    def run():
        return provider.update_with_camera_views(
            capture, lambda *_: None, [view], prioritize=lambda *_: [view],
            allow_marker_depth_reobserve=is_place,
        )

    if fault is None:
        run()
        assert provider.last_observation.observation_id == good.observation_id
        assert len(provider.records) == 1
    else:
        try:
            run()
        except ValueError:
            assert provider.last_observation is reference and provider.records == []
        else:
            pytest.fail(f"accepted {fault} as recovery: {provider.last_observation.evidence()}")
