"""CPU惰性批读取；进程独立打开HDF5，尺寸不同保留列表避免隐式缩放。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np

from cloud_edge_robot_arm.datasets.external.models import DatasetSample


def read_sample(ref: dict[str, Any]) -> DatasetSample:
    if ref["dataset_id"] in {"industryshapes_real", "microagi01_small", "vins_rgbd_small"}:
        from cloud_edge_robot_arm.datasets.external.prepared import read_prepared_sample

        return read_prepared_sample(ref)
    if ref["dataset_id"] == "graspclutter6d_curated":
        from cloud_edge_robot_arm.datasets.external.fiftyone_curated import (
            read_curated_grasp_sample,
        )

        return read_curated_grasp_sample(ref)
    if ref["dataset_id"] == "robomind":
        from cloud_edge_robot_arm.datasets.external.robomind import read_robomind_sample

        return read_robomind_sample(ref)
    if ref["dataset_id"] == "graspclutter6d":
        from cloud_edge_robot_arm.datasets.external.graspclutter import read_grasp_sample

        return read_grasp_sample(ref)
    raise ValueError("unsupported dataset; synthetic fallback is forbidden")


def collate_samples(samples: list[DatasetSample]) -> dict[str, Any]:
    if not samples:
        raise ValueError("batch must contain real observations")
    observations = [sample.model_input() for sample in samples]
    batch: dict[str, Any] = {}
    for key in observations[0]:
        values = [row[key] for row in observations]
        if (
            all(isinstance(value, np.ndarray) for value in values)
            and len({(value.shape, value.dtype.str) for value in values}) == 1
        ):
            batch[key] = np.stack(values)
        else:
            batch[key] = values
    return batch


def time_windows(
    rows: list[dict[str, Any]], *, length: int, stride: int = 1
) -> list[list[dict[str, Any]]]:
    if length <= 0 or stride <= 0:
        raise ValueError("window length and stride must be positive")
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row.get("episode_id"):
            raise ValueError("time windows require trajectory episode identities")
        key = (
            row["dataset_id"],
            row.get("task_id"),
            row.get("source_file"),
            row["episode_id"],
            row["camera_id"],
            row.get("split", row.get("official_split")),
        )
        groups[key].append(row)
    windows = []
    for group in groups.values():
        group.sort(key=lambda row: row["frame_index"])
        for start in range(0, len(group) - length + 1, stride):
            selected = group[start : start + length]
            if all(
                b["frame_index"] == a["frame_index"] + 1
                for a, b in zip(selected, selected[1:], strict=False)
            ):
                windows.append(selected)
    return windows


def scene_views(rows: list[dict[str, Any]], scene_id: str) -> list[dict[str, Any]]:
    result = [row for row in rows if row.get("scene_id") == scene_id]
    if not result:
        raise ValueError("scene is not in the fixed index")
    return sorted(result, key=lambda row: (row["frame_index"], row["camera_id"]))


class DatasetLoader:
    def __init__(
        self, rows: list[dict[str, Any]], *, batch_size: int = 2, num_workers: int = 0
    ) -> None:
        if not rows:
            raise ValueError("dataset is missing or empty")
        if batch_size <= 0 or not 0 <= num_workers <= 16:
            raise ValueError("invalid batch size or worker count")
        self.rows = rows
        self.batch_size = batch_size
        self.num_workers = num_workers

    def __iter__(self) -> Iterator[dict[str, Any]]:
        if self.num_workers == 0:
            for start in range(0, len(self.rows), self.batch_size):
                yield collate_samples(
                    [read_sample(row) for row in self.rows[start : start + self.batch_size]]
                )
            return
        # 只提交当前batch，限制预取与子进程内存；不共享父进程HDF5句柄。
        with ProcessPoolExecutor(max_workers=self.num_workers) as pool:
            for start in range(0, len(self.rows), self.batch_size):
                refs = self.rows[start : start + self.batch_size]
                yield collate_samples(list(pool.map(read_sample, refs)))


class RoboMINDWindowLoader:
    def __init__(
        self, rows: list[dict[str, Any]], *, length: int = 4, stride: int = 1, num_workers: int = 0
    ) -> None:
        self.windows = time_windows(rows, length=length, stride=stride)
        self.num_workers = num_workers

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for window in self.windows:
            yield next(
                iter(DatasetLoader(window, batch_size=len(window), num_workers=self.num_workers))
            )


class GraspClutterViewLoader:
    def __init__(self, rows: list[dict[str, Any]], *, scene_id: str, num_workers: int = 0) -> None:
        self.views = scene_views(rows, scene_id)
        self.num_workers = num_workers

    def __iter__(self) -> Iterator[dict[str, Any]]:
        yield from DatasetLoader(self.views, num_workers=self.num_workers)
