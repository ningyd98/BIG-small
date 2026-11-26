"""Trace the existing fixed-TCP IK branch without integration, rendering or control."""
import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import mujoco as mj
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-g1-fixed-tcp-id7-geometry-20261126"))
import fixed_tcp_geometry as original  # noqa: E402

PLAN = original.read(HERE / "plan.json")
# Integer increments avoid comparisons of accumulated floating-point scheduling ticks.
UNIT = PLAN["min_step_deg"]
NOMINAL = int(PLAN["nominal_step_deg"] / UNIT)
REPORT = int(PLAN["report_grid_deg"] / UNIT)
LIMIT = int(PLAN["max_signed_parameter_deg"] / UNIT)


class OutsideBranch(ValueError):
    """A trial segment failed and the last accepted state must be restored."""


def tangent(jacobian, aligned=None):
    _, sigma, directions = np.linalg.svd(jacobian, full_matrices=True)
    if sigma[0] == 0 or sigma[-1] / sigma[0] <= PLAN["min_rank_ratio_strict"]:
        raise OutsideBranch("jacobian_rank")
    value = directions[-1]
    if aligned is None:
        if abs(value[3]) < 1e-8:
            raise OutsideBranch("initial_joint4_sign_ambiguous")
        return value if value[3] > 0 else -value
    dot = float(value @ aligned)
    if abs(dot) < np.cos(np.deg2rad(PLAN["max_tangent_angle_deg"])):
        raise OutsideBranch("tangent_rotation_exceeded")
    return value if dot > 0 else -value


def contact_depths(model, data):
    contacts = {}
    for contact in data.contact:
        pair = tuple(sorted([
            model.geom(contact.geom1).name,
            model.geom(contact.geom2).name,
        ]))
        contacts.setdefault(pair, []).append(float(contact.dist))
    return {pair: np.sort(values) for pair, values in contacts.items()}


class State:
    def __init__(self, model, data, cal):
        self.model, self.data, self.cal = model, data, cal
        joints = [model.joint(name) for name in original.JOINTS[:7]]
        self.qpos = np.array([int(joint.qposadr[0]) for joint in joints])
        self.qvel = np.array([int(joint.dofadr[0]) for joint in joints])
        self.root = data.qpos[self.qpos].copy()
        self.target = original.pose(data)
        self.clock = float(data.time)
        self.other = np.setdiff1d(np.arange(model.nq), self.qpos)
        self.nonarm = data.qpos[self.other].copy()
        self.original_velocity = data.qvel.copy()
        self.original_control = data.ctrl.copy()
        camera = model.camera("rgbd").id
        self.camera_id = camera
        self.camera = (data.cam_xpos[camera].copy(), data.cam_xmat[camera].copy())
        self.allowed = contact_depths(model, data)
        original.require(
            self.allowed.keys() == {tuple(sorted(("object_geom", "table")))},
            "original slot has unexpected actual contacts",
        )
        self.fixed_gaps = {
            pair: original.distance(model, data, *pair) for pair in self.allowed
        }
        self.forbidden = [
            pair for pair in original.PAIRS if tuple(sorted(pair)) not in self.allowed
        ]
        ranges = np.array([joint.range for joint in joints])
        # Intersection of MJCF physical limits and the native apply_joint_targets clip.
        self.lower = np.maximum(ranges[:, 0], -2.8)
        self.upper = np.minimum(ranges[:, 1], 2.8)

    def set_geometry(self, q):
        """Assign coordinates only, then refresh static derived quantities."""
        self.data.qpos[self.qpos] = q
        mj.mj_forward(self.model, self.data)

    def check_anchor_invariants(self):
        data = self.data
        original.require(
            data.time == self.clock
            and np.array_equal(data.qpos[self.other], self.nonarm)
            and np.array_equal(data.qvel, self.original_velocity)
            and np.array_equal(data.ctrl, self.original_control)
            and np.array_equal(data.cam_xpos[self.camera_id], self.camera[0])
            and np.array_equal(data.cam_xmat[self.camera_id], self.camera[1]),
            "non-arm state, camera or source clock changed in static calculation",
        )

    def jacobian(self):
        matrix = original.jacobian(self.model, self.data, self.qvel)
        return np.vstack((matrix[:3] / PLAN["translation_scale_m"], matrix[3:] / 0.12))

    def check_coordinates(self, q):
        if (
            not np.isfinite(q).all()
            or np.any(q <= self.lower)
            or np.any(q >= self.upper)
            or np.any(abs(q - self.root) > np.deg2rad(PLAN["max_joint_excursion_deg"]))
        ):
            raise OutsideBranch("joint_range_or_excursion")

    def screen(self, q):
        self.check_anchor_invariants()
        self.check_coordinates(q)
        contacts = contact_depths(self.model, self.data)
        if contacts.keys() != self.allowed.keys() or any(
            values.shape != self.allowed[pair].shape
            or not np.isfinite(values).all()
            or np.any(values < self.allowed[pair] - 1e-9)
            for pair, values in contacts.items()
        ):
            raise OutsideBranch("changed_or_deepened_contact")
        options = sorted(
            (original.distance(self.model, self.data, *pair), pair) for pair in self.forbidden
        )
        if not np.isfinite([gap for gap, _ in options]).all():
            raise OutsideBranch("unknown_static_distance")
        gap, pair = options[0]
        if gap <= PLAN["min_static_distance_strict_m"]:
            raise OutsideBranch("static_distance:" + "/".join(pair))
        return dict(gap_m=gap, pair=pair,
                    actual_allowed_contact_count=sum(len(values) for values in contacts.values()))

    def correct(self, anchor, predictor, normal, total_step):
        q = predictor.copy()
        for iteration in range(PLAN["max_corrections"] + 1):
            self.check_coordinates(q)
            self.set_geometry(q)
            dx, dr = original.residuals(self.data, self.target)
            dp = float((predictor - q) @ normal)
            p_err, r_err = map(float, (np.linalg.norm(dx), np.linalg.norm(dr)))
            if (
                p_err <= PLAN["max_position_error_m"]
                and r_err <= PLAN["max_angle_error_rad"]
                and abs(dp) <= PLAN["max_plane_error_rad"]
            ):
                if float((q - anchor) @ normal) <= 0:
                    raise OutsideBranch("backwards_correction")
                return q, iteration, (p_err, r_err, abs(dp))
            if iteration == PLAN["max_corrections"]:
                break
            system = self.jacobian()
            tangent(system, normal)
            try:
                q = q + np.linalg.solve(
                    np.vstack((system, normal)),
                    np.r_[dx / PLAN["translation_scale_m"], dr, dp],
                )
            except np.linalg.LinAlgError as error:
                raise OutsideBranch("singular_corrector") from error
            if np.linalg.norm(q - predictor) > total_step * PLAN["max_correction_fraction"]:
                raise OutsideBranch("correction_left_local_predictor")
        raise OutsideBranch("pose_plane_corrector_not_converged")

    def segment(self, anchor, normal, units):
        last = anchor
        total_step = np.deg2rad(UNIT * units)
        chords = []
        results = []
        try:
            for t in np.linspace(1 / PLAN["subdivision_count"], 1, PLAN["subdivision_count"]):
                q, iterations, errors = self.correct(
                    anchor, anchor + total_step * t * normal, normal, total_step
                )
                proof = self.screen(q)
                next_tangent = tangent(self.jacobian(), normal)
                chord = float(np.rad2deg(np.linalg.norm(q - last)))
                if chord > PLAN["max_checked_chord_deg"] or float((q - last) @ normal) <= 0:
                    raise OutsideBranch("subdivision_jump_or_reverse")
                chords.append(chord)
                results.append(dict(proof, errors=errors, correction_iterations=iterations))
                last = q
        except OutsideBranch:
            self.set_geometry(anchor)
            self.check_anchor_invariants()
            original.require(np.array_equal(self.data.qpos[self.qpos], anchor),
                             "rejected segment did not roll back")
            raise
        return q, next_tangent, chords, results

    def optical(self):
        rays = original.Rays(self.model, self.data, self.cal["primary_camera"])
        seventh = rays.measure(7)
        eighth = rays.measure(8)
        choices = seventh["compatible_dictionary_orientations"]
        left, right = seventh["depth_only_edge_columns"]
        return {
            "arm_q_rad": self.data.qpos[self.qpos].tolist(),
            "ID7_visible": seventh["visible"],
            "ID7_first_hits": seventh["first_hits"],
            "ID7_visible_cells": seventh["visible_cells"],
            "ID7_compatible": choices,
            "ID7_ideal_edge_columns_with_4px_span": [left, right],
            "ID8_visible": eighth["visible"], "ID8_all_face_visible": eighth["visible"] == 1024,
            "both_sides_clear_ideal_depth": min(left, right) >= 5,
            "unique_ID7_original_orientation": choices == [[7, 0]],
            "qualifies_as_geometry_candidate": (
                eighth["visible"] == 1024 and min(left, right) >= 5 and choices == [[7, 0]]
            ),
            "static": self.screen(self.data.qpos[self.qpos]),
        }


def trace_branch(state, sign, initial):
    q = state.root.copy()
    state.set_geometry(q)
    normal = sign * initial
    checked = 0
    chords = 0.0
    failures = []
    samples = {}
    segments = []
    stop = "maximum_nominal_arclength"
    while checked < LIMIT:
        if len(segments) >= PLAN["max_accepted_segments_per_direction"]:
            stop = "segment_limit"
            break
        attempt = min(NOMINAL, REPORT - checked % REPORT, LIMIT - checked)
        while attempt:
            try:
                next_q, next_tangent, lengths, checks = state.segment(q, normal, attempt)
            except OutsideBranch as error:
                failures.append({
                    "start_parameter_deg": sign * checked * UNIT,
                    "attempt_deg": attempt * UNIT, "reason": str(error),
                    "rollback_verified": True,
                })
                attempt //= 2
            else:
                break
        if attempt == 0:
            stop = failures[-1]["reason"]
            break
        checked += attempt
        chords += sum(lengths)
        q, normal = next_q, next_tangent
        segments.append(dict(
            parameter_deg=sign * checked * UNIT,
            cumulative_chord_deg=chords,
            subchords_deg=lengths, checks=checks, arm_q_rad=q.tolist(),
        ))
        if checked % REPORT == 0:
            samples[str(sign * checked * UNIT)] = state.optical()
    return dict(stop=stop, final_parameter_deg=sign * checked * UNIT,
                cumulative_chord_deg=chords, samples=samples, segments=segments, refusals=failures)


def controls(state, initial):
    # Positive rays and wrong-code refusal at the same original ID8 cell centre.
    cell = state.data.geom("g1_dual_id8_r2c2")
    half = state.model.geom("g1_dual_id8_r2c2").size[2]
    point = cell.xpos + half * cell.xmat.reshape(3, 3)[:, 2]
    rays = original.Rays(state.model, state.data, state.cal["primary_camera"])
    assert rays.seen(point, "g1_dual_id8_")[0] and not rays.seen(point, "g1_dual_id7_")[0]

    qo = state.root.copy()
    state.set_geometry(qo + [0.002, 0, 0, 0, 0, 0, 0])
    dx, dr = original.residuals(state.data, state.target)
    assert np.linalg.norm(dx) > PLAN["max_position_error_m"]
    assert np.linalg.norm(dr) > PLAN["max_angle_error_rad"]
    state.set_geometry(qo)
    object_addr = int(state.model.joint("object_free").qposadr[0])
    seal = state.data.qpos.copy()
    state.data.qpos[object_addr : object_addr + 3] = state.data.geom("hand").xpos
    mj.mj_forward(state.model, state.data)
    assert not original.screen(state.model, state.data, original.live_pairs(
        state.model, state.data
    ).intersection({frozenset(pair) for pair in state.allowed}), state.fixed_gaps)["pass"]
    state.data.qpos[:] = seal
    state.set_geometry(qo)
    try:
        tangent(np.zeros((6, 7)))
    except OutsideBranch as error:
        assert str(error) == "jacobian_rank"
    else:
        raise AssertionError("rank deficient fixture was accepted")
    with patch.object(state, "screen", side_effect=OutsideBranch("fixture_stop")):
        try:
            state.segment(qo, initial, NOMINAL)
        except OutsideBranch as error:
            assert str(error) == "fixture_stop"
        else:
            raise AssertionError("rejection/rollback control did not trigger")
    assert np.array_equal(state.data.qpos[state.qpos], qo)
    q_next, next_dir, _, _ = state.segment(qo, initial, NOMINAL)
    roundtrip, _, _, _ = state.segment(q_next, -next_dir, NOMINAL)
    error = float(np.linalg.norm(roundtrip - qo))
    assert error <= 1e-5
    state.set_geometry(qo)
    return dict(
        original_positive=True, wrong_code_refused=True, wrong_tcp_refused=True,
        overlap_refused=True, rank_rejected=True, rollback_exact=True, closed_loop_error_rad=error,
    )


def run():
    for path, expected in PLAN["sha256"].items():
        path = Path(path)
        assert path.resolve().is_relative_to(Path.cwd().resolve())
        assert original.sha(path) == expected
    parent = original.read(original.HERE / "plan.json")
    slots, calibration, files = original.preflight(parent)
    assert mj.__version__ == PLAN["model_version"]
    previous_path = next(path for path in PLAN["sha256"] if path.endswith("/primary.json"))
    previous = original.read(Path(previous_path))["states"]
    results = {}
    model = mj.MjModel.from_xml_path(str(original.ASSET))
    model.opt.timestep = 1 / 240
    check_controls = None
    for scene, clocks in PLAN["slots"].items():
        for tick in clocks:
            key = f"B/{scene}/{tick}"
            data = mj.MjData(model)
            restored = original.restore(model, data, slots[key], calibration)
            reference = original.scan_case(
                model, data, key, restored, calibration, parent["limits"],
            )
            for offset in ("-6", "0", "6"):
                assert (
                    reference["per_offset_deg"][offset] == previous[key]["per_offset_deg"][offset]
                )
            original.restore(model, data, slots[key], calibration)
            state = State(model, data, calibration)
            direction = tangent(state.jacobian())
            if check_controls is None:
                check_controls = controls(state, direction)
            zero = state.optical()
            results[key] = dict(
                restored=restored, baseline=zero, checked_previous_offsets_deg=[-6, 0, 6],
                branches={str(sign): trace_branch(state, sign, direction) for sign in (-1, 1)},
            )
    candidates = {}
    for sign in (-1, 1):
        entries = [item["branches"][str(sign)]["samples"] for item in results.values()]
        common = set.intersection(*(set(row) for row in entries))
        for level in common:
            nodes = [row[level] for row in entries]
            if all(node["qualifies_as_geometry_candidate"] for node in nodes):
                candidates[level] = min(node["static"]["gap_m"] for node in nodes)
    chosen = min(
        candidates, key=lambda value: (abs(float(value)), -candidates[value], -float(value)),
        default=None,
    )
    return dict(
        original_A_B_manifest_files=files, controls=check_controls, states=results,
        plan_sha256=original.sha(HERE / "plan.json"), reader_sha256=original.sha(Path(__file__)),
        common_candidate_minimum_gap_m=candidates, selected_nominal_arclength_deg=chosen,
        integrations=0, render_calls=0, new_exposures=0, control_actions=0, formal_runs=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with (
        patch.object(mj, "mj_step", original.forbidden),
        patch.object(mj, "mj_step1", original.forbidden),
        patch.object(mj, "mj_step2", original.forbidden),
        patch.object(mj, "Renderer", original.forbidden),
    ):
        original.write(args.output, run())
