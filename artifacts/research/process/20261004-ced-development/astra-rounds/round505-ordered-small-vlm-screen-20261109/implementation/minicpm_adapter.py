"""Published MiniCPM-V4.7 grounding: boxed 0..1000 and documented legacy box."""
import re
from score_native import box_pixel
from chat_candidate_adapter import build as chat_build
from molmoer_adapter import tensor_evidence, strip_end, next_call_index


def native_prompt(mode,phrase):
    assert mode=="box"
    return ('Please provide the bounding box coordinate of the region this sentence '
            f'describes: <ref>{phrase}</ref> If the requested item is not visible, return exactly ABSENT.')


def build(processor,request,root,processor_kwargs):
    if request["stage"]!="NATIVE_RGB":return chat_build(processor,request,root,processor_kwargs)
    import hashlib
    from pathlib import Path
    from PIL import Image
    path=Path(root)/request["rgb_path"];assert hashlib.sha256(path.read_bytes()).hexdigest()==request["rgb_sha256"]
    messages=[{"role":"user","content":[{"type":"image","image":Image.open(path).convert("RGB")},{"type":"text","text":native_prompt("box",request["phrase"])}]}]
    text=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
    features=processor.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=True,return_tensors="pt",**processor_kwargs)
    return features,text


def parse_native(raw,mode,width,height):
    assert mode=="box"
    text=strip_end(raw).strip();result={"status":"INVALID","point":None,"predictions":[]}
    if text=="ABSENT":result["status"]="REFUSAL";return {mode:result}
    try:
        matches=list(re.finditer(r"\\boxed\{\s*\[?\s*([\d,\s]+?)\s*\]?\s*\}|<box>\s*([\d\s]+?)\s*</box>",text))
        if not matches or re.search(r"\bABSENT\b",text):raise ValueError("missing published bbox or contradictory absence")
        predictions=[]
        for match in matches:
            values=[int(x) for x in re.split(r"[,\s]+",(match.group(1) or match.group(2)).strip()) if x]
            box,point=box_pixel(values,width,height,"normalized_1000");predictions.append({"box":list(box),"point":list(point)})
        result.update(status="DETECTED",predictions=predictions,point=predictions[0]["point"])
    except ValueError as error:result["error"]=str(error)
    return {mode:result}
