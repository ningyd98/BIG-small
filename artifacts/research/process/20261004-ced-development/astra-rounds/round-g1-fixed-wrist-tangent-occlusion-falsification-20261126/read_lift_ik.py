"""Read the frozen native IK response at the two recorded grid-04 refusals."""

import gzip
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
from read_grasp_pre import HERE, ROOT, read, require, sha

from cloud_edge_robot_arm.simulation.mujoco.motion_controller import MuJoCoMotionController
from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
from cloud_edge_robot_arm.vision.observations import RGBDObservation


def main():
    plan = read(HERE / "plan.json")
    generation = plan["runtime_manifest_sha256"]
    runtime = (
        ROOT
        / "experiments/results/g1-complete-cv-repair-20261125/builds"
        / generation
        / "runtime-source"
    )
    source = Path(inspect.getsourcefile(MuJoCoMotionController)).resolve()
    relative = source.relative_to(runtime.resolve()).as_posix()
    require(
        sha(runtime / "runtime-build.json") == generation
        and sha(source) == plan["runtime_relative_source_sha256"][relative]
        and mujoco.__version__ == "3.3.7",
        "native IK runtime differs",
    )
    derived = HERE.parent / "round-g1-grid04-cross-route-silhouette-test-20261126"
    for name in ("plan.json", "cross-route.public.json"):
        key = f"{derived.name}/{name}"
        require(
            sha(derived / name) == plan["round_sources_relative_to_astra_rounds_sha256"][key],
            "prior readback seal differs",
        )
    registration = read(derived / "plan.json")
    report = {}
    for route, tick in (("original", 2112), ("midcourse", 2384)):
        slot = registration["slots"][route]
        directory = ROOT / slot["path"] / "g1-lift-grid-04"
        filename = slot["frames"][str(tick)]
        for name in (slot["allocation"], filename, "rgbd-index.json", "clearance-gate.json"):
            path = directory / name
            key = path.relative_to(ROOT).as_posix()
            require(sha(path) == registration["source_sha256"][key], f"input changed: {key}")
        allocation = read(directory / slot["allocation"])
        index = read(directory / "rgbd-index.json")
        (indexed,) = [row for row in index["rows"] if row["file"] == filename]
        (gate,) = [
            row
            for row in read(directory / "clearance-gate.json")["checks"]
            if (row["step"], row["skill"], row["phase"]) == (tick, "LIFT", "FEEDBACK")
        ]
        frozen = indexed["robot"]
        frame = RGBDObservation.model_validate_json(
            gzip.decompress((directory / filename).read_bytes())
        )
        require(
            (indexed["skill"], indexed["phase"], frozen["physics_step"])
            == ("LIFT", "FEEDBACK", tick)
            and frame.frame_id == frozen["frame_id"] == gate["frame_id"]
            and frame.checksum_sha256 == frozen["checksum_sha256"] == gate["checksum_sha256"]
            and frame.sim_time_s == frozen["sim_time_s"] == frozen["camera_encoder_sim_time_s"]
            and frame.episode_id == index["episode_id"]
            and gate["current"]["status"] == "BLOCKED",
            "not the original synchronized refusal",
        )
        asset = runtime / allocation["geometry"]["asset_path"]
        require(sha(asset) == allocation["asset_sha256"], "original assembly digest differs")
        model = mujoco.MjModel.from_xml_path(str(asset))
        data = mujoco.MjData(model)
        addresses = [int(model.joint(f"joint{i}").qposadr[0]) for i in range(1, 8)]
        q = np.asarray(frozen["joint_positions_rad"])
        data.qpos[addresses] = q
        mujoco.mj_forward(model, data)
        tcp = data.site("tcp")
        original = tcp.xpos.copy()
        native = MuJoCoMotionController(SimpleNamespace(_model=model, _data=data, _mujoco=mujoco))
        shift = np.array([plan["candidate_mm"] / 1000, 0, 0])
        rotation = np.array(_DOWNWARD)
        baseline = native._inverse_kinematics(original, rotation, tcp.id)
        tangent = native._inverse_kinematics(original + shift, rotation, tcp.id)
        require(
            baseline is not None and tangent is not None, "native solver returned no comparison"
        )
        identical = bool(np.array_equal(baseline, q) and np.array_equal(tangent, q))
        report[str(tick)] = {
            "frame_id": frame.frame_id,
            "source_status": gate["current"]["status"],
            "source_unknown_pixels_uv": gate["current"]["depth"]["unmatched_pixels_uv"],
            "comparison_target_xyz_m": original.tolist(),
            "tangent_target_xyz_m": (original + shift).tolist(),
            "fixed_orientation_wxyz": list(_DOWNWARD),
            "baseline_max_joint_delta_rad": float(np.max(abs(baseline - q))),
            "tangent_max_joint_delta_rad": float(np.max(abs(tangent - q))),
            "identical_local_robot_geometry": identical,
            "pixel_cone_and_3x3_effect": (
                "IDENTICAL_BY_SAME_CONFIGURATION" if identical else "UNVERIFIED"
            ),
        }
    print(
        json.dumps(
            {
                "scope": "SAME_STATE_NATIVE_IK_ONLY",
                "no_new_integrations_or_exposures": True,
                "earlier_approach_offset_execution_and_visibility": "UNVERIFIED",
                "observations": report,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
