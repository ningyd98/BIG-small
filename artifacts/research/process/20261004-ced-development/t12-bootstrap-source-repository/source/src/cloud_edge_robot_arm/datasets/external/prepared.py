"""有摘要的逐帧派生记录；只读接口不再每帧重新扫描原始容器。"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .fiftyone_curated import _atomic_derived_write
from .models import DatasetSample, decode_image
from .transfer import hash_file

DATASETS = ("industryshapes_real", "microagi01_small", "vins_rgbd_small")
FORMAT = "bigsmall.prepared-rgbd.v1"
IDENTITY = (
    "dataset_id",
    "source_revision",
    "source_file",
    "relative_path",
    "source_sha256",
    "frame_index",
    "camera_id",
    "official_split",
    "task_id",
    "episode_id",
    "scene_id",
    "protocol",
    "timestamp",
    "time_basis",
)


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("path must be an unambiguous relative path")
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts:
        raise ValueError("relative path escapes dataset root")
    target = root / value
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("dataset symlink is forbidden")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes dataset root")
    return target


def write_observation(
    root: Path,
    fields: dict[str, Any],
    rgb: np.ndarray,
    depth: np.ndarray,
    *,
    minimum_free_bytes: int = 0,
    episode_length: int | None = None,
) -> dict[str, Any]:
    """以 PNG 无损保存原生图像，JSON 保存原始元数据和能力缺口。"""
    if fields["dataset_id"] not in DATASETS or depth.dtype != np.uint16:
        raise ValueError("prepared adapter requires a supported dataset and uint16 depth")
    DatasetSample(**fields, rgb=rgb, depth_raw=depth)
    identity = {key: fields.get(key) for key in IDENTITY}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:32]
    folder = f"records/{key}"
    safe_path(root, folder).mkdir(parents=True, exist_ok=True)
    images = {}
    for kind, array in (("rgb", rgb), ("depth", depth)):
        stream = io.BytesIO()
        Image.fromarray(array).save(stream, format="PNG")
        payload = stream.getvalue()
        relative = f"{folder}/{kind}.png"
        _atomic_derived_write(root, relative, payload, minimum_free_bytes)
        images[kind] = {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
    envelope = {"format": FORMAT, "fields": fields, "images": images}
    payload = (json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n").encode()
    relative = f"{folder}/sample.json"
    _atomic_derived_write(root, relative, payload, minimum_free_bytes)
    return {
        **identity,
        "root": str(root.resolve()),
        "source_root": str(root.resolve()),
        "record_relative_path": relative,
        "record_sha256": hashlib.sha256(payload).hexdigest(),
        "episode_length": episode_length,
        "metadata": fields.get("metadata", {}),
    }


def read_prepared_sample(ref: dict[str, Any]) -> DatasetSample:
    root = Path(ref["root"])
    record = safe_path(root, ref["record_relative_path"])
    if record.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("prepared metadata exceeds record size limit")
    if hash_file(record) != ref["record_sha256"]:
        raise ValueError("prepared record digest mismatch")
    envelope = json.loads(record.read_text())
    if envelope.get("format") != FORMAT:
        raise ValueError("unsupported prepared record format")
    fields = envelope["fields"]
    if fields["dataset_id"] not in DATASETS or any(
        fields.get(key) != ref.get(key) for key in IDENTITY
    ):
        raise ValueError("prepared reference identity differs from sealed record")
    arrays = {}
    for kind in ("rgb", "depth"):
        entry = envelope["images"][kind]
        path = safe_path(root, entry["path"])
        if path.stat().st_size > 128 * 1024 * 1024:
            raise ValueError("prepared image exceeds size limit")
        if hash_file(path) != entry["sha256"]:
            raise ValueError("prepared image digest mismatch")
        arrays[kind] = decode_image(path.read_bytes(), kind=kind)  # type: ignore[arg-type]
    if arrays["depth"].dtype != np.uint16:
        raise ValueError("prepared depth must retain uint16")
    return DatasetSample(**fields, rgb=arrays["rgb"], depth_raw=arrays["depth"])


def discover_prepared(root: Path, dataset: str, revision: str) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in safe_path(root, "samples.jsonl").read_text().splitlines()]
    if not rows:
        raise ValueError("prepared dataset contains no observations")
    for row in rows:
        if row["dataset_id"] != dataset or row["source_revision"] != revision:
            raise ValueError("prepared index identity mismatch")
        row.update(root=str(root.resolve()), source_root=str(root.resolve()))
    return rows


def pair_timestamps(
    rgb: list[dict[str, Any]],
    depth: list[dict[str, Any]],
    *,
    tolerance_ns: int,
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], dict[str, Any]]:
    """按 RGB 顺序选择最近的未使用深度帧；等距歧义不配对，保留原帧号。"""
    if isinstance(tolerance_ns, bool) or not isinstance(tolerance_ns, int) or tolerance_ns < 0:
        raise ValueError("timestamp tolerance must be a nonnegative integer")
    for frames in (rgb, depth):
        stamps = [f["timestamp_ns"] for f in frames]
        if any(type(t) is not int or t < 0 for t in stamps) or any(
            a >= b for a, b in zip(stamps, stamps[1:], strict=False)
        ):
            raise ValueError("timestamps must be unique, ordered integer nanoseconds")
    remaining = list(depth)
    pairs = []
    missed = []
    deltas = []
    for frame in rgb:
        candidates = sorted(
            (abs(frame["timestamp_ns"] - other["timestamp_ns"]), i)
            for i, other in enumerate(remaining)
            if abs(frame["timestamp_ns"] - other["timestamp_ns"]) <= tolerance_ns
        )
        if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
            missed.append(frame["frame_index"])
            continue
        delta, position = candidates[0]
        other = remaining.pop(position)
        pairs.append((frame, other))
        deltas.append(delta)
    return pairs, {
        "method": "ordered_rgb_nearest_unused_depth_no_ties",
        "tolerance_ns": tolerance_ns,
        "rgb_frames": len(rgb),
        "depth_frames": len(depth),
        "paired_frames": len(pairs),
        "unpaired_rgb": missed,
        "unpaired_depth": [f["frame_index"] for f in remaining],
        "max_delta_ns": max(deltas, default=None),
    }
