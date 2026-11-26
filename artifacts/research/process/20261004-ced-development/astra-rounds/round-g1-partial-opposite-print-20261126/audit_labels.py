"""Compare frozen discrete ranges with already disclosed geometry after prediction."""
import gzip
from pathlib import Path

import numpy as np

from partial_print import HERE, OUTPUT, optics, patch, source

LABEL_PLAN = HERE / "label-audit-registration.json"
T02_TRUTH = source.T02_REL + "/instance/offline-truth.json"
AB_ROOT = source.ROOT / "experiments/results/g1-release-terminal-rebound-20261125"
TOLERANCE = 1e-9


def read_truth(packets, plan):
    ab = source.read(source.pin(source.AB / "source-slots.json", plan["ab_source_slots_sha256"]))
    t02_path = source.pin(source.CV / T02_TRUTH, plan["t02_physical_label_sha256"])
    t02_samples = source.read(t02_path)["samples"]
    truth = {
        f"t02/{row['physics_step']}": (
            row["object_geom_position_m"],
            row["object_geom_rotation_row_major"],
            row["sim_time_s"],
        )
        for row in t02_samples if f"t02/{row['physics_step']}" in packets
    }
    for key, info in packets.items():
        if key.startswith("t02/"):
            continue
        arm, case, tick = key.split("/")
        entry = ab[key]
        run = "replay-01" if arm == "A" and case == "dense-fit-01" else "replay-02"
        folder = AB_ROOT / run / arm / case
        trace = source.pin(folder / "native-trace.jsonl.gz", entry["source_trace_sha256"])
        receipt = source.read(source.pin(folder / "receipt.json", entry["source_receipt_sha256"]))
        assert receipt["trace_sha256"] == entry["source_trace_sha256"]
        assert info["step"] == entry["source_tick"] == int(tick)
        with gzip.open(trace, "rt") as file:
            row = next(row for line in file if (row := source.json.loads(line))["tick"] == int(tick))
        assert row["time_s"] == entry["source_time_s"]
        center, rotation = row["geom"]["object_geom"]
        truth[key] = (center, rotation, row["time_s"])
    assert set(truth) == set(packets)
    return truth


def read_optical_source(key, info, bindings, detector):
    path, scene, episode = bindings[info["binding"]]
    identity, geometry = (
        source.bound(path, scene, episode) if key.startswith("t02/")
        else source.bind_fixture(path.parent, {"id": scene, "episode_id": episode})
    )
    frame = source.checked_packet(source.ROOT / info["path"], info["sha256"])
    marker = detector(frame, geometry)
    assert frame.frame_id == info["frame_id"] and frame.checksum_sha256 == info["checksum"]
    assert identity.matches(frame, marker, geometry, info["step"])
    with patch.object(optics, "_opposite_edges", return_value=None):
        pose = optics.measured_pose(frame, marker, geometry)
    assert pose and pose["ids"] == [8]
    return frame, pose, geometry


def compare(frame, pose, geometry, truth, partial, half_cell):
    center, rotation, time_s = truth
    assert frame.sim_time_s == time_s
    rotation = np.asarray(rotation).reshape(3, 3)
    id8_basis = np.asarray(pose["rotation_object_to_world"])
    id8_anchor = np.asarray(pose["anchor_world_m"])
    lever = np.asarray(
        geometry["development_dual"]["markers"]["7"]["object_T_marker"]
    ).reshape(4, 4)[:3, 3]
    true_marker_center = np.asarray(center) + rotation @ lever
    xy = 1000 * ((true_marker_center - id8_anchor) @ id8_basis[:, :2] + [0.26, 0])
    relative = id8_basis.T @ rotation
    yaw = np.rad2deg(np.arctan2(relative[1, 0], relative[0, 0]))
    coords = np.r_[xy, yaw]
    lo = np.asarray(partial["all_pose_grid_min_mm_deg"])
    hi = np.asarray(partial["all_pose_grid_max_mm_deg"])
    in_grid = (coords >= lo - TOLERANCE) & (coords <= hi + TOLERANCE)
    after_quantization = (coords >= lo - half_cell - TOLERANCE) & (
        coords <= hi + half_cell + TOLERANCE
    )
    return {
        "source_true_pose_relative_to_ID8_plane_mm_mm_deg": coords.tolist(),
        "raw_discrete_interval_covers_axes": in_grid.tolist(),
        "half_cell_padded_discrete_range_covers_axes": after_quantization.tolist(),
        "observed_increment_axes": partial.get("axis_with_discrete_metric_increment", [False, False]),
        "half_cell_excess_abs_mm_mm_deg": np.maximum(
            np.maximum(lo - half_cell - coords, coords - hi - half_cell), 0,
        ).tolist(),
    }


def main(output):
    plan = source.read(LABEL_PLAN)
    reg = source.read(source.pin(OUTPUT / "registration.json", plan["input_registration_sha256"]))
    left, right = [
        source.pin(OUTPUT / ("prediction-" + name + ".json"), plan["prediction_sha256_both"])
        for name in ("first", "second")
    ]
    assert left.read_bytes() == right.read_bytes()
    raw = source.read(left)
    assert raw["registered_input_sha256"] == plan["input_registration_sha256"]
    assert raw["physical_labels_read"] is False and raw["frames"].keys() == reg["packets"].keys()
    truth = read_truth(reg["packets"], plan)
    _, bindings = source.exposure_metadata()
    detector, digest = source.native_marker(source.GENER)
    assert digest == source.PLAN["marker_sha256"]
    half_cell = np.asarray(plan["half_cell_allowance_mm_mm_deg"])
    results = {}
    for key, packet in reg["packets"].items():
        predicted = raw["frames"][key]["partial_print"]
        frame, pose, geometry = read_optical_source(key, packet, bindings, detector)
        assert "all_pose_grid_min_mm_deg" in predicted
        results[key] = compare(frame, pose, geometry, truth[key], predicted, half_cell)
    source.write(output, {
        "label_audit_registration_sha256": source.sha(LABEL_PLAN),
        "predicted_sha256": plan["prediction_sha256_both"],
        "no_new_authority": True,
        "captures": 0,
        "rows": results,
    })


if __name__ == "__main__":
    import sys
    main(Path(sys.argv[1]))
