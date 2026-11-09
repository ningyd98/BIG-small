"""Bind the preauthorized R505 stages to frozen official Lens source and inputs."""

import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
SDK = CACHE / "sdk/Xiaomi-Lens-0-9ecbee757b"
MODEL = CACHE / "models/Xiaomi-Lens-0"
OUT = HERE / "candidates/03-lens"
sys.path.insert(0, str(SDK))
sys.path.insert(0, str(SDK / "src"))
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import torch
    from PIL import Image
    from transformers import AutoProcessor
    from lens_adapter import build_json_inputs, tensor_evidence
    cpu = json.loads((OUT / "cpu-contract.json").read_text())
    assert cpu["status"] == "PASS"
    assets = json.loads((OUT / "download-result.json").read_text())
    assert assets["status"] == "PASS"
    # Full hashes already checked during download; stat every immutable file now.
    for row in assets["files"]:
        assert Path(row["path"]).stat().st_size == row["size"]
    source = json.loads((HERE.parent / "round501-taichu-captured-multiscene-20261108/diagnostic/frozen-message-inputs.json").read_text())
    public = json.loads((HERE / "diagnostic/model-inputs.json").read_text())
    original_systems = {row["messages"][0]["content"] for row in source}
    assert len(original_systems) == 1
    original = original_systems.pop()
    initial = "Inspect image 1 (RGB) to identify the requested object and destination. Image 2 is aligned depth for spatial context."
    assert original.startswith(initial)
    system = "Inspect the RGB image to identify the requested object and destination." + original[len(initial):]
    processor = AutoProcessor.from_pretrained(str(MODEL), local_files_only=True)
    json_rows = []
    for case in public["cases"]:
        image = Image.open(ROOT / case["rgb_path"]).convert("RGB")
        features, text = build_json_inputs(processor, image, system, case["instruction"], torch.device("cpu"))
        assert len(features["image_grid_thw"]) == 1 and features["input_ids"].shape[1] < 8192
        json_rows.append({"id": case["id"], "system": system, "instruction": case["instruction"],
                          "rendered_sha256": hashlib.sha256(text.encode()).hexdigest(), "features": tensor_evidence(features)})
    json_path = OUT / "json-rgb-cpu-contract.json"
    with json_path.open("x") as stream:
        json.dump({"status": "PASS", "cases": json_rows, "model_generations": 0}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    own_sources = [HERE / "implementation" / name for name in ["score_native.py", "lens_adapter.py", "cpu_lens.py", "prepare_lens_protocol.py", "run_candidate_lens.py"]]
    protocol = {"candidate": "03-lens", "official_model_repo": "SeerRay-Lab/Xiaomi-Lens-0",
        "official_modelscope_link_from_SDK_readme": "https://modelscope.cn/models/SeerRay-Lab/Xiaomi-Lens-0",
        "source_metadata_sha256": assets["source_metadata_sha256"], "asset_manifest_sha256": sha(OUT / "asset-manifest.json"),
        "weight_hash_verification": "PASS during complete download; files kept local; no direct HF equivalence claim",
        "model_directory": str(MODEL), "sdk_directory": str(SDK), "sdk_commit": cpu["sdk_commit"],
        "precision": "BF16 full model including original vision and native mask decoder; no quantization",
        "runtime": str(CACHE / "runtimes/lens-r505/bin/python"), "versions": cpu["versions"],
        "attention": "sdpa through official load_model_and_processor argument; original FLA0.6 overlay visible; actual CUDA binding captured in GPU process",
        "thinking": False, "native_modes": ["mask", "box"], "primary_mode": "mask", "native_point": "UNSUPPORTED",
        "reuse_modalities": "one bbox+mask completion scored in both native modes, unique actual calls counted once",
        "warm_repetitions": "after complete native screen, repeat case-0001 target twice; same two results cover both modes",
        "generation": {"do_sample": False, "num_beams": 1, "use_cache": True, "max_new_tokens": 512, "seed": 0},
        "native_prompt_template": 'Locate all instances in the image that match the description "{phrase}". Report bbox coordinates and masks. If no matching instance is visible, return None.',
        "official_output": "final <bbox>[x1,y1,x2,y2]</bbox><mask><|mask|></mask>; normalized0..1000; official thought-mask exclusion",
        "absence_exact_bodies_case_insensitive": ["", "None", "None.", "null", "[]", "<bbox>None</bbox>"],
        "mask_threshold": "official sigmoid >=0.5; equivalent raw logit >=0; nearest resize to original",
        "derived_point": "predicted foreground nearest its own centroid, tie y,x; boxes geometric center floor; first output only, never oracle",
        "JSON_RGB": "16 requests, original R501 system with only two-image opening replaced by single-RGB opening",
        "JSON_DUAL": "UNSUPPORTED_BY_PUBLISHED_INFER_HELPER; not claimed through underlying backbone",
        "authorized_model_loads": 1, "authorized_generation_calls": 50, "request_timeout_s": 900,
        "public_inputs_sha256": sha(HERE / "diagnostic/model-inputs.json"), "json_inputs_sha256": sha(json_path),
        "cpu_contract_sha256": sha(OUT / "cpu-contract.json"), "plan_sha256": sha(HERE / "plan.json"),
        "research_sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in own_sources],
        "formal_acceptance": "NOT_PERFORMED", "hardware_dispatch": False}
    with (OUT / "protocol.json").open("x") as stream:
        json.dump(protocol, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("LENS_PROTOCOL_FROZEN", sha(OUT / "protocol.json"), "50 total generation calls maximum", flush=True)


if __name__ == "__main__":
    main()
