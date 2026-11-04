"""All assigned actions and dependent groups remain in the diagnostic denominator."""

import math
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from importlib import import_module, util

import pytest


def api():
    name = "cloud_edge_robot_arm.research.native_completion_calibration"
    assert util.find_spec(name) is not None, "missing planned joint calibration kernel"
    return import_module(name)


def cases(count=9):
    module = api()
    metric = import_module("cloud_edge_robot_arm.vision.native_completion")
    assignments, observations = [], {}
    for i in range(1, count + 1):
        group = f"group-{i}"
        score = metric.completion_metric_v2(
            geometric_error_m=0,
            command_points_m=[(0, 0, 0)],
            capture_reference_points_m=[(0, 0, 0)],
            terminal_reference_points_m=[(0, 0, 0)],
            actual_points_m=[(i / 1000, 0, 0)],
        ).completion_error_m
        assignments.append(
            module.CompletionGroupAssignmentV2(
                group,
                (f"ancestor-{i}",),
                (f"fingerprint-{i}",),
                tuple(
                    module.CompletionActionAssignmentV2(skill, 5, ("terminal", "hold-1"))
                    for skill in metric.COMPLETION_SKILLS_V2
                ),
            )
        )
        observations[group] = [
            module.CompletionActionDiagnosticsV2(
                skill, "COMPLETE", 10, 10, 15, (("terminal", score), ("hold-1", score))
            )
            for skill in metric.COMPLETION_SKILLS_V2
        ]
    return module, assignments, observations


def run(assignments, observations):
    return api().joint_completion_calibration_v2(assignments, observations)


def reason(result, group="group-1"):
    return dict(result.group_reasons)[group]


def unavailable(result):
    assert result.assigned_group_count == result.component_count == result.rank == 9
    assert result.joint_bound_m is None
    assert dict(result.group_scores)["group-1"] is None
    assert result.unavailable_group_ids == ("group-1",)


def test_nine_complete_eight_action_groups_have_joint_rank_nine():
    _, assignments, observations = cases()
    result = run(assignments, observations)
    assert (result.assigned_group_count, result.component_count, result.rank) == (9, 9, 9)
    assert result.joint_bound_m == 0.009
    assert len(result.group_scores) == len(result.components) == len(result.component_scores) == 9
    assert sum(len(a.actions) for a in assignments) == 72
    assert sum(len(a.samples) for group in observations.values() for a in group) == 144
    assert not result.unavailable_group_ids
    assert all(not reasons for _, reasons in result.group_reasons)
    assert result.evidence_scope == "SOFTWARE_ONLY"
    assert result.native_authority == "UNAVAILABLE"


def test_any_of_eight_actions_controls_joint_score():
    _, assignments, observations = cases()
    for index in range(8):
        rows = list(observations["group-1"])
        rows[index] = replace(rows[index], samples=(("terminal", 0.02), ("hold-1", 0.001)))
        result = run(assignments, {**observations, "group-1": rows})
        assert dict(result.group_scores)["group-1"] == result.joint_bound_m == 0.02


def test_missing_group_action_sample_retains_infinite_denominator():
    _, assignments, observations = cases()
    result = run(assignments, {k: v for k, v in observations.items() if k != "group-1"})
    unavailable(result)
    assert "missing_group" in reason(result)
    rows = observations["group-1"]
    for index, action in enumerate(rows):
        result = run(assignments, {**observations, "group-1": rows[:index] + rows[index + 1 :]})
        unavailable(result)
        assert f"missing_action:{action.skill}" in reason(result)
        for sample_index, (sample_id, _) in enumerate(action.samples):
            changed = list(rows)
            changed[index] = replace(
                action, samples=action.samples[:sample_index] + action.samples[sample_index + 1 :]
            )
            result = run(assignments, {**observations, "group-1": changed})
            unavailable(result)
            assert f"missing_sample:{action.skill}:{sample_id}" in reason(result)


def test_failed_unknown_incomplete_and_infinite_samples():
    _, assignments, observations = cases()
    for outcome in ("FAILED", "UNKNOWN", "INCOMPLETE"):
        rows = list(observations["group-1"])
        rows[2] = replace(rows[2], outcome=outcome)
        result = run(assignments, {**observations, "group-1": rows})
        unavailable(result)
        assert f"outcome:GRASP:{outcome}" in reason(result)
        rows[2] = replace(rows[2], samples=(("terminal", math.nan),))
        with pytest.raises(ValueError):
            run(assignments, {**observations, "group-1": rows})
    for score in (None, math.inf):
        rows = list(observations["group-1"])
        rows[5] = replace(rows[5], samples=(("terminal", score), ("hold-1", 0.001)))
        result = run(assignments, {**observations, "group-1": rows})
        unavailable(result)
        assert "unavailable_sample:PLACE:terminal" in reason(result)


def test_exact_assigned_horizon_and_zero_age():
    _, assignments, observations = cases()
    assert run(assignments, observations).joint_bound_m == 0.009
    for change, expected in (
        ({"terminal_step": 14}, "terminal_horizon_mismatch"),
        ({"terminal_step": 16}, "terminal_horizon_mismatch"),
        ({"terminal_step": 9}, "terminal_horizon_mismatch"),
        ({"terminal_step": 10}, "terminal_horizon_mismatch"),
        ({"capture_step": 9}, "capture_dispatch_mismatch"),
        ({"capture_step": 11}, "capture_dispatch_mismatch"),
    ):
        rows = list(observations["group-1"])
        rows[3] = replace(rows[3], **change)
        result = run(assignments, {**observations, "group-1": rows})
        unavailable(result)
        assert f"{expected}:LIFT" in reason(result)


def test_ancestry_and_fingerprint_merge_transitively():
    _, assignments, observations = cases()
    assignments[1] = replace(
        assignments[1],
        ancestor_ids=assignments[0].ancestor_ids,
        fingerprints=assignments[2].fingerprints,
    )
    result = run(assignments, observations)
    assert (result.assigned_group_count, result.component_count, result.rank) == (9, 7, 8)
    assert ("group-1", "group-2", "group-3") in result.components
    assert result.joint_bound_m is None
    observations.pop("group-2")
    missing = run(assignments, observations)
    component = missing.components.index(("group-1", "group-2", "group-3"))
    assert missing.component_scores[component] is None
    assert missing.component_count == 7
    assert missing == run(list(reversed(assignments)), dict(reversed(list(observations.items()))))


def test_exact_rank_and_infinity_ordering():
    module = api()
    for count, rank, finite in ((8, 9, False), (9, 9, True), (19, 18, True)):
        _, assignments, observations = cases(count)
        result = run(assignments, observations)
        assert result.component_count == count and result.rank == rank
        assert (result.joint_bound_m is not None) == finite
    for group, rows in observations.items():
        score = int(group.split("-")[1])
        observations[group] = [
            replace(a, samples=(("terminal", score), ("hold-1", score))) for a in rows
        ]
    observations.pop("group-19")
    result = run(assignments, observations)
    assert result.joint_bound_m == 18
    assert result.unavailable_group_ids == ("group-19",)
    assert result.component_scores.count(None) == 1
    observations.pop("group-18")
    assert run(assignments, observations).joint_bound_m is None
    with pytest.raises(ValueError):
        module.joint_completion_calibration_v2([], {})


def test_assignment_and_observation_schema_is_strict():
    _, assignments, observations = cases()
    first, action = assignments[0], assignments[0].actions[0]
    invalid_groups = [
        replace(first, actions=first.actions[:-1]),
        replace(first, actions=(action,) + first.actions[1:-1] + (action,)),
        replace(first, ancestor_ids=()),
        replace(first, fingerprints=()),
        replace(first, ancestor_ids=("a", "a")),
        replace(first, fingerprints=("f", "f")),
        replace(first, group_id="group-2"),
        replace(first, group_id=" "),
        replace(first, group_id=3),
        replace(first, ancestor_ids=("",)),
        replace(first, fingerprints=(True,)),
        replace(first, actions=({},) + first.actions[1:]),
        {},
    ]
    for field, values in (
        ("skill", ("HOME", "", True)),
        ("full_horizon_steps", (0, -1, True, 5.0, "5", None)),
        ("sample_ids", ((), ("terminal", "terminal"), (" ",), (None,))),
    ):
        invalid_groups.extend(
            replace(first, actions=(replace(action, **{field: v}),) + first.actions[1:])
            for v in values
        )
    for group in invalid_groups:
        with pytest.raises(ValueError):
            run([group] + assignments[1:], observations)
    for obs in ({**observations, "foreign": []}, {**observations, True: []}):
        with pytest.raises(ValueError):
            run(assignments, obs)
    rows = observations["group-1"]
    invalid_rows = [
        rows + [rows[0]],
        [{}] + rows[1:],
        [replace(rows[0], skill="HOME")] + rows[1:],
        [replace(rows[0], outcome="SUCCEEDED")] + rows[1:],
        [replace(rows[0], samples=(("foreign", 0),))] + rows[1:],
        [replace(rows[0], samples=(("terminal", 0), ("terminal", 0)))] + rows[1:],
    ]
    for field in ("capture_step", "dispatch_step", "terminal_step"):
        invalid_rows += [
            [replace(rows[0], **{field: v})] + rows[1:] for v in (True, 1.0, "1", -1, None)
        ]
    for changed in invalid_rows:
        with pytest.raises(ValueError):
            run(assignments, {**observations, "group-1": changed})


def test_scores_are_strict_and_diagnostics_detached():
    _, assignments, observations = cases()
    rows = observations["group-1"]
    for score in (True, "0", -0.1, math.nan, -math.inf):
        with pytest.raises(ValueError):
            run(
                assignments,
                {
                    **observations,
                    "group-1": [
                        replace(rows[0], samples=(("terminal", score), ("hold-1", 0))),
                        *rows[1:],
                    ],
                },
            )
    result = run(assignments, observations)
    observations.clear()
    assignments.clear()
    assert result.joint_bound_m == 0.009 and len(result.group_scores) == 9
    with pytest.raises(FrozenInstanceError):
        result.joint_bound_m = 0
    _, assignments, observations = cases()
    for index, name in enumerate(("a|b", "a", "b")):
        old = assignments[index].group_id
        assignments[index] = replace(assignments[index], group_id=name)
        observations[name] = observations.pop(old)
    zero = {
        k: [replace(a, samples=(("terminal", 0), ("hold-1", 0))) for a in v]
        for k, v in observations.items()
    }
    result = run(assignments, zero)
    assert result.joint_bound_m == 0 and result.component_count == 9
    assert all((name,) in result.components for name in ("a|b", "a", "b"))


def test_finite_joint_diagnostics_cannot_upgrade_legacy_evidence():
    _, assignments, observations = cases()
    result = run(assignments, observations)
    from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
    from cloud_edge_robot_arm.vision.action_evidence import native_action_contract
    from tests.test_native_action_submit import sample

    online, contract, step = sample()
    online = replace(
        online,
        visual_facts={
            **online.visual_facts,
            "joint_completion_bound_m": result.joint_bound_m,
            "native_authority": "VALID",
            "bound_proof": {"status": "VALID", "joint_bound_m": result.joint_bound_m},
        },
    )
    action = native_action_contract(online, contract, step)
    assert action.evidence.geometric_error_bound_m is None
    assert action.evidence.motion_bound_m_s is None
    assert (
        validate_evidence(
            action,
            datetime.now(UTC),
            online.context_hash,
            online.observation.calibration_version,
            online_evidence=online,
        ).status
        == "UNKNOWN"
    )
    assert not hasattr(result, "geometric_error_bound_m")
    assert not hasattr(result, "motion_bound_m_s")
    for field in ("evidence_scope", "native_authority", "schema_version"):
        with pytest.raises(ValueError):
            replace(result, **{field: "VALID"})
