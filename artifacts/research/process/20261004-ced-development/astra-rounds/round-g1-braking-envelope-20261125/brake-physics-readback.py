"""Independent cold check of the raw full-stop records, geometry and directional bounds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, upper_support


def read(p):
    return json.loads(p.read_bytes())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=True)
        f.write("\n")


def audit(dir_, reg, case, profile, motion):
    ref = read(dir_ / "results.json")
    main = np.load(dir_ / "normal-prefix.npz", allow_pickle=False)
    rows = ref["unique_stops"]
    anchors = ref["anchor_to_native_stop_steps"]
    names = ref["named_geometries"]
    pairs = [tuple(i) for i in ref["named_pairs"]]
    assert len(names) == 18 and len(pairs) == 24
    aid = np.array([names.index(p) for p in profile["parts"]])
    ids = {s: i for i, s in enumerate(main["step"].tolist())}
    assert set(ids) == {s for c in anchors.values() for s in c}
    assert set(ids) == {v["brake_start"] for v in rows}
    case_checkpoints, series_peaks = {}, {}
    all_gaps = []
    discrepancy = 0.0
    branch_contacts = set()
    domain = "MOVE_ABOVE" if case["name"] == "t02" else "APPROACH"
    axes = np.asarray(profile["axes"])
    measures = profile["phases"][domain]
    pad = 1.25 * (np.asarray(measures["normal"]) + np.asarray(measures["stop"])) + 0.0005 * np.abs(
        axes
    ).sum(axis=1)
    # Static table and non-moving base are stored in the native trajectory. The online
    # motion model separately handles them and includes 16 moving bodies in the support grid.
    for anchor_s, steps in anchors.items():
        anchor = int(anchor_s)
        assert steps == list(range(anchor, anchor + 9))
        i = ids[anchor]
        q = main["q"][i]
        v = main["qvel"][i]
        center = main["centers"][i, names.index("object_geom")]
        rot = main["rotation"][i, names.index("object_geom")]

        def batch(x):
            return np.repeat(np.asarray(x)[None], 9, axis=0)

        pred_c, pred_r = motion.forecast(
            batch(q[:7]),
            batch(q[7:9]),
            batch(v[:7]),
            batch(v[7:9]),
            batch(center),
            batch(rot),
            np.arange(9)[:, None] / 240,
            False,
        )
        predicted = motion.vertices(pred_c, pred_r)
        up = np.stack([upper_support(predicted[:, j], axes, pad[j]) for j in range(len(aid))])
        mins = np.full(len(pairs), np.inf)
        worst_m = 1.0
        worst_witness = None
        for step in steps:
            j = ids[step]
            w = np.load(dir_ / f"stop-{step}.npz", allow_pickle=False)
            assert w["points"].shape == (241, 18, 8, 3) and w["pair_gap"].shape == (241, 24)
            assert w["xyz_directed_gap"].shape == (241, 24, 2, 3)
            assert all(np.isfinite(w[k]).all() for k in w.files)
            np.testing.assert_allclose(w["points"][0], main["points"][j], atol=2e-13, rtol=0)
            np.testing.assert_array_equal(w["q"][0, :7], w["command_q"][0])
            np.testing.assert_array_equal(w["command_q"], np.broadcast_to(w["q"][0, :7], (241, 7)))
            np.testing.assert_allclose(w["centers"], w["points"].mean(axis=2), atol=4e-15, rtol=0)
            pos = w["centers"][:, 10] - w["tcp"]
            np.testing.assert_allclose(
                w["cube_in_tcp"][:, :, -1],
                np.einsum("tij,ti->tj", w["tcp_rotation"], pos),
                atol=1e-14,
                rtol=0,
            )
            axes_w = w["sat_axis"]
            witness = w["sat_gap"]
            # Verify the signed separating witness against every physical corner projection.
            xyz = w["points"]
            ind0 = [names.index(a) for a, b in pairs]
            ind1 = [names.index(b) for a, b in pairs]
            a = xyz[:, ind0]
            b = xyz[:, ind1]
            recomputed = np.einsum("tpvi,tpi->tpv", b, axes_w).min(axis=2) - np.einsum(
                "tpvi,tpi->tpv", a, axes_w
            ).max(axis=2)
            discrepancy = max(discrepancy, float(abs(witness - recomputed).max()))
            np.testing.assert_allclose(witness, recomputed, atol=4e-13, rtol=0)
            np.testing.assert_allclose(
                w["xyz_directed_gap"][:, :, 0], b.min(axis=2) - a.max(axis=2), atol=4e-14, rtol=0
            )
            np.testing.assert_allclose(
                w["xyz_directed_gap"][:, :, 1], a.min(axis=2) - b.max(axis=2), atol=4e-14, rtol=0
            )
            native = w["engine_gap"]
            backup = np.where((native == 0) & (witness > 0), witness, native)
            np.testing.assert_array_equal(w["pair_gap"], backup)
            assert [k[0] for k in read(dir_ / f"contacts-{step}.json")] == list(range(241))
            if any(
                pair
                for record in rows
                if record["brake_start"] == step
                for pair in record["forbidden_pairs"]
            ):
                branch_contacts.add(step)
            # Project the actual native points. The online model independently constructs
            # its forecast, including its own enclosing geometry for each capsule.
            if case["xml_mode"] == "original" and ref["xml_sha256"] != reg["current_asset_sha256"]:
                continue
            prefix = np.array([main["points"][ids[s], aid] for s in range(anchor, step + 1)])
            truth = np.concatenate((prefix, xyz[:, aid]), axis=0)
            support = np.einsum("tpvi,ki->tpvk", truth, axes, optimize=True).max(axis=2)
            slack = up[None] - support
            j0, p0, k0 = np.unravel_index(slack.argmin(), slack.shape)
            if slack[j0, p0, k0] < worst_m:
                worst_m = float(slack[j0, p0, k0])
                worst_witness = dict(
                    absolute_tick=int(anchor + j0 if j0 < len(prefix) else step + j0 - len(prefix)),
                    halt_step=step,
                    geometry=profile["parts"][p0],
                    axis=axes[k0].tolist(),
                    at_tick_after_stop=int(j0 - len(prefix)),
                )
            for setname, sl in [
                ("arm_links", slice(0, 6)),
                ("hand_and_fingers", slice(6, 9)),
                ("assembly", slice(9, None)),
            ]:
                val = float(slack[:, sl].min())
                series_peaks[setname] = min(series_peaks.get(setname, 1.0), val)
            mins = np.minimum(mins, w["pair_gap"].min(axis=0))
        # Merge in the entire normal 0..8 prefix for every pair, including the shortest-stop branch.
        normal_min = main["pair_gap"][[ids[s] for s in steps]].min(axis=0)
        stored_min = np.min([r["min_gap_m"] for r in rows if r["brake_start"] in steps], axis=0)
        mins = np.minimum(normal_min, stored_min)
        all_gaps.append(mins)
        j = int(mins.argmin())
        case_checkpoints[anchor_s] = dict(
            minimum_gap_m=float(mins[j]),
            minimum_pair=pairs[j],
            left_and_right_id8_minimum_m=[
                float(mins[pairs.index((p, "g1_dual_id8_plate"))])
                for p in ("left_finger_geom", "right_finger_geom")
            ],
            forbidden_starts=sorted(branch_contacts.intersection(steps)),
            measured_support_minimum_margin_m=worst_m if worst_witness else None,
            measured_support_worst=worst_witness,
        )
    allgaps = np.min(all_gaps, axis=0)
    i = int(allgaps.argmin())
    return dict(
        series=ref["name"],
        role=ref["role"],
        xml_sha256=ref["xml_sha256"],
        case_anchors=case_checkpoints,
        distinct_native_brakes_in_this_trajectory_mode=len(rows),
        branch_windows_with_contact=len(branch_contacts),
        forbidden_pairs=sorted({p for r in rows for p in r["forbidden_pairs"]}),
        minimum_gap_m=float(allgaps[i]),
        minimum_pair=pairs[i],
        maximum_offline_SAT_crosscheck_error_m=discrepancy,
        signed_support_minimum_truth_anchor_margin_by_body_m=series_peaks,
        maximum_original_replay_residuals=ref["maximum_absolute_original_replay_residual"],
        sent_velocity_native_equal_timestamp_undefined=ref.get(
            "sent_velocity_native_equal_timestamp_undefined", []
        ),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    root = args.root.resolve()
    raw = args.raw.resolve()
    reg = read(Path(__file__).with_name("brake-physics-preregistration.json"))
    support = root / "scripts/graduation/g1_complete_cv_support_profile.json"
    profile = read(support)
    if sha(support) != "1202b3a1bafe024dd99b1d4d5b0869c608fbf73713ece3597482c942ef63eae6":
        raise ValueError("support profile changed before independent verification")
    geom = MotionGeometry(Model(root / reg["frozen_runtime"] / reg["current_asset"]))
    assert geom.names == profile["parts"]
    args.out.mkdir(exist_ok=True, parents=True)
    files = {str(p.relative_to(raw)): sha(p) for p in sorted(raw.glob("*/*")) if p.is_file()}
    write(args.out / "file-manifest.json", files)
    result = []
    for d in sorted(p for p in raw.iterdir() if p.is_dir()):
        case = next(c for c in reg["cases"] if d.name.startswith(c["name"] + "-"))
        r = audit(d, reg, case, profile, geom)
        result.append(r)
        print(
            d.name,
            "slack",
            r["signed_support_minimum_truth_anchor_margin_by_body_m"],
            "gaps",
            r["minimum_gap_m"],
            flush=True,
        )
    total = sum(i["distinct_native_brakes_in_this_trajectory_mode"] for i in result)
    coded = dict(
        total_trajectory_mode_stops=total,
        total_solver_advances_after_stop=total * 240,
        timed_windows_including_duplicate_endpoints=sum(9 * len(i["case_anchors"]) for i in result),
        raw_files=len(files),
        raw_manifest_sha256=sha(args.out / "file-manifest.json"),
        support_profile_sha256=sha(support),
        notes=(
            "The independent directional test uses the offline physical origin for each "
            "8-tick forecast. Minimum margin includes all true world XYZ moving OBB "
            "vertices on 98 signed axes at all pre-brake and brake sample ticks. "
            "Optical registration uncertainty and continuous between-tick containment "
            "require independent evidence."
        ),
        series=result,
    )
    write(args.out / "readback.json", coded)


if __name__ == "__main__":
    main()
