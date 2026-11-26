"""Cold-check selected ambiguity witnesses and measure sealed wrist-relative drift."""

import argparse
from pathlib import Path

import mujoco
import numpy as np
from find_witness import OUT, PLAN, PLAN_FILE, StaticRays, history, pinned, require, save
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent


def verify_pair(scanner, chain, cases, target_window):
    require(len(cases) == 2 and cases[0]["geom"] != cases[1]["geom"], "no opposing first faces")
    for stored in cases:
        relative = np.asarray(stored["rotation"])
        translation = np.asarray(stored["translation_m"])
        require(
            np.allclose(relative.T @ relative, np.eye(3), atol=1e-10, rtol=0)
            and abs(np.linalg.det(relative) - 1) < 1e-10,
            "witness is not a rigid transform",
        )
        suffix = stored["validated_history_frames"]
        require(target_window <= suffix <= len(chain), "false history coverage")
        for row in chain[-suffix:]:
            z = row["wrist"].T @ (row["anchor_world"] - row["tcp"])
            a = row["base"] @ (translation + relative @ row["anchor"] - z)
            b = row["base"] @ relative - np.eye(3)
            require(
                min(row["err"] - abs(a)) > PLAN["minimum_anchor_constraint_margin_m"]
                and (row["basis_err"] - abs(b)).min() > PLAN["minimum_rotation_constraint_margin"],
                "witness violates original bound",
            )
        scanner.place(relative, translation)
        actual = scanner.measure(0)
        require(
            actual
            and actual["geom"] == stored["geom"]
            and abs(actual["ray_length_m"] - stored["ray_length_m"]) <= 1e-10,
            "cold first hit or distance differs",
        )


def imported_labels(family, case, chain):
    base = ROOT / PLAN["captures"][family]
    members = read(base / "seal.json")["sealed_sha256"]
    rel = f"{case}/offline-physics.json"
    labels = read(pinned(base, rel, members[rel]))["frame_labels"]
    keyed = {row["frame_id"]: row for row in labels}
    require(len(keyed) == len(labels), "duplicated sealed label")
    series = []
    for shutter in chain:
        label = keyed[shutter["frame_id"]]
        require(
            label["checksum_sha256"] == shutter["checksum_sha256"]
            and label["physics_step"] == shutter["tick"],
            "physical label lacks co-exposure join",
        )
        wrist = shutter["wrist"]
        center = wrist.T @ (np.asarray(label["center_m"]) - shutter["tcp"])
        rotation = wrist.T @ np.asarray(label["rotation"])
        require(np.isfinite(np.r_[center, rotation.ravel()]).all(), "nonfinite physical label")
        series.append((shutter["tick"], center, rotation))
    return series


def drift(series):
    values = []
    for (i, x, a), (j, y, b) in zip(series, series[1:], strict=False):
        require(j - i == PLAN["capture_stride"], "nonconsecutive label drift")
        relative = a.T @ b
        skew = relative[[2, 0, 1], [1, 2, 0]] - relative[[1, 2, 0], [2, 0, 1]]
        angle = float(
            np.degrees(np.arctan2(np.linalg.norm(skew) / 2, (np.trace(relative) - 1) / 2))
        )
        values.append([float(abs(y - x).max() * 1000), angle])
    points = np.asarray(values).reshape(-1, 2)
    return {
        "adjacent_pairs": len(points),
        "max_translation_component_mm": float(points[:, 0].max(initial=0)),
        "max_rotation_angle_deg": float(points[:, 1].max(initial=0)),
        "budget_exceedances": [
            {
                "translation_mm": t,
                "rotation_deg": r,
                "pairs_exceeding_either": int(
                    ((points[:, 0] > t + 1e-9) | (points[:, 1] > r + 1e-9)).sum()
                ),
            }
            for t in PLAN["drift_translation_mm"]
            for r in PLAN["drift_angles_deg"]
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction-sha", required=True)
    d = parser.parse_args().prediction_sha
    forecast = read(pinned(OUT, "prediction.json", d))
    pinned(OUT, "prediction.cold.json", d)
    require(
        forecast["plan_sha256"] == sha(PLAN_FILE)
        and forecast["script_sha256"] == sha(HERE / "find_witness.py")
        and all(forecast["controls"].values()),
        "predictions or controls changed",
    )
    old_control = read(
        pinned(ROOT, PLAN["isolated_readback_control"], PLAN["isolated_readback_control_sha256"])
    )
    require(
        old_control["native_optical_alias"]["bare_and_pin_RGB_depth_mask_identical"]
        and old_control["old_no_pin_stop_with_pin_geometry"]["first_intersection_stop_step"] == 176,
        "sealed needle counterexample differs",
    )
    path = ROOT / PLAN["asset"]
    rig, model = Model(path), mujoco.MjModel.from_xml_path(str(path))
    rows = []
    count = 0
    for row in forecast["rows"]:
        family, case, tick = (row[k] for k in ("family", "case", "tick"))
        camera, chain = history(rig, family, case, tick)
        require(
            len(chain) == row["history_frames"] and chain[-1]["frame_id"] == row["frame_id"],
            "history provenance changed",
        )
        for window in row["windows"]:
            pair = window.get("example")
            if pair is None:
                continue
            scanner = StaticRays(model, camera, chain[-1], [pair["uv"]])
            verify_pair(scanner, chain, pair["witnesses"], window["window"])
            count += 1
        rows.append(
            {
                "family": family,
                "case": case,
                "tick": tick,
                "measured_drift": drift(imported_labels(family, case, chain)),
            }
        )
    save(
        "readback.json",
        {
            "forecast_sha256": d,
            "cold_rechecked_opposite_pairs": count,
            "rows": rows,
            "t02_scope": "sealed same-image hazard control only",
            "old_needle_evidence_sha256": PLAN["isolated_readback_control_sha256"],
        },
    )


if __name__ == "__main__":
    main()
