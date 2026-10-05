"""Loopback-only, real Transformers InternVL bridge for the unchanged RGB-D planner."""

from __future__ import annotations

# ruff: noqa: E402 -- offline environment is set before importing Transformers
import base64
import hashlib
import io
import json
import os
import threading
import time
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
HERE = Path(__file__).parent
ROOT = HERE.parents[3]
os.environ["HF_HOME"] = str(ROOT / "datasets/model-cache/hf-runtime")
header_root = ROOT / "datasets/model-cache/python312-headers/root/usr/include"
os.environ["CPATH"] = str(header_root) + ":" + str(header_root / "python3.12")
os.environ["TRITON_CACHE_DIR"] = str(ROOT / "datasets/model-cache/triton-runtime")
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from PIL import Image
from torchvision import transforms
from torchvision.transforms.functional import InterpolationMode
from transformers import (
    AutoModel,
    AutoTokenizer,
    BitsAndBytesConfig,
    LogitsProcessor,
    LogitsProcessorList,
)

CACHE = ROOT / "datasets/model-cache/internvl2_5-8b"
NAME = "InternVL2_5-8B-research-bnb8-json"
manifest = json.loads((HERE / "internvl8-download-protocol.json").read_text())
weights = {r["Path"]: r["Sha256"] for r in manifest["files"] if r["Path"].endswith(".safetensors")}
weight_digest = hashlib.sha256(json.dumps(weights, sort_keys=True).encode()).hexdigest()
for r in manifest["files"]:
    p = CACHE / r["Path"]
    with p.open("rb") as f:
        actual = hashlib.file_digest(f, "sha256").hexdigest()
    if actual != r["Sha256"] or p.stat().st_size != r["Size"]:
        raise ValueError("source integrity differs: " + str(p))
torch.manual_seed(0)
torch.cuda.manual_seed_all(0)
torch.set_num_threads(8)
load_start = time.perf_counter()
model = AutoModel.from_pretrained(
    str(CACHE),
    torch_dtype=torch.bfloat16,
    low_cpu_mem_usage=True,
    quantization_config=BitsAndBytesConfig(load_in_8bit=True),
    device_map={"": 0},
    use_flash_attn=False,
    trust_remote_code=True,
    local_files_only=True,
).eval()
tokenizer = AutoTokenizer.from_pretrained(
    str(CACHE), trust_remote_code=True, use_fast=False, local_files_only=True
)
load_wall = time.perf_counter() - load_start
import importlib.metadata
from importlib import import_module

from lmformatenforcer import JsonSchemaParser
from lmformatenforcer.integrations.transformers import (
    build_token_enforcer_tokenizer_data,
    build_transformers_prefix_allowed_tokens_fn,
)

conversation_module = import_module(type(model).__module__.rsplit(".", 1)[0] + ".conversation")
native_eos = tokenizer.convert_tokens_to_ids(
    conversation_module.get_conv_template(model.template).sep.strip()
)
tree_start = time.perf_counter()
tokenizer_data = build_token_enforcer_tokenizer_data(tokenizer)
tokenizer_data.eos_token_id = native_eos
tree_wall = time.perf_counter() - tree_start


def array_schema(value):
    if isinstance(value, list):
        return [array_schema(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: array_schema(v) for k, v in value.items()}
    if "prefixItems" in result:
        values = result.pop("prefixItems")
        if not values or not all(v == values[0] for v in values):
            raise ValueError("only homogeneous tuple schema supported")
        result["items"] = values[0]
    return result


import bitsandbytes as bnb

quantized = [n for n, m in model.named_modules() if isinstance(m, bnb.nn.Linear8bitLt)]
if not torch.cuda.is_available() or not quantized:
    raise RuntimeError("CUDA/8-bit loading not realized")
config = {
    "provider": "openai_compatible",
    "model": NAME,
    "endpoint": "http://127.0.0.1:11436",
    "weight_digest": weight_digest,
    "quantization": "BNB_INT8",
    "image_size": [320, 240],
    "coordinate_system": "normalized_1000",
    "grasp_profile": "mujoco_upright_box_v1",
    "timeout_s": 180,
    "generation_parameters": {
        "temperature": 0,
        "num_ctx": 8192,
        "num_predict": 512,
        "think": False,
    },
}
(HERE / "internvl8-normalized.json").write_text(json.dumps(config, indent=2) + "\n")
import accelerate
import torchvision
import transformers

runtime = {
    "model": NAME,
    "weight_digest": weight_digest,
    "load_wall_s": load_wall,
    "torch": torch.__version__,
    "transformers": transformers.__version__,
    "torchvision": torchvision.__version__,
    "accelerate": accelerate.__version__,
    "bitsandbytes": bnb.__version__,
    "cuda": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(0),
    "quantized_linear_count": len(quantized),
    "quantized_module_names": quantized,
    "device_map": model.hf_device_map,
    "processor": {
        "tile_size": 448,
        "max_num": 4,
        "use_thumbnail": True,
        "normalization": "ImageNet",
        "interpolation": "bicubic",
        "input_size": [320, 240],
    },
    "generation": (
        "greedy, max_new_tokens=512, native chat, LM Format Enforcer "
        "equivalent VisualDecision JSON schema"
    ),
    "json_policy": "raw native output, no repairs or coordinate rescaling",
    "lm_format_enforcer": importlib.metadata.version("lm-format-enforcer"),
    "tokenizer_tree_build_s": tree_wall,
    "native_eos_token_id": native_eos,
    "json_schema_policy": (
        "identical VisualDecision schema; homogeneous prefixItems represented as items; "
        "no coordinate or semantic constraints added"
    ),
    "source_code_review": (
        "official pinned code inspected; no external network execution; offline mode"
    ),
    "cuda_allocated_bytes": torch.cuda.memory_allocated(),
    "cuda_reserved_bytes": torch.cuda.memory_reserved(),
}
(HERE / "internvl8-runtime.json").write_text(json.dumps(runtime, indent=2) + "\n")
transform = transforms.Compose(
    [
        transforms.Resize((448, 448), interpolation=InterpolationMode.BICUBIC),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
    ]
)


def image_tiles(image):
    # Official dynamic tiling with max_num=4; count selected before seeing model replies.
    width, height = image.size
    aspect = width / height
    area = width * height
    ratios = sorted(
        {
            (i, j)
            for n in range(1, 5)
            for i in range(1, n + 1)
            for j in range(1, n + 1)
            if 1 <= i * j <= 4
        },
        key=lambda x: x[0] * x[1],
    )
    best = (1, 1)
    difference = float("inf")
    for ratio in ratios:
        current = abs(aspect - ratio[0] / ratio[1])
        if current < difference or (
            current == difference and area > 0.5 * 448 * 448 * ratio[0] * ratio[1]
        ):
            best = ratio
            difference = current
    resized = image.resize((448 * best[0], 448 * best[1]))
    tiles = [
        resized.crop(
            (
                i % best[0] * 448,
                i // best[0] * 448,
                (i % best[0] + 1) * 448,
                (i // best[0] + 1) * 448,
            )
        )
        for i in range(best[0] * best[1])
    ]
    if len(tiles) > 1:
        tiles.append(image.resize((448, 448)))
    return torch.stack([transform(tile) for tile in tiles])


class NativeJsonLogitsProcessor(LogitsProcessor):
    """Mask native inputs_embeds generation, including its empty initial token prefix."""

    def __init__(self, prefix_function):
        self.prefix_function = prefix_function

    def __call__(self, input_ids, scores):
        mask = torch.full_like(scores, float("-inf"))
        for batch in range(input_ids.shape[0]):
            allowed = self.prefix_function(batch, input_ids[batch])
            mask[batch, allowed] = 0
        return scores + mask


app = FastAPI()
lock = threading.Lock()
events = []
original_generate = model.generate
current_usage = {}


def measured_generate(**kwargs):
    count = int(kwargs["input_ids"].shape[1])
    if count + kwargs.get("max_new_tokens", 512) > 8192:
        raise ValueError("expanded prompt exceeds frozen 8192 token budget")
    current_usage["prompt_tokens"] = count
    result = original_generate(**kwargs)
    current_usage["completion_tokens"] = int(result.shape[-1])
    return result


model.generate = measured_generate


@app.get("/health")
def health():
    return {
        "status": "ready",
        "model": NAME,
        "weight_digest": weight_digest,
        "cuda": True,
        "quantized_linear_count": len(quantized),
    }


@app.post("/chat/completions")
def chat(body: dict):
    with lock:
        if (
            body.get("model") != NAME
            or body.get("temperature") != 0
            or body.get("max_tokens") != 512
        ):
            raise HTTPException(400, "model/generation differs from frozen candidate")
        messages = body.get("messages", [])
        if len(messages) != 2 or [m.get("role") for m in messages] != ["system", "user"]:
            raise HTTPException(400, "expected system and user")
        contents = messages[1]["content"]
        texts = [r["text"] for r in contents if r.get("type") == "text"]
        images = [r["image_url"]["url"] for r in contents if r.get("type") == "image_url"]
        if len(images) != 2 or len(texts) != 1:
            raise HTTPException(400, "expected two real image payloads and one task")
        raw = []
        tensors = []
        counts = []
        for url in images:
            if not url.startswith("data:image/png;base64,"):
                raise HTTPException(400, "only inline PNG accepted")
            payload = base64.b64decode(url.split(",", 1)[1], validate=True)
            raw.append(payload)
            im = Image.open(io.BytesIO(payload)).convert("RGB")
            if im.size != (320, 240):
                raise HTTPException(400, "image size differs")
            tensor = image_tiles(im)
            tensors.append(tensor)
            counts.append(len(tensor))
        if raw[0] == raw[1]:
            raise HTTPException(400, "RGB and depth unexpectedly identical")
        question = texts[0] + "\nImage 1 (RGB): <image>\nImage 2 (aligned depth): <image>"
        model.system_message = messages[0]["content"]
        pixels = torch.cat(tensors).to(device="cuda", dtype=torch.bfloat16)
        schema = json.loads(messages[0]["content"].split(" Schema: ", 1)[1])
        normalized_schema = array_schema(schema)
        if body.get("response_format") != {"type": "json_object"}:
            raise HTTPException(400, "JSON mode required")
        prefix_function = build_transformers_prefix_allowed_tokens_fn(
            tokenizer_data, JsonSchemaParser(normalized_schema)
        )
        current_usage.clear()
        torch.cuda.reset_peak_memory_stats()
        start = time.perf_counter()
        with torch.inference_mode():
            response = model.chat(
                tokenizer,
                pixels,
                question,
                {
                    "max_new_tokens": 512,
                    "do_sample": False,
                    "logits_processor": LogitsProcessorList(
                        [NativeJsonLogitsProcessor(prefix_function)]
                    ),
                },
                num_patches_list=counts,
            )
        torch.cuda.synchronize()
        wall = time.perf_counter() - start
        event = {
            "index": len(events) + 1,
            "model": NAME,
            "input_image_sha256": [hashlib.sha256(r).hexdigest() for r in raw],
            "system_text": messages[0]["content"],
            "user_text": texts[0],
            "native_question": question,
            "num_patches_list": counts,
            "decoder_schema": normalized_schema,
            "response_format": body["response_format"],
            "raw_output": response,
            "wall_s": wall,
            "usage": dict(current_usage),
            "cuda_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "cuda_peak_reserved_bytes": torch.cuda.max_memory_reserved(),
            "invoice_cost_cny": 0,
        }
        events.append(event)
        with (HERE / "internvl8-native-events.jsonl").open("a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        print("GENERATED", len(events), round(wall, 3), counts, dict(current_usage), flush=True)
        return {
            "model": NAME,
            "choices": [
                {"message": {"role": "assistant", "content": response}, "finish_reason": "stop"}
            ],
            "usage": dict(current_usage),
            "native_inference_wall_s": wall,
            "invoice_cost_cny": 0,
        }


if __name__ == "__main__":
    print("READY", NAME, load_wall, len(quantized), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=11436, log_level="warning")
