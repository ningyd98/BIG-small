"""Independently count common release-offset prerequisites from the sealed passes."""

import argparse
import json
from collections import Counter
from itertools import product
from math import hypot
from pathlib import Path

from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def passed(row):
    return row["reject"] is None


def quality(row):
    sight = row["optical"]
    marker_edges = sight["ID7_geometry"]["depth_only_edge_columns"]
    marker_ratio = min(marker_edges) / 5
    if sight["ID7_complete_ideal_tag"]:
        marker_ratio = max(1.0, marker_ratio)
    red_ratio = sight["optical_geometric_sample_limits"]["red_side_first_hit_pixels"] / 3
    return min(marker_ratio, red_ratio)


def summarize():
    primary, cold = (OUT / name for name in ("geometry.json", "geometry.cold.json"))
    require(primary.read_bytes() == cold.read_bytes(), "cold geometry differs")
    result = read(primary)
    require(
        result["plan_sha256"] == sha(HERE / "plan.json")
        and result["source_sha256"] == sha(HERE / "screen_release.py"),
        "unbound CPU geometry results",
    )
    require(
        result["geometry_only"] == {"integrations": 0, "renders": 0, "native_commands": 0}
        and all(result["zero_reference_controls"].values()),
        "nonstatic operation or baseline control failed",
    )
    expected = {f"B/{fit}/{tick}" for fit, ticks in PLAN["cases"].items() for tick in ticks}
    require(set(result["states"]) == expected, "original slot roster changed")
    coords = {f"{a},{b}" for a, b in product(PLAN["grid_mm"], repeat=2)}
    observed, optical, passed_all = Counter(), Counter(), []
    offsets = []
    for x, y in product(PLAN["grid_mm"], repeat=2):
        key = f"{x},{y}"
        current = []
        local = Counter()
        for slot, stations in result["states"].items():
            require(set(stations) == coords, f"source grid incomplete in {slot}")
            r = stations[key]
            if not passed(r):
                observed[r["reject"]] += 1
                continue
            current.append(r)
            local["physical"] += 1
            geometry = r["physical"]
            require(
                min(geometry["pad_gaps_m"]) > PLAN["separation_strict_gt_m"]
                and geometry["cube_region_margin_m"] > PLAN["containment_margin_m"]
                and geometry["minimum_path_forbidden_gap_m"] > PLAN["static_gap_m_strict"],
                "serialized physical clearance does not pass",
            )
            vision = r["optical"]
            limits = vision["optical_geometric_sample_limits"]
            local["pose"] += bool(vision["ideal_pose_prerequisite"])
            local["red_side"] += bool(limits["red_side_ideal_gate"])
            local["red_top"] += bool(limits["red_top_ideal_gate"])
            local["table"] += bool(limits["table_ideal_gate"])
            local["target"] += bool(limits["target_ideal_gate"])
            local["joint"] += bool(vision["joint_optical_prerequisites"])
            local["ID7_complete"] += bool(vision["ID7_complete_ideal_tag"])
            local["ID7_two_edges"] += bool(vision["ID7_both_ideal_edges"])
        optical.update(local)
        if local["joint"] == 9:
            passed_all.append((hypot(x, y), -min(map(quality, current)), x, y))
        offsets.append(
            {
                "offset_xy_mm": [x, y],
                "physical_slots_out_of_9": local["physical"],
                "ideal_pose_slots_out_of_9": local["pose"],
                "ideal_red_side_slots_out_of_9": local["red_side"],
                "ideal_red_top_slots_out_of_9": local["red_top"],
                "ideal_table_slots_out_of_9": local["table"],
                "ideal_target_slots_out_of_9": local["target"],
                "joint_ideal_slots_out_of_9": local["joint"],
                "full_ID7_slots_out_of_9": local["ID7_complete"],
                "two_edges_slots_out_of_9": local["ID7_two_edges"],
            }
        )
    output = {
        "schema": "g1.release-region-offset.readback.v1",
        "source_cpu_sha256": sha(primary),
        "states": len(expected),
        "offsets": len(coords),
        "registered_endpoints": len(expected) * len(coords),
        "counts_by_prerequisite": dict(optical),
        "geometric_path_rejections": dict(observed),
        "common_physical_offsets": sum(r["physical_slots_out_of_9"] == 9 for r in offsets),
        "common_optical_prerequisite_offsets": len(passed_all),
        "selected_offset_mm": list(min(passed_all)[2:]) if passed_all else None,
        "offset_rows": offsets,
        "new_native_exposures": 0,
        "new_integrations": 0,
        "static_geometric_upper_visibility_only": True,
    }
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--digest", required=True)
    args = p.parse_args()
    output = summarize()
    require(output["source_cpu_sha256"] == args.digest, "CPU forecast hash differs")
    with (OUT / "readback.json").open("x", encoding="utf-8") as f:
        f.write(json.dumps(output, sort_keys=True, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
