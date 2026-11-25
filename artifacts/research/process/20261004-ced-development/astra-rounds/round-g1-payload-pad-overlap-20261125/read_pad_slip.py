"""Read friction utilization from sealed transport, without advancing simulation."""

import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
from read_gripper_preload import ASSET, ASSET_SHA, FIT_SUMMARY, HERE, RAW, read, sha


def usage(path):
    archive = read(path)
    force = archive["contact_columns"].index("MuJoCo_contact_force_torque_local")
    friction = archive["contact_columns"].index("friction_coefficients")
    manifolds = archive["columns"].index("loaded_contact_rows")
    loads = []
    coefficients = set()
    for row in archive["rows"]:
        for patch in row[manifolds]:
            normal, tangential_1, tangential_2, *torque = patch[force]
            mu_1, mu_2 = patch[friction][:2]
            if normal <= 0 or min(mu_1, mu_2) <= 0 or any(torque):
                raise ValueError("expected positive normal force in 3D loaded contact")
            ratio = (abs(tangential_1) / mu_1 + abs(tangential_2) / mu_2) / normal
            if not 0 <= ratio <= 1:
                raise ValueError("loaded wrench falls outside the registered pyramidal cone")
            loads.append(ratio)
            coefficients.add((mu_1, mu_2))
    return {
        "native_ticks": len(archive["rows"]),
        "loaded_contact_count": len(loads),
        "sliding_friction_used_by_solver": sorted(coefficients),
        "friction_cone_fraction_median": float(np.median(loads)),
        "friction_cone_fraction_p95": float(np.quantile(loads, 0.95)),
        "friction_cone_fraction_max": max(loads),
        "private_manifest_sha256": sha(path),
    }


def main(root, output):
    summary_path = HERE / "pad-physics-fit-results.public.json"
    asset = root / ASSET
    if sha(summary_path) != FIT_SUMMARY or sha(asset) != ASSET_SHA:
        raise ValueError("simulation model or contact receipt changed")
    summary = read(summary_path)
    model = mujoco.MjModel.from_xml_path(str(asset))
    cone = mujoco.mjtCone(int(model.opt.cone))
    geoms = ("left_finger_geom", "right_finger_geom", "object_geom")
    if cone != mujoco.mjtCone.mjCONE_PYRAMIDAL or any(
        model.geom(name).condim[0] != 3 for name in geoms
    ):
        raise ValueError("this reader requires the original 3D pyramidal contact")
    courses = {}
    for key in summary["cases"]:
        path = RAW / key / "transport-contact-manifolds.json.gz"
        if sha(root / path) != summary["bindings"][str(path)]:
            raise ValueError(f"frozen contact archive changed: {path}")
        courses[key] = usage(root / path)
    payload = {
        "schema": "g1.pad.friction.utilization-readback.v1",
        "source_summary_sha256": sha(summary_path),
        "asset_sha256": ASSET_SHA,
        "readback_sha256": sha(Path(__file__)),
        "mujoco_version": mujoco.__version__,
        "scope": "Offline force audit on the three original fitting courses.",
        "cone": cone.name,
        "solver": mujoco.mjtSolver(int(model.opt.solver)).name,
        "impratio": float(model.opt.impratio),
        "noslip_iterations": int(model.opt.noslip_iterations),
        "fraction_formula": "(abs(Ft1)/mu1 + abs(Ft2)/mu2)/Fn",
        "courses": courses,
        "qualification": False,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, allow_nan=False, indent=2, sort_keys=True)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=Path.cwd())
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    main(args.root.resolve(), args.output)
