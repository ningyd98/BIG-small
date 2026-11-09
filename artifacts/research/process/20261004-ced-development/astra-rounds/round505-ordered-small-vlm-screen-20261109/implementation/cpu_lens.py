"""No-weight/no-generation CPU qualification of the pinned Lens SDK and inputs."""

import hashlib
import importlib.metadata
import inspect
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
SDK = CACHE / "sdk/Xiaomi-Lens-0-9ecbee757b"
MODEL = CACHE / "models/Xiaomi-Lens-0"
OUT = HERE / "candidates/03-lens"
sys.path.insert(0, str(SDK))
sys.path.insert(0, str(SDK / "src"))
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"),
                  HF_MODULES_CACHE=str(CACHE / "hf-modules"))


def main():
    started = time.monotonic()
    import torch
    from PIL import Image
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoProcessor
    from xiaomi_lens.model.modeling_xiaomi_lens import XiaomiLensQwen3_5ForConditionalGeneration
    import infer
    from lens_adapter import build_inputs, native_prompt, tensor_evidence, verify_public_case, normalize_lens
    from score_native import assert_public_inputs

    public = json.loads((HERE / "diagnostic/model-inputs.json").read_text())
    assert_public_inputs(public)
    processor = AutoProcessor.from_pretrained(str(MODEL), local_files_only=True)
    config = AutoConfig.from_pretrained(str(MODEL), local_files_only=True)
    config._attn_implementation = "sdpa"
    config.text_config._attn_implementation = "sdpa"
    config.vision_config._attn_implementation = "sdpa"
    with init_empty_weights(include_buffers=False):
        model = XiaomiLensQwen3_5ForConditionalGeneration(config)
    assert all(value.device.type == "meta" for value in model.parameters())
    assert hasattr(model, "mask_decoder") and hasattr(model.model, "compute_3d_position_ids")
    meta = {"parameters": sum(p.numel() for p in model.parameters()), "mask_parameters": sum(p.numel() for p in model.mask_decoder.parameters()),
            "parameters_all_meta": True, "class": type(model).__name__, "official_loader_signature": str(inspect.signature(infer.load_model_and_processor))}
    del model
    cases = []
    for row in public["cases"]:
        image = Image.open(verify_public_case(ROOT, row)).convert("RGB")
        modes = {}
        for kind in ("target", "destination"):
            prompt = native_prompt(row[kind + "_phrase"])
            inputs, text = build_inputs(processor, image, prompt, torch.device("cpu"))
            assert text.endswith("<think>\n\n</think>\n\n")
            assert len(inputs["image_grid_thw"]) == 1
            assert inputs["input_ids"].shape[-1] < 8192
            modes[kind] = {"prompt": prompt, "rendered_sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "features": tensor_evidence(inputs)}
        cases.append({"id": row["id"], "modes": modes})
    assert infer.parse_answer_bboxes('<bbox>[250, 250, 750, 750]</bbox><mask><|mask|></mask>') == [[250, 250, 750, 750]]
    assert normalize_lens(infer, "None<|im_end|>", None, 320, 240)["mask"]["status"] == "REFUSAL"
    assert normalize_lens(infer, "malformed response", None, 320, 240)["mask"]["status"] == "INVALID"
    fake = torch.ones((1, 1, 4, 4))
    normalized = normalize_lens(infer, '<bbox>[250, 250, 750, 750]</bbox><mask><|mask|></mask>', fake, 320, 240)
    assert normalized["box"]["point"] == [160, 120]
    assert normalized["mask"]["point"] == [159, 119]
    versions = {name: importlib.metadata.version(name) for name in ["torch", "torchvision", "transformers", "accelerate", "numpy", "pillow", "safetensors"]}
    sdk_hashes = [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                  for p in sorted(SDK.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    result = {"status": "PASS", "model_weight_loads": 0, "generation_calls": 0, "device": "CPU_META_ONLY",
        "model_meta": meta, "versions": versions, "thinking": False, "cases": cases,
        "supported_native_modes": ["mask", "box"], "primary_mode": "mask", "point_mode": "UNSUPPORTED",
        "dual": "UNSUPPORTED_BY_PUBLISHED_INFER_HELPER", "attention": "sdpa via official public loader argument",
        "mask_threshold": "raw logit >=0 (official sigmoid probability >=0.5)", "coordinate_system": "normalized_1000",
        "sdk_commit": "9ecbee757b5b807a4c5854aeed44ed8cfec10bae", "sdk_files": sdk_hashes,
        "elapsed_s": time.monotonic() - started}
    with (OUT / "cpu-contract.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("LENS_CPU_PASS", len(cases), versions, flush=True)


if __name__ == "__main__":
    main()
