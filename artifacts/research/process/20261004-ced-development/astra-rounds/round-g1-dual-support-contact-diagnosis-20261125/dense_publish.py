"""Publish separate native, same-state counterfactual and observed-space measurements."""

import importlib
import itertools
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
source = importlib.import_module("dense_readback")
read, write, sha, require = source.read, source.write, source.sha, source.require


def check_twice(private, previous):
    lanes = [private / lane for lane in ("one", "two")]
    receipts = read(private / "cold-reader-receipts.json")
    require(
        len(receipts) == 2
        and len({r["pid"] for r in receipts}) == 2
        and all(r["exit_code"] == 0 for r in receipts),
        "two independent cold workers did not complete",
    )
    seals = [read(p / "seal.json") for p in lanes]
    require(
        seals[0] == seals[1] and seals[0]["plan_sha256"] == source.PLAN,
        "independent source or data hashes differ",
    )
    seal = seals[0]
    for name, checksum in seal["files_sha256"].items():
        require(all(sha(d / name) == checksum for d in lanes), "sealed worker file changed")
    first = read(previous / "one/seal.json")
    require(
        first["files_sha256"] == seal["files_sha256"],
        "source formatting changed a numerical result",
    )
    for p in (
        Path(source.__file__),
        Path(source.geom.__file__),
        Path(source.registered.__file__),
        Path(source.old.__file__),
    ):
        require(sha(p) == seal["programs_sha256"][p.name], "source changed after measurement")
    return {
        **seal,
        "two_cold_reader_pids": [r["pid"] for r in receipts],
        "two_seals_sha256": [sha(p / "seal.json") for p in lanes],
        "source_data_byte_identical_after_ruff_format": True,
        "final_private_directory": str(private.resolve()),
        "preformat_private_directory": str(previous.resolve()),
        "private_preformat_source_sha256": {
            p.name: sha(p) for p in (previous / "frozen-source").iterdir()
        },
        "full_raw_and_derived_products": {
            k: {"path": str((lanes[0] / k).resolve()), "sha256": v}
            for k, v in seal["files_sha256"].items()
        },
    }


def per_pair(detail, summary):
    pair_rows = {}
    strict_count = 0
    for i, p in enumerate(detail["pair_order"]):
        if p[0] not in source.old.PARTS or p[1] not in source.geom.ARMS:
            continue
        key = tuple(p)
        nearest = source.separation_key(summary, key)
        contact = []
        nonpositive = []
        unproved = []
        for state in detail["states"]:
            adjustment = next((x for x in state["separation_witness"] if x[0] == i), None)
            val = state["raw_signed_mm"][i] if adjustment is None else adjustment[1]
            if val <= 0:
                nonpositive.append(state["step"])
            if adjustment and adjustment[2] == "separation_unproved":
                unproved.append(state["step"])
            n = sum(set(c["pair"]) == set(p) for c in state["reconstructed_contacts"])
            if n:
                contact.append([state["step"], n])
        strict_count += 1
        pair_rows[" / ".join(p)] = {
            **nearest,
            "geometric_nonpositive_steps": nonpositive,
            "unproved_steps": unproved,
            "engine_contact_step_and_multiplicity": contact,
            "first_engine_contact_step": contact[0][0] if contact else None,
        }
    require(strict_count == 18, "incomplete hand/left/right by the six parts")
    return pair_rows


def occupancy_summary(data, private):
    names = source.geom.ARMS
    results = {}
    for trace, s in data["observed_traces"].items():
        filtered = {}
        for offset, code, region in itertools.product(
            (15, 30),
            (7, 8),
            ("root_face", "pillar_connection_face", "plate_connection_face", "original_beam"),
        ):
            key = f"{offset}/id{code}/{region}"
            v = min(
                (
                    {**s["minimum_by_hand_and_zone"][hand + ";" + key], "hand": hand}
                    for hand in names
                ),
                key=lambda r: r["max_sat_gap_m"],
            )
            filtered[key] = v
        results[trace] = {
            "states": s["samples"],
            "object_frame_hand_boxes": s["boxes"],
            "raw_box_history_sha256": s["raw_sha256"],
            "located_intersections": s["all_intersections"],
            "intersection_counts": s["nonseparated_step_counts"],
            "contact_with_root_or_pillar_or_plate_connection_faces": s[
                "contact_with_registered_connection_faces"
            ],
            "minimum_tested_signed_axis_gap_by_region": filtered,
            "per_hand_and_region": s["minimum_by_hand_and_zone"],
            "maximum_FK_residuals": s["maximum_fk_residuals"],
        }
    long = results["30"]
    rows = long["located_intersections"]
    actual = next(x for x in rows if x["zone"] == "30/id7/original_beam")
    short = next(x for x in rows if x["zone"] == "15/id7/original_beam")
    require(
        actual["step"] == short["step"] == 1228
        and actual["hand"] == short["hand"] == "left_finger_geom"
        and actual["positive_3d_volume"]
        and actual["vertices_m"] == short["vertices_m"]
        and actual["volume_m3"] == short["volume_m3"]
        and actual["min_m"][1] > 0.035
        and actual["max_m"][1] < 0.071,
        "intersection is not confined to the shared retained beam",
    )
    require(
        not any("extension_" in x["zone"] or x["zone"].endswith("face") for x in rows)
        and not results["15"]["located_intersections"],
        "unexpected intersection with an attachment face",
    )
    vertices = np.array(actual["vertices_m"])
    interior = vertices.mean(axis=0)
    occupied = read(private / "one/occupation-30.json.gz")["states"][-1]["occupancy"][
        "left_finger_geom"
    ]
    hand_axis = np.array(occupied["local_from_box_rotation_row_major"]).reshape(3, 3)
    margin = np.asarray(occupied["half_m"]) - np.abs(
        hand_axis.T @ (interior - occupied["center_m"])
    )
    box_lo, box_hi = np.array(data["zones_bounds_m"]["15/id7/original_beam"])
    radius = float(np.min(np.r_[margin, interior - box_lo, box_hi - interior]) - source.geom.TOL_M)
    require(radius > 0, "no certified common interior ball")
    ball = {
        "center_object_m": interior.tolist(),
        "conservative_radius_m": radius,
        "applicability": (
            "Same +30 physical state 1228. The entire ball is inside the left finger and the "
            "retained material of both registered ID7 beams."
        ),
    }
    return {
        "schema": "g1.dual-support.discrete-occupancy.v1",
        "plan_sha256": source.PLAN,
        "states": {"15": 1222, "30": 1229},
        "recorded_hand_finger_boxes": sum(s["object_frame_hand_boxes"] for s in results.values()),
        "coordinate_frame": (
            "Object geometric center, object-local +X/+Y/+Z; SI units. R maps geometry-local "
            "coordinates into the object frame."
        ),
        "sampled_forbidden_set": (
            "Union over the two recorded trajectories, sampled steps and left finger/right "
            "finger/palm of c + R q, |q_i| <= h_i."
        ),
        "closed_set_membership": (
            "abs(R.T @ (point - c)) <= h, per axis; numerical halfspace tolerance 1e-12 metre. "
            "Raw vertices use corner sign order (-1,+1)^3."
        ),
        "sample_scope": (
            "Discrete poses only. Motion interpolation, between-step swept occupancy and future "
            "closed-loop trajectories are unknown."
        ),
        "spatial_bound_scope": (
            "A positive maximum SAT projection gap certifies separation and lower-bounds "
            "Euclidean distance. Actual clipped intersection volumes and vertices are reported "
            "separately."
        ),
        "reconstruction_uncertainty": (
            "Raw per-step archive-vs-FK residuals are retained separately. They measure "
            "reproducibility of recorded kinematics, not a bound on real hardware or a "
            "between-step envelope."
        ),
        "zones_object_local_bounds_m": data["zones_bounds_m"],
        "geometry_masks": data["geometry_masks"],
        "trajectories": results,
        "common_intersection_1228": {
            "volume_mm3": actual["volume_m3"] * 1e9,
            "min_object_mm": (1000 * np.array(actual["min_m"])).tolist(),
            "max_object_mm": (1000 * np.array(actual["max_m"])).tolist(),
            "verified_common_interior_ball": ball,
        },
        "necessary_condition": (
            "Any support intended to avoid the two recorded hand sweeps must exclude the observed "
            "occupied interiors. Both registered straight ID7 spans include the clipped positive "
            "volume at state 1228. Extending the same rooted cross-section preserves this "
            "intersection at that fixed state."
        ),
        "load_path": (
            "The two registered root faces and beam/pillar connection faces themselves are "
            "separated from the hands at sampled poses. Connectivity or load capacity of a "
            "redesigned route, safety between samples, and interaction beyond the stops remain "
            "unverified."
        ),
    }


def compare_stages(traces):
    starts = {
        k: next(z["entered_step"] for z in v["action_endpoints"] if z["skill"] == "APPROACH")
        for k, v in traces.items()
    }
    return {
        "15_approach_start_step": starts["15"],
        "30_approach_start_step": starts["30"],
        "same_absolute_step_is_different_approach_elapsed": True,
        "at_step_1221_approach_elapsed_steps": {
            "15": 1221 - starts["15"],
            "30": 1221 - starts["30"],
        },
    }


def publish(private, previous):
    seal = check_twice(private, previous)
    data = private / "one"
    packed = read(data / "matrix-summary.json")
    matrix = {}
    for name, s in packed.items():
        detail = read(data / (name + ".json.gz"), s["detail_sha256"])
        matrix[name] = {
            k: s[k]
            for k in (
                "trace",
                "mount",
                "type",
                "states",
                "source",
                "left_beam",
                "right_plate",
                "unauthorized_contact_timesteps",
                "by_geometric_pair",
                "critical",
                "contact_steps",
                "minimum_each_pair",
                "unauthorized_contact_steps",
                "unproved_separation_steps",
                "nonpositive_or_unauthorized_steps",
                "first_hazard",
                "source_contact_multiplicity_differences",
                "maximum_restoration_residual",
                "detail_sha256",
                "pairs_per_state",
            )
        }
        matrix[name]["hand_to_each_support_part"] = per_pair(detail, s)
    require(
        matrix["trace30_mount30"]["first_hazard"]["step"] == 1228
        and matrix["trace15_mount15"]["first_hazard"]["step"] == 1221
        and not matrix["trace30_mount30"]["source_contact_multiplicity_differences"]
        and not matrix["trace15_mount15"]["source_contact_multiplicity_differences"],
        "native first physical hazard changed",
    )
    require(
        matrix["trace30_mount30"]["right_plate"]["minimum_mm"] > 6
        and matrix["trace15_mount30"]["right_plate"]["minimum_mm"] > 3,
        "registered same-pose positive gap missing",
    )
    tr = read(data / "trajectory-summary.json")
    command = tr["native_control"]
    joint_diff = read(data / "trajectory-control-differences.json.gz", tr["measurements_sha256"])
    max_rows = {k: max(joint_diff, key=lambda r: r[k]) for k in tr["max_by_metric"]}
    rotation = max(
        joint_diff, key=lambda r: r["delta_30_minus_15"]["object_rotation_difference_rad"]
    )
    tr["largest_same_absolute_step_differences"] = {
        k: {"at_step": v["step"], "value": v[k]} for k, v in max_rows.items()
    }
    tr["largest_object_rotation_difference_rad"] = {
        "at_step": rotation["step"],
        "value": rotation["delta_30_minus_15"]["object_rotation_difference_rad"],
    }
    tr["approach_alignment"] = compare_stages(command)
    tr["schema"] = "g1.dual-support.native-trajectory-differences.v1"
    tr["plan_sha256"] = source.PLAN
    write(HERE / "dense-trajectories.public.json", tr)
    write(
        HERE / "dense-matrix.public.json",
        {
            "schema": "g1.dual-support.registered-pose-matrix.v1",
            "plan_sha256": source.PLAN,
            "matrices": matrix,
            "separation_unit": "millimetres, positive separated and negative penetrating",
            "scopes": {
                "native": (
                    "Restored exact source trajectory and its own compiled physical assembly."
                ),
                "counterfactual": (
                    "Identical recorded kinematics for that source trajectory with the other "
                    "existing assembly. No future motion response or new trial."
                ),
            },
        },
    )
    write(
        HERE / "dense-occupancy.public.json",
        occupancy_summary(read(data / "occupation-summary.json"), private),
    )
    docs = (
        "dense-trajectories.public.json",
        "dense-matrix.public.json",
        "dense-occupancy.public.json",
    )
    seal["derived_public_outputs_sha256"] = {n: sha(HERE / n) for n in docs}
    seal["timing_or_native_trials"] = 0
    seal["source_plan_files_sha256"] = read(HERE / "plan.json", source.PLAN)["inputs_sha256"]
    seal["orchestration_sources_sha256"] = {
        p.name: sha(p)
        for p in (Path(__file__), HERE / "dense_run.py", HERE / "dense_test_geometry.py")
    }
    write(HERE / "dense-independent-seal.public.json", seal)
    print(
        "Readbacks identical.",
        {n: sha(HERE / n) for n in (*docs, "dense-independent-seal.public.json")},
        flush=True,
    )


if __name__ == "__main__":
    publish(Path(sys.argv[1]), Path(sys.argv[2]))
