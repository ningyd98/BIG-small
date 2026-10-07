"""OC2 sole-observer BOOTTIME ledger beside unchanged MONOTONIC/UTC originals."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cloud_edge_robot_arm.research.native_reset_capture_v2 import (
    VisualResetClockRecorderV2,
    _boundary_payload,
)
from cloud_edge_robot_arm.research.operational_prefix_schema_v1 import canonical_bytes_v1
from cloud_edge_robot_arm.simulation.mujoco.backend import BackendOperationBoundary
from cloud_edge_robot_arm.vision.raw_recorder_v3 import _plain

if TYPE_CHECKING:
    from cloud_edge_robot_arm.research.operational_prefix_v1 import OperationalPrefixApplicationV1

_ISSUER = object()


def _detach_original(value: Any) -> Any:
    value = _plain(value)
    if isinstance(value, bytes):
        return {"original_bytes_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {key: _detach_original(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_detach_original(item) for item in value]
    return value


def _json_boundary(event: BackendOperationBoundary) -> dict[str, Any]:
    return cast(dict[str, Any], _detach_original(_boundary_payload(event)))


class OperationalPrefixRecorderV1(VisualResetClockRecorderV2):
    """Exactly issued recorder; one observer tees the complete source denominator."""

    def __init__(
        self,
        *args: Any,
        application: OperationalPrefixApplicationV1,
        owner: Any,
        session_id: str,
        _token: object | None = None,
        **kwargs: Any,
    ) -> None:
        if _token is not _ISSUER:
            raise TypeError("operational recorder requires private application issuance")
        super().__init__(*args, **kwargs)
        self._application = application
        self._owner = owner
        self._session_id = session_id
        self._domain_sha = hashlib.sha256(canonical_bytes_v1(asdict(owner.domain))).hexdigest()
        self._d_events: list[dict[str, Any]] = []
        self._d_pending: dict[int, tuple[dict[str, Any], Any]] = {}
        self._d_receipts: dict[str, tuple[Any, Any]] = {}
        self._d_sequence = 0
        self._d_failures: list[dict[str, Any]] = []
        self._d_current: dict[str, Any] | None = None
        self._operational_frozen: dict[str, Any] | None = None
        self._operational_export: dict[str, Any] | None = None
        self._legacy_freeze_attempted = False
        self._operational_freeze_attempted = False
        self._operational_export_attempted = False
        self._operational_export_error: BaseException | None = None

    @classmethod
    def from_application(
        cls,
        application: OperationalPrefixApplicationV1,
        backend: Any,
        capture: Any,
        executor: Any,
        *,
        directory: Path,
    ) -> OperationalPrefixRecorderV1:
        from cloud_edge_robot_arm.research.operational_prefix_v1 import _issue_recorder_v1

        if cls is not OperationalPrefixRecorderV1:
            raise TypeError("exact operational recorder class required")
        return _issue_recorder_v1(application, backend, capture, executor, directory=directory)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        # Our frozen source export owns persistence; base flush would create a
        # second mutable slab after publication. No source event is synthesized.
        try:
            self._observer_context.__exit__(exc_type, exc, traceback)
        finally:
            self._open = False

    def _sequence(self) -> int:
        self._d_sequence += 1
        return self._d_sequence

    def record_failure(self, phase: str, error: BaseException) -> None:
        self._d_failures.append(
            {"phase": phase, "error_type": type(error).__name__, "error": str(error)}
        )

    def _on_boundary(self, event: BackendOperationBoundary) -> None:
        row: dict[str, Any] | None = None
        try:
            if self._operational_frozen is not None:
                raise RuntimeError("source event after operational freeze")
            if event.phase == "BEGIN":
                row = {
                    "attempt_seq": len(self._d_events) + 1,
                    "operation_id": event.operation_id,
                    "kind": event.kind,
                    "source_session_id": self._session_id,
                    "domain_sha256": self._domain_sha,
                    "begin": _json_boundary(event),
                    "end": None,
                    "begin_seq": self._sequence(),
                    "mark_seq": None,
                    "end_seq": None,
                    "token_identity": None,
                    "begin_ns": None,
                    "bracket": None,
                    "acquisition_id": None,
                    "error": None,
                }
                self._d_events.append(row)
                if event.operation_id in self._d_pending:
                    raise ValueError("duplicate operation BEGIN")
                token = self._owner.begin_event(event.kind)
                row["token_identity"] = token.event_identity
                row["begin_ns"] = self._owner._events[id(token)].lower_ns
                self._d_pending[event.operation_id] = (row, token)
                super()._on_boundary(event)
                if event.kind == "CAPTURE":
                    row["acquisition_id"] = self._operations[event.operation_id]["acquisition_id"]
                return
            entry = self._d_pending.get(event.operation_id)
            if entry is None:
                raise ValueError("operation END without original BEGIN")
            row, token = entry
            if row["end"] is not None or row["kind"] != event.kind:
                raise ValueError("duplicate/foreign operation END")
            row["end"] = _json_boundary(event)
            audit_before = len(self._audit_failures)
            super()._on_boundary(event)
            if event.error_type is not None or event.error is not None:
                raise RuntimeError("failed operation END cannot MARK")
            expected = (
                "sensor_frame"
                if event.kind == "CAPTURE"
                else "control_state"
                if event.kind == "CONTROL"
                else "physics_state"
            )
            if (
                event.result is None
                or event.result.get(expected) is None
                or len(self._audit_failures) != audit_before
            ):
                raise ValueError("trusted successful operation result unavailable")
            if event.parameters != row["begin"]["parameters"]:
                # Dataclass boundary stores detached tuples; plain forms match.
                if _json_boundary(event)["parameters"] != row["begin"]["parameters"]:
                    raise ValueError("original operation parameters changed")
            self._owner.mark_event(token)
            row["mark_seq"] = self._sequence()
            receipt = self._owner.end_event(token)
            row["end_seq"] = self._sequence()
            row["bracket"] = {
                "event_identity": receipt.event_identity,
                "lower_ns": receipt.lower_ns,
                "upper_ns": receipt.upper_ns,
                "domain_sha256": self._domain_sha,
            }
            if row["acquisition_id"] is not None:
                self._d_receipts[row["acquisition_id"]] = (token, receipt)
        except BaseException as error:
            if row is not None:
                row["error"] = {"error_type": type(error).__name__, "error": str(error)}
            self.record_failure("observer", error)
            raise

    def read_capture_current(self) -> dict[str, Any]:
        self._require_open()
        if self.last_captured_frame is None:
            raise ValueError("original explicit captured frame required")
        observation = self.last_captured_frame.observation.model_dump(mode="json")
        matches = [f for f in self._frames if f["observation_payload"] == observation]
        if not matches:
            raise ValueError("cached return lacks original source acquisition identity")
        frame = matches[-1]
        source_id = frame["source_acquisition_id"] or frame["acquisition_id"]
        if source_id not in self._d_receipts:
            raise ValueError("original capture D receipt missing")
        token, event = self._d_receipts[source_id]
        current = self._owner.read_current(after=token)
        age = self._owner.age_bounds(event, current)
        self._d_current = {
            "source_acquisition_id": source_id,
            "returned_acquisition_id": frame["acquisition_id"],
            "after_token_identity": token.event_identity,
            "domain_sha256": self._domain_sha,
            "current_identity": current.event_identity,
            "lower_ns": current.lower_ns,
            "upper_ns": current.upper_ns,
            "current_seq": self._sequence(),
            "episode_id": self.backend._episode_id,
            "physics_step": self.backend.total_physics_steps,
            "sim_time_s": self.backend.get_sim_time(),
            "age_lower_ns": age.lower_ns,
            "age_upper_ns": age.upper_ns,
            "within_5s": age.upper_ns <= 5_000_000_000,
        }
        return dict(self._d_current)

    def _detached_operational_ledger(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            _detach_original(
                {
                    "schema_version": "simulation.operational-prefix.originals.v1",
                    "source_session_id": self._session_id,
                    "domain_sha256": self._domain_sha,
                    "events": self._d_events,
                    "current": self._d_current,
                    "allocated_acquisition_ids": list(self.allocated_acquisition_ids),
                    "allocated_action_ids": list(self.allocated_action_span_ids),
                    "failures": self._d_failures,
                    "backend_observer_failures": self.backend.operation_observer_failures,
                    "super_audit_failures": self._audit_failures,
                }
            ),
        )

    def detached_partial_attempts(self) -> dict[str, Any]:
        """Actual complete attempt data independent of legacy freeze/export success."""
        return cast(
            dict[str, Any],
            _detach_original(
                {
                    "schema_version": "simulation.operational-prefix.partial-attempts.v1",
                    "source_session_id": self._session_id,
                    "domain_sha256": self._domain_sha,
                    "operational_ledger": self._detached_operational_ledger(),
                    "backend_operation_ledger": self.backend.operation_ledger,
                    "pending_operation_ids": [
                        key for key, (row, _) in self._d_pending.items() if row["end"] is None
                    ],
                    "incomplete_operation_ids": [
                        row["operation_id"] for row in self._d_events if row["bracket"] is None
                    ],
                    "legacy_operations": self._operations,
                    "legacy_intervals": self._intervals,
                    "legacy_clock_pairs": self._pair_originals,
                    "legacy_reset_journal": self._reset_journal,
                    "legacy_reset_metadata": self._reset_metadata,
                    "legacy_reset_result": self._reset_result,
                    "legacy_reset_count": self._reset_count,
                    "legacy_physics": self._physics,
                    "legacy_commands": self._commands,
                    "legacy_frames": self._frames,
                    "legacy_frame_aux": self._frame_aux,
                    "legacy_actions": self._actions,
                    "legacy_purpose_allocations": self._purpose_allocations,
                    "last_captured_frame": self.last_captured_frame,
                    "explicit_acquisitions": self._explicit_acquisitions,
                    "observed_episode_id": self.backend._episode_id,
                    "observed_total_physics_steps": self.backend.total_physics_steps,
                    "source_hashes": dict(self.source_hashes),
                }
            ),
        )

    def freeze_operational_prefix(self) -> dict[str, Any]:
        self._require_open()
        if self._operational_freeze_attempted:
            raise RuntimeError("operational originals freeze already attempted")
        self._operational_freeze_attempted = True
        # Detach the complete new ledger first: an inherited failure cannot erase it.
        self._operational_frozen = json.loads(
            canonical_bytes_v1(self._detached_operational_ledger())
        )
        if self._frozen_prefix is None:
            self._legacy_freeze_attempted = True
            self.freeze_unbound_prefix()
        return cast(dict[str, Any], json.loads(canonical_bytes_v1(self._operational_frozen)))

    def export_operational_prefix(self) -> dict[str, Any]:
        self._require_open()
        if self._operational_export_error is not None:
            raise self._operational_export_error
        if self._operational_export is not None:
            return cast(dict[str, Any], json.loads(canonical_bytes_v1(self._operational_export)))
        if self._operational_export_attempted:
            raise RuntimeError("operational export already attempted without completion")
        if self._operational_frozen is None:
            raise RuntimeError("freeze complete source denominator before export")
        self._operational_export_attempted = True
        from cloud_edge_robot_arm.research.operational_prefix_v1 import _pin, _write_exclusive_v1

        try:
            _write_exclusive_v1(
                self.directory / "operational-originals.json",
                canonical_bytes_v1(self._operational_frozen),
            )
            legacy = self.export_unbound_prefix()
            if legacy["export_failures"]:
                raise RuntimeError("legacy frame/export failure retained")
            inventory = {
                str(p.relative_to(self.directory)): _pin(p)
                for p in self.directory.rglob("*")
                if p.is_file()
            }
            self._operational_export = {"original_files": inventory, "legacy_export": legacy}
            return cast(dict[str, Any], json.loads(canonical_bytes_v1(self._operational_export)))
        except BaseException as error:
            self._operational_export_error = error
            raise
