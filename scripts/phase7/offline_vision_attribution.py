"""Compare sealed pixel results to offline simulator labels/physics in a separate pass."""

from __future__ import annotations

import argparse
import inspect
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scripts.phase7.frozen_vision import MODES, Json, _path, _sha_file, encoded, require

from cloud_edge_robot_arm.research.native_geometry_calibration import full_rigid_geometry_errors
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration


def attribute(root: Path, directory: Path) -> None:
    root = root.resolve(strict=True)
    require(not directory.resolve().is_relative_to(root), "output overlaps originals")
    source = json.loads((directory / "source.private.json").read_text())
    require(_sha_file(directory / "frames.private.jsonl") == source["details_sha256"], "pixel seal")
    manifest = json.loads(_path(root, "inventory.json").read_bytes())
    require(_sha_file(root / "inventory.json") == source["inventory_file_sha256"], "inventory seal")
    files = manifest["files"]
    for name in ("partial-originals.json", "source-binding.json"):
        require(_sha_file(_path(root, name)) == files[name]["sha256"], "physics/geometry SHA")
    raw = json.loads((root / "partial-originals.json").read_bytes())
    geometry = json.loads((root / "source-binding.json").read_bytes())["geometry"]
    states = {
        s["physics_step"]: (s["object_geom_position_m"], s["object_geom_rotation_row_major"])
        for s in [raw["reset"]["physics_state"]] + [p["post_state_payload"] for p in raw["physics"]]
    }
    algorithm_sources = {}
    for obj in (NativeGeometryRegistration, full_rigid_geometry_errors):
        actual_file = Path(inspect.getfile(obj)).resolve()
        registered_file = "src/" + obj.__module__.replace(".", "/") + ".py"
        sha = _sha_file(actual_file)
        require(sha == raw["source_hashes"][registered_file], "offline geometry algorithm SHA")
        algorithm_sources[registered_file] = sha
    del raw
    scope = NativeGeometryRegistration(geometry)
    attribute_counts: dict[str, Counter] = defaultdict(Counter)
    visibility: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    error_lists: dict[str, list[float]] = defaultdict(list)
    color_attribution: dict[str, Counter] = defaultdict(Counter)
    representatives = {4200: 7028, 6240: 11109}
    terminal = None
    with (
        (directory / "frames.private.jsonl").open() as rows,
        (directory / "offline-attribution.private.jsonl").open("x") as details,
    ):
        for line in rows:
            row = json.loads(line)
            number, step, role = row["acquisition"], row["step"], row["role"]
            name = f"frames/acquisition-{number}/source-frame.json"
            metadata_path = _path(root, name)
            require(
                _sha_file(metadata_path) == row["metadata_sha256"] == files[name]["sha256"],
                "offline metadata SHA",
            )
            metadata = json.loads(metadata_path.read_bytes())
            details_row: Json = {"acquisition": number, "step": step, "role": role}
            if metadata["instances_available"]:
                path = f"frames/acquisition-{number}/instances.i32"
                require(
                    _sha_file(_path(root, path))
                    == row["pixel_and_instance_blob_sha256"][path]
                    == files[path]["sha256"],
                    "offline instance SHA",
                )
                frame = np.fromfile(root / path, dtype="<i4").reshape(240, 320)
                labels = {int(k): v for k, v in metadata["instance_labels"].items()}
                cells = [
                    i for i, name in labels.items() if name.startswith("pose_marker_outboard_v3_r")
                ]
                require(len(cells) == 36, "registered 6x6 tag label mapping missing")
                # Local integer lookup table keeps per-pixel semantics, including background -1.
                ids = np.unique(frame)
                require(set(ids) - {-1} <= set(labels), "unknown offline instance ID")
                lookup = np.zeros(max(labels) + 2, dtype=np.uint8)
                lookup[np.asarray(cells) + 1] = 1
                ys, xs = np.nonzero(lookup[frame + 1])
                seen: Json = {
                    "tag_cells_with_labeled_pixels": len(set(ids) & set(cells)),
                    "tag_cell_pixels": int(ys.size),
                    "tag_cell_bbox_xyxy": (
                        [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
                        if ys.size
                        else None
                    ),
                }
                if "color" in row:
                    labels_by_support = []
                    for p in row["color"]["components"]:
                        values = np.concatenate(
                            [frame[y, lo : hi + 1] for y, lo, hi in p["row_runs_px"]]
                        )
                        ix, counts = np.unique(values, return_counts=True)
                        measured = {
                            labels.get(int(i), "BACKGROUND"): int(n)
                            for i, n in zip(ix, counts, strict=True)
                        }
                        labels_by_support.append(measured)
                        grouping = (
                            "ALL_OBJECT_GEOM"
                            if set(measured) == {"object_geom"}
                            else (
                                "MIXED_INCLUDING_OBJECT"
                                if "object_geom" in measured
                                else "NO_OBJECT_GEOM"
                            )
                        )
                        color_attribution["support_counts_by_label"][grouping] += 1
                        color_attribution["pixel_counts_by_label"].update(measured)
                    seen["component_instance_pixel_counts"] = labels_by_support
                    color_attribution["acquisitions"]["with_labels"] += 1
                    if step in representatives and number == representatives[step] and step == 6240:
                        terminal = labels_by_support
                details_row["offline_labels"] = seen
            else:
                require(
                    metadata["instance_count"] == 0 and metadata["instance_labels"] == {},
                    "unexpected two-pass labels",
                )
                details_row["offline_labels"] = None
                if "color" in row:
                    color_attribution["acquisitions"]["without_labels"] += 1
            for mode in MODES:
                mark = row["markers"][mode]
                key = mode + "/" + mark["reason"]
                label_map = details_row["offline_labels"]
                if label_map is None:
                    attribute_counts[key]["two_pass_labels_unavailable"] += 1
                else:
                    cells_seen = label_map["tag_cells_with_labeled_pixels"]
                    category = (
                        "all_36_cells_sampled"
                        if cells_seen == 36
                        else ("partial_cells_sampled" if cells_seen else "no_cells_sampled")
                    )
                    attribute_counts[key][category] += 1
                    visibility[key]["cell_counts"].append(cells_seen)
                    visibility[key]["tag_cell_pixels"].append(label_map["tag_cell_pixels"])
                estimate = mark["registered_sample_object_pose"]
                if estimate is None:
                    details_row[mode] = None
                    continue
                error = full_rigid_geometry_errors(
                    scope, estimate["center_world_m"], estimate["rotation_to_world"], *states[step]
                )
                details_row[mode] = asdict(error)
                error_lists[mode].append(error.joint_geometry_error_m)
            details.write(encoded(details_row) + "\n")
    result = {
        "scope": "SIMULATOR_TRUTH_AFTER_SEALED_PIXEL_DECISIONS",
        "actual_geometry_code_sha256": algorithm_sources,
        "sealed_pixel_records_sha256": source["details_sha256"],
        "detail_sha256": _sha_file(directory / "offline-attribution.private.jsonl"),
        "terminal_component_instance_pixel_counts": terminal,
        "lift_color_components": color_attribution,
        "marker_visibility_by_mode_and_original_reason": {
            key: {
                "counts": counts,
                "per_labeled_acquisition": {
                    name: {
                        "min": min(values),
                        "median": float(np.median(values)),
                        "max": max(values),
                    }
                    for name, values in visibility[key].items()
                },
            }
            for key, counts in attribute_counts.items()
        },
        "registered_rigid_error_on_observed_samples_only": {
            m: {"acquisitions": len(v), "median_m": float(np.median(v)), "maximum_m": max(v)}
            for m, v in error_lists.items()
        },
        "metric": "Maximum point distance over eight vertices, three contacts and registered TCP.",
        "label_semantics": (
            "A labeled cell contributes at least one sampled pixel. A missing ID may reflect "
            "occlusion or rasterization. Two-pass acquisitions have no instance image."
        ),
        "inference": (
            "Neither offline labels nor physics residuals enter a detector or tracker verdict."
        ),
    }
    (directory / "offline-attribution.private.json").write_text(encoded(result) + "\n")


def failure_regions(root: Path, directory: Path) -> None:
    """Locate failed/recovered samples using sealed instance labels only after pixel decisions."""
    source = json.loads((directory / "source.private.json").read_text())
    attribution = json.loads((directory / "offline-attribution.private.json").read_text())
    require(
        _sha_file(directory / "frames.private.jsonl") == source["details_sha256"]
        and _sha_file(directory / "offline-attribution.private.jsonl")
        == attribution["detail_sha256"],
        "both offline stage inputs must be sealed",
    )
    groups: dict[str, list[Json]] = defaultdict(list)
    geometry = source["registration"]
    require(geometry["marker_id"] == 7 and geometry["marker_size_m"] == 0.075, "registered tag")
    with (
        (directory / "frames.private.jsonl").open() as rows,
        (directory / "offline-attribution.private.jsonl").open() as truth,
        (directory / "offline-regions.private.jsonl").open("x") as detail,
    ):
        for line, label_line in zip(rows, truth, strict=True):
            row, label_row = json.loads(line), json.loads(label_line)
            require(row["acquisition"] == label_row["acquisition"], "offline join")
            unknown = [m for m in MODES if row["markers"][m]["status"] == "UNKNOWN"]
            if not unknown:
                continue
            number = row["acquisition"]
            labels = label_row["offline_labels"]
            measured: Json = {"acquisition": number, "step": row["step"], "tag_pixels": None}
            if labels and labels["tag_cell_bbox_xyxy"] is not None:
                x0, y0, x1, y1 = labels["tag_cell_bbox_xyxy"]
                name = f"frames/acquisition-{number}/rgb.png"
                path = _path(root, name)
                require(_sha_file(path) == row["pixel_and_instance_blob_sha256"][name], "RGB SHA")
                with Image.open(path) as image:
                    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
                crop = gray[y0 : y1 + 1, x0 : x1 + 1]
                measured["tag_pixels"] = {
                    "bbox_xyxy": [x0, y0, x1, y1],
                    "gray_range": [int(crop.min()), int(crop.max())],
                    "all_36_cells_labeled": labels["tag_cells_with_labeled_pixels"] == 36,
                }
            for mode in unknown + (["SUBPIX_RECOVERED"] if unknown == ["NONE"] else []):
                selected = "SUBPIX" if mode == "SUBPIX_RECOVERED" else mode
                mark = row["markers"][selected]
                key = mode + "/" + mark["reason"]
                entry = dict(measured)
                tag = measured["tag_pixels"]
                trace = mark["trace"]
                quads = trace["decoded_corners_px"] + trace["rejected_quads_px"]
                if tag and quads:
                    x0, y0, x1, y1 = tag["bbox_xyxy"]
                    box = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
                    entry["nearest_quad_to_axis_aligned_tag_bbox_max_corner_distance_px"] = min(
                        float(np.linalg.norm(np.asarray(q) - np.roll(b, i, axis=0), axis=1).max())
                        for q in quads
                        for b in (box, box[::-1])
                        for i in range(4)
                    )
                groups[key].append(entry)
                detail.write(encoded(dict(mode_reason=key, **entry)) + "\n")
    aggregates: Json = {}
    for key, entries in groups.items():
        labeled = [v for v in entries if v["tag_pixels"] is not None]
        boxes = np.asarray([v["tag_pixels"]["bbox_xyxy"] for v in labeled])
        if not labeled:
            aggregates[key] = {"acquisitions": len(entries), "with_labels": 0}
            continue
        d = [
            v["nearest_quad_to_axis_aligned_tag_bbox_max_corner_distance_px"]
            for v in labeled
            if "nearest_quad_to_axis_aligned_tag_bbox_max_corner_distance_px" in v
        ]
        contrasts = [np.diff(v["tag_pixels"]["gray_range"])[0] for v in labeled]
        aggregates[key] = {
            "acquisitions": len(entries),
            "with_labels": len(labeled),
            "actual_cell_bbox_union_xyxy": [
                int(boxes[:, 0].min()),
                int(boxes[:, 1].min()),
                int(boxes[:, 2].max()),
                int(boxes[:, 3].max()),
            ],
            "raw_grayscale_max_minus_min_in_labeled_tag_bbox": [
                int(min(contrasts)),
                int(max(contrasts)),
            ],
            "nearest_detector_quad_to_tag_bbox_max_corner_distance_px": (
                {"min": min(d), "median": float(np.median(d)), "max": max(d)} if d else None
            ),
            "with_any_detector_quad": len(d),
            "first_labeled": labeled[0],
            "last_labeled": labeled[-1],
        }
    summary = {
        "pixel_sha256": source["details_sha256"],
        "detail_sha256": _sha_file(directory / "offline-regions.private.jsonl"),
        "mode_reason": aggregates,
        "scope": (
            "External instance-cell bounds locate the tag in original RGB "
            "for attribution only. Corner distances are descriptive and never "
            "alter detector gates."
        ),
    }
    (directory / "offline-regions.private.json").write_text(encoded(summary) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--private", type=Path, required=True)
    args = parser.parse_args()
    attribute(args.originals, args.private)
    failure_regions(args.originals, args.private)
