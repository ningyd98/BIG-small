"""Record frozen scalar verifier returns and originating seeds on native radial d02 inputs."""

import argparse
import gzip
import hashlib
import inspect
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROUND = Path(__file__).resolve().parent
ROOT = next(p for p in ROUND.parents if (p / "pyproject.toml").is_file())
DATA = ROOT / "experiments/results/g1-visibility-pose-repair-20261124"
GENERATION = "36f9658b9e7ef0d94db0a87876f4224e30d357d59f6dcc18dc65768dbb1e23bf"
FROZEN = DATA / "builds" / GENERATION / "runtime-source"
TRIAL = DATA / "batches/train-radial15-01/d02"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def trace_frame(grid, method, frame, geometry):
    source = Path(inspect.getsourcefile(grid._verify)).read_text().splitlines()
    functions = [grid._verify, grid._accept, grid._weak_grid_cells, grid._crossings]
    names = {fn.__code__: fn.__name__ for fn in functions}
    state = {"groups": [], "verifications": [], "batch_screens": [], "crossing_calls": 0}
    positions = {}

    def trace(call, event, result):
        name = names.get(call.f_code)
        if not name:
            return None
        # Return-line attribution needs no per-line Python trace events.
        call.f_trace_lines = False
        args = call.f_locals
        if event == "call":
            if name == "_accept":
                state["groups"].append(
                    {
                        "source": args["source"],
                        "seed_count": len(args["seeds"]),
                        "codes": dict(Counter(seed[0] for seed in args["seeds"])),
                    }
                )
            elif name == "_crossings":
                state["crossing_calls"] += 1
            elif name == "_verify":
                positions[id(call)] = (args["center"].tolist(), args["basis"].tolist())
            return trace
        if event == "return" and name == "_verify":
            center, basis = positions.pop(id(call))
            idx = call.f_lineno - 1
            row = dict(
                group=len(state["groups"]) - 1,
                code=args["code"],
                center=center,
                basis=basis,
                returned_line=idx + 1,
                iteration=args.get("iteration"),
                first_reject_source=source[idx - 1].strip() if result is None else None,
            )
            if "values" in args:
                threshold = float(args["threshold"])
                values = args["values"]
                contrast = float(args["contrast"])
                row.update(
                    fitted_center=args["center"].tolist(),
                    fitted_basis=args["basis"].tolist(),
                    contrast=contrast,
                    threshold=threshold,
                    wrong_centers=int(np.count_nonzero((values > threshold) != args["bits"])),
                    min_margin=float(np.min(abs(values - threshold)) / contrast)
                    if contrast
                    else None,
                )
            if "cell_measurements" in args:
                local = args["cell_measurements"]
                row.update(
                    wrong_local=int(np.count_nonzero((local > threshold) != args["bits"])),
                    min_local_margin=float(np.min(abs(local - threshold)) / contrast),
                )
            if "good" in args:
                row["unsupported_heldout"] = int(np.sum(~args["good"][args["held"]]))
            if "rms" in args:
                row["heldout_rms_px"] = float(args["rms"])
            state["verifications"].append(row)
        if event == "return" and name == "_weak_grid_cells":
            seeds = args["seeds"]
            state["batch_screens"].append(
                dict(
                    group=len(state["groups"]) - 1,
                    code=args["code"],
                    original_poses=[
                        {"center": s[1].tolist(), "basis": s[2].tolist()} for s in seeds
                    ],
                    negative_indices=list(map(int, result)),
                )
            )
        return trace

    sys.settrace(trace)
    try:
        result = method(frame, geometry)
    finally:
        sys.settrace(None)
    state.update(
        observed_ids=result["observed_ids"],
        usable_ids=result["usable_ids"],
        measurement_sha256=sha(canonical(result)),
    )
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.path[:0] = [str(FROZEN), str(FROZEN / "src")]
    from scripts.graduation import g1_visibility_grid as grid
    from scripts.graduation import g1_visibility_vision as vision

    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    assert (
        sha(Path(grid.__file__).read_bytes())
        == "dba9b870fb73c92b1a19af78b203ccf816c26573d86e3938af4c21f445b0f6fa"
    )
    plan = json.loads((ROUND / "plan.json").read_bytes())
    for rel, digest in plan["inputs_sha256"].items():
        assert sha((ROOT / rel).read_bytes()) == digest, rel
    geometry = json.loads((TRIAL / "allocation.json").read_bytes())["geometry"]
    rows = {}
    index = json.loads((TRIAL / "instance/pixel-index.json").read_bytes())["frames"]
    for item in index[-4:]:
        path = TRIAL / "instance" / item["file"]
        raw = path.read_bytes()
        assert sha(raw) == item["file_sha256"]
        frame = RGBDObservation.model_validate_json(raw)
        assert (
            frame.frame_id == item["frame_id"] and frame.checksum_sha256 == item["checksum_sha256"]
        )
        record = trace_frame(grid, vision.measure_frame, frame, geometry)
        record.update(
            file_sha256=item["file_sha256"],
            frame_id=frame.frame_id,
            checksum_sha256=frame.checksum_sha256,
            physics_step=item["physics_step"],
        )
        rows[item["file"]] = record
        print(
            item["file"],
            record["crossing_calls"],
            sorted(
                Counter((r["code"], r["returned_line"]) for r in record["verifications"]).items()
            ),
        )
    doc = dict(
        generation=GENERATION,
        grid_sha256=sha(Path(grid.__file__).read_bytes()),
        vision_sha256=sha(Path(vision.__file__).read_bytes()),
        opencv=cv2.__version__,
        input="real native RGB-D only; Python trace; no timing claims",
        frames=rows,
    )
    with args.output.open("xb") as f:
        f.write(gzip.compress(canonical(doc), mtime=0))


if __name__ == "__main__":
    main()
