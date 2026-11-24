from types import SimpleNamespace

import pytest
from scripts.graduation import proposal_fault_recoverability as study
from scripts.graduation.proposal_fault_recoverability_score import check_actuators, measured_fault


def test_interleaved_cases_are_distinct_instances_of_one_scene():
    cases = [
        {"direction": 1, "teacher_case": "NORMAL"},
        {"direction": 1, "teacher_case": "NO_CONTACT"},
        {"direction": -1, "teacher_case": "NO_CONTACT"},
        {"direction": -1, "teacher_case": "NORMAL"},
    ]
    assert [c["ordinal"] for c in study.allocate_cases(cases)] == [1, 2, 3, 4]
    with pytest.raises(ValueError):
        study.allocate_cases([cases[0], *cases[0:3]])


def test_fault_evidence_uses_registered_direction_and_event_steps():
    states = [
        SimpleNamespace(physics_step=i, sim_time_s=i, object_position_m=[0, 0.020 - i * 0.010, 0])
        for i in range(3)
    ]
    fault = {
        "fault_type": "TARGET_MOTION",
        "parameters": {"direction_y": -1.0, "speed_m_s": 0.02, "duration_s": 1.0},
    }
    start = {
        "event": "TARGET_MOTION_STARTED",
        "physics_step": 1,
        "sim_time_s": 1,
        **fault["parameters"],
    }
    end = {"event": "TARGET_MOTION_FINISHED", "physics_step": 2, "sim_time_s": 2}
    assert measured_fault(states, [start, end], fault, 2)["signed_delta_y_m"] == -0.01
    with pytest.raises(ValueError):
        measured_fault(states, [{**start, "direction_y": 1}, end], fault, 2)
    with pytest.raises(ValueError):
        measured_fault(states, [start, end], fault, 1)


def test_pre_actuator_joins_every_step_to_the_previous_state():
    states = [SimpleNamespace(physics_step=i, sim_time_s=i / 240, episode_id="A") for i in range(3)]
    controls = [{"physics_step": i, "sim_time_s": (i - 1) / 240, "episode_id": "A"} for i in (1, 2)]
    check_actuators(states, controls)
    for rows in (
        controls[:1],
        [controls[0], controls[0]],
        [controls[0], {**controls[1], "episode_id": "B"}],
    ):
        with pytest.raises(ValueError):
            check_actuators(states, rows)


def test_unsupported_no_contact_failure_stays_in_denominator():
    rows = [
        {"ordinal": 1, "case": "NORMAL", "status": "PROVEN"},
        {"ordinal": 2, "case": "NO_CONTACT", "status": "REJECTED"},
        {"ordinal": 3, "case": "NO_CONTACT", "status": "REJECTED"},
        {"ordinal": 4, "case": "NORMAL", "status": "REJECTED"},
    ]
    assert study.count_cases(rows) == {
        "NORMAL": {"proven": 1, "allocated": 2},
        "NO_CONTACT": {"proven": 0, "allocated": 2},
    }
    with pytest.raises(ValueError):
        study.count_cases(rows[:-1])
