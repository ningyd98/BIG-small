"""Software source/compiler checks, with no fake actual owner or physical success."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module

import pytest

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from tests.test_visual_owner_registration import values


def api():
    return import_module("cloud_edge_robot_arm.vision.worker_owner")


@pytest.fixture
def running(tmp_path):
    repo = SQLiteSimulationJobRepository(tmp_path / "jobs.db")
    job = repo.create_job(
        run_id="source-run",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="CLOUD",
        seed=0,
        manifest_id="source-manifest",
        reproducibility_hash="a" * 64,
        draft={},
        timeout_seconds=120,
        max_attempts=2,
        artifact_root="software-attempt",
        source_commit="software-only",
        source_tree_hash="b" * 64,
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="software",
        worker_id="",
        lease_id="",
    )
    lease = repo.acquire_lease(worker_id="source-worker", backend="MUJOCO", lease_ttl_seconds=60)
    assert lease is not None
    stale = repo.get_job(job.job_id)
    attempt = repo.start_attempt(job.job_id, worker_id="source-worker")
    for old, new in [
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ]:
        assert repo.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="software",
            worker_id="source-worker",
            lease_id=lease.lease_id,
            expected_lease_id=lease.lease_id,
        )
    return repo, stale, lease, attempt


def read(running, **changes):
    repo, job, lease, _ = running
    args = dict(
        job_id=job.job_id, run_id=job.run_id, worker_id=lease.worker_id, lease_id=lease.lease_id
    )
    args.update(changes)
    return api().read_visual_worker_lease(repo, **args)


def test_actual_repository_reread_joins_new_attempt_instead_of_old_job(running):
    _, old, _, attempt = running
    assert old.attempt == 0
    source = read(running)
    assert source.attempt == attempt.attempt == 1
    assert source.scope == "WORKER_LEASE_SOURCE_ONLY"
    assert not hasattr(source, "execution_admitted")
    assert source.digest() == source.digest()
    detached = source.to_payload()
    detached["attempt"] = 99
    assert source.attempt == 1


@pytest.mark.parametrize("field", ["run_id", "worker_id", "lease_id"])
def test_foreign_source_identity_cannot_attach(running, field):
    with pytest.raises(ValueError):
        read(running, **{field: "foreign"})


@pytest.mark.parametrize("kind", ["released", "cancelled", "expired", "ended", "two_open"])
def test_missing_live_lease_or_unique_open_attempt_rejects(running, kind):
    repo, job, lease, attempt = running
    if kind == "released":
        repo.release_lease(lease.lease_id)
    elif kind == "cancelled":
        repo.request_cancel(job.job_id)
    elif kind == "ended":
        repo.finish_attempt(
            job.job_id,
            attempt=attempt.attempt,
            result="FAILED",
            error="software",
            artifact_paths={},
        )
    elif kind == "two_open":
        repo.start_attempt(job.job_id, worker_id=lease.worker_id)
    with pytest.raises(ValueError):
        read(running, **({"now": lease.expires_at} if kind == "expired" else {}))


def test_rewritten_repository_subclass_is_not_a_source_provider(running):
    repo, job, lease, _ = running

    class ForgedRepository(SQLiteSimulationJobRepository):
        pass

    forged = ForgedRepository(repo.database_path)
    with pytest.raises(TypeError):
        api().read_visual_worker_lease(
            forged,
            job_id=job.job_id,
            run_id=job.run_id,
            worker_id=lease.worker_id,
            lease_id=lease.lease_id,
        )


def compilation(running):
    source = read(running)
    data = values()
    before = data["original"]
    now = datetime.now(UTC)
    observation = data["online"].observation.model_validate(
        {
            **data["online"].observation.model_dump(),
            "captured_at": now,
            "checksum_sha256": "",
        }
    )
    contract = before.contract.model_copy(
        update={"issued_at": now, "valid_until": now + timedelta(seconds=60)}, deep=True
    )
    identity = source.identity(
        episode_id=observation.episode_id,
        task_id=contract.task_id,
        plan_id="source-plan",
        robot_id="simulator-instance",
    )
    sources = {name: "a" * 64 for name in api().REQUIRED_COMPILER_SOURCES}
    return dict(
        lease_source=source,
        identity=identity,
        contract=contract,
        observation=observation,
        proposal_hash="b" * 64,
        role_bundle_hash="c" * 64,
        source_hashes=sources,
        registered_at=now,
        task_deadline_at=now + timedelta(seconds=55),
        verification_deadline_at=now + timedelta(seconds=40),
    )


def test_compile_preserves_original_and_adds_full_local_canonical_requirements(running):
    data = compilation(running)
    original = api().compile_worker_original_plan(**data)
    assert original.contract.model_dump(mode="json") == data["contract"].model_dump(mode="json")
    requirement = original.requirements["move"]
    assert {c.name for c in requirement.preconditions} >= {
        "target_visible",
        "target_reachable",
        "gripper_open",
    }
    assert "tcp_above_target" in {c.name for c in requirement.postconditions}
    target = next(c for c in requirement.postconditions if c.name == "tcp_at_resolved_target")
    assert target.tolerances["max_distance_m"] == 0.02
    assert target.tolerances["target_reference"] == "grounded_step.parameters.target_pose"
    assert requirement.allowed_error_m == 0.01 and requirement.ordinary_ttl_s == 5.0
    assert requirement.sensor_requirements == ("rgbd",)
    assert requirement.original_step.retry_limit == data["contract"].steps[0].retry_limit
    assert original.effective_deadline_at == data["verification_deadline_at"]
    data["contract"].steps[0].parameters["object_id"] = "changed"
    assert original.contract.steps[0].parameters["object_id"] != "changed"


@pytest.mark.parametrize(
    "kind",
    [
        "foreign_attempt",
        "foreign_frame",
        "missing_calibration",
        "missing_source",
        "empty_source",
        "expired",
    ],
)
def test_complete_registered_identity_frame_sources_and_deadlines_required(running, kind):
    data = compilation(running)
    if kind == "foreign_attempt":
        data["identity"] = replace(data["identity"], attempt=2)
    elif kind == "foreign_frame":
        data["observation"] = data["observation"].model_copy(
            update={"episode_id": "foreign"}, deep=True
        )
    elif kind == "missing_calibration":
        data["observation"] = data["observation"].model_copy(
            update={"calibration_version": None}, deep=True
        )
    elif kind == "missing_source":
        data["source_hashes"].pop(next(iter(api().REQUIRED_COMPILER_SOURCES)))
    elif kind == "empty_source":
        data["source_hashes"] = {}
    elif kind == "expired":
        data["task_deadline_at"] = data["registered_at"]
    with pytest.raises(ValueError):
        api().compile_worker_original_plan(**data)


def test_unsupported_skill_has_no_invented_requirements(running):
    data = compilation(running)
    contract = data["contract"]
    contract.steps[0] = contract.steps[0].model_copy(update={"skill": SkillName.HOME}, deep=True)
    with pytest.raises(ValueError):
        api().compile_worker_original_plan(**data)


def test_source_reader_rejects_lexical_root_symlinks_and_changed_bytes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    target = root / "source.py"
    target.write_text("SOURCE = 1\n")
    import hashlib

    expected = {"source.py": hashlib.sha256(target.read_bytes()).hexdigest()}
    result = api().pin_worker_source_inventory(root, expected, required_paths={"source.py"})
    assert dict(result) == expected
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        api().pin_worker_source_inventory(alias, expected, required_paths={"source.py"})
    target.write_text("SOURCE = 2\n")
    with pytest.raises(ValueError):
        api().pin_worker_source_inventory(root, expected, required_paths={"source.py"})


def effect_values(running):
    from tests.test_visual_owner_registration import bind

    data = compilation(running)
    original = api().compile_worker_original_plan(**data)
    grounding = replace(
        bind(),
        original_plan_hash=original.digest(),
        current_identity=original.identity,
        original_requirements=original.requirements["move"],
        plan_version=original.contract.plan_version,
        command_seq=original.contract.command_seq,
        grounding_source_hashes=original.source_hashes,
        created_at=data["registered_at"],
        valid_until=data["registered_at"] + timedelta(seconds=2),
    )
    return original, grounding


def test_effect_coordinates_come_only_from_bound_step_and_original_template_is_preserved(running):
    original, grounding = effect_values(running)
    original_hash = original.digest()
    conditions = api().grounded_worker_effect_conditions(original, grounding)
    target = next(c for c in conditions if c.name == "tcp_at_resolved_target")
    assert {axis: target.tolerances[f"target_{axis}"] for axis in "xyz"} == {
        "x": 0.2,
        "y": 0.1,
        "z": 0.16,
    }
    template = next(
        c for c in original.requirements["move"].postconditions if c.name == target.name
    )
    assert all(target.tolerances[key] == value for key, value in template.tolerances.items())
    assert not any(f"target_{axis}" in template.tolerances for axis in "xyz")
    assert [c.name for c in conditions] == [
        c.name for c in original.requirements["move"].postconditions
    ]
    assert original.digest() == original_hash
    with pytest.raises(TypeError):
        target.tolerances["target_x"] = 99


@pytest.mark.parametrize(
    "kind",
    [
        "foreign_hash",
        "foreign_identity",
        "foreign_version",
        "foreign_requirement",
        "foreign_source",
        "missing_pose",
        "bool_coordinate",
    ],
)
def test_effect_instantiation_requires_original_binding_and_strict_pose(running, kind):
    import json

    original, grounding = effect_values(running)
    if kind == "foreign_hash":
        grounding = replace(grounding, original_plan_hash="f" * 64)
    elif kind == "foreign_identity":
        grounding = replace(grounding, current_identity=replace(original.identity, attempt=2))
    elif kind == "foreign_version":
        grounding = replace(grounding, command_seq=grounding.command_seq + 1)
    elif kind == "foreign_requirement":
        grounding = replace(
            grounding, original_requirements=values()["original"].requirements["move"]
        )
    elif kind == "foreign_source":
        grounding = replace(grounding, grounding_source_hashes={"foreign.py": "a" * 64})
    else:
        step = grounding.grounded_step
        if kind == "missing_pose":
            step.parameters.pop("target_pose")
        else:
            step.parameters["target_pose"]["x"] = True
        grounding = replace(grounding, _grounded_step_json=json.dumps(step.model_dump(mode="json")))
    with pytest.raises(ValueError):
        api().grounded_worker_effect_conditions(original, grounding)


def test_original_minimum_safe_height_is_never_replaced_by_fixed_local_default(running):
    data = compilation(running)
    safety = data["contract"].safety_constraints.model_copy(update={"minimum_safe_height": 0.21})
    data["contract"] = data["contract"].model_copy(update={"safety_constraints": safety}, deep=True)
    original = api().compile_worker_original_plan(**data)
    assert all(
        c.tolerances["minimum_safe_height"] == 0.21
        for r in original.requirements.values()
        for c in (*r.preconditions, *r.postconditions)
    )


@pytest.mark.parametrize(
    "skill,pre,post",
    [
        (
            SkillName.MOVE_ABOVE,
            {"target_visible", "target_reachable", "gripper_open"},
            {"tcp_at_resolved_target"},
        ),
        (
            SkillName.APPROACH,
            {"target_visible", "target_reachable", "gripper_open"},
            {"tcp_at_resolved_target"},
        ),
        (
            SkillName.GRASP,
            {"target_visible", "target_reachable", "gripper_open"},
            {"gripper_holding"},
        ),
        (
            SkillName.LIFT,
            {"gripper_holding"},
            {
                "gripper_holding",
                "tcp_at_resolved_target",
                "object_held",
                "object_lifted",
                "object_stable",
            },
        ),
        (
            SkillName.MOVE_TO_REGION,
            {"gripper_holding"},
            {"gripper_holding", "tcp_at_resolved_target"},
        ),
        (SkillName.PLACE, {"gripper_holding"}, {"gripper_holding", "tcp_at_resolved_target"}),
        (
            SkillName.RELEASE,
            {"object_inside_target_region", "gripper_holding"},
            {"gripper_released"},
        ),
        (SkillName.RETREAT, {"gripper_released"}, {"gripper_released", "tcp_at_resolved_target"}),
    ],
)
def test_full_skill_policy_requires_real_effects_and_preserves_original_attempt_limits(
    running, skill, pre, post
):
    data = compilation(running)
    step = (
        data["contract"]
        .steps[0]
        .model_copy(
            update={
                "skill": skill,
                "preconditions": [],
                "success_conditions": [],
                "timeout_ms": 17000,
                "retry_limit": 2,
            },
            deep=True,
        )
    )
    data["contract"] = data["contract"].model_copy(update={"steps": [step]}, deep=True)
    original = api().compile_worker_original_plan(**data)
    requirement = original.requirements["move"]
    assert {c.name for c in requirement.preconditions} == pre
    assert {c.name for c in requirement.postconditions} == (
        post | set(data["contract"].completion_criteria)
    )
    assert requirement.expected_duration_s >= 17
    assert (
        requirement.original_step.timeout_ms == 17000 and requirement.original_step.retry_limit == 2
    )
    assert all(
        c.target_id == data["contract"].task_target.object_id for c in requirement.preconditions
    )
    assert original.dependencies[0].completed is False


def test_unknown_original_semantics_reject_instead_of_removing_original_names(running):
    data = compilation(running)
    data["contract"].steps[0].preconditions.append("unregistered_custom_condition")
    with pytest.raises(ValueError):
        api().compile_worker_original_plan(**data)


@pytest.mark.parametrize("relative", [False, True])
def test_lexical_symlink_followed_by_parent_cannot_disappear_before_root_guard(
    tmp_path, monkeypatch, relative
):
    import hashlib
    from pathlib import Path

    real = tmp_path / "realroot"
    real.mkdir()
    source = real / "source.py"
    source.write_text("SOURCE = 'software-only'\n")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    expected = {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}
    supplied = alias / ".." / "realroot"
    if relative:
        monkeypatch.chdir(tmp_path)
        supplied = Path("alias/../realroot")
    with pytest.raises(ValueError):
        api().pin_worker_source_inventory(supplied, expected, required_paths={"source.py"})


def test_regular_parent_navigation_remains_valid_without_a_lexical_alias(tmp_path):
    import hashlib

    real = tmp_path / "realroot"
    real.mkdir()
    source = real / "source.py"
    source.write_text("SOURCE = 'software-only'\n")
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    expected = {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}
    assert (
        dict(
            api().pin_worker_source_inventory(
                ordinary / ".." / "realroot", expected, required_paths={"source.py"}
            )
        )
        == expected
    )


class PermissiveSourceString(str):
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    __hash__ = str.__hash__


@pytest.mark.parametrize("kind", ["digest", "filename", "required_path"])
def test_source_inventory_rejects_str_subclasses_before_comparison(tmp_path, kind):
    import hashlib

    (tmp_path / "source.py").write_text("VALUE=1\n")
    actual = hashlib.sha256((tmp_path / "source.py").read_bytes()).hexdigest()
    name = PermissiveSourceString("source.py") if kind == "filename" else "source.py"
    digest = PermissiveSourceString("f" * 64) if kind == "digest" else actual
    required = {PermissiveSourceString("source.py")} if kind == "required_path" else {"source.py"}
    with pytest.raises(ValueError, match="plain source"):
        api().pin_worker_source_inventory(tmp_path, {name: digest}, required_paths=required)


def test_original_compiler_rejects_subclass_source_registration(running):
    data = compilation(running)
    sources = dict(data["source_hashes"])
    key = next(iter(sources))
    sources[key] = PermissiveSourceString(sources[key])
    with pytest.raises(ValueError, match="plain source"):
        api().compile_worker_original_plan(**{**data, "source_hashes": sources})
