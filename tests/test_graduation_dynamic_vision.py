"""Software-only checks of the sealed development trace and its sampling windows."""

import pytest
from scripts.graduation.dynamic_vision_score import checked_steps, fixed_window, summarize_errors


def state(index, *, episode="dev"):
    return {"episode_id": episode, "physics_step": index, "sim_time_s": index / 240}


@pytest.mark.parametrize("sequence", [[0, 2], [0, 1, 1], [1, 2], []])
def test_missing_duplicate_or_absent_reset_is_rejected(sequence):
    with pytest.raises(ValueError):
        checked_steps([state(i) for i in sequence], "dev", "aa", "aa")


def test_wrong_episode_or_asset_cannot_join():
    with pytest.raises(ValueError):
        checked_steps([state(0, episode="other")], "dev", "aa", "aa")
    with pytest.raises(ValueError):
        checked_steps([state(0)], "dev", "aa", "bb")


def test_window_keeps_original_start_and_includes_both_endpoints():
    steps = {i: state(i) for i in range(130)}
    assert fixed_window(steps, 8, 120)["actual_samples"] == 121
    assert fixed_window(steps, 10, 120)["status"] == "INCOMPLETE"
    assert fixed_window(steps, None, 240)["status"] == "NOT_RUN"


def test_unknown_keeps_denominator_and_no_empirical_bound():
    value = summarize_errors([None, 0.003, None])
    assert value["frames"] == 3 and value["estimated"] == 1 and value["rejected"] == 2
    assert value["p90_m"] == 0.003
    assert summarize_errors([None])["p90_m"] is None


def test_frame_byte_tamper_detected_before_any_truth_join(tmp_path):
    from scripts.graduation.dynamic_vision_score import frame_from_row
    from scripts.graduation.perception_io import sha

    path = tmp_path / "frame.json"
    path.write_text("{}")
    row = {"file": path.name, "file_sha256": sha(path)}
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="SHA256"):
        frame_from_row(tmp_path, row, "episode", "scene", {})


def test_software_worker_obtains_one_real_lease_and_stops(tmp_path):
    from scripts.graduation.dynamic_vision import Owner

    alloc = {
        "case": {"visual_id": "software-only/r593", "visual_seed": 23110101},
        "intent_descriptor": {"type": "software"},
        "baseline": "a" * 40,
        "component_catalog_sha256": "b" * 64,
    }
    owner = Owner(tmp_path, alloc, "c" * 64)
    assert owner.current().attempt == 1
    summary = owner.close(False)
    assert summary["lease_released"] and summary["final_job_status"] == "FAILED"


def test_source_inventory_uses_the_registered_r593_prepare_catalog():
    from scripts.graduation.dynamic_vision import inventory

    from cloud_edge_robot_arm.research.native_calibration_collection import digest, source_inventory
    from cloud_edge_robot_arm.vision.marker_families import SIDE_PREPARE_ONLY_FAMILY as family

    selected = inventory()
    default = source_inventory(marker_family_id=family)
    v4 = source_inventory(
        marker_family_id=family, protocol_schema="native.calibration.operational.v4"
    )
    v5 = source_inventory(
        marker_family_id=family, protocol_schema="native.calibration.operational.v5"
    )
    assert selected == default == v4
    assert len(selected) == 456
    assert digest(v4) == "01f29ebf95837973d52c112d183e11a7abc361a750e42606f1811fad7c9ad04b"
    assert digest(v5) == "c8f48579e8ad7d3ce6efe5cf2b5bee3c96894ec69545997374c65fe6f3f7c519"
    assert "configs/research/native_operational_calibration_side_y_plus_75mm_r593.yaml" in v4
    assert (
        "configs/research/native_operational_calibration_side_y_plus_single_teacher_r595.yaml" in v5
    )
    assert "assets/robots/franka_panda/scene_pose_marker_side_y_plus_75mm_r593.xml" in v4
    with pytest.raises(ValueError, match="registered schema/family pair required"):
        source_inventory(
            marker_family_id=family, protocol_schema="native.calibration.operational.v10"
        )


def test_both_6000_step_source_clocks_accept_their_own_full_grid_and_reject_exchange():
    from scripts.graduation.dynamic_physics import validate_series

    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from tests.test_graduation_dynamic_physics import envelope

    canonical_dt = SimulatorConfig().physics_dt_s
    visual_dt = 1 / 240
    template = envelope(0)
    sequences = {}
    for key, dt in (("canonical", canonical_dt), ("vision", visual_dt)):
        elapsed = 0.0
        sequence = []
        for i in range(6001):
            sequence.append(
                {
                    **template,
                    "snapshot": {**template["snapshot"], "physics_step": i, "sim_time_s": elapsed},
                }
            )
            elapsed += dt
        sequences[key] = sequence
    canonical, vision = sequences["canonical"], sequences["vision"]
    assert len(validate_series(canonical, "case", "asset", "ep", 6000, canonical_dt)) == 6001
    assert len(checked_steps([r["snapshot"] for r in vision], "ep", "asset", "asset")) == 6001
    with pytest.raises(ValueError, match="registered clock"):
        validate_series(vision, "case", "asset", "ep", 6000, canonical_dt)
    with pytest.raises(ValueError, match="exactly cover"):
        checked_steps([r["snapshot"] for r in canonical], "ep", "asset", "asset")
    bad = [r["snapshot"] for r in vision]
    for wrong in ({"physics_step": 5999}, {"sim_time_s": 26.0}):
        with pytest.raises(ValueError, match="exactly cover"):
            checked_steps([*bad[:-1], {**bad[-1], **wrong}], "ep", "asset", "asset")
    assert canonical_dt * 6000 - visual_dt * 6000 == pytest.approx(2e-7, abs=1e-12)


def test_frozen_component_call_signatures_bind_no_actuation():
    import inspect

    from scripts.graduation import dynamic_vision as live

    dummy = object()
    calls = [
        (
            live.build_collection_contract_v2,
            0,
            "assignment current_owner geometry source_hashes observation protocol_settings",
        ),
        (live.validate_registration_handoff, 4, "step_before step_after now"),
        (
            live.bootstrap_registered_collection_tracker_v2,
            2,
            "source_root source_hashes nominal_policy",
        ),
        (
            live.registered_collection_step_v2,
            1,
            "index observation state tracker lease_source evidence_sink",
        ),
        (live.registered_expected_conditions_v2, 3, ""),
        (live.evaluate_registered_conditions_v2, 2, "grounding_inputs now"),
        (
            live.research_safety_shield().context_builder.build,
            0,
            "contract step robot_state scene_version resolved_parameters scene_updated_at "
            "telemetry_timestamp wall_clock_now step_started_at_mono task_started_at_mono "
            "monotonic_now requested_joint_velocities requested_velocity requested_acceleration "
            "vertical_clearance expected_holding_object_id",
        ),
        (live.research_safety_shield().pre_check, 1, ""),
        (live.research_safety_shield().post_check, 1, ""),
        (live.SkillExecutor.execute_attempt, 1, "contract step attempt"),
        (
            live.OpenCVServoFeedback,
            3,
            "skill initial_target marker_family_id verify_mujoco_calibration",
        ),
        (live.OpenCVServoFeedback.update, 2, ""),
        (live.VisualServoSession, 1, "vertical_clearance"),
    ]
    for function, positional, keywords in calls:
        inspect.signature(function).bind(
            *([dummy] * positional), **dict.fromkeys(keywords.split(), dummy)
        )
