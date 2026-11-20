"""Pair timing on/off on three archived RGB-D encode inputs and on empty spans."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
from contextlib import nullcontext
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy  # noqa: F401 - activate the observed production validation path
from PIL import Image

from cloud_edge_robot_arm.research.native_action_timing import (
    ActionTiming,
    timed,
    use_action_timing,
)
from cloud_edge_robot_arm.research.native_full_horizon_originals import _restore_frame
from cloud_edge_robot_arm.simulation.models import SensorFrame
from cloud_edge_robot_arm.vision.observations import RGBDObservation, observation_from_sensor_frame

_IDS = ("acquisition-110", "acquisition-122", "acquisition-123")


def _frames(root: Path) -> tuple[list[SensorFrame], dict]:
    frames = []
    provenance = {}
    for aid in _IDS:
        relative = f"frames/{aid}/source-frame.json"
        data = (root / relative).read_bytes()
        metadata = json.loads(data)
        frame = _restore_frame(root, metadata)
        observation = RGBDObservation.model_validate(frame["observation_payload"])
        with Image.open(root / "frames" / aid / "rgb.png") as image:
            pixels = image.tobytes()
        frames.append(
            SensorFrame(
                **{
                    name: getattr(observation, name)
                    for name in (
                        "frame_id",
                        "sim_time_s",
                        "width",
                        "height",
                        "camera_to_world",
                        "captured_at",
                        "scene_id",
                        "episode_id",
                        "calibration_version",
                    )
                },
                rgb=pixels,
                depth=observation.depth_values(),
                intrinsics=tuple(observation.intrinsics),
                valid_mask=observation.valid_mask_bytes(),
            )
        )
        provenance[aid] = {
            "source_frame_sha256": hashlib.sha256(data).hexdigest(),
            "role": metadata["capture_source"]["role"],
            "source_files": frame["file_hashes"],
        }
    return frames, provenance


def _encode_replay(frames: list[SensorFrame], directory: Path) -> list[str]:
    sums = []
    for index, frame in enumerate(frames, 1):
        with timed("backend_capture", operation_id=index), timed("raw_frame_spool"):
            with timed("raw_encode"):
                raw = observation_from_sensor_frame(
                    frame, source="mujoco_camera", png_compress_level=1
                )
            with timed("metadata"), timed("spool_index_hash"):
                payload = raw.model_dump_json().encode()
                with timed("sync_write"), (directory / f"{index}.json").open("wb") as stream:
                    stream.write(payload)
                    stream.flush()
                sums.append(hashlib.sha256(payload).hexdigest())
        with timed("session_encode"):
            observation = observation_from_sensor_frame(
                frame, source="mujoco_camera", png_compress_level=1
            )
        if raw.checksum_sha256 != observation.checksum_sha256:
            raise ValueError("fixture checksum differs across encodes")
    return sums


def _empty_replay(count: int) -> None:
    for _ in range(count):
        with timed("owner_check"), timed("sqlite"):
            pass


def _sample(active, function, *args):
    trace = ActionTiming()
    with use_action_timing(trace) if active else nullcontext():
        start, cpu = perf_counter_ns(), process_time_ns()
        result = function(*args)
        wall_ns, cpu_ns = perf_counter_ns() - start, process_time_ns() - cpu
    return result, wall_ns, cpu_ns, trace.payload()


def _pairs(function, args, pairs: int) -> list[dict]:
    rows = []
    for index in range(pairs):
        recorded = {}
        for active in (False, True) if index % 2 == 0 else (True, False):
            recorded[active] = _sample(active, function, *args)
        off, on = recorded[False], recorded[True]
        if off[0] != on[0]:
            raise ValueError("probe altered paired fixture payload checksum")
        rows.append(
            dict(
                pair=index + 1,
                on_first=index % 2 == 1,
                off_wall_ns=off[1],
                on_wall_ns=on[1],
                delta_wall_ns=on[1] - off[1],
                off_cpu_ns=off[2],
                on_cpu_ns=on[2],
                delta_cpu_ns=on[2] - off[2],
                active_spans=len(on[3]["spans"]),
                serialized_trace_bytes=len(json.dumps(on[3], separators=(",", ":")).encode()),
            )
        )
    return rows


def _summarize(rows: list[dict]) -> dict:
    wall = [row["delta_wall_ns"] for row in rows]
    cpu = [row["delta_cpu_ns"] for row in rows]
    return dict(
        rows=rows,
        median_delta_wall_ns=statistics.median(wall),
        wall_delta_range_ns=[min(wall), max(wall)],
        median_delta_cpu_ns=statistics.median(cpu),
        cpu_delta_range_ns=[min(cpu), max(cpu)],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archived_originals", type=Path)
    args = parser.parse_args()
    frames, provenance = _frames(args.archived_originals)
    with tempfile.TemporaryDirectory(prefix="whole-action-probe-") as folder:
        output = Path(folder)
        expected = _encode_replay(frames, output)
        encodes = _pairs(_encode_replay, (frames, output), 30)
        empty = _pairs(_empty_replay, (4_000,), 12)
    print(
        json.dumps(
            dict(
                scope="ARCHIVED_CPU_FIXTURE_ONLY",
                frame_provenance=provenance,
                payload_sha256=expected,
                paired_encode_replay=_summarize(encodes),
                paired_empty_spans=_summarize(empty),
                fixture_has_real_egl=False,
                fixture_has_real_sqlite=False,
                fixture_has_real_owner=False,
                fixture_has_real_live_session=False,
                notes=(
                    "Same archived RGB/depth/mask at compression level 1, two actual observation "
                    "encodes and one temporary JSON write/flush per frame. Both arms call the same "
                    "instrumented code. Only ContextVar activation changes. Empty spans isolate a "
                    "Python context-entry clock and in-memory retention proxy. Serialization is "
                    "measured as bytes outside the timed sections."
                ),
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
