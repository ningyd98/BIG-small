"""不依赖 MongoDB/FiftyOne 的精选 RGB-D 导出只读接口。"""

from __future__ import annotations

import base64
import binascii
import errno
import hashlib
import io
import json
import math
import os
import re
import shutil
import zlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .models import DatasetSample

MAX_ARRAY_BYTES = 128 * 1024 * 1024
MAX_ARRAY_SIDE = 8192
_DATASET = "graspclutter6d_curated"
_SCHEMA = "bigsmall.fiftyone-curated-record.v1"


def _path(root: Path, relative: str) -> Path:
    """派生记录和源文件均禁止跨根、符号链接与含糊的跨平台路径。"""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("dataset path must be an unambiguous relative path")
    value = Path(relative)
    if value.is_absolute() or any(part in {"..", "."} for part in value.parts):
        raise ValueError("dataset path escapes raw root")
    candidate = root / value
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("dataset path escapes raw root")
    current = root
    for part in value.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("dataset path contains a symbolic link")
    return candidate


def _digest_uncached(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


@lru_cache(maxsize=4096)
def _cached_digest(path: str, size: int, mtime: int, ctime: int, inode: int) -> str:
    # stat 键使每帧复验不会反复扫描数百 MB 的源 samples.json。
    return _digest_uncached(Path(path))


def _digest(path: Path) -> str:
    stat = path.stat()
    return _cached_digest(
        str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino
    )


def _json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("curated source JSON must be a mapping")
    return value


def _scene_id(value: Any) -> str:
    if not re.fullmatch(r"[0-9]{1,6}", str(value)):
        raise ValueError("scene identifier must be numeric and no longer than six digits")
    return f"{int(value):06d}"


def _identity(record: dict[str, Any]) -> tuple[str, str, int]:
    scene = _scene_id(record.get("scene_id"))
    camera = record.get("camera")
    viewpoint = record.get("viewpoint")
    if not isinstance(camera, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", camera):
        raise ValueError("camera identifier must be an explicit source name")
    if (
        isinstance(viewpoint, bool)
        or not isinstance(viewpoint, int)
        or not 0 <= viewpoint <= 1000000
    ):
        raise ValueError("viewpoint must be a nonnegative source index")
    return scene, camera, viewpoint


def _decode_array(value: Any) -> np.ndarray:
    """有界解压再检查 NPY 头和长度；不执行 pickle 或加载压缩炸弹。"""
    if not isinstance(value, dict) or not isinstance(value.get("$binary"), dict):
        raise ValueError("array binary envelope is missing")
    binary = value["$binary"]
    text = binary.get("base64")
    if binary.get("subType") != "00" or not isinstance(text, str):
        raise ValueError("array binary subtype or base64 is invalid")
    if len(text) > ((MAX_ARRAY_BYTES + 2) // 3) * 4:
        raise ValueError("array binary exceeds the configured size limit")
    try:
        compressed = base64.b64decode(text, validate=True)
        decoder = zlib.decompressobj()
        payload = decoder.decompress(compressed, MAX_ARRAY_BYTES + 1)
    except (binascii.Error, zlib.error, ValueError) as exc:
        raise ValueError("array binary cannot be decoded") from exc
    if len(payload) > MAX_ARRAY_BYTES or decoder.unconsumed_tail:
        raise ValueError("compressed array exceeds the configured size limit")
    if not decoder.eof or decoder.unused_data:
        raise ValueError("compressed array stream is truncated or has trailing data")
    stream = io.BytesIO(payload)
    try:
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, _, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=16384)
        elif version == (2, 0):
            shape, _, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=16384)
        else:
            raise ValueError("unsupported array NPY format")
        if dtype.hasobject or dtype.kind not in "bifu":
            raise ValueError("array dtype must be numeric; pickle/object forbidden")
        if len(shape) != 2 or any(not 0 < size <= MAX_ARRAY_SIDE for size in shape):
            raise ValueError("array must be a bounded nonempty two-dimensional image")
        if math.prod(shape) * dtype.itemsize != len(payload) - stream.tell():
            raise ValueError("array payload length differs from its declared shape")
        array = np.load(io.BytesIO(payload), allow_pickle=False, max_header_size=16384)
    except (OSError, EOFError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid array: {exc}") from exc
    return np.asarray(array)


def _rgb_shape(path: Path, record: dict[str, Any]) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        if not 0 < width <= MAX_ARRAY_SIDE or not 0 < height <= MAX_ARRAY_SIDE:
            raise ValueError("RGB image dimensions exceed the configured limit")
        image.verify()
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("image metadata must be a mapping")
    if metadata.get("width", width) != width or metadata.get("height", height) != height:
        raise ValueError("RGB image dimensions differ from exported metadata")
    return height, width


def _visible_mask(detection: dict[str, Any], shape: tuple[int, int]) -> np.ndarray:
    box = detection.get("bounding_box")
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("visible mask requires a four-value normalized bounding box")
    values = np.asarray(box, dtype=float)
    if not np.isfinite(values).all() or (values[:2] < 0).any() or (values[2:] <= 0).any():
        raise ValueError("visible mask bounding box is invalid")
    height, width = shape
    pixels = values * np.array([width, height, width, height])
    integer = np.rint(pixels)
    if not np.allclose(pixels, integer, atol=1e-5, rtol=0):
        raise ValueError("visible mask bounding box does not define exact source pixel bounds")
    x, y, crop_width, crop_height = (int(value) for value in integer)
    if (
        x < 0
        or y < 0
        or crop_width <= 0
        or crop_height <= 0
        or x + crop_width > width
        or y + crop_height > height
    ):
        raise ValueError("visible mask bounding box exceeds RGB bounds")
    mask = _decode_array(detection.get("mask"))
    if mask.shape != (crop_height, crop_width):
        raise ValueError("visible mask crop dimensions differ from its bounding box")
    if mask.dtype.kind not in "biu" or not np.isin(mask, [0, 1, 255]).all():
        raise ValueError("visible mask must contain binary integer values")
    result = np.zeros(shape, dtype=np.uint8)
    result[y : y + crop_height, x : x + crop_width] = (mask > 0).astype(np.uint8) * 255
    return result


def _detections(record: dict[str, Any]) -> list[dict[str, Any]]:
    container = record.get("detections", {})
    if not isinstance(container, dict):
        raise ValueError("detections must be an exported mapping")
    result = container.get("detections", [])
    if (
        not isinstance(result, list)
        or len(result) > 10000
        or any(not isinstance(item, dict) for item in result)
    ):
        raise ValueError("detections must be a bounded list of instance mappings")
    return result


def _atomic_derived_write(
    root: Path, relative: str, payload: bytes, minimum_free_bytes: int
) -> None:
    """先保留完整写入空间；每块重查，失败时保留断点与原有成品。"""
    target = _path(root, relative)
    partial = _path(root, relative + ".partial")

    def check_space(size: int) -> None:
        if shutil.disk_usage(target.parent).free < minimum_free_bytes + size:
            raise RuntimeError(
                "BLOCKED_STORAGE: derived records would consume the free-space reserve"
            )

    # 空间不足时不打开或截断先前的 partial，也不覆盖原成品。
    check_space(len(payload))
    try:
        with partial.open("wb") as stream:
            for start in range(0, len(payload), 1024 * 1024):
                chunk = payload[start : start + 1024 * 1024]
                check_space(len(chunk))
                stream.write(chunk)
                stream.flush()
            os.fsync(stream.fileno())
        partial.replace(target)
    except OSError as exc:
        if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
            raise RuntimeError("BLOCKED_STORAGE: derived record storage is exhausted") from exc
        raise


def materialize_curated_records(
    root: Path,
    revision: str,
    scene_ids: list[str],
    metadata: dict[str, Any] | None = None,
    *,
    minimum_free_bytes: int = 0,
) -> dict[str, Any]:
    """只展开已选场景的图像记录；原深度与 GT blob 原样保存在派生记录中。"""
    root = root.resolve()
    if (
        isinstance(minimum_free_bytes, bool)
        or not isinstance(minimum_free_bytes, int)
        or minimum_free_bytes < 0
    ):
        raise ValueError("minimum_free_bytes must be a nonnegative integer")
    selected = {_scene_id(scene) for scene in scene_ids}
    if not selected:
        raise ValueError("at least one scene must be selected")
    sources = {name: _digest(_path(root, name)) for name in ("samples.json", "metadata.json")}
    _json(_path(root, "metadata.json"))
    samples = _json(_path(root, "samples.json")).get("samples")
    if not isinstance(samples, list):
        raise ValueError("source samples JSON must contain a samples list")
    options = dict(metadata or {})
    records: list[str] = []
    files: list[str] = []
    found: set[str] = set()
    identities: set[tuple[str, str, int]] = set()
    folder = _path(root, ".curated-records")
    folder.mkdir(exist_ok=True)
    for record in samples:
        if not isinstance(record, dict):
            raise ValueError("source sample must be a mapping")
        if (
            record.get("_media_type") != "image"
            or _scene_id(record.get("scene_id")) not in selected
        ):
            continue
        identity = _identity(record)
        if identity in identities:
            raise ValueError("duplicate scene/camera/viewpoint in curated export")
        identities.add(identity)
        found.add(identity[0])
        rgb_relative = record.get("filepath")
        if not isinstance(rgb_relative, str):
            raise ValueError("RGB filepath must be a relative dataset path")
        rgb_path = _path(root, rgb_relative)
        shape = _rgb_shape(rgb_path, record)
        stable_id = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
        masks: list[dict[str, Any]] = []
        for position, detection in enumerate(_detections(record)):
            relative = f".curated-records/{stable_id}-{position:06d}-visible.png"
            try:
                pixels = _visible_mask(detection, shape)
                target = _path(root, relative)
                encoded = io.BytesIO()
                Image.fromarray(pixels).save(encoded, format="PNG")
                _atomic_derived_write(root, relative, encoded.getvalue(), minimum_free_bytes)
                mask = {
                    "available": True,
                    "relative_path": relative,
                    "sha256": _digest(target),
                    "kind": "exported_cropped_mask",
                }
                files.append(relative)
            except (ValueError, TypeError, OSError) as exc:
                mask = {"available": False, "error": str(exc), "kind": "exported_cropped_mask"}
            masks.append(mask)
        relative = f".curated-records/{stable_id}.json"
        envelope = {
            "schema": _SCHEMA,
            "dataset_id": _DATASET,
            "source_revision": revision,
            "source_hashes": sources,
            "rgb_sha256": _digest(rgb_path),
            "record": record,
            "metadata": options,
            "visible_masks": masks,
        }
        encoded_record = (json.dumps(envelope, ensure_ascii=False, allow_nan=True) + "\n").encode(
            "utf-8"
        )
        _atomic_derived_write(root, relative, encoded_record, minimum_free_bytes)
        records.append(relative)
        files.append(relative)
    missing = selected - found
    if missing:
        raise FileNotFoundError(f"selected scene has no image records: {sorted(missing)}")
    if any(_digest(_path(root, name)) != digest for name, digest in sources.items()):
        raise ValueError("source digest changed during record materialization")
    return {"records": records, "files": files, "samples": len(records), "scenes": sorted(found)}


def _verify_hashes(root: Path, hashes: Any) -> None:
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("source digest inventory is missing")
    for relative, digest in hashes.items():
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("source digest inventory is invalid")
        if _digest(_path(root, relative)) != digest:
            raise ValueError(f"source digest mismatch: {relative}")


def _envelope(path: Path, root: Path, revision: str) -> dict[str, Any]:
    value = _json(path)
    if value.get("schema") != _SCHEMA or value.get("dataset_id") != _DATASET:
        raise ValueError("unsupported curated record schema")
    if value.get("source_revision") != revision:
        raise ValueError("curated record revision differs from requested revision")
    source_hashes = value.get("source_hashes")
    if not isinstance(source_hashes, dict) or set(source_hashes) != {
        "samples.json",
        "metadata.json",
    }:
        raise ValueError("curated record source digest binding is missing")
    _verify_hashes(root, source_hashes)
    if not isinstance(value.get("record"), dict) or not isinstance(value.get("metadata"), dict):
        raise ValueError("curated record or metadata is invalid")
    return value


def discover_curated_grasp_samples(
    root: Path, revision: str, scene_ids: list[str]
) -> list[dict[str, Any]]:
    """读取小型派生记录并复验源摘要，保留真实相机名称和源视角编号。"""
    root = root.resolve()
    selected = {_scene_id(scene) for scene in scene_ids}
    results: list[dict[str, Any]] = []
    found: set[str] = set()
    identities: set[tuple[str, str, int]] = set()
    folder = _path(root, ".curated-records")
    for path in sorted(folder.glob("*.json")):
        relative = path.relative_to(root).as_posix()
        envelope = _envelope(_path(root, relative), root, revision)
        record = envelope["record"]
        identity = _identity(record)
        if identity[0] not in selected:
            continue
        if identity in identities:
            raise ValueError("duplicate curated scene/camera/viewpoint records")
        identities.add(identity)
        found.add(identity[0])
        rgb_relative = record.get("filepath")
        if not isinstance(rgb_relative, str):
            raise ValueError("RGB filepath must be a relative dataset path")
        source_hashes = {
            **envelope["source_hashes"],
            relative: _digest(path),
            rgb_relative: envelope.get("rgb_sha256"),
        }
        masks = envelope.get("visible_masks")
        if not isinstance(masks, list) or len(masks) != len(_detections(record)):
            raise ValueError("visible mask inventory differs from exported detections")
        for mask in masks:
            if not isinstance(mask, dict):
                raise ValueError("visible mask inventory must contain mappings")
            if mask.get("available"):
                source_hashes[mask["relative_path"]] = mask["sha256"]
        _verify_hashes(root, source_hashes)
        results.append(
            {
                "dataset_id": _DATASET,
                "source_revision": revision,
                "sample_kind": "static_multiview_scene",
                "root": str(root),
                "source_root": str(root),
                "scene_id": identity[0],
                "camera_id": identity[1],
                "frame_index": identity[2],
                "official_split": None,
                "protocol": "curated_export",
                "source_file": str(_path(root, rgb_relative)),
                "relative_path": rgb_relative,
                "source_sha256": source_hashes[rgb_relative],
                "record_relative_path": relative,
                "source_hashes": source_hashes,
                "metadata": {
                    **envelope["metadata"],
                    "source_variant": "voxel51_fiftyone_curated_export",
                },
            }
        )
    if selected - found:
        raise FileNotFoundError(
            f"selected scene has no materialized image records: {sorted(selected - found)}"
        )
    return results


def read_curated_grasp_sample(ref: dict[str, Any]) -> DatasetSample:
    """未知量纲、标定、采集时间和机器人控制字段保持为空。"""
    if ref.get("dataset_id") != _DATASET:
        raise ValueError("sample reference is not a curated GraspClutter6D record")
    root = Path(ref["root"]).resolve()
    _verify_hashes(root, ref.get("source_hashes"))
    relative = ref["record_relative_path"]
    envelope = _envelope(_path(root, relative), root, ref["source_revision"])
    record = envelope["record"]
    required_hashes = {
        **envelope["source_hashes"],
        relative: _digest(_path(root, relative)),
        record.get("filepath"): envelope.get("rgb_sha256"),
    }
    masks = envelope.get("visible_masks")
    if not isinstance(masks, list) or len(masks) != len(_detections(record)):
        raise ValueError("visible mask inventory differs from exported detections")
    for mask in masks:
        if not isinstance(mask, dict):
            raise ValueError("visible mask inventory must contain mappings")
        if mask.get("available"):
            required_hashes[mask["relative_path"]] = mask["sha256"]
    if ref["source_hashes"] != required_hashes:
        raise ValueError("source digest inventory differs from the complete curated record")
    identity = _identity(record)
    if identity != (
        ref.get("scene_id"),
        ref.get("camera_id"),
        ref.get("frame_index"),
    ) or record.get("filepath") != ref.get("relative_path"):
        raise ValueError("curated sample reference identity differs from its source record")
    rgb_path = _path(root, record["filepath"])
    if _digest(rgb_path) != envelope.get("rgb_sha256") or ref.get("source_sha256") != envelope.get(
        "rgb_sha256"
    ):
        raise ValueError("RGB source digest differs from curated record")
    _rgb_shape(rgb_path, record)
    with Image.open(rgb_path) as image:
        rgb = np.array(image.convert("RGB"), dtype=np.uint8)
    depth_container = record.get("depth")
    if not isinstance(depth_container, dict):
        raise ValueError("curated RGB observation has no depth map")
    depth = _decode_array(depth_container.get("map"))
    if depth.dtype.kind not in "uif":
        raise ValueError("depth array dtype must be numeric")
    options = envelope["metadata"]
    evidence = options.get("source_depth_evidence")
    if evidence is not None and (not isinstance(evidence, str) or not evidence.strip()):
        raise ValueError("depth scale evidence must be a nonempty source citation")
    alignment_evidence = options.get("source_alignment_evidence")
    aligned: bool | None = None
    if depth.shape != rgb.shape[:2]:
        aligned = False
        alignment_evidence = None
    elif isinstance(alignment_evidence, str) and alignment_evidence.strip():
        aligned = True
    else:
        alignment_evidence = None
    instances: list[dict[str, Any]] = []
    issues: list[str] = []
    for position, detection in enumerate(_detections(record)):
        mask = dict(masks[position])
        if mask.get("available"):
            mask["path"] = str(_path(root, mask["relative_path"]))
        else:
            issues.append(f"instance {position}: {mask.get('error', 'mask unavailable')}")
        instances.append(
            {
                "instance_id": position,
                "source_instance_idx": detection.get("instance_idx"),
                "obj_id": detection.get("obj_id"),
                "label": detection.get("label"),
                "bounding_box": detection.get("bounding_box"),
                "visible_mask": mask,
                "source_detection": detection,
            }
        )
    annotations = {
        "instances": instances,
        "exported_detections": record.get("detections", {}),
        "grasp_lines": record.get("grasp_lines", {}),
        "grasp_annotation_kind": "exported_2d_visualization",
        "official_grasp_tensor_available": False,
        "issues": issues,
    }
    return DatasetSample(
        dataset_id=_DATASET,
        source_revision=ref["source_revision"],
        sample_kind="static_multiview_scene",
        source_file=str(rgb_path),
        relative_path=record["filepath"],
        source_sha256=envelope["rgb_sha256"],
        frame_index=identity[2],
        camera_id=identity[1],
        official_split=None,
        rgb=rgb,
        depth_raw=depth,
        scene_id=identity[0],
        protocol="curated_export",
        timestamp=None,
        time_basis="static_multiview_index",
        depth_scale_m=0.001 if evidence else None,
        depth_scale_evidence=evidence,
        depth_semantics="unknown",
        rgb_depth_aligned=aligned,
        alignment_evidence=alignment_evidence,
        annotations=annotations,
        metadata={
            **options,
            "source_variant": "voxel51_fiftyone_curated_export",
            "export_created_at": record.get("created_at"),
            "export_last_modified_at": record.get("last_modified_at"),
            "source_record": relative,
            "source_hashes": ref["source_hashes"],
            "upstream_image_id": None,
            "execution_verified": False,
        },
    )
