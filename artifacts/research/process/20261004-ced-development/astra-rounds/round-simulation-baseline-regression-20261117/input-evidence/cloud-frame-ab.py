import base64, datetime, json, subprocess, sys, types
from pathlib import Path
import numpy as np
from cloud_edge_robot_arm.vision import tracking
from cloud_edge_robot_arm.vision.observations import RGBDObservation

root = Path("experiments/results/phase9/grasp-place-repair-20261117/baseline-cloud/test_actual_worker_cloud_image0/worker-run")
ev = json.loads((root / "planning/planning-stage-02.json").read_text())["attempts"][0]["draft"]["observation_evidence"]
previous = types.ModuleType("previous_tracking")
previous.__file__ = tracking.__file__
src = subprocess.check_output(["git", "show", "57c4dc0d^:src/cloud_edge_robot_arm/vision/tracking.py"])
exec(compile(src, "57c4dc0d-parent/tracking.py", "exec"), previous.__dict__)
for folder in (root / "before", root / "component/frames/post-cloud"):
    meta = json.loads((folder / "observation.json").read_text())
    values = {k: meta[k] for k in RGBDObservation.model_fields if k in meta}
    for field, name in (("rgb_png_base64", "rgb.png"), ("depth_float32_base64", "depth.f32"), ("valid_mask_base64", "valid_mask.u8")):
        values[field] = base64.b64encode((folder / name).read_bytes()).decode()
    obs = RGBDObservation.model_validate(values)
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return obs.captured_at + datetime.timedelta(milliseconds=100)
    print(str(folder.relative_to(root)), obs.checksum_sha256)
    for label, module in (("57c4dc0d^", previous), ("4ed5cb50", tracking)):
        module.datetime = Clock
        info = {}
        def trace(frame, event, arg):
            if frame.f_code is module.OpenCVTargetTracker._geometry.__code__ and event == "return" and frame.f_locals["target"]:
                info.update({k: frame.f_locals[k] for k in ("selected", "ring", "top_depth_max", "depth", "valid", "shaded_edge") if k in frame.f_locals})
            return trace
        sys.settrace(trace)
        try:
            tracker = module.OpenCVTargetTracker(obs, ev)
            state = "ACCEPT"
        except ValueError as e:
            state = str(e)
        finally:
            sys.settrace(None)
        geom = np.frombuffer((folder / "instance_geom_ids.i32").read_bytes(), dtype="<i4").reshape(obs.height, obs.width)
        def count(mask):
            ids, counts = np.unique(geom[mask], return_counts=True)
            return [(meta["instance_labels"].get(str(i), str(i)), int(n)) for i, n in zip(ids, counts)]
        bad = info["ring"] & ~(np.isfinite(info["depth"]) & (info["valid"] > 0) & (info["depth"] > info["top_depth_max"]))
        print(label, state, "bad outer pixels (offline geom-ID audit only):", count(bad))
        if "shaded_edge" in info:
            print("absorbed (offline geom-ID audit only):", count(info["shaded_edge"]))
