"""Planning pipeline: from InitialPlanningRequest to validated TaskContract.

The pipeline enforces the *model untrusted boundary*:
- Models may *never* decide task_id, plan_version, command_seq, issued_at,
  valid_until, safety policy version, or cloud request IDs.
- Models output is strictly validated; low-level controls and safety bypass
  fields are rejected.
- Failed repairs → REQUEST_MORE_OBSERVATION or PLANNER_FAILED; no partial
  contracts are dispatched.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from cloud_edge_robot_arm.cloud.planning.adapter import PlannerAdapter
from cloud_edge_robot_arm.cloud.planning.models import (
    InitialPlanningRequest,
    InitialPlanningResponse,
    PlannerDraft,
    PlanningAttempt,
    PlanningOutcome,
    ValidationResult,
)
from cloud_edge_robot_arm.contracts import SkillName, TaskContract

# ── Forbidden fields (model MUST NOT set) ────────────────────────────────────

TRUSTED_FIELDS = frozenset(
    {
        "task_id",
        "plan_version",
        "command_seq",
        "issued_at",
        "valid_until",
        "timestamp",
    }
)

FORBIDDEN_KEYS = frozenset(
    {
        "joint_angles",
        "motor_commands",
        "PWM",
        "servo_pulse",
        "trajectory_points",
        "disable_safety",
        "bypass_safety",
        "ignore_collision",
        "force_execute",
    }
)


# ── Scene sufficiency ────────────────────────────────────────────────────────


def check_scene_sufficiency(
    request: InitialPlanningRequest,
    scene_staleness_ms: int = 5_000,
) -> str | None:
    """Return a reason string if the scene is insufficient, else None."""
    scene = request.scene
    now = datetime.now(UTC)
    age_ms = int((now - scene.updated_at).total_seconds() * 1_000)
    if age_ms > scene_staleness_ms:
        return f"scene is stale (age={age_ms}ms, max={scene_staleness_ms}ms)"

    if scene.scene_confidence < 0.5:
        return f"scene confidence too low ({scene.scene_confidence:.2f})"

    if not scene.objects:
        return "no objects in scene"

    if not scene.regions:
        return "no target regions in scene"

    # Check for target object presence and disambiguation
    instruction = request.user_instruction.lower()
    matching_objects = [
        obj
        for obj in scene.objects
        if _object_matches_instruction(obj.object_id, obj.object_class, instruction)
    ]
    if len(matching_objects) == 0:
        # Could be a refill task, so just note that no explicit match found
        pass
    elif len(matching_objects) > 1:
        ids = ", ".join(obj.object_id for obj in matching_objects)
        return f"ambiguous target: multiple matching objects ({ids})"

    # Check missing poses
    objects_without_pose = [obj.object_id for obj in scene.objects if obj.pose is None]
    if objects_without_pose:
        ids = ", ".join(objects_without_pose)
        return f"objects missing pose: {ids}"

    # Check obstacle data when collision check is needed
    # (soft check — not a hard block)

    return None


def _object_matches_instruction(
    object_id: str,
    object_class: str,
    instruction: str,
) -> bool:
    oid = object_id.lower()
    ocl = object_class.lower()
    words = instruction.replace(",", " ").replace(".", " ").split()
    for w in words:
        wl = w.lower()
        if wl in oid or wl in ocl or oid in wl or ocl in wl:
            return True
    return False


# ── Semantic validation ──────────────────────────────────────────────────────


def semantic_validate(
    parsed: dict[str, Any],
    request: InitialPlanningRequest,
) -> ValidationResult:
    """Check business-logic correctness of planner output."""
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    steps = parsed.get("steps", [])
    if not isinstance(steps, list):
        return ValidationResult(
            passed=False,
            errors=[{"field": "steps", "message": "steps must be a list"}],
        )

    skill_set = {s.value for s in SkillName}

    # All skills must be registered
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append({"field": f"steps[{i}]", "message": "step must be a dict"})
            continue
        skill = step.get("skill", "")
        if skill not in skill_set:
            errors.append(
                {
                    "field": f"steps[{i}].skill",
                    "message": f"unknown skill {skill!r}",
                    "value": skill,
                }
            )

    # Target object must exist in scene
    task_target = parsed.get("task_target", {})
    target_object_id = task_target.get("object_id", "")
    if target_object_id:
        scene_obj_ids = {obj.object_id for obj in request.scene.objects}
        if target_object_id not in scene_obj_ids:
            errors.append(
                {
                    "field": "task_target.object_id",
                    "message": f"target object {target_object_id!r} not in scene",
                    "value": target_object_id,
                }
            )

    # Target region must exist
    target_region_id = task_target.get("target_region_id", "")
    if target_region_id:
        scene_region_ids = {r.region_id for r in request.scene.regions}
        if target_region_id not in scene_region_ids:
            errors.append(
                {
                    "field": "task_target.target_region_id",
                    "message": f"target region {target_region_id!r} not in scene",
                    "value": target_region_id,
                }
            )

    # Skill ordering constraints
    skill_order = [s.get("skill", "") for s in steps]
    for i, skill in enumerate(skill_order):
        if skill == "GRASP" and i > 0:
            # Some approach-like skill should precede grasp
            prior = skill_order[:i]
            if not any(s in prior for s in ("APPROACH", "MOVE_ABOVE", "HOME")):
                warnings.append(
                    {
                        "field": f"steps[{i}].skill",
                        "message": "GRASP without prior APPROACH/MOVE_ABOVE",
                    }
                )
        if skill == "LIFT" and i > 0:
            if "GRASP" not in skill_order[:i]:
                errors.append(
                    {
                        "field": f"steps[{i}].skill",
                        "message": "LIFT before GRASP",
                    }
                )
        if skill == "PLACE" and i > 0:
            prior = skill_order[:i]
            if not any(s in prior for s in ("GRASP", "LIFT")):
                warnings.append(
                    {
                        "field": f"steps[{i}].skill",
                        "message": "PLACE without prior GRASP/LIFT",
                    }
                )

    # Success conditions must be verifiable
    for i, step in enumerate(steps):
        conditions = step.get("success_conditions", [])
        if not conditions:
            warnings.append(
                {
                    "field": f"steps[{i}].success_conditions",
                    "message": "no success conditions defined",
                }
            )

    # Timeout/duration sanity
    for i, step in enumerate(steps):
        duration = step.get("expected_duration_ms", 0)
        timeout = step.get("timeout_ms", 0)
        if timeout < duration:
            errors.append(
                {
                    "field": f"steps[{i}]",
                    "message": f"timeout_ms ({timeout}) < expected_duration_ms ({duration})",
                }
            )
        if timeout > 60_000:
            warnings.append(
                {
                    "field": f"steps[{i}].timeout_ms",
                    "message": f"unusually long timeout ({timeout}ms)",
                }
            )

    # Scene version consistency
    parsed_scene = parsed.get("scene_version", 0)
    if parsed_scene != 0 and parsed_scene != request.scene.scene_version:
        warnings.append(
            {
                "field": "scene_version",
                "message": (
                    f"mismatch: contract={parsed_scene}, scene={request.scene.scene_version}"
                ),
            }
        )

    # Safety constraints cannot relax edge limits
    if request.safety_policy is not None:
        sp = request.safety_policy
        safety = parsed.get("safety_constraints", {})
        if safety.get("max_tcp_velocity", 0) > sp.hard_limit_max_tcp_velocity:
            errors.append(
                {
                    "field": "safety_constraints.max_tcp_velocity",
                    "message": "cloud attempted to relax edge velocity limit",
                }
            )
        if safety.get("max_joint_velocity", 0) > sp.hard_limit_max_joint_velocity:
            errors.append(
                {
                    "field": "safety_constraints.max_joint_velocity",
                    "message": "cloud attempted to relax edge joint velocity limit",
                }
            )

    # Forbidden low-level control fields
    _check_forbidden_fields(parsed, "", errors)
    for i, step in enumerate(steps):
        _check_forbidden_fields(step, f"steps[{i}]", errors)
        params = step.get("parameters", {})
        _check_forbidden_fields(params, f"steps[{i}].parameters", errors)

    passed = len(errors) == 0
    return ValidationResult(passed=passed, errors=errors, warnings=warnings)


def _check_forbidden_fields(obj: Any, path: str, errors: list[dict[str, Any]]) -> None:
    if not isinstance(obj, dict):
        return
    for key in obj:
        if key in FORBIDDEN_KEYS:
            field = f"{path}.{key}" if path else key
            errors.append(
                {
                    "field": field,
                    "message": f"forbidden field {key!r} — low-level control or safety bypass",
                }
            )


# ── Repair ───────────────────────────────────────────────────────────────────


def attempt_repair(
    draft: PlannerDraft,
    validation: ValidationResult,
    request: InitialPlanningRequest,
) -> dict[str, Any] | None:
    """Try to repair a draft based on structured validation errors.

    Only fixes field-level issues; never adds new skills or changes intent.
    Returns repaired dict, or None if repair is impossible.
    """
    if draft.parsed_json is None:
        return None

    repaired = dict(draft.parsed_json)

    for err in validation.errors:
        field = err.get("field", "")
        msg = err.get("message", "")

        # "timeout < duration" → set timeout = duration * 2
        if "timeout_ms" in msg and "<" in msg and "expected_duration_ms" in msg:
            try:
                idx = int(field.split("[")[1].split("]")[0])
            except IndexError, ValueError:
                continue
            steps = repaired.get("steps", [])
            if idx < len(steps):
                duration = steps[idx].get("expected_duration_ms", 0)
                steps[idx]["timeout_ms"] = max(duration * 2, 3000)

        # Missing success_conditions → add generic
        if "success_conditions" in field and "no success" in msg:
            try:
                idx = int(field.split("[")[1].split("]")[0])
            except IndexError, ValueError:
                continue
            steps = repaired.get("steps", [])
            if idx < len(steps):
                skill = steps[idx].get("skill", "UNKNOWN")
                steps[idx]["success_conditions"] = [f"skill_{skill.lower()}_completed"]

        # Cloud tried to relax edge velocity → clamp
        if "attempted to relax edge velocity" in msg and request.safety_policy is not None:
            repaired.setdefault("safety_constraints", {})["max_tcp_velocity"] = (
                request.safety_policy.hard_limit_max_tcp_velocity
            )

        if "attempted to relax edge joint velocity" in msg and request.safety_policy is not None:
            repaired.setdefault("safety_constraints", {})["max_joint_velocity"] = (
                request.safety_policy.hard_limit_max_joint_velocity
            )

    # Remove forbidden fields (can't repair those — drop them)
    _strip_forbidden(repaired)
    for step in repaired.get("steps", []):
        if isinstance(step, dict):
            _strip_forbidden(step)
            if isinstance(step.get("parameters"), dict):
                _strip_forbidden(step["parameters"])

    return repaired


def _strip_forbidden(obj: dict[str, Any]) -> None:
    for key in FORBIDDEN_KEYS:
        obj.pop(key, None)


# ── Trusted-field completion ─────────────────────────────────────────────────


def complete_trusted_fields(
    parsed: dict[str, Any],
    *,
    task_id: str,
    plan_version: int,
    command_seq: int,
    issued_at: datetime,
    valid_until: datetime,
) -> dict[str, Any]:
    """Overwrite trusted fields with server-generated values."""
    completed = dict(parsed)
    completed["task_id"] = task_id
    completed["plan_version"] = plan_version
    completed["command_seq"] = command_seq
    completed["issued_at"] = issued_at.isoformat()
    completed["valid_until"] = valid_until.isoformat()
    completed["timestamp"] = issued_at.isoformat()
    return completed


# ── TaskContract construction ────────────────────────────────────────────────


def build_task_contract(completed: dict[str, Any]) -> TaskContract:
    """Construct a validated TaskContract from completed trusted fields."""
    # Remove internal sentinel if present
    completed.pop("_sentinel", None)
    completed.pop("_reason", None)
    return TaskContract(**completed)


# ── ID / version generation ──────────────────────────────────────────────────


def generate_task_id() -> str:
    entropy = uuid.uuid4().hex[:8]
    return f"task-{datetime.now(UTC).strftime('%Y%m%d')}-{entropy}"


def compute_request_hash(request: InitialPlanningRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Full pipeline ────────────────────────────────────────────────────────────


class PlanningPipeline:
    """End-to-end pipeline: request → scene check → planner → validate → repair → contract."""

    def __init__(
        self,
        *,
        planner: PlannerAdapter,
        command_ttl_ms: int = 10_000,
        max_repair_attempts: int = 2,
        scene_staleness_ms: int = 5_000,
    ) -> None:
        self._planner = planner
        self._command_ttl_ms = command_ttl_ms
        self._max_repair_attempts = max_repair_attempts
        self._scene_staleness_ms = scene_staleness_ms
        # Idempotency cache: request_id -> (request_hash, response)
        self._cache: dict[str, tuple[str, InitialPlanningResponse]] = {}

    def process(
        self,
        request: InitialPlanningRequest,
    ) -> InitialPlanningResponse:
        """Run the full planning pipeline."""
        created_at = datetime.now(UTC)

        # --- Idempotency ---
        request_hash = compute_request_hash(request)
        if request.request_id in self._cache:
            cached_hash, cached_response = self._cache[request.request_id]
            if cached_hash == request_hash:
                return cached_response
            else:
                return InitialPlanningResponse(
                    request_id=request.request_id,
                    outcome=PlanningOutcome.REJECTED,
                    reason="REQUEST_ID_CONFLICT: same request_id, different payload",
                    created_at=created_at,
                )

        # --- Scene sufficiency ---
        insufficiency = check_scene_sufficiency(
            request, scene_staleness_ms=self._scene_staleness_ms
        )
        if insufficiency is not None:
            response = InitialPlanningResponse(
                request_id=request.request_id,
                outcome=PlanningOutcome.REQUEST_MORE_OBSERVATION,
                reason=insufficiency,
                created_at=created_at,
            )
            self._cache[request.request_id] = (request_hash, response)
            return response

        # --- Call planner ---
        started = time.monotonic()
        try:
            draft = self._planner.plan(request)
        except Exception as exc:
            response = InitialPlanningResponse(
                request_id=request.request_id,
                outcome=PlanningOutcome.PLANNER_FAILED,
                reason=f"Planner exception: {exc}",
                created_at=created_at,
            )
            self._cache[request.request_id] = (request_hash, response)
            return response
        latency_ms = int((time.monotonic() - started) * 1_000)

        raw_output_hash = hashlib.sha256(draft.raw_text.encode("utf-8")).hexdigest()

        # --- Handle sentinel ---
        if draft.parsed_json and draft.parsed_json.get("_sentinel") == "REQUEST_MORE_OBSERVATION":
            reason = draft.parsed_json.get("_reason", "planner requested more observation")
            response = InitialPlanningResponse(
                request_id=request.request_id,
                outcome=PlanningOutcome.REQUEST_MORE_OBSERVATION,
                reason=reason,
                attempts=[
                    PlanningAttempt(
                        attempt=1,
                        planner_name=self._planner.planner_name,
                        model_name=self._planner.model_name,
                        prompt_version="1.0",
                        prompt_hash="",
                        temperature=0.0,
                        max_tokens=0,
                        draft=draft,
                        latency_ms=latency_ms,
                        raw_output_hash=raw_output_hash,
                    )
                ],
                created_at=created_at,
            )
            self._cache[request.request_id] = (request_hash, response)
            return response

        # --- JSON parse check ---
        if draft.parsed_json is None:
            response = InitialPlanningResponse(
                request_id=request.request_id,
                outcome=PlanningOutcome.PLANNER_FAILED,
                reason=f"Failed to parse JSON: {draft.parse_error}",
                attempts=[
                    PlanningAttempt(
                        attempt=1,
                        planner_name=self._planner.planner_name,
                        model_name=self._planner.model_name,
                        prompt_version="1.0",
                        prompt_hash="",
                        temperature=0.0,
                        max_tokens=0,
                        draft=draft,
                        latency_ms=latency_ms,
                        raw_output_hash=raw_output_hash,
                    )
                ],
                created_at=created_at,
            )
            self._cache[request.request_id] = (request_hash, response)
            return response

        # --- Trusted-field pre-fill for validation ---
        # Model output may have empty/zero trusted fields.  Fill them with
        # sensible temporary values so schema validation passes.  Final
        # values are written later through complete_trusted_fields().
        pre_task_id = generate_task_id()
        pre_now = datetime.now(UTC)
        pre_valid = pre_now + timedelta(milliseconds=self._command_ttl_ms)
        pre_filled = complete_trusted_fields(
            draft.parsed_json,
            task_id=pre_task_id,
            plan_version=1,
            command_seq=1,
            issued_at=pre_now,
            valid_until=pre_valid,
        )

        # --- Schema validation ---
        try:
            TaskContract(**pre_filled)
            schema_ok = True
            schema_errors: list[dict[str, Any]] = []
        except PydanticValidationError as exc:
            schema_ok = False
            schema_errors = [
                {
                    "field": ".".join(str(loc) for loc in err["loc"]),
                    "message": err["msg"],
                    "type": err["type"],
                }
                for err in exc.errors()
            ]

        # --- Semantic validation ---
        sem_result = semantic_validate(pre_filled, request)

        all_errors = schema_errors + sem_result.errors
        validation = ValidationResult(
            passed=(schema_ok and sem_result.passed),
            errors=all_errors,
            warnings=sem_result.warnings,
        )

        # --- Repair loop ---
        parsed = pre_filled
        repaired = False
        repair_attempts = 0
        for attempt in range(1, self._max_repair_attempts + 1):
            if validation.passed:
                break
            fixed = attempt_repair(
                PlannerDraft(raw_text=draft.raw_text, parsed_json=parsed),
                validation,
                request,
            )
            if fixed is None:
                break
            repair_attempts = attempt
            repaired = True
            # Re-validate (re-apply trusted fields for each repair iteration)
            fixed = complete_trusted_fields(
                fixed,
                task_id=pre_task_id,
                plan_version=1,
                command_seq=1,
                issued_at=pre_now,
                valid_until=pre_valid,
            )
            try:
                TaskContract(**fixed)
                schema_ok = True
                schema_errors = []
            except PydanticValidationError as exc:
                schema_ok = False
                schema_errors = [
                    {
                        "field": ".".join(str(loc) for loc in err["loc"]),
                        "message": err["msg"],
                        "type": err["type"],
                    }
                    for err in exc.errors()
                ]
            sem_result = semantic_validate(fixed, request)
            all_errors = schema_errors + sem_result.errors
            validation = ValidationResult(
                passed=(schema_ok and sem_result.passed),
                errors=all_errors,
                warnings=sem_result.warnings,
            )
            parsed = fixed

        attempt_record = PlanningAttempt(
            attempt=1,
            planner_name=self._planner.planner_name,
            model_name=self._planner.model_name,
            prompt_version="1.0",
            prompt_hash="",
            temperature=0.0,
            max_tokens=0,
            draft=draft,
            validation=validation,
            repaired=repaired,
            repair_attempts=repair_attempts,
            latency_ms=latency_ms,
            raw_output_hash=raw_output_hash,
        )

        if not validation.passed:
            # Determine failure type
            has_info_gap = any(
                "missing" in e.get("message", "").lower()
                or "not in scene" in e.get("message", "").lower()
                for e in validation.errors
            )
            if has_info_gap:
                outcome = PlanningOutcome.REQUEST_MORE_OBSERVATION
                reason = f"repair failed with info gaps: {len(validation.errors)} errors"
            else:
                outcome = PlanningOutcome.PLANNER_FAILED
                reason = f"repair failed: {len(validation.errors)} errors"
            response = InitialPlanningResponse(
                request_id=request.request_id,
                outcome=outcome,
                reason=reason,
                attempts=[attempt_record],
                validation=validation,
                created_at=created_at,
            )
            self._cache[request.request_id] = (request_hash, response)
            return response

        # --- Trusted-field completion ---
        task_id = generate_task_id()
        now = datetime.now(UTC)
        valid_until = now + timedelta(milliseconds=self._command_ttl_ms)
        completed = complete_trusted_fields(
            parsed,
            task_id=task_id,
            plan_version=1,
            command_seq=1,
            issued_at=now,
            valid_until=valid_until,
        )

        # --- Build contract ---
        try:
            contract = build_task_contract(completed)
        except Exception as exc:
            response = InitialPlanningResponse(
                request_id=request.request_id,
                outcome=PlanningOutcome.PLANNER_FAILED,
                reason=f"Contract construction failed: {exc}",
                attempts=[attempt_record],
                validation=validation,
                created_at=created_at,
            )
            self._cache[request.request_id] = (request_hash, response)
            return response

        response = InitialPlanningResponse(
            request_id=request.request_id,
            outcome=PlanningOutcome.PLANNED,
            contract=contract,
            attempts=[attempt_record],
            validation=validation,
            created_at=created_at,
        )
        self._cache[request.request_id] = (request_hash, response)
        return response
