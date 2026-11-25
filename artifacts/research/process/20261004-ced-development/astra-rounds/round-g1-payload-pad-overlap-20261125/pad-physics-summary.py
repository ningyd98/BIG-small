"""Cold-read physical fit artifacts and align transport exposure poses and native force peaks."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
RAW = Path("experiments/results/g1-payload-pad-overlap-20261125/fit-pad-physics-01")
FITS = ("dense-fit-01","dense-fit-02","dense-fit-03")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def matrix(wxyz):
    w,x,y,z=np.array(wxyz)/np.linalg.norm(wxyz)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def measured_relative(source):
    index=read(source/"rgbd-index.json")["rows"]
    truth={r["frame_id"]:r for r in read(source/"offline-physics.json")["frame_labels"]}
    states={}
    for row in index:
        if sha(source/row["file"])!=row["file_sha256"]:
            raise ValueError("original pixel bytes differ from exposure index")
        if row["skill"]!="MOVE_TO_REGION":
            continue
        robot=row["robot"]
        object_pose=truth[robot["frame_id"]]
        hand=matrix(robot["tcp_quaternion_wxyz"])
        pos=hand.T@(np.asarray(object_pose["center_m"])-robot["tcp_position_m"])
        rot=hand.T@np.asarray(object_pose["rotation"])
        step=robot["physics_step"]
        if step in states:
            np.testing.assert_array_equal(states[step][0],pos)
            np.testing.assert_array_equal(states[step][1],rot)
        states[step]=(pos,rot)
    ticks=sorted(states)
    ref,ref_rot=states[ticks[0]]
    translation=[float(np.linalg.norm(states[t][0]-ref)) for t in ticks]
    angle=[float(np.degrees(np.arccos(np.clip((np.trace(ref_rot.T@states[t][1])-1)/2,-1,1)))) for t in ticks]
    return {"archived_pixel_files_verified":len(index),"unique_transport_exposure_steps":len(ticks),
            "maximum_measured_relative_translation_m":max(translation),
            "step_max_translation":ticks[int(np.argmax(translation))],"maximum_measured_relative_rotation_deg":max(angle),
            "step_max_rotation":ticks[int(np.argmax(angle))]}


def summary(root):
    bindings = {p.relative_to(root).as_posix():sha(p) for p in
                (HERE/"plan.json", HERE/"plan.md", HERE/"pad-physics-replay.py", HERE/"pad-physics-wrench.py", Path(__file__))}
    rows={}
    for name in FITS:
        d=root/RAW/name
        report=read(d/"replay.json")
        wrench=read(d/"wrench-summary.json")
        for source in ("transport-contact-manifolds.json.gz", "transport-contact-wrenches.json.gz",
                       "replay.json", "wrench-summary.json"):
            f=d/source
            bindings[f.relative_to(root).as_posix()]=sha(f)
        assert wrench["replay_sha256"]==sha(d/"replay.json")
        assert report["archive_sha256"]==sha(d/"transport-contact-manifolds.json.gz")
        assert wrench["wrenches_sha256"]==sha(d/"transport-contact-wrenches.json.gz")
        for k,h in report["source_hash"].items():
            f=root/report["source_dir"]/k
            if sha(f)!=h:
                raise ValueError("input no longer matches existing native replay")
            bindings[f.relative_to(root).as_posix()]=h
        actual=wrench["trigger"]
        assert any(e[1]==report["trigger_frame"] for e in actual["exposures"])
        assert all(e==0 for e in report["max_abs_errors"].values())
        assert report["transport_samples"]==wrench["transport"]["bilateral_positive_steps"]==1081
        rows[name]={
            "trigger_frame_id":report["trigger_frame"], "trigger_step":report["trigger_step"], "first_refusal_measured":actual,
            "whole_transport":wrench["transport"], "before_first_refusal":wrench["before_trigger"],
            "after_first_refusal":wrench["after_trigger"], "actual_motion":measured_relative(root/report["source_dir"]),
            "timing_range_steps":report["transport_range"], "max_original_replay_errors":report["max_abs_errors"],
            "physical_ticks_compared":report["dense_ticks"], "original_frames_matched":report["same_frame_checks"],
            "original_commands_matched":report["command_count"],
        }
    return {"schema":"g1.payload.pad.physical-fit-01", "cases":rows, "bindings":bindings,
            "fitting_courses":3,"total_dense_ticks_verified":sum(x["physical_ticks_compared"] for x in rows.values()),
            "total_captured_frames_verified":sum(x["original_frames_matched"] for x in rows.values()),
            "total_original_commands_verified":sum(x["original_commands_matched"] for x in rows.values()),
            "transport_states_with_two_positive_pads":sum(x["whole_transport"]["bilateral_positive_steps"] for x in rows.values()),
            "original_holdout_raw_opened":0, "new_action_dispatches":0, "formal":0, "hardware":0,
            "scope":"Original 9ed source command replay and recorded images from three fitting courses. True pad contacts, forces and gravity wrench capacity are offline labels. No unseen optical, preload, dynamic stopping or hardware eligibility certified."}


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--root",required=True,type=Path)
    a.add_argument("--verify",action="store_true")
    args=a.parse_args()
    v=summary(args.root.resolve())
    p=HERE/"pad-physics-fit-results.public.json"
    if args.verify:
        if v!=read(p):
            raise ValueError("cold read differs from sealed summary")
    else:
        with p.open("x") as f:
            json.dump(v,f,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)
            f.write("\n")
    print(v["total_dense_ticks_verified"],v["total_captured_frames_verified"],len(v["bindings"]),sha(p))
