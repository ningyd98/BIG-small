"""Check continuation topology and publish the small geometry-only result."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def branch_rows(branch, direction, plan):
    step = plan["min_step_deg"]
    report = plan["report_grid_deg"]
    segments = branch["segments"]
    assert len(segments) <= plan["max_accepted_segments_per_direction"]
    signed = [segment["parameter_deg"] for segment in segments]
    advances = np.diff([0, *signed]) * direction
    assert np.all(advances >= step) and np.all(advances <= plan["nominal_step_deg"])
    assert np.allclose(advances / step, np.rint(advances / step), rtol=0, atol=1e-9)
    terminal = signed[-1] if segments else 0
    assert terminal == branch["final_parameter_deg"]
    assert abs(terminal) <= plan["max_signed_parameter_deg"]
    assert set(branch["samples"]) == {
        str(float(sign_level))
        for sign_level in signed if abs(sign_level) % report == 0
    }
    maxima = np.zeros(3)
    total_chord = 0.0
    minimum = float("inf")
    for segment in segments:
        chords = segment["subchords_deg"]
        checks = segment["checks"]
        assert len(checks) == len(chords) == plan["subdivision_count"]
        assert all(0 < chord <= plan["max_checked_chord_deg"] for chord in chords)
        total_chord += sum(chords)
        assert abs(total_chord - segment["cumulative_chord_deg"]) < 1e-9
        for check in checks:
            assert check["actual_allowed_contact_count"] > 0
            assert check["correction_iterations"] <= plan["max_corrections"]
            assert check["gap_m"] > plan["min_static_distance_strict_m"]
            maxima = np.maximum(maxima, check["errors"])
            minimum = min(minimum, check["gap_m"])
    for refusal in branch["refusals"]:
        assert refusal["rollback_verified"] and refusal["attempt_deg"] >= step
    assert abs(total_chord - branch["cumulative_chord_deg"]) < 1e-9
    assert np.all(maxima <= [
        plan["max_position_error_m"], plan["max_angle_error_rad"], plan["max_plane_error_rad"],
    ])
    return clear_summary(branch, minimum, maxima)


def clear_summary(branch, minimum, maxima):
    return dict(
        stop=branch["stop"], terminal_nominal_deg=branch["final_parameter_deg"],
        terminal_chord_deg=branch["cumulative_chord_deg"],
        accepted_segments=len(branch["segments"]), refused_attempts=len(branch["refusals"]),
        first_refusal=next(iter(branch["refusals"]), None),
        minimum_clearance_m=minimum if np.isfinite(minimum) else None,
        max_position_rotation_plane_errors=maxima.tolist(),
    )


def main(root, destination):
    first, second = (root / suffix for suffix in ("first.json", "second.json"))
    assert first.read_bytes() == second.read_bytes()
    report = read(first)
    plan = read(HERE / "plan.json")
    assert report["plan_sha256"] == digest(HERE / "plan.json")
    assert report["reader_sha256"] == digest(HERE / "screen_branch.py")
    actual_runs = (
        "integrations", "render_calls", "new_exposures", "control_actions", "formal_runs",
    )
    assert all(report[key] == 0 for key in actual_runs)
    assert set(report["states"]) == {
        f"B/{case}/{tick}" for case, ticks in plan["slots"].items() for tick in ticks
    }
    records = {}
    for slot, item in report["states"].items():
        assert item["checked_previous_offsets_deg"] == [-6, 0, 6]
        base = item["baseline"]
        branches = {sign: branch_rows(branch, int(sign), plan)
                    for sign, branch in item["branches"].items()}
        rows = {"0.0": base}
        for branch in item["branches"].values():
            rows.update(branch["samples"])
        for row in rows.values():
            assert row["qualifies_as_geometry_candidate"] == (
                row["ID8_visible"] == 1024
                and min(row["ID7_ideal_edge_columns_with_4px_span"]) >= 5
                and row["ID7_compatible"] == [[7, 0]]
            )
        best, value = max(
            rows.items(),
            key=lambda pair: (
                min(pair[1]["ID7_ideal_edge_columns_with_4px_span"]),
                pair[1]["ID7_visible"], pair[1]["static"]["gap_m"], -abs(float(pair[0])),
            ),
        )
        records[slot] = dict(
            branches=branches, original_ID7_points=base["ID7_visible"],
            scoreable_grid_points=len(rows),
            largest_ID7_point_count=max(row["ID7_visible"] for row in rows.values()),
            ideal_both_sides_grid_points=sum(
                row["both_sides_clear_ideal_depth"] for row in rows.values()
            ),
            unique_ID7_offsets_deg=sorted(
                float(offset) for offset, row in rows.items()
                if row["unique_ID7_original_orientation"]
            ),
            complete_ID7_point_grid_points=sum(row["ID7_visible"] == 1024 for row in rows.values()),
            max_count_on_previously_blocked_side=max(
                row["ID7_ideal_edge_columns_with_4px_span"][0] for row in rows.values()
            ),
            qualified_offsets_deg=[float(offset) for offset, row in rows.items()
                                   if row["qualifies_as_geometry_candidate"]],
            best_edge_then_visibility_nominal_deg=float(best),
            best_edge_then_visibility=value,
        )
    joined = set.intersection(*(
        set(row["qualified_offsets_deg"]) for row in records.values()
    ))
    assert joined == set(map(float, report["common_candidate_minimum_gap_m"]))
    common_identity = set.intersection(*(
        set(row["unique_ID7_offsets_deg"]) for row in records.values()
    ))
    with destination.open("x") as out:
        json.dump(dict(
            same_bytes_sha256=digest(first), driver_sha256=report["reader_sha256"],
            plan_sha256=report["plan_sha256"], checked_controls=report["controls"],
            common_qualified_offsets_deg=sorted(joined),
            common_ideal_unique_ID7_offsets_deg=sorted(common_identity),
            selected_nominal_arclength_deg=report["selected_nominal_arclength_deg"],
            slots=records, development_motion_qualification=False, new_exposures=0,
            new_steps=0, formal_trials=0,
        ), out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    main(args.root, args.destination)
