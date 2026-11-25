from types import SimpleNamespace

import pytest
from scripts.graduation import g1_complete_trials as trials


def test_independent_release_requires_native_success_and_full_feedback():
    record = {
        "runtime_build_sha256": "a" * 64,
        "calibration_sha256": "b" * 64,
        "receipt_sha256": "c" * 64,
        "qualified": True,
        "complete_feedback_ok": True,
        "result": {"dispatched_skills": []},
    }
    with pytest.raises(ValueError):
        trials.training_gate([record, record], "a" * 64, "b" * 64)


def test_each_scope_keeps_registration_order_and_is_single_use():
    reg = {
        "slots": [
            {"id": "a", "scope": "training"},
            {"id": "b", "scope": "training"},
            {"id": "c", "scope": "independent_development"},
            {"id": "d", "scope": "independent_development"},
        ]
    }
    assert [r["id"] for r in trials.select_slots(reg, "evaluation")] == ["c", "d"]
    assert [r["id"] for r in trials.select_slots(reg, "train-002")] == ["a", "b"]
    with pytest.raises(ValueError):
        trials.select_slots(reg, "evaluation-retry")


def test_registration_cannot_overwrite_or_substitute_a_fixture(tmp_path):
    path = tmp_path / "registration.json"
    trials.write_once(path, {"slots": [1, 2]})
    trials.write_once(path, {"slots": [1, 2]})
    with pytest.raises(ValueError):
        trials.write_once(path, {"slots": [2, 1]})


@pytest.mark.parametrize("preflight", [False, True])
def test_pre_clearance_stop_keeps_original_admission_records(monkeypatch, preflight):
    from scripts.graduation import g1_complete_worker as worker

    episode = object.__new__(worker.ClearanceEpisode)
    episode.preflight = preflight
    episode.approach_diagnostic = False
    events = []
    step = SimpleNamespace(
        skill=SimpleNamespace(value="MOVE_ABOVE"), parameters={"target_pose": {}}
    )
    frame = object()

    def native_shield(self, observation, phase, contract, step, started, clearance):
        events.append("native_shield")
        return {"allowed": True, "unmodified": True}

    def native_admission(self, observation, phase, contract, step, binding, started, clearance):
        self.check_shield(observation, phase, contract, step, started, clearance)
        events.append("native_action_pre_and_conditions")

    def local(observation, skill, target, phase):
        assert observation is frame and phase == "PRE" and skill == "MOVE_ABOVE"
        events.append("local_pre")
        if not preflight:
            raise worker.native.ComponentStopped("intrusion")

    monkeypatch.setattr(worker.TranslatedEpisode, "check_shield", native_shield)
    monkeypatch.setattr(worker.TranslatedEpisode, "admission", native_admission)
    episode.check_current = local
    with pytest.raises(worker.native.ComponentStopped):
        episode.admission(frame, "PRE", None, step, None, 1, None)
    assert events == ["native_shield", "native_action_pre_and_conditions", "local_pre"]


def test_continuous_grasp_inherits_real_joint_motion_and_freezes_entry_setpoint():
    from scripts.graduation import g1_complete_worker as worker

    episode = object.__new__(worker.ClearanceEpisode)
    episode.entry_command = None
    episode.report = {"actions": [{}, {"skill": "APPROACH", "status": "PASS", "end_step": 1392}]}
    backend = SimpleNamespace(
        total_physics_steps=1392,
        next_command_sequence=259,
        _data=SimpleNamespace(ctrl=[0.4] * 7 + [0.039, 0.039]),
        _target_positions=[0.31] * 7,
        _gripper_open=True,
        get_joint_command_state=lambda: SimpleNamespace(velocity_rad_s=[0.0] * 7),
    )
    episode.backend = backend
    robot = dict(
        joint_positions_rad=[0.3] * 7,
        joint_velocities_rad_s=[0.0, 0.09] + [0.0] * 5,
        finger_positions_m=[0.039] * 2,
        finger_velocities_m_s=[0.0, 0.0],
    )
    frame = SimpleNamespace(frame_id="fresh", checksum_sha256="abc")
    first = episode.command_handoff("GRASP", "PRE", robot, frame)
    assert first["entry_joint_velocities_rad_s"][1] == 0.09
    assert first["entry_effective_arm_goal_rad"] == [0.31] * 7
    assert first["entry_native_arm_velocity_rad_s"] == [0.0] * 7
    assert first["entry_gripper_open"] is True
    assert first["entry_step"] == first["prior_end_step"] == first["current_step"] == 1392
    backend.total_physics_steps += 8
    backend.next_command_sequence += 1
    backend._data.ctrl[7:9] = [0.0, 0.0]
    later = episode.command_handoff("GRASP", "FEEDBACK", robot, frame)
    assert later["entry_finger_target_m"] == [0.039, 0.039]
    assert later["effective_finger_target_m"] == [0.0, 0.0]
    assert later["entry_command_seq"] + 1 == later["last_command_seq"]
    with pytest.raises(ValueError, match="physical step"):
        episode.command_handoff("GRASP", "PRE", robot, frame)


def test_optical_identity_comes_from_successful_independent_reset():
    from scripts.graduation.g1_complete_worker import native_reset_ids

    base = dict(
        kind="RESET",
        physics_step=0,
        sim_time_s=0,
        operation_id=5,
        parameters={"requested": {"scenario_id": "allocated/one"}},
        error=None,
        error_type=None,
    )
    first = base | dict(phase="BEGIN", episode_id=None)
    last = base | dict(phase="END", episode_id="reset-episode", result={"physics_dt_s": 1 / 240})
    assert native_reset_ids([first, last], "allocated/one", "reset-episode") == (
        "allocated/one",
        "reset-episode",
    )
    for wrong in (
        last | {"episode_id": "other"},
        last | {"operation_id": 6},
        last | {"physics_step": 1},
        last | {"phase": "BEGIN"},
    ):
        with pytest.raises(ValueError, match="reset"):
            native_reset_ids([first, wrong], "allocated/one", "reset-episode")
    with pytest.raises(ValueError, match="reset"):
        native_reset_ids([first, last], "allocated/two", "reset-episode")


def test_passive_support_uses_actual_return_and_accepted_gripper_command():
    from scripts.graduation.g1_complete_worker import ClearanceEpisode

    episode = object.__new__(ClearanceEpisode)
    episode.observed_command_count = 0
    episode.last_gripper_command = None
    episode.backend = SimpleNamespace(
        next_command_sequence=3,
        _command_records=[
            dict(type="gripper", accepted=True, target_open=False, physics_step=1392),
            dict(type="gripper", accepted=False, target_open=True, physics_step=1430),
        ],
    )
    episode.report = {
        "actions": [
            dict(
                skill="GRASP",
                controller_result={"success": True},
                controller_return_step=1632,
                end_step=1632,
                status="PASS",
            ),
            dict(skill="LIFT", status="ENTERED", dispatch_step=1632),
        ]
    }
    state = episode.payload_command_context()
    assert state["previous_native_successful_skill"] == "GRASP"
    assert state["previous_native_return_step"] == state["previous_native_terminal_step"] == 1632
    assert state["last_accepted_gripper_open"] is False
    assert state["last_accepted_gripper_command_step"] == 1392
    episode.backend._command_records.append(
        dict(type="gripper", accepted=True, target_open=True, physics_step=6120)
    )
    episode.backend.next_command_sequence = 4
    episode.report["actions"].append(
        dict(
            skill="RELEASE",
            controller_result={"success": True},
            controller_return_step=6360,
            status="ENTERED",
        )
    )
    current = episode.payload_command_context()
    assert current["previous_native_successful_skill"] == "RELEASE"
    assert current["previous_native_return_step"] == 6360
    assert current["previous_native_terminal_step"] is None
    assert current["last_accepted_gripper_open"] is True
