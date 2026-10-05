"""Unbound native RESET/clock originals; no UTC calibration or action authority."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast

from cloud_edge_robot_arm.research.native_clock_source_v2 import ClockTupleV2, canonical_bytes
from cloud_edge_robot_arm.simulation.mujoco.backend import BackendOperationBoundary
from cloud_edge_robot_arm.vision.raw_recorder_v3 import VisualRawRecorderV3, _error, _plain


def _boundary_payload(event: BackendOperationBoundary) -> dict[str, Any]:
    return cast(
        dict[str, Any], _plain({field.name: getattr(event, field.name) for field in fields(event)})
    )


@dataclass(frozen=True)
class PrefixOriginalSnapshotV2:
    """Detached historical original payload; public construction grants no ownership."""

    _json: str

    def to_payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._json))

    def digest(self) -> str:
        return hashlib.sha256(canonical_bytes(self.to_payload())).hexdigest()


class VisualResetClockRecorderV2(VisualRawRecorderV3):
    """The existing sole observer with an exact pair tee and separate RESET journal."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pair_originals: list[dict[str, Any]] = []
        self._reset_journal: list[dict[str, Any]] = []
        self._late_events: list[dict[str, Any]] = []
        self._frozen_prefix: PrefixOriginalSnapshotV2 | None = None
        self._explicit_acquisitions = 0

    @classmethod
    def from_worker_owner(
        cls,
        application: Any,
        worker_source: Any,
        backend: Any,
        capture: Any,
        executor: Any,
        *,
        clock_source: Any,
        directory: Path,
    ) -> VisualResetClockRecorderV2:
        from cloud_edge_robot_arm.research.native_clock_publication_v2 import (
            _issue_recorder_v2,
        )

        if worker_source is not None:
            raise ValueError("source-only prefix has no adopted RawV3 worker owner")
        return _issue_recorder_v2(
            application, backend, capture, executor, clock_source=clock_source, directory=directory
        )

    @property
    def clock_pair_originals(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(json.dumps(self._pair_originals)))

    @property
    def late_event_count(self) -> int:
        return len(self._late_events)

    def _clock_pair(self) -> tuple[int, int, Any, int]:
        original = super()._clock_pair()
        sequence, before, utc, after = original
        self._pair_originals.append(
            ClockTupleV2(self._clock_domain_id, sequence, before, utc, after).to_payload()
        )
        return original

    def _on_boundary(self, event: BackendOperationBoundary) -> None:
        if self._frozen_prefix is not None:
            self._late_events.append(_boundary_payload(event))
            return
        if event.kind != "RESET":
            super()._on_boundary(event)
            return
        # The callback bracket is distinct from the UTC sampling bracket.
        before = time.monotonic_ns()
        row: dict[str, Any] = {
            "reset_journal_seq": len(self._reset_journal) + 1,
            "event": _boundary_payload(event),
            "mono_before_ns": before,
            "mono_after_ns": None,
            "clock_sequence": None,
            "observer_error": None,
        }
        self._reset_journal.append(row)
        try:
            row["clock_sequence"] = self._clock_pair()[0]
            super()._on_boundary(event)
        except BaseException as error:
            row["observer_error"] = _error(error)
            raise
        finally:
            row["mono_after_ns"] = time.monotonic_ns()

    def capture(self) -> Any:
        self._explicit_acquisitions += 1
        return super().capture()

    def bind_source(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("unbound source-only prefix cannot adopt a RawV3 owner")

    def bind_worker_source(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("unbound source-only prefix cannot adopt a RawV3 owner")

    def freeze_unbound_prefix(self) -> PrefixOriginalSnapshotV2:
        self._require_open()
        if self._frozen_prefix is not None:
            raise RuntimeError("prefix original slab is already frozen")
        payload = {
            "schema_version": "native.reset.prefix.originals.v2",
            "raw_source_binding": "UNBOUND",
            "clock_domain_id": self._clock_domain_id,
            "clock_pairs": self._pair_originals,
            "reset_journal": self._reset_journal,
            "reset_metadata": self._reset_metadata,
            "reset_result": self._reset_result,
            "reset_count": self._reset_count,
            "intervals": self._intervals,
            "physics": self._physics,
            "commands": self._commands,
            "frames": self._frames,
            "frame_aux": self._frame_aux,
            "actions": self._actions,
            "purpose_allocations": self._purpose_allocations,
            "operation_ledger": self.backend.operation_ledger,
            "observer_failures": [*self.backend.operation_observer_failures, *self._audit_failures],
            "source_hashes": dict(self.source_hashes),
            "observed_episode_id": self.backend._episode_id,
            "observed_total_physics_steps": self.backend.total_physics_steps,
            "explicit_acquisitions": self._explicit_acquisitions,
        }
        self._frozen_prefix = PrefixOriginalSnapshotV2(
            json.dumps(_plain(payload), sort_keys=True, allow_nan=False)
        )
        return self._frozen_prefix

    def export_unbound_prefix(self) -> dict[str, Any]:
        self._require_open()
        if self._frozen_prefix is None:
            raise RuntimeError("export requires a frozen complete original inventory")
        self.directory.mkdir(parents=True, exist_ok=True)
        frozen = self._frozen_prefix.to_payload()
        names = {
            "reset-journal.json": "reset_journal",
            "clock-pairs.json": "clock_pairs",
            "operation-ledger.json": "operation_ledger",
            "unbound-intervals.json": "intervals",
            "unbound-physics.json": "physics",
            "unbound-commands.json": "commands",
            "unbound-frames.json": "frames",
            "purpose-allocations.json": "purpose_allocations",
            "observer-failures.json": "observer_failures",
            "source-hashes.json": "source_hashes",
        }
        hashes = {name: self._write_json(name, frozen[key]) for name, key in names.items()}
        hashes["frozen-originals.json"] = self._write_json("frozen-originals.json", frozen)
        hashes["late-events.json"] = self._write_json("late-events.json", self._late_events)
        hashes["observed-reset-source.json"] = self._write_json(
            "observed-reset-source.json",
            {key: frozen[key] for key in ("reset_metadata", "reset_result", "reset_count")},
        )
        try:
            # This preserves every cached frame and failed allocated frame; no new camera call.
            frame_hashes = self._save_frames()
            hashes.update(frame_hashes)
            hashes["persisted-frames.json"] = self._write_json(
                "persisted-frames.json", self._frames
            )
        except BaseException as error:
            self._audit_failures.append(_error(error))
        report = {
            "scope": "NATIVE_RESET_PREFIX_EXCLUDED",
            "raw_source_binding": "UNBOUND",
            "source_consistency": "INCOMPLETE",
            "snapshot_sha256": self._frozen_prefix.digest(),
            "file_hashes": hashes,
            "cached_capture_allocations": len(frozen["frames"]),
            "explicit_acquisitions": frozen["explicit_acquisitions"],
            "allocated_actions": len(frozen["actions"]),
            "late_event_count": self.late_event_count,
            "export_failures": list(self._audit_failures),
            "native_authority": "UNAVAILABLE",
            "utc_calibration": "UNAVAILABLE",
            "continuous_motion": "NOT_CERTIFIED",
        }
        self._write_json("unbound-export.json", report)
        return report
