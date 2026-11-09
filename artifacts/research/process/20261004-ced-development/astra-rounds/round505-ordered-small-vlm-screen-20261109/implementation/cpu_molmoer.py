"""R507 real-checkpoint CPU import/input gate. No weights or generation."""
import hashlib
import importlib
import json
import os
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
OUT = HERE / "candidates/04-molmoer"
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"),
                  HF_MODULES_CACHE=str(CACHE / "hf-modules-molmoer-r507"), PYTHONDONTWRITEBYTECODE="1")


def main():
    import torch
    import transformers
    from transformers import AutoConfig, AutoProcessor
    from transformers.dynamic_module_utils import get_class_from_dynamic_module
    from molmoer_adapter import build_inputs, tensor_evidence
    from score_native import assert_public_inputs
    assert transformers.__version__ == "4.57.1"
    assert not any("runtime-b" in path for path in sys.path)
    versions = {}
    for name in ("torch", "torchvision", "transformers", "tokenizers", "huggingface_hub"):
        module = importlib.import_module(name)
        versions[name] = {"version": module.__version__, "file": module.__file__}
    assert versions["tokenizers"]["version"] == "0.22.1"
    model = str(CACHE / "models/Molmo2-ER")
    config = AutoConfig.from_pretrained(model, trust_remote_code=True, local_files_only=True)
    cls = get_class_from_dynamic_module(config.auto_map["AutoModelForImageTextToText"], model, local_files_only=True)
    processor = AutoProcessor.from_pretrained(model, trust_remote_code=True, local_files_only=True, use_fast=False, padding_side="left")
    public = json.loads((HERE / "diagnostic/model-inputs.json").read_text())
    assert_public_inputs(public)
    dual = {r["id"]: r for r in json.loads((HERE / "diagnostic/model-inputs-dual.json").read_text())["cases"]}
    rows = []
    for case in public["cases"]:
        row = {"id": case["id"], "modes": {}}
        for kind in ("target", "destination"):
            inputs = {**case, "phrase": case[kind + "_phrase"]}
            features, text = build_inputs(processor, inputs, ROOT)
            assert int(features["image_num_crops"].numel()) == 1
            assert features["input_ids"].shape[1] + 512 < 16384
            row["modes"][kind] = {"rendered_sha256": hashlib.sha256(text.encode()).hexdigest(), "features": tensor_evidence(features)}
        merged = {**case, **dual[case["id"]], "phrase": case["target_phrase"]}
        features, text = build_inputs(processor, merged, ROOT, dual=True)
        assert int(features["image_num_crops"].numel()) == 2
        row["dual_cpu_only"] = {"rendered_sha256": hashlib.sha256(text.encode()).hexdigest(), "features": tensor_evidence(features)}
        rows.append(row)
    try:
        processor.apply_chat_template([{"role": "system", "content": "Original system role must remain system."},
                                       {"role": "user", "content": "test"}], tokenize=False, add_generation_prompt=True)
        raise AssertionError("published template unexpectedly accepts system role")
    except Exception as error:
        assert "Conversation roles must alternate user/assistant" in str(error)
        system = {"status": "UNSUPPORTED_SYSTEM_ROLE", "exception_type": type(error).__name__, "message": str(error)}
    assert not torch.cuda.is_initialized()
    result = {"status": "PASS", "versions": versions, "sys_path": sys.path, "python": sys.executable,
              "model_class": cls.__name__, "processor_class": type(processor).__name__, "cases": rows,
              "system_role": system, "dual_image_processor": "PASS_16_SEPARATE_RGB_AND_DEPTH_IMAGES_NO_GENERATION",
              "model_loads": 0, "generation_calls": 0, "cuda_initialized": False}
    with (OUT / "cpu-contract-r507.json").open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("MOLMOER_CPU_PASS", len(rows), flush=True)


if __name__ == "__main__":
    main()
