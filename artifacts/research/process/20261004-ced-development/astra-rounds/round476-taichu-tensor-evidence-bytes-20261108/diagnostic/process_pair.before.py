"""Inspect actual official-processor features for the two captured images."""

import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/zdtaichu5-9b-fp8-round473"
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                  HF_HOME=str(CACHE / "hf-runtime"), HF_MODULES_CACHE=str(CACHE / "hf-modules"))


def process(processor):
    protocol = json.loads((HERE / "dual-image-protocol.json").read_text())
    messages = json.loads(Path(protocol["messages_path"]).read_text())
    for image in protocol["images"]:
        raw = Path(image["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != image["sha256"]:
            raise ValueError("image source drift")
    started = time.perf_counter()
    features = processor.from_messages(messages, return_tensors="pt")
    elapsed = time.perf_counter() - started
    info = {}
    for key, value in features.items():
        if hasattr(value, "shape"):
            info[key] = {"shape": list(value.shape), "dtype": str(value.dtype),
                         "sha256": hashlib.sha256(value.detach().cpu().numpy().tobytes()).hexdigest()}
            if key in ["num_patches", "image_grid_thw", "image_flags"]:
                info[key]["values"] = value.tolist()
        else:
            info[key] = {"value": value}
    patches = features.get("num_patches")
    if hasattr(patches, "tolist"):
        patches = patches.tolist()
    grid = features.get("image_grid_thw")
    two_images = len(patches) == 2 if patches is not None else (
        grid is not None and len(grid) == 2)
    context = features["input_ids"].shape[-1]
    if not two_images or context > 8192:
        raise ValueError("processor did not preserve two image entries or exceeded 8192 context")
    record = {"status": "PASS", "input_image_count": 2,
              "input_image_sha256": [image["sha256"] for image in protocol["images"]],
              "input_image_order": [image["kind"] for image in protocol["images"]],
              "processor_two_distinct_images": True, "features": info,
              "input_tokens": context, "processor_s": elapsed,
              "image_processor_config": processor.image_processor.to_dict(),
              "template_sha256": hashlib.sha256((processor.tokenizer.chat_template or "").encode()).hexdigest()}
    return features, record


def main():
    route = sys.argv[1].lower()
    try:
        from transformers import AutoProcessor

        processor = AutoProcessor.from_pretrained(str(CACHE), trust_remote_code=True,
                                                 local_files_only=True, use_fast=False)
        features, record = process(processor)
        record["route"] = route
        ids = features["input_ids"][0].tolist()
        raw = CACHE / "actual" / f"processor-{route}"
        raw.mkdir(exist_ok=False)
        (raw / "input-token-ids.json").write_text(json.dumps(ids))
        (raw / "decoded-input.txt").write_text(processor.tokenizer.decode(ids, skip_special_tokens=False))
    except Exception as error:
        record = {"status": "PROCESSOR_REJECTS_TWO_IMAGES", "route": route,
                  "error": str(error), "traceback": traceback.format_exc()}
        print(record["traceback"], file=sys.stderr)
    with (HERE / f"steps/processor-{route}.json").open("x") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
