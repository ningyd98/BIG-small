"""R507 single resident Molmo2-ER BF16, 32 native queries and two repeats."""
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
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
OUT = HERE / "candidates/04-molmoer"
RAW = CACHE / "actual/04-molmoer/run-01"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def timeout(signum, frame):
    raise TimeoutError("R507 model/request timeout")


def main():
    protocol = json.loads((OUT / "protocol-r507.json").read_text())
    for row in protocol["research_sources"]:
        assert sha(ROOT / row["path"]) == row["sha256"]
    assert sha(HERE / "diagnostic/model-inputs.json") == protocol["public_inputs_sha256"]
    assert json.loads((HERE / "candidates/03-lens/run-01.json").read_text())["status"] == "ALL_50_REQUESTS_COMPLETED"
    RAW.mkdir(parents=True, exist_ok=False)
    state = {"candidate": "04-molmoer", "status": "STARTED", "created_at": now(), "pid": os.getpid(),
             "model_loads_started": 0, "generation_calls_started": 0, "completed": [], "raw_directory": str(RAW),
             "protocol_sha256": sha(OUT / "protocol-r507.json"), "hardware_dispatch": False,
             "formal_acceptance": "NOT_PERFORMED", "JSON_RGB": "UNSUPPORTED_SYSTEM_ROLE", "JSON_DUAL": "UNSUPPORTED_SYSTEM_ROLE"}
    def progress():
        (OUT / "run-progress.local.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    lock = (ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX)
    sampler = None
    stream = None
    signal.signal(signal.SIGALRM, timeout)
    try:
        apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], text=True).strip()
        free = int(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], text=True).strip())
        ram = int(next(s.split()[1] for s in Path("/proc/meminfo").read_text().splitlines() if s.startswith("MemAvailable:"))) * 1024
        disk = __import__("shutil").disk_usage(CACHE).free
        assert not apps and free >= 12000 and ram >= 8 * 1024**3 and disk >= 60 * 1024**3
        state["admission"] = {"foreign_compute_apps": apps, "gpu_free_MiB": free, "ram_available_bytes": ram, "disk_free_bytes": disk}
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"),
                          HF_MODULES_CACHE=str(CACHE / "hf-modules-molmoer-r507"))
        import torch
        import transformers
        from transformers import AutoModelForImageTextToText, AutoProcessor
        from molmoer_adapter import build_inputs, tensor_evidence, parse_native, strip_end, next_call_index
        from score_native import assert_public_inputs
        assert transformers.__version__ == "4.57.1" and torch.cuda.is_available()
        assert not any("runtime-b" in p for p in sys.path)
        torch.manual_seed(0)
        public = json.loads((HERE / "diagnostic/model-inputs.json").read_text())
        assert_public_inputs(public)
        cpu = {row["id"]: row for row in json.loads((OUT / "cpu-contract-r507.json").read_text())["cases"]}
        processor = AutoProcessor.from_pretrained(protocol["model_directory"], trust_remote_code=True, local_files_only=True, use_fast=False, padding_side="left")
        stream = (RAW / "gpu-memory-200ms.csv").open("xb")
        sampler = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits", "-lms", "200"], stdout=stream, stderr=subprocess.DEVNULL)
        state["model_loads_started"] = 1
        progress()
        signal.setitimer(signal.ITIMER_REAL, 1800)
        start = time.perf_counter()
        model = AutoModelForImageTextToText.from_pretrained(protocol["model_directory"], trust_remote_code=True,
                local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa", device_map={"": 0}).eval()
        torch.cuda.synchronize()
        signal.setitimer(signal.ITIMER_REAL, 0)
        state["load_s"] = time.perf_counter() - start
        assert all(p.device.type == "cuda" and p.dtype == torch.bfloat16 for p in model.parameters())
        state["dtype_inventory"] = {"all_parameters_BF16": True, "parameter_count": sum(p.numel() for p in model.parameters())}
        state["runtime"] = {"torch": torch.__version__, "transformers": transformers.__version__, "device": torch.cuda.get_device_name(0)}
        save(RAW / "parameter-inventory.json", [{"name": n, "shape": list(p.shape), "dtype": str(p.dtype), "device": str(p.device)} for n,p in model.named_parameters()])

        def request(case, kind, repeat=False):
            index = next_call_index(state["generation_calls_started"], protocol["authorized_generation_calls"])
            folder = RAW / f"request-{index:04}"
            folder.mkdir(exist_ok=False)
            row = {"index": index, "id": case["id"], "query": kind, "repeat": repeat, "stage": "NATIVE_RGB", "started_at": now(), "raw_directory": str(folder)}
            save(folder / "started.json", row)
            torch.cuda.reset_peak_memory_stats()
            signal.setitimer(signal.ITIMER_REAL, 900)
            start = time.perf_counter()
            features, rendered = build_inputs(processor, {**case, "phrase": case[kind + "_phrase"]}, ROOT)
            evidence = tensor_evidence(features)
            expected = cpu[case["id"]]["modes"][kind]
            assert evidence == expected["features"] and hashlib.sha256(rendered.encode()).hexdigest() == expected["rendered_sha256"]
            save(folder / "processor.json", evidence)
            save(folder / "input-token-ids.json", features["input_ids"][0].tolist())
            (folder / "prompt.txt").write_text(rendered)
            row["input_tokens"] = features["input_ids"].shape[1]
            features = {k: v.to("cuda:0") for k,v in features.items()}
            state["generation_calls_started"] += 1
            progress()
            torch.cuda.synchronize()
            before = time.perf_counter()
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                output = model.generate(**features, max_new_tokens=512, do_sample=False, num_beams=1, use_cache=True)
            torch.cuda.synchronize()
            row["generation_s"] = time.perf_counter() - before
            ids = output[0, row["input_tokens"]:].tolist()
            raw = processor.tokenizer.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
            text = strip_end(raw)
            save(folder / "output-token-ids.json", ids)
            (folder / "raw-response-with-special-tokens.txt").write_text(raw)
            (folder / "raw-response.txt").write_text(text)
            row.update(status="GENERATED", output_tokens=len(ids), reached_cap=len(ids) == 512, raw_response_sha256=hashlib.sha256(text.encode()).hexdigest())
            save(folder / "generated.json", row)
            from PIL import Image
            with Image.open(ROOT / case["rgb_path"]) as image:
                row["native"] = parse_native(raw, image.width, image.height)
            row.update(status="COMPLETED", end_to_end_s=time.perf_counter()-start, finished_at=now(),
                       torch_peak_allocated_bytes=torch.cuda.max_memory_allocated(), torch_peak_reserved_bytes=torch.cuda.max_memory_reserved())
            signal.setitimer(signal.ITIMER_REAL, 0)
            save(folder / "attempt.json", row)
            state["completed"].append(row)
            progress()
            print("REQUEST_COMPLETED", index, case["id"], kind, round(row["end_to_end_s"], 3), flush=True)
            del output, features
        for case in public["cases"]:
            for kind in ("target", "destination"):
                request(case, kind)
        for _ in range(2):
            request(public["cases"][0], "target", repeat=True)
        state["status"] = "ALL_34_REQUESTS_COMPLETED"
    except Exception as error:
        state.update(status="FAILED_NEW_ISSUE", error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        save(RAW / "failed.json", state)
        print(state["traceback"], file=sys.stderr, flush=True)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        if sampler is not None:
            sampler.terminate()
            sampler.wait(timeout=10)
        if stream is not None:
            stream.close()
        state["finished_at"] = now()
        save(OUT / "run-01.json", state)
        progress()
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    return 0 if state["status"] == "ALL_34_REQUESTS_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
