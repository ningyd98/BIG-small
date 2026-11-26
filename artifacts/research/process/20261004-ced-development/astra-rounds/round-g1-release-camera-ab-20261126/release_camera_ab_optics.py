"""Classify new G1 exposures without access to physical labels or source trajectories."""

import argparse
import sys
from pathlib import Path
from time import perf_counter_ns

import numpy as np

from release_camera_ab_inputs import (
    PLAN, ROOT, checked_json, expand, inside, ordered_keys, packet, read, require, sha, write,
)
from read_dense_payload import bind_fixture
from read_pose_coverage import native_marker
from release_clearance_probe import (
    chain_controls, frame_gate, hand_geometry, per_corner_intervals, red_top_diagnostic, row_eligible,
)
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation import g1_complete_cv_payload_observation as observer
from scripts.graduation.g1_complete_cv_geometry import Model


def associate(row, source, frame, identity, marker, geometry):
    require(
        row["source"] == source
        and row["new_episode"] not in {source["historical_fit_episode"], source["source_replay_episode"]}
        and row["new_episode"] == frame.episode_id == identity.episode_id
        and frame.frame_id != source["historical_A_frame"]
        and source["source_open"]["episode_id"] == source["source_replay_episode"]
        and row["source_tick"] == source["source_tick"] == row["robot"]["physics_step"]
        and frame_gate(frame, marker, geometry, row["robot"], identity)
        and frame.sim_time_s == source["source_time_s"]
        and row["robot"].get("previous_native_return_step") is None
        and row["robot"].get("previous_native_successful_skill") is None,
        "stale, wrong or unbound exposure identity, source or encoder time",
    )


def index_rows(rows, arm):
    require(list(rows) == ordered_keys(arm), f"{arm}: missing, reordered or additional exposures")
    require(len({row["frame_id"] for row in rows.values()}) == len(rows), "duplicate exposure identity")


def openness(command, step):
    return (
        command.get("accepted") is True
        and command.get("target_open") is True
        and command.get("type") == "gripper"
        and type(command.get("physics_step")) is int
        and 0 <= command["physics_step"] <= step
    )


def eligible(intervals, command, step, fingers, support):
    if intervals is not None:
        require(
            intervals.shape == (2, 2) and np.isfinite(intervals).all()
            and (intervals[:, 0] <= intervals[:, 1]).all(),
            "invalid directional interval",
        )
    return row_eligible(intervals, openness(command, step), fingers, support)


def interval_covers(intervals, gaps):
    if intervals is None:
        return None
    bounds = np.asarray(intervals)
    return bool(np.all((bounds[:, 0] <= gaps) & (gaps <= bounds[:, 1])))


def rejected(call, *args):
    try:
        call(*args)
    except ValueError:
        return True
    return False


def edge_diagnostic(frame, marker, geometry):
    proposal = optics.measured_pose(frame, marker, geometry)
    probe = {}
    code = optics._opposite_edges.__code__

    def inspect_return(called, event, _value):
        if event != "return" or called.f_code != code:
            return
        counts = called.f_locals.get("edge_counts", [])
        probe["qualified_columns_neg_pos"] = list(counts) + [None] * (2 - len(counts))
        rows = called.f_locals.get("metric", [])
        probe["ink_samples_neg_pos"] = [
            sum(bool(line[3]) for line in rows if line[2] == side) for side in (-1, 1)
        ]

    profiler = sys.getprofile()
    try:
        sys.setprofile(inspect_return)
        require(optics.measured_pose(frame, marker, geometry) == proposal, "diagnostics changed pose output")
    finally:
        sys.setprofile(profiler)
    return proposal, probe


def observe(frame, marker, geometry, robot, identity, command, model, *, diagnostics):
    step = robot["physics_step"]
    start = perf_counter_ns()
    require(frame_gate(frame, marker, geometry, robot, identity), "encoder/exposure linkage failed")
    pose = optics.rigid_pose(frame, marker, geometry, identity=identity, physics_step=step)
    history = {}
    result = observer.payload_observation(
        frame, marker, geometry, robot, "RELEASE", "DWELL",
        identity=identity, physics_step=step, optical=pose, history=history,
    )
    _, axes, planes, fingers = hand_geometry(model, robot)
    intervals, _, widths = per_corner_intervals(pose, model, axes, planes) if pose else (None, None, None)
    support = bool(result["evidence"].get("observed_support_and_rim", False))
    success = eligible(intervals, command, step, fingers, support)
    probe_ms = (perf_counter_ns() - start) / 1e6
    proposal, edge = edge_diagnostic(frame, marker, geometry) if diagnostics else (None, {})
    red = red_top_diagnostic(frame, marker, geometry, pose or proposal, model, axes, planes, widths)
    reasons = []
    if pose is None:
        reasons.append("no_current_independently_qualified_pose")
    if not support:
        reasons.append("current_support_or_rim_unproven")
    if not openness(command, step) or min(fingers) <= 0.035:
        reasons.append("current_opening_unproven")
    if intervals is not None and np.any(intervals[:, 0] <= 0.00025):
        for side, bounds in zip(("left", "right"), intervals, strict=True):
            if bounds[1] <= 0.00025:
                reasons.append(f"{side}_clearance_insufficient")
            elif bounds[0] <= 0.00025:
                reasons.append(f"{side}_clearance_unknown")
    return {
        "pose": pose,
        "pose_method": pose["method"] if pose else None,
        "proposal_method": proposal["method"] if proposal else None,
        "observed_ids": marker.get("observed_ids", []),
        "usable_ids": marker.get("usable_ids", []),
        "opposite_board": edge,
        "red_top": red,
        "fingers_m": fingers.tolist(),
        "observed_support_and_rim": support,
        "support_surface_visible": result["evidence"].get("support_surface_visible"),
        "registered_destination_visible": result["evidence"].get("registered_destination_visible"),
        "gaps_m": intervals.tolist() if intervals is not None else None,
        "static_frame_eligible": success,
        "original_gate_qualified": False,
        "original_gate_missing": ["current_native_release_return", "continuous_dwell", "full_live_feedback_timing"],
        "reason_codes": reasons or None,
        "probe_ms": probe_ms,
    }


def sealed_optics():
    measure, detector = native_marker(expand("{D}").parent.name)
    require(
        not observer._profile()["single_id8_red_print"]["enabled"]
        and detector == "9e216e93e17f52c0a20619b789d0e05f1382cd22385be96811084d7d8331f3ed",
        "registered visual detector or certificate changed",
    )
    return measure


def historical_controls(slots):
    opt = PLAN["gate"]["historical_positive"]
    folder = expand("{F}/physical-03") / opt["case"]
    receipt = read(folder / "sensor-receipt.json")
    identity, geometry = bind_fixture(folder, receipt)
    measure = sealed_optics()
    positive = packet(folder / "0000.json.gz")
    rows = read(folder / "rgbd-index.json")["rows"]
    item, = [row for row in rows if row["file"] == "0000.json.gz"]
    old = read(expand("{F}") / f"{opt['case']}-prediction-02.json")["records"][0]
    require(
        sha(folder / "0000.json.gz") == item["file_sha256"]
        and positive.frame_id == opt["frame_id"] == old["frame_id"]
        and positive.checksum_sha256 == old["checksum_sha256"]
        and opt["step"] == item["robot"]["physics_step"] == old["step"],
        "source of historical vision positive changed",
    )
    marker = measure(positive, geometry)
    require(frame_gate(positive, marker, geometry, item["robot"], identity), "historical positive identity")
    pose = optics.rigid_pose(positive, marker, geometry, identity=identity, physics_step=opt["step"])
    require(pose and pose["method"] == opt["method"] and old["result"]["pose"]["method"] == opt["method"],
            "historical positive lost the qualified pose")
    for name in ("center_m", "rotation", "anchor_error_object_m", "basis_error_object",
                 "center_error_m", "rotation_error_rad"):
        np.testing.assert_allclose(pose[name], old["result"]["pose"][name], rtol=0, atol=1e-12)

    negatives = {
        "wrong_calibration": not frame_gate(
            positive.model_copy(update={"calibration_version": "incorrect"}), marker, geometry, item["robot"], identity),
        "foreign_episode": not frame_gate(
            positive.model_copy(update={"episode_id": "other-trajectory"}), marker, geometry, item["robot"], identity),
        "wrong_tick": optics.rigid_pose(positive, marker, geometry, identity=identity, physics_step=opt["step"] + 8) is None,
        "stale_encoders": not frame_gate(
            positive, marker, geometry, dict(item["robot"], camera_encoder_sim_time_s=positive.sim_time_s - 8/240), identity),
    }
    from dataclasses import replace

    command = slots[ordered_keys("A")[0]]["source"]["source_open"]
    step = command["physics_step"] + 240
    intervals = np.asarray([[0.0004, 0.0006], [0.0008, 0.0012]])
    fingers = np.ones(2) * 0.039
    require(eligible(intervals, command, step, fingers, True), "synthetic two-sided positive rejected")
    synthetic_source = {
        "arm": "A", "case": opt["case"], "source_tick": opt["step"],
        "historical_fit_episode": "original-synthetic", "source_replay_episode": "counterfactual-synthetic",
        "source_time_s": positive.sim_time_s, "historical_A_frame": "archived-synthetic",
        "source_open": dict(command, episode_id="counterfactual-synthetic"),
    }
    robot = dict(item["robot"], previous_native_return_step=None, previous_native_successful_skill=None)
    owned = {"source": synthetic_source, "new_episode": positive.episode_id, "source_tick": opt["step"], "robot": robot}
    associate(owned, synthetic_source, positive, identity, marker, geometry)
    keys = ordered_keys("A")
    index = {key: {"frame_id": key} for key in keys}
    index_rows(index, "A")
    negatives.update(
        no_open=not eligible(intervals, dict(command, accepted=False), step, fingers, True),
        one_finger_open=not eligible(intervals, command, step, np.asarray([0.039, 0.035]), True),
        exact_threshold=not eligible(np.asarray([[0.00025, 0.0006], [0.0008, 0.0012]]), command, step, fingers, True),
        below_one_side=not eligible(np.asarray([[0.0001, 0.0002], [0.0008, 0.0012]]), command, step, fingers, True),
        no_support=not eligible(intervals, command, step, fingers, False),
        no_pose=not eligible(None, command, step, fingers, True),
        cross_case_identity=not frame_gate(
            positive, marker, geometry, item["robot"], replace(identity, episode_id="wrong-case")),
        damaged_digest=not frame_gate(
            positive, dict(marker, checksum="0"*64), geometry, item["robot"], identity),
        unlike_arm=rejected(
            associate, dict(owned, source=dict(synthetic_source, arm="B")),
            synthetic_source, positive, identity, marker, geometry),
        cross_case_source=rejected(
            associate, dict(owned, source=dict(synthetic_source, case="dense-fit-02")),
            synthetic_source, positive, identity, marker, geometry),
        fabricated_return=rejected(
            associate, dict(owned, robot=dict(robot, previous_native_return_step=opt["step"],
                                             previous_native_successful_skill="RELEASE")),
            synthetic_source, positive, identity, marker, geometry),
        duplicate_packet=rejected(index_rows, {**index, keys[-1]: {"frame_id": keys[0]}}, "A"),
        no_terminal_packet=rejected(index_rows, {k: index[k] for k in keys[:-1]}, "A"),
        wrong_terminal_packet=rejected(index_rows, {k: index[k] for k in [*keys[:-2], keys[-1], keys[-2]]}, "A"),
        switched_pad_sides=(
            interval_covers(intervals, np.array([0.0005, 0.001]))
            and not interval_covers(intervals[::-1], np.array([0.0005, 0.001]))
        ),
        **chain_controls(),
    )
    archive = []
    model = Model(ROOT / geometry["asset_path"])
    for key in ordered_keys("A"):
        record = slots[key]
        raw = packet(record["archive_A"])
        raw_id, geo = bind_fixture(record["archive_A"].parent, read(record["archive_A"].parent / "sensor-receipt.json"))
        expected = record["archive_prediction"]
        result = observe(raw, measure(raw, geo), geo, record["archive_encoder"], raw_id,
                         record["source"]["source_open"], model, diagnostics=True)
        require(
            result["pose_method"] == expected["qualified_pose_method"]
            and result["observed_support_and_rim"] == bool(expected["support_pose"])
            and result["gaps_m"] == expected["revised_per_corner_intervals_m"]
            and not result["static_frame_eligible"], "archived A optics did not replay",
        )
        archive.append({
            "slot": key, "frame_id": raw.frame_id, "pose_method": result["pose_method"],
            "unqualified_proposal": result["proposal_method"], "usable_ids": result["usable_ids"], "eligible": False,
        })
    negatives["single_or_partial_board_not_promoted"] = any(
        row["usable_ids"] in ([7], [8]) and row["pose_method"] is None for row in archive
    )
    require(all(negatives.values()), f"legacy control failed: {negatives}")
    return {
        "positive": {"frame_id": positive.frame_id, "step": opt["step"], "method": pose["method"]},
        "diagnostic_formula_positive": True,
        "archived_A": archive,
        "negative_controls": negatives,
        "new_physical_obstacle_controls": 0,
    }


def prediction_file(root, arm, reg_sha):
    registration = checked_json(root / "registration.json", reg_sha)
    sources = checked_json(root / "source-slots.json", registration["source_slots_sha256"])
    directory = root / arm
    index = read(directory / "index.json")
    require(index["registration_sha256"] == reg_sha, "capture registration differs")
    entries = index["rows"]
    index_rows(entries, arm)

    # This process may open only the current image/encoder envelope and the pinned
    # runtime/identity sources. Physical truth, historical expectations and scores
    # never enter the predictor.
    allow = {directory / "predictions.json"}
    for cid in (case["id"] for case in PLAN["cases"]):
        allow.add(directory / cid / "native-resets.json")
    for name in (
        "{D}/runtime-build.json",
        "{D}/scripts/graduation/g1_visibility_vision.py",
        "{G}/batches/train-full-04/allocation.json",
        "{G}/batches/train-full-04/cvfix-t02/allocation.json",
    ):
        allow.add(expand(name))
    for key, row in entries.items():
        case, tick = key.split("/")[1:]
        expected = directory / case / f"{tick}.json.gz"
        require(inside(directory, row["packet"]) == expected, f"unexpected packet path: {key}")
        allow.add(expected)

    private = ROOT / "experiments/results"

    def deny_labels(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            import os
            p = Path(os.fsdecode(args[0])).resolve()
            if p.is_relative_to(private) and p not in allow:
                raise PermissionError("read outside sealed optical input allowlist")

    sys.addaudithook(deny_labels)
    try:
        (expand("{F}/physical-03/dense-fit-01/offline-physics.json")).open("rb").close()
    except PermissionError:
        pass
    else:
        raise ValueError("label access barrier failed its negative control")
    measure = sealed_optics()
    model = None
    cache = {}
    predictions = {}
    for key, row in entries.items():
        source = sources[key]
        cid = source["case"]
        folder = directory / cid
        if cid not in cache:
            require(sha(folder / "native-resets.json") == index["cases"][cid]["reset_sha256"], "native reset digest")
            cache[cid] = bind_fixture(folder, {"id": cid, "episode_id": index["cases"][cid]["episode_id"]})
        identity, geometry = cache[cid]
        if model is None:
            model = Model(ROOT / geometry["asset_path"])
        filename = inside(directory, row["packet"])
        require(sha(filename) == row["file_sha256"], "frame packet digest differs")
        frame = packet(filename)
        marker = measure(frame, geometry)
        associate(row, source, frame, identity, marker, geometry)
        require(frame.frame_id == row["frame_id"] and frame.checksum_sha256 == row["checksum_sha256"],
                "index frame/checksum mismatch")
        observed = observe(frame, marker, geometry, row["robot"], identity, source["source_open"], model, diagnostics=True)
        predictions[key] = dict(
            observed, source_trace_sha256=source["source_trace_sha256"], source_tick=source["source_tick"],
            frame_id=frame.frame_id, new_episode=frame.episode_id, checksum_sha256=frame.checksum_sha256,
        )
    write(directory / "predictions.json", {
        "registration_sha256": reg_sha, "predictions": predictions,
        "physical_label_access": "denied_by_audit_hook",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("arm", choices=("A", "B"))
    parser.add_argument("registration_sha256")
    args = parser.parse_args()
    prediction_file(args.root.resolve(), args.arm, args.registration_sha256)
