"""Verify that frozen source-profile growth leaves archived free-lift checks intact."""

import argparse
from pathlib import Path

import numpy as np
from precheck_expansion import PANDA, require, source, volume_check
from read_refit_stops import OUT, frame_sources, gate_source, load_optics, profiles
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import PayloadClearance
from scripts.graduation.perception_io import pinned, read, sha, write


def scoped(guard, robot, evidence, views):
    return guard.check(
        "LIFT",
        np.array(robot["joint_positions_rad"]),
        np.array(robot["finger_positions_m"]),
        np.array(robot["joint_velocities_rad_s"]),
        np.array(robot["finger_velocities_m_s"]),
        robot["handoff"],
        evidence["payload_observation"],
        volume_check(guard.motion.model, views, {}),
        allow_grasp_station_contact=False,
        native_target=np.array(evidence["commanded_target_xyz_m"]),
    )


def verify(reader, cases):
    seal = read(OUT / "fit/fit-seal.json")
    candidate = pinned(OUT / "fit/candidate-profile.json", seal["profile_sha256"])
    require(seal["ready_for_challenge"], "source refit did not qualify for sealed checks")
    motion = MotionGeometry(Model(source("runtime/" + PANDA)))
    old_source, payload = profiles()
    old = PayloadClearance(motion, payload, old_source)
    new = PayloadClearance(motion, payload, candidate)
    reg, views = load_optics()
    results = {}
    for case in cases:
        frames = frame_sources(case)
        passed = []
        aborts = []
        handoff = []
        for tick, item in frames.items():
            e = item[1]
            if e["status"] != "CLEAR":
                aborts.append(
                    {
                        "tick": tick,
                        "status": e["status"],
                        "reason": e["reason"],
                        "native_rejection_kept": True,
                    }
                )
                continue
            if e["short_motion"].get("plan") == "continuous_native_handoff":
                handoff.append(tick)
                continue
            if e.get("source_table_support", {}).get("qualified"):
                continue
            robot, e = gate_source(case, tick, item, reg)
            A = scoped(old, robot, e, views)
            B = scoped(new, robot, e, views)
            require(
                A == B
                and A["reason"] == e["short_motion"]["reason"]
                and A["limiting_pair"] == e["short_motion"]["limiting_pair"]
                and abs(A["minimum_gap_m"] - e["short_motion"]["minimum_gap_m"]) <= 1e-12,
                f"generic envelope differs at {case} / {tick}",
            )
            passed.append(tick)
        results[case] = {
            "verified_generic_ticks": passed,
            "independent_handoff_ticks": handoff,
            "original_rejections": aborts,
        }
    write(
        OUT / f"scope-{reader}.json",
        {
            "profile_sha256": seal["profile_sha256"],
            "results": results,
            "new_exposures": 0,
            "code_sha256": sha(Path(__file__)),
            "not_replayed_live_handoff_or_unknown_surface": True,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reader", choices=("reader-1", "reader-2"))
    p.add_argument("--after-challenge", action="store_true")
    ns = p.parse_args()
    if ns.after_challenge:
        require((OUT / "challenge/grid02/seal.json").is_file(), "challenge has not been acquired")
    verify(ns.reader, ("grid04", "t01", "grid02") if ns.after_challenge else ("grid04", "t01"))
