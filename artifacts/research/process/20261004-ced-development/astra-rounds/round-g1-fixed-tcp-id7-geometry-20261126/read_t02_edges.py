"""Read the unchanged opposite-edge predicates on three original t02 exposures."""
import json
from pathlib import Path
import sys

import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation import g1_complete_cv_handoff_optics as optics
from scripts.graduation.perception_io import sha

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "round-g1-continuous-payload-observation-20261125"))
from read_dense_payload import SOURCE
from read_pose_coverage import native_marker

SOURCE_SHA = "82fd17f15c8e9e5714603c72aaa4f4813cf7bcb4e8b27fb85772736d781ba873"
ORIGINAL = Path("experiments/results/g1-complete-cv-repair-20261125/batches/train-full-04/cvfix-t02")


def read_edges():
    import inspect

    plan = json.loads((HERE / "plan.json").read_bytes())
    t02 = Path(plan["roots"]["t02"])
    index_path = t02 / "pixel-index.json"
    assert sha(index_path) == plan["sha256"]["{t02}/pixel-index.json"]
    assert sha(Path(optics.__file__)) == SOURCE_SHA
    allocation = ORIGINAL / "allocation.json"
    assert sha(allocation) == "b39063b55558a4369e069646cfbacfc3385083d39a746722d13b55d892064af0"
    geometry = json.loads(allocation.read_bytes())["geometry"]
    index = json.loads(index_path.read_bytes())
    detector, marker_sha = native_marker(SOURCE)
    func = optics._opposite_edges
    source, offset = inspect.getsourcelines(func)
    before_color = offset + next(i for i, text in enumerate(source) if "match &= (fg - bg" in text)
    outputs = []
    for row in index["frames"]:
        if row["label"] != "LIFT/feedback" or row["physics_step"] not in (1504,1512,1520):
            continue
        file = t02 / row["file"]
        assert sha(file) == row["file_sha256"]
        frame = RGBDObservation.model_validate_json(file.read_bytes())
        assert frame.frame_id == row["frame_id"] and frame.checksum_sha256 == row["checksum_sha256"]
        marker = detector(frame,geometry)
        sides = []

        def observe(call, event, _arg):
            if event == "line" and call.f_lineno == before_color:
                state = call.f_locals
                depth = state["match"]
                contrast = (state["fg"]-state["bg"] > 22) & (state["last"]-state["first"] > 9)
                columns = state["ux"][(depth & contrast).sum(axis=1) == 1]
                sides.append({"side":state["side"], "depth_columns":int(np.count_nonzero(depth.any(1))),
                              "unique_depth_color_columns":int(columns.size),
                              "unique_column_span_px":int(np.ptp(columns)) if columns.size else 0})
            return observe

        def trace(call, event, arg):
            return observe if event == "call" and call.f_code is func.__code__ else None

        base = optics.measured_pose(frame,marker,geometry)
        previous_trace = sys.gettrace()
        try:
            sys.settrace(trace)
            traced = optics.measured_pose(frame,marker,geometry)
        finally:
            sys.settrace(previous_trace)
        assert traced == base and len(sides) == 2
        outputs.append({"step":row["physics_step"],"frame_id":frame.frame_id,"file_sha256":row["file_sha256"],
                        "method":base["method"],"usable_ids":marker["usable_ids"],"sides":sides})
    assert [r["step"] for r in outputs] == [1504,1512,1520]
    return {"optics_sha256":SOURCE_SHA,"marker_sha256":marker_sha,"runtime_sha256":SOURCE,
            "allocation_sha256":sha(ORIGINAL/"allocation.json"),"frames":outputs}


if __name__ == "__main__":
    with Path(sys.argv[1]).open("x") as out:
        json.dump(read_edges(),out,sort_keys=True,indent=2,allow_nan=False)
        out.write("\n")
