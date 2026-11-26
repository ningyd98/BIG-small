"""Offline left-finger endpoint separation with the frozen native closing reserve."""

# ruff: noqa: E402
import argparse
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
BLIND = OUT / "blind"
BP = ROOT / PLAN["source_bp"]
BP_MIN = ROOT / PLAN["source_minimal_bp"]
Q = ROOT / PLAN["source_q"]
sys.path.insert(0, str(HERE.parent / "round-g1-release-fit03-q-dwell-handoff-20261126"))

import read_q as q_reader
from audit_closing import PAIR, audit, require
from scripts.graduation import g1_complete_cv_handoff as gate
from scripts.graduation.g1_complete_cv_geometry import Box, box_gap
from scripts.graduation.g1_complete_cv_handoff_optics import directional_error, rigid_pose

Q_DRIVER = q_reader.route
HAND = Q_DRIVER.handoff
READER = Q_DRIVER.reader
OPT = Q_DRIVER.dwell.optics
EXACT = Q_DRIVER.minimal.exact
store = Q_DRIVER.store


def source_pins():
    require(
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == PLAN["baseline"],
        "registered development commit differs",
    )
    for file, expected in PLAN["sha256"].items():
        require(sha(ROOT / file) == expected, f"frozen input changed: {file}")


def old_seal(folder, file, key):
    sealing = read(folder / file)
    Q_DRIVER.verified_tree(folder, sealing[key])
    return sealing


def proposal_sources():
    base = BP / "native-01"
    old_seal(base, "capture-seal.json", "members")
    old_seal(BP_MIN, "preflight-seal.json", "inputs")
    old_seal(Q / "native-01", "capture-seal.json", "members")
    old_seal(Q / "blind-01", "blind-seal.json", "members")
    b = read(BP_MIN / "blinded.json")["frames"]
    q = read(Q / "blind-01/input.json")
    q_reader.minimal_scope(q)
    tail = q["slots"][-1]
    yield (
        "P",
        BP_MIN,
        next(x for x in b if x["key"] == "c2"),
        BP / "exposure-replay.json",
        base / "b1",
    )
    yield (
        "Q",
        Q / "blind-01",
        {
            **tail["endpoint"],
            "observable_reset": q["observable_reset"],
            "frame_file": tail["path"],
            "frame_sha256": tail["sha256"],
        },
        Q / "exposure-witness.json",
        Q / "native-01/q",
    )
    yield (
        "B",
        BP_MIN,
        next(x for x in b if x["key"] == "c1"),
        BP / "exposure-replay.json",
        base / "b0",
    )


def verify_endpoint(slot, archive, proof):
    record = read(archive / "native.json")
    robot = slot["robot"]
    ticks = robot["physics_step"]
    photos = read(archive / "frames.json")
    marker = read(archive / "observable.json")
    (event,) = [e for e in marker["events"] if e.get("frame_id") == robot["frame_id"]]
    code = archive.name
    closure = (proof["route"] if code == "q" else proof["routes"][code])["shots"][-1]
    require(
        photos[-1]["role"] == slot["role"] == "DWELL-30"
        and ticks == record["open_tick"] + 480 == record["rows"] - 1
        and photos[-1]["sha256"] == slot["frame_sha256"]
        and photos[-1]["robot"] == robot == slot["robot"],
        "not actual registered last dwell exposure",
    )
    Q_DRIVER.replay.checked_witness(code, photos[-1], event, closure)
    require(
        slot["observable_reset"]
        == Q_DRIVER.minimal.reset_identity_only(
            {"episode": marker["episode"], "resets": marker["resets"]}
        ),
        "source reset identity changed",
    )
    cut = HAND.command_prefix(record["commands"], record["actions"], marker, "DWELL-30", ticks)
    require(
        cut == (slot["command_seq"], slot["arm_commands"], slot["gripper_command"]),
        "cold endpoint command prefix changed",
    )
    frozen_robot = HAND.one_tick_rows(archive / "physical.jsonl.gz", {ticks})[ticks]
    require(
        frozen_robot == slot["physical_robot"]
        and HAND.actuator_values(slot) == slot["registered_actuation"],
        "cold endpoint encoders changed",
    )


def prepare():
    source_pins()
    calibration = audit(ROOT / PLAN["historical_motion"])
    require(not OUT.exists() and OUT.resolve() == OUT, "cold attempt already claimed")
    BLIND.mkdir(parents=True)
    store(OUT / "original-closure.json", calibration)
    public, private = [], {}
    for i, (label, folder, row, prooffile, archive) in enumerate(proposal_sources()):
        verify_endpoint(row, archive, read(prooffile))
        picture = folder / row["frame_file"]
        target = BLIND / f"c{i}.json.gz"
        with target.open("xb") as stream:
            stream.write(picture.read_bytes())
        require(sha(target) == row["frame_sha256"], "slot image changed")
        data = {
            name: row[name]
            for name in (
                "role",
                "robot",
                "command_seq",
                "arm_commands",
                "gripper_command",
                "physical_robot",
                "registered_actuation",
                "observable_reset",
            )
        }
        data["path"] = target.name
        data["sha256"] = sha(target)
        validate(data, i)
        public.append(data)
        private[target.name] = {
            "condition": label,
            "archive": str(archive.relative_to(ROOT)),
            "role": row["role"],
            "tick": row["robot"]["physics_step"],
        }
    store(BLIND / "inputs.json", {"input": public})
    store(OUT / "slot-key.json", private)
    store(
        BLIND / "seal.json",
        {
            "plan_sha256": sha(HERE / "plan.json"),
            "script_sha256": sha(Path(__file__).resolve()),
            "original_closure_audit_sha256": sha(OUT / "original-closure.json"),
            "members": {f.name: sha(f) for f in BLIND.iterdir()},
        },
    )


def validate(data, n):
    EXACT(
        data,
        "path sha256 role robot command_seq arm_commands gripper_command physical_robot "
        "registered_actuation observable_reset",
    )
    require(
        data["path"] == f"c{n}.json.gz" and data["role"] == "DWELL-30", "unexpected registered role"
    )
    for field in ("robot", "physical_robot", "registered_actuation"):
        EXACT(data[field], Q_DRIVER.minimal.ATTRIBUTES[field])
        for value in data[field].values():
            Q_DRIVER.minimal.values_only(value)
    command = Q_DRIVER.minimal.COMMAND
    for cmd in data["arm_commands"]:
        EXACT(cmd, command + " applied_target_positions_rad target_positions_rad")
        for v in cmd.values():
            Q_DRIVER.minimal.values_only(v)
    EXACT(data["gripper_command"], command + " target_open")
    reset = data["observable_reset"]
    EXACT(reset, "episode resets")
    require(len(reset["resets"]) == 2, "wrong identity event count")
    for event in reset["resets"]:
        EXACT(event, Q_DRIVER.minimal.RESET_FIELDS)
        EXACT(event["parameters"], "requested")
        EXACT(event["parameters"]["requested"], "scenario_id")
        if event["phase"] == "BEGIN":
            require(event["result"] is None, "RESET BEGIN metadata exceeds identity")
        else:
            EXACT(event["result"], "physics_dt_s")
    Q_DRIVER.minimal.native_reset_ids(reset["resets"], Q_DRIVER.minimal.SCENE, reset["episode"])


def face_axes(box):
    require(
        np.all(np.isfinite(box.r))
        and np.allclose(box.r.T @ box.r, np.eye(3), rtol=0, atol=1e-12)
        and np.linalg.det(box.r) > 0,
        "invalid known finger orientation",
    )
    return np.concatenate((box.r.T, -box.r.T), axis=0)


def lower_support(left, local, optical):
    unit = face_axes(left)
    center, rotation = np.asarray(optical["center_m"]), np.asarray(optical["rotation"])
    require(
        np.array_equal(rotation, optical["rotation_object_to_world"]), "mixed certificate basis"
    )
    corners = local.corners()
    placed = corners @ rotation.T + center
    pa = left.corners()
    rows = []
    for k, u in enumerate(unit):
        error = directional_error(optical, corners, u)
        lower = placed @ u - error
        limits = pa @ u
        i = int(np.argmin(lower))
        rows.append(
            {
                "axis": u.tolist(),
                "finger_face": k % 3,
                "axis_sign": 1 if k < 3 else -1,
                "limiting_object_vertex_index": i,
                "optical_directional_error_m": error.tolist(),
                "optical_vertex_lower_m": lower.tolist(),
                "optical_vertex_upper_m": (placed @ u + error).tolist(),
                "finger_upper_m": float(limits.max()),
                "initial_gap_lower_m": float(lower[i] - limits.max() - PLAN["outward_roundoff_m"]),
            }
        )
    return rows


def check_correspondence(physical_corners, rows, case):
    for item in rows:
        projection = physical_corners @ np.array(item["axis"])
        lo, hi = [np.asarray(item[k]) for k in ("optical_vertex_lower_m", "optical_vertex_upper_m")]
        require(
            np.all((lo - 1e-12 <= projection) & (projection <= hi + 1e-12)),
            f"physical corner outside optical interval in {case}",
        )


def synthetic_controls():
    left = Box("left_finger_geom", np.zeros(3), np.full(3, 0.5), np.eye(3))
    local = Box("object_geom", np.array([0.023, -0.006, 0.002]), np.full(3, 0.029), np.eye(3))
    anchor = np.array([0.12, -0.04, 0.001])
    basis = np.full((3, 3), 0.003)
    uncertainty = np.full(3, 0.002)
    nominal = np.eye(3)
    rng = np.random.default_rng(814087)
    for i in range(256):
        x, y, z = rng.uniform(-0.002, 0.002, size=3)
        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        actual = np.linalg.solve(np.eye(3) - skew / 2, np.eye(3) + skew / 2)
        require(np.all(abs(actual - nominal) <= basis), "synthetic draw exceeds declared rotation")
        axis = -1 if i % 2 else 1
        center = np.array([0.7 * axis, 0.6, 0.12]) + rng.uniform(-0.1, 0.1, size=3)
        optical = {
            "center_m": center,
            "rotation": nominal,
            "rotation_object_to_world": nominal,
            "anchor_object_m": anchor,
            "anchor_error_object_m": uncertainty,
            "basis_error_object": basis,
        }
        truth = local.placed(
            center + rng.uniform(-1, 1, size=3) * uncertainty + (nominal - actual) @ anchor, actual
        )
        projections = lower_support(left, local, optical)
        check_correspondence(truth.corners(), projections, "synthetic convex box")
        require(
            max(row["initial_gap_lower_m"] for row in projections) <= box_gap(left, truth) + 1e-12,
            "known-axis lower bound exceeds true box SAT",
        )
    same_size = Box("object_geom", np.zeros(3), np.full(3, 0.5), np.eye(3))
    zero = {
        "rotation": nominal,
        "rotation_object_to_world": nominal,
        "anchor_object_m": anchor,
        "anchor_error_object_m": np.zeros(3),
        "basis_error_object": np.zeros((3, 3)),
    }
    for amount in (1.0, 0.9, 2.0, -2.0):
        location = np.array([amount, 0, 0])
        projections = lower_support(left, same_size, zero | {"center_m": location})
        require(
            abs(
                max(p["initial_gap_lower_m"] for p in projections)
                - (box_gap(left, same_size.placed(location, nominal)) - PLAN["outward_roundoff_m"])
            )
            < 1e-12,
            "zero-error contact/penetration or face sign control",
        )
    start, stop = np.array([2, 1, 0]), np.array([1, 2, 0])
    require(
        box_gap(left, same_size.placed(start, nominal))
        == box_gap(left, same_size.placed(stop, nominal))
        and start[0] - stop[0] == 1,
        "axis-switch negative did not exercise different quantities",
    )
    diagonal = np.array([1.0, 1.0, 0]) / np.sqrt(2)
    diagonal_box = same_size.placed(np.array([2, 2, 0]), nominal)
    unsupported = (diagonal_box.corners() @ diagonal).min() - (left.corners() @ diagonal).max()
    require(unsupported > box_gap(left, diagonal_box), "arbitrary-axis negative did not exceed SAT")
    return {
        "bounded_poses": 256,
        "zero_error_contact_and_both_signs": True,
        "limiting_axis_switch": True,
        "arbitrary_axis_negative": True,
    }


def restrict(output):
    resources = {
        BLIND / "seal.json",
        BLIND / "inputs.json",
        OUT / "original-closure.json",
        *(BLIND / f"c{i}.json.gz" for i in range(3)),
        HAND.ALLOCATION,
        HAND.ALLOCATION.parents[1] / "allocation.json",
        HAND.ASSET,
        Q_DRIVER.dwell.inputs.expand("{D}/runtime-build.json"),
        Q_DRIVER.dwell.inputs.expand("{D}/scripts/graduation/g1_visibility_vision.py"),
        *(
            HAND.CALIBRATION / name
            for name in ("manifest.json", "panel-primary.npy", "panel-start.npy")
        ),
        output.resolve(),
    }

    def file_audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            p = Path(os.fsdecode(args[0])).resolve()
            if p.is_relative_to(ROOT / "experiments") and p not in resources:
                raise PermissionError(
                    "outside registered frame/encoder/handoff calibration allowlist"
                )

    sys.addaudithook(file_audit)
    for file in (
        OUT / "slot-key.json",
        BP / "native-01/b1/physical.jsonl.gz",
        BP_MIN / "inputs.json",
        BP_MIN.parent / "readback.minimal.primary.json",
        Q / "reduction.primary.json",
        Q / "native-01/q/native.json",
    ):
        try:
            file.open("rb").close()
        except PermissionError:
            continue
        raise ValueError("blind process acquired unblinding evidence")


def scoped_handoff(frame, marker, slot, model, maps, pose, reserve):
    scope = HAND.scope_for_math("RETREAT", slot, frame)
    q, dq, f, df = [
        np.asarray(scope[f"entry_{suffix}"])
        for suffix in (
            "joint_positions_rad",
            "joint_velocities_rad_s",
            "finger_positions_m",
            "finger_velocities_m_s",
        )
    ]
    (local,) = [p for p in model.object if p.name == "object_geom"]
    strict_floor = HAND.volume_callback(model, maps, False)
    center = marker.get("object_center_world_m")
    in_region = center is not None and np.all(
        abs(np.asarray(center)[:2] - model.region.c[:2]) <= model.region.h[:2]
    )
    optional_floor = HAND.volume_callback(model, maps, True) if in_region else None

    def invoke(volume):
        return gate.handoff_motion(
            frame,
            marker,
            scope,
            "RETREAT",
            "PRE",
            q,
            f,
            dq,
            df,
            None,
            None,
            model,
            optical=pose,
            volume_check=volume,
        )

    original_box_gap = gate.box_gap
    baseline_pairs = {}

    def trace(left, right):
        value = original_box_gap(left, right)
        baseline_pairs[(left.name, right.name)] = value
        return value

    with patch.object(gate, "box_gap", trace):
        baseline = invoke(strict_floor)
    if pose is None or PAIR not in baseline_pairs:
        return {
            "baseline": baseline,
            "modified_strict": baseline,
            "modified_conditional": None,
            "source_pose": pose,
            "six_directions": [],
            "selected_pair": None,
        }
    require(
        tuple(PLAN["pair"]) == PAIR
        and dict(
            zip(
                map(tuple, gate.profile()["stages"]["RETREAT"]["pairs"]),
                gate.profile()["stages"]["RETREAT"]["pair_closing_m"],
                strict=True,
            )
        )[PAIR]
        == reserve,
        "frozen pair reserve and target mapping changed",
    )
    diagnostics = []
    unchanged = {}

    def only_selected_pair(left, right):
        value = original_box_gap(left, right)
        if (left.name, right.name) != PAIR:
            unchanged[(left.name, right.name)] = value
            return value
        diagnostics.extend(lower_support(left, local, pose))
        directed = max(v["initial_gap_lower_m"] for v in diagnostics)
        require(directed < 2, "directional separation outside engine distance cap")
        return max(value, directed) if directed > 0 else value

    with patch.object(gate, "box_gap", only_selected_pair):
        strict = invoke(strict_floor)
        conditional = invoke(optional_floor) if optional_floor else None
    require(
        {k: v for k, v in baseline_pairs.items() if k != PAIR} == unchanged
        and len(diagnostics) in {6, 12},
        "other frozen OBB pairs or invocation counts changed",
    )
    if len(diagnostics) == 12:
        require(diagnostics[:6] == diagnostics[6:], "floor hypothesis changed pair projection")
    axes = diagnostics[:6]
    directed = max(x["initial_gap_lower_m"] for x in axes)
    original = baseline_pairs[PAIR]
    return {
        "baseline": baseline,
        "modified_strict": strict,
        "modified_conditional": conditional,
        "source_pose": pose,
        "six_directions": axes,
        "selected_pair": {
            "original_initial_lower_m": original,
            "robot_face_initial_lower_m": directed,
            "frozen_closing_reserve_m": reserve,
            "original_remaining_lower_m": original - reserve,
            "robot_face_remaining_lower_m": directed - reserve if directed > 0 else None,
            "stronger_proof_used": directed > max(original, 0),
        },
    }


def predict(output):
    restrict(output)
    manifest = BLIND / "seal.json"
    seal = read(manifest)
    require(
        seal["plan_sha256"] == sha(HERE / "plan.json")
        and seal["script_sha256"] == sha(Path(__file__).resolve())
        and seal["original_closure_audit_sha256"] == sha(OUT / "original-closure.json"),
        "sealed actionless prediction sources changed",
    )
    Q_DRIVER.verified_tree(BLIND, seal["members"])
    frozen = read(OUT / "original-closure.json")
    reserved = frozen["selected_pair_original_closing_m"]
    require(frozen["all_30_original_closing_values_exact"], "frozen closure audit failed")
    payload = read(BLIND / "inputs.json")
    EXACT(payload, "input")
    slots = payload["input"]
    require(len(slots) == 3, "unexpected experimental slots")
    measures = OPT.sealed_optics()
    model = HAND.Model(HAND.ASSET)
    maps = HAND.calibration_maps()
    results = {}
    for i, item in enumerate(slots):
        validate(item, i)
        bad = item | {"role": "DWELL-00"}
        require(OPT.rejected(validate, bad, i), "relabelled first dwell passed endpoint control")
        frame = Q_DRIVER.dwell.inputs.packet(BLIND / item["path"])
        robot = item["robot"]
        identity, config = READER.fixture(item["observable_reset"])
        marker = measures(frame, config)
        require(
            HAND.optical_check(frame, robot, marker, identity, config), "wrong current marker/clock"
        )
        fake = robot | {"frame_id": "other-exposure"}
        require(
            not HAND.optical_check(frame, fake, marker, identity, config),
            "foreign exposure passed frame binding",
        )
        pose = rigid_pose(
            frame, marker, config, identity=identity, physics_step=robot["physics_step"]
        )
        diagnostics = scoped_handoff(frame, marker, item, model, maps, pose, reserved)
        results[item["path"]] = diagnostics | {
            "source_role": item["role"],
            "tick": robot["physics_step"],
            "authorized": False,
        }
    store(
        output,
        {
            "seal_sha256": sha(manifest),
            "synthetic_controls": synthetic_controls(),
            "slots": results,
            "scope": "frozen stage entry necessary conditions only",
        },
    )


def native_initial_gap(terminal_row, model, analytic_box):
    # Reproduce the original distance query on detached geometry at the same true physical state.
    import mujoco

    asset = mujoco.MjModel.from_xml_path(str(HAND.ASSET))
    data = mujoco.MjData(asset)
    data.qpos[:9] = terminal_row["q"]
    center, rotation = terminal_row["geom"][PAIR[1]]
    center, rotation = np.asarray(center), np.asarray(rotation)
    (left_local,) = [p for p in model.object if p.name == PAIR[1]]
    address = int(asset.joint("object_free").qposadr[0])
    data.qpos[address : address + 3] = center - rotation @ left_local.c
    mujoco.mju_mat2Quat(data.qpos[address + 3 : address + 7], rotation.reshape(9))
    mujoco.mj_kinematics(asset, data)
    exact_boxes = []
    for name in PAIR:
        geom = data.geom(name)
        exact_boxes.append(
            Box(
                name, geom.xpos.copy(), asset.geom(name).size.copy(), geom.xmat.reshape(3, 3).copy()
            )
        )
    left_native, right_native = exact_boxes
    require(
        np.max(abs(left_native.c - analytic_box.c)) <= 1e-12
        and np.max(abs(left_native.r - analytic_box.r)) <= 1e-12
        and np.array_equal(left_native.h, analytic_box.h),
        "directional proof's known arm face axes did not bind to truth FK",
    )
    sat = box_gap(left_native, right_native)
    engine = mujoco.mj_geomDistance(
        asset, data, asset.geom(PAIR[0]).id, asset.geom(PAIR[1]).id, 2.0, None
    )
    return sat, engine, max(sat, 0.0) if engine == 0 else engine, right_native.corners()


def reduce(first, second, output):
    source_pins()
    require(first.read_bytes() == second.read_bytes(), "independent cold results differ")
    result = read(first)
    seal = read(BLIND / "seal.json")
    require(
        result["seal_sha256"] == sha(BLIND / "seal.json"), "sealed cold package identity differs"
    )
    Q_DRIVER.verified_tree(BLIND, seal["members"])
    key = read(OUT / "slot-key.json")
    original_bp = read(BP_MIN.parent / "readback.minimal.primary.json")["slots"]
    original_q = read(Q / "reduction.primary.json")["dwell"][-1]["handoff"]["strict"]
    original = {"B": original_bp["c1"]["strict"], "P": original_bp["c2"]["strict"], "Q": original_q}
    model = HAND.Model(HAND.ASSET)
    final = {}
    for picture, answer in result["slots"].items():
        binding = key[picture]
        name = binding["condition"]
        require(
            binding["tick"] == answer["tick"]
            and binding["role"] == answer["source_role"]
            and original[name] == answer["baseline"],
            "baseline-vs-new source scope differs",
        )
        if answer["source_pose"] is None:
            require(
                name == "B" and answer["baseline"]["reason"] == "no_current_handoff_pose_interval",
                "scheduled missing-pose negative changed",
            )
            final[name] = answer | {"true_corner_coverage": None}
            continue
        file = ROOT / binding["archive"] / "physical.jsonl.gz"
        with gzip.open(file, "rt") as stream:
            row = next(json.loads(line) for n, line in enumerate(stream) if n == answer["tick"])
        require(row["tick"] == answer["tick"], "wrong independent truth tick")
        m = gate.geometry(model)
        center, orientation = row["geom"][PAIR[1]]
        centers, rotations, _, _ = m.solids(
            np.asarray(row["q"][:7])[None],
            np.asarray(row["q"][7:9])[None],
            np.asarray(center)[None],
            np.asarray(orientation)[None],
        )
        left = m.names.index(PAIR[0])
        located = Box(PAIR[0], centers[0, left], m.sizes[left], rotations[0, left])
        sat, engine, blended, corners = native_initial_gap(row, model, located)
        check_correspondence(corners, answer["six_directions"], name)
        bound = answer["selected_pair"]["robot_face_initial_lower_m"]
        require(
            bound <= sat + 1e-12 and (bound <= 0 or bound <= blended + 1e-12),
            "proposed initial gap not covered by real entry geometry",
        )
        final[name] = answer | {
            "true_corner_coverage": True,
            "independent_initial_truth_m": {
                "sat": sat,
                "engine": engine,
                "frozen_hybrid_definition": blended,
            },
        }
    store(
        output,
        {
            "capture_unchanged": True,
            "historical_closure": read(OUT / "original-closure.json"),
            "source_blind_primary_sha256": sha(first),
            "source_blind_cold_sha256": sha(second),
            "results": final,
            "new_retreat_evidence_is_initial_only": True,
            "actual_retreat": 0,
            "phys_steps": 0,
            "exposures": 0,
            "whole": 0,
            "formal_trials": 0,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "predict", "reduce"))
    parser.add_argument("paths", type=Path, nargs="*")
    args = parser.parse_args()
    Q_DRIVER.cv2.setNumThreads(1)
    globals()[args.mode](*args.paths)


if __name__ == "__main__":
    main()
