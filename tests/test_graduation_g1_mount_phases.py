"""Phase diagnostics retain actual action roles and never substitute another trajectory."""

import pytest
from scripts.graduation import g1_mount_phases as phases


def test_stage_samples_follow_actual_dispatch_and_preserve_shared_endpoints():
    stages = [
        {"skill": "APPROACH", "executor_entered": True, "dispatch_step": 4, "end_step": 9},
        {"skill": "GRASP", "executor_entered": True, "dispatch_step": 9, "end_step": 11},
        {"skill": "LIFT", "status": "NOT_RUN"},
    ]
    sampled = phases.phase_steps(stages, 11)
    assert sampled == {"APPROACH": [4, 6, 9], "GRASP": [9, 10, 11], "LIFT": []}
    assert phases.requires_teacher(sampled, [{"label": "GRASP/POST", "physics_step": 11}])
    assert len({step for values in sampled.values() for step in values}) == 5


def test_endpoint_only_grasp_and_unrelated_middle_frame_require_separate_diagnostic():
    sampled = {skill: [0, 1, 2] for skill in phases.SKILLS}
    frames = [{"label": skill + "/feedback", "physics_step": 1} for skill in phases.SKILLS]
    assert not phases.requires_teacher(sampled, frames)
    frames[1] = {"label": "GRASP/POST", "physics_step": 2}
    assert phases.requires_teacher(sampled, frames)


def test_dispatch_with_missing_end_or_unbound_time_cannot_be_declared_observed():
    stages = [{"skill": skill, "status": "NOT_RUN"} for skill in phases.SKILLS]
    stages[0].update(executor_entered=True, dispatch_step=2, end_step=8)
    with pytest.raises(ValueError, match="phase interval"):
        phases.phase_steps(stages, 7)
    stages[0].pop("end_step")
    with pytest.raises(ValueError, match="phase interval"):
        phases.phase_steps(stages, 7)


def test_foreign_episode_or_physics_clock_is_rejected_on_old_teacher_grid():
    steps = [
        {"physics_step": i, "episode_id": "one", "sim_time_s": i * 0.0041666667} for i in range(3)
    ]
    phases.check_teacher_grid(steps, "one", 0.0041666667, 2)
    with pytest.raises(ValueError, match="teacher state"):
        phases.check_teacher_grid(steps, "another", 0.0041666667, 2)
    steps[2]["sim_time_s"] = 1.0
    with pytest.raises(ValueError, match="teacher state"):
        phases.check_teacher_grid(steps, "one", 0.0041666667, 2)
