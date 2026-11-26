"""Evaluate the frozen pin and RNG prerequisites without opening an EGL device."""

import argparse
import base64
import gzip
import hashlib
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import mujoco
import numpy as np
from pin_evidence import (
    ROOT,
    archived_frame,
    canonical,
    inputs,
    read,
    require,
    sha,
    verify_imports,
    verify_sources,
    write,
)
from pin_geometry import geometry
from pin_prefix import load_lines, tick_index
from supported_pin import cpu_environment, stamp

from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera


def no_camera_or_step():
    def deny(*args, **kwargs):
        raise RuntimeError("offline preflight attempted a render, exposure, reset or integration")

    stack = (
        patch.multiple(
            mujoco, Renderer=deny, mjr_render=deny, mj_step=deny, mj_step1=deny, mj_step2=deny
        ),
        patch.multiple(MuJoCoRGBDCamera, __init__=deny, capture=deny, _capture=deny),
        patch.multiple(
            MuJoCoPhysicsBackend,
            reset=deny,
            capture_sensor_frame=deny,
            capture_sensor_frame_with_instances=deny,
        ),
    )
    return stack


def prefix_files(output):
    folder = output / "prefix"
    receipt = read(folder / "receipt.json")
    actual_inventory = set(path.name for path in folder.iterdir() if path.is_file())
    require(
        actual_inventory == set(receipt["sha256"]) | {"receipt.json"}, "wrong prefix journal set"
    )
    for name, digest in receipt["sha256"].items():
        require(sha(folder / name) == digest, f"prefix member SHA256 mismatch: {name}")
    require(receipt["status"] == "ARCHIVED_PREFIX_EXACT", "prefix did not close")
    require(
        read(folder / "attempt.json")["registration_sha256"] == sha(output / "registration.json"),
        "prefix is not bound to the registration",
    )
    return folder, receipt


def noise_check(plan):
    camera = plan["camera"]
    roots = plan["roots"]
    case = ROOT / roots["old"] / roots["case_under_old"]
    entries = read(case / "rgbd-index.json")["rows"]
    require(len(entries) == 112, "wrong archived valid-mask inventory")
    mask_sha = camera["archived_valid_mask_sha256_112_of_112"]
    count = camera["draws_per_batch_to_validate"]
    for entry in entries:
        with gzip.open(case / entry["file"], "rb") as stream:
            import json

            row = json.load(stream)
        mask = base64.b64decode(row["valid_mask_base64"], validate=True)
        require(
            len(mask) == 76800
            and mask.count(b"\x01") == count
            and hashlib.sha256(mask).hexdigest() == mask_sha,
            f"historical mask drift: {entry['file']}",
        )
    sounds = read(case / "sensor-receipt.json")["camera_calls"]
    require(len(sounds) == 117, "historical capture receipt count differs")
    rng = np.random.default_rng(camera["historical_post_reset_depth_seed"])
    batch = 0
    (u0, u1), (v0, v1) = camera["rng_preflight_roi_uv_inclusive"]
    window = np.s_[v0 : v1 + 1, u0 : u1 + 1]
    results = []
    for slot, index, prior in zip(
        plan["shutters"],
        camera["historical_camera_call_indices_zero_based"],
        camera["hypothesized_prior_noise_batches_after_reseed"],
        strict=True,
    ):
        frame = archived_frame(case / slot["file"])
        require(
            frame.frame_id == slot["original_frame_id"]
            and frame.checksum_sha256 == slot["original_checksum"]
            and sounds[index] == {"step": slot["tick"], "time_s": slot["time_s"]},
            f"historical request/shutter relation differs: {slot['tick']}",
        )
        with np.load(
            ROOT / roots["surface"] / f"reference-projections/{slot['tick']}.npz",
            allow_pickle=False,
        ) as references:
            reference = references["robot"][window].astype("<f4")
        require(
            (reference == np.float32(camera["roi_reference_float32_m"])).all(),
            f"reference patch depth disagrees at {slot['tick']}",
        )
        mask = (
            np.frombuffer(base64.b64decode(frame.valid_mask_base64), "u1")
            .reshape(240, 320)
            .astype(bool)
        )
        measured = np.frombuffer(base64.b64decode(frame.depth_float32_base64), "<f4").reshape(
            240, 320
        )
        require(mask[window].all() and int(mask.sum()) == count, "invalid historical RNG ROI")
        while batch < prior:
            rng.normal(0, camera["depth_sigma_m"], size=count)
            batch += 1
        require(batch == prior, "noise slot order differs")
        state = rng.bit_generator.state
        predicted = np.full(measured.shape, camera["roi_reference_float32_m"], dtype="<f4")
        predicted[mask] += rng.normal(0, camera["depth_sigma_m"], size=count)
        batch += 1
        actual_patch, predicted_patch = measured[window], predicted[window]
        matches = actual_patch.view("<u4") == predicted_patch.view("<u4")
        abs_error = abs(actual_patch.astype("f8") - predicted_patch)
        results.append(
            {
                "tick": slot["tick"],
                "source_file_sha256": sha(case / slot["file"]),
                "frame_checksum_sha256": frame.checksum_sha256,
                "batch_index": prior,
                "tested_float32_words": matches.size,
                "matching_float32_words": int(matches.sum()),
                "max_absolute_difference_mm": float(1e3 * abs_error.max()),
                "archived_patch_sha256": hashlib.sha256(actual_patch.tobytes()).hexdigest(),
                "calculated_patch_sha256": hashlib.sha256(predicted_patch.tobytes()).hexdigest(),
                "registered_rng_state": state,
            }
        )
    require(
        all(row["matching_float32_words"] != row["tested_float32_words"] for row in results),
        "fixed RNG preregistration failure was not reproduced",
    )
    return {
        "status": "RNG_PREFLIGHT_FAILED",
        "slots": results,
        "roi_uv_inclusive": [list(x) for x in camera["rng_preflight_roi_uv_inclusive"]],
        "seed": camera["historical_post_reset_depth_seed"],
        "draws_per_batch": count,
        "archived_frame_mask_count": len(entries),
        "archived_mask_sha256": mask_sha,
        "new_seed_or_offset_searches": 0,
        "acquisition_gate": "CLOSED_FOR_THIS_ROUND",
    }


def run(plan, amendment):
    cpu_environment(plan)
    sources = verify_sources(plan, amendment)
    verify_imports(plan, sources["sha256"])
    output = ROOT / plan["private_output"]
    folder, _ = prefix_files(output)
    target = output / "preflight"
    target.mkdir(exist_ok=False)
    reset_zero = {"resets": 0, "native_commands": 0, "mj_steps": 0, "renders": 0, "exposures": 0}
    write(
        target / "source-first-failure.json",
        {
            **amendment["source_first_failure"],
            "override": amendment["plan_value_override"],
            "source_diagnostic_chunk": "82392e",
            "verified_correction": True,
        },
    )
    startup = read(Path(__file__).with_name("startup-amendment.json"))
    write(
        target / "startup-first-failure.json",
        {
            **startup["implementation"],
            "startup_diagnostic_chunk": "12e419",
            "startup_fixed_without_package_installations": True,
        },
    )
    write(
        target / "requests.json",
        [
            {
                "arm": arm,
                "source_tick": slot["tick"],
                "requested": False,
                "status": amendment["rng_first_failure"]["all_four_slots"],
            }
            for arm in ("A", "B")
            for slot in plan["shutters"]
        ],
    )
    render, camera, backend = no_camera_or_step()
    with render, camera, backend:
        rows = load_lines(folder / "endpoints.jsonl")
        tick_index(rows, "step", 0, 1520)
        rng = noise_check(plan)
        write(target / "rng-first-failure.json", {**rng, "initial_arithmetic_chunk": "0e6ae5"})
        raw = []
        try:
            result = geometry(plan, rows, target / "diagnostic-pin.xml", raw)
            write(
                target / "geometry.json",
                {
                    **result,
                    "distance_comparison_counts": dict(Counter(x["comparison"] for x in raw)),
                },
            )
        except BaseException as error:
            write(
                target / "geometry-first-failure.json",
                {"error": type(error).__name__, "detail": str(error), "counts": reset_zero},
            )
            raise
        finally:
            with (target / "distance-evaluations.jsonl").open("xb") as stream:
                for row in raw:
                    stream.write(canonical(row))
            write(
                target / "receipt.json",
                {
                    "counts": reset_zero,
                    "end_utc": stamp(),
                    "registration_sha256": sha(output / "registration.json"),
                    "prefix_receipt_sha256": sha(folder / "receipt.json"),
                    "members_sha256": {path.name: sha(path) for path in sorted(target.iterdir())},
                },
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    run(*inputs(args.plan))
