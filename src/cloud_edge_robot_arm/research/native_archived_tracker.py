"""Byte-reader-only adapter for the original tracker algorithm at recorded UTC.

This private subclass is rejected by the live application's exact-type gate.
Every call requires its own validated original time, and confers no authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.research.native_collection_grounding import (
    RegisteredCollectionPreviewTrackerV1,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.registered_object_tracking import RegisteredObjectTrackerV1
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker


def _validated_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("original tracker time must be aware UTC")
    return value


class _ArchivedTargetTracker(OpenCVTargetTracker):
    def __init__(
        self, observation: RGBDObservation, grounding: dict[str, Any], *, evaluated_at: datetime
    ) -> None:
        self._original_time: datetime | None = _validated_utc(evaluated_at)
        try:
            super().__init__(observation, grounding)
        finally:
            self._original_time = None

    def _binding_reason(self, observation: RGBDObservation) -> str | None:
        evaluated_at = self._original_time
        if evaluated_at is None:
            raise ValueError("single-use original tracker time required")
        self._original_time = None
        self._last_binding_evaluated_at = evaluated_at
        return self._binding_reason_at(observation, evaluated_at)

    def facts_at(
        self, observation: RGBDObservation, state: RobotState, *, evaluated_at: datetime
    ) -> dict[str, Any]:
        if self._original_time is not None:
            raise ValueError("nested archive tracker clock context")
        self._original_time = _validated_utc(evaluated_at)
        try:
            return super().facts(observation, state)
        finally:
            self._original_time = None


class _ArchivedRegisteredObjectTracker(RegisteredObjectTrackerV1):
    """仅重算原记录时间的来源值；live精确类型检查拒绝此子类。"""

    def __init__(self, reference, registration, *, source_root, source_hashes, initialized_at):
        stamp = _validated_utc(initialized_at)
        if not 0 <= (stamp - reference.captured_at).total_seconds() < 5:
            raise ValueError("recorded registered bootstrap time invalid")
        self._recorded_times = (stamp, stamp)
        self._inside_update = False
        try:
            super().__init__(
                reference, registration, source_root=source_root, source_hashes=source_hashes
            )
        finally:
            self._recorded_times = None

    def _binding_reason(self, observation, evaluated_at):
        if self._recorded_times is None:
            raise ValueError("validated recorded registered time required")
        return super()._binding_reason(observation, self._recorded_times[0])

    def _recheck_current(self, observation):
        if self._recorded_times is None:
            raise ValueError("validated recorded registered time required")
        current = RGBDObservation.model_validate(observation.model_dump())
        self._verify_sources()
        stamp = self._recorded_times[0 if self._inside_update else 1]
        return super()._binding_reason(current, stamp), stamp

    def _result(self, observation, **kwargs):
        if self._recorded_times is None:
            raise ValueError("validated recorded registered time required")
        kwargs["evaluated_at"] = self._recorded_times[0]
        return super()._result(observation, **kwargs)

    def update(self, observation):
        if self._recorded_times is None:
            raise ValueError("validated recorded registered time required")
        self._inside_update = True
        try:
            return super().update(observation)
        finally:
            self._inside_update = False


class _ArchivedRegisteredCollectionTracker(RegisteredCollectionPreviewTrackerV1):
    """独立reader的原计算重建，不提供当前观测或执行认证。"""

    def __init__(self, reference, registration, *, source_root, source_hashes, initialized_at):
        import numpy as np

        from cloud_edge_robot_arm.research.native_collection_grounding import (
            collection_bootstrap_evidence,
        )
        from cloud_edge_robot_arm.vision.worker_owner import pin_worker_source_inventory

        pin_worker_source_inventory(
            source_root,
            source_hashes,
            required_paths=frozenset(
                {
                    "src/cloud_edge_robot_arm/research/native_archived_tracker.py",
                }
            ),
        )
        self._provider = _ArchivedRegisteredObjectTracker(
            reference,
            registration,
            source_root=source_root,
            source_hashes=source_hashes,
            initialized_at=initialized_at,
        )
        evidence = collection_bootstrap_evidence(reference, registration.to_payload())
        self._region_tracker = _ArchivedTargetTracker(
            reference, evidence, evaluated_at=initialized_at
        )
        footprint = np.asarray(self._region_tracker.destination["mask"], dtype=bool)
        self._reference_region_footprint = (tuple(footprint.shape), footprint.tobytes(order="C"))

    def preview_at(self, observation, state, *, evaluated_at, finished_at):
        from cloud_edge_robot_arm.research.native_collection_grounding import (
            _shared_registered_collection_preview,
        )

        start, finish = _validated_utc(evaluated_at), _validated_utc(finished_at)
        if (
            type(self) is not _ArchivedRegisteredCollectionTracker
            or self._provider._recorded_times is not None
            or not observation.captured_at <= start <= finish
            or not 0 <= (finish - observation.captured_at).total_seconds() < 5
        ):
            raise ValueError("recorded registered preview time/context invalid")
        self._provider._recorded_times = (start, finish)
        try:
            return _shared_registered_collection_preview(self, observation, state)
        finally:
            self._provider._recorded_times = None
