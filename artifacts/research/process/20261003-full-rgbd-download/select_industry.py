"""离线筛选/验证 IndustryShapes 实拍 classic test；不联网或修改下载账本。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from cloud_edge_robot_arm.datasets.external.fiftyone_curated import _visible_mask

REVISION = "560b0dd042bc34945de6798d67d3cb2da7e9de28"
INDEX_BYTES = 137313312
INDEX_SHA256 = "ad25ad006b06df6fed56eced0f2aff9bca51c3276a7134b509b6c4831fb3f070"
SOURCE_ID = "Voxel51/IndustryShapes"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("source path must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError("source path is not canonical or escapes the raw root")
    return value


def under(root: Path, relative: str) -> Path:
    target = root / relative_path(relative)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("local file escapes the raw root")
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("local source file contains a symlink")
    return target


def fields(record: dict[str, Any]) -> dict[str, Any]:
    scene, frame = record.get("scene_id"), record.get("image_id")
    if not all(isinstance(x, str) and re.fullmatch(r"\d{1,8}", x) for x in (scene, frame)):
        raise ValueError("missing explicit numeric scene/image identifiers")
    k = np.asarray(record.get("camera_intrinsics"), dtype=float)
    if (
        k.shape != (3, 3)
        or not np.isfinite(k).all()
        or k[0, 0] <= 0
        or k[1, 1] <= 0
        or not np.allclose(k[2], [0, 0, 1], atol=1e-8)
    ):
        raise ValueError("camera_intrinsics is not a valid source matrix")
    scale = record.get("depth_scale")
    if isinstance(scale, bool) or scale != 1.0:
        raise ValueError("classic test scale must be 1.0; other units require source review")
    detections = record.get("ground_truth", {}).get("detections")
    if not isinstance(detections, list) or not detections:
        raise ValueError("missing ground_truth detections")
    for item in detections:
        rotation = np.asarray(item.get("rotation_matrix"), dtype=float)
        translation = np.asarray(item.get("translation_mm"), dtype=float)
        if (
            rotation.shape != (3, 3)
            or translation.shape != (3,)
            or not np.isfinite(rotation).all()
            or not np.isfinite(translation).all()
            or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-3)
            or not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-3)
        ):
            raise ValueError("invalid object-to-camera R/translation_mm")
        if isinstance(item.get("obj_id"), bool) or item.get("obj_id") not in range(1, 6):
            raise ValueError("unexpected object identifier")
    return {
        "scene_id": scene,
        "image_id": frame,
        "rgb": relative_path(record.get("filepath")),
        "depth": relative_path(record.get("depth", {}).get("map_path")),
        "instance_count": len(detections),
    }


def inventory_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and "files" in value:
        entries = value["files"]
    elif isinstance(value, dict) and "Files" in value:
        entries = value["Files"]
    elif isinstance(value, dict) and isinstance(value.get("Data"), dict):
        entries = value["Data"].get("Files")
    elif isinstance(value, list):
        entries = value
    else:
        raise ValueError("inventory must contain files/Files entries")
    if not isinstance(entries, list):
        raise ValueError("inventory files must be a list")
    return entries


def select(args: argparse.Namespace) -> None:
    if args.samples.stat().st_size != INDEX_BYTES or digest(args.samples) != INDEX_SHA256:
        raise ValueError("samples.json does not match the complete pinned source index")
    inventory = read_json(args.inventory)
    if not isinstance(inventory, dict) or not inventory.get("complete", False):
        raise ValueError(
            "inventory must attest complete=true for relevant pinned parent directories"
        )
    if inventory.get("revision") != REVISION:
        raise ValueError("inventory revision does not match the pinned source index")
    files = {}
    for item in inventory_entries(inventory):
        if item.get("Type", item.get("type", "blob")) != "blob":
            continue
        name = relative_path(item.get("Path", item.get("path")))
        if name in files and files[name] != item:
            raise ValueError(f"conflicting inventory records for {name}")
        files[name] = item
    source = read_json(args.samples)
    records = source["samples"]
    selected, rejected, downloads, identities = [], [], {}, set()
    classic_test = [
        item
        for item in records
        if item.get("dataset_subset") == "classic" and item.get("split") == "test"
    ]
    for record in classic_test:
        identity = {
            "scene_id": record.get("scene_id"),
            "image_id": record.get("image_id"),
            "rgb": record.get("filepath"),
            "depth": record.get("depth", {}).get("map_path"),
        }
        reasons = []
        try:
            identity.update(fields(record))
            key = (identity["scene_id"], identity["image_id"])
            if key in identities:
                raise ValueError("duplicate scene/image identity")
            identities.add(key)
            for field in ("rgb", "depth"):
                path = identity[field]
                item = files.get(path)
                if item is None:
                    reasons.append(f"missing_{field}_in_pinned_mirror")
                    continue
                size, sha = (
                    item.get("Size", item.get("size")),
                    item.get("Sha256", item.get("sha256")),
                )
                if item.get("InCheck", item.get("in_check", False)):
                    reasons.append(f"{field}_under_source_review")
                elif (
                    isinstance(size, bool)
                    or not isinstance(size, int)
                    or size <= 0
                    or not isinstance(sha, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", sha)
                ):
                    reasons.append(f"{field}_missing_size_or_source_sha256")
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            reasons.append(str(exc))
        if reasons:
            rejected.append({**identity, "reasons": reasons})
            continue
        selected.append(record)
        for field in ("rgb", "depth"):
            item = files[identity[field]]
            downloads[identity[field]] = {
                "path": identity[field],
                "size": item.get("Size", item.get("size")),
                "sha256": item.get("Sha256", item.get("sha256")),
            }
    selected.sort(key=lambda item: (int(item["scene_id"]), int(item["image_id"])))
    common = {"dataset_id": SOURCE_ID, "revision": REVISION}
    summary = {
        **common,
        "scope": "all_available_real_classic_test_pairs_in_pinned_mirror",
        "status": "SOURCE_INCOMPLETE_PAIRS_SELECTED" if rejected else "FULL_CLASSIC_TEST_SELECTED",
        "source_index": {"size": INDEX_BYTES, "sha256": INDEX_SHA256},
        "inventory_sha256": digest(args.inventory),
        "source_records": len(records),
        "classic_test_records": len(classic_test),
        "selected_records": len(selected),
        "quarantined_records": len(rejected),
        "selected_scenes": dict(Counter(item["scene_id"] for item in selected)),
        "source_scenes": dict(Counter(item["scene_id"] for item in classic_test)),
        "quarantine_reasons": dict(
            Counter(reason for item in rejected for reason in item["reasons"])
        ),
        "download_file_count": len(downloads),
        "download_media_bytes": sum(item["size"] for item in downloads.values()),
        "depth_units": "classic depth_scale=1.0; source PNG numeric values in mm",
        "depth_65535_policy": "record saturation/extreme counts; physical validity unresolved",
        "official_test_split_preserved": True,
        "geometry_and_grasp_claims": (
            "K/object pose present; no native grasp or robot action labels"
        ),
    }
    write_json(args.output_dir / "selection-summary.json", summary)
    write_json(
        args.output_dir / "download-manifest.json", {**common, "files": list(downloads.values())}
    )
    write_json(args.output_dir / "selected-samples.json", {**common, "samples": selected})
    write_json(args.output_dir / "quarantine.json", {**common, "records": rejected})
    print(json.dumps(summary, ensure_ascii=False))


def validate(args: argparse.Namespace) -> None:
    manifest = read_json(args.selection_dir / "download-manifest.json")
    selection = read_json(args.selection_dir / "selected-samples.json")
    if any(
        item.get("dataset_id") != SOURCE_ID or item.get("revision") != REVISION
        for item in (manifest, selection)
    ):
        raise ValueError("selection files must retain source repository/revision identity")
    selected = selection["samples"]
    if not selected or not manifest["files"]:
        raise ValueError("empty selected data cannot pass RGBD acceptance")
    failures, hashes = [], {}
    for item in manifest["files"]:
        path = under(args.raw_root, item["path"])
        try:
            if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                raise ValueError("size/source SHA256 mismatch")
            hashes[item["path"]] = True
        except (OSError, ValueError) as exc:
            failures.append({"path": item["path"], "reason": str(exc)})
    checked, preview_scenes = [], set()
    for record in selected:
        identity = fields(record)
        if not all(hashes.get(identity[field]) for field in ("rgb", "depth")):
            continue
        try:
            with Image.open(under(args.raw_root, identity["rgb"])) as image:
                rgb = np.asarray(image)
            with Image.open(under(args.raw_root, identity["depth"])) as image:
                depth = np.asarray(image)
            metadata = record["metadata"]
            expected = (metadata["height"], metadata["width"])
            if rgb.dtype != np.uint8 or rgb.shape != (*expected, 3):
                raise ValueError("RGB dtype/shape differs from source metadata")
            if depth.dtype != np.uint16 or depth.shape != expected:
                raise ValueError("depth must be a matching-size uint16 numeric PNG")
            overlay = rgb.copy()
            for detection in record["ground_truth"]["detections"]:
                mask = _visible_mask(detection, expected) > 0
                overlay[mask] = ((rgb[mask].astype(float) + [255, 90, 30]) / 2).astype(np.uint8)
            below_max = (depth > 0) & (depth < 65535)
            checked.append(
                {
                    **identity,
                    "rgb_shape": list(rgb.shape),
                    "depth_shape": list(depth.shape),
                    "depth_dtype": str(depth.dtype),
                    "zero_count": int((depth == 0).sum()),
                    "uint16_max_count": int((depth == 65535).sum()),
                    "positive_below_uint16_max_ratio": float(below_max.mean()),
                    "raw_depth_min": int(depth.min()),
                    "raw_depth_max": int(depth.max()),
                }
            )
            if (
                identity["scene_id"] not in preview_scenes
                and len(preview_scenes) < args.preview_count
            ):
                preview_scenes.add(identity["scene_id"])
                gray = np.zeros(depth.shape, dtype=np.uint8)
                if below_max.any():
                    low, high = np.percentile(depth[below_max], [2, 98])
                    if high > low:
                        gray[below_max] = (
                            np.clip((depth[below_max] - low) / (high - low), 0, 1) * 255
                        ).astype(np.uint8)
                canvas = Image.new("RGB", (rgb.shape[1] * 3, rgb.shape[0] + 30), "white")
                canvas.paste(Image.fromarray(rgb), (0, 30))
                canvas.paste(Image.fromarray(gray).convert("RGB"), (rgb.shape[1], 30))
                canvas.paste(Image.fromarray(overlay), (rgb.shape[1] * 2, 30))
                ImageDraw.Draw(canvas).text(
                    (8, 8),
                    f"classic test scene {identity['scene_id']} frame {identity['image_id']}"
                    " | RGB / depth display / instance masks",
                    fill="black",
                )
                args.output_dir.mkdir(parents=True, exist_ok=True)
                canvas.save(
                    args.output_dir
                    / f"scene-{identity['scene_id']}-frame-{identity['image_id']}.png"
                )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            failures.append({**identity, "reason": str(exc)})
    result = {
        "dataset_id": SOURCE_ID,
        "revision": REVISION,
        "status": "VERIFIED_SELECTED_RGBD_PAIRS"
        if not failures and len(checked) == len(selected)
        else "VALIDATION_FAILED",
        "selected_frame_count": len(selected),
        "validated_frame_count": len(checked),
        "validated_file_count": len(hashes),
        "preview_count": len(preview_scenes),
        "depth_policy": (
            "65535 is reported separately and omitted from display only; "
            "no metric validity or point-cloud claim"
        ),
        "split_preserved": "test",
        "frames": checked,
        "failures": failures,
    }
    write_json(args.output_dir / "validation.json", result)
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in {"frames", "failures"}},
            ensure_ascii=False,
        )
    )
    if failures or len(checked) != len(selected):
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    selection = commands.add_parser("select")
    selection.add_argument("--samples", type=Path, required=True)
    selection.add_argument("--inventory", type=Path, required=True)
    selection.add_argument("--output-dir", type=Path, required=True)
    validation = commands.add_parser("validate")
    validation.add_argument("--selection-dir", type=Path, required=True)
    validation.add_argument("--raw-root", type=Path, required=True)
    validation.add_argument("--output-dir", type=Path, required=True)
    validation.add_argument("--preview-count", type=int, default=5)
    args = parser.parse_args()
    if args.command == "select":
        select(args)
    else:
        validate(args)


if __name__ == "__main__":
    main()
