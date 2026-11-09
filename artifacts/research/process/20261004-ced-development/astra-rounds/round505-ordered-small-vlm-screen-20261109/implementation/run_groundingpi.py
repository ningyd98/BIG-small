"""Single resident model and frozen sequential R505 chat-candidate requests."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from run_candidate_molmoer import sha, save, now, timeout
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"


def main(candidate):
    out = HERE / "candidates" / candidate
    raw = CACHE / "actual" / candidate / "run-01"
    protocol = json.loads((out / "protocol.json").read_text())
    for row in protocol["research_sources"]:
        assert sha(ROOT / row["path"]) == row["sha256"]
    assert sha(out / "cpu-contract-r511.json") == protocol["cpu_contract_sha256"]
    contract = json.loads((out / "cpu-contract-r511.json").read_text())
    assert candidate == "06-groundingpi"
    assert json.loads((HERE / "candidates/05-rynn/run-01.json").read_text())["status"] == "ALL_REQUESTS_COMPLETED"
    raw.mkdir(parents=True, exist_ok=False)
    state = {"candidate": candidate, "status": "STARTED", "created_at": now(), "pid": os.getpid(), "model_loads_started": 0,
             "generation_calls_started": 0, "completed": [], "raw_directory": str(raw), "protocol_sha256": sha(out / "protocol.json"),
             "formal_acceptance": "NOT_PERFORMED", "hardware_dispatch": False}
    def progress():
        (out / "run-progress.local.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    lock = (ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX)
    sampler = None
    stream = None
    signal.signal(signal.SIGALRM, timeout)
    try:
        apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        free = int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True).strip())
        ram = int(next(s.split()[1] for s in Path("/proc/meminfo").read_text().splitlines() if s.startswith("MemAvailable:"))) * 1024
        assert not apps and free >= 12000 and ram >= 8 * 1024**3
        assert __import__("shutil").disk_usage(CACHE).free >= 60 * 1024**3
        state["admission"] = {"gpu_free_MiB": free, "foreign_compute_apps": apps, "ram_available_bytes": ram}
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"), HF_MODULES_CACHE=str(CACHE / "hf-modules-groundingpi-r511"), IMAGE_MAX_TOKEN_NUM="512")
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoProcessor
        from groundingpi_adapter import build, tensor_evidence, parse_native as parse_rynn, strip_end
        from molmoer_adapter import next_call_index
        torch.manual_seed(0)
        assert torch.cuda.is_available()
        processor = AutoProcessor.from_pretrained(protocol["model_directory"], trust_remote_code=True, local_files_only=True)
        stream = (raw / "gpu-memory-200ms.csv").open("xb")
        sampler = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits", "-lms", "200"], stdout=stream, stderr=subprocess.DEVNULL)
        state["model_loads_started"] = 1
        progress()
        signal.setitimer(signal.ITIMER_REAL, 1800)
        started = time.perf_counter()
        model = AutoModelForCausalLM.from_pretrained(protocol["model_directory"], trust_remote_code=True, local_files_only=True, dtype=torch.bfloat16,
                    attn_implementation="sdpa", device_map={"": 0}).eval()
        torch.cuda.synchronize()
        signal.setitimer(signal.ITIMER_REAL, 0)
        state["load_s"] = time.perf_counter() - started
        assert all(p.dtype == torch.bfloat16 and p.device.type == "cuda" for p in model.parameters())
        state["dtype_inventory"] = {"all_parameters_BF16": True, "parameter_count": sum(p.numel() for p in model.parameters())}
        state["runtime"] = {"torch": str(torch.__version__), "transformers": transformers.__version__, "device": torch.cuda.get_device_name(0)}
        save(raw / "parameter-inventory.json", [{"name": n, "shape": list(p.shape), "dtype": str(p.dtype), "device": str(p.device)} for n,p in model.named_parameters()])
        for request in contract["requests"]:
            index = next_call_index(state["generation_calls_started"], protocol["authorized_generation_calls"])
            folder = raw / f"request-{index:04}"
            folder.mkdir(exist_ok=False)
            row = {key: request[key] for key in ("id", "query", "mode", "stage", "repeat")}
            row.update(index=index, status="STARTED", started_at=now(), raw_directory=str(folder))
            save(folder / "started.json", row)
            signal.setitimer(signal.ITIMER_REAL, 900)
            torch.cuda.reset_peak_memory_stats()
            started = time.perf_counter()
            features, rendered = build(processor, request, ROOT, protocol["processor_kwargs"])
            evidence = tensor_evidence(features)
            import hashlib
            assert evidence == request["features"] and hashlib.sha256(rendered.encode()).hexdigest() == request["rendered_sha256"]
            save(folder / "processor.json", evidence)
            save(folder / "input-token-ids.json", features["input_ids"][0].tolist())
            (folder / "prompt.txt").write_text(rendered)
            row["input_tokens"] = features["input_ids"].shape[1]
            features = {k: v.to("cuda:0") if hasattr(v, "to") else v for k,v in features.items()}
            state["generation_calls_started"] += 1
            progress()
            torch.cuda.synchronize()
            before = time.perf_counter()
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                output = model.generate(**features, max_new_tokens=512, do_sample=False, num_beams=1, use_cache=True, **protocol["generate_kwargs"])
            torch.cuda.synchronize()
            row["generation_s"] = time.perf_counter() - before
            ids = output[0, row["input_tokens"]:].tolist()
            raw_text = processor.tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
            text = strip_end(raw_text)
            save(folder / "output-token-ids.json", ids)
            (folder / "raw-response-with-special-tokens.txt").write_text(raw_text)
            (folder / "raw-response.txt").write_text(text)
            row.update(status="GENERATED", output_tokens=len(ids), reached_cap=len(ids)==512, raw_response_sha256=hashlib.sha256(text.encode()).hexdigest())
            save(folder / "generated.json", row)
            if request["stage"] == "NATIVE_RGB":
                from PIL import Image
                with Image.open(ROOT / request["rgb_path"]) as image:
                    row["native"] = parse_rynn(raw_text, request["mode"], image.width, image.height, reached_cap=len(ids)==512)
            row.update(status="COMPLETED", end_to_end_s=time.perf_counter()-started, finished_at=now(),
                       torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(), torch_peak_reserved_bytes=torch.cuda.max_memory_reserved())
            signal.setitimer(signal.ITIMER_REAL, 0)
            save(folder / "attempt.json", row)
            state["completed"].append(row)
            progress()
            print("REQUEST_COMPLETED", index, request["stage"], request["id"], request["mode"], round(row["end_to_end_s"],3), flush=True)
            del features, output
        state["status"] = "ALL_REQUESTS_COMPLETED"
    except Exception as error:
        state.update(status="FAILED_NEW_ISSUE", error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        save(raw / "failed.json", state)
        print(state["traceback"], file=sys.stderr, flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if sampler is not None:
            sampler.terminate()
            sampler.wait(timeout=10)
        if stream is not None:
            stream.close()
        state["finished_at"] = now()
        save(out / "run-01.json", state)
        progress()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    return 0 if state["status"] == "ALL_REQUESTS_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
