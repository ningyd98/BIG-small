"""Exercise pre-transport visibility recovery without advancing blind robot motion."""

import json


def test_worker_recovers_lift_marker_occlusion_with_current_camera_frame(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.vision.servo import OpenCVServoFeedback
    from tests.test_sol_molmo_worker_integration import (
        test_real_worker_runs_explicit_component_diagnostic_with_safety_and_physical_evidence,
    )

    original = OpenCVServoFeedback._marker_grasp
    injected = []

    def occluded_once(feedback, observation):
        # One explicit perception fault while physically lifting; the retry
        # must really capture and decode a different current view.
        if feedback.skill == "LIFT" and feedback.records and not injected:
            injected.append(observation.observation_id)
            return None
        return original(feedback, observation)

    monkeypatch.setattr(OpenCVServoFeedback, "_marker_grasp", occluded_once)
    test_real_worker_runs_explicit_component_diagnostic_with_safety_and_physical_evidence(
        tmp_path, monkeypatch, True, False, None, True,
    )
    episode = json.loads((tmp_path / "worker-run/component/episode.json").read_text())
    assert injected
    lift = next(action for action in episode["actions"] if action["skill"] == "LIFT")
    recovery = next(sample for sample in lift["visual_servo"]["visual_samples"]
                    if sample.get("camera_recovery"))
    assert recovery["camera_recovery"][0]["observation_id"] == injected[0]
    assert recovery["observation_id"] != injected[0]
    changes = [row for row in episode["camera_adjustments"]
               if row.get("step_id") == lift["step_id"]]
    assert changes and changes[0]["physics_step"] >= lift["start_step"]
    place = next(action for action in episode["actions"] if action["skill"] == "PLACE")
    overview = next(row for row in episode["camera_adjustments"]
                    if row["source"] == "CURRENT_MEASURED_PLACE_OVERVIEW")
    assert overview["step_id"] == place["step_id"]
    assert overview["physics_step"] == place["start_step"]
    first_place = place["visual_servo"]["visual_samples"][0]
    assert first_place["camera_position_m"] == overview["position_m"]
    assert max(sample["sample_and_ik_s"] for sample in
               lift["visual_servo"]["control_samples"]) <= 0.1
