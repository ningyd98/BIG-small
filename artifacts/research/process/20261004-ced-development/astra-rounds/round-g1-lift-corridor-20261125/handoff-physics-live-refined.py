"""Replay the prospectively frozen fixed-height candidate under real native optical feedback."""

import argparse
import fcntl
import importlib.util
from pathlib import Path

import cv2


HERE = Path(__file__).resolve().parent
FIXED_SHA = "ca86d655282e1a0108439b4d872bdc5b34bb6e5e29ef3b0391f56728917bda1b"
LIVE = HERE / "handoff-physics-live-candidate.py"
REFINEMENT = HERE / "handoff-physics-candidate-refinement.py"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(root, out, cases):
    live = load_file("paired_native_controller", LIVE)
    refine = load_file("refined_native_targets", REFINEMENT)
    freeze = HERE / "handoff-physics-refinement-fixed-freeze.public.json"
    if live.io.sha(freeze) != FIXED_SHA:
        raise ValueError("fixed candidate freeze mismatch")
    choice = live.io.read(freeze)["selected_id"]
    live.FREEZE = FIXED_SHA
    live.rule.choose = lambda optical_center: choice
    study = live.io.read(HERE / "handoff-physics-candidate-refinement-design.json")
    live.candidates.DESIGN["candidates"].extend(study["candidate_set"])
    live.candidates.target = refine.target
    cv2.setNumThreads(1)
    with (root / "experiments/results/g1-visibility-pose-repair-20261124/egl.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for case in cases:
            live.execute(root, out, case, "rule")
    bound = {
        case: live.io.sha(out / case / "rule" / "results.json") for case in cases
    }
    live.io.write(out / "fixed22-source-binding.json", {
        "freeze": FIXED_SHA, "candidate": choice, "results": bound,
        "sources": {p.name: live.io.sha(p) for p in (LIVE, REFINEMENT, Path(__file__))},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--case", action="append", choices=("t01", "t02"), required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.out.resolve(), args.case)
