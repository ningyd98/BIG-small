"""Use frozen official reference preprocessing and native GAM grammar."""
import base64
import hashlib
import sys
from pathlib import Path
from score_native import point_pixel, box_pixel
from molmoer_adapter import tensor_evidence, strip_end
ROOT = Path(__file__).resolve().parents[7]
SDK = ROOT / "datasets/model-cache/ordered-small-vlm-20261109/sdk/GroundingPI-98641f0b8e"


def official():
    if str(SDK) not in sys.path:sys.path.insert(0,str(SDK))
    from grounding_pi import protocol
    return protocol


def native_prompt(mode,phrase):
    protocol=official()
    return (protocol.build_refer_bbox_prompt if mode=="box" else protocol.build_refer_point_prompt)(phrase)


def build(processor,request,root,processor_kwargs=None):
    official()
    from infer.serve_vlm import read_messages, render_prompt, expand_image_tokens
    content=[]
    for role in ("rgb","depth"):
        if role+"_path" not in request:continue
        path=Path(root)/request[role+"_path"];blob=path.read_bytes()
        assert hashlib.sha256(blob).hexdigest()==request[role+"_sha256"]
        content.append({"type":"image_url","image_url":{"url":"data:image/png;base64,"+base64.b64encode(blob).decode()}})
    if request["stage"]=="NATIVE_RGB":
        messages=[{"role":"user","content":content+[{"type":"text","text":native_prompt(request["mode"],request["phrase"])}]}]
    else:
        messages=[{"role":"system","content":request["system"]},{"role":"user","content":content+[{"type":"text","text":request["instruction"]}]}]
    # --max-images is an official configurable reference-server argument.
    normalized,images=read_messages(messages,max_images=2)
    rendered=render_prompt(processor,normalized,True)
    image_inputs=processor.image_processor(images=images,return_tensors="pt")
    merge=processor.image_processor.merge_size**2
    sizes=[int(grid.prod()) for grid in image_inputs["image_grid_thw"]]
    assert all(n%merge==0 for n in sizes)
    rendered=expand_image_tokens(rendered,[n//merge for n in sizes])
    return dict(processor.tokenizer([rendered],return_tensors="pt"),**image_inputs),rendered


def parse_native(raw,mode,width,height,*,reached_cap=False):
    result={"status":"INVALID","point":None,"predictions":[]}
    try:
        if reached_cap:raise ValueError("truncated native response")
        protocol=official();entries=protocol.parse_answer(strip_end(raw).strip(),task="bbox" if mode=="box" else "point",require_canonical=True)
        predictions=[]
        for entry in entries:
            for coordinates in entry.coordinates or ():
                if mode=="box":
                    box,point=box_pixel(coordinates,width,height,"normalized_999");prediction={"box":list(box),"point":list(point),"label":entry.phrase}
                else:prediction={"point":list(point_pixel(coordinates,width,height,"normalized_999")),"label":entry.phrase}
                predictions.append(prediction)
        if predictions:result.update(status="DETECTED",predictions=predictions,point=predictions[0]["point"])
        elif entries and all(entry.coordinates is None for entry in entries):result["status"]="REFUSAL"
        else:result["status"]="EMPTY"
    except ValueError as error:result["error"]=str(error)
    return {mode:result}
