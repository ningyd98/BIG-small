"""Measured wall time and bytes, including all required paired methods and ablations."""

from __future__ import annotations

from collections.abc import Sequence

from cloud_edge_robot_arm.research.pilot import PilotReport


def estimate_budget(report: PilotReport, candidate_ns: Sequence[int]) -> dict[str, float]:
    if not report.records:
        raise ValueError("resource budget requires measured pilot records")
    mean_seconds = sum(float(r["wall_duration_s"]) for r in report.records) / len(report.records)
    mean_bytes = sum(int(r["artifact_bytes"]) for r in report.records) / len(report.records)
    result = {"mean_episode_wall_s": mean_seconds, "mean_episode_bytes": mean_bytes,
              "foundation_120_hours": 120 * mean_seconds / 3600,
              "power_120_x4_hours": 120 * 4 * mean_seconds / 3600,
              "recovery_200_x2_hours": 200 * 2 * mean_seconds / 3600}
    for n in candidate_ns:
        result[f"formal_{n}_x4_plus3_ablations_hours"] = n * 7 * mean_seconds / 3600
        result[f"formal_{n}_x4_plus3_ablations_bytes"] = n * 7 * mean_bytes
    result["full_perception_10000_estimated_bytes"] = 10000 * 1158966.504
    result["rerun_reserve_fraction"] = .2
    return result
