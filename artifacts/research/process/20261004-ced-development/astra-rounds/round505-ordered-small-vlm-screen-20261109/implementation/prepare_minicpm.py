"""Freeze real processor contracts and request list before model loading."""
import hashlib
import json
import os
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[5]
CACHE = ROOT / "datasets/model-cache/ordered-small-vlm-20261109"
candidate = sys.argv[1]
out = HERE / "candidates" / candidate
settings = {
    "05-rynn": {"repo": "DAMO_Academy/RynnBrain1.1-2B", "model": "RynnBrain1.1-2B", "native_modes": ["box", "point"], "processor_kwargs": {}, "generate_kwargs": {}},
    "08-minicpm": {"repo": "OpenBMB/MiniCPM-V-4.7-1B", "model": "MiniCPM-V-4.7-1B", "native_modes": ["box"], "processor_kwargs": {"downsample_mode": "16x", "max_slice_nums": 36}, "generate_kwargs": {"downsample_mode": "16x"}},
}[candidate]
os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HOME=str(CACHE / "hf-runtime"), HF_MODULES_CACHE=str(CACHE / ("hf-modules-" + candidate)))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    import torch
    import transformers
    from transformers import AutoConfig, AutoProcessor, AutoModelForImageTextToText
    from minicpm_adapter import build, tensor_evidence, native_prompt
    from score_native import assert_public_inputs
    model = str(CACHE / "models" / settings["model"])
    config = AutoConfig.from_pretrained(model, local_files_only=True)
    cls = AutoModelForImageTextToText._model_mapping[type(config)]
    processor = AutoProcessor.from_pretrained(model, local_files_only=True)
    public = json.loads((HERE / "diagnostic/model-inputs.json").read_text())
    assert_public_inputs(public)
    dual = {r["id"]: r for r in json.loads((HERE / "diagnostic/model-inputs-dual.json").read_text())["cases"]}
    original = json.loads((HERE.parent / "round501-taichu-captured-multiscene-20261108/diagnostic/frozen-message-inputs.json").read_text())[0]["messages"][0]["content"]
    initial = "Inspect image 1 (RGB) to identify the requested object and destination. Image 2 is aligned depth for spatial context."
    assert original.startswith(initial)
    single = "Inspect the RGB image to identify the requested object and destination." + original[len(initial):]
    assert settings["native_modes"] == ["box"]
    requests = []
    for mode in settings["native_modes"]:
        for case in public["cases"]:
            for kind in ("target", "destination"):
                requests.append({"id": case["id"], "query": kind, "mode": mode, "stage": "NATIVE_RGB", "repeat": False,
                                 "rgb_path": case["rgb_path"], "rgb_sha256": case["rgb_sha256"], "phrase": case[kind + "_phrase"]})
        for _ in range(2):
            case = public["cases"][0]
            requests.append({"id": case["id"], "query": "target", "mode": mode, "stage": "NATIVE_RGB", "repeat": True,
                             "rgb_path": case["rgb_path"], "rgb_sha256": case["rgb_sha256"], "phrase": case["target_phrase"]})
    for stage in ("JSON_RGB", "JSON_DUAL"):
        for case in public["cases"]:
            request = {"id": case["id"], "query": "task", "mode": None, "stage": stage, "repeat": False,
                       "rgb_path": case["rgb_path"], "rgb_sha256": case["rgb_sha256"], "instruction": case["instruction"], "system": single if stage == "JSON_RGB" else original}
            if stage == "JSON_DUAL":
                request.update(depth_path=dual[case["id"]]["depth_path"], depth_sha256=dual[case["id"]]["depth_sha256"])
            requests.append(request)
    for i, request in enumerate(requests):
        features, text = build(processor, request, ROOT, settings["processor_kwargs"])
        assert features["input_ids"].shape[1] + 512 < 16384
        if "image_grid_thw" in features:
            assert len(features["image_grid_thw"]) == (2 if request["stage"] == "JSON_DUAL" else 1)
        assert all(hasattr(value, "shape") for value in features.values()), "non-tensor input requires explicit complete evidence"
        request.update(features=tensor_evidence(features), rendered_sha256=hashlib.sha256(text.encode()).hexdigest())
        print("CPU_REQUEST", i+1, request["stage"], request["id"], flush=True)
    assert not torch.cuda.is_initialized() and len(requests) <= 134
    contract = {"status": "PASS", "requests": requests, "model_class": cls.__name__, "processor_class": type(processor).__name__,
                "versions": {"torch": torch.__version__, "transformers": transformers.__version__}, "model_loads": 0, "generation_calls": 0}
    with (out / "cpu-contract.json").open("x") as stream:
        json.dump(contract, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    assets = json.loads((out / "download-result.json").read_text())
    for row in assets["files"]:
        path = Path(row["path"])
        assert path.stat().st_size == row["size"] and sha(path) == row["sha256"]
    sources = [HERE / "implementation" / p for p in ["score_native.py", "molmoer_adapter.py", "run_candidate_molmoer.py", "chat_candidate_adapter.py", "prepare_chat_candidate.py", "run_chat_candidate.py", "minicpm_adapter.py", "prepare_minicpm.py", "run_minicpm.py"]]
    protocol = {"candidate": candidate, "official_model_repo": settings["repo"], "model_directory": model,
                "runtime": sys.executable, "precision": "BF16 full model", "attention": "sdpa", "thinking": False,
                "native_modes": settings["native_modes"], "primary_mode": settings["native_modes"][0] if settings["native_modes"] else None,
                "JSON_RGB": "SUPPORTED_CPU_PASS", "JSON_DUAL": "SUPPORTED_CPU_PASS", "depth_causal_use": "NOT_ASSESSED",
                "processor_kwargs": settings["processor_kwargs"], "generate_kwargs": settings["generate_kwargs"],
                "native_prompt_examples": {mode: native_prompt(mode, "{phrase}") for mode in settings["native_modes"]},
                "native_coordinates": "normalized_1000, original-order first candidate, no oracle",
                "authorized_model_loads": 1, "authorized_generation_calls": len(requests),
                "generation": {"max_new_tokens": 512, "do_sample": False, "num_beams": 1, "use_cache": True, "seed": 0},
                "cpu_contract_sha256": sha(out / "cpu-contract.json"), "public_inputs_sha256": sha(HERE / "diagnostic/model-inputs.json"),
                "plan_sha256": sha(HERE / "plan.json"), "asset_manifest_sha256": sha(out / "asset-manifest.json"),
                "research_sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sources],
                "formal_acceptance": "NOT_PERFORMED", "hardware_dispatch": False}
    with (out / "protocol.json").open("x") as stream:
        json.dump(protocol, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("CHAT_CANDIDATE_PROTOCOL_PASS", candidate, len(requests), flush=True)


if __name__ == "__main__":
    main()
