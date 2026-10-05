"""GraspClutter6D 的只读 BOP 多视角接口。"""

from __future__ import annotations

import hashlib
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .models import DatasetSample, decode_image, validate_transform

_API = (
    "https://github.com/SeungBack/graspclutter6dAPI/blob/"
    "a7798be8eeee77bf6f328ddeab9f7d6c31e6c977/graspclutter6dAPI/graspclutter6d.py"
)
_BOP = "https://github.com/thodan/bop_toolkit/blob/master/docs/bop_datasets_format.md"
_CAMERAS = ("realsense-d415", "realsense-d435", "azure-kinect", "zivid")


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _path(root: Path, relative: str) -> Path:
    """索引引用始终限定在原始数据根内，包括符号链接解析后的目标。"""
    candidate = root / relative
    if Path(relative).is_absolute() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("dataset path escapes raw root")
    return candidate


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"annotation JSON must be a mapping: {path.name}")
    return value


def _scene_id(value: str | int) -> str:
    if not re.fullmatch(r"[0-9]{1,6}", str(value)):
        raise ValueError("scene identifier must be a nonnegative six-digit ID")
    return f"{int(value):06d}"


def _split_members(splits: dict[str, Any], protocol: str) -> dict[str, str]:
    value = splits.get(protocol, splits)
    if not isinstance(value, dict):
        raise ValueError("official splits must be a mapping")
    result: dict[str, str] = {}
    for name, members in value.items():
        if re.fullmatch(r"[0-9]{1,6}", str(name)) and isinstance(members, str):
            entries, split = [name], members
        elif isinstance(members, list):
            entries = members
            split = name.removeprefix(f"{protocol}_").removesuffix("_scene_ids")
        else:
            raise ValueError("official splits must map names to scene IDs or IDs to names")
        for scene in entries:
            key = _scene_id(scene)
            if key in result and result[key] != split:
                raise ValueError(f"scene {key} is in more than one official split")
            result[key] = split
    return result


def discover_grasp_samples(
    root: Path,
    source_revision: str,
    splits: dict[str, Any],
    scene_ids: list[str],
    protocol: str = "grasp",
) -> list[dict[str, Any]]:
    """按官方场景划分枚举图像，编号含相机和视角，不是执行时序。"""
    root = root.resolve()
    if not (root / "scenes").is_dir():
        raise FileNotFoundError(f"GraspClutter6D scenes are missing: {root}")
    membership = _split_members(splits, protocol)
    output: list[dict[str, Any]] = []
    for selected in scene_ids:
        scene_id = _scene_id(selected)
        scene = _path(root, f"scenes/{scene_id}")
        if not (scene / "rgb").is_dir():
            raise FileNotFoundError(f"scene RGB directory is missing: {scene_id}")
        frames = sorted((scene / "rgb").glob("*.png"))
        if not frames:
            raise FileNotFoundError(f"scene contains no RGB frames: {scene_id}")
        metadata_hashes = {
            path.relative_to(root).as_posix(): _digest(path)
            for name in ("scene_camera.json", "scene_gt.json", "scene_gt_info.json")
            if (path := _path(root, f"scenes/{scene_id}/{name}")).is_file()
        }
        for image in frames:
            if not re.fullmatch(r"[0-9]{6}", image.stem) or not 1 <= int(image.stem) <= 52:
                raise ValueError(f"unsupported official image identifier: {image.name}")
            image_id = int(image.stem)
            relative = image.relative_to(root).as_posix()
            image = _path(root, relative)
            depth_relative = f"scenes/{scene_id}/depth/{image.name}"
            depth = _path(root, depth_relative)
            if not depth.is_file():
                raise FileNotFoundError(f"RGB frame has no corresponding depth: {relative}")
            source_hashes = {
                **metadata_hashes,
                relative: _digest(image),
                depth_relative: _digest(depth),
            }
            output.append(
                {
                    "dataset_id": "graspclutter6d",
                    "source_revision": source_revision,
                    "sample_kind": "static_multiview_scene",
                    "root": str(root),
                    "scene_id": scene_id,
                    "image_id": image_id,
                    "frame_index": (image_id - 1) // 4,
                    "camera_id": _CAMERAS[(image_id - 1) % 4],
                    "official_split": membership.get(scene_id),
                    "protocol": protocol,
                    "source_file": str(image),
                    "relative_path": relative,
                    "source_sha256": source_hashes[relative],
                    "source_hashes": source_hashes,
                    "depth_relative_path": depth_relative,
                }
            )
    return output


def _transform(
    rotation: Any, translation: Any, *, from_frame: str, evidence: str
) -> dict[str, Any]:
    matrix = np.eye(4, dtype=np.float64)
    try:
        matrix[:3, :3] = np.asarray(rotation, dtype=np.float64).reshape(3, 3)
        matrix[:3, 3] = np.asarray(translation, dtype=np.float64).reshape(3) * 0.001
    except (ValueError, TypeError) as exc:
        raise ValueError("BOP transform must contain a 3x3 rotation and 3D translation") from exc
    return validate_transform(
        {
            "from_frame": from_frame,
            "to_frame": "camera",
            "translation_unit": "m",
            "matrix": matrix.tolist(),
            "evidence": evidence,
        }
    )


def _mask_reference(root: Path, candidates: list[str], shape: tuple[int, ...]) -> dict[str, Any]:
    for relative in candidates:
        path = _path(root, relative)
        if not path.is_file():
            continue
        try:
            with Image.open(path) as image:
                if image.size != (shape[1], shape[0]):
                    raise ValueError("mask dimensions differ from corresponding RGB")
                image.verify()
            return {"path": str(path), "relative_path": relative, "available": True}
        except (OSError, ValueError) as exc:
            return {"path": str(path), "available": False, "error": str(exc)}
    return {"path": str(_path(root, candidates[0])), "available": False, "error": "missing"}


def _npz_reference(root: Path, relative: str, *, kind: str) -> dict[str, Any]:
    """仅读NPY头与zip目录检查dtype/形状；不加载数十亿抓取候选。"""
    path = _path(root, relative)
    result: dict[str, Any] = {"path": str(path), "relative_path": relative, "available": False}
    if not path.is_file():
        return {**result, "error": "missing"}
    try:
        arrays: dict[str, dict[str, Any]] = {}
        # allow_pickle=False既约束未来读取，也避免采用默认的pickle选项。
        with np.load(path, allow_pickle=False) as container, zipfile.ZipFile(path) as archive:
            if len(container.files) > 10000:
                raise ValueError("too many annotation arrays")
            for key in container.files:
                entry = archive.getinfo(f"{key}.npy")
                with archive.open(entry) as stream:
                    version = np.lib.format.read_magic(stream)
                    if version == (1, 0):
                        dimensions, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        dimensions, fortran, dtype = np.lib.format.read_array_header_2_0(stream)
                    else:
                        raise ValueError("unsupported annotation NPY format")
                    if dtype.hasobject or dtype.kind not in "bifu":
                        raise ValueError("object/non-numeric annotation dtype is forbidden")
                    if entry.file_size != stream.tell() + math.prod(dimensions) * dtype.itemsize:
                        raise ValueError("annotation array payload length is inconsistent")
                    arrays[key] = {
                        "shape": list(dimensions),
                        "dtype": str(dtype),
                        "fortran_order": bool(fortran),
                    }
        if kind == "grasp":
            if set(arrays) != {"points", "offsets", "scores"}:
                raise ValueError("grasp NPZ requires points/offsets/scores")
            points = arrays["points"]["shape"]
            if (
                len(points) != 2
                or points[1] != 3
                or arrays["offsets"]["shape"] != [points[0], 300, 12, 4, 3]
                or arrays["scores"]["shape"] != [points[0], 300, 12, 4]
            ):
                raise ValueError("grasp annotation grid shape is inconsistent")
        else:
            if not arrays or any(not re.fullmatch(r"arr_[0-9]+", key) for key in arrays):
                raise ValueError("collision NPZ requires ordered arr_N instance keys")
            if any(value["dtype"] != "bool" for value in arrays.values()):
                raise ValueError("collision label arrays must be boolean")
        result.update(
            available=True, arrays=arrays, validation="NPY headers, not full grasp evaluation"
        )
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, EOFError) as exc:
        result["error"] = str(exc)
    return result


def _annotations(
    root: Path, scene_id: str, image_id: int, shape: tuple[int, ...]
) -> tuple[dict[str, Any], list[str]]:
    """GT仅进入独立oracle/evaluation通道，实例索引不以obj_id去重。"""
    base = f"scenes/{scene_id}"
    gt = _json(_path(root, f"{base}/scene_gt.json")).get(str(image_id), [])
    info = _json(_path(root, f"{base}/scene_gt_info.json")).get(str(image_id), [])
    if not isinstance(gt, list) or not isinstance(info, list):
        raise ValueError("BOP image annotations must be instance lists")
    result: dict[str, Any] = {
        "channel": "oracle/evaluation",
        "instances": [],
        "grasp_labels": {},
        "object_models": {},
    }
    issues: list[str] = []
    for instance_id, item in enumerate(gt):
        obj_id = int(item["obj_id"])
        if not 1 <= obj_id <= 200:
            raise ValueError("object ID is outside the official range 1..200")
        mask_name = f"{image_id:06d}_{instance_id:06d}.png"
        instance: dict[str, Any] = {
            "instance_id": instance_id,
            "obj_id": obj_id,
            "model_to_camera": _transform(
                item["cam_R_m2c"],
                item["cam_t_m2c"],
                from_frame=f"object_model:{obj_id}:instance:{instance_id}",
                evidence=f"scene_gt.json[{image_id}][{instance_id}]; BOP translation mm",
            ),
            "gt_info": info[instance_id] if instance_id < len(info) else None,
            "amodal_mask": _mask_reference(root, [f"{base}/mask/{mask_name}"], shape),
            "visible_mask": _mask_reference(
                root, [f"{base}/mask_visib/{mask_name}", f"{base}/visible_mask/{mask_name}"], shape
            ),
        }
        result["instances"].append(instance)
        for channel in ("amodal_mask", "visible_mask"):
            if not instance[channel]["available"]:
                issues.append(f"instance {instance_id} {channel}: {instance[channel]['error']}")
        key = str(obj_id)
        if key not in result["grasp_labels"]:
            reference = _npz_reference(
                root, f"grasp_label/obj_{obj_id:06d}_labels.npz", kind="grasp"
            )
            reference["coordinate_frame"] = f"object_model:{obj_id}"
            reference["length_unit"] = "m"
            reference["score_semantics"] = "minimum friction coefficient; not execution success"
            result["grasp_labels"][key] = reference
            model = _path(root, f"models_m/obj_{obj_id:06d}.ply")
            result["object_models"][key] = {
                "path": str(model),
                "length_unit": "m",
                "available": model.is_file(),
            }
            if not reference["available"]:
                issues.append(f"object {obj_id} grasp: {reference['error']}")
            if not model.is_file():
                issues.append(f"object {obj_id} meter model: missing")
    collision = _npz_reference(root, f"collision_label/{scene_id}.npz", kind="collision")
    result["collision_labels"] = collision
    if not collision["available"]:
        issues.append(f"collision labels: {collision['error']}")
    elif any(f"arr_{i}" not in collision["arrays"] for i in range(len(gt))):
        collision.update(available=False, error="missing collision instance index")
        issues.append("collision labels: missing collision instance index")
    else:
        for instance_id, instance in enumerate(result["instances"]):
            grasp = result["grasp_labels"][str(instance["obj_id"])]
            if (
                grasp["available"]
                and collision["arrays"][f"arr_{instance_id}"]["shape"]
                != grasp["arrays"]["scores"]["shape"]
            ):
                collision.update(available=False, error="collision and object grasp grid differ")
                issues.append(f"instance {instance_id} collision and object grasp grid differ")
    label_path = _path(root, f"{base}/label/{image_id:06d}.png")
    if label_path.is_file():
        with Image.open(label_path) as image:
            label = np.array(image)
        if label.ndim == 3 and label.shape[2] == 3:
            if not np.all(label == label[..., :1]):
                raise ValueError("semantic label PNG channels disagree")
            label = label[..., 0]
        if label.shape != shape[:2] or label.dtype.kind not in "ui":
            raise ValueError("semantic labels must be an integer map matching RGB size")
        if label.size and label.max() > 200:
            raise ValueError("semantic label contains unknown object IDs")
        result["semantic_label"] = label
        result["semantic_label_path"] = str(label_path)
    else:
        result["semantic_label"] = None
        issues.append("semantic label: missing")
    if not gt:
        issues.append("object poses: missing")
    if len(info) != len(gt):
        issues.append("gt_info instance count differs from object poses")
    return result, issues


def read_grasp_sample(ref: dict[str, Any]) -> DatasetSample:
    """惰性读取一个RGBD相机视角，能力依据来自真实元数据和官方算法。"""
    root = Path(ref["root"]).resolve()
    scene_id = _scene_id(ref["scene_id"])
    image_id = int(ref["image_id"])
    if not 1 <= image_id <= 52:
        raise ValueError("image ID is outside official camera/viewpoint numbering")
    if (
        ref["relative_path"] != f"scenes/{scene_id}/rgb/{image_id:06d}.png"
        or ref["depth_relative_path"] != f"scenes/{scene_id}/depth/{image_id:06d}.png"
    ):
        raise ValueError("image identifier and frame paths disagree")
    for relative, wanted in ref.get("source_hashes", {}).items():
        if _digest(_path(root, relative)) != wanted:
            raise ValueError(f"source digest mismatch: {relative}")
    rgb_path = _path(root, ref["relative_path"])
    if _digest(rgb_path) != ref["source_sha256"]:
        raise ValueError("source digest mismatch: RGB frame")
    depth_path = _path(root, ref["depth_relative_path"])
    rgb = decode_image(rgb_path.read_bytes(), kind="rgb")
    depth = decode_image(depth_path.read_bytes(), kind="depth")
    if depth.dtype != np.uint16:
        raise ValueError("official depth PNG must preserve uint16")
    camera = _json(_path(root, f"scenes/{scene_id}/scene_camera.json")).get(str(image_id), {})
    if not isinstance(camera, dict):
        raise ValueError("per-image camera metadata must be a mapping")
    intrinsics = None
    if "cam_K" in camera:
        intrinsics = np.asarray(camera["cam_K"], dtype=np.float64).reshape(3, 3)
    scale = float(camera["depth_scale"]) * 0.001 if "depth_scale" in camera else None
    scale_evidence = (
        f"scene_camera.json[{image_id}].depth_scale: raw*scale gives mm; mm*0.001 gives m; {_BOP}"
        if scale is not None
        else None
    )
    transforms: dict[str, dict[str, Any]] = {}
    if "cam_R_w2c" in camera or "cam_t_w2c" in camera:
        if not {"cam_R_w2c", "cam_t_w2c"} <= camera.keys():
            raise ValueError("world-to-camera transform requires both rotation and translation")
        transforms["world_to_camera"] = _transform(
            camera["cam_R_w2c"],
            camera["cam_t_w2c"],
            from_frame="dataset_world",
            evidence=f"scene_camera.json[{image_id}] cam_R_w2c/cam_t_w2c; BOP mm",
        )
    same_shape = rgb.shape[:2] == depth.shape
    aligned: bool | None = (True if same_shape else False) if intrinsics is not None else None
    # 官方API仅证明同一像素网格的深度内参；异分辨率不据此推算焦距或主点。
    depth_intrinsics = intrinsics if same_shape else None
    annotations, annotation_issues = _annotations(root, scene_id, image_id, rgb.shape)
    return DatasetSample(
        dataset_id="graspclutter6d",
        source_revision=ref["source_revision"],
        sample_kind="static_multiview_scene",
        source_file=str(rgb_path),
        relative_path=ref["relative_path"],
        source_sha256=ref["source_sha256"],
        frame_index=(image_id - 1) // 4,
        camera_id=_CAMERAS[(image_id - 1) % 4],
        official_split=ref.get("official_split"),
        scene_id=scene_id,
        protocol=ref.get("protocol", "grasp"),
        time_basis="static_multiview_index",
        rgb=rgb,
        depth_raw=depth,
        depth_scale_m=scale,
        depth_scale_evidence=scale_evidence,
        depth_semantics="optical_z",
        K_rgb=intrinsics,
        K_depth=depth_intrinsics,
        rgb_depth_aligned=aligned,
        alignment_evidence=(
            f"official loadScenePointCloud uses RGB and depth at identical pixels "
            f"with scene_camera.cam_K; matching actual dimensions; {_API}#L497-L569"
            if aligned
            else None
        ),
        transforms=transforms,
        annotations=annotations,
        metadata={
            "image_id": image_id,
            "view_index": (image_id - 1) // 4,
            "raw_depth_unit": "BOP integer units; use per-frame depth_scale",
            "depth_semantics_evidence": f"official API points_z=depths/s; {_API}#L508-L530",
            "intrinsics_evidence": (
                f"per-image scene_camera.cam_K; {_API}#L508-L528"
                if intrinsics is not None
                else None
            ),
            "depth_intrinsics_evidence": (
                f"official API cam_K on matching RGB-depth pixel grid; {_API}#L508-L530"
                if depth_intrinsics is not None
                else None
            ),
            "geometry_issues": (
                ["RGB-depth dimensions differ; no independent depth-resolution calibration"]
                if not same_shape
                else []
            ),
            "original_rgb_shape": list(rgb.shape),
            "original_depth_shape": list(depth.shape),
            "source_hashes": ref.get("source_hashes", {}),
            "annotation_issues": annotation_issues,
            "grasp_evaluation_available": False,
            "temporal_note": "image IDs identify camera/viewpoint, not robot execution time",
        },
    )
