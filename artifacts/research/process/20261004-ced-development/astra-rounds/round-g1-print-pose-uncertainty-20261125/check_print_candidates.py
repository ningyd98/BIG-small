"""Replay the registered pixel support on three fitting sequences, then score its sealed predictions."""
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = Path("experiments/results/g1-continuous-payload-observation-20261125")
OUT = Path("experiments/results/g1-print-pose-uncertainty-20261125")
REG = HERE / "diagnostic-registration.json"
REG_SHA = "3a3f129013e34997b4a6eac173c7a9afef57703639ad3a4253912c5b946e54e9"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def store(path, value):
    with path.open("x") as target:
        json.dump(value, target, sort_keys=True, allow_nan=False)
        target.write("\n")


def replay():
    assert sha(REG) == REG_SHA
    reg = read(REG)
    for name, digest in reg["input_sha256"].items():
        assert sha(Path(name)) == digest, name
    source = HERE.parent / "round-g1-continuous-payload-observation-20261125/red-ink-fit.py"
    spec = importlib.util.spec_from_file_location("registered_ink", source)
    ink = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ink)
    out = []
    for name in reg["development_replay"]:
        folder = BASE / "physical-03" / name
        receipt = read(folder / "sensor-receipt.json")
        assert sha(folder / "rgbd-index.json") == receipt["index_sha256"]
        assert receipt["baseline_camera"] == reg["camera"] and receipt["role"] == "fit"
        records = read(BASE / (name + "-prediction-01.json"))["records"]
        for item, old in zip(read(folder / "rgbd-index.json")["rows"], records, strict=True):
            pose = old["result"]["pose"]
            if not pose or pose["method"] != "id8_and_red_top":
                continue
            path = folder / item["file"]
            assert sha(path) == item["file_sha256"]
            frame = json.loads(gzip.decompress(path.read_bytes()))
            assert frame["checksum_sha256"] == pose["checksum_sha256"] == old["checksum_sha256"]
            row = dict(case=name, frame=frame["frame_id"], checksum=frame["checksum_sha256"],
                       rotation=pose["rotation"], eligible=False, support_count=0)

            def trace(call, event, value):
                if call.f_code is ink.metric.__code__ and event == "return" and value is not None:
                    local = call.f_locals
                    supported = ink.GRID[local["supported"]]
                    yaw = np.rad2deg(supported[:, 0])
                    lo, hi = float(yaw.min() - .1), float(yaw.max() + .1)
                    edge = bool(np.any(abs(yaw) >= 2.99) or np.any(abs(supported[:, 1:]) >= .00149))
                    strong = (not edge and hi-lo <= 1 and value["gray_pixels"] >= 180
                              and value["red_pixels"] >= 24)
                    row.update(eligible=strong, interval_deg=[lo, hi], boundary=edge,
                               support_count=len(yaw), print_pixels=value["gray_pixels"],
                               red_pixels=value["red_pixels"])
                return trace

            sys.settrace(trace)
            try:
                ink.metric(frame, pose)
            finally:
                sys.settrace(None)
            out.append(row)
    OUT.mkdir(parents=True, exist_ok=True)
    store(OUT / "fit-prediction.json", dict(registration=REG_SHA, script=sha(Path(__file__)),
                                           physics_labels_read=False, records=out))


def score():
    pred = OUT / "fit-prediction.json"
    assert read(pred)["script"] == sha(Path(__file__)) and read(pred)["registration"] == REG_SHA
    rows = read(pred)["records"]
    report = {}
    for name in read(REG)["development_replay"]:
        labels = BASE / "physical-03" / name / "offline-physics.json"
        assert sha(labels) == read(BASE / (name + "-score-02.json"))["raw_physics_sha256"]
        truth = {v["frame_id"]: v for v in read(labels)["frame_labels"]}
        fit = [r for r in rows if r["case"] == name]
        issued = misses = boundary = unsupported = 0
        widths = []
        for r in fit:
            t = truth[r["frame"]]
            assert t["checksum_sha256"] == r["checksum"]
            if not r["support_count"]:
                unsupported += 1
                continue
            lo, hi = r["interval_deg"]
            widths.append(hi - lo)
            boundary += r["boundary"]
            if r["eligible"]:
                issued += 1
                rel = np.asarray(r["rotation"]).T @ np.asarray(t["rotation"])
                yaw = np.rad2deg(np.arctan2(rel[1, 0], rel[0, 0]))
                misses += int(not lo <= yaw <= hi)
        report[name] = dict(frames=len(fit), eligible=issued, misses=misses,
                            touches_boundary=boundary, unsupported=unsupported,
                            median_yaw_width_deg=float(np.median(widths)) if widths else None)
    store(HERE / "fit-diagnostic.public.json", dict(fit_only=report, certificate_issued=False,
          prediction_sha256=sha(pred), registration_sha256=REG_SHA, raw_files_new_holdout_opened=0))


if __name__ == "__main__":
    {"replay": replay, "score": score}[sys.argv[1]]()
