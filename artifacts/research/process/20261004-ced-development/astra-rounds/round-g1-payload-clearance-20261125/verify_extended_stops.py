"""Read both untouched near-table validation courses against frozen directional supports."""

import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_geometry import Model
from scripts.graduation.g1_complete_cv_motion import MotionGeometry
from scripts.graduation.g1_complete_cv_payload import (
    SPEED_CLASSES,
    PayloadClearance,
    object_matrix,
)
from scripts.graduation.g1_complete_cv_payload_fit import measurements
from scripts.graduation.g1_complete_trials import write_once
from scripts.graduation.perception_io import ROOT, pinned, read, sha

HERE = Path(__file__).resolve().parent
RAW = ROOT / "experiments/results/g1-payload-clearance-20261125"
PLAN = "d0003983ec05d1dc5034ea08d70184ebbd3dc4af413c1873ac785a0d795b89b0"
PROFILES = {
    "payload_profile": "48d5108e194fed21373f96133d174951afaf78fbe4a6e36766d2ee0ba6b1a10e",
    "source_support_profile": "6dd36013c01e14763d6897804b9fb45cbff7dfc84edcfcc7eccf4f75860f2e0d",
    "source_motion_profile": "afeaa3ca7360f8287a094a4cb3285126cd47398548fb3b51b2f41d2e3be16f76",
}


def prospect(layout, source, label):
    prefix = RAW / "fresh-normal-03-native-source" / label
    normal = prefix / "normal.npz"
    index_file = RAW / "physical-stops-03-native-source" / label / "index.json"
    index = read(index_file)
    assert index["normal_sha256"] == sha(normal)
    assert index["packed_sha256"] == sha(prefix / "restart.npz")
    assert index["prereg_sha256"] == sha(HERE / "payload-motion-preregistration-03.json")
    actions = read(prefix / "actions.json")
    summary = read(prefix / "summary.json")
    assert index["case"] == summary["case"] == label and index["role"] == summary["role"]
    checks = []
    with np.load(normal) as closed:
        for entry in index["phases"]["LIFT"]:
            before = entry["step"]
            branch = index_file.parent / entry["file"]
            assert sha(branch) == entry["sha256"]
            world, relative, speed, forbidden, row = measurements(
                layout.motion, branch, layout.axes
            )
            np.testing.assert_allclose(row, closed["q"][before], atol=1e-12, rtol=0)
            rot = object_matrix(row[None])[0]
            bottom = float(row[11] - 0.035 * abs(rot[2]).sum())
            speed_key = next(
                (str(x) for x in SPEED_CLASSES if speed <= x and str(x) in source), "all"
            )
            standard = layout.data["LIFT"]["classes"]
            standard_key = next(
                (str(x) for x in SPEED_CLASSES if speed <= x and str(x) in standard), "all"
            )
            active = standard[standard_key]
            signed = 1.25 * np.asarray(source[speed_key]["world"]) + 0.0005
            relative_margin = (
                active["relative"][layout.motion.hand_start :]
                - relative[layout.motion.hand_start :]
            )
            checks.append(
                dict(
                    step=before,
                    bottom_m=bottom,
                    world_margin_m=float((active["world"] - world).min()),
                    near_station_margin_m=float((signed - world).min()),
                    arm_and_grip_relative_margin_m=float(relative_margin.min()),
                    forbidden_contact_ticks=forbidden,
                    sha256=entry["sha256"],
                    raw=branch.relative_to(ROOT).as_posix(),
                )
            )
    return dict(
        native_end=dict(
            skill=actions[-1]["stage"],
            code=actions[-1]["error_code"],
            duration_steps=actions[-1]["step"] - actions[-1]["start_step"],
        ),
        input_sha256={
            p.relative_to(ROOT).as_posix(): sha(p)
            for p in (
                normal,
                index_file,
                prefix / "summary.json",
                prefix / "actions.json",
                prefix / "restart.npz",
            )
        },
        actual_emergency_stop_branches=len(checks) * 9,
        checked_windows=checks,
    )


def main():
    pinned(HERE / "plan.json", PLAN)
    profiles = {
        k: pinned(ROOT / "scripts/graduation" / f"g1_complete_cv_{k}.json", v)
        for k, v in PROFILES.items()
    }
    rig = (
        ROOT
        / "assets/robots/franka_panda"
        / "scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml"
    )
    assert sha(rig) == profiles["payload_profile"]["asset_sha256"]
    layout = PayloadClearance(MotionGeometry(Model(rig)), profiles["payload_profile"])
    values = {
        n: prospect(layout, profiles["source_motion_profile"]["classes"], n)
        for n in ("payload-val-07", "payload-val-08")
    }
    result = dict(
        checked_profiles=PROFILES,
        scope="independent native near-source physical stop branches",
        no_new_integrated_qualification=True,
        results=values,
    )
    write_once(HERE / "source-support-extra-validation.public.json", result)
    print(
        json.dumps(
            {
                k: [
                    v["actual_emergency_stop_branches"],
                    v["native_end"],
                    min(a["near_station_margin_m"] for a in v["checked_windows"]),
                    max(a["forbidden_contact_ticks"] for a in v["checked_windows"]),
                ]
                for k, v in values.items()
            }
        )
    )


if __name__ == "__main__":
    main()
