"""Record the planned schema, official architecture and processor import gates."""

import importlib.metadata
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                  HF_HOME=str(CACHE / "hf-runtime"), HF_MODULES_CACHE=str(CACHE / "hf-modules"))


def main():
    route = sys.argv[1]
    result = {"route": route, "created_at": datetime.now(UTC).isoformat(),
              "model_weights_loaded": False, "packages": {}}
    for name in ["torch", "torchvision", "transformers", "compressed-tensors", "pydantic"]:
        result["packages"][name] = importlib.metadata.version(name)
    try:
        import torch
        from transformers import AutoConfig, AutoProcessor, CompressedTensorsConfig
        from transformers.dynamic_module_utils import get_class_from_dynamic_module
        from transformers.quantizers.quantizer_compressed_tensors import CompressedTensorsHfQuantizer

        raw = json.loads((CACHE / "config.json").read_text())
        options = ({"run_compressed": True} if route == "A" else
                   {"use_optimized_inference": True, "dequantize": False})
        quantization = CompressedTensorsConfig.from_dict(raw["quantization_config"], **options)
        loader = CompressedTensorsHfQuantizer(quantization)
        loader.validate_environment()
        result["schema"] = "PASS"
        result["run_compressed"] = getattr(quantization, "run_compressed", None)
        result["use_fp8_kernel"] = getattr(loader, "use_fp8_kernel", None)
        if route == "B" and result["use_fp8_kernel"] is not True:
            raise ValueError("B runtime did not enable actual FP8 kernels")
        result["format"] = raw["quantization_config"]["format"]
        config = AutoConfig.from_pretrained(str(CACHE), trust_remote_code=True, local_files_only=True)
        model_class = get_class_from_dynamic_module(config.auto_map["AutoModel"], str(CACHE),
                                                   local_files_only=True)
        result["architecture"] = model_class.__name__
        processor = AutoProcessor.from_pretrained(str(CACHE), trust_remote_code=True,
                                                 local_files_only=True, use_fast=False)
        result["processor"] = type(processor).__name__
        result["torch_cuda"] = torch.version.cuda
        result["cuda_available"] = torch.cuda.is_available()
        result["status"] = "PASS"
    except Exception as error:
        result.update(status="DEPENDENCY_OR_FORMAT_INCOMPATIBLE", error_type=type(error).__name__,
                      error=str(error), traceback=traceback.format_exc())
        print(result["traceback"], file=sys.stderr)
    with (HERE / f"steps/runtime-{route.lower()}-preflight.json").open("x") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
