"""Dependency repair retains unrelated steps and completed physical effects."""

import importlib

import pytest


def api():
    return importlib.import_module("cloud_edge_robot_arm.cloud.replanning.visual_dependencies")


def steps():
    m = api()
    return [
        m.StepDependency("grasp", (), ("grasp-evidence",), "grasp-effect", True),
        m.StepDependency("place", ("grasp",), ("target-evidence",), "place-effect", False),
        m.StepDependency("release", ("place",), (), "release-effect", False),
        m.StepDependency("telemetry", (), ("network-evidence",), None, False),
    ]


def window(values, invalid):
    return api().find_repair_window(values, invalid, expected_plan_version=4,
                                    expected_command_seq=7)


def test_repair_changes_only_dependent_unfinished_suffix():
    result = window(steps(), {"target-evidence"})
    assert result.first_affected_step_id == "place"
    assert result.replace_step_ids == ("place", "release")
    assert result.preserved_step_ids == ("grasp", "telemetry")
    assert (result.expected_plan_version, result.expected_command_seq) == (4, 7)


def test_completed_release_never_resubmitted():
    m = api()
    result = window([m.StepDependency("release", (), ("lost-effect",), "effect", True),
                     m.StepDependency("verify", ("release",), (), None, False)],
                    {"lost-effect"})
    assert result.replace_step_ids == ("verify",)
    assert result.preserved_step_ids == ("release",)


@pytest.mark.parametrize("kind", ["duplicate", "missing", "cycle", "forward"])
def test_invalid_dependency_graph_is_rejected(kind):
    m = api()
    cases = {
        "duplicate": [m.StepDependency("a", (), (), None, False)] * 2,
        "missing": [m.StepDependency("a", ("absent",), (), None, False)],
        "cycle": [m.StepDependency("a", ("b",), (), None, False),
                  m.StepDependency("b", ("a",), (), None, False)],
        "forward": [m.StepDependency("a", ("b",), (), None, False),
                    m.StepDependency("b", (), (), None, False)],
    }
    with pytest.raises(ValueError):
        window(cases[kind], {"lost"})


def test_missing_version_binding_cannot_invent_repair_versions():
    with pytest.raises(ValueError, match="version|sequence"):
        api().find_repair_window(steps(), {"target-evidence"})


@pytest.mark.parametrize("plan,seq", [(True, 7), (4, False), (-1, 7), (4, 0)])
def test_invalid_version_identity_rejected(plan, seq):
    with pytest.raises(ValueError):
        api().find_repair_window(steps(), {"target-evidence"},
                                 expected_plan_version=plan, expected_command_seq=seq)


def test_dependency_inputs_are_immutable_copies():
    m = api()
    evidence, parents = ["target-evidence"], []
    value = m.StepDependency("place", parents, evidence, None, False)
    evidence.clear()
    parents.append("unknown")
    assert window([value], {"target-evidence"}).replace_step_ids == ("place",)


def test_unknown_invalid_evidence_does_not_replace_anything():
    result = window(steps(), {"unreferenced"})
    assert result.first_affected_step_id == ""
    assert result.replace_step_ids == ()
    assert result.preserved_step_ids == ("grasp", "place", "release", "telemetry")


def test_reusing_completed_effect_under_new_step_identity_is_rejected():
    m = api()
    with pytest.raises(ValueError, match="effect"):
        window([m.StepDependency("released", (), (), "same-effect", True),
                m.StepDependency("new-release-id", ("released",), ("lost",),
                                 "same-effect", False)], {"lost"})
