"""Drive finite original-controller courses from an actual observed MOVE_ABOVE return."""

import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
OLDER = HERE.parent / "round-g1-lift-corridor-20261125"
REG = HERE / "physics_selection_preregistration.json"
RAW = Path("experiments/results/g1-grasp-approach-selection-20261125/physical-selection-01")
BUILD = "816ed631e9dd17b510d2853afda7995b87e210c6cf8259df799a8a4da6b491eb"
LOCK = Path("experiments/results/g1-visibility-pose-repair-20261124/egl.lock")
ALLOCATION = Path("experiments/results/g1-complete-cv-repair-20261125/batches/train-full-04/cvfix-t01/allocation.json")


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def code(height, tangent):
    return f"h{height:02d}_t{tangent:+d}"


def root_candidates(heights, tangents):
    return [
        {"id": code(h, t), "height_above_estimated_center_mm": h,
         "tangential_mm": t, "radial_mm": 0} for h in heights for t in tangents
    ]


def inputs(root):
    reg = read(REG)
    fit = [r["name"] for r in reg["fit"]]
    blind = reg["blind_mechanical_first"] + reg["blind_optical_first"]
    return reg, fit, [r["name"] for r in blind]


def native_engine(root):
    reg, _, _ = inputs(root)
    old = load("registered_original_native_mechanics", OLDER / "handoff-physics-candidates.py")
    # Reuse the old trace/dynamics helpers with this round's explicitly locked imports.
    # Their own compiled-asset SHA and module-location check are still executed.
    old.native.REG["frozen_runtime"] = str(Path("experiments/results/g1-complete-cv-repair-20261125/builds") / BUILD / "runtime-source")
    old.DESIGN["cases"] = reg["fit"] + reg["blind_mechanical_first"] + reg["blind_optical_first"]
    old.DESIGN["candidates"] = root_candidates(reg["heights_mm"], [0, *reg["tangents_mm"]])
    return old


def object_target(center, rotation, candidate):
    translation = np.array([0.0, candidate["tangential_mm"], candidate["height_above_estimated_center_mm"]]) / 1000
    return np.asarray(center) + np.asarray(rotation).reshape(3, 3) @ translation


def geometry(root):
    old = read(root / "experiments/results/g1-complete-cv-repair-20261125/batches/train-full-02/cvfix-t01/allocation.json")
    latest = read(root / ALLOCATION)
    for key in ("asset_sha256", "calibration_sha256", "geometry"):
        if latest[key] != old[key]:
            raise ValueError(f"original physical setup changed {key}")
    if latest["runtime_build_sha256"] != BUILD:
        raise ValueError("changed runtime generation")
    return latest["geometry"]


def prepare(root, dest, names):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_visibility_vision import measure_frame
    import cv2
    import mujoco
    from scripts.graduation.g1_complete_cv_angle import grasp_readiness
    engine = native_engine(root)
    geom = geometry(root)
    cv2.setNumThreads(1)
    with (root / LOCK).open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name in names:
            start = time.monotonic_ns()
            engine.prepare(root, dest, name)
            prefix = dest / "prefix" / name
            frame = RGBDObservation.model_validate_json(gzip.decompress((prefix / "approach-reference.json.gz").read_bytes()))
            with bind_scene("approach-candidate-" + name):
                measured = measure_frame(frame, geom)
            if not measured["usable"]:
                raise ValueError("unusable original approach anchor")
            native = np.load(prefix / "return.npz")
            q, dq = native["q"], native["qvel"]
            rot = np.asarray(measured["rotation_object_to_world"]).reshape(3, 3)
            centre = np.asarray(measured["object_center_world_m"])
            reference = object_target(centre, rot, {"tangential_mm": 0, "height_above_estimated_center_mm": 10})
            np.testing.assert_allclose(reference, measured["grasp_world_m"], atol=1e-12)
            info = read(prefix / "prefix.json")
            evidence = {
                "case": name, "frame_sha256": sha(prefix / "approach-reference.json.gz"),
                "physics_state_sha256": sha(prefix / "return.npz"), "source_registration": sha(REG),
                "generation": BUILD, "renderer": info["renderer"], "measured_center": centre.tolist(),
                "rotation": rot.tolist(), "ids": measured["usable_ids"], "frame_id": frame.frame_id,
                "features": [centre.tolist(), q[:7].tolist(), dq[:7].tolist(),
                             (native["command_q"] - q[:7]).tolist(), q[7:9].tolist(), dq[7:9].tolist(),
                             rot[:, 0].tolist()],
                "elapsed_s": (time.monotonic_ns() - start) / 1e9,
                "imported_sources": {str(p): sha(p) for p in (Path(mujoco.__file__), Path(importlib.util.find_spec(grasp_readiness.__module__).origin),
                    Path(importlib.util.find_spec(measure_frame.__module__).origin))},
            }
            write(prefix / "measured-input.json", evidence)


def run_mechanics(root, dest, names, candidates):
    engine = native_engine(root)
    for name in names:
        anchor = read(dest / "prefix" / name / "measured-input.json")
        engine.target = lambda c, candidate: object_target(c, anchor["rotation"], candidate)
        t = time.monotonic_ns()
        engine.simulate(root, dest, name, candidates)
        key = "-".join(candidates)
        write(dest / "timing" / name / (key + ".json"),
              {"cpu_wall_s": (time.monotonic_ns() - t) / 1e9, "candidates": candidates})


def allowed(root, dest, stage, names):
    design, fits, blind = inputs(root)
    if stage in ("prepare-fit", "center-fit", "tangent-fit") and not set(names) <= set(fits):
        raise ValueError("unexpected fit case")
    if stage in ("prepare-blind", "blind") and not set(names) <= set(blind):
        raise ValueError("unexpected independent case")
    if stage == "center-fit":
        return [c["id"] for c in root_candidates(design["heights_mm"], [0])]
    if stage == "tangent-fit":
        seal = read(HERE / "physics_selection_tangent_seal.public.json")
        if seal["registration_sha256"] != sha(REG):
            raise ValueError("wrong tangent authorization")
        return [c["id"] for c in root_candidates(seal["heights"], design["tangents_mm"])]
    if stage in ("prepare-blind", "blind"):
        frozen = read(HERE / "physics_selection_freeze.public.json")
        if frozen["registration_sha256"] != sha(REG):
            raise ValueError("wrong frozen selection rule")
        if stage == "blind":
            for name in names:
                if read(dest / "prefix" / name / "decision.json")["freeze_sha256"] != sha(HERE / "physics_selection_freeze.public.json"):
                    raise ValueError("blind physical outcome requested before prospective choice")
        return frozen["candidate_ids"]
    return []


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--root", type=Path, required=True)
    a.add_argument("--mode", choices=("prepare-fit", "center-fit", "tangent-fit", "prepare-blind", "blind"), required=True)
    a.add_argument("--case", action="append", required=True)
    args = a.parse_args()
    root = args.root.resolve()
    dest = root / RAW
    choices = allowed(root, dest, args.mode, args.case)
    if args.mode.startswith("prepare"):
        prepare(root, dest, args.case)
    else:
        run_mechanics(root, dest, args.case, choices)
