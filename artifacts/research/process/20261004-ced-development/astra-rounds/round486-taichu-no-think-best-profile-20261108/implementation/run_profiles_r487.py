"""One FP8 load and the eight preregistered ON/OFF requests per runtime."""

import fcntl
import functools
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[7]
os.environ["TRITON_CACHE_DIR"] = str(TASK_ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/jit-round486/triton")
os.environ["TORCHINDUCTOR_CACHE_DIR"] = str(TASK_ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/jit-round486/inductor")

from experiment_r487 import BASELINE, CACHE, HERE, RAW, ROOT, base_versions, check_sources, kernel_bindings, mode_features, read, save
from r478_adapter import EMBEDDER, R478, prepare


def deadline(_signal, _frame):
    raise TimeoutError("R486 stage deadline reached")


def run(profile):
    if profile not in {"base", "fla"}:
        raise ValueError("unknown runtime profile")
    raw = RAW / ("run-" + profile + "-r487")
    raw.mkdir(parents=True, exist_ok=False)
    state = {"profile": profile, "status": "STARTED", "created_at": datetime.now(UTC).isoformat(),
             "pid": os.getpid(), "actual_requests": [], "requests_started": 0,
             "inference_calls_started": 0, "planned_requests": 8,
             "formal_acceptance": "NOT_PERFORMED", "real_hardware_dispatch": False}
    model = None
    model_class = None
    original_patterns = None
    sampler = None
    originals = {}
    qwen_module = None
    stage = "preflight"
    lock = (ROOT / "cache/research/.r468-r469-gpu.lock").open("a+")
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGTERM, deadline)
    try:
        check_sources()
        weight_gate = read(HERE / "weight-verification.json")
        weight = CACHE / "model.safetensors"
        signature = [weight.stat().st_size, weight.stat().st_mtime_ns, weight.stat().st_ctime_ns]
        if weight_gate["status"] != "PASS" or signature != weight_gate["stat_signature"]:
            raise ValueError("fixed weight byte verification no longer applies")
        processor_gate = read(HERE / ("processor-" + profile + ".json"))
        if processor_gate["status"] != "PASS":
            raise ValueError("full paired-image processor gate failed")
        state["base_68"] = base_versions()
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state["admission"] = []
        admitted = False
        for check in range(2):
            gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.free",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True, timeout=10)
            compute = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                                      "--format=csv,noheader"], capture_output=True, text=True, check=True, timeout=10)
            state["admission"].append({"gpu": gpu.stdout, "compute": compute.stdout})
            if int(gpu.stdout.strip().rsplit(",", 1)[1]) >= 14000 and not compute.stdout.strip():
                admitted = True
                break
            if check == 0:
                time.sleep(30)
        if not admitted:
            state["status"] = "INSUFFICIENT_RESOURCES"
            return

        import torch
        from transformers import AutoProcessor, CompressedTensorsConfig

        torch.manual_seed(0)
        state.update(torch=torch.__version__, cuda=torch.version.cuda,
                     capability=list(torch.cuda.get_device_capability(0)))
        sample_out = (raw / "gpu-200ms.csv").open("xb")
        sample_err = (raw / "gpu-sampler.stderr").open("xb")
        sampler = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,memory.free,utilization.gpu",
                                    "--format=csv,noheader,nounits", "--loop-ms=200"],
                                   stdout=sample_out, stderr=sample_err, start_new_session=True)
        sample_out.close()
        sample_err.close()
        state["sampler_pid"] = sampler.pid
        config, model_class, original_patterns, evidence = prepare()
        meta = read(R478 / "meta-scope-verification-v3-detailed.json")
        if meta["status"] != "PASS" or meta["selected_modules"] != evidence["fp8_modules"]:
            raise ValueError("exact FP8 replacement scope gate failed")
        save(raw / "adapter.json", evidence)
        quantization = CompressedTensorsConfig.from_dict(config.quantization_config,
                                                       use_optimized_inference=True, dequantize=False)
        stage = "load"
        signal.alarm(600)
        start = time.perf_counter()
        model, loading = model_class.from_pretrained(
            str(CACHE), config=config, trust_remote_code=True, local_files_only=True, dtype=torch.bfloat16,
            device_map={"": "cuda:0"}, attn_implementation="sdpa", quantization_config=quantization,
            output_loading_info=True)
        model.eval()
        torch.cuda.synchronize()
        state["model_load_s"] = time.perf_counter() - start
        signal.alarm(0)
        save(raw / "loading-info.json", loading)
        if any(loading.get(key) for key in ["missing_keys", "mismatched_keys", "error_msgs"]):
            raise ValueError("missing or mismatched model weights")
        if any(not any(re.search(pattern, key) for pattern in original_patterns)
               for key in loading.get("unexpected_keys", [])):
            raise ValueError("unexplained unexpected model weights")

        def inventory():
            layers = [{"name": name, "dtype": str(module.weight.dtype), "device": str(module.weight.device)}
                      for name, module in model.named_modules()
                      if type(module).__name__ == "CompressedTensorsFP8Linear"]
            return {"fp8_layers": layers, "all_parameters_cuda": all(p.device.type == "cuda" for p in model.parameters()),
                    "use_fp8_kernel": bool(model.hf_quantizer.use_fp8_kernel)}

        loaded = inventory()
        embedder = model.get_submodule(EMBEDDER)
        attention = {"top": model.config._attn_implementation,
                     "llm": model.language_model.config._attn_implementation,
                     "vision_use_flash_attn": model.config.vision_config.use_flash_attn}
        if (sorted(row["name"] for row in loaded["fp8_layers"]) != evidence["fp8_modules"]
                or not loaded["all_parameters_cuda"] or not loaded["use_fp8_kernel"]
                or any("float8" not in row["dtype"] for row in loaded["fp8_layers"])
                or type(embedder).__name__ != meta["embedder_class_before"]
                or embedder.weight.dtype != torch.bfloat16 or hasattr(embedder, "weight_scale")
                or attention != {"top": "sdpa", "llm": "sdpa", "vision_use_flash_attn": False}):
            raise ValueError("actual FP8/attention/BF16 scope mismatch")
        save(raw / "initial-inventory.json", loaded)
        save(raw / "model-config.json", model.config.to_dict())
        save(raw / "generation-config.json", model.generation_config.to_dict())
        state.update(compressed_load="PASS", effective_attention=attention, fp8_layer_count=248)
        qwen_module, bindings = kernel_bindings()
        if bindings != processor_gate["kernel_bindings"]:
            raise ValueError("effective kernel bindings changed after processor gate")
        save(raw / "kernel-bindings.json", bindings)
        counts = Counter()
        for name in bindings:
            original = getattr(qwen_module, name)
            originals[name] = original

            def counted(*args, _original=original, _name=name, **kwargs):
                counts[_name] += 1
                return _original(*args, **kwargs)

            setattr(qwen_module, name, functools.wraps(original)(counted))
        processor = AutoProcessor.from_pretrained(str(CACHE), trust_remote_code=True,
                                                 local_files_only=True, use_fast=False)
        schedule = read(HERE / "plan.json")["stage_A_order" if profile == "base" else "stage_B_order"]
        state["schedule"] = schedule
        mode_counts = Counter()
        eos = model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos, list) else [eos])
        think_end = processor.tokenizer.convert_tokens_to_ids("</think>")
        for index, mode in enumerate(schedule, 1):
            stage = "request-" + str(index)
            state["requests_started"] += 1
            mode_counts[mode] += 1
            request_dir = raw / stage
            request_dir.mkdir(exist_ok=False)
            signal.alarm(180)
            start = time.perf_counter()
            features, processor_evidence, decoded = mode_features(processor, mode == "ON")
            if processor_evidence["features"] != processor_gate["modes"][mode]["features"]:
                raise ValueError("request processor features differ from fixed mode gate")
            save(request_dir / "processor.json", processor_evidence)
            save(request_dir / "input-token-ids.json", features["input_ids"].tolist())
            (request_dir / "decoded-input.txt").write_text(decoded)
            features = features.to("cuda:0")
            input_length = features["input_ids"].shape[-1]
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            before_counts = counts.copy()
            generation_start = time.perf_counter()
            state["inference_calls_started"] += 1
            with torch.inference_mode():
                output = model.generate(**features, do_sample=False, max_new_tokens=512,
                                        num_beams=1, use_cache=True, return_dict_in_generate=False,
                                        output_scores=False)
            torch.cuda.synchronize()
            generation_s = time.perf_counter() - generation_start
            ids = output[0, input_length:].tolist()
            response = processor.tokenizer.decode(ids, skip_special_tokens=True)
            special = processor.tokenizer.decode(ids, skip_special_tokens=False)
            (request_dir / "raw-response.txt").write_text(response)
            (request_dir / "raw-response-with-special-tokens.txt").write_text(special)
            save(request_dir / "output-token-ids.json", ids)
            after = inventory()
            preserved = (after["all_parameters_cuda"] and len(after["fp8_layers"]) == 248
                         and all("float8" in row["dtype"] for row in after["fp8_layers"]))
            attempt = {"index": index, "profile": profile, "mode": mode,
                       "mode_index": mode_counts[mode], "mode_warm_sample": mode_counts[mode] > 1,
                       "first_model_request": index == 1, "status": "COMPLETED",
                       "input_tokens": input_length, "output_tokens": len(ids),
                       "processor_s": processor_evidence["processor_s"], "generation_s": generation_s,
                       "end_to_end_s": time.perf_counter() - start,
                       "torch_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                       "torch_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                       "fp8_weights_preserved": preserved, "ttft": "NOT_MEASURED",
                       "output_contains_think_tag": "<think>" in response or "</think>" in response,
                       "tokens_through_think_end": ids.index(think_end) + 1 if think_end in ids else None,
                       "ended_with_eos": bool(ids and ids[-1] in eos), "reached_token_cap": len(ids) == 512,
                       "raw_response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                       "kernel_call_counts": {name: counts[name] - before_counts[name] for name in bindings},
                       "raw_directory": str(request_dir)}
            save(request_dir / "attempt.json", attempt)
            state["actual_requests"].append(attempt)
            print("REQUEST_COMPLETED", profile, index, mode, len(ids), round(generation_s, 3), flush=True)
            signal.alarm(0)
            if not preserved:
                raise ValueError("compressed FP8 weights not preserved after generation")
        save(raw / "final-inventory.json", inventory())
        state.update(status="EIGHT_REQUESTS_COMPLETED", kernel_call_counts=dict(counts))
    except Exception as error:
        state.update(status="FAILED", failed_stage=stage, error_type=type(error).__name__,
                     error=str(error), traceback=traceback.format_exc())
        if isinstance(error, TimeoutError):
            state["status"] = "TIMEOUT"
        elif "out of memory" in str(error).lower():
            state["status"] = "LOAD_OOM" if stage == "load" else "INFERENCE_OOM"
        elif isinstance(error, BlockingIOError):
            state["status"] = "INSUFFICIENT_RESOURCES_GPU_LOCK"
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
        for name, original in originals.items():
            setattr(qwen_module, name, original)
        if model_class is not None:
            model_class._keys_to_ignore_on_load_unexpected = original_patterns
        if model is not None:
            del model
        state["finished_at"] = datetime.now(UTC).isoformat()
        save(raw / "run-result.json", state)
        save(HERE / ("run-" + profile + "-r487.json"), state)
        lock.close()
        print("RUN_RESULT", state["status"], len(state["actual_requests"]), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
