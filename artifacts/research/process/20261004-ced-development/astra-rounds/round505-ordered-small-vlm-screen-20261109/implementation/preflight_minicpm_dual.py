"""Additional CPU evidence for MiniCPM's two independent image sequences."""
import hashlib
import inspect
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
OUT = HERE / "candidates/08-minicpm"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    import torch
    from transformers import AutoConfig, AutoProcessor
    from minicpm_adapter import build, tensor_evidence
    protocol = json.loads((OUT / "protocol.json").read_text())
    contract = json.loads((OUT / "cpu-contract.json").read_text())
    config = AutoConfig.from_pretrained(protocol["model_directory"], local_files_only=True)
    processor = AutoProcessor.from_pretrained(protocol["model_directory"], local_files_only=True)
    start = config.image_start_id
    end = config.image_end_id
    image = config.image_token_id
    assert all(type(value) is int for value in (start, end, image))
    assert processor.image_processor.downsample_mode == "16x"
    rows = []
    for request in contract["requests"]:
        features, rendered = build(processor, request, ROOT, protocol["processor_kwargs"])
        assert tensor_evidence(features) == request["features"]
        assert hashlib.sha256(rendered.encode()).hexdigest() == request["rendered_sha256"]
        ids = features["input_ids"][0]
        expected = 2 if request["stage"] == "JSON_DUAL" else 1
        starts = (ids == start).nonzero().flatten().tolist()
        ends = (ids == end).nonzero().flatten().tolist()
        assert len(starts) == len(ends) == expected
        assert all(a < b for a, b in zip(starts, ends))
        assert all(ends[i] < starts[i + 1] for i in range(expected - 1))
        image_tokens = int((ids == image).sum())
        sizes = features["target_sizes"]
        assert image_tokens == int((sizes.prod(-1) // 16).sum())
        rows.append({"id": request["id"], "stage": request["stage"], "query": request["query"],
                     "repeat": request["repeat"], "separate_image_sequences": expected,
                     "image_start_positions": starts, "image_end_positions": ends,
                     "image_patch_tokens": image_tokens, "target_sizes": sizes.tolist()})
    assert len(rows) == 66 and sum(r["separate_image_sequences"] == 2 for r in rows) == 16
    assert not torch.cuda.is_initialized()
    sources = [inspect.getfile(type(processor)), inspect.getfile(type(processor.image_processor)), __file__]
    evidence = {"status": "PASS", "requests": rows, "model_loads": 0, "generation_calls": 0,
                "cpu_contract_sha256": sha(OUT / "cpu-contract.json"), "protocol_sha256": sha(OUT / "protocol.json"),
                "token_ids": {"image_start": start, "image_end": end, "image": image},
                "sources": [{"path": path, "sha256": sha(path)} for path in sources],
                "depth_causal_use": "NOT_ASSESSED"}
    with (OUT / "dual-independent-image-gate.json").open("x") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("MINICPM_INDEPENDENT_IMAGES_PASS", len(rows), "dual", 16, flush=True)


if __name__ == "__main__":
    main()
