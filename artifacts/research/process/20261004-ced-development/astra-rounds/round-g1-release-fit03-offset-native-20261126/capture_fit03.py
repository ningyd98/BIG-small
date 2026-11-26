"""Acquire and cold-check a bounded B03 offset mechanism experiment."""

import argparse
import json
import struct
import subprocess
import sys
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import mujoco
import numpy as np
from scripts.graduation.perception_io import ROOT, read, sha

HERE = Path(__file__).resolve().parent
PLAN = read(HERE / "plan.json")
OUT = ROOT / PLAN["output"]
CID = "dense-fit-03"
TICKS = PLAN["cases"][CID]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify_sources():
    for key, digest in PLAN["verified_sha256"].items():
        p = ROOT / key
        require(p.resolve(strict=True) == p and sha(p) == digest, f"changed input {key}")


def reuse():
    verify_sources()
    path = ROOT / PLAN["native_reuse"]
    spec = spec_from_file_location("frozen_static_capture", path)
    driver = module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def record(path, data):
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def prepare(driver):
    original_slots, cal = driver.verify_pin_set()
    geo = ROOT / PLAN["geometry_data"]
    a, b = (geo / name for name in ("geometry.json", "geometry.cold.json"))
    require(a.read_bytes() == b.read_bytes(), "geometry cold outputs differ")
    summary = read(geo / "readback.json")
    require(
        summary["source_cpu_sha256"] == sha(a)
        and summary["selected_offset_mm"] is None
        and summary["common_optical_prerequisite_offsets"] == 0,
        "scope of partial B03 experiment changed",
    )
    rows = read(a)["states"]
    controls = driver.optics.historical_controls(original_slots)
    asset = driver.native.ASSET
    model = mujoco.MjModel.from_xml_path(str(asset))
    model.opt.timestep = 1 / 240
    physical = driver.old.source_module(
        "frozen_static_physical_clearance", driver.inputs.expand("{T}/terminal_rebound.py")
    )
    prepared, labels = {}, {}
    for condition, (x, y) in PLAN["conditions"].items():
        for tick in TICKS:
            key = f"{condition}/{CID}/{tick}"
            old_key = f"B/{CID}/{tick}"
            original = original_slots[old_key]
            selected = rows[old_key][f"{x},{y}"]
            require(
                selected["reject"] is None
                and selected["optical"]["joint_optical_prerequisites"] == (condition != "r0"),
                f"geometric gate no longer joins {key}",
            )
            data = mujoco.MjData(model)
            driver.native.restore(model, data, original, cal)
            reg = data.geom("target_region_geom")
            axes = reg.xmat.reshape(3, 3).copy()
            dx = axes @ np.array([x, y, 0], dtype=float) / 1000.0
            require(abs(dx[2]) < 1e-12, "offset is not horizontal")
            slot = deepcopy(original)
            if condition != "r0":
                addr = int(model.joint("object_free").qposadr[0])
                q = np.asarray(selected["physical"]["final_joint_positions_rad"])
                data.qpos[:7] = q
                data.qpos[addr : addr + 3] += dx
                mujoco.mj_forward(model, data)
                original_p = np.asarray(original["row"]["tcp_xyz_m"])
                original_r = np.asarray(original["row"]["tcp_R"])
                tcp = data.site("tcp")
                cube = data.geom("object_geom")
                target = np.asarray(original["row"]["geom"]["object_geom"][0]) + dx
                require(
                    np.linalg.norm(tcp.xpos - original_p - dx) <= 1e-7
                    and np.linalg.norm(tcp.xmat.reshape(3, 3) - original_r) <= 2e-6
                    and np.max(abs(tcp.xpos - selected["physical"]["tcp_pose_m"])) <= 1e-10
                    and np.linalg.norm(cube.xpos - target) <= 1e-9
                    and np.linalg.norm(
                        cube.xmat.reshape(3, 3) - original["row"]["geom"]["object_geom"][1]
                    )
                    <= 1e-9
                    and np.array_equal(data.qvel[:9], original["row"]["dq"])
                    and np.array_equal(data.qvel[9:], original["row"]["object_qvel"])
                    and np.array_equal(data.ctrl, original["row"]["control"])
                    and data.time == original["row"]["time_s"],
                    f"wrong position, arm, or source state overlay: {key}",
                )
                slot["row"]["q"][:7] = q.tolist()
                for name in ("left_finger_geom", "right_finger_geom", "object_geom"):
                    part = data.geom(name)
                    slot["row"]["geom"][name] = [
                        part.xpos.tolist(),
                        part.xmat.reshape(3, 3).tolist(),
                    ]
                slot["row"]["tcp_xyz_m"] = tcp.xpos.tolist()
                slot["row"]["tcp_R"] = tcp.xmat.reshape(3, 3).tolist()
            restored = mujoco.MjData(model)
            closure = driver.native.restore(model, restored, slot, cal)
            static = driver.branch.original.screen(
                model,
                restored,
                {frozenset(("object_geom", "table"))},
                {
                    ("object_geom", "table"): driver.branch.original.distance(
                        model, data, "object_geom", "table"
                    )
                },
            )
            gap, bottom, inside = physical.gap_and_table(slot["row"], slot["size"])
            require(
                static["pass"]
                and inside
                and min(gap) > 0.00025
                and min(restored.qpos[7:9]) > 0.035
                and max(abs(np.array(gap) - selected["physical"]["pad_gaps_m"])) <= 1e-6
                and not physical.dwell_issues(slot["row"], gap, inside),
                f"restored B03 physical contract not reproduced: {key}",
            )
            prepared[key] = slot
            labels[key] = {
                "source": old_key,
                "source_q": original["row"]["q"],
                "assigned_q": slot["row"]["q"],
                "geometry": slot["row"]["geom"],
                "axis_basis": axes.tolist(),
                "delta_world_m": dx.tolist(),
                "source_object": original["row"]["geom"]["object_geom"],
                "source_tcp_xyz_m": original["row"]["tcp_xyz_m"],
                "tcp_xyz_m": slot["row"]["tcp_xyz_m"],
                "source_clock": slot["row"]["time_s"],
                "jaw_gaps_m": gap,
                "bottom_m": bottom,
                "minimum_gap_m": static["minimum_gap_m"],
                "closure": closure,
            }
    require(
        not np.array_equal(
            labels[f"r0/{CID}/{TICKS[0]}"]["assigned_q"],
            labels[f"r1/{CID}/{TICKS[0]}"]["assigned_q"],
        ),
        "wrong-candidate negative control insensitive",
    )
    controls["baseline_and_shifted_assignment_distinct"] = True
    return prepared, labels, cal, controls, physical


def configure(driver):
    driver.PRIVATE = OUT
    driver.PLAN = driver.PLAN | {
        "head": PLAN["head"],
        "cases": PLAN["cases"],
        "conditions": PLAN["conditions"],
        "max_rgbd": 9,
    }

    def run_optics(condition, digest):
        subprocess.run([sys.executable, "-B", __file__, "predict", condition, digest], check=True)

    driver.optics_command = run_optics


def registration(driver, labels, cal, controls):
    return {
        "head": PLAN["head"],
        "plan_sha256": sha(HERE / "plan.json"),
        "plan_md_sha256": sha(HERE / "plan.md"),
        "source_sha256": sha(Path(__file__).resolve()),
        "calibration": cal,
        "conditions": PLAN["conditions"],
        "ticks": TICKS,
        "geometry_bindings": labels,
        "historical_controls": controls,
        "frozen_formal_originals": driver.inputs.originals(),
        "limits": PLAN["limits"],
    }


def capture(driver):
    prepared, labels, cal, controls, _ = prepare(driver)
    configure(driver)
    driver.check_native()
    reg = registration(driver, labels, cal, controls)
    require(OUT.resolve() == OUT and not OUT.exists(), "native capture already attempted")
    OUT.mkdir(parents=True, exist_ok=False)
    mapping = OUT / "registration.json"
    record(mapping, reg)
    reg_sha = sha(mapping)
    stage = ["exclusive EGL"]
    try:
        driver.attempt(stage, prepared, cal, reg_sha)
        require(
            driver.inputs.originals() == reg["frozen_formal_originals"], "formal originals changed"
        )
    except BaseException as failure:
        record(
            OUT / "aborted.json",
            {"stage": stage, "type": type(failure).__name__, "detail": str(failure)},
        )
        raise
    finally:
        members = driver.seal_members()
        count = sum(name.endswith("-request.json") for name in members)
        packets = sum(name.endswith(".json.gz") for name in members)
        record(
            OUT / "capture-seal.json",
            {
                "registration_sha256": reg_sha,
                "requests": count,
                "packets": packets,
                "complete": count == packets == 9 and not (OUT / "aborted.json").exists(),
                "sealed_sha256": members,
            },
        )


def encoders(p):
    return struct.pack("<9d", *(p["camera_joint_positions_rad"] + p["camera_finger_positions_m"]))


def cold_read(driver, filename):
    prepared, labels, cal, controls, terminal = prepare(driver)
    configure(driver)
    seal = read(OUT / "capture-seal.json")
    require(seal["complete"] and seal["requests"] == seal["packets"] == 9, "capture not complete")
    require(seal["sealed_sha256"] == driver.seal_members(), "capture seal differs")
    reg = driver.inputs.checked_json(OUT / "registration.json", seal["registration_sha256"])
    require(
        reg == registration(driver, labels, cal, controls), "reconstructed registration changed"
    )
    model = mujoco.MjModel.from_xml_path(str(driver.native.ASSET))
    model.opt.timestep = 1 / 240
    all_frames, seeds = {}, {}
    counts, summaries = {}, {}
    for condition in PLAN["conditions"]:
        directory = OUT / condition
        index = read(directory / "index.json")
        held = read(directory / "predictions.json")
        require(list(index["rows"]) == list(held) == driver.keys(condition), "missing sealed frame")
        episode = driver.old.native_identity(
            directory, CID, index["cases"][CID], prepared[f"{condition}/{CID}/{TICKS[0]}"]["reset"]
        )
        counts[condition] = 0
        for key, entry in index["rows"].items():
            tick = prepared[key]["source"]["source_tick"]
            p = prepared[key]
            receipt = read(directory / CID / f"{tick}-receipt.json")
            q = p["row"]["q"]
            data = mujoco.MjData(model)
            driver.native.restore(model, data, p, cal)
            reconstructed = driver.native.camera_encoder_pose(model, data)
            require(
                struct.pack("<9d", *q) == struct.pack("<9d", *receipt["source_step_end_encoders"])
                and encoders(reconstructed)
                == encoders(entry["robot"])
                == encoders(receipt["robot"])
                and entry["robot"] == receipt["robot"]
                and entry["new_episode"] == episode,
                "independent exposure encoder or static assignment mismatch",
            )
            frame, row = driver.old.read_slot(OUT, entry, key, held[key], p, cal, terminal)
            require(frame.frame_id not in all_frames, "duplicated native frame")
            all_frames[frame.frame_id] = key
            same_seed = seeds.setdefault(tick, row["rng_initial_sha256"])
            require(same_seed == row["rng_initial_sha256"], "unequal paired sensor RNG")
            counts[condition] += int(row["static_frame_eligible"])
            summaries[key] = row
    require(
        counts["r0"] == 0 and len(all_frames) == 9, "original baseline optical rejection changed"
    )
    record(
        Path(filename),
        {
            "seal_sha256": sha(OUT / "capture-seal.json"),
            "registration_sha256": seal["registration_sha256"],
            "counts_static_joint": counts,
            "slots": summaries,
            "native_steps": 0,
            "new_rgbd": 9,
        },
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("preflight", "capture", "predict", "read"))
    p.add_argument("extra", nargs="*")
    args = p.parse_args()
    driver = reuse()
    if args.mode == "preflight":
        _, labels, cal, controls, _ = prepare(driver)
        print(
            json.dumps(
                {"states": len(labels), "renderer": cal["renderer"], "controls": len(controls)}
            )
        )
    elif args.mode == "predict":
        configure(driver)
        driver.predict(*args.extra)
    elif args.mode == "capture":
        capture(driver)
    else:
        cold_read(driver, *args.extra)


if __name__ == "__main__":
    main()
