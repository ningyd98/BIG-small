"""Recompute physical reserves from sealed grid-04 states after CPU capture."""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
from screen_braking import ASSET, ENTRY, OUT, PLAN, ROOT
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    AXES,
    PayloadClearance,
    object_matrix,
    positive_support,
    snapshot,
)
from scripts.graduation.perception_io import read, sha, write


def require(valid, message):
    if not valid:
        raise ValueError(message)


def read_run(folder):
    path = folder / "interchange.json"
    data = read(path)
    signal = data["result"]
    samples = read(folder / "candidate-trace.json")
    basis = {r["tick"]: r for r in samples}
    require(list(basis) == list(range(ENTRY, ENTRY + len(samples))), "trace is not consecutive")
    count = signal["stop_count"]
    total_motion = signal["last_step"] - ENTRY
    require(
        signal["steps"] == 2112 + total_motion + 240 * count
        and signal["steps"] <= PLAN["budget"]["maximum_CPU_ticks"],
        "integration receipt differs from the sealed timeline",
    )
    return signal, samples, basis, data["stops"]


def independent(folder, reader):
    from screen_braking import FINGER_CONTACTS, ROOTS, TABLE_CONTACT, verify_inputs

    verify_inputs()
    signal, samples, basis, stops = read_run(folder)
    guard = PayloadClearance(
        MotionGeometry(Model(ASSET)),
        read(ROOT / "scripts/graduation/g1_complete_cv_payload_profile.json"),
        read(ROOT / "scripts/graduation/g1_complete_cv_source_motion_profile.json"),
    )
    gates = {
        v["step"]: v["current"]["short_motion"]
        for v in read(ROOTS["case"] / "clearance-gate.json")["checks"]
        if v["skill"] == "LIFT" and v["phase"] == "FEEDBACK" and v["status"] == "CLEAR"
    }
    triggers = defaultdict(list)
    for result in stops:
        triggers[result["stop_tick"]].append(result)
    require(
        len(triggers) == signal["stop_count"] == len(list((folder / "stops").glob("*.npz"))),
        "raw stop branch count differs",
    )
    used = ["baseline.json", "preflight.json", "candidate-trace.json", "interchange.json"]
    for tick, checks in triggers.items():
        record = folder / "stops" / f"stop-{tick}.npz"
        pairs = folder / "stops" / f"stop-{tick}.json"
        used.extend(str(f.relative_to(folder)) for f in (record, pairs))
        contacts = [set(map(tuple, c)) for c in read(pairs)]
        with np.load(record, allow_pickle=False) as f:
            q, dq = f["q"], f["dq"]
        require(
            q.shape == (241, 16)
            and dq.shape == (241, 15)
            and np.isfinite(q).all()
            and np.isfinite(dq).all()
            and np.array_equal(q[0], basis[tick]["q"])
            and np.array_equal(dq[0], basis[tick]["dq"])
            and len(contacts) == 241,
            "stop branch broke the phase or data contract",
        )
        points, velocities, relative, relative_velocities = snapshot(
            guard.motion, q, dq, q[:, 9:12], object_matrix(q)
        )
        for result in checks:
            now = result["feedback_tick"]
            require(0 <= tick - now <= 8, "stop does not belong to the original window")
            phase = gates[now]
            q0 = np.asarray(basis[now]["q"])[None]
            dq0 = np.asarray(basis[now]["dq"])[None]
            xyz, _, rel, _ = snapshot(guard.motion, q0, dq0, q0[:, 9:12], object_matrix(q0))
            reference = guard.data["LIFT"]["classes"][phase["speed_class"]]
            source = phase.get("registered_source_speed_class")
            world = reference["world"] if source is None else guard.source_classes[source][0]
            w = world - positive_support(points, velocities, xyz[0], AXES)
            r = reference["relative"] - positive_support(
                relative, relative_velocities, rel[0], guard.axes
            )
            allowed = FINGER_CONTACTS | ({TABLE_CONTACT} if source is not None else set())
            fault = next(
                (i for i, c in enumerate(contacts) if not FINGER_CONTACTS <= c <= allowed), None
            )
            require(
                result["worst_world_margin_m"] == float(w.min())
                and result["worst_relative_margin_m"] == float(r.min())
                and result["first_invalid_contact"] == fault,
                "independent geometry did not reproduce the stop receipt",
            )
    p0, p1 = samples[0], samples[-1]
    tcp = np.array([x["tcp_m"] for x in samples])
    cube = np.array([x["cube_m"] for x in samples])
    record = {
        "baseline": read(folder / "baseline.json"),
        "candidate": read(folder / "preflight.json"),
        "result": signal,
        "halt_stop": stops[-1] if stops and signal["status"] == "CPU_STOPPED" else None,
        "total_stop_checks": len(stops),
        "all_file_sha256": {name: sha(folder / name) for name in sorted(used)},
        "max_lateral_m": float(np.linalg.norm(tcp[:, :2] - tcp[0, :2], axis=1).max()),
        "end_cube_lift_m": p1["cube_m"][2] - p0["cube_m"][2],
        "end_TCP_lift_m": p1["tcp_m"][2] - p0["tcp_m"][2],
        "max_cube_lift_m": float((cube[:, 2] - cube[0, 2]).max()),
        "program_sha256": sha(Path(__file__)),
    }
    write(folder / f"{reader}.json", record)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("attempt", choices=("cpu-02",))
    cli.add_argument("reader", choices=("reader-1", "reader-2"))
    options = cli.parse_args()
    independent(OUT / options.attempt, options.reader)
