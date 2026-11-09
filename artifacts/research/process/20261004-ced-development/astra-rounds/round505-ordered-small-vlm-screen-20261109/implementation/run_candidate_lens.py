"""One resident Lens model, ordered R505 native and JSON-RGB requests; no oracle."""

import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
OUT = HERE / "candidates/03-lens"
RAW = CACHE / "actual/03-lens/run-01"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def alarm_handler(signum, frame):
    raise TimeoutError("R505 request exceeded 900 seconds")


def main():
    protocol = json.loads((OUT / "protocol.json").read_text())
    for row in protocol["research_sources"]:
        assert sha(ROOT / row["path"]) == row["sha256"], row["path"]
    assert sha(HERE / "plan.json") == protocol["plan_sha256"]
    assert sha(HERE / "diagnostic/model-inputs.json") == protocol["public_inputs_sha256"]
    for candidate in ("01-wevis4b", "02-wevis2b"):
        previous = json.loads((HERE / "candidates" / candidate / "result.json").read_text())
        assert previous["status"] == "DOWNLOAD_DEFERRED"
    RAW.mkdir(parents=True, exist_ok=False)
    state = {"candidate": "03-lens", "created_at": now(), "status": "STARTED", "pid": os.getpid(),
             "model_loads_started": 0, "generation_calls_started": 0, "mask_forward_calls_started": 0,
             "completed": [], "protocol_sha256": sha(OUT / "protocol.json"), "formal_acceptance": "NOT_PERFORMED",
             "hardware_dispatch": False, "dual_stage": "UNSUPPORTED_BY_PUBLISHED_INFER_HELPER",
             "raw_directory": str(RAW), "background_asset_preparation": "CPU/network-only sequential download process may run; no other GPU inference permitted"}

    def progress():
        (OUT / "run-progress.local.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")

    progress()
    lockpath = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock"
    lockpath.parent.mkdir(exist_ok=True)
    lock = lockpath.open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX)
    sampler = None
    sample_stream = None
    try:
        apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        assert not apps, "GPU occupied by another compute process"
        free = int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True).strip())
        assert free >= 12000, free
        memory_available = int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines() if line.startswith("MemAvailable:"))) * 1024
        assert memory_available >= 8 * 1024**3
        state["admission"] = {"gpu_free_MiB": free, "foreign_compute_apps": apps, "ram_available_bytes": memory_available}
        sdk = Path(protocol["sdk_directory"])
        sys.path.insert(0, str(sdk))
        sys.path.insert(0, str(sdk / "src"))
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"),
                          HF_MODULES_CACHE=str(CACHE / "hf-modules"))
        import torch
        import numpy as np
        from PIL import Image
        import infer
        from lens_adapter import (build_inputs, build_json_inputs, native_prompt, tensor_evidence,
                                  verify_public_case, normalize_lens, strip_native_end_tokens)
        from score_native import assert_public_inputs
        assert torch.cuda.is_available() and torch.cuda.get_device_capability(0) == (8, 9)
        torch.manual_seed(0)
        public = json.loads((HERE / "diagnostic/model-inputs.json").read_text())
        assert_public_inputs(public)
        cpu_rows = {row["id"]: row for row in json.loads((OUT / "cpu-contract.json").read_text())["cases"]}
        json_rows = {row["id"]: row for row in json.loads((OUT / "json-rgb-cpu-contract.json").read_text())["cases"]}
        signal.signal(signal.SIGALRM, alarm_handler)
        sample_stream = (RAW / "gpu-memory-200ms.csv").open("xb")
        sampler = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits", "-lms", "200"], stdout=sample_stream, stderr=subprocess.DEVNULL)
        state["model_loads_started"] = 1
        progress()
        before = time.perf_counter()
        model, processor, mask_id = infer.load_model_and_processor(Path(protocol["model_directory"]), torch.device("cuda:0"), attn_implementation="sdpa")
        torch.cuda.synchronize()
        state["load_s"] = time.perf_counter() - before
        assert all(p.device.type == "cuda" for p in model.parameters())
        assert hasattr(model, "mask_decoder")
        model.generation_config.num_beams = 1
        model.generation_config.use_cache = True
        inventory = [{"name": name, "dtype": str(value.dtype), "device": str(value.device), "shape": list(value.shape)} for name, value in model.named_parameters()]
        save_new(RAW / "parameter-inventory.json", inventory)
        assert all(row["dtype"] == "torch.bfloat16" for row in inventory)
        state["dtype_inventory"] = {"all_parameters_BF16": True, "parameter_count": sum(p.numel() for p in model.parameters()), "mask_parameter_count": sum(p.numel() for p in model.mask_decoder.parameters())}
        state["runtime"] = {"torch": str(torch.__version__), "cuda": torch.version.cuda, "device": torch.cuda.get_device_name(0)}
        from transformers.models.qwen3_5 import modeling_qwen3_5 as qwen
        state["kernel_bindings"] = {key: str(getattr(qwen, key, None)) for key in ["is_fast_path_available", "chunk_gated_delta_rule", "torch_chunk_gated_delta_rule", "causal_conv1d_fn"]}
        save_new(RAW / "effective-generation-settings.json", {key: getattr(model.generation_config, key, None) for key in ["num_beams", "use_cache", "eos_token_id", "pad_token_id", "bos_token_id", "repetition_penalty"]})
        progress()

        def request(row, kind, stage, repeat=False):
            index = state["generation_calls_started"] + 1
            assert index <= protocol["authorized_generation_calls"]
            folder = RAW / f"request-{index:04}"
            folder.mkdir(exist_ok=False)
            record = {"index": index, "id": row["id"], "query": kind, "stage": stage, "repeat": repeat, "status": "STARTED", "started_at": now(), "raw_directory": str(folder)}
            save_new(folder / "started.json", record)
            signal.setitimer(signal.ITIMER_REAL, 900)
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            image = Image.open(verify_public_case(ROOT, row)).convert("RGB")
            if stage == "NATIVE_RGB":
                prompt = native_prompt(row[kind + "_phrase"])
                features, rendered = build_inputs(processor, image, prompt, torch.device("cuda:0"))
                expected = cpu_rows[row["id"]]["modes"][kind]
            else:
                source = json_rows[row["id"]]
                prompt = source["system"] + "\n" + source["instruction"]
                features, rendered = build_json_inputs(processor, image, source["system"], source["instruction"], torch.device("cuda:0"))
                expected = source
            evidence = tensor_evidence(features)
            assert evidence == expected["features"] and hashlib.sha256(rendered.encode()).hexdigest() == expected["rendered_sha256"]
            save_new(folder / "processor.json", evidence)
            save_new(folder / "input-token-ids.json", features["input_ids"][0].tolist())
            (folder / "prompt.txt").write_text(rendered)
            record["input_tokens"] = features["input_ids"].shape[1]
            state["generation_calls_started"] += 1
            progress()
            torch.cuda.synchronize()
            gen_start = time.perf_counter()
            ids, raw_text, mask_count = infer.generate_completion(model, processor, features, 512, mask_id, do_sample=False)
            torch.cuda.synchronize()
            record["generation_s"] = time.perf_counter() - gen_start
            token_ids = ids[0].tolist()
            save_new(folder / "output-token-ids.json", token_ids)
            (folder / "raw-response-with-special-tokens.txt").write_text(raw_text)
            response = strip_native_end_tokens(raw_text)
            (folder / "raw-response.txt").write_text(response)
            record.update(status="GENERATED", output_tokens=len(token_ids), mask_tokens=mask_count, reached_cap=len(token_ids) == 512, raw_response_sha256=hashlib.sha256(response.encode()).hexdigest())
            save_new(folder / "generated.json", record)
            masks = None
            if stage == "NATIVE_RGB" and mask_count:
                state["mask_forward_calls_started"] += 1
                progress()
                mask_started = time.perf_counter()
                masks = infer.run_forward(model, features, ids, mask_id, torch.device("cuda:0"))
                torch.cuda.synchronize()
                record["mask_forward_s"] = time.perf_counter() - mask_started
            if stage == "NATIVE_RGB":
                try:
                    record["native"] = normalize_lens(infer, raw_text, masks, image.width, image.height)
                except ValueError as error:
                    record["native"] = {mode: {"status": "INVALID", "point": None, "predictions": [], "error": str(error)} for mode in ("mask", "box")}
            else:
                record["json_response_path"] = str(folder / "raw-response.txt")
            record["end_to_end_s"] = time.perf_counter() - started
            signal.setitimer(signal.ITIMER_REAL, 0)
            if masks is not None:
                np.save(folder / "raw-mask-logits.npy", masks.float().cpu().numpy())
            record.update(status="COMPLETED", finished_at=now(), torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(), torch_peak_reserved_bytes=torch.cuda.max_memory_reserved())
            save_new(folder / "attempt.json", record)
            state["completed"].append(record)
            progress()
            print("REQUEST_COMPLETED", index, stage, row["id"], kind, len(token_ids), round(record["end_to_end_s"], 3), flush=True)
            del features, ids, masks

        for row in public["cases"]:
            for kind in ("target", "destination"):
                request(row, kind, "NATIVE_RGB")
        for _ in range(2):
            request(public["cases"][0], "target", "NATIVE_RGB", repeat=True)
        for row in public["cases"]:
            request(row, "task", "JSON_RGB")
        state["status"] = "ALL_50_REQUESTS_COMPLETED"
    except Exception as error:
        signal.setitimer(signal.ITIMER_REAL, 0)
        state.update(status="FAILED_NEW_ISSUE", error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        save_new(RAW / "failed.json", {"error": state["error"], "traceback": state["traceback"], "generation_calls_started": state["generation_calls_started"]})
        print(state["traceback"], file=sys.stderr, flush=True)
    finally:
        if sampler is not None:
            sampler.terminate()
            sampler.wait(timeout=10)
        if sample_stream is not None:
            sample_stream.close()
        state["finished_at"] = now()
        save_new(OUT / "run-01.json", state)
        progress()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    print("LENS_RUN_FINISHED", state["status"], len(state["completed"]), flush=True)
    return 0 if state["status"] == "ALL_50_REQUESTS_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
