"""Offline native BF16 MiniCPM-V4.6, loopback-only frozen RGB-D bridge.

CPU preflight never instantiates a model. GPU server requires a root-issued lease.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HOME"] = str(HERE / "hf-runtime")
os.environ["TRITON_CACHE_DIR"] = str(HERE / "triton-runtime")
sys.path.insert(0, str(HERE.parent / "source-snapshot/src"))
from adapter_contract import parse_request
from cloud_edge_robot_arm.vision.messages import build_visual_messages
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import VisualDecision, compatible_messages

NAME = "MiniCPM-V-4.6-research-bf16-4x-json"
CACHE = HERE / "minicpm-model"
SOURCE = json.loads((HERE / "minicpm-source-metadata.json").read_text())
WEIGHTS = {r["Path"]: r["Sha256"] for r in SOURCE["Data"]["Files"] if r["Path"].endswith(".safetensors")}
DIGEST = hashlib.sha256(json.dumps(WEIGHTS, sort_keys=True).encode()).hexdigest()
CONFIG = {"provider": "openai_compatible", "model": NAME, "endpoint": "http://127.0.0.1:11438", "weight_digest": DIGEST, "quantization": "BF16", "image_size": [320, 240], "coordinate_system": "normalized_1000", "grasp_profile": "mujoco_upright_box_v1", "timeout_s": 180, "generation_parameters": {"temperature": 0, "num_ctx": 8192, "num_predict": 512, "think": False}}

def verify_source(*, include_weights):
    records = []
    for row in SOURCE["Data"]["Files"]:
        if row["Type"] != "blob" or not include_weights and row["Path"].endswith(".safetensors"):
            continue
        path = CACHE / row["Path"]
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != row["Sha256"] or path.stat().st_size != row["Size"]:
            raise ValueError("pinned source size/SHA differs: " + row["Path"])
        records.append({"file": row["Path"], "revision": row["Revision"], "sha256": digest, "size": row["Size"]})
    return records

def array_schema(value):
    if isinstance(value, list):
        return [array_schema(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: array_schema(v) for k, v in value.items()}
    if "prefixItems" in result:
        entries = result.pop("prefixItems")
        if not entries or not all(v == entries[0] for v in entries):
            raise ValueError("only homogeneous tuple schemas supported")
        result["items"] = entries[0]
    return result

def load_processor():
    from transformers import AutoConfig, AutoProcessor
    config = AutoConfig.from_pretrained(CACHE, local_files_only=True, trust_remote_code=False)
    processor = AutoProcessor.from_pretrained(CACHE, local_files_only=True, trust_remote_code=False)
    return config, processor

def cpu_preflight():
    records = verify_source(include_weights=False)
    config, processor = load_processor()
    bank = HERE.parent / "shared/scene-bank/cases/positive-03/observation-transport.json"
    observation = RGBDObservation.model_validate_json(bank.read_text())
    messages = compatible_messages(build_visual_messages("CPU input compatibility check only.", observation, image_size=(320, 240), coordinate_system="normalized_1000", decision_schema=VisualDecision.model_json_schema()))
    request = {"model": NAME, "temperature": 0, "max_tokens": 512, "response_format": {"type": "json_object"}, "messages": messages}
    native, raw, schema = parse_request(request, model_name=NAME)
    template = processor.apply_chat_template(native, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    inputs = processor.apply_chat_template(native, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt", processor_kwargs={"downsample_mode":"4x", "max_slice_nums":36}, enable_thinking=False)
    count = int(inputs["input_ids"].shape[-1])
    if count + 512 > 8192:
        raise ValueError("expanded native prompt exceeds frozen8192 budget")
    if not template.endswith("<think>\n\n</think>\n\n"):
        raise ValueError("native no-thinking generation prefix differs")
    from lmformatenforcer import JsonSchemaParser
    from lmfe_transformers_compat import build_token_enforcer_tokenizer_data, build_transformers_prefix_allowed_tokens_fn
    started = time.perf_counter()
    data = build_token_enforcer_tokenizer_data(processor.tokenizer)
    prefix = build_transformers_prefix_allowed_tokens_fn(data, JsonSchemaParser(array_schema(schema)))
    allowed = prefix(0, inputs["input_ids"][0])
    image_tokens = int((inputs["input_ids"] == config.image_token_id).sum())
    target_sizes = inputs["target_sizes"].tolist()
    if image_tokens != sum(h*w//4 for h,w in target_sizes):
        raise ValueError("native placeholders do not realize frozen4x mode")
    result = {"status": "cpu_processor_and_schema_ready", "quality_measured": False, "model_loaded": False, "cuda_used": False, "source_files": records, "model_config_class": type(config).__name__, "processor_class": type(processor).__name__, "torch": importlib.metadata.version("torch"), "transformers": importlib.metadata.version("transformers"), "tokenizers": importlib.metadata.version("tokenizers"), "lm_format_enforcer": importlib.metadata.version("lm-format-enforcer"), "input_image_sha256": [hashlib.sha256(b).hexdigest() for b in raw], "downsample_mode": "4x", "max_slice_nums": 36, "enable_thinking": False, "expanded_prompt_tokens": count, "image_placeholder_tokens":image_tokens, "target_sizes_patches":target_sizes, "input_tensor_shapes": {k: list(v.shape) for k, v in inputs.items() if hasattr(v, "shape")}, "native_generation_prefix": template[-80:], "tokenizer_eos_token_id": processor.tokenizer.eos_token_id, "json_prefix_allowed_initial_tokens": len(allowed), "tokenizer_tree_build_and_constraint_s": time.perf_counter() - started}
    (HERE / "minicpm-cpu-preflight.json").write_text(json.dumps(result, indent=2) + "\n")
    (HERE / "minicpm-normalized.json").write_text(json.dumps(CONFIG, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "processor_class", "expanded_prompt_tokens", "input_tensor_shapes", "native_generation_prefix", "json_prefix_allowed_initial_tokens")}))

def serve(lease, run_id):
    if not lease:
        raise RuntimeError("GPU model loading requires an explicit root lease")
    if not run_id or not all(c.isalnum() or c in "-_" for c in run_id):
        raise ValueError("run_id must be a simple unique evidence label")
    runtime_path = HERE / ("minicpm-runtime-" + run_id + ".json")
    events_path = HERE / ("minicpm-native-events-" + run_id + ".jsonl")
    if runtime_path.exists() or events_path.exists():
        raise FileExistsError("refusing to overwrite prior native run evidence")
    records = verify_source(include_weights=True)
    import torch
    import uvicorn
    import transformers
    from fastapi import FastAPI, HTTPException
    from transformers import AutoModelForImageTextToText
    from lmformatenforcer import JsonSchemaParser
    from lmfe_transformers_compat import build_token_enforcer_tokenizer_data, build_transformers_prefix_allowed_tokens_fn
    config, processor = load_processor()
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    torch.set_num_threads(8)
    started = time.perf_counter()
    model = AutoModelForImageTextToText.from_pretrained(CACHE, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa", local_files_only=True, trust_remote_code=False).eval()
    torch.cuda.synchronize()
    load_wall = time.perf_counter() - started
    if not all(p.device.type == "cuda" for p in model.parameters()):
        raise RuntimeError("candidate did not load wholly onto leased GPU")
    data = build_token_enforcer_tokenizer_data(processor.tokenizer)
    runtime = {"status": "gpu_loaded", "gpu_lease": lease, "model": NAME, "weight_digest": DIGEST, "source_files": records, "load_wall_s": load_wall, "torch": torch.__version__, "transformers": transformers.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0), "model_class": type(model).__name__, "dtype_parameter_counts": {}, "processor": {"class": type(processor).__name__, "downsample_mode": "4x", "max_slice_nums": 36, "input_size": [320,240]}, "native_generation": {"do_sample": False, "temperature": None, "max_new_tokens":512, "expanded_total_context_limit":8192, "enable_thinking":False, "downsample_mode":"4x", "attn_implementation":"sdpa"}, "json_schema_policy":"same current VisualDecision schema; homogeneous prefixItems represented as items with unchanged min/maxItems; no semantic constraints or repairs", "source_code_review":"model repository contains no executable Python code; pinned Transformers native implementation; trust_remote_code=False; local_files_only=True; HF and Transformers offline", "invoice_cost_cny":0}
    for p in model.parameters():
        key = str(p.dtype)
        runtime["dtype_parameter_counts"][key] = runtime["dtype_parameter_counts"].get(key,0) + p.numel()
    runtime["run_id"] = run_id
    runtime["native_acceleration"] = "Torch fallback for linear attention; optional fla/causal-conv1d absent"
    with runtime_path.open("x") as stream:
        json.dump(runtime, stream, indent=2)
    frozen_config = json.loads((HERE / "minicpm-normalized.json").read_text())
    if frozen_config != CONFIG:
        raise ValueError("candidate config differs from frozen CPU preflight")
    app = FastAPI()
    lock = threading.Lock()

    @app.get("/health")
    def health():
        return {"status":"ready", "model":NAME, "weight_digest":DIGEST, "cuda":True}

    @app.post("/chat/completions")
    def chat(body:dict):
        with lock:
            try:
                native, raw, schema = parse_request(body, model_name=NAME)
                inputs = processor.apply_chat_template(native, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt", processor_kwargs={"downsample_mode":"4x", "max_slice_nums":36}, enable_thinking=False)
                prompt_count = int(inputs["input_ids"].shape[-1])
                if prompt_count + 512 > 8192:
                    raise ValueError("expanded prompt exceeds frozen8192 token budget")
                normalized_schema = array_schema(schema)
                prefix = build_transformers_prefix_allowed_tokens_fn(data, JsonSchemaParser(normalized_schema))
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(400, str(exc)) from exc
            inputs = inputs.to(model.device)
            torch.cuda.reset_peak_memory_stats()
            start = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**inputs, downsample_mode="4x", max_new_tokens=512, do_sample=False, temperature=None, top_p=None, top_k=None, prefix_allowed_tokens_fn=prefix)
            torch.cuda.synchronize()
            wall = time.perf_counter() - start
            trimmed = generated[:, prompt_count:]
            output = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
            completion_count = int(trimmed.shape[-1])
            usage = {"prompt_tokens":prompt_count, "completion_tokens":completion_count, "total_tokens":prompt_count+completion_count}
            event = {"model":NAME, "weight_digest":DIGEST, "input_image_sha256":[hashlib.sha256(b).hexdigest() for b in raw], "system_text":native[0]["content"], "user_text":native[1]["content"][-1]["text"], "native_image_order":["RGB","aligned_depth"], "downsample_mode_processor":"4x", "downsample_mode_generate":"4x", "enable_thinking":False, "decoder_schema":normalized_schema, "raw_output":output, "wall_s":wall, "usage":usage, "cuda_peak_allocated_bytes":torch.cuda.max_memory_allocated(), "cuda_peak_reserved_bytes":torch.cuda.max_memory_reserved(), "invoice_cost_cny":0}
            with events_path.open("a") as stream:
                stream.write(json.dumps(event, ensure_ascii=False)+"\n")
            print("GENERATED", round(wall,3), usage, flush=True)
            return {"model":NAME, "choices":[{"message":{"role":"assistant","content":output},"finish_reason":"length" if completion_count==512 else "stop"}], "usage":usage, "native_inference_wall_s":wall, "invoice_cost_cny":0}
    print("READY",NAME,DIGEST,load_wall,flush=True)
    uvicorn.run(app, host="127.0.0.1", port=11438, log_level="warning")

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cpu-preflight", action="store_true")
    parser.add_argument("--gpu-lease")
    parser.add_argument("--run-id", default="first")
    args=parser.parse_args()
    if args.cpu_preflight:
        cpu_preflight()
    else:
        serve(args.gpu_lease, args.run_id)
