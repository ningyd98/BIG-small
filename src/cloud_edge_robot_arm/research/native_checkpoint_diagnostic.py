"""Fixed, single-use development release for the native EGL checkpoint prefix."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cloud_edge_robot_arm.research.native_calibration_collection import (
    _REGISTERED_TEACHER_CONFIG,
    ROOT,
    _registered_teacher_protocol,
    canonical,
    digest,
    fresh_directory,
    load_json,
    regular,
    save_exclusive,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.simulation.mujoco.backend import ExecutionGuardBoundaryV1
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

DIAGNOSTIC_SCHEMA = "native.checkpoint-egl.development.v1"
DIAGNOSTIC_SCOPE = "CHECKPOINT_EGL_DEVELOPMENT"
DIAGNOSTIC_ASSIGNMENT = "native-dev-checkpoint-20261120-0001"
DIAGNOSTIC_SEED = 11920067
DIAGNOSTIC_WALL_NS = 8_000_000_000
CLAIM_FILE = "diagnostic-claim.json"


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _diagnostic_recipe() -> dict[str, Any]:
    # The internal recipe retains v9's typed grounding, full horizon and sensors.
    # Its development identity can never reconstruct the nine-assignment v9 protocol.
    recipe = _registered_teacher_protocol()
    assignment = dict(
        assignment_id=DIAGNOSTIC_ASSIGNMENT,
        seed=DIAGNOSTIC_SEED,
        ancestors=["checkpoint-egl-development-20261120"],
        pool="DEVELOPMENT_ONLY",
        status="DEVELOPMENT_RELEASED",
    )
    recipe["settings"].update(
        assigned_groups=1,
        first_seed=DIAGNOSTIC_SEED,
        released_assignment=DIAGNOSTIC_ASSIGNMENT,
    )
    recipe.update(
        scope=DIAGNOSTIC_SCOPE,
        assignments=[assignment],
        released_assignments=[],
        execution_release="DEVELOPMENT_CHECKPOINT_PREFIX_ONLY",
        execution_allowed=False,
        prepare_only=False,
        budget_basis="DEVELOPMENT_CHECKPOINT_PREFIX_CEILINGS",
    )
    recipe["authorized_actual_budget"].update(teacher_acquisitions=0)
    if (
        recipe["actions"][0]["skill"] != "MOVE_ABOVE"
        or recipe["actions"][0]["recipe"]["original_timeout_ns"] != DIAGNOSTIC_WALL_NS
        or any(
            recipe["authorized_actual_budget"][key] for key in ("model_loads", "paid", "hardware")
        )
    ):
        raise ValueError("diagnostic first action or zero-model/zero-hardware budget changed")
    return recipe


def _release_path(path: Path) -> Path:
    absolute = path.absolute()
    if ".." in absolute.parts or any(
        parent.is_symlink() for parent in (absolute, *absolute.parents)
    ):
        raise ValueError("diagnostic registration requires a canonical path without symlink")
    if any(
        (parent / marker).exists()
        for parent in absolute.parents
        for marker in ("protocol.json", "startup.json")
    ):
        raise ValueError("diagnostic registration cannot be nested under another release or run")
    return absolute


def _registration(path: Path) -> dict[str, Any]:
    python = Path(sys.executable).resolve(strict=True)
    return dict(
        schema_version=DIAGNOSTIC_SCHEMA,
        scope=DIAGNOSTIC_SCOPE,
        registration_directory=str(path),
        output=str(path / "run"),
        assignment_id=DIAGNOSTIC_ASSIGNMENT,
        seed=DIAGNOSTIC_SEED,
        first_action="MOVE_ABOVE",
        step_wall_budget_ns=DIAGNOSTIC_WALL_NS,
        qualification_credit=0,
        expected_environment=dict(
            source_root=str(ROOT),
            interpreter=str(python),
            interpreter_sha256=_sha256(python),
            prefix=str(Path(sys.prefix).resolve(strict=True)),
            python_version=sys.version,
            mujoco_gl="egl",
            recipe_config_sha256=_sha256(regular(ROOT / _REGISTERED_TEACHER_CONFIG)),
        ),
        recipe=_diagnostic_recipe(),
    )


def register_checkpoint_diagnostic(output: Path) -> dict[str, Any]:
    root = _release_path(output)
    registration = _registration(root)
    fresh_directory(root)
    save_exclusive(root / "protocol.json", registration)
    return dict(
        status="CHECKPOINT_DIAGNOSTIC_REGISTERED",
        scope=DIAGNOSTIC_SCOPE,
        path=str(root),
        registration_sha256=digest(registration),
        qualification_credit=0,
    )


def _read_registration(path: Path) -> dict[str, Any]:
    root = _release_path(path)
    registration = load_json(root / "protocol.json")
    if (
        not isinstance(registration, dict)
        or registration.get("schema_version") != DIAGNOSTIC_SCHEMA
        or canonical(registration) != canonical(_registration(root))
    ):
        raise ValueError("fixed diagnostic registration, source and output required")
    return registration


def _require_egl_source() -> None:
    if Path.cwd() != ROOT or os.environ.get("MUJOCO_GL") != "egl":
        raise ValueError(
            "diagnostic requires the registered source root and explicit MUJOCO_GL=egl"
        )
    # An earlier offscreen import can choose another driver permanently for this process.
    gl = sys.modules.get("mujoco.gl_context")
    if (
        gl is not None
        and getattr(getattr(gl, "GLContext", None), "__module__", None) != "mujoco.egl"
    ):
        raise ValueError("diagnostic already imported a non-EGL MuJoCo renderer")


def _import_sources(registered_hashes: dict[str, str]) -> dict[str, dict[str, str]]:
    """Record real imported file origins once per command boundary, outside the guard."""
    imported: dict[str, dict[str, str]] = {}
    for name, module in sorted(sys.modules.copy().items()):
        spec = getattr(module, "__spec__", None)
        origin = getattr(spec, "origin", None)
        if not isinstance(origin, str) or origin in {"built-in", "frozen"}:
            continue
        path = Path(origin).resolve()
        if not path.is_file():
            continue
        sha = _sha256(path)
        if name == "cloud_edge_robot_arm" or name.startswith("cloud_edge_robot_arm."):
            if (
                not path.is_relative_to(ROOT)
                or registered_hashes.get(str(path.relative_to(ROOT))) != sha
            ):
                raise ValueError("diagnostic imported source does not match registration: " + name)
        imported[name] = dict(path=str(path), sha256=sha)
    return imported


def _read_cutoff_result(path: Path, *, registration_sha256: str) -> dict[str, Any] | None:
    try:
        result: object = load_json(path)
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(result, dict):
        return None
    qualification = result.get("qualification_credit")
    if (
        result.get("status") != "COLLECTION_PARTIAL"
        or result.get("assignment_id") != DIAGNOSTIC_ASSIGNMENT
        or result.get("scope") != DIAGNOSTIC_SCOPE
        or type(qualification) is not int
        or qualification != 0
        or result.get("final_lifecycle_receipt") is not True
        or result.get("execution_admitted") is not False
        or result.get("teacher_collection_admitted") is not False
        or result.get("native_qualification") != "UNKNOWN"
    ):
        return None
    diagnostic = result.get("checkpoint_diagnostic")
    if not isinstance(diagnostic, dict):
        return None
    qualification = diagnostic.get("qualification_credit")
    if (
        diagnostic.get("status") != "CUTOFF"
        or diagnostic.get("scope") != DIAGNOSTIC_SCOPE
        or diagnostic.get("registration_sha256") != registration_sha256
        or type(qualification) is not int
        or qualification != 0
    ):
        return None
    failures = result.get("failures")
    if not isinstance(failures, list) or any(not isinstance(row, dict) for row in failures):
        return None
    primary = [row for row in failures if row.get("role") == "PRIMARY"]
    deadline_type = _CheckpointDiagnosticDeadline.__name__
    if len(primary) != 1 or not all(
        primary[0].get(key) == value
        for key, value in (
            ("phase", "collection_body"),
            ("error_type", deadline_type),
            ("error", f"{deadline_type}: 8-second development first-action deadline reached"),
        )
    ):
        return None
    return result


def _worker_terminal_matches(error: RuntimeError, receipt: dict[str, Any]) -> bool:
    # execute_once includes the worker snapshot in its terminal RuntimeError.
    # A receipt from the same registration alone does not identify that exception.
    prefix = "worker terminal outcome: "
    if type(error) is not RuntimeError or len(error.args) != 1:
        return False
    message = error.args[0]
    snapshot = receipt.get("worker_snapshot")
    if not isinstance(message, str) or not message.startswith(prefix):
        return False
    if not isinstance(snapshot, dict):
        return False
    try:
        observed: object = json.loads(message[len(prefix) :])
        return isinstance(observed, dict) and canonical(observed) == canonical(snapshot)
    except (ValueError, RecursionError):
        return False


def run_checkpoint_diagnostic(protocol: Path) -> dict[str, Any]:
    from cloud_edge_robot_arm.research.native_collection_application import (
        NativeCollectionApplication,
    )

    registration = _read_registration(protocol)
    registration_sha256 = digest(registration)
    sources = registration["recipe"]["source_hashes"]
    before = _import_sources(sources)
    app = NativeCollectionApplication.from_checkpoint_diagnostic(protocol)
    try:
        return app.execute_once()
    except RuntimeError as error:
        receipt = _read_cutoff_result(
            app.output / "collection-result.json", registration_sha256=registration_sha256
        )
        if receipt is not None and _worker_terminal_matches(error, receipt):
            return receipt
        raise
    finally:
        after = _import_sources(sources)
        if any(after.get(name) != row for name, row in before.items()):
            raise ValueError("diagnostic imported source changed during execution")
        save_exclusive(
            app.output / "imported-source-manifest.json",
            dict(
                registration_sha256=registration_sha256,
                before=before,
                after=after,
            ),
        )


class _CheckpointDiagnosticDeadline(RuntimeError):
    """The development cutoff is carried through the original fail-closed stop."""


@dataclass(slots=True)
class _CheckpointDiagnostic:
    registration_sha256: str
    first_action_started_monotonic_ns: int | None = None
    cutoff_monotonic_ns: int | None = None
    last_authorized_monotonic_ns: int | None = None
    last_authorized_checkpoint: dict[str, Any] | None = None
    cutoff_observed_monotonic_ns: int | None = None
    rejected_checkpoint: dict[str, Any] | None = None
    guard_exit_monotonic_ns: int | None = None
    body_cleanup_finished_monotonic_ns: int | None = None
    dispatch_physics_step: int | None = None
    final_physics_step: int | None = None
    mode: str | None = None
    reads_attempted: int = 0
    reads_completed: int = 0
    readonly_snapshots: int = 0
    read_wall_ns: int = 0
    action_reads_attempted: int = 0
    action_reads_completed: int = 0
    action_read_wall_ns: int = 0

    def start_action(self, now: int, physics_step: int) -> None:
        if self.first_action_started_monotonic_ns is not None:
            raise RuntimeError("diagnostic first action can start only once")
        self.first_action_started_monotonic_ns = now
        self.cutoff_monotonic_ns = now + DIAGNOSTIC_WALL_NS
        self.dispatch_physics_step = physics_step
        self.last_authorized_monotonic_ns = None
        self.last_authorized_checkpoint = None

    def authorize(self, checkpoint: ExecutionGuardBoundaryV1, now: int) -> None:
        if self.cutoff_monotonic_ns is None:
            return
        if now >= self.cutoff_monotonic_ns:
            self.cutoff_observed_monotonic_ns = now
            self.rejected_checkpoint = asdict(checkpoint)
            raise _CheckpointDiagnosticDeadline(
                "8-second development first-action deadline reached"
            )
        self.last_authorized_monotonic_ns = now
        self.last_authorized_checkpoint = asdict(checkpoint)

    @contextmanager
    def measure_sqlite(
        self,
        read_scope: AbstractContextManager[Any],
        repository: SQLiteSimulationJobRepository,
        mode: str,
    ) -> Iterator[None]:
        action = self.first_action_started_monotonic_ns is not None
        self.mode = mode
        self.reads_attempted += 1
        self.action_reads_attempted += int(action)
        began = time.monotonic_ns()
        try:
            with read_scope:
                if repository._teacher_checkpoint_connection() is not None:
                    self.readonly_snapshots += 1
                else:
                    raise RuntimeError("diagnostic requires the actual readonly SQLite snapshot")
                yield
            self.reads_completed += 1
            self.action_reads_completed += int(action)
        finally:
            elapsed = time.monotonic_ns() - began
            self.read_wall_ns += elapsed
            if action:
                self.action_read_wall_ns += elapsed

    def confirm_guard_authorization(self, checks: list[Any], guard_events: tuple[Any, ...]) -> None:
        # A callback can return before the backend's remaining observer veto.
        self.last_authorized_monotonic_ns = None
        self.last_authorized_checkpoint = None
        for check in reversed(checks):
            sequence = check.get("guard_sequence")
            if sequence is not None and guard_events[sequence - 1].get("outcome") == "ALLOWED":
                self.last_authorized_monotonic_ns = check["diagnostic_authorized_monotonic_ns"]
                self.last_authorized_checkpoint = check["checkpoint"]
                break

    def payload(self, *, prefix_complete: bool) -> dict[str, Any]:
        fields = asdict(self)
        sqlite = {
            key: fields.pop(key)
            for key in (
                "mode",
                "reads_attempted",
                "reads_completed",
                "readonly_snapshots",
                "read_wall_ns",
                "action_reads_attempted",
                "action_reads_completed",
                "action_read_wall_ns",
            )
        }
        return dict(
            scope=DIAGNOSTIC_SCOPE,
            qualification_credit=0,
            status="CUTOFF"
            if self.cutoff_observed_monotonic_ns is not None
            else "PREFIX_COMPLETE"
            if prefix_complete
            else "EARLY_STOP",
            **fields,
            sqlite=sqlite,
            cutoff_cost_scope="MONOTONIC_CHECKPOINT_AUTHORIZATION",
            sqlite_cost_scope="MONOTONIC_CONTEXT_ENTRY_THROUGH_EXIT_WITH_TWO_CLOCK_READS",
            post_shutdown_physics="UNKNOWN",
        )
