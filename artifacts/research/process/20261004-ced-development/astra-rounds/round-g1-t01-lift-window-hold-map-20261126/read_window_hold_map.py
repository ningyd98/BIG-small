"""Seal encoder-only HOLD predictions and compare with archived stop labels."""

import argparse
import itertools
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.g1_clearance_score import verify_generation
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import ROOT, pinned, read, sha, write

from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD

HERE = Path(__file__).resolve().parent
REPO = next(path for path in HERE.parents if (path / ".git").exists())
PLAN = read(HERE / "plan.json")
RAW = REPO / PLAN["instance"]
OUT = REPO / PLAN["output"]
BEGIN, LAST = 1632, 1840
BODY = "g1_dual_id8_plate"
POINTS = np.array(list(itertools.product((-1.0, 1.0), repeat=3)))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def inputs():
    require(ROOT == (REPO / PLAN["runtime"]).resolve(), "wrong frozen imports")
    verify_generation(ROOT, PLAN["sha256"][PLAN["runtime"] + "/runtime-build.json"])
    for name, expected in PLAN["sha256"].items():
        require(sha(REPO / name) == expected, "input drift: " + name)
    receipt = read(RAW / "receipt.json")
    alloc = pinned(RAW.parent / "allocation.json", receipt["allocation_sha256"])
    asset = ROOT / alloc["case"]["asset_path"]
    require(sha(asset) == alloc["asset_sha256"], "wrong assembly")
    return receipt, alloc, asset


def rotations(model, geom, alloc):
    box = next(box for box in geom.object if box.name == BODY)
    nominal_wrist = np.empty(9)
    mujoco.mju_quat2Mat(nominal_wrist, np.asarray(_DOWNWARD, dtype=float))
    nominal_wrist = nominal_wrist.reshape(3, 3)
    yaw = alloc["case"]["yaw_rad"]
    r = np.array([[np.cos(yaw), -np.sin(yaw), 0], [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    obj_tcp = np.asarray(alloc["geometry"]["object_to_tcp"]).reshape(4, 4)
    require(np.array_equal(obj_tcp[:3, :3], np.eye(3)), "changed nominal object-to-tool mount")
    require(model.nv == 15 and int(model.joint("object_free").dofadr[0]) == 9, "wrong rigid model")
    return ((POINTS * box.h @ box.r.T + box.c - obj_tcp[:3, 3]) @ r.T) @ nominal_wrist


def predictions(alloc, asset):
    model = mujoco.MjModel.from_xml_path(str(asset))
    geom = Model(asset)
    data = mujoco.MjData(model)
    relative = rotations(model, geom, alloc)
    source = read(RAW.parent / "lift-qualification-trace.json")
    witness = read(REPO / PLAN["witness"])
    receipt_by_tick = {row["physics_step"]: row for row in witness["states"]}
    commands = {r["physics_step"]: r for r in source["before_integrations"]}
    local = {
        row["frame_id"]: row
        for row in read(RAW / "local-clearance.json")["rows"]
        if row["skill"] == "LIFT" and row["phase"] == "FEEDBACK"
    }
    gains = model.actuator_gainprm[:7, 0]
    low, high = model.actuator_ctrlrange[:7].T
    p, r = np.zeros((3, model.nv)), np.zeros((3, model.nv))
    mass = np.empty((model.nv, model.nv))
    found = []
    for frame in source["frames"]:
        if frame["phase"] != "FEEDBACK" or frame["status"] != "CLEAR":
            continue
        stamp = frame["state"]["physics_step"]
        values = receipt_by_tick[stamp]
        robot = local[frame["frame_id"]]["robot"]
        require(robot["physics_step"] == stamp, "old exact exposure identity differs")
        data.qpos[:7] = values["qr"]
        data.qpos[7:9] = robot["finger_positions_m"]
        mujoco.mj_kinematics(model, data)
        mujoco.mj_comPos(model, data)
        mujoco.mj_jacSite(model, data, p, r, model.site("tcp").id)
        q = data.qpos[:7]
        state = commands[stamp]
        qfrc_bias = np.asarray(values["bias"])
        retained = np.clip(
            q + np.clip(np.asarray(state["arm_target"]) - q, -0.1, 0.1) + qfrc_bias / gains,
            low,
            high,
        )
        hold = np.clip(q + qfrc_bias / gains, low, high)
        require(np.array_equal(retained, state["ctrl"][:7]), "input retained CTRL not reproduced")
        delta_tau = gains * (retained - hold)
        mujoco.mj_fullM(model, mass, np.asarray(values["qM"]))
        dd = np.linalg.solve(mass[:9, :9], np.r_[delta_tau, 0.0, 0.0])
        corners = relative @ data.site("tcp").xmat.reshape(3, 3).T
        loss = (p[:, :9] @ dd + np.cross(r[:, :9] @ dd, corners))[:, 2]
        dq = np.r_[values["dq"], robot["finger_velocities_m_s"]]
        vz = (p[:, :9] @ dq + np.cross(r[:, :9] @ dq, corners))[:, 2]
        worst = int(loss.argmax())
        found.append(
            {
                "step": stamp,
                "handoff_entry_dispatch": stamp == BEGIN,
                "group": ((stamp - 1640) // 8) % 2 if stamp > BEGIN else None,
                "predicted_worst_corner": worst,
                "predicted_down_acceleration_loss_m_s2": float(loss[worst]),
                "incoming_down_speed_at_same_corner_m_s": float(-vz[worst]),
                "predicted_TCP_down_acceleration_loss_m_s2": float((p[:, :9] @ dd)[2]),
                "retained_minus_hold_tau_nm": delta_tau.tolist(),
                "original_motion_class": frame["motion"].get("speed_class"),
                "published_source_class": frame["motion"].get("registered_source_speed_class"),
            }
        )
    require(
        [row["step"] for row in found] == list(range(BEGIN, LAST + 1, 8)), "missing source window"
    )
    require(
        found[-1]["predicted_down_acceleration_loss_m_s2"] > 0
        and found[-1]["predicted_TCP_down_acceleration_loss_m_s2"] > 0,
        "directional anchor falsifies the registered predictor",
    )
    return found


def stop_label(motion, path, allowance, row):
    with np.load(path, allow_pickle=False) as stop:
        q, dq, pairs, counts = stop["q"], stop["qvel"], stop["pair_names"], stop["contact_counts"]
    require(q.shape == (241, 16), "incomplete archived native stop")
    v, vdot, rel, rdot = snapshot(motion, q, dq, q[:, 9:12], object_matrix(q))
    _, _, tcp, _ = motion.solids(q[:, :7], q[:, 7:9], q[:, 9:12], object_matrix(q))
    j = motion.names.index(BODY)
    delta = v[:, j, :, 2] - v[0, j, :, 2]
    i0, corner = np.unravel_index(delta.argmin(), delta.shape)
    world = positive_support(v, vdot, v[0], AXES)
    baseline, allowable, different = allowance
    relative = positive_support(rel, rdot, rel[0], different)
    table = np.zeros(241, dtype=bool)
    contacts = pairs.tolist()
    table_pair = ["object_geom", "table"]
    if table_pair in contacts:
        table = counts[:, contacts.index(table_pair)] > 0
    first = np.flatnonzero(table)
    clearance = {
        "maximum_ID8_downward_m": float(world[j, 5]),
        "worst_actual_endpoint_m": float(-delta[i0, corner]),
        "worst_actual_endpoint_tick": int(i0),
        "worst_corner": int(corner),
        "first_table_contact_stop_tick": int(first[0]) if first.size else None,
        "initial_table_contact": bool(table[0]),
        "samples": [
            {
                "offset": t,
                "tcp_delta_z_m": float(tcp[t, 2] - tcp[0, 2]),
                "load_delta_z_m": float(q[t, 11] - q[0, 11]),
                "corner_delta_z_m": delta[t].tolist(),
                "active_contact_pairs": [p for p, n in zip(contacts, counts[t], strict=True) if n],
            }
            for t in (0, 1, 8, 25, 240, int(i0))
        ],
    }
    if row["handoff_entry_dispatch"]:
        clearance.update(status="SEPARATE_HANDOFF", fixed_source_margin_m=None)
    else:
        clearance.update(
            fixed_source_margin_m=float((baseline - world).min()),
            generic_world_margin_m=float((allowable["world"] - world).min()),
            generic_relative_margin_m=float((allowable["relative"] - relative).min()),
            status=(
                "OVER_CAP"
                if min(
                    (baseline - world).min(),
                    (allowable["world"] - world).min(),
                    (allowable["relative"] - relative).min(),
                )
                < 0
                else "WITHIN_CAP"
            ),
        )
    return clearance


def score(asset, predicted):
    directory = REPO / PLAN["stop_index"]
    ledger = read(directory)
    geom = MotionGeometry(Model(asset))
    profile_root = ROOT / "scripts/graduation"
    from scripts.graduation.g1_complete_cv_payload import PayloadClearance

    guard = PayloadClearance(
        geom,
        read(profile_root / "g1_complete_cv_payload_profile.json"),
        read(profile_root / "g1_complete_cv_source_motion_profile.json"),
    )
    source = guard.source_classes["0.075"][0]
    generic = guard.data["LIFT"]["classes"]["0.075"]
    rows = []
    groups = [[], []]
    for entry in predicted:
        step = entry["step"]
        name = f"{step}-{'entry_dispatch' if step == BEGIN else 'after_integration'}.npz"
        path = directory.parent / name
        require(sha(path) == ledger["branches"][name], f"changed archived branch: {name}")
        matching = [m for m in ledger["checks"] if m["window"] == step and m["delay"] == 0]
        require(
            len(matching) == 1 and matching[0]["forbidden"] is None, "unexpected contact ledger"
        )
        label = stop_label(geom, path, (source, generic, guard.axes), entry)
        if step != BEGIN:
            old_margin = matching[0]["margins"]["world"]["margin_m"]
            require(
                abs(label["fixed_source_margin_m"] - old_margin) < 1e-12,
                f"source envelope differs at {step}",
            )
        row = {**entry, **label}
        rows.append(row)
        if row["group"] is not None:
            groups[row["group"]].append(row)
    require(
        rows[-1]["status"] == "OVER_CAP"
        and abs(rows[-1]["maximum_ID8_downward_m"] - 0.002777251732861987) < 1e-12,
        "old 1840 challenge not reproduced",
    )
    counterexamples = []
    for x in rows[1:]:
        for y in rows[1:]:
            comparable = (
                x["initial_table_contact"] == y["initial_table_contact"]
                and x["published_source_class"] == y["published_source_class"]
                and x["original_motion_class"] == y["original_motion_class"]
            )
            if (
                comparable
                and x["status"] == "OVER_CAP"
                and y["status"] == "WITHIN_CAP"
                and (
                    x["predicted_down_acceleration_loss_m_s2"]
                    <= y["predicted_down_acceleration_loss_m_s2"]
                    and x["incoming_down_speed_at_same_corner_m_s"]
                    <= y["incoming_down_speed_at_same_corner_m_s"]
                )
            ):
                counterexamples.append((x["step"], y["step"]))
    coverage = [
        {
            "passes": sum(r["status"] == "WITHIN_CAP" for r in group),
            "rejections": sum(r["status"] == "OVER_CAP" for r in group),
        }
        for group in groups
    ]
    return {
        "rows": rows,
        "alternating_groups": coverage,
        "comparable_pass_fail_dominance_counterexamples": counterexamples,
        "progress_candidate_admitted": False,
        "minimum_required_mixed_group_support": all(
            g["passes"] and g["rejections"] for g in coverage
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("predict", "score"))
    parser.add_argument("reader", choices=("reader-1", "reader-2"))
    args = parser.parse_args()
    _, alloc, asset = inputs()
    OUT.mkdir(exist_ok=True)
    info = {"plan_sha256": sha(HERE / "plan.json"), "source_sha256": sha(Path(__file__))}
    path = OUT / f"{args.reader}.predictions.json"
    if args.mode == "predict":
        write(path, dict(info, result=predictions(alloc, asset)))
    else:
        manifest = read(OUT / "sealed-predictions.json")
        data = pinned(path, manifest[path.name])
        require(all(data[name] == digest for name, digest in info.items()), "prediction seal drift")
        write(OUT / f"{args.reader}.result.json", dict(info, result=score(asset, data["result"])))


if __name__ == "__main__":
    main()
