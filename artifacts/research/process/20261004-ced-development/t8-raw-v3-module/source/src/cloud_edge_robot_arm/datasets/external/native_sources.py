"""三套已选真实源转换为惰性逐帧记录；不修改上游文件或猜测能力。"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Any, Literal

import numpy as np
from PIL import Image

from .fiftyone_curated import _atomic_derived_write
from .models import decode_image, validate_intrinsics, validate_transform
from .prepared import pair_timestamps, safe_path, write_observation


def _base(plan: dict[str, Any], source: Path, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset_id": plan["dataset_id"],
        "source_revision": plan["revision"],
        "source_file": str(safe_path(source, entry["path"])),
        "relative_path": entry["path"],
        "source_sha256": entry["sha256"],
        "official_split": None,
        "depth_excluded_values": [65535],
        "depth_validity_evidence": "BIGsmall conservative uint16 saturation exclusion; "
        "source sentinel semantics unverified; raw values retained",
        "metadata": {"execution_verified": False, "source_variant": plan["dataset_id"]},
    }


def _container(plan: dict[str, Any], suffix: str) -> dict[str, Any]:
    files = [f for f in plan["files"] if f["path"].endswith(suffix)]
    if len(files) != 1:
        raise ValueError("selected native reader requires exactly one source container")
    return dict(files[0])


def convert_industry(
    plan: dict[str, Any],
    source: Path,
    output: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    files = {f["path"]: f for f in plan["files"]}
    source_index = safe_path(source, "samples.json")
    if source_index.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("IndustryShapes source index exceeds selected reader size limit")
    samples = json.loads(source_index.read_text())["samples"]
    refs = []
    identities = set()
    instances_count = 0
    for record in samples:
        if record.get("dataset_subset") != "classic" or record.get("split") != "test":
            continue
        rgb_path = record["filepath"]
        depth_path = record.get("depth", {}).get("map_path")
        if rgb_path not in files or depth_path not in files:
            continue
        scene, frame = record["scene_id"], record["image_id"]
        if not all(isinstance(v, str) and v.isdecimal() for v in (scene, frame)):
            raise ValueError("IndustryShapes requires explicit numeric scene/image identity")
        identity = (scene, frame)
        if identity in identities:
            raise ValueError("duplicate IndustryShapes scene/frame identity")
        identities.add(identity)
        if isinstance(record["depth_scale"], bool) or record["depth_scale"] != 1:
            raise ValueError("selected classic depth_scale must be the reviewed 1 mm")
        rgb = decode_image(safe_path(source, rgb_path).read_bytes(), kind="rgb")
        depth = decode_image(safe_path(source, depth_path).read_bytes(), kind="depth")
        shape = (record["metadata"]["height"], record["metadata"]["width"])
        if rgb.shape[:2] != shape or depth.shape != shape:
            raise ValueError("IndustryShapes image dimensions disagree with source metadata")
        k = validate_intrinsics(record["camera_intrinsics"])
        if k is None:
            raise ValueError("IndustryShapes source intrinsics are missing")
        instances = []
        for position, detection in enumerate(record["ground_truth"]["detections"]):
            matrix = np.eye(4)
            matrix[:3, :3] = detection["rotation_matrix"]
            matrix[:3, 3] = np.asarray(detection["translation_mm"], dtype=float) / 1000
            transform = validate_transform(
                {
                    "from_frame": "object",
                    "to_frame": "camera",
                    "translation_unit": "m",
                    "matrix": matrix,
                }
            )
            instances.append(
                {
                    "instance_id": position,
                    "obj_id": detection["obj_id"],
                    "model_to_camera": transform,
                    "source_detection": detection,
                }
            )
        if not instances:
            raise ValueError("selected IndustryShapes ground truth is missing")
        fields = _base(plan, source, files[rgb_path])
        fields.update(
            sample_kind="static_multiview_scene",
            camera_id="source_camera",
            scene_id=scene,
            frame_index=int(frame),
            official_split="test",
            protocol="classic_real_test",
            timestamp=None,
            time_basis="static_image_index",
            K_rgb=k.tolist(),
            depth_scale_m=0.001,
            depth_scale_evidence=(
                "pinned IndustryShapes README classic millimetres; sample depth_scale=1"
            ),
            annotations={"instances": instances},
        )
        fields["metadata"].update(
            depth_source_path=depth_path,
            depth_source_sha256=files[depth_path]["sha256"],
            source_index_sha256=files["samples.json"]["sha256"],
            camera_intrinsics_assignment=(
                "source image camera; depth-camera registration unverified"
            ),
        )
        refs.append(
            write_observation(
                output, fields, rgb, depth, minimum_free_bytes=plan["minimum_free_bytes"]
            )
        )
        instances_count += len(instances)
    if not refs:
        raise ValueError("selected manifest has no IndustryShapes RGBD pairs")
    return refs, {
        "samples": len(refs),
        "scenes": len({r["scene_id"] for r in refs}),
        "instances": instances_count,
        "official_split": "test",
    }


def _cache_frame(folder: Path, name: str, image: bytes | np.ndarray, reserve: int) -> str:
    if isinstance(image, np.ndarray):
        encoded = io.BytesIO()
        Image.fromarray(image).save(encoded, format="PNG")
        image = encoded.getvalue()
    _atomic_derived_write(folder, name, image, reserve)
    return str(folder / name)


def convert_microagi(
    plan: dict[str, Any],
    source: Path,
    output: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .mcap_native import iter_mcap_messages

    entry = _container(plan, ".mcap")
    base = _base(plan, source, entry)
    output.mkdir(parents=True, exist_ok=True)
    frames: dict[str, list[dict[str, Any]]] = {"rgb": [], "depth": []}
    calibration: dict[str, Any] = {}
    refs = []
    kind: Literal["rgb", "depth"]
    with tempfile.TemporaryDirectory(prefix="native-frames-", dir=output) as temp:
        cache = Path(temp)
        for item in iter_mcap_messages(Path(base["source_file"])):
            topic, message = item["topic"], item["message"]
            if topic in {"/camera/color/image", "/camera/depth/image"}:
                kind = "rgb" if topic == "/camera/color/image" else "depth"
                if len(frames[kind]) >= 10000:
                    raise ValueError("selected MicroAGI frame count limit exceeded")
                index = len(frames[kind])
                array = decode_image(message["data"], kind=kind)
                if kind == "depth" and array.dtype != np.uint16:
                    raise ValueError("MicroAGI numeric depth must be uint16")
                path = _cache_frame(
                    cache, f"{kind}-{index}.image", message["data"], plan["minimum_free_bytes"]
                )
                frames[kind].append(
                    {
                        "frame_index": index,
                        "path": path,
                        "shape": list(array.shape),
                        "timestamp_ns": item["timestamp_ns"],
                        "publish_time_ns": item["publish_time_ns"],
                        "sequence": item["sequence"],
                        "embedded_timestamp": message.get("timestamp"),
                    }
                )
            elif topic in {
                "/camera/color/info",
                "/camera/depth/info",
                "/camera/depth/unit_of_depth_in_mm",
                "/tf_static",
            }:
                if topic in calibration and calibration[topic] != message:
                    raise ValueError("changing MicroAGI calibration requires per-frame handling")
                calibration[topic] = message
        required = {"/camera/color/info", "/camera/depth/info", "/camera/depth/unit_of_depth_in_mm"}
        if not required <= calibration.keys():
            raise ValueError("MicroAGI calibration/depth unit messages missing")
        unit = calibration["/camera/depth/unit_of_depth_in_mm"]["unit_in_mm"]
        if not np.isfinite(unit) or unit <= 0:
            raise ValueError("invalid MicroAGI source depth unit")
        pairs, pairing = pair_timestamps(frames["rgb"], frames["depth"], tolerance_ns=10_000_000)
        for color, depth in pairs:
            fields = {**base, "metadata": dict(base["metadata"])}
            infos = [calibration[f"/camera/{name}/info"] for name in ("color", "depth")]
            for frame, info in zip((color, depth), infos, strict=True):
                if frame["shape"][:2] != [info["height"], info["width"]]:
                    raise ValueError("MicroAGI image dimensions disagree with CameraInfo")
            fields.update(
                sample_kind="trajectory_observation",
                episode_id=Path(entry["path"]).stem,
                camera_id="native_color_depth",
                frame_index=color["frame_index"],
                timestamp=color["timestamp_ns"],
                time_basis="mcap_log_time_ns",
                depth_scale_m=float(unit) / 1000,
                depth_scale_evidence="recorded /camera/depth/unit_of_depth_in_mm protobuf message",
                K_rgb=np.asarray(infos[0]["K"]).reshape(3, 3).tolist(),
                K_depth=np.asarray(infos[1]["K"]).reshape(3, 3).tolist(),
                distortion={
                    "rgb": infos[0].get("D"),
                    "depth": infos[1].get("D"),
                    "rgb_model": infos[0].get("distortion_model"),
                    "depth_model": infos[1].get("distortion_model"),
                },
                rgb_depth_aligned=False,
            )
            fields["metadata"].update(
                rgb_time={k: v for k, v in color.items() if k != "path"},
                depth_time={k: v for k, v in depth.items() if k != "path"},
                pairing_basis=(
                    "nearest recorded log time within 10 ms; acquisition synchronization unverified"
                ),
                calibration_messages=calibration,
            )
            refs.append(
                write_observation(
                    output,
                    fields,
                    decode_image(Path(color["path"]).read_bytes(), kind="rgb"),
                    decode_image(Path(depth["path"]).read_bytes(), kind="depth"),
                    minimum_free_bytes=plan["minimum_free_bytes"],
                    episode_length=len(frames["rgb"]),
                )
            )
    if not refs:
        raise ValueError("MicroAGI has no paired RGBD frames")
    return refs, {
        "samples": len(refs),
        "pairing": pairing,
        "calibration": calibration,
        "sequence_kind": "human_egocentric_observations_not_robot_actions",
    }


def convert_vins(
    plan: dict[str, Any],
    source: Path,
    output: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .rosbag_native import RGB_TOPIC, iter_ros1_images

    entry = _container(plan, ".bag")
    base = _base(plan, source, entry)
    output.mkdir(parents=True, exist_ok=True)
    frames: dict[str, list[dict[str, Any]]] = {"rgb": [], "depth": []}
    refs = []
    with tempfile.TemporaryDirectory(prefix="native-frames-", dir=output) as temp:
        cache = Path(temp)
        for item in iter_ros1_images(Path(base["source_file"])):
            kind = "rgb" if item["topic"] == RGB_TOPIC else "depth"
            index = len(frames[kind])
            if index >= 10000:
                raise ValueError("selected VINS frame count limit exceeded")
            path = _cache_frame(
                cache, f"{kind}-{index}.png", item.pop("array"), plan["minimum_free_bytes"]
            )
            frames[kind].append({**item, "frame_index": index, "path": path})
        pairs, pairing = pair_timestamps(frames["rgb"], frames["depth"], tolerance_ns=0)
        for color, depth in pairs:
            fields = {**base, "metadata": dict(base["metadata"])}
            fields.update(
                sample_kind="trajectory_observation",
                episode_id=entry["path"],
                camera_id="color_and_aligned_depth",
                frame_index=color["frame_index"],
                timestamp=color["timestamp_ns"],
                time_basis="ros_header_stamp_ns",
                temporal_alignment=True,
                temporal_evidence="exact RGB/depth ROS header.stamp equality",
            )
            fields["metadata"].update(
                rgb_header=color["header"],
                depth_header=depth["header"],
                rgb_bag_time_ns=color["bag_time_ns"],
                depth_bag_time_ns=depth["bag_time_ns"],
                rgb_topic=color["topic"],
                depth_topic=depth["topic"],
                source_depth_frame_index=depth["frame_index"],
                alignment_note=(
                    "aligned topic name retained; pixel registration independently unverified"
                ),
                geometry_note="CameraInfo and verified depth scale absent in selected source",
            )
            refs.append(
                write_observation(
                    output,
                    fields,
                    decode_image(Path(color["path"]).read_bytes(), kind="rgb"),
                    decode_image(Path(depth["path"]).read_bytes(), kind="depth"),
                    minimum_free_bytes=plan["minimum_free_bytes"],
                    episode_length=len(frames["rgb"]),
                )
            )
    if not refs:
        raise ValueError("VINS has no paired numeric RGBD frames")
    return refs, {
        "samples": len(refs),
        "pairing": pairing,
        "sequence_kind": "handheld_camera_observations_not_robot_actions",
    }
