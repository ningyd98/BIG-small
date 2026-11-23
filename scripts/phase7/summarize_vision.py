"""Summarize per-acquisition frozen visual evidence without pooling same-step captures."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

import numpy as np
from scripts.phase7.frozen_vision import (
    MODES,
    PER_STEP,
    Json,
    _sha_file,
    encoded,
    require,
)


def ranges(steps: Iterable[int]) -> list[list[int]]:
    result: list[list[int]] = []
    for step in sorted(set(steps)):
        if result and result[-1][1] + 1 == step:
            result[-1][1] = step
        else:
            result.append([step, step])
    return result


def step_coverage(steps: list[int], start: int, end: int) -> dict:
    selected = [n for n in steps if start <= n <= end]
    seen = set(selected)
    return {
        "expected_unique_steps": end - start + 1,
        "observed_unique_steps": len(seen),
        "acquisitions": len(selected),
        "same_step_extra_acquisitions": len(selected) - len(seen),
        "missing_step_ranges": ranges(set(range(start, end + 1)) - seen),
        "both_endpoints_present": start in seen and end in seen,
    }


def failure_runs(records: Iterable[tuple[int, int, bool]]) -> list[dict]:
    result: list[dict] = []
    active = None
    for acquisition, step, observed in records:
        if observed:
            active = None
        elif active is None:
            active = {
                "first_acquisition": acquisition,
                "last_acquisition": acquisition,
                "first_step": step,
                "last_step": step,
                "acquisitions": 1,
            }
            result.append(active)
        else:
            active.update(
                last_acquisition=acquisition,
                last_step=step,
                acquisitions=active["acquisitions"] + 1,
            )
    return result


def same_pixel_links(
    previous_step: int,
    previous: list[Json],
    step: int,
    current: list[Json],
) -> list[Json]:
    """Report exact overlap of measured supports, never propagate a physical identity."""
    if step != previous_step + 1:
        return []

    def pixels(component: Json) -> set[tuple[int, int]]:
        return {(x, y) for y, a, b in component["row_runs_px"] for x in range(a, b + 1)}

    latter = [pixels(c) for c in current]
    result = []
    for i, component in enumerate(previous):
        earlier = pixels(component)
        for j, region in enumerate(latter):
            overlap = len(earlier & region)
            if overlap:
                result.append({"previous_index": i, "current_index": j, "common_pixels": overlap})
    return result


def pair(row: Json) -> str:
    a, b = (row["markers"][mode]["status"] == "OBSERVED" for mode in MODES)
    return (
        "both_observed"
        if a and b
        else "none_only"
        if a
        else "subpix_only"
        if b
        else "neither_observed"
    )


def compact_marker(marker: Json) -> Json:
    return {
        k: marker[k]
        for k in (
            "status",
            "reason",
            "registered_sample_object_pose",
            "yaw_world_rad",
            "measured_min_side_px",
        )
    }


def compact_part(p: Json) -> Json:
    return {
        k: p[k]
        for k in (
            "bbox_xywh",
            "area_px",
            "centroid_px",
            "valid_depth_pixels",
            "range_optical_z_m",
            "median_optical_z_m",
            "mean_visible_world_xyz_m",
            "visible_world_aabb_m",
        )
    }


def offsets(parts: list[Json], marker: Json) -> list[list[float] | None] | None:
    pose = marker["registered_sample_object_pose"]
    if pose is None:
        return None
    center = np.asarray(pose["center_world_m"])
    rotation = np.asarray(pose["rotation_to_world"]).reshape(3, 3)
    return [
        ((np.asarray(p["mean_visible_world_xyz_m"]) - center) @ rotation).tolist()
        if p["mean_visible_world_xyz_m"] is not None
        else None
        for p in parts
    ]


def stats(values: list[float]) -> Json | None:
    if not values:
        return None
    return {"min": min(values), "median": float(np.median(values)), "max": max(values)}


def marker_stats(rows: list[Json]) -> Json:
    return {
        "acquisitions": len(rows),
        "same_acquisition_2x2": {
            k: sum(r["pair"] == k for r in rows)
            for k in ("both_observed", "none_only", "subpix_only", "neither_observed")
        },
        "reasons": {m: Counter(r["markers"][m]["reason"] for r in rows) for m in MODES},
    }


def segment(row: Json, horizons: list[Json]) -> str:
    if row["step"] <= horizons[0]["dispatch_step"]:
        return "SETUP"
    for h in horizons:
        if row["step"] <= h["terminal_step"]:
            return str(h["skill"])
    raise ValueError("capture outside horizons")


def aligned_quad_distance(query: np.ndarray, reference: np.ndarray) -> float:
    return min(
        float(np.linalg.norm(query - np.roll(q, k, axis=0), axis=1).max())
        for q in (reference, reference[::-1])
        for k in range(4)
    )


def roi_diagnostics(markers: Json) -> Json:
    recovered = markers["SUBPIX"]["trace"]
    candidates = [
        np.asarray(c)
        for c in markers["NONE"]["trace"]["decoded_corners_px"]
        + markers["NONE"]["trace"]["rejected_quads_px"]
    ]
    corners = np.asarray(recovered["decoded_corners_px"][0])
    return {
        "subpix_stage": "NATIVE_UNIQUE_ID7"
        if recovered["native_ids"] == [7]
        else "ZERO_BIT_FALLBACK",
        "none_native_ids": markers["NONE"]["trace"]["native_ids"],
        "none_candidate_quads": len(candidates),
        "nearest_none_quad_max_corner_distance_px": (
            min(aligned_quad_distance(corners, c) for c in candidates) if candidates else None
        ),
        "subpix_min_edge_px": markers["SUBPIX"]["measured_min_side_px"],
        "registered_measured_edges_m": markers["SUBPIX"]["measured_edge_lengths_m"],
        "subpix_plane": markers["SUBPIX"]["diagnostics"]["plane"],
    }


def measured_window(rows: list[Json], start: int, end: int) -> Json:
    selected = [r for r in rows if start <= r["step"] <= end]
    report = {
        "coverage": step_coverage([r["step"] for r in selected], start, end),
        "color_multiplicity": Counter(str(len(r["components"])) for r in selected),
        "color_geometry_gate": Counter(r["color_reason"] or "OBSERVED" for r in selected),
        "full_extent_samples": sum(r["extent"] for r in selected),
        "capture_utc_span_s": (
            datetime.fromisoformat(selected[-1]["captured_at"])
            - datetime.fromisoformat(selected[0]["captured_at"])
        ).total_seconds(),
        "sim_time_span_s": selected[-1]["sim_time_s"] - selected[0]["sim_time_s"],
        "marker": marker_stats(selected),
        "sample_pose_diagnostics": {},
    }
    for mode in MODES:
        marked = [r for r in selected if r["markers"][mode]["status"] == "OBSERVED"]
        zs = [
            r["markers"][mode]["registered_sample_object_pose"]["center_world_m"][2] for r in marked
        ]
        linear_rates, angular_rates = [], []
        for left, right in zip(marked, marked[1:], strict=False):
            if right["step"] - left["step"] != 1:
                continue
            p = left["markers"][mode]["registered_sample_object_pose"]
            q = right["markers"][mode]["registered_sample_object_pose"]
            elapsed = right["sim_time_s"] - left["sim_time_s"]
            linear_rates.append(
                float(np.linalg.norm(np.subtract(q["center_world_m"], p["center_world_m"])))
                / elapsed
            )
            rotation = np.asarray(p["rotation_to_world"]).reshape(3, 3).T @ np.asarray(
                q["rotation_to_world"]
            ).reshape(3, 3)
            radians = math.acos(float(np.clip((np.trace(rotation) - 1.0) / 2, -1, 1)))
            angular_rates.append(radians / elapsed)
        report["sample_pose_diagnostics"][mode] = {
            "observed_object_center_z_m": stats(zs),
            "consecutive_observed_pairs": len(linear_rates),
            "missing_marker_step_ranges": ranges(
                r["step"] for r in selected if r["markers"][mode]["status"] != "OBSERVED"
            ),
            "max_adjacent_estimate_displacement_over_sim_dt_m_s": max(linear_rates, default=None),
            "max_adjacent_estimate_rotation_over_sim_dt_rad_s": max(angular_rates, default=None),
            "continuous_physical_linear_speed_upper_bound_m_s": None,
            "continuous_physical_angular_speed_upper_bound_rad_s": None,
        }
    return report


def lift_public(
    all_rows: list[Json],
    chosen: list[Json],
    source: Json,
    private: Path,
) -> Json:
    lift_rows = [r for r in all_rows if r["step"] >= 4200]
    anchors = {
        n: [r["acquisition"] for r in lift_rows if r["step"] == n]
        for n in (4200, 5035, 5155, 6120, 6240)
    }
    keys = [4200, 5155, 6240]
    by_step = {r["step"]: r for r in chosen}
    showcases = {}
    for n in keys:
        r = by_step[n]
        showcases[str(n)] = {
            "acquisition": r["acquisition"],
            "role": r["role"],
            "components": [compact_part(p) for p in r["components"]],
            "registered_color_gate": r["color_reason"],
            "marker_pose_at_sample": {
                m: {
                    "status": r["markers"][m]["status"],
                    "object_center_world_m": (
                        r["markers"][m]["registered_sample_object_pose"] or {}
                    ).get("center_world_m"),
                    "color_centroids_in_nominal_object_coords_m": offsets(
                        r["components"], r["markers"][m]
                    ),
                }
                for m in MODES
            },
        }
    linked: Counter[str] = Counter()
    prev: Json | None = None
    with (private / "lift-steps.private.jsonl").open("x") as steps:
        for row in chosen:
            links = (
                []
                if prev is None
                else same_pixel_links(
                    prev["step"], prev["components"], row["step"], row["components"]
                )
            )
            if prev is not None:
                earlier, later = len(prev["components"]), len(row["components"])
                bijective = (
                    len(links) == earlier == later > 0
                    and len({v["current_index"] for v in links}) == later
                    and len({v["previous_index"] for v in links}) == earlier
                )
                key = f"{earlier}_to_{later}/" + (
                    "one_to_one_overlap" if bijective else "other_overlap"
                )
                linked[key] += 1
            steps.write(
                encoded(
                    {
                        "step": row["step"],
                        "acquisition": row["acquisition"],
                        "role": row["role"],
                        "sim_time_s": row["sim_time_s"],
                        "captured_at": row["captured_at"],
                        "pair": row["pair"],
                        "components": [compact_part(p) for p in row["components"]],
                        "registered_geometry_reason": row["color_reason"],
                        "nominal_color_centroids_m": {
                            m: offsets(row["components"], row["markers"][m]) for m in MODES
                        },
                        "consecutive_observed_pixel_overlaps": links,
                    }
                )
                + "\n"
            )
            prev = row
    require(len(chosen) == len(by_step) == 2041, "representative step denominator")
    chosen_ids = {r["acquisition"] for r in chosen}
    missing_boundaries = sorted(set(range(4200, 6241)) - set(by_step))
    contexts = {r["acquisition"]: r for r in lift_rows}
    return {
        "step_interval_including_all_same_step_acquisitions": {
            **step_coverage([r["step"] for r in lift_rows], 4200, 6240),
            "by_role": Counter(r["role"] for r in lift_rows),
            "color_multiplicity": Counter(str(len(r["components"])) for r in lift_rows),
            "color_geometry_gate": Counter(r["color_reason"] or "OBSERVED" for r in lift_rows),
            "full_extent_samples": sum(r["extent"] for r in lift_rows),
            "clock_progress_compared_to_preceding_allocated_acquisition": Counter(
                r["time_progress"] for r in lift_rows
            ),
        },
        "acquisition_interval_from_actual_lift_pre_through_post": {
            "first_acquisition": int(source["lift_dispatch_id"].split("-")[-1]),
            "last_acquisition": int(source["terminal_id"].split("-")[-1]),
            "acquisitions": sum(
                r["acquisition"] >= int(source["lift_dispatch_id"].split("-")[-1])
                for r in lift_rows
            ),
            "earlier_at_same_dispatch_step": [n for n in anchors[4200] if n not in chosen_ids],
        },
        "step_selection": (
            "Use the original PRE/POST boundary acquisitions at 4200/6240 and the independently "
            "registered per-physics-step acquisition at each intermediate step."
        ),
        "missing_step_positions": missing_boundaries,
        "anchor_acquisitions_by_step": {
            str(n): [{"acquisition": i, "role": contexts[i]["role"]} for i in aids]
            for n, aids in anchors.items()
        },
        "original_lift_admission_captures": [
            {"step": row["step"], "acquisition": row["acquisition"], **c}
            for row in lift_rows
            for c in row["clocks"]
            if c["step_id"] == "step-4" and c["purpose"].startswith("ADMISSION_")
        ],
        "color_multiplicity_step_ranges": {
            str(count): ranges(r["step"] for r in chosen if len(r["components"]) == count)
            for count in sorted({len(r["components"]) for r in chosen})
        },
        "consecutive_spatial_support_links": dict(linked),
        "link_rule": (
            "Compare supports at adjacent physical steps using at least one identical image "
            "pixel. Multiple connected spatial traces remain unlabeled; overlap is descriptive."
        ),
        "anchors": showcases,
        "windows": {
            k: measured_window(chosen, a, b)
            for k, a, b in (
                ("dispatch_to_terminal", 4200, 6240),
                ("controller_contact_hold", 5035, 5155),
                ("terminal_half_second", 6120, 6240),
            )
        },
        "nominal_endpoint_center_height_change_m": {
            m: (
                showcases["6240"]["marker_pose_at_sample"][m]["object_center_world_m"][2]
                - showcases["4200"]["marker_pose_at_sample"][m]["object_center_world_m"][2]
            )
            if (
                showcases["6240"]["marker_pose_at_sample"][m]["object_center_world_m"] is not None
                and showcases["4200"]["marker_pose_at_sample"][m]["object_center_world_m"]
                is not None
            )
            else None
            for m in MODES
        },
        "physical_facts": {
            "terminal_color_target_identity": "UNKNOWN",
            "registered_marker_identity_at_terminal": {
                m: showcases["6240"]["marker_pose_at_sample"][m]["status"] for m in MODES
            },
            "color_full_object_extent": "UNKNOWN",
            "certified_lift_lower_bound_m": None,
            "object_lifted": "UNKNOWN",
            "object_stable": "UNKNOWN",
            "depth_error_bound_m": source["calibration_error_bound_m"],
            "continuous_motion_evidence": "UNKNOWN",
            "limitations": [
                "Color-matched fragments have no unique target association or complete silhouette.",
                "A successfully decoded unique mounted marker gives an ordered sample pose. "
                "Neither registration nor the sensor supplies a calibrated metric error envelope.",
                "A square colored fragment has quarter-turn ambiguity. Ordered tag corners "
                "can distinguish orientation at a decoded sample only. Consecutive samples "
                "cannot exclude intervening translation, oscillation or complete turns.",
            ],
        },
        "unchanged_original_lift_post": source["lift_online"],
        "step_detail_sha256": _sha_file(private / "lift-steps.private.jsonl"),
    }


def summarize(private: Path, public: Path) -> None:
    source = json.loads((private / "source.private.json").read_text())
    require(_sha_file(private / "frames.private.jsonl") == source["details_sha256"], "pixel seal")
    offline = json.loads((private / "offline-attribution.private.json").read_text())
    offline_regions = json.loads((private / "offline-regions.private.json").read_text())
    require(offline_regions["pixel_sha256"] == source["details_sha256"], "region pixels seal")
    offline["localization_on_failed_or_recovered_acquisitions"] = offline_regions
    require(offline["sealed_pixel_records_sha256"] == source["details_sha256"], "attribution seal")
    groups: dict[str, list[Json]] = defaultdict(list)
    clocks: list[Json] = []
    recoveries: list[Json] = []
    time_progress: Counter[str] = Counter()
    region: dict[str, list[Json]] = defaultdict(list)
    selected: list[Json] = []
    ages: list[float] = []
    prev: Json | None = None
    with (private / "frames.private.jsonl").open() as frames:
        for line in frames:
            row = json.loads(line)
            aid, n, markers = row["acquisition"], row["step"], row["markers"]
            lo, hi = map(datetime.fromisoformat, row["utc_capture_interval"])
            stamp = datetime.fromisoformat(row["captured_at"])
            require(lo <= stamp <= hi, "sensor timestamp outside original capture")
            if prev is not None:
                require(row["operation_ns"][0] >= prev["operation_ns"][1], "operational time order")
            prev = {"operation_ns": row["operation_ns"]}
            stage = segment(row, source["horizons"])
            match = pair(row)
            record = {
                k: row[k]
                for k in (
                    "step",
                    "acquisition",
                    "role",
                    "captured_at",
                    "sim_time_s",
                    "time_progress",
                    "mask_valid_px",
                )
            }
            record |= {
                "pair": match,
                "stage": stage,
                "clocks": [
                    {k: c[k] for k in ("purpose", "step_id", "index", "age_at_evaluation_s")}
                    for c in row["tracker_evaluations"]
                ],
                "markers": {m: compact_marker(markers[m]) for m in MODES},
            }
            time_progress[row["time_progress"]] += 1
            for clock in record["clocks"]:
                ages.append(clock["age_at_evaluation_s"])
                clocks.append({"acquisition": aid, "step": n, **clock})
            if match == "subpix_only":
                recoveries.append({"acquisition": aid, "step": n, **roi_diagnostics(markers)})
            if "color" in row:
                record.update(
                    components=row["color"]["components"],
                    color_reason=row["color"]["tracker_geometry_reason"],
                    extent=row["color"]["full_extent"],
                )
                selected_here = (
                    aid == int(source["lift_dispatch_id"].split("-")[-1])
                    if n == 4200
                    else aid == int(source["terminal_id"].split("-")[-1])
                    if n == 6240
                    else row["role"] == PER_STEP
                )
                if selected_here:
                    selected.append(record)
            for key in (
                "all",
                f"role/{row['role']}",
                "step_range/" + stage,
                "step_range_role/" + stage + "/" + row["role"],
            ):
                groups[key].append(record)
            for m in MODES:
                mark = markers[m]
                if mark["status"] == "UNKNOWN":
                    trace = mark["trace"]
                    measured_edges = mark["diagnostics"].get("depth_samples", [])
                    metric = []
                    for p in measured_edges[:4]:
                        fx, fy, cx, cy = source["camera"]["intrinsics"]
                        u, v = p["pixel"]
                        z = p["median_optical_depth_m"]
                        metric.append([(u - cx) * z / fx, (v - cy) * z / fy, z])
                    metric_edges = (
                        np.linalg.norm(np.roll(metric, -1, axis=0) - metric, axis=1).tolist()
                        if len(metric) == 4
                        else []
                    )
                    region[m + "/" + mark["reason"]].append(
                        {
                            "acquisition": aid,
                            "step": n,
                            "role": row["role"],
                            "decoded_ids": trace["decoded_ids"],
                            "detected_or_rejected_quads": (
                                len(trace["decoded_corners_px"]) + len(trace["rejected_quads_px"])
                            ),
                            "min_decoded_edge_px": (
                                min(
                                    float(np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1).min())
                                    for c in trace["decoded_corners_px"]
                                )
                                if trace["decoded_corners_px"]
                                else None
                            ),
                            "registered_metric_edges_m": metric_edges,
                        }
                    )
    all_rows = groups["all"]
    require(len(all_rows) == source["allocated"] == 11109, "marker denominator")
    profiles = {k: marker_stats(rows) for k, rows in groups.items()}
    all_runs: Json = {}
    brief: Json = {}
    for name, records in groups.items():
        if name.startswith("step_range_role/"):
            continue
        all_runs[name] = {}
        brief[name] = {}
        for m in MODES:
            spans = failure_runs(
                (r["acquisition"], r["step"], r["markers"][m]["status"] == "OBSERVED")
                for r in records
            )
            all_runs[name][m] = spans
            if spans:
                brief[name][m] = {
                    "run_count": len(spans),
                    "first_run": spans[0],
                    "last_run": spans[-1],
                    "longest_by_acquisitions": max(spans, key=lambda s: s["acquisitions"]),
                }
            else:
                brief[name][m] = {"run_count": 0}
    reason_stats = {}
    for key, entries in region.items():
        n_bad = {r["acquisition"] for r in entries}
        recorded = failure_runs(
            (r["acquisition"], r["step"], r["acquisition"] not in n_bad) for r in all_rows
        )
        all_runs["reason/" + key] = recorded
        reason_stats[key] = {
            "count": len(entries),
            "first": entries[0],
            "last": entries[-1],
            "longest_by_acquisitions": max(recorded, key=lambda s: s["acquisitions"]),
            "decoder_quad_count_including_rejected": stats(
                [v["detected_or_rejected_quads"] for v in entries]
            ),
            "diagnostic": (
                "No decoded ID; rejected quads alone cannot distinguish physical occlusion, "
                "raster sampling, contrast or dictionary mismatch."
                if key.endswith("/known_marker_not_observed")
                else "Frozen detector's first failing gate. Later gates are unevaluated."
            ),
        }
    cross_step: Counter[str] = Counter()
    step_rows: dict[int, list[Json]] = defaultdict(list)
    for r in all_rows:
        step_rows[r["step"]].append(r)
    for rows in step_rows.values():
        key = "consistent" if len({r["pair"] for r in rows}) == 1 else "different_same_step_results"
        cross_step[key] += 1
    traces = {
        "failure_runs_by_population_or_reason": all_runs,
        "subpix_only_acquisition_evidence": recoveries,
        "first_failing_gate_evidence": region,
    }
    (private / "marker-runs.private.json").write_text(encoded(traces) + "\n")
    marker_public = {
        "frames": len(all_rows),
        "actual_detector_calls": 2 * len(all_rows),
        "independent_native_decoder_trace_calls": 2 * len(all_rows),
        "cache_reuses": source["cached_detector_results"],
        "modes": MODES,
        "same_step_repeats_checked_independently": dict(cross_step),
        "exclusive_step_ranges": {
            "SETUP": [0, source["horizons"][0]["dispatch_step"]],
            **{
                h["skill"]: [h["dispatch_step"] + 1, h["terminal_step"]] for h in source["horizons"]
            },
        },
        "boundary_semantics": "A shared POST/PRE acquisition is counted once in the ending step "
        "range. Each original tracker use appears in the clock list.",
        "tables": profiles,
        "failure_runs": brief,
        "failure_reasons": reason_stats,
        "first_failing_gate_counts": {
            mode: {
                "id_not_decoded_unresolved": len(region[mode + "/known_marker_not_observed"]),
                "single_foreign_id": sum(
                    len(v["decoded_ids"]) == 1
                    for v in region[mode + "/foreign_or_ambiguous_marker"]
                ),
                "multiple_ids": sum(
                    len(v["decoded_ids"]) > 1 for v in region[mode + "/foreign_or_ambiguous_marker"]
                ),
                **{
                    k: len(region[mode + "/" + reason])
                    for k, reason in {
                        "boundary": "marker_boundary_clipped",
                        "corner_resolution": "marker_resolution_insufficient",
                        "depth_patch": "marker_metric_depth_unavailable",
                        "metric_size": "registered_marker_size_inconsistent",
                        "plane": "marker_depth_not_planar",
                        "axes": "ordered_marker_axes_degenerate",
                        "camera_context": "registered_camera_context_missing",
                        "invalid_rgbd": "invalid_registered_rgbd",
                    }.items()
                },
            }
            for mode in MODES
        },
        "run_semantics": "Consecutive rows in the named population in allocation order. Global "
        "spans contain every allocated acquisition; step numbers may repeat.",
        "subpix_only_validation": {
            "count": len(recoveries),
            "zero_bit_or_native_stage": Counter(v["subpix_stage"] for v in recoveries),
            "unique_id": 7,
            "min_edge_px": stats([v["subpix_min_edge_px"] for v in recoveries]),
            "registered_metric_edges_m": stats(
                [e for r in recoveries for e in r["registered_measured_edges_m"]]
            ),
            "center_plane_residual_m": stats(
                [r["subpix_plane"]["center_residual_m"] for r in recoveries]
            ),
            "max_corner_plane_residual_m": stats(
                [r["subpix_plane"]["max_corner_residual_m"] for r in recoveries]
            ),
            "nearest_none_decoded_or_rejected_quad_max_corner_distance_px": stats(
                [
                    r["nearest_none_quad_max_corner_distance_px"]
                    for r in recoveries
                    if r["nearest_none_quad_max_corner_distance_px"] is not None
                ]
            ),
            "none_has_no_quad_to_compare": sum(r["none_candidate_quads"] == 0 for r in recoveries),
        },
        "thresholds": {
            "dictionary": "DICT_4X4_50",
            "id": 7,
            "size_m": 0.075,
            "min_side_px": 8,
            "error_correction_rate": 0.0,
            "decoded_id_count": 1,
            "relative_edge_tolerance": 0.30,
            "corner_and_center_depth_patches": "Five 3x3 positive finite optical-Z patches",
            "max_corner_or_center_plane_residual_m": 0.002,
        },
        "all_frame_gate_policy": "Frozen default NONE and alternative SUBPIX are reported "
        "separately. No policy or asset change.",
        "run_detail_sha256": _sha_file(private / "marker-runs.private.json"),
    }
    result = {
        "schema_version": "research.v10.phase7.frozen-vision-summary.v1",
        "evidence_scope": "OFFLINE_READING_OF_ORIGINAL_FROZEN_V10_PIXELS",
        "source": {
            k: source[k]
            for k in (
                "inventory_file_sha256",
                "inventory_entry_digest",
                "verified_files",
                "inventory_bytes",
                "allocated",
                "roles",
                "references",
                "camera",
                "marker_family",
                "registration",
                "source_generation",
                "algorithm_and_asset_sha256",
                "protocol_sha256",
                "details_sha256",
                "cv2",
                "numpy",
            )
        },
        "binding_checks": [
            "Pinned complete inventory count, byte count, member set and each member SHA256.",
            "Every allocated acquisition linked by ID, capture role, operation, interval, record "
            "sequence, episode, physical-state hash, original camera, observation checksum and "
            "registered camera/optical depth. Every original source-frame was reconstructed.",
            "Each blob matches the per-frame and inventory hashes; RGB-D validation verifies "
            "the valid mask is exactly positive finite depth.",
        ],
        "sensor_time": {
            "physics_step_coverage": step_coverage([r["step"] for r in all_rows], 0, 6240),
            "progress_by_acquisition": time_progress,
            "capture_inside_recorded_utc_interval": len(all_rows),
            "valid_depth_pixels_per_frame": stats([r["mask_valid_px"] for r in all_rows]),
            "operational_capture_brackets_ordered": len(all_rows),
            "online_tracker_clock_records": clocks,
            "online_tracker_clock_rows_by_purpose": Counter(c["purpose"] for c in clocks),
            "online_tracker_clock_records_count": len(clocks),
            "captured_frame_count_without_registered_evaluation": len(all_rows)
            - len({c["acquisition"] for c in clocks}),
            "online_observed_capture_age_s": stats(ages),
            "unique_frames_with_these_tracker_clocks": len({r["acquisition"] for r in clocks}),
            "freshness_rule_age_s": [-0.05, 5.0],
            "clock_basis": "Recorded evaluation UTC is used only for an original tracker call. "
            "Other archived pixels have sensor capture UTC and simulation time but "
            "no original tracker evaluation time.",
        },
        "color_thresholds": {
            "normalized_rgb_distance_lt": 0.14,
            "channel_range_gt": 30,
            "connectivity": 8,
            "minimum_area_px": 8,
        },
        "lift": lift_public(all_rows, selected, source, private),
        "r593": marker_public,
        "software_control_suite": {
            "file": "tests/test_phase7_frozen_vision.py",
            "expected_outcomes": {
                "unique_standard_color_and_metric_extent": "OBSERVED_WITH_SYNTHETIC_CALIBRATION",
                "two_exchangeable_supports": "UNKNOWN_IDENTITY",
                "missing_or_split_color_support": "MISSING_OR_AMBIGUOUS",
                "registered_depth_hole": "REJECTED_INCOMPLETE_DEPTH",
                "uncalibrated_metric_extent": "UNKNOWN",
                "missing_step_boundary": "MISSING_RANGE_RECORDED",
                "same_step_reacquisition": "NO_PHYSICS_ADVANCE",
                "decreasing_step_or_capture_clock": "OUT_OF_ORDER",
                "expired_tracker_time_or_missing_camera_binding": "REJECTED",
                "grounding_clock_rebound_to_another_frame": "REJECTED",
                "same_pixel_overlap_in_missing_time": "NO_LINK",
                "ordered_90_degree_marker_pose": "OBSERVED_AT_SAMPLES_ONLY",
                "unique_registered_marker": "OBSERVED",
                "foreign_duplicate_or_plain_black_marker": "UNKNOWN",
                "wrong_size_or_invalid_marker_depth": "UNKNOWN",
            },
        },
        "offline_simulator_attribution": offline,
        "computational_scope": {
            "formal_simulations": 0,
            "formal_claims": 0,
            "hardware_actions": 0,
            "model_calls": 0,
        },
    }
    with public.open("x") as f:
        json.dump(result, f, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        f.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", required=True, type=Path)
    parser.add_argument("--public", required=True, type=Path)
    args = parser.parse_args()
    summarize(args.private, args.public)
