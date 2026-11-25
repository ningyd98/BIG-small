"""Recover native contact wrenches at the exact candidate-course integration steps."""

import argparse
import gzip
import hashlib
import importlib.util
import json
import warnings
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DATA = Path("experiments/results/g1-lift-corridor-20261125/candidate-calibration-01")
WRENCH = HERE.parent / "round-g1-skill-handoff-20261125/handoff-physics-contact-wrench.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recover(root, out):
    import mujoco
    preview = load_module("native_candidate_study", HERE / "handoff-physics-sensor-preview.py")
    out.mkdir(parents=True, exist_ok=False)
    for course in sorted((root / DATA / "courses").glob("fresh*/*/result.json")):
        result = json.loads(course.read_bytes())
        case, candidate = result["case"], result["candidate"]["id"]
        selected = json.loads((root / DATA / "prefix" / case / "selection.json").read_bytes())
        if candidate not in {"r+0_t+0_h22", selected["selection"]["choice"]}:
            continue
        b, _ = preview.s.setup(root, case)
        try:
            sensors = preview.s.native.Sensors(b)
            source = course.with_name("series.npz")
            with np.load(source) as stream:
                arrays = {k: stream[k] for k in ("packed", "q", "qvel", "ctrl", "forces", "stage", "step")}
            steps = np.flatnonzero(arrays["stage"] == "GRASP")[-1:].tolist()
            lifts = np.flatnonzero(arrays["stage"] == "LIFT")
            if len(lifts):
                steps.extend(lifts[-120:].tolist())
            rows = []
            max_q = max_dq = max_force = 0.0
            for index in steps:
                # MuJoCo retains its dynamics/contact work arrays from the preceding
                # substep. Re-integrating the exact prior state and effective control
                # reproduces that instant, including the solver's contact forces.
                packed = arrays["packed"][index - 1]
                mujoco.mj_setState(b._model, b._data, packed, preview.io.STATE)
                b._data.ctrl[:] = arrays["ctrl"][index]
                mujoco.mj_step(b._model, b._data)
                observed, contacts = sensors.snap(b)
                max_q = max(max_q, float(np.max(abs(observed["q"] - arrays["q"][index]))))
                max_dq = max(max_dq, float(np.max(abs(observed["qvel"] - arrays["qvel"][index]))))
                max_force = max(max_force, float(np.max(abs(observed["force_N"] - arrays["forces"][index]))))
                rows.append({
                    "step": int(arrays["step"][index]), "stage": str(arrays["stage"][index]),
                    "contacts": contacts, "center": observed["centers"][10].tolist(),
                    "rotation": observed["rotation"][10].tolist(),
                    "com": observed["world_com"].tolist(),
                })
            if max_q > 1e-10 or max_dq > 1e-8 or max_force > 1e-6:
                raise ValueError(f"native identity failed {case} {candidate} {max_q} {max_dq} {max_force}")
            native = dict(
                case=case, candidate=candidate, source_sha256=sha(source),
                model_geom_names=sensors.names,
                mass=float(b._model.body_mass[sensors.objectbody]), rows=rows,
                errors=dict(q=max_q, dq=max_dq, normal_force_N=max_force),
                native_full_eligible=result["eligible"], forbidden=result["actual_structure_contact_steps"],
                held=result["last_120_bilateral_over_50mm"],
            )
            dest = out / f"{case}-{candidate}.json.gz"
            dest.write_bytes(gzip.compress(json.dumps(native, allow_nan=False).encode(), mtime=0))
        finally:
            b.shutdown()


def evaluate(out):
    w = load_module("measured_contact_wrench_capacity", WRENCH)
    summary = []
    for source in sorted(out.glob("*.json.gz")):
        native = json.loads(gzip.decompress(source.read_bytes()))
        stages = {}
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=w.OptimizeWarning, message="Unrecognized options detected.*")
            for row in native["rows"]:
                state = w.frame(row["contacts"], np.array(row["com"]), np.array(row["rotation"]),
                                np.array(row["center"]), native["model_geom_names"], native["mass"])
                stages.setdefault(row["stage"], []).append(state)
        values = {}
        for stage, rows in stages.items():
            values[stage] = {
                "sample_count": len(rows),
                "minimum_static_gravity_wrench_weights": min(r["gravity_scale_from_measured_normals"] for r in rows),
                "min_bilateral_normals_N": np.min([r["force_N"] for r in rows], axis=0).tolist(),
                "max_gravity_torque_Nm": max(r["gravity_torque_about_measured_patch_centroid_Nm"] for r in rows),
                "max_measured_contact_torque_norm_Nm": max(float(np.linalg.norm(r["measured_contact_torque_Nm"])) for r in rows),
            }
        summary.append({k: native[k] for k in ("case", "candidate", "errors", "native_full_eligible", "forbidden", "held")} |
                       {"stages": values, "contact_file": source.name, "contact_sha256": sha(source)})
    with (out / "index.json").open("x") as f:
        json.dump({"courses": summary, "source": sha(Path(__file__)), "wrench_solver": sha(WRENCH)},
                  f, indent=2, sort_keys=True, allow_nan=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("recover", "wrench"))
    args = parser.parse_args()
    if args.mode == "recover":
        recover(args.root.resolve(), args.out.resolve())
    else:
        evaluate(args.out.resolve())
