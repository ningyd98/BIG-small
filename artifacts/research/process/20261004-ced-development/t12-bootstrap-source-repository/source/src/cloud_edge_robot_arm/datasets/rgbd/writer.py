"""Atomic episode publication, payload verification and resumable indexes.

Only a renamed episode directory with a valid COMMIT.json is authoritative.
samples.jsonl is an atomically replaced, reconstructible index of those episodes.
One dataset writer process is supported, matching the single-renderer contract.
"""

from __future__ import annotations

import base64
import errno
import hashlib
import io
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cloud_edge_robot_arm.datasets.rgbd.models import (
    DatasetConfig,
    DatasetManifest,
    SampleRecord,
    canonical_json,
    content_digest,
    safe_component,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.offline_reader import (
    load_numeric,
    load_offline_observation,
    resolve_payload,
)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value: Any) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _config(root: Path) -> DatasetConfig | None:
    path = root / "config.json"
    if not path.exists():
        return None
    return DatasetConfig.model_validate_json(resolve_payload(root, "config.json").read_bytes())


def load_manifest(root: Path) -> DatasetManifest | None:
    root = Path(root).resolve()
    if not (root / "manifest.json").exists():
        return None
    manifest = DatasetManifest.model_validate_json(
        resolve_payload(root, "manifest.json").read_bytes()
    )
    config = _config(root)
    if config is not None and manifest.config_hash != config.config_hash:
        raise ValueError("manifest/config mismatch")
    return manifest


def save_manifest(root: Path, manifest: DatasetManifest) -> None:
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Revalidate because pydantic model_copy intentionally does not validate updates.
    manifest = DatasetManifest.model_validate(manifest.model_dump(mode="json"))
    existing = load_manifest(root)
    config = _config(root)
    if (existing is not None and existing.config_hash != manifest.config_hash) or (
        config is not None and config.config_hash != manifest.config_hash
    ):
        raise ValueError("refusing to overwrite incompatible dataset config/manifest")
    _atomic_write(root / "manifest.json", _json_bytes(manifest.model_dump(mode="json")))


def _read_records(payload: bytes, root: Path) -> list[SampleRecord]:
    return [
        SampleRecord.model_validate_json(line).model_copy(update={"root": root})
        for line in payload.splitlines()
        if line.strip()
    ]


def _content_hash(record: SampleRecord, observation: RGBDObservation, instance_bytes: bytes) -> str:
    return content_digest(
        {
            "scene_hash": record.scene.scene_hash,
            "physics_state_hash": record.physics_state_hash,
            "labels": record.labels,
            "rgb": hashlib.sha256(base64.b64decode(observation.rgb_png_base64)).hexdigest(),
            "depth": hashlib.sha256(base64.b64decode(observation.depth_float32_base64)).hexdigest(),
            "mask": hashlib.sha256(observation.valid_mask_bytes()).hexdigest(),
            "instance": hashlib.sha256(instance_bytes).hexdigest(),
            "calibration": {
                key: record.observation_metadata.get(key)
                for key in (
                    "width",
                    "height",
                    "intrinsics",
                    "camera_to_world",
                    "depth_convention",
                    "calibration_version",
                    "source",
                )
            },
        }
    )


def load_records(root: Path) -> list[SampleRecord]:
    """Verify committed episodes, ignoring staging debris and a missing/stale index."""
    root = Path(root).resolve()
    config = _config(root)
    manifest = load_manifest(root)
    if config is None and manifest is not None:
        config = manifest.config
    records: list[SampleRecord] = []
    seen: set[str] = set()
    episodes = root / "episodes"
    if episodes.is_symlink():
        raise ValueError("symlink episodes path is forbidden")
    if episodes.exists():
        for directory in sorted(episodes.iterdir()):
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError("invalid committed episode path")
            safe_component(directory.name)
            prefix = f"episodes/{directory.name}/"
            commit = json.loads(resolve_payload(root, prefix + "COMMIT.json").read_bytes())
            if commit.get("schema_version") != "rgbd.dataset.v1":
                raise ValueError("unknown episode schema")
            if config is None or commit.get("config_hash") != config.config_hash:
                raise ValueError("committed episode/config mismatch")
            payload = resolve_payload(root, prefix + "records.jsonl").read_bytes()
            if hashlib.sha256(payload).hexdigest() != commit.get("records_sha256"):
                raise ValueError("episode index checksum mismatch")
            episode_records = _read_records(payload, root)
            if not episode_records or len(episode_records) != commit.get("sample_count"):
                raise ValueError("committed episode count mismatch")
            for record in episode_records:
                if record.episode_id != directory.name or record.sample_id in seen:
                    raise ValueError("duplicate or mismatched committed sample identity")
                observation = load_offline_observation(record)
                instances = load_numeric(
                    resolve_payload(root, record.paths["instance"]).read_bytes(),
                    "<i4",
                    (observation.height, observation.width),
                    "instance",
                )
                if _content_hash(record, observation, instances.tobytes()) != record.content_hash:
                    raise ValueError("sample content hash mismatch")
                seen.add(record.sample_id)
                records.append(record)
    records.sort(key=lambda item: (item.episode_id, item.sample_id))
    index = root / "samples.jsonl"
    if index.exists():
        committed = {record.sample_id: record.model_dump(mode="json") for record in records}
        indexed: set[str] = set()
        for record in _read_records(resolve_payload(root, "samples.jsonl").read_bytes(), root):
            if record.sample_id in indexed or committed.get(record.sample_id) != record.model_dump(
                mode="json"
            ):
                raise ValueError("dataset index differs from committed episodes")
            indexed.add(record.sample_id)
    return records


def _array_bytes(array: np.ndarray) -> bytes:
    stream = io.BytesIO()
    np.save(stream, array, allow_pickle=False)
    return stream.getvalue()


def _observation_payloads(observation: RGBDObservation) -> dict[str, bytes]:
    shape = (observation.height, observation.width)
    metadata = observation.model_dump(
        mode="json", exclude={"rgb_png_base64", "depth_float32_base64", "valid_mask_base64"}
    )
    return {
        "rgb": base64.b64decode(observation.rgb_png_base64, validate=True),
        "depth": _array_bytes(
            np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").reshape(
                shape
            )
        ),
        "valid_mask": _array_bytes(
            np.frombuffer(observation.valid_mask_bytes(), dtype="u1").reshape(shape)
        ),
        "camera": _json_bytes(metadata),
    }


class DatasetWriter:
    def __init__(self, root: Path, config: DatasetConfig) -> None:
        self.root = Path(root).resolve()
        self.config = DatasetConfig.model_validate(config.model_dump(mode="json"))
        self.root.mkdir(parents=True, exist_ok=True)
        existing = _config(self.root)
        manifest = load_manifest(self.root)
        if (existing is not None and existing.config_hash != config.config_hash) or (
            manifest is not None and manifest.config_hash != config.config_hash
        ):
            raise ValueError("cannot resume incompatible dataset config")
        if existing is None:
            _atomic_write(self.root / "config.json", _json_bytes(config.model_dump(mode="json")))
        for name in ("episodes", ".staging"):
            path = self.root / name
            if path.is_symlink():
                raise ValueError("symlink dataset directory is forbidden")
            path.mkdir(exist_ok=True)
        self._records = load_records(self.root)
        self._write_index()

    @property
    def records(self) -> list[SampleRecord]:
        return list(self._records)

    @property
    def total_bytes(self) -> int:
        return sum(
            path.stat().st_size
            for path in self.root.rglob("*")
            if path.is_file() and not path.is_symlink()
        )

    def _write_index(self) -> None:
        _atomic_write(
            self.root / "samples.jsonl",
            b"".join(_json_bytes(record.model_dump(mode="json")) for record in self._records),
        )

    def _prepare(self, record: SampleRecord, stage: Path) -> SampleRecord:
        frame = record.captured_frame
        if frame is None:
            raise ValueError("new records require captured_frame payload")
        # Reconstruct the boundary object instead of trusting model_copy mutations.
        record = SampleRecord.model_validate(
            {
                **record.model_dump(mode="json"),
                "captured_frame": frame,
                "raw_captured_frame": record.raw_captured_frame,
            }
        )
        observation = frame.observation
        if record.observation_metadata != observation.model_dump(
            mode="json", exclude={"rgb_png_base64", "depth_float32_base64", "valid_mask_base64"}
        ):
            raise ValueError("captured frame differs from indexed observation metadata")
        if (
            not record.physics_state_hash.strip()
            or record.physics_state_hash != frame.physics_state_hash
            or len(frame.pass_state_hashes) != 3
            or any(value != frame.physics_state_hash for value in frame.pass_state_hashes)
        ):
            raise ValueError("three render passes must preserve a nonempty indexed physics state")
        if len(frame.instance_ids) != observation.width * observation.height:
            raise ValueError("instance shape does not match camera dimensions")
        mapping: dict[int, int] = {}
        for instance in record.labels.get("instances", []):
            semantic = instance["semantic_id"]
            if type(semantic) is not int or not 1 <= semantic <= 5:
                raise ValueError("semantic instance IDs must lie in [1, 5]")
            for geom in instance["geom_ids"]:
                if type(geom) is not int or geom < 0 or geom in mapping:
                    raise ValueError("ambiguous or invalid geometry semantic mapping")
                mapping[geom] = semantic
        semantics = np.array([mapping.get(geom, 0) for geom in frame.instance_ids], dtype="<i4")
        semantics = semantics.reshape((observation.height, observation.width))
        payloads = _observation_payloads(observation)
        try:
            payloads["depth_vis"] = base64.b64decode(observation.depth_png_base64())
        except ValueError:
            stream = io.BytesIO()
            Image.new("L", (observation.width, observation.height), 0).save(stream, format="PNG")
            payloads["depth_vis"] = stream.getvalue()
        payloads.update(
            {
                "instance": _array_bytes(semantics),
                "scene": _json_bytes(record.scene.model_dump(mode="json")),
                "labels": _json_bytes(record.labels),
                "state": _json_bytes({
                    "physics_state_hash": frame.physics_state_hash,
                    "pass_state_hashes": frame.pass_state_hashes,
                }),
            }
        )
        if record.raw_captured_frame is not None:
            raw = record.raw_captured_frame
            if (
                raw.physics_state_hash != record.physics_state_hash
                or len(raw.pass_state_hashes) != 3
                or any(value != record.physics_state_hash for value in raw.pass_state_hashes)
            ):
                raise ValueError("raw evidence must share the same physics state")
            payloads.update(
                {
                    "raw_" + key: value
                    for key, value in _observation_payloads(
                        record.raw_captured_frame.observation
                    ).items()
                }
            )
            payloads["raw_state"] = _json_bytes(
                {
                    "physics_state_hash": raw.physics_state_hash,
                    "pass_state_hashes": raw.pass_state_hashes,
                }
            )
        names = {
            "rgb": "rgb.png",
            "depth": "depth.npy",
            "depth_vis": "depth_vis.png",
            "valid_mask": "valid_mask.npy",
            "instance": "instance.npy",
            "camera": "camera.json",
            "scene": "scene.json",
            "labels": "labels.jsonl",
            "state": "state.json",
            "raw_rgb": "raw_rgb.png",
            "raw_depth": "raw_depth.npy",
            "raw_valid_mask": "raw_valid_mask.npy",
            "raw_camera": "raw_camera.json",
            "raw_state": "raw_state.json",
        }
        sample_directory = stage / record.sample_id
        sample_directory.mkdir()
        for key, payload in payloads.items():
            _write_bytes(sample_directory / names[key], payload)
        _fsync_directory(sample_directory)
        return record.model_copy(
            update={
                "paths": {
                    key: f"episodes/{record.episode_id}/{record.sample_id}/{names[key]}"
                    for key in payloads
                },
                "file_hashes": {
                    key: hashlib.sha256(payload).hexdigest() for key, payload in payloads.items()
                },
                "content_hash": _content_hash(record, observation, semantics.tobytes()),
                "root": self.root,
                "captured_frame": None,
                "raw_captured_frame": None,
            }
        )

    def write_episode(self, records: Sequence[SampleRecord]) -> None:
        if not records:
            raise ValueError("cannot publish an empty episode")
        episode_ids = {safe_component(record.episode_id) for record in records}
        if len(episode_ids) != 1 or len({r.sample_id for r in records}) != len(records):
            raise ValueError("episode requires one ID and unique samples")
        episode_id = next(iter(episode_ids))
        existing = [record for record in self._records if record.episode_id == episode_id]
        if existing and all(record.captured_frame is None for record in records):
            if sorted(r.model_dump_json() for r in existing) != sorted(
                r.model_dump_json() for r in records
            ):
                raise ValueError("existing episode has different content")
            load_records(self.root)
            return
        if (
            any(r.sample_id in {item.sample_id for item in self._records} for r in records)
            and not existing
        ):
            raise ValueError("sample ID conflicts with an existing episode")
        stage_root = self.root / ".staging" / uuid.uuid4().hex
        stage = stage_root / "episodes" / episode_id
        stage.mkdir(parents=True)
        try:
            prepared = sorted(
                (self._prepare(record, stage) for record in records),
                key=lambda item: item.sample_id,
            )
            if existing:
                if [r.model_dump(mode="json") for r in existing] != [
                    r.model_dump(mode="json") for r in prepared
                ]:
                    raise ValueError("existing episode has different content")
                load_records(self.root)
                return
            for record in prepared:
                load_offline_observation(record.model_copy(update={"root": stage_root}))
            index = b"".join(_json_bytes(record.model_dump(mode="json")) for record in prepared)
            _write_bytes(stage / "records.jsonl", index)
            _write_bytes(
                stage / "COMMIT.json",
                _json_bytes(
                    {
                        "schema_version": "rgbd.dataset.v1",
                        "config_hash": self.config.config_hash,
                        "sample_count": len(prepared),
                        "records_sha256": hashlib.sha256(index).hexdigest(),
                    }
                ),
            )
            _fsync_directory(stage)
            index_growth = sum(
                len(_json_bytes(record.model_dump(mode="json"))) for record in prepared
            )
            if self.total_bytes + index_growth > self.config.max_bytes:
                raise OSError(errno.ENOSPC, "dataset byte budget exhausted")
            if shutil.disk_usage(self.root).free - index_growth < self.config.min_free_bytes:
                raise OSError(errno.ENOSPC, "dataset minimum free space budget exhausted")
            os.replace(stage, self.root / "episodes" / episode_id)
            _fsync_directory(self.root / "episodes")
            self._records = sorted(
                [*self._records, *prepared], key=lambda item: (item.episode_id, item.sample_id)
            )
            self._write_index()
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)
