"""R511 actual frozen SDK CPU gate; no model construction or generation."""
import hashlib
import json
import os
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[5]
CACHE=ROOT/"datasets/model-cache/ordered-small-vlm-20261109"
SDK=CACHE/"sdk/GroundingPI-98641f0b8e"
OUT=HERE/"candidates/06-groundingpi"
os.environ.update(HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",HF_HOME=str(CACHE/"hf-cache-groundingpi-r511"),HF_MODULES_CACHE=str(CACHE/"hf-modules-groundingpi-r511"),IMAGE_MAX_TOKEN_NUM="512")


def main():
    import torch
    import transformers
    import huggingface_hub,regex,tokenizers
    assert transformers.__version__=="5.7.0" and Path(transformers.__file__).is_relative_to(SDK/"vendor/transformers/src")
    assert huggingface_hub.__version__=="1.32.0" and tokenizers.__version__=="0.22.1"
    sys.path.insert(0,str(SDK))
    from infer.serve_vlm import bundled_transformers
    assert bundled_transformers()[1]=="90dd8674248257e1115e531f2250fd85a32c3863"
    from transformers import AutoConfig,AutoProcessor
    from transformers.dynamic_module_utils import get_class_from_dynamic_module
    from groundingpi_adapter import build,tensor_evidence,native_prompt,parse_native
    model=str(CACHE/"models/GroundingPI")
    config=AutoConfig.from_pretrained(model,trust_remote_code=True,local_files_only=True)
    cls=get_class_from_dynamic_module(config.auto_map["AutoModelForCausalLM"],model,local_files_only=True)
    processor=AutoProcessor.from_pretrained(model,trust_remote_code=True,local_files_only=True)
    public=json.loads((HERE/"diagnostic/model-inputs.json").read_text())
    from score_native import assert_public_inputs
    assert_public_inputs(public)
    dual={c["id"]:c for c in json.loads((HERE/"diagnostic/model-inputs-dual.json").read_text())["cases"]}
    original=json.loads((HERE.parent/"round501-taichu-captured-multiscene-20261108/diagnostic/frozen-message-inputs.json").read_text())[0]["messages"][0]["content"]
    initial="Inspect image 1 (RGB) to identify the requested object and destination. Image 2 is aligned depth for spatial context."
    assert original.startswith(initial)
    single="Inspect the RGB image to identify the requested object and destination."+original[len(initial):]
    requests=[]
    for mode in ("box","point"):
        for case in public["cases"]:
            for kind in ("target","destination"):
                requests.append({"id":case["id"],"query":kind,"mode":mode,"stage":"NATIVE_RGB","repeat":False,"rgb_path":case["rgb_path"],"rgb_sha256":case["rgb_sha256"],"phrase":case[kind+"_phrase"]})
        requests.extend([dict(requests[-32],repeat=True) for _ in range(2)])
    for stage in ("JSON_RGB","JSON_DUAL"):
        for case in public["cases"]:
            row={"id":case["id"],"query":"task","mode":None,"stage":stage,"repeat":False,"rgb_path":case["rgb_path"],"rgb_sha256":case["rgb_sha256"],"instruction":case["instruction"],"system":single if stage=="JSON_RGB" else original}
            if stage=="JSON_DUAL":row.update(depth_path=dual[case["id"]]["depth_path"],depth_sha256=dual[case["id"]]["depth_sha256"])
            requests.append(row)
    for i,row in enumerate(requests):
        features,text=build(processor,row,ROOT)
        assert len(features["image_grid_thw"])==(2 if row["stage"]=="JSON_DUAL" else 1)
        assert features["input_ids"].shape[1]+512<16384
        row.update(features=tensor_evidence(features),rendered_sha256=hashlib.sha256(text.encode()).hexdigest())
        print("CPU_REQUEST_PASS",i+1,row["stage"],row["id"],flush=True)
    assert not torch.cuda.is_initialized()
    result={"status":"PASS","model_class":cls.__name__,"processor_class":type(processor).__name__,"requests":requests,"model_loads":0,"generation_calls":0,"cuda_initialized":False,
            "versions":{"transformers":transformers.__version__,"huggingface_hub":huggingface_hub.__version__,"tokenizers":tokenizers.__version__,"regex":regex.__version__,"torch":torch.__version__},
            "reference_native_preprocess":"read_messages(max_images=2), render_prompt(non_thinking=True), original image_processor, expand_image_tokens, original tokenizer",
            "dual_source":"official configurable --max-images argument and complete 16-case two-grid CPU proof; depth causality NOT_ASSESSED"}
    with (OUT/"cpu-contract-r511.json").open("x") as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write("\n")
    print("GROUNDINGPI_CPU_PASS",len(requests),flush=True)


if __name__=="__main__":main()
