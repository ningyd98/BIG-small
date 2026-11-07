"""Byte-reader-only adapter for the original tracker algorithm at recorded UTC.

This private subclass is rejected by the live application's exact-type gate.
Every call requires its own validated original time, and confers no authority.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.vision.observations import RGBDObservation
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
