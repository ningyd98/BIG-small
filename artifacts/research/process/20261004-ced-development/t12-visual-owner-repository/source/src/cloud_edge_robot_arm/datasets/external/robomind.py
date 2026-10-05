"""惰性读取 RoboMIND 真实 Franka RGB-D，未核验的几何与动作保持为空。"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from cloud_edge_robot_arm.datasets.external.models import DatasetSample, decode_image

_RGB_PATH = "observations/rgb_images/camera_top"
_DEPTH_PATH = "observations/depth_images/camera_top"
_STATE_PATHS = {"master/joint_position": 8, "puppet/joint_position": 8, "puppet/end_effector": 6}


def _revision(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("source revision must be a complete immutable commit SHA")
    return value


@lru_cache(maxsize=128)
def _file_digest(path: str, size: int, mtime: int, ctime: int, inode: int) -> str:
    """每个进程仅缓存稳定文件的摘要；不缓存跨 worker 的 HDF5 句柄。"""
    file = Path(path)
    digest = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    stat = file.stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino) != (
        size,
        mtime,
        ctime,
        inode,
    ):
        raise ValueError("source file changed while computing checksum")
    return digest.hexdigest()


def _sha256(file: Path) -> str:
    stat = file.stat()
    return _file_digest(str(file), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)


def _dataset(h5: h5py.File, name: str) -> h5py.Dataset:
    """拒绝链接、外部存储与虚拟映射，只读取被源文件摘要绑定的内容。"""
    for index in range(1, len(name.split("/")) + 1):
        component = "/".join(name.split("/")[:index])
        if not isinstance(h5.get(component, getlink=True), h5py.HardLink):
            raise ValueError(f"missing dataset or forbidden HDF5 link: {name}")
    value = h5.get(name)
    if not isinstance(value, h5py.Dataset):
        raise ValueError(f"missing dataset: {name}")
    if value.external:
        raise ValueError(f"external raw storage is forbidden: {name}")
    if value.is_virtual:
        raise ValueError(f"virtual dataset is forbidden: {name}")
    return value


def _validate_trajectory(h5: h5py.File) -> int:
    if "sim" not in h5.attrs or not isinstance(h5.attrs["sim"], (bool, np.bool_)):
        raise ValueError("real trajectory requires an explicit boolean sim attribute")
    if bool(h5.attrs["sim"]):
        raise ValueError("simulation trajectory is outside the real Franka subset")
    rgb, depth = _dataset(h5, _RGB_PATH), _dataset(h5, _DEPTH_PATH)
    if rgb.ndim == 0 or depth.ndim == 0 or len(rgb) == 0 or len(rgb) != len(depth):
        raise ValueError("RGB/depth trajectory lengths must be equal and nonempty")
    for name, width in _STATE_PATHS.items():
        state = _dataset(h5, name)
        if state.shape != (len(rgb), width) or state.dtype.kind not in "uif":
            raise ValueError(f"robot state dimensions or frame count mismatch: {name}")
    return len(rgb)


def _identity(relative: Path) -> tuple[str, str, str | None]:
    parts = relative.parts
    if "success_episodes" not in parts:
        raise ValueError("trajectory path lacks official task/episode identity")
    index = parts.index("success_episodes")
    if index < 1 or len(parts) <= index + 2:
        raise ValueError("trajectory path lacks official task/episode identity")
    task = parts[index - 1]
    split = parts[index + 1] if parts[index + 1] in {"train", "val", "test"} else None
    episode_index = index + (2 if split else 1)
    if len(parts) <= episode_index + 2 or parts[episode_index + 1] != "data":
        raise ValueError("trajectory path has unsupported episode structure")
    return task, parts[episode_index], split


def discover_robomind_samples(
    root: Path, source_revision: str, metadata: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """索引真实轨迹；文件级异常隔离，帧解码由后续校验惰性执行。"""
    revision = _revision(source_revision)
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"RoboMIND dataset directory is missing: {root}")
    metadata = metadata if metadata is not None else {}
    quarantine = metadata.setdefault("quarantine", [])
    if not isinstance(quarantine, list):
        raise ValueError("metadata quarantine must be a list")
    sample_metadata = {key: value for key, value in metadata.items() if key != "quarantine"}
    references: list[dict[str, Any]] = []
    candidates = sorted({*root.rglob("trajectory.hdf5"), *root.rglob("trajectory.h5")})
    for file in candidates:
        try:
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                raise ValueError("source trajectory symlink/path escape is forbidden")
            # 实际原始目录可能省略 embodiment 层；遇到明确其他机器人目录必须拒绝。
            if any(
                part.startswith("h5_") and part != "h5_franka_1rgb"
                for part in file.relative_to(root).parts
            ):
                raise ValueError("trajectory is outside the requested h5_franka_1rgb subset")
            relative = file.relative_to(root)
            task, episode, split = _identity(relative)
            digest = _sha256(file)
            with h5py.File(file, "r") as h5:
                frames = _validate_trajectory(h5)
                local_metadata = dict(sample_metadata)
                if bool(h5.attrs.get("synthetic_fixture", False)):
                    local_metadata["sample_provenance"] = "synthetic_fixture"
            references.extend(
                {
                    "dataset_id": "robomind",
                    "source_revision": revision,
                    "source_file": str(file.resolve()),
                    "source_root": str(root),
                    "relative_path": relative.as_posix(),
                    "source_sha256": digest,
                    "frame_index": frame,
                    "camera_id": "camera_top",
                    "episode_id": episode,
                    "task_id": task,
                    "official_split": split,
                    "episode_length": frames,
                    "metadata": dict(local_metadata),
                }
                for frame in range(frames)
            )
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            quarantine.append(
                {
                    "source_file": str(file),
                    "reason": str(exc),
                    "scope": "trajectory",
                    "status": "QUARANTINED",
                }
            )
    if not references:
        raise ValueError("no valid real Franka trajectory was found in the dataset")
    return references


def _depth_evidence(metadata: dict[str, Any]) -> tuple[float | None, str | None]:
    declared = metadata.get("source_depth_evidence")
    if declared is None:
        return None, None
    if not isinstance(declared, dict) or declared.get("unit") not in {"mm", "m"}:
        raise ValueError("source depth unit requires explicit mm/m evidence")
    evidence = declared.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("source depth scale requires source evidence")
    expected_scale = 0.001 if declared["unit"] == "mm" else 1.0
    if declared.get("scale_m", expected_scale) != expected_scale:
        raise ValueError("source depth unit and scale disagree")
    return expected_scale, evidence


def _robot_state(h5: h5py.File, frame: int) -> dict[str, Any]:
    master = np.asarray(_dataset(h5, "master/joint_position")[frame])
    puppet = np.asarray(_dataset(h5, "puppet/joint_position")[frame])
    end_effector = np.asarray(_dataset(h5, "puppet/end_effector")[frame])
    if not all(np.isfinite(value).all() for value in [master, puppet, end_effector]):
        raise ValueError("robot state contains nonfinite values")
    joint_semantics = ["arm_position_unconfirmed"] * 7 + ["gripper_position_unconfirmed"]
    common = {
        "joint_position_semantics": joint_semantics,
        "joint_order": "unconfirmed",
        "joint_position_units": ["unconfirmed"] * 8,
    }
    return {
        "master": {
            **common,
            "joint_position": master.tolist(),
            "role": "control_side_state; not an action label",
        },
        "puppet": {
            **common,
            "joint_position": puppet.tolist(),
            "role": "robot_side_state",
            "end_effector": end_effector.tolist(),
            "end_effector_fields": ["x", "y", "z", "roll", "pitch", "yaw"],
            "end_effector_units": ["unconfirmed"] * 6,
            "pose_convention": "official xyz+rpy; frame and angle convention unconfirmed",
        },
    }


def read_robomind_sample(ref: dict[str, Any]) -> DatasetSample:
    """每次独立打开 HDF5，压缩帧与原始 BGR 数组分别转换且不伪造时间。"""
    revision = _revision(ref["source_revision"])
    if ref.get("dataset_id") != "robomind" or ref.get("camera_id") != "camera_top":
        raise ValueError("sample identity is not the requested RoboMIND camera")
    file = Path(ref["source_file"])
    root = Path(ref["source_root"]).resolve()
    relative = Path(ref["relative_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("source relative path escapes dataset root")
    if file.is_symlink() or file.resolve() != (root / relative).resolve():
        raise ValueError("source trajectory path does not match indexed identity")
    if not file.resolve().is_relative_to(root) or not file.is_file():
        raise FileNotFoundError("indexed source trajectory is missing")
    if _sha256(file.resolve()) != ref["source_sha256"]:
        raise ValueError("source trajectory checksum does not match indexed revision")
    frame = ref["frame_index"]
    if type(frame) is not int:
        raise ValueError("frame index must be an integer")
    metadata = dict(ref.get("metadata", {}))
    scale, scale_evidence = _depth_evidence(metadata)
    timestamp, time_basis = None, "unknown"
    with h5py.File(file, "r") as h5:
        frames = _validate_trajectory(h5)
        if not 0 <= frame < frames:
            raise IndexError("frame index is outside the complete trajectory")
        rgb = decode_image(_dataset(h5, _RGB_PATH)[frame], kind="rgb", raw_color_order="BGR")
        depth = decode_image(_dataset(h5, _DEPTH_PATH)[frame], kind="depth")
        if not (np.isfinite(depth) & (depth > 0)).any():
            raise ValueError("RGB-D sample contains no valid depth pixels")
        state = _robot_state(h5, frame)
        if bool(h5.attrs.get("synthetic_fixture", False)):
            metadata["sample_provenance"] = "synthetic_fixture"
        timestamp_path = metadata.get("timestamp_path")
        if timestamp_path is not None:
            time_basis = metadata.get("timestamp_time_basis", "unknown")
            if not metadata.get("timestamp_evidence") or time_basis == "unknown":
                raise ValueError("timestamp requires original time basis and source evidence")
            timestamps = _dataset(h5, timestamp_path)
            if timestamps.shape != (frames,):
                raise ValueError("timestamp sequence length does not match RGB-D frames")
            timestamp = timestamps[frame]
            if isinstance(timestamp, np.generic):
                timestamp = timestamp.item()
    geometry = metadata.get("camera_calibration", {})
    if not isinstance(geometry, dict):
        raise ValueError("camera calibration must be an evidence-bearing object")
    if (
        geometry.get("K_rgb") is not None
        or geometry.get("K_depth") is not None
        or geometry.get("depth_semantics") is not None
    ) and not geometry.get("evidence"):
        raise ValueError("camera calibration requires source evidence")
    valid_depth = np.isfinite(depth) & (depth > 0)
    metadata.update(
        {
            "original_rgb_shape": list(rgb.shape),
            "original_depth_shape": list(depth.shape),
            "rgb_color_order": "RGB",
            "decoded_color_evidence": (
                "Pillow compressed image decoder returns RGB; raw Franka arrays BGR"
            ),
            "depth_unit": "unknown" if scale is None else ("mm" if scale == 0.001 else "m"),
            "depth_statistics": {
                "valid_ratio": float(valid_depth.mean()),
                "zero_pixels": int(np.count_nonzero(depth == 0)),
                "nonfinite_pixels": int(np.count_nonzero(~np.isfinite(depth))),
                "negative_pixels": int(np.count_nonzero(depth < 0)),
                "valid_raw_min": float(depth[valid_depth].min()),
                "valid_raw_max": float(depth[valid_depth].max()),
            },
            "frame_pairing": ("matching source indices; acquisition synchronization unverified"),
            "episode_length": frames,
            "source": "dataset_replay",
        }
    )
    return DatasetSample(
        dataset_id="robomind",
        source_revision=revision,
        sample_kind="trajectory_observation",
        source_file=str(file.resolve()),
        relative_path=ref["relative_path"],
        source_sha256=ref["source_sha256"],
        frame_index=frame,
        camera_id="camera_top",
        official_split=ref.get("official_split"),
        task_id=ref.get("task_id"),
        episode_id=ref.get("episode_id"),
        rgb=rgb,
        depth_raw=depth,
        timestamp=timestamp,
        time_basis=time_basis,
        depth_scale_m=scale,
        depth_scale_evidence=scale_evidence,
        depth_semantics=geometry.get("depth_semantics", "unknown"),
        K_rgb=geometry.get("K_rgb"),
        K_depth=geometry.get("K_depth"),
        distortion=geometry.get("distortion", {}),
        rgb_depth_aligned=geometry.get("rgb_depth_aligned"),
        alignment_evidence=geometry.get("alignment_evidence"),
        temporal_alignment=metadata.get("temporal_alignment"),
        temporal_evidence=metadata.get("temporal_evidence"),
        transforms=geometry.get("transforms", {}),
        robot_state=state,
        action=None,
        annotations={},
        metadata=metadata,
    )
