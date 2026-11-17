"""Use the project's verified Molmo runtime and unmodified production point provider."""
import base64
import json
import runpy
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from cases import CASES, FRAMES, MAIN, WORKTREE, rgb_sha, write_json

LAUNCHER = WORKTREE / ("artifacts/research/process/20261004-ced-development/astra-rounds/"
                      "round545-molmo-opencv-runtime-overlay-20261110/implementation/launch_molmo_grounded.py")
ASSETS = MAIN / "datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER"
MANIFEST = MAIN / ("artifacts/research/process/20261004-ced-development/astra-rounds/"
                   "round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/asset-manifest.json")

def replay_observation(folder):
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    meta = json.loads((folder / "observation.json").read_text())
    data = {k: v for k, v in meta.items() if k in RGBDObservation.model_fields}
    for key, file in (
        ("rgb_png_base64", "rgb.png"),
        ("depth_float32_base64", "depth.f32"),
        ("valid_mask_base64", "valid_mask.u8"),
    ):
        data[key] = base64.b64encode((folder / file).read_bytes()).decode("ascii")
    return RGBDObservation.model_validate(data)

def main(out):
    out.mkdir(exist_ok=False)
    runtime = runpy.run_path(str(LAUNCHER))["configure_overlay"]()
    import torch
    from cloud_edge_robot_arm.vision.molmo_pointing import MolmoPointProvider

    observations = {frame: replay_observation(folder) for frame, folder in FRAMES.items()}
    write_json(out / "preflight.json", runtime)
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    model = MolmoPointProvider(
        model_directory=ASSETS, asset_manifest=MANIFEST, raw_directory=out / "provider",
        generation_limit=len(CASES),
    )
    model_load_and_verification_s = time.perf_counter() - started
    rows = []
    for i, (case, frame, phrase, _) in enumerate(CASES, 1):
        try:
            observed = observations[frame]
            bound = model.point(observed, phrase)
            assert bound.observation_checksum == observed.checksum_sha256
            assert bound.rgb_sha256 == rgb_sha(frame)
            row = {"case": case, "frame": frame, "phrase": phrase, "rgb_sha256": bound.rgb_sha256,
                   "observation_checksum": bound.observation_checksum,
                   **asdict(bound.result), "evidence": dict(bound.evidence)}
        except Exception as exc:
            row = {"case": case, "frame": frame, "phrase": phrase, "rgb_sha256": rgb_sha(frame),
                   "status": "ERROR", "error": repr(exc), "traceback": traceback.format_exc()}
        rows.append(row)
        write_json(out / f"{i:02d}.json", row)
        print(case, row["status"], row.get("normalized_1000"), flush=True)
    write_json(out / "results.json", {
        "model": "allenai/Molmo2-ER", "runtime": model.runtime,
        "gpu": torch.cuda.get_device_name(),
        "model_load_including_assets_verification_s": model_load_and_verification_s,
        "peak_gpu_allocated_MiB": torch.cuda.max_memory_allocated()/2**20,
        "generation_calls_started": model.generation_calls_started,
        "generation_calls_completed": model.generation_calls_completed,
        "results": rows,
    })

if __name__ == "__main__":
    main(Path(sys.argv[1]))
