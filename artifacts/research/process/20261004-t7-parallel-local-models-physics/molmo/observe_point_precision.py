"""Read actual loaded precision once; execute the unchanged registered bridge.

No model/class patch, forward hook, generation change, tensor copies or online
oracle. The Python profile is disabled at constructor return, before inspecting
metadata and before every timed inference. Loaded allocator totals include
unregistered quantization buffers; parameter byte counts do not.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import time
from pathlib import Path

import native_bridge as bridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--precision-observation", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.precision_observation.exists():
        raise FileExistsError("exclusive precision evidence already exists")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    registration = json.loads(
        (bridge.HERE / "MolmoPoint-first-gpu-prospective-registration.json").read_text()
    )
    for filename, key in (
        ("native_bridge.py", "bridge_sha256"),
        ("native_adapter.py", "native_adapter_sha256"),
    ):
        if hashlib.sha256((bridge.HERE / filename).read_bytes()).hexdigest() != registration[key]:
            raise ValueError("registered source changed before Point launch")
    observed = False
    profile_started = None

    def observe_constructor(frame, event, arg):
        nonlocal observed
        if event != "return" or frame.f_code is not bridge.NativeMolmo.__init__.__code__:
            return
        constructor_returned = time.perf_counter()
        sys.setprofile(None)
        if sys.getprofile() is not None:
            raise RuntimeError("startup profile was not disabled")
        instance = frame.f_locals["self"]
        if not hasattr(instance, "model"):
            return
        model = instance.model
        modules = collections.Counter()
        int8_modules = []
        for name, module in model.named_modules():
            qualified_class = type(module).__module__ + "." + type(module).__name__
            modules[qualified_class] += 1
            if type(module).__name__ == "Linear8bitLt":
                int8_modules.append(name)
        groups = {}
        bf16_parameters = []
        non_cuda_parameters = []
        for name, parameter in model.named_parameters():
            key = " | ".join(
                (str(parameter.dtype), str(parameter.device),
                 type(parameter).__module__ + "." + type(parameter).__name__)
            )
            group = groups.setdefault(key, {"tensors": 0, "elements": 0, "metadata_bytes": 0})
            group["tensors"] += 1
            group["elements"] += parameter.numel()
            group["metadata_bytes"] += parameter.numel() * parameter.element_size()
            if str(parameter.dtype) == "torch.bfloat16":
                bf16_parameters.append({"name": name, "elements": parameter.numel()})
            if parameter.device.type != "cuda":
                non_cuda_parameters.append({"name": name, "device": str(parameter.device)})
        torch = instance.torch
        record = {
            "scope": "actual loaded module and parameter metadata; no tensor values, copies, model calls or GT",
            "observer_disabled_before_metadata_and_timed_inference": sys.getprofile() is None,
            "profile_interval": "immediately before unchanged CLI main until NativeMolmo.__init__ returns; no inference",
            "profile_interval_wall_s": constructor_returned - profile_started,
            "metadata_observer_wall_s_excluding_artifact_write": time.perf_counter() - constructor_returned,
            "cold_load_note": "original bridge load_seconds includes Python constructor profile overhead; metadata observer runs after it and before task timing",
            "bridge_sha256": hashlib.sha256((bridge.HERE / "native_bridge.py").read_bytes()).hexdigest(),
            "observer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "model": instance.name,
            "gpu_lease": instance.gpu_lease,
            "load_seconds": instance.load_seconds,
            "quantization_config": model.config.quantization_config.to_dict()
                if hasattr(model.config.quantization_config, "to_dict")
                else model.config.quantization_config,
            "is_loaded_in_8bit": getattr(model, "is_loaded_in_8bit", None),
            "hf_device_map": getattr(model, "hf_device_map", None),
            "module_class_counts": dict(modules),
            "Linear8bitLt_count": len(int8_modules),
            "Linear8bitLt_module_names": int8_modules,
            "parameter_groups": groups,
            "BF16_parameter_names_and_elements": bf16_parameters,
            "non_CUDA_parameter_names": non_cuda_parameters,
            "allocator_load_current_bytes": torch.cuda.memory_allocated(),
            "allocator_load_peak_bytes": torch.cuda.max_memory_allocated(),
            "allocator_load_reserved_bytes": torch.cuda.memory_reserved(),
            "parameter_bytes_note": "metadata estimate excludes unregistered quantization buffers; not runtime VRAM",
        }
        bridge.write_exclusive_json(args.precision_observation, record)
        observed = True

    sys.argv = [str(bridge.HERE / "native_bridge.py"), *command]
    profile_started = time.perf_counter()
    sys.setprofile(observe_constructor)
    try:
        bridge.main()
    finally:
        sys.setprofile(None)
        if not observed and not args.precision_observation.exists():
            bridge.write_exclusive_json(args.precision_observation, {
                "scope": "observer status; raw model-load failure preserved by original bridge",
                "actual_loaded_model_observed": False,
                "runtime_precision": "unmeasured",
                "observer_disabled": True,
            })


if __name__ == "__main__":
    main()
