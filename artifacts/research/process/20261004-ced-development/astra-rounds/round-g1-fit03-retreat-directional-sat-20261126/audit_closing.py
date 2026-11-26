"""Reproduce the frozen RETREAT closure reserve from its hybrid distance archive."""

import hashlib

import numpy as np
from scripts.graduation.g1_complete_cv_handoff import profile, required_delays
from scripts.graduation.perception_io import read, sha

PAIR = ("left_finger_geom", "object_geom")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def robot_face_gaps(positions, rotations, half, left, right):
    axes = rotations[:, left].transpose(0, 2, 1)
    offset = positions[:, right] - positions[:, left]
    displacement = np.einsum("nij,nj->ni", axes, offset)
    load_support = abs(axes @ rotations[:, right]) @ half[right]
    return (abs(displacement) - half[left] - load_support).max(axis=1)


def check_hybrid(engine, hybrid, face, fallback_mask):
    require(
        np.array_equal(engine[~fallback_mask], hybrid[~fallback_mask]),
        "pair_gap did not retain native nonzero distance",
    )
    require(np.all(hybrid[fallback_mask] >= 0), "negative zero-distance SAT fallback")
    require(
        np.all(face[face > 0] <= hybrid[face > 0] + 1e-12),
        "known positive face separation exceeded frozen hybrid distance",
    )


def audit(motion):
    qualified = profile()
    fit_path = motion / "handoff-motion-fit-02.json"
    unqualified = read(fit_path)
    require(
        qualified["qualified"] is True
        and unqualified["qualified"] is False
        and qualified["fit_sha256"] == sha(fit_path)
        and {k: qualified[k] for k in unqualified if k != "qualified"}
        == {k: unqualified[k] for k in unqualified if k != "qualified"},
        "qualified profile differs from frozen fit",
    )
    stage = qualified["stages"]["RETREAT"]
    pair_index = stage["pairs"].index(list(PAIR))
    result = {}
    all_closing = []
    for case in ("fit-b", "fit-c"):
        source = motion / "physical-capture-01" / case
        folder = motion / "physical-stops-01" / case / "RETREAT"
        expected = qualified["fits"][f"{case}/RETREAT"]
        require(
            sha(source / "normal.npz") == expected["normal_sha256"]
            and sha(folder / "limits.json") == expected["limits_sha256"]
            and expected["contact"] is False
            and expected["stage_passed"] is True,
            "raw training provenance is not the frozen RETREAT fit",
        )
        limits = read(folder / "limits.json")
        names = limits["body_names"]
        require(
            limits["geometry_pairs"] == stage["pairs"]
            and limits["incoming"] == "RETREAT"
            and {row["delay"] for row in limits["delays"]} == required_delays("RETREAT")
            and len(limits["delays"]) == stage["delays"] == 9,
            "wrong original stop horizon",
        )
        left, right = [names.index(name) for name in PAIR]
        with np.load(source / "physical-geometries.npz", allow_pickle=False) as loaded:
            require(loaded["names"].tolist() == names, "raw geometry order differs")
            half = 0.5 * np.ptp(loaded["local_vertices"], axis=1)
        close = np.full(len(stage["pairs"]), np.inf)
        half_tick = np.zeros_like(close)
        catalog = hashlib.sha256()
        zero_count = 0
        max_excess = -np.inf
        baseline = None
        for item in limits["delays"]:
            number = int(item["delay"])
            require(
                item["start_step"] == limits["start_step"] + number
                and item["geometry_at_start_error_m"] < 1e-12
                and not item["forbidden_contacts"],
                "original stop identity differs",
            )
            raw = folder / f"stop-{number}.npz"
            catalog.update(f"{raw.name} {sha(raw)}\n".encode())
            with np.load(raw, allow_pickle=False) as samples:
                pair_gaps = samples["pair_gap"]
                engine = samples["engine_gap"][:, pair_index]
                hybrid = pair_gaps[:, pair_index]
                signed_face = robot_face_gaps(
                    samples["centers"], samples["rotation"], half, left, right
                )
                require(
                    pair_gaps.shape == (241, len(stage["pairs"])) and np.isfinite(pair_gaps).all(),
                    "raw stop matrix shape or finiteness differs",
                )
                check_hybrid(engine, hybrid, signed_face, engine == 0.0)
                zero_count += int((engine == 0).sum())
                max_excess = max(max_excess, float((signed_face - hybrid).max()))
                close = np.minimum(close, pair_gaps.min(axis=0))
                half_tick = np.maximum(half_tick, 0.5 * abs(np.diff(pair_gaps, axis=0)).max(axis=0))
                if number == 0:
                    baseline = pair_gaps[0].copy()
        require(
            catalog.hexdigest() == expected["raw_catalog_sha256"] and baseline is not None,
            "original ordered native stop archive digest changed",
        )
        fitted = np.maximum(0, baseline - close) + half_tick
        all_closing.append(fitted)
        result[case] = {
            "steps": 2169,
            "stop_delays": 9,
            "pair_gap_initial_m": float(baseline[pair_index]),
            "minimum_pair_gap_m": float(close[pair_index]),
            "half_step_allowance_m": float(half_tick[pair_index]),
            "paired_pre_margin_fit_m": float(fitted[pair_index]),
            "maximum_face_minus_hybrid_m": max_excess,
            "engine_zero_in_pair": zero_count,
            "raw_catalog_sha256": catalog.hexdigest(),
        }
    recovered = 1.25 * np.max(all_closing, axis=0) + 0.00075
    require(
        np.array_equal(recovered, stage["pair_closing_m"]),
        "full original closing vector did not reproduce",
    )
    witnesses = []
    for name, digest in qualified["qualification_sha256"].items():
        path = motion / name
        require(sha(path) == digest, "historical independent qualification changed")
        witnesses += [row for row in read(path) if row["skill"] == "RETREAT" and row["continued"]]
    require(
        len(witnesses) == 3
        and all(
            row["in_domain"]
            and not row["actual_contact"]
            and row["scheduled_stop_instants"] == 9
            and row["envelope_pair_reserve_m"] >= 0
            and row["envelope_vertex_reserve_m"] >= 0
            for row in witnesses
        ),
        "prior independently verified RETREAT envelope missing",
    )
    ok_engine = np.array([0.4, 0.0, -0.1])
    ok_hybrid = np.array([0.4, 0.2, -0.1])
    directions = np.array([0.3, 0.19, -0.2])
    check_hybrid(ok_engine, ok_hybrid, directions, ok_engine == 0)
    try:
        check_hybrid(ok_hybrid, ok_engine, directions, ok_hybrid == 0)
    except ValueError:
        pass
    else:
        raise ValueError("engine/pair channel swap negative failed")
    return {
        "scope": "published original in-domain native RETREAT hybrid-distance envelope",
        "fit_rows": result,
        "independently_qualified_historical_trajectories": len(witnesses),
        "independent_revalidation_raw_opened": 0,
        "all_30_original_closing_values_exact": True,
        "selected_pair_original_closing_m": float(recovered[pair_index]),
        "trained_quantity": "native_nonzero_mj_geomDistance_or_clipped_SAT_substitute_at_zero",
    }
