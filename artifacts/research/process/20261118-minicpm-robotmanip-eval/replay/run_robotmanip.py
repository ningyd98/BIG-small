"""Run unmodified RobotManip VLA and an explicitly non-native probe of its embedded VLM."""
import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

import diffusers
import numpy as np
import torch
import transformers
from PIL import Image

from cases import CASES, FRAMES, INSTRUCTION, MAIN, rgb_sha, sha, write_json

REVISION = "29cb257541e9f96f493abe21174f8892e5dffe3f"
OFFICIAL_CODE = "f666593066641d2c0cef06bc17bfb1e954547674"
CHECKPOINT = MAIN / "datasets/model-cache/minicpm-robotmanip-20261117/openbmb-29cb2575"
PROMPT = (
    "Point to the {phrase}. If it is not visible, output exactly ABSENT. "
    "Otherwise output only a JSON array [x,y] of two integers normalized to 0–1000 "
    "relative to this image, with [0,0] at the top left and [1000,1000] at the "
    "bottom right. Do not output a box or any other text."
)
POINT = re.compile(r"\[\s*(0|[1-9][0-9]{0,3})\s*,\s*(0|[1-9][0-9]{0,3})\s*\]")
MAX_NEW_TOKENS = 96

def probe_vlm(runner, image, phrase, eos_token_ids):
    prompt = PROMPT.format(phrase=phrase)
    messages = [{"role": "user", "content": [
        {"type": "image", "image": image},
        {"type": "text", "text": prompt},
    ]}]
    tok = runner.processor.tokenizer
    if tok.eos_token_id not in eos_token_ids:
        raise ValueError("checkpoint and chat template EOS disagree")
    started = time.perf_counter()
    features = runner.processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_dict=True,
        return_tensors="pt", enable_thinking=False, processor_kwargs={"padding": False},
    )
    features = {key: value.to(runner.device) for key, value in features.items()
                if isinstance(value, torch.Tensor)}
    input_tokens = int(features["input_ids"].shape[1])
    torch.cuda.synchronize()
    generation_started = time.perf_counter()
    with torch.inference_mode(), torch.autocast("cuda", dtype=runner.model.vlm_dtype):
        output = runner.model.vlm.generate(
            **features, max_new_tokens=MAX_NEW_TOKENS, do_sample=False, num_beams=1, use_cache=True,
            eos_token_id=eos_token_ids, pad_token_id=tok.pad_token_id,
        )
    torch.cuda.synchronize()
    generation_s = time.perf_counter() - generation_started
    ids = output[0, input_tokens:].tolist()
    raw = tok.decode(ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
    decoded = tok.decode(ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    text = decoded.strip()
    match = POINT.fullmatch(text)
    coords = None if match is None else [int(x) for x in match.groups()]
    if len(ids) >= MAX_NEW_TOKENS:
        status, coords, error = "INVALID", None, "output token cap"
    elif text == "ABSENT":
        status, coords, error = "ABSENT", None, None
    elif coords is not None and all(0 <= x <= 1000 for x in coords):
        status, error = "POINT", None
    else:
        status, coords, error = "INVALID", None, "not exactly an in-range integer JSON pair or ABSENT"
    return {"status": status, "normalized_1000": coords, "error": error, "raw_text": raw,
            "decoded_text": decoded, "prompt": prompt, "evidence": {
                "eos_token_ids": eos_token_ids, "input_tokens": input_tokens, "output_tokens": len(ids), "token_ids": ids,
                "generation_s": generation_s, "end_to_end_s": time.perf_counter() - started}}

def main(out, official):
    out.mkdir(exist_ok=False)
    sys.path.insert(0, str(official))
    from vla_infer import MiniCPMVLAInference

    runtime = {"python": sys.version.split()[0], "torch": torch.__version__,
               "transformers": transformers.__version__, "diffusers": diffusers.__version__,
               "numpy": np.__version__, "gpu": torch.cuda.get_device_name(),
               "hf_revision": REVISION, "official_code_revision": OFFICIAL_CODE}
    write_json(out / "preflight.json", runtime)
    eos_token_ids = json.loads((CHECKPOINT / "generation_config.json").read_text())["eos_token_id"]
    images = {}
    for frame, folder in FRAMES.items():
        with Image.open(folder / "rgb.png") as source:
            images[frame] = source.convert("RGB")
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    runner = MiniCPMVLAInference(CHECKPOINT, device="cuda:0")
    torch.cuda.synchronize()
    load_s = time.perf_counter() - started
    loaded = {"load_s": load_s, "vlm_type": type(runner.model.vlm).__name__,
              "vlm_dtype": str(runner.model.vlm_dtype),
              "action_head_dtype": str(runner.model.action_head_dtype),
              "parameter_dtypes": sorted({str(p.dtype) for p in runner.model.parameters()}),
              "parameter_count": sum(p.numel() for p in runner.model.parameters())}
    write_json(out / "loaded.json", loaded)
    print("RobotManip loaded", load_s, flush=True)
    actions = []
    action_params = {"instruction": INSTRUCTION, "embodiment_id": 0, "state": "zero (official default)", "seed": 0}
    for frame, image in images.items():
        row = {"frame": frame, "rgb_sha256": rgb_sha(frame), **action_params}
        try:
            torch.cuda.synchronize()
            started = time.perf_counter()
            tensor = runner.predict([image], INSTRUCTION, state=None, embodiment_id=0, seed=0)
            torch.cuda.synchronize()
            seconds = time.perf_counter() - started
            arr = tensor.numpy()
            finite = bool(np.isfinite(arr).all())
            path = out / f"action-{frame}.npy"
            np.save(path, arr, allow_pickle=False)
            row.update(status="FINITE_ACTION_CHUNK" if finite and arr.shape == (30, 80) and arr.dtype == np.float32
                       else "INVALID_ACTION_CHUNK", shape=list(arr.shape), dtype=str(arr.dtype),
                       finite=finite, seconds=seconds, array_sha256=sha(path.read_bytes()))
        except Exception as exc:
            row.update(status="ERROR", error=repr(exc), traceback=traceback.format_exc())
        actions.append(row)
        write_json(out / f"action-{frame}.json", row)
        print("action", frame, row["status"], row.get("seconds"), flush=True)
    rows = []
    for i, (case, frame, phrase, _) in enumerate(CASES, 1):
        row = {"case": case, "frame": frame, "phrase": phrase, "rgb_sha256": rgb_sha(frame)}
        try:
            row.update(probe_vlm(runner, images[frame], phrase, eos_token_ids))
        except Exception as exc:
            row.update(status="ERROR", error=repr(exc), traceback=traceback.format_exc())
        rows.append(row)
        write_json(out / f"{i:02d}.json", row)
        print("vlm", case, row["status"], row.get("normalized_1000"), flush=True)
    write_json(out / "results.json", {
        "model": "openbmb/MiniCPM-RobotManip", "runtime": runtime, "loaded": loaded,
        "peak_gpu_allocated_MiB": torch.cuda.max_memory_allocated()/2**20,
        "action_results": actions, "results": rows,
    })

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("official", type=Path)
    args = parser.parse_args()
    main(args.out, args.official)
