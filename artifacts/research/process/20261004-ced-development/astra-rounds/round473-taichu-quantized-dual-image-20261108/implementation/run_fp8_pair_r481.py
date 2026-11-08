"""One official FP8 load and four preregistered real paired-image requests."""

import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import time
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from process_pair import CACHE, HERE, ROOT, process
from r478_adapter import EMBEDDER, R478, prepare


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False, default=str)
        stream.write("\n")


def deadline(_signal, _frame):
    raise TimeoutError("preregistered stage deadline or external termination")


def run():
    raw = CACHE / "actual/model-run-b-r481"
    raw.mkdir(exist_ok=False)
    state = {"route": "B", "status": "STARTED", "created_at": datetime.now(UTC).isoformat(),
             "pid": os.getpid(), "actual_requests": [], "planned_requests": 4,
             "requests_started": 0, "inference_calls_started": 0,
             "loader_adapter_round": "R478", "historical_failed_loads": 1, "historical_processor_failures_after_load": 1,
             "dependency_adapter_round": "R481",
             "real_hardware_dispatch": False, "formal_acceptance": "NOT_PERFORMED"}
    sampler = None
    model = None
    model_class = None
    original_patterns = None
    stage = "admission"
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGTERM, deadline)
    lock = (ROOT / "cache/research/.r468-r469-gpu.lock").open("a+")
    sample_stdout = (raw / "gpu-200ms.csv").open("xb")
    sample_stderr = (raw / "gpu-sampler.stderr").open("xb")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, check=True, timeout=10)
        compute = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                                  "--format=csv,noheader"], capture_output=True, text=True, check=True, timeout=10)
        state["admission"] = {"gpu": gpu.stdout, "compute": compute.stdout}
        free_mib = int(gpu.stdout.strip().rsplit(",", 1)[1])
        if free_mib < 14000 or compute.stdout.strip():
            state["status"] = "INSUFFICIENT_RESOURCES"
            return
        processor_gate = json.loads((HERE / "steps/processor-b-r481.json").read_text())
        dependency_gate = json.loads((R478.parent / "round481-taichu-processor-required-imports-20261108/dependency-verification.json").read_text())
        if (processor_gate.get("status") != "PASS"
                or processor_gate.get("input_image_count") != 2
                or not processor_gate.get("processor_two_distinct_images")
                or dependency_gate.get("status") != "PASS"
                or not dependency_gate.get("original_64_versions_unchanged")):
            raise ValueError("R481 dependency or complete paired-image processor gate not passed")
        before = json.loads((HERE / "source-manifest.json").read_text())
        for row in before["files"]:
            if hashlib.sha256((CACHE / row["name"]).read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("official source drift before load")
        import torch
        from transformers import AutoModel, AutoProcessor, CompressedTensorsConfig

        torch.manual_seed(0)
        state["torch"] = torch.__version__
        state["cuda"] = torch.version.cuda
        state["capability"] = list(torch.cuda.get_device_capability(0))
        sampler = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,memory.free,utilization.gpu",
                                    "--format=csv,noheader,nounits", "--loop-ms=200"],
                                   stdout=sample_stdout, stderr=sample_stderr, start_new_session=True)
        state["sampler_pid"] = sampler.pid
        meta_gate = json.loads((R478 / "meta-scope-verification-v3-detailed.json").read_text())
        if (meta_gate.get("status") != "PASS" or not meta_gate.get("all_parameters_meta")
                or meta_gate.get("cpu_buffer_bytes", 2**63) > 64 * 1024**2):
            raise ValueError("R478 meta scope gate not passed")
        config, model_class, original_patterns, adapter_evidence = prepare()
        if (meta_gate.get("selected_modules") != adapter_evidence["fp8_modules"]
                or meta_gate.get("checkpoint_header_sha256") != adapter_evidence["checkpoint_header_sha256"]):
            raise ValueError("R478 meta evidence no longer matches current checkpoint scope")
        save(raw / "adapter-evidence.json", adapter_evidence)
        quantization = CompressedTensorsConfig.from_dict(config.quantization_config,
                                                       use_optimized_inference=True, dequantize=False)
        stage = "load"
        signal.alarm(600)
        started = time.perf_counter()
        model, loading = model_class.from_pretrained(
            str(CACHE), config=config, trust_remote_code=True, local_files_only=True, dtype=torch.bfloat16,
            device_map={"": "cuda:0"}, attn_implementation="sdpa", quantization_config=quantization,
            output_loading_info=True)
        model.eval()
        torch.cuda.synchronize()
        state["model_load_s"] = time.perf_counter() - started
        signal.alarm(0)
        save(raw / "loading-info.json", loading)
        save(raw / "model-config.json", model.config.to_dict())
        save(raw / "generation-config.json", model.generation_config.to_dict())

        def inventory():
            layers = [{"name": name, "type": type(module).__name__, "dtype": str(module.weight.dtype),
                       "shape": list(module.weight.shape), "device": str(module.weight.device)}
                      for name, module in model.named_modules()
                      if type(module).__name__ == "CompressedTensorsFP8Linear"]
            counts = Counter()
            for parameter in model.parameters():
                counts[str(parameter.dtype)] += parameter.numel()
            return {"fp8_layers": layers, "parameter_numel_by_dtype": dict(counts),
                    "all_parameters_cuda": all(p.device.type == "cuda" for p in model.parameters()),
                    "use_fp8_kernel": getattr(model.hf_quantizer, "use_fp8_kernel", False)}

        loaded = inventory()
        save(raw / "quantized-load-inventory.json", loaded)
        state["fp8_layer_count"] = len(loaded["fp8_layers"])
        if (not loaded["fp8_layers"] or not loaded["all_parameters_cuda"] or not loaded["use_fp8_kernel"]
                or any("float8" not in row["dtype"] for row in loaded["fp8_layers"])):
            state["status"] = "BLOCKED_FORMAT_RUNTIME"
            return
        if loading.get("missing_keys") or loading.get("mismatched_keys") or loading.get("error_msgs"):
            state["status"] = "LOAD_MISSING_WEIGHTS"
            return
        unexplained = [key for key in loading.get("unexpected_keys", [])
                       if not any(re.search(pattern, key) for pattern in original_patterns)]
        if unexplained:
            state["status"] = "UNEXPLAINED_UNEXPECTED_WEIGHTS"
            state["unexplained_unexpected_keys"] = unexplained
            return
        embedder = model.get_submodule(EMBEDDER)
        state["embedder"] = {"class": type(embedder).__name__, "dtype": str(embedder.weight.dtype),
                             "has_weight_scale": hasattr(embedder, "weight_scale")}
        state["effective_attention"] = {"top": model.config._attn_implementation,
            "llm": model.language_model.config._attn_implementation,
            "vision_use_flash_attn": model.config.vision_config.use_flash_attn}
        if (sorted(row["name"] for row in loaded["fp8_layers"]) != adapter_evidence["fp8_modules"]
                or embedder.weight.dtype != torch.bfloat16
                or type(embedder).__name__ != meta_gate["embedder_class_before"]
                or hasattr(embedder, "weight_scale")
                or state["effective_attention"] != {"top": "sdpa", "llm": "sdpa", "vision_use_flash_attn": False}):
            state["status"] = "LOADED_QUANTIZATION_SCOPE_MISMATCH"
            return
        state["compressed_load"] = "PASS"
        processor = AutoProcessor.from_pretrained(str(CACHE), trust_remote_code=True,
                                                 local_files_only=True, use_fast=False)
        for index in range(4):
            stage = f"request-{index+1}"
            state["requests_started"] += 1
            request_dir = raw / f"request-{index+1}"
            request_dir.mkdir(exist_ok=False)
            signal.alarm(180)
            beginning = time.perf_counter()
            features, evidence = process(processor)
            save(request_dir / "processor-evidence.json", evidence)
            save(request_dir / "input-token-ids.json", features["input_ids"].tolist())
            (request_dir / "decoded-input.txt").write_text(
                processor.tokenizer.decode(features["input_ids"][0].tolist(), skip_special_tokens=False))
            features = features.to("cuda:0")
            input_tokens = features["input_ids"].shape[-1]
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            generation_start = time.perf_counter()
            state["inference_calls_started"] += 1
            with torch.inference_mode():
                output = model.generate(**features, do_sample=False, max_new_tokens=512,
                                        num_beams=1, use_cache=True, return_dict_in_generate=False,
                                        output_scores=False)
            torch.cuda.synchronize()
            generation_s = time.perf_counter() - generation_start
            ids = output[0, input_tokens:].tolist()
            text = processor.tokenizer.decode(ids, skip_special_tokens=True)
            text_with_special = processor.tokenizer.decode(ids, skip_special_tokens=False)
            (request_dir / "raw-response.txt").write_text(text)
            (request_dir / "raw-response-with-special-tokens.txt").write_text(text_with_special)
            save(request_dir / "output-token-ids.json", ids)
            after = inventory()
            preserved = all("float8" in row["dtype"] for row in after["fp8_layers"])
            attempt = {"index": index+1, "kind": "first-inference-after-corrected-reload" if index == 0 else f"warm{index}",
                       "status": "COMPLETED", "input_tokens": input_tokens, "output_tokens": len(ids),
                       "processor_s": evidence["processor_s"], "generation_s": generation_s,
                       "end_to_end_s": time.perf_counter()-beginning,
                       "torch_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                       "torch_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                       "fp8_weights_preserved": preserved,
                       "raw_response_sha256": hashlib.sha256(text.encode()).hexdigest(),
                       "raw_directory": str(request_dir), "ttft": "NOT_MEASURED"}
            save(request_dir / "attempt.json", attempt)
            state["actual_requests"].append(attempt)
            print("REQUEST_COMPLETED", index+1, len(ids), round(generation_s, 3), preserved, flush=True)
            signal.alarm(0)
            if not preserved:
                state["status"] = "FP8_NOT_PRESERVED"
                return
        state["status"] = "FOUR_REQUESTS_COMPLETED"
        save(raw / "quantized-final-inventory.json", inventory())
    except Exception as error:
        state.update(status="FAILED", failed_stage=stage, error_type=type(error).__name__,
                     error=str(error), traceback=traceback.format_exc())
        if "out of memory" in str(error).lower():
            state["status"] = "LOAD_OOM" if stage == "load" else "INFERENCE_OOM"
        elif isinstance(error, TimeoutError):
            state["status"] = "TIMEOUT"
        (raw / "exception.txt").write_text(state["traceback"])
        print(state["traceback"], flush=True)
    finally:
        signal.alarm(0)
        if sampler is not None:
            sampler.terminate()
            try:
                sampler.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sampler.kill()
                sampler.wait(timeout=5)
            state["sampler_returncode"] = sampler.returncode
        sample_stdout.close()
        sample_stderr.close()
        if model is not None:
            del model
        if model_class is not None:
            model_class._keys_to_ignore_on_load_unexpected = original_patterns
        state["finished_at"] = datetime.now(UTC).isoformat()
        save(raw / "run-result.json", state)
        save(HERE / "steps/model-run-b-r481-result.json", state)
        lock.close()
        print("RUN_RESULT", state["status"], len(state["actual_requests"]), flush=True)


if __name__ == "__main__":
    run()
