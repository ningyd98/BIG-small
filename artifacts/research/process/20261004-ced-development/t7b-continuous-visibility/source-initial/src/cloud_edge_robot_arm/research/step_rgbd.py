"""Lossless whole-step research capture; no native or continuous certification.

The episode owner supplies only step metadata and a camera closure. Body truth
does not enter this closure or pose detection. Complete collection means every
declared physical state has a saved frame, not physical or method acceptance.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.vision.observations import RGBDObservation


def _finite(value: object) -> bool:
    return type(value) in {int, float} and math.isfinite(value)  # type: ignore[arg-type]


class StepRGBDRecorder:
    def __init__(
        self,
        directory: Path,
        capture: Callable[[], tuple[RGBDObservation, tuple[str, ...]]],
        *,
        episode_id: str,
        max_sample_gap_s: float = 0.005,
    ) -> None:
        if type(episode_id) is not str or not episode_id:
            raise ValueError("exact episode identity required")
        if not _finite(max_sample_gap_s) or not 0 < max_sample_gap_s <= 0.005:
            raise ValueError("original physical sample gap cannot be enlarged")
        self.directory = Path(directory)
        self.directory.mkdir()  # One new collection; existing data is never replaced.
        (self.directory / "frames").mkdir()
        self._index = (self.directory / "index.jsonl").open("x")
        self._capture = capture
        self.episode_id = episode_id
        self.max_sample_gap_s = max_sample_gap_s
        self._last_step = -1
        self._last_sim: float | None = None
        self._last_end: datetime | None = None
        self._camera: tuple[object, ...] | None = None
        self._ids: set[str] = set()
        self._attempted = 0
        self._completed = 0
        self._failed: str | None = None
        self._closed = False
        self._max_gap = 0.0

    def _event(self, value: dict[str, Any]) -> None:
        self._index.write(json.dumps(value, allow_nan=False) + "\n")
        self._index.flush()

    def record_step(
        self,
        *,
        episode_id: str,
        physics_step: int,
        sim_time_s: float,
    ) -> dict[str, Any]:
        if self._closed or self._failed is not None:
            raise RuntimeError("collection stopped; capture cannot be retried")
        gap = (
            sim_time_s - self._last_sim if _finite(sim_time_s) and self._last_sim is not None else 0
        )
        if (
            type(episode_id) is not str
            or episode_id != self.episode_id
            or type(physics_step) is not int
            or physics_step != self._last_step + 1
            or not _finite(sim_time_s)
            or sim_time_s < 0
            or self._last_sim is not None
            and not 0 < gap <= self.max_sample_gap_s + 1e-9
        ):
            self._failed = "step_episode_time_or_gap_invalid"
            self._event(
                {
                    "event": "REJECTED",
                    "reason": self._failed,
                    "declared_step": repr(physics_step),
                    "declared_time": repr(sim_time_s),
                }
            )
            raise ValueError(self._failed)
        begin_ns = time.monotonic_ns()
        begin_utc = datetime.now(UTC)
        row: dict[str, Any] = {
            "event": "BEGIN",
            "episode_id": episode_id,
            "physics_step": physics_step,
            "sim_time_s": sim_time_s,
            "monotonic_begin_ns": begin_ns,
            "utc_begin": begin_utc.isoformat(),
        }
        self._attempted += 1
        self._event(row)
        try:
            observation, pass_hashes = self._capture()
            observation = RGBDObservation.model_validate(observation.model_dump())
            end_ns = time.monotonic_ns()
            end_utc = datetime.now(UTC)
            row.update(monotonic_end_ns=end_ns, utc_end=end_utc.isoformat())
            if (
                type(pass_hashes) is not tuple
                or len(pass_hashes) != 2
                or any(
                    type(value) is not str
                    or len(value) != 64
                    or any(char not in "0123456789abcdef" for char in value)
                    for value in pass_hashes
                )
                or pass_hashes[0] != pass_hashes[1]
            ):
                raise ValueError("two registered render passes require identical state hashes")
            if (
                observation.episode_id != episode_id
                or abs(observation.sim_time_s - sim_time_s) > 1e-9
                or observation.observation_id in self._ids
            ):
                raise ValueError("original frame episode_time_or_identity_mismatch")
            if (
                end_ns < begin_ns
                or not begin_utc <= observation.captured_at <= end_utc
                or self._last_end is not None
                and begin_utc < self._last_end
            ):
                raise ValueError("nominal capture clock bracket invalid")
            camera = (
                observation.width,
                observation.height,
                observation.intrinsics,
                observation.camera_to_world,
                observation.calibration_version,
                observation.scene_id,
                observation.source,
            )
            if (
                not observation.calibration_version
                or not observation.scene_id
                or (self._camera is not None and self._camera != camera)
            ):
                raise ValueError("registered camera context changed or missing")
            data = observation.model_dump_json().encode()
            compressed = gzip.compress(data, compresslevel=1, mtime=0)
            relative = f"frames/{physics_step:07d}.json.gz"
            with (self.directory / relative).open("xb") as output:
                output.write(compressed)
            row.update(
                event="END",
                file=relative,
                compressed_sha256=hashlib.sha256(compressed).hexdigest(),
                observation_json_sha256=hashlib.sha256(data).hexdigest(),
                observation_checksum_sha256=observation.checksum_sha256,
                observation_id=observation.observation_id,
                captured_at=observation.captured_at.isoformat(),
                calibration_version=observation.calibration_version,
                pass_state_hashes=pass_hashes,
                original_bytes=len(data),
                compressed_bytes=len(compressed),
                external_utc_uncertainty="UNAVAILABLE",
            )
            self._event(row)
            self._last_step, self._last_sim, self._last_end = physics_step, sim_time_s, end_utc
            self._camera = camera
            self._ids.add(observation.observation_id)
            self._max_gap = max(self._max_gap, gap)
            self._completed += 1
            return row
        except BaseException as error:
            self._failed = f"{type(error).__name__}: {error}"
            self._event({**row, "event": "FAILED", "reason": self._failed})
            raise

    def finish(self, *, final_step: int, final_sim_time_s: float) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("collection already finalized")
        horizon_valid = (
            type(final_step) is int
            and final_step >= 0
            and _finite(final_sim_time_s)
            and self._last_sim is not None
            and final_step == self._last_step
            and abs(final_sim_time_s - self._last_sim) <= 1e-9
            and self._completed == final_step + 1
        )
        summary = {
            "schema_version": "research.whole-step-rgbd.v1",
            "status": "COMPLETE" if horizon_valid and self._failed is None else "INCOMPLETE",
            "episode_id": self.episode_id,
            "allocated_steps": final_step + 1
            if type(final_step) is int and final_step >= 0
            else None,
            "attempted_captures": self._attempted,
            "completed_captures": self._completed,
            "failed_captures": self._attempted - self._completed,
            "max_sim_sample_gap_s": self._max_gap,
            "original_max_sample_gap_s": self.max_sample_gap_s,
            "final_step": final_step,
            "final_sim_time_s": final_sim_time_s,
            "reason": self._failed or (None if horizon_valid else "full_terminal_horizon_mismatch"),
            "clock_scope": "SAME_PROCESS_NOMINAL_BRACKETS_ONLY",
            "external_utc_uncertainty": "UNAVAILABLE",
            "continuous_motion": "NOT_CERTIFIED",
            "formal_accepted": False,
        }
        try:
            with (self.directory / "summary.json").open("x") as output:
                output.write(json.dumps(summary, indent=2, allow_nan=False) + "\n")
        finally:
            self._index.close()
            self._closed = True
        return summary
