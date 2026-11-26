"""Independently verify the geometry split and localize failed measured supports."""

import argparse
from fractions import Fraction
from itertools import combinations, product

import cv2
import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha
from split import (
    GAP,
    HERE,
    MM,
    OUT,
    PLAN,
    PLAN_PATH,
    P,
    check,
    registered,
    require,
    save,
    sorted_pairs,
    stations,
)


def isolated_geometry(frames):
    """Independently enumerate qualified intervals, then pair the two roles."""
    groups = {"fit": [], "validation": []}
    for lo, hi in combinations(MM, 2):
        intervals = []
        for frame in frames:
            rows = [frame[x] for x in range(lo, hi + 1)]
            if not all(r["available"] for r in rows):
                break
            unique = {}
            for r in sorted(rows, key=lambda r: (r["column_center_distance"], r["mm"])):
                unique.setdefault(r["u"], r)
            coverage = frozenset((r["u"], v) for r in unique.values() for v in r["all_search_rows"])
            columns = [r["mm"] for r in unique.values()]
            intervals.append((len(unique), max(columns) - min(columns), coverage))
        if len(intervals) != 2:
            continue
        for role in groups:
            ratio = min(
                min(Fraction(c, P[f"{role}_columns"]), Fraction(length, P[f"{role}_span_mm"]))
                for c, length, _ in intervals
            )
            if ratio >= 1:
                groups[role].append(((lo, hi), ratio, [pixels for _, _, pixels in intervals]))
    passed = []
    for fit, val in product(groups["fit"], groups["validation"]):
        gap = max(fit[0][0] - val[0][1], val[0][0] - fit[0][1])
        if gap < GAP or any(a & b for a, b in zip(fit[2], val[2], strict=True)):
            continue
        passed.append((min(fit[1], val[1]), gap, *(-x for x in (*fit[0], *val[0]))))
    if not passed:
        return 0, None
    winner = max(passed)
    return len(passed), [-x for x in winner[2:]]


def measured_conditions(base, model, meta, sign, r, c, segment, data):
    bar = model.geom(base.CROSSBAR)
    pivot = c + r @ (bar.pos + [0, 0, bar.size[2]])
    rows = []
    depth, rgb, valid = data
    for station in segment["legal"]:
        y = np.asarray(station["all_search_rows"])[::sign]
        x = np.full(len(y), station["u"])
        uv = np.column_stack((x, y))
        if not valid[y, x].all():
            rows.append([False] * 5)
            continue
        _, near = base.plane_points(uv, meta, r[:, 2], pivot)
        _, far = base.plane_points(uv, meta, [0, 0, 1], [0, 0, 0])
        sample = depth[y, x]
        usable = np.isfinite(sample) & (sample > 0)
        near_ok = usable & (abs(sample - near) < P["depth_band_m"])
        far_ok = (
            usable
            & (abs(sample - far) < P["depth_band_m"])
            & (sample - near > P["outside_offset_m"])
        )
        pair = near_ok[:-3] & near_ok[1:-2] & far_ok[2:-1] & far_ok[3:]
        gray = cv2.cvtColor(rgb[y, x].reshape(-1, 1, 3), cv2.COLOR_RGB2GRAY)[:, 0].astype(float)
        broad = gray[:-3] - gray[3:]
        across = gray[1:-2] - gray[2:-1]
        outer_contrast = pair & (abs(broad) > P["contrast_inner_outer_dn"])
        both_contrasts = (
            outer_contrast & (abs(across) > P["contrast_adjacent_dn"]) & (broad * across > 0)
        )
        rows.append(
            [
                True,
                bool(pair.any()),
                bool(outer_contrast.any()),
                bool(both_contrasts.any()),
                np.count_nonzero(both_contrasts) == 1,
            ]
        )
    sums = np.asarray(rows, dtype=int).reshape(-1, 5).sum(axis=0)
    return dict(
        zip(
            ("valid", "directed_depth", "broad_contrast", "both_contrasts", "unique"),
            sums.tolist(),
            strict=True,
        )
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prediction-sha", required=True)
    digest = p.parse_args().prediction_sha
    path = OUT / "prediction.json"
    require(sha(path) == sha(OUT / "prediction.cold.json") == digest, "cold predictions differ")
    pred = read(path)
    require(
        pred["script_sha256"] == sha(HERE / "split.py")
        and pred["plan_sha256"] == sha(PLAN_PATH)
        and all(pred["controls"].values()),
        "unbound prediction or failed control",
    )
    check(PLAN["isolated_score_sources"])
    base, geometry, _, info, seeds = registered()
    model = mujoco.MjModel.from_xml_path(str(ROOT / base.PLAN["asset"]))
    rows = []
    for (group, source), row in zip(sorted_pairs(info), pred["pairs"], strict=True):
        require(group == row["group"], "different pair order")
        rebuilt, transform = zip(
            *(stations(base, geometry, model, record, seeds[record[3]]) for record in source),
            strict=True,
        )
        require(
            [sorted((str(k), v) for k, v in s.items()) for s in rebuilt]
            == [sorted(s.items()) for s in row["stations_by_frame"]],
            "reconstructed station schedule differs",
        )
        count, endpoints = isolated_geometry(rebuilt)
        selection = row["selection"]
        selected = selection["selected"]
        require(
            count == selection["candidate_outcomes"].get("eligible", 0), "qualifying count differs"
        )
        reported = selected["fit_mm"] + selected["validation_mm"] if selected else None
        require(endpoints == reported, "independent geom optimum differs")
        scored = []
        for i, (record, result) in enumerate(zip(source, row["frames"], strict=True)):
            job, meta, file, frame = record
            require(
                frame == result["frame_id"]
                and job["checksum_sha256"] == result["episode_shutter_checksum"]
                and meta["file_sha256"] == result["dense_raw_sha256"],
                "native optical exposure not bound",
            )
            measured = result.get("measurement")
            require(bool(selected) == bool(measured), "unexpected raw source access")
            scores, reason = None, "no_disjoint_paired_geometry"
            if measured:
                require(
                    measured["pose"] is None,
                    "a new pose requires physical label and held-out ray score",
                )
                require(sha(file) == result["dense_raw_sha256"], "raw frame changed")
                with np.load(file, allow_pickle=False) as data:
                    packet = data["depth_m"], data["rgb"], data["valid"]
                scores = {
                    group: measured_conditions(base, model, meta, *transform[i], v[i], packet)
                    for group, v in selected["actual_measurement_footprints"].items()
                }
                for role, status in scores.items():
                    require(
                        status["unique"] == len(measured[f"measured_{role}"]["legal"]),
                        "independent measured step count differs",
                    )
                reason = measured["reason"]
            scored.append(
                {
                    "frame_id": frame,
                    "key": result["key"],
                    "fixture": result["fixture"],
                    "stages": scores,
                    "reason": reason,
                    "new_pose": None,
                }
            )
        if group == "old_t02":
            require(
                scored[0]["stages"] == scored[1]["stages"], "needle altered the guarded measurement"
            )
        rows.append(
            {"group": group, "eligible_splits": count, "selected_mm": endpoints, "scores": scored}
        )
    save(
        "readback.json",
        {
            "schema": "g1.development.contiguous-crossbar-split.readback.v1",
            "prediction_sha256": digest,
            "rows": rows,
            "new_poses_scored": 0,
            "inherited_needle_strong_returns_still_rejected": 4,
            "raw_selection_reproduced": True,
        },
    )


if __name__ == "__main__":
    main()
