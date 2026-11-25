"""Confirm candidate-specific owner PLACE height and compare the identical incoming LIFT."""

import argparse
from pathlib import Path

import numpy as np

import physics_selection_study as s


def run(root, phase, names):
    dest = root / s.RAW
    out = dest / "owner-registered-physics"
    out.mkdir(exist_ok=True)
    anchor = out / "prefix"
    if not anchor.exists():
        try:
            anchor.symlink_to("../prefix", target_is_directory=True)
        except FileExistsError:
            pass
    eng = s.native_engine(root)
    original = eng.native.execute
    eligible = s.allowed(root, dest, phase, names)
    geom = s.geometry(root)
    np.testing.assert_allclose(geom["region_world_m"], [.2, .25, .004], atol=0, rtol=0)
    assert geom["support_height_m"] == 0
    for name in names:
        measured = s.read(dest / "prefix" / name / "measured-input.json")
        eng.target = lambda center, candidate: s.object_target(center, measured["rotation"], candidate)
        for cid in eligible:
            prior = dest / "courses" / name / cid
            checked = out / "labels" / name / (cid + ".json")
            if checked.exists():
                continue
            prior_result = s.read(prior / "result.json")
            pre_lift_failure = "MOVE_TO_REGION" not in [v["stage"] for v in prior_result["actions"]]
            selected = prior_result["actual_approach_target"]
            z = geom["region_world_m"][2]+selected[2]-geom["support_height_m"]
            if pre_lift_failure:
                s.write(checked, {
                    "case": name, "candidate": cid, "correct_place_m": z, "actual_suffix": False,
                    "complete_settled_240": False, "incoming_lift_stop": prior_result["terminal_error"],
                    "prior_sha256": s.sha(prior / "result.json"), "native_source": s.sha(Path(__file__)),
                })
                continue
            def per_candidate(robot, backend, skill, aim, task):
                if skill in ("MOVE_TO_REGION", "PLACE"):
                    aim = selected
                return original(robot, backend, skill, aim, task)
            eng.native.execute = per_candidate
            eng.simulate(root, out, name, [cid])
            other = out / "courses" / name / cid
            result = s.read(other / "result.json")
            with np.load(prior/"series.npz") as a, np.load(other/"series.npz") as b:
                n = int(np.flatnonzero(a["stage"] == "MOVE_TO_REGION")[0])
                if n != int(np.flatnonzero(b["stage"] == "MOVE_TO_REGION")[0]):
                    raise ValueError("physical LIFT source clock changed")
                for key in ("q", "qvel", "ctrl", "command_q", "contacts" if "contacts" in a else "contact_count", "forces"):
                    np.testing.assert_array_equal(a[key][:n], b[key][:n])
                fi = np.flatnonzero(b["stage"] == "FINAL_OBSERVATION")
                may = len(fi) == 240 and np.all(b["contact_count"][fi, 2] > 0)
                if may:
                    vv = b["qvel"][fi]
                    safe = np.all(abs(b["cube_corners_world"][fi,:,:2]-[.2,.25]) < [.08,.08])
                    may = safe and np.max(np.linalg.norm(vv[:,9:12],axis=1))<.01 and np.max(np.linalg.norm(vv[:,12:15],axis=1))<.1
            clock = result["source_return_step"]
            timely = True
            for action in result["actions"]:
                timely &= (action["end"] - clock) / 240 <= (1 if action["stage"] in ("GRASP","RELEASE") else 8)
                clock = action["end"]
            s.write(checked, {
                "case": name, "candidate": cid, "correct_place_m": z, "actual_suffix": True,
                "complete_settled_240": bool(result["eligible"] and may and timely),
                "lateral_peak_m": result["lift_peak_lateral_m"], "forbidden": result["actual_structure_contact_steps"],
                "identical_prefix_ticks": n, "prior_sha256": s.sha(prior/"result.json"),
                "owner_course_sha256": s.sha(other/"result.json"), "native_source": s.sha(Path(__file__)),
            })


if __name__ == "__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--root",required=True,type=Path)
    a.add_argument("--phase",required=True,choices=("center-fit","tangent-fit","blind"))
    a.add_argument("--case",action="append",required=True)
    args=a.parse_args()
    run(args.root.resolve(),args.phase,args.case)
