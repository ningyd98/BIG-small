"""Concrete lease observations and pure original-policy compilation.

These sources carry no METHOD, execution, native or physical admission. A lease
observation is valid at its read time; the live worker must recheck each boundary.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Set
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import ClassVar

from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
from cloud_edge_robot_arm.contracts import SkillName, TaskContract
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.simulation_runtime.in_memory_repository import (
    InMemorySimulationJobRepository,
)
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
    SQLiteSimulationJobRepository,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    OriginalActionRequirements,
    StepGroundingBinding,
    VisualOriginalPlan,
    VisualOwnerIdentity,
    _aware,
    _condition,
    _digest,
    _freeze,
    _model_json,
    _sha,
    _sources,
    freeze_original_visual_plan,
)

REQUIRED_COMPILER_SOURCES = frozenset(
    {
        "src/cloud_edge_robot_arm/vision/worker_owner.py",
        "src/cloud_edge_robot_arm/vision/owner_registration.py",
        "src/cloud_edge_robot_arm/vision/execution.py",
        "src/cloud_edge_robot_arm/vision/evaluation.py",
        "src/cloud_edge_robot_arm/vision/action_evidence.py",
        "src/cloud_edge_robot_arm/edge/evidence/conditions.py",
        "src/cloud_edge_robot_arm/simulation_runtime/worker.py",
        "src/cloud_edge_robot_arm/simulation_runtime/sqlite_repository.py",
    }
)


def _identity_string(value: str) -> str:
    if (
        type(value) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is None
        or value.lower() in {"unknown", "none", "placeholder", "robot-unknown"}
    ):
        raise ValueError("explicit nonplaceholder source identity required")
    return value


@dataclass(frozen=True)
class WorkerLeaseObservation:
    job_id: str
    run_id: str
    worker_id: str
    lease_id: str
    attempt: int
    acquired_at: datetime
    observed_at: datetime
    expires_at: datetime
    job_state_hash: str
    lease_state_hash: str
    attempt_state_hash: str
    scope: ClassVar[str] = "WORKER_LEASE_SOURCE_ONLY"

    def __post_init__(self) -> None:
        for value in (self.job_id, self.run_id, self.worker_id, self.lease_id):
            _identity_string(value)
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("positive current attempt required")
        if not _aware(self.acquired_at) <= _aware(self.observed_at) < _aware(self.expires_at):
            raise ValueError("source acquisition/observation/expiry order invalid")
        for value in (self.job_state_hash, self.lease_state_hash, self.attempt_state_hash):
            _sha(value)

    def to_payload(self) -> dict[str, str | int]:
        return {
            "scope": self.scope,
            "job_id": self.job_id,
            "run_id": self.run_id,
            "worker_id": self.worker_id,
            "lease_id": self.lease_id,
            "attempt": self.attempt,
            "acquired_at": self.acquired_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "job_state_hash": self.job_state_hash,
            "lease_state_hash": self.lease_state_hash,
            "attempt_state_hash": self.attempt_state_hash,
        }

    def digest(self) -> str:
        return _digest(self.to_payload())

    def identity(
        self, *, episode_id: str, task_id: str, plan_id: str, robot_id: str
    ) -> VisualOwnerIdentity:
        epoch = _digest([self.job_id, self.run_id, self.worker_id, self.lease_id, self.attempt])
        return VisualOwnerIdentity(
            self.job_id,
            self.run_id,
            self.attempt,
            self.worker_id,
            self.lease_id,
            epoch,
            episode_id,
            task_id,
            plan_id,
            robot_id,
        )


def read_visual_worker_lease(
    repository: SQLiteSimulationJobRepository,
    *,
    job_id: str,
    run_id: str,
    worker_id: str,
    lease_id: str,
    now: datetime | None = None,
) -> WorkerLeaseObservation:
    """Join current concrete records under the existing publication guard.

    No draft, secret, result artifact or controller payload is read into the
    returned observation. Caller-supplied repository subclasses are rejected.
    """
    if type(repository) not in {SQLiteSimulationJobRepository, InMemorySimulationJobRepository}:
        raise TypeError("concrete simulation repository required")
    for value in (job_id, run_id, worker_id, lease_id):
        _identity_string(value)
    with SQLiteSimulationJobRepository.publication_guard(repository):
        observed = _aware(now if now is not None else datetime.now(UTC))
        try:
            job = SQLiteSimulationJobRepository.get_job(repository, job_id)
        except KeyError as error:
            raise ValueError("worker job source missing") from error
        if (
            job.run_id != run_id
            or job.worker_id != worker_id
            or job.lease_id != lease_id
            or job.status != RuntimeJobStatus.RUNNING
            or job.cancel_requested
            or job.lease_expires_at is None
            or _aware(job.lease_expires_at) <= observed
            or type(job.attempt) is not int
            or job.attempt < 1
        ):
            raise ValueError("worker job identity/status/lease source invalid")
        leases = [
            row
            for row in SQLiteSimulationJobRepository.list_leases(repository, run_id)
            if row.job_id == job_id
            and row.released_at is None
            and _aware(row.expires_at) > observed
        ]
        if len(leases) != 1:
            raise ValueError("unique live job lease required")
        lease = leases[0]
        if lease.lease_id != lease_id or lease.worker_id != worker_id:
            raise ValueError("live lease identity differs from worker/job")
        attempts = [
            row
            for row in SQLiteSimulationJobRepository.list_attempts(repository, run_id)
            if row.job_id == job_id and row.ended_at is None
        ]
        if len(attempts) != 1:
            raise ValueError("unique open job attempt required")
        attempt = attempts[0]
        if (
            attempt.run_id != run_id
            or attempt.worker_id != worker_id
            or attempt.attempt != job.attempt
            or attempt.result != "RUNNING"
            or not _aware(lease.acquired_at) <= _aware(attempt.started_at) <= observed
        ):
            raise ValueError("current job/lease/attempt join invalid")
        return WorkerLeaseObservation(
            job_id,
            run_id,
            worker_id,
            lease_id,
            job.attempt,
            lease.acquired_at,
            observed,
            min(job.lease_expires_at, lease.expires_at),
            _digest(
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "worker_id": job.worker_id,
                    "lease_id": job.lease_id,
                    "attempt": job.attempt,
                    "status": job.status,
                    "cancel_requested": job.cancel_requested,
                    "lease_expires_at": job.lease_expires_at,
                }
            ),
            _digest(
                {
                    "lease_id": lease_id,
                    "job_id": lease.job_id,
                    "worker_id": lease.worker_id,
                    "acquired_at": lease.acquired_at,
                    "expires_at": lease.expires_at,
                    "heartbeat_at": lease.heartbeat_at,
                    "released_at": lease.released_at,
                }
            ),
            _digest(
                {
                    "job_id": attempt.job_id,
                    "run_id": attempt.run_id,
                    "attempt": attempt.attempt,
                    "worker_id": attempt.worker_id,
                    "started_at": attempt.started_at,
                    "ended_at": attempt.ended_at,
                    "result": attempt.result,
                }
            ),
        )


def _plain_worker_sources(value: Mapping[str, str]) -> Mapping[str, str]:
    # Do not call comparisons or path methods supplied by str subclasses.
    if not isinstance(value, Mapping):
        raise ValueError("plain source inventory mapping required")
    copied: dict[str, str] = {}
    for name, digest in value.items():
        if type(name) is not str or type(digest) is not str:
            raise ValueError("plain source names and SHA strings required")
        copied[name] = digest
    return _sources(copied)


def pin_worker_source_inventory(
    root: Path,
    expected: Mapping[str, str],
    *,
    required_paths: Set[str] = REQUIRED_COMPILER_SOURCES,
) -> Mapping[str, str]:
    """Hash existing regular sources; lexical aliases are checked before resolve.

    This verifies local byte consistency, not publisher authenticity. The worker
    selects its registered root/inventory; a caller cannot grant admission here.
    """
    lexical_root = Path(root)
    if not lexical_root.is_absolute():
        lexical_root = Path.cwd() / lexical_root
    if any(path.is_symlink() for path in (lexical_root, *lexical_root.parents)):
        raise ValueError("lexical source root/ancestor symlink rejected")
    if not lexical_root.is_dir():
        raise ValueError("source root missing")
    # Only after checking the original lexical ancestors may parent navigation
    # be normalized for containment. abspath would erase an alias/.. first.
    lexical_root = lexical_root.resolve()
    copied = _plain_worker_sources(expected)
    if not isinstance(required_paths, Set) or any(type(name) is not str for name in required_paths):
        raise ValueError("plain source required-path strings required")
    required_paths = frozenset(required_paths)
    if not required_paths or not required_paths <= copied.keys():
        raise ValueError("complete required source inventory missing")
    for name, digest in copied.items():
        relative = PurePosixPath(name)
        if str(relative) != name or "\\" in name or relative.is_absolute():
            raise ValueError("canonical relative source path required")
        path = lexical_root / name
        if any(part.is_symlink() for part in (path, *path.parents)):
            raise ValueError("source file/ancestor symlink rejected")
        if not path.is_file() or not path.resolve().is_relative_to(lexical_root):
            raise ValueError("regular source inside registered root required")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("current source bytes differ from registered source")
    return MappingProxyType(dict(copied))


_PRE = {
    SkillName.MOVE_ABOVE: ("target_visible", "target_reachable", "gripper_open"),
    SkillName.APPROACH: ("target_visible", "target_reachable", "gripper_open"),
    SkillName.GRASP: ("target_visible", "target_reachable", "gripper_open"),
    SkillName.LIFT: ("gripper_holding",),
    SkillName.MOVE_TO_REGION: ("gripper_holding",),
    SkillName.PLACE: ("gripper_holding",),
    SkillName.RELEASE: ("object_inside_target_region", "gripper_holding"),
    SkillName.RETREAT: ("gripper_released",),
}
_POST = {
    SkillName.MOVE_ABOVE: ("tcp_at_resolved_target",),
    SkillName.APPROACH: ("tcp_at_resolved_target",),
    SkillName.GRASP: ("gripper_holding",),
    SkillName.LIFT: (
        "gripper_holding",
        "tcp_at_resolved_target",
        "object_held",
        "object_lifted",
        "object_stable",
    ),
    SkillName.MOVE_TO_REGION: ("gripper_holding", "tcp_at_resolved_target"),
    SkillName.PLACE: ("gripper_holding", "tcp_at_resolved_target"),
    SkillName.RELEASE: ("gripper_released",),
    SkillName.RETREAT: ("gripper_released", "tcp_at_resolved_target"),
}

# TaskContract condition fields are strings, not an enum. This v1 allowlist is
# the explicit adapter between the actual cloud pick/place templates (planning/
# adapter.py and vision/planner.py) and the online evaluator. Names remain intact;
# unrecognised cloud criteria cannot be dropped or turned into completion flags.
WORKER_CONDITION_REGISTRY_VERSION = "visual.worker.full-effects.v1"
WORKER_CONDITION_REGISTRY = MappingProxyType(
    {
        name: "region" if name == "tcp_above_region" else "object"
        for name in (
            "target_visible",
            "target_reachable",
            "tcp_above_target",
            "tcp_near_target",
            "tcp_above_region",
            "robot_clear_of_object",
            "robot_at_home",
            "object_inside_target_region",
            "object_grasped",
            "object_held",
            "object_attached",
            "object_lifted",
            "object_stable",
            "placement_stable",
            "object_placed",
            "gripper_open",
            "gripper_closed",
            "gripper_released",
            "object_released",
            "robot_stopped",
            "robot_in_safe_pose",
            "tcp_above_safe_height",
            "gripper_holding",
            "tcp_at_resolved_target",
        )
    }
)


def compile_worker_original_plan(
    *,
    lease_source: WorkerLeaseObservation,
    identity: VisualOwnerIdentity,
    contract: TaskContract,
    observation: RGBDObservation,
    proposal_hash: str,
    role_bundle_hash: str,
    source_hashes: Mapping[str, str],
    registered_at: datetime,
    task_deadline_at: datetime,
    verification_deadline_at: datetime,
) -> VisualOriginalPlan:
    """Freeze complete original requirements before per-frame resolution.

    TCP coordinates are registered templates; only the bound grounded step may
    instantiate them. Unknown/unsupported semantics cannot be silently removed.
    Supplied source hashes are consistency inputs, not actual-source admission.
    """
    if (
        type(lease_source) is not WorkerLeaseObservation
        or type(identity) is not VisualOwnerIdentity
    ):
        raise ValueError("concrete lease observation and owner identity required")
    contract = TaskContract.model_validate_json(_model_json(contract, TaskContract))
    observation = RGBDObservation.model_validate_json(_model_json(observation, RGBDObservation))
    start = _aware(registered_at)
    episode_id, calibration_version = observation.episode_id, observation.calibration_version
    if not episode_id or not calibration_version:
        raise ValueError("explicit episode and calibration source required")
    if (
        identity
        != lease_source.identity(
            episode_id=episode_id,
            task_id=contract.task_id,
            plan_id=identity.plan_id,
            robot_id=identity.robot_id,
        )
        or not lease_source.observed_at <= start < lease_source.expires_at
        or not lease_source.acquired_at <= _aware(observation.captured_at) <= start
    ):
        raise ValueError("current identity/acquisition/calibration/source time mismatch")
    sources = _plain_worker_sources(source_hashes)
    if not REQUIRED_COMPILER_SOURCES <= sources.keys():
        raise ValueError("complete compiler/policy source inventory required")
    requirements: dict[str, OriginalActionRequirements] = {}
    graph = []
    for index, step in enumerate(contract.steps):
        if step.skill not in _PRE:
            raise ValueError("unsupported visual skill has no registered original requirements")

        def condition(name: str) -> ConditionSpec:
            if name not in WORKER_CONDITION_REGISTRY:
                raise ValueError("original condition has no versioned online mapping")
            tolerances: dict[str, str | float] = {
                "max_age_s": 5.0,
                "calibration_version": calibration_version,
                "minimum_safe_height": contract.safety_constraints.minimum_safe_height,
                "condition_registry_version": WORKER_CONDITION_REGISTRY_VERSION,
            }
            if name == "object_held":
                # This source-worker v1 requirement joins visual identity with
                # proprioception. Existing unversioned LEGACY specs retain their
                # historical evaluator contract.
                tolerances["holding_feedback_required"] = True
            if name == "tcp_at_resolved_target":
                tolerances.update(
                    target_reference="grounded_step.parameters.target_pose",
                    max_distance_m=0.02,
                )
            target_id = (
                contract.task_target.target_region_id
                if WORKER_CONDITION_REGISTRY[name] == "region"
                else contract.task_target.object_id
            )
            return ConditionSpec(name, target_id, tolerances, ("rgbd",))

        requirements[step.step_id] = OriginalActionRequirements(
            step,
            tuple(
                condition(name) for name in dict.fromkeys((*step.preconditions, *_PRE[step.skill]))
            ),
            tuple(
                condition(name)
                for name in dict.fromkeys(
                    (
                        *step.success_conditions,
                        *_POST[step.skill],
                        *(contract.completion_criteria if index == len(contract.steps) - 1 else ()),
                    )
                )
            ),
            0.01,
            ("rgbd",),
            5.0,
            max(step.timeout_ms, step.expected_duration_ms) / 1000,
            sources,
        )
        graph.append(
            StepDependency(
                step.step_id,
                () if index == 0 else (contract.steps[index - 1].step_id,),
                (observation.observation_id,),
                f"{step.step_id}:effect",
                False,
            )
        )
    return freeze_original_visual_plan(
        identity=identity,
        contract=contract,
        proposal_hash=proposal_hash,
        role_bundle_hash=role_bundle_hash,
        compiler_source_hashes=sources,
        source_hashes=sources,
        requirements=requirements,
        dependencies=graph,
        task_deadline_at=task_deadline_at,
        verification_deadline_at=verification_deadline_at,
        registered_at=start,
    )


def grounded_worker_effect_conditions(
    original: VisualOriginalPlan, grounding: StepGroundingBinding
) -> tuple[ConditionSpec, ...]:
    """Instantiate an original TCP template from its exact bound step only.

    This returns deterministic check inputs, never a verdict or permission. It
    does not replace the original requirement/template and has no clock oracle.
    A live caller must separately recheck current lease/frame/expiry and safety.
    """
    if type(original) is not VisualOriginalPlan or type(grounding) is not StepGroundingBinding:
        raise ValueError("concrete original plan and grounding binding required")
    original = freeze_original_visual_plan(**original.freeze_inputs())
    grounding = replace(grounding)
    step = grounding.grounded_step
    requirement = original.requirements.get(step.step_id)
    if (
        requirement is None
        or grounding.original_plan_hash != original.digest()
        or grounding.current_identity != original.identity
        or (grounding.plan_version, grounding.command_seq)
        != (original.contract.plan_version, original.contract.command_seq)
        or grounding.original_requirements.digest() != requirement.digest()
        or any(
            original.source_hashes.get(k) != v for k, v in grounding.grounding_source_hashes.items()
        )
        or not original.registered_at <= grounding.created_at < grounding.valid_until
        or grounding.valid_until > original.effective_deadline_at
    ):
        raise ValueError("grounded effect original/source/version/policy binding mismatch")
    result = []
    for condition in requirement.postconditions:
        if condition.name != "tcp_at_resolved_target":
            result.append(_condition(condition))
            continue
        if condition.tolerances.get(
            "target_reference"
        ) != "grounded_step.parameters.target_pose" or any(
            f"target_{axis}" in condition.tolerances for axis in "xyz"
        ):
            raise ValueError("registered original TCP template required")
        pose = step.parameters.get("target_pose")
        if not isinstance(pose, dict) or set(pose) != {"x", "y", "z"}:
            raise ValueError("exact bound target position required")
        coordinates = {}
        for axis in "xyz":
            value = pose[axis]
            if type(value) not in {int, float}:
                raise ValueError("bound target coordinates require strict finite numbers")
            try:
                coordinate = float(value)
            except OverflowError as error:
                raise ValueError("bound target coordinate exceeds finite range") from error
            if not math.isfinite(coordinate):
                raise ValueError("bound target coordinate nonfinite")
            coordinates[f"target_{axis}"] = coordinate
        result.append(
            ConditionSpec(
                condition.name,
                condition.target_id,
                _freeze({**condition.tolerances, **coordinates}),
                tuple(condition.sensor_requirements),
            )
        )
    return tuple(result)


def grounded_worker_execution_effect_conditions(
    original: VisualOriginalPlan,
    execution_contract: TaskContract,
    *,
    grounding: StepGroundingBinding,
    step_id: str,
) -> tuple[ConditionSpec, ...]:
    """Use the complete typed execution payload only after exact receipt binding.

    This pure check does not authorize an action or authenticate a controller.
    The caller must join the receipt to its current durable checkpoint and, for
    historical effects, to the typed completion of the original attempt.
    """
    contract = TaskContract.model_validate_json(_model_json(execution_contract, TaskContract))
    # Validate the complete original/source binding before consulting parameters.
    grounded_worker_effect_conditions(original, grounding)
    if grounding.grounded_step.step_id != step_id:
        raise ValueError("effect receipt step differs from full execution payload")
    expected = original.contract.model_dump(mode="json")
    expected["steps"] = [
        grounding.grounded_step.model_dump(mode="json") if s["step_id"] == step_id else s
        for s in expected["steps"]
    ]
    if contract.model_dump(mode="json") != expected:
        raise ValueError("full effect execution payload differs from exact original binding")
    step = next(s for s in contract.steps if s.step_id == step_id)
    return grounded_worker_effect_conditions(
        original, replace(grounding, _grounded_step_json=step.model_dump_json())
    )
