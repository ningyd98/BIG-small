"""Measure v1 versus the proposed second version on two historical frames in fixed order."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from pixel_timing import prior


def main():
    args = argparse.ArgumentParser()
    args.add_argument("v1_diagnostic_tree", type=Path)
    args.add_argument("candidate_source", type=Path)
    args.add_argument("output", type=Path)
    p = args.parse_args()
    old = prior()
    methods = old.readers(p.v1_diagnostic_tree)["candidate"]
    key = "scripts.graduation.g1_visibility_grid"
    grid, vision = [p.candidate_source / s for s in old.SOURCES]
    prior_grid = sys.modules[key]
    try:
        sys.modules[key] = old.module("working_grid", grid)
        new = old.module("working_vision", vision).measure_frame
    finally:
        sys.modules[key] = prior_grid
    frames, values, geometry = old.inputs()
    funcs = {"v1": methods, "v2": new}
    out = {}
    for r in frames[-2:]:
        f = values[r["frame_id"]]
        for measurement in funcs.values():
            measurement(f, geometry)
        pairs = []
        for n in range(16):
            sequence = list(funcs) if n % 2 == 0 else list(funcs)[::-1]
            results = {}
            for name in sequence:
                v, times = old.clock_call(funcs[name], f, geometry)
                results[name] = dict(**times, measurement_sha256=old.sha(old.canonical(v)))
            assert results["v1"]["measurement_sha256"] == results["v2"]["measurement_sha256"]
            pairs.append(dict(order=sequence, results=results))
        out[r["file"]] = dict(
            frame_id=f.frame_id,
            checksum_sha256=f.checksum_sha256,
            file_sha256=r["file_sha256"],
            pairs=pairs,
            median_ms={
                k: float(np.median([x["results"][k]["ns"] for x in pairs])) / 1e6 for k in funcs
            },
            paired_median_saving_ms=float(
                np.median([x["results"]["v1"]["ns"] - x["results"]["v2"]["ns"] for x in pairs])
            )
            / 1e6,
        )
    doc = dict(
        v1_detector_files_sha256=old.SOURCES,
        candidate_detector_files_sha256={
            s: old.sha((p.candidate_source / s).read_bytes()) for s in old.SOURCES
        },
        source_sha256=old.sha(Path(__file__).read_bytes()),
        frames=out,
        method="One ordinary warmup per version then 16 same-process alternating pairs per "
        "frame. Complete measure_frame with independent output hashes. Engineering scout only.",
    )
    with p.output.open("x") as fp:
        json.dump(doc, fp, sort_keys=True, indent=2, allow_nan=False)
        fp.write("\n")
    print({k: (v["median_ms"], v["paired_median_saving_ms"]) for k, v in out.items()})


if __name__ == "__main__":
    main()
