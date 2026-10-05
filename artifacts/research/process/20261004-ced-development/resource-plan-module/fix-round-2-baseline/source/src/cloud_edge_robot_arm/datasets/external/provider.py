"""dataset_replay明确属于离线模式；原时刻与回放时钟独立保存。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from cloud_edge_robot_arm.datasets.external.loaders import read_sample
from cloud_edge_robot_arm.datasets.external.models import DatasetSample


class DatasetObservationProvider:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        mode: str = "offline",
        reader: Callable[[dict[str, Any]], DatasetSample] = read_sample,
    ) -> None:
        if mode not in {"offline", "simulation_test"}:
            raise ValueError("dataset_replay provider is offline only; hardware is forbidden")
        if not rows:
            raise ValueError("dataset replay requires a nonempty real index")
        self.rows = rows
        self.reader = reader
        self.position = 0
        self.paused = False
        self.started_at = time.monotonic()
        self.last_sample: DatasetSample | None = None

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def seek(self, index: int) -> None:
        if not 0 <= index < len(self.rows):
            raise IndexError("frame index is outside the replay scope")
        self.position = index

    def select_scene_camera(self, scene_id: str, camera_id: str) -> None:
        matches = [
            i
            for i, row in enumerate(self.rows)
            if row.get("scene_id") == scene_id and row["camera_id"] == camera_id
        ]
        if not matches:
            raise ValueError("scene/camera is not in the replay scope")
        self.seek(matches[0])

    def next_observation(self) -> dict[str, Any]:
        if self.paused:
            raise RuntimeError("dataset replay is paused")
        if self.position >= len(self.rows):
            raise StopIteration
        self.last_sample = self.reader(self.rows[self.position])
        self.position += 1
        return {
            **self.last_sample.model_input(),
            "replay_elapsed_s": time.monotonic() - self.started_at,
            "replay_clock_basis": "monotonic_since_provider_start",
            "acquisition_time_unknown": (
                self.last_sample.timestamp is None
                or self.last_sample.time_basis == "mcap_log_time_ns"
            ),
            "execution_verified": False,
        }

    def oracle_annotations(self) -> dict[str, Any]:
        if self.last_sample is None:
            raise RuntimeError("no observation has been replayed")
        return {"channel": "oracle_evaluation", **self.last_sample.annotations}
