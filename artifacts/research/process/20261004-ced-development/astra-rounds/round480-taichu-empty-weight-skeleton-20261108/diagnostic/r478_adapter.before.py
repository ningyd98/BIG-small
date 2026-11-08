"""Narrow in-memory compatibility for unchanged official FP8 checkpoint bytes."""

import copy
import hashlib
import json
import math
import re
import struct
import sys
import traceback
from pathlib import Path

from process_pair import CACHE, HERE

R478 = HERE.parent / "round478-taichu-loader-api-scope-20261108"
EMBEDDER = "vision_model.radio_model.model.patch_generator.embedder"


def prepare():
    from transformers import AutoConfig
    from transformers.dynamic_module_utils import get_class_from_dynamic_module

    path = CACHE / "model.safetensors"
    with path.open("rb") as stream:
        length = struct.unpack("<Q", stream.read(8))[0]
        header_bytes = stream.read(length)
    header = json.loads(header_bytes)
    weights = {name: value for name, value in header.items()
               if isinstance(value, dict) and value.get("dtype", "").startswith("F8")}
    if len(weights) != 248 or any(not name.endswith(".weight") for name in weights):
        raise ValueError("unexpected FP8 checkpoint parameter set")
    modules = sorted(name[:-len(".weight")] for name in weights)
    for module in modules:
        weight = header[module + ".weight"]
        scale = header.get(module + ".weight_scale")
        if (scale is None or len(weight["shape"]) != 2
                or math.prod(scale["shape"]) != weight["shape"][0]):
            raise ValueError("FP8 channel scale does not match checkpoint weight")
    config = AutoConfig.from_pretrained(str(CACHE), trust_remote_code=True, local_files_only=True)
    # Match the already selected R473 SDPA runtime in every nested configuration.
    attention_before = {"top": config._attn_implementation,
                        "llm": config.llm_config._attn_implementation,
                        "vision_use_flash_attn": config.vision_config.use_flash_attn}
    config._attn_implementation = "sdpa"
    config.llm_config._attn_implementation = "sdpa"
    config.vision_config.use_flash_attn = False
    model_class = get_class_from_dynamic_module(config.auto_map["AutoModel"], str(CACHE), local_files_only=True)
    original_patterns = model_class._keys_to_ignore_on_load_unexpected
    if not isinstance(original_patterns, (list, set)):
        raise ValueError("unexpected official ignore metadata type")
    model_class._keys_to_ignore_on_load_unexpected = set(original_patterns)
    if set(original_patterns) != model_class._keys_to_ignore_on_load_unexpected:
        raise ValueError("ignore metadata semantic drift")
    derived = copy.deepcopy(config)
    before = copy.deepcopy(config.quantization_config)
    after = copy.deepcopy(before)
    if after["config_groups"]["group_0"]["targets"] != ["Linear"]:
        raise ValueError("unexpected original target scope")
    after["config_groups"]["group_0"]["targets"] = ["re:^" + re.escape(name) + "$" for name in modules]
    restored = copy.deepcopy(after)
    restored["config_groups"]["group_0"]["targets"] = before["config_groups"]["group_0"]["targets"]
    if restored != before:
        raise ValueError("configuration changed beyond target scope")
    derived.quantization_config = after
    evidence = {"checkpoint_header_sha256": hashlib.sha256(header_bytes).hexdigest(),
                "runtime_attention_before": attention_before,
                "runtime_attention_after": {"top": config._attn_implementation,
                    "llm": config.llm_config._attn_implementation,
                    "vision_use_flash_attn": config.vision_config.use_flash_attn},
                "original_ignore_type": type(original_patterns).__name__,
                "original_ignore_patterns": sorted(original_patterns),
                "adapted_ignore_patterns": sorted(model_class._keys_to_ignore_on_load_unexpected),
                "only_quantization_targets_changed": True, "fp8_modules": modules,
                "quantization_before": before, "quantization_after": after}
    return derived, model_class, original_patterns, evidence


def main():
    import torch
    from transformers import CompressedTensorsConfig
    from transformers.quantizers.quantizer_compressed_tensors import CompressedTensorsHfQuantizer

    model_class = None
    original = None
    result = {"status": "FAILED"}
    try:
        config, model_class, original, evidence = prepare()
        with torch.device("meta"):
            model = model_class._from_config(config, attn_implementation="sdpa")
        before_classes = {name: type(module).__name__ for name, module in model.named_modules()}
        embedder_before = type(model.get_submodule(EMBEDDER)).__name__
        quantization = CompressedTensorsConfig.from_dict(config.quantization_config,
                                                       use_optimized_inference=True, dequantize=False)
        loader = CompressedTensorsHfQuantizer(quantization)
        loader.validate_environment()
        loader._process_model_before_weight_loading(model)
        selected = sorted(name for name, module in model.named_modules()
                          if type(module).__name__ == "CompressedTensorsFP8Linear")
        expected = evidence["fp8_modules"]
        embedder = model.get_submodule(EMBEDDER)
        if (selected != expected or type(embedder).__name__ != embedder_before
                or hasattr(embedder, "weight_scale") or not loader.use_fp8_kernel):
            raise ValueError("meta replacement scope is not an exact checkpoint match")
        result = {"status": "PASS", **evidence, "selected_modules": selected,
                  "module_mapping": [{"name": name, "before": before_classes[name],
                                      "after": type(model.get_submodule(name)).__name__} for name in selected],
                  "embedder_class_before": embedder_before, "embedder_class_after": type(embedder).__name__,
                  "embedder_has_scale": False, "meta_weights_are_not_real_weight_evidence": True,
                  "use_fp8_kernel": loader.use_fp8_kernel}
    except Exception as error:
        result = {"status": "FAILED", "error": str(error), "traceback": traceback.format_exc()}
        print(result["traceback"], file=sys.stderr)
    finally:
        if model_class is not None:
            model_class._keys_to_ignore_on_load_unexpected = original
        with (R478 / "meta-scope-verification-v2.json").open("x") as stream:
            json.dump(result, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print("META_SCOPE", result["status"], len(result.get("selected_modules", [])), flush=True)


if __name__ == "__main__":
    main()
