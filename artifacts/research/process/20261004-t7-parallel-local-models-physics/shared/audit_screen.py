"""Independent read-only replay of screen image binding and metric arithmetic."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import math
import struct
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values,q):
    if not values:
        return None
    values=sorted(values)
    i=(len(values)-1)*q
    return values[math.floor(i)]+(values[math.ceil(i)]-values[math.floor(i)])*(i-math.floor(i))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("screen",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    bank=BASE/"shared/scene-bank"
    assignments=read(bank/"assignments.json")["cases"]
    manifest=read(bank/"bank-manifest.json")
    rows=read(args.screen/"results.json")
    errors=[]
    for relative,expected in manifest["files"].items():
        if sha(bank/relative)!=expected:
            errors.append("bank hash differs: "+relative)
    protocol=read(args.screen/"protocol.json")
    if protocol["bank_manifest_sha256"]!=sha(bank/"bank-manifest.json"):
        errors.append("bank protocol binding differs")
    by_id={row["case_id"]:row for row in rows}
    if len(by_id)!=20 or len(rows)!=20 or set(by_id)!={case["case_id"] for case in assignments}:
        errors.append("not exactly one retained result per20 assignments")
    conditional_errors=[]
    all_valid_errors=[]
    geometric_hits={"positive":0,"negative_absent":0,"FIXED_S01":0}
    bindings=0
    for case in assignments:
        if case["case_id"] not in by_id:
            continue
        row=by_id[case["case_id"]]
        case_path=bank/"cases"/case["case_id"]
        out_path=args.screen/"cases"/case["case_id"]
        if row!=read(out_path/"outcome.json"):
            errors.append(case["case_id"]+": aggregate differs from individual result")
        if row["kind"]!=case["kind"] or row["scene_sha256"]!=case.get("scene_sha256"):
            errors.append(case["case_id"]+": assignment binding differs")
        calls=read(out_path/"requests.json")
        chats=[call for call in calls if call["path"] in {"/api/chat","/chat/completions","/v1/chat/completions"}]
        if len(chats)!=1:
            errors.append(case["case_id"]+": expected exactly1 actual model call")
            continue
        message_images=[]
        image_messages=0
        for message in chats[0]["request"].get("messages",[]):
            images=list(message.get("images",[]))
            if isinstance(message.get("content"),list):
                images += [part["image_url"]["url"].split(",",1)[1]
                           for part in message["content"] if part.get("type")=="image_url"]
            if images:
                image_messages+=1
                if message.get("role")!="user":
                    errors.append("images outside user message")
            message_images += images
        hashes=[hashlib.sha256(base64.b64decode(value,validate=True)).hexdigest() for value in message_images]
        expected=[sha(case_path/"initial-offline/rgb.png"),sha(case_path/"initial-offline/depth.png")]
        if hashes!=expected or image_messages!=1:
            errors.append(case["case_id"]+": dual image transport differs")
        else:
            bindings+=1
        if any(key in json.dumps(chats[0]["request"]) for key in ["scene_parameters","geom_ids","initial_truth"]):
            errors.append(case["case_id"]+": oracle metadata in model request")
        response=chats[0].get("response",{})
        if "error" not in chats[0] and response.get("model")!=protocol["model"]["model"]:
            errors.append(case["case_id"]+": returned model identity differs")
        metadata=read(case_path/"initial-offline/observation.json")
        binding=read(case_path/"frame-binding.json")
        if len(set(binding["pass_state_hashes"]))!=1 or not binding["synchronized"]:
            errors.append(case["case_id"]+": capture passes not synchronized")
        pixel=row["attempt"].get("target_offline_check",{}).get("pixel")
        check=row["attempt"].get("target_offline_check",{})
        world=None
        hit=False
        if (isinstance(pixel,(list,tuple)) and len(pixel)==2 and all(type(p)is int for p in pixel)
            and 0<=pixel[0]<metadata["width"] and 0<=pixel[1]<metadata["height"]):
            index=pixel[1]*metadata["width"]+pixel[0]
            ids=(case_path/"initial-offline/instance_geom_ids.i32").read_bytes()
            geom=struct.unpack_from("<i",ids,index*4)[0]
            depth=struct.unpack_from("<f",(case_path/"initial-offline/depth.f32").read_bytes(),index*4)[0]
            valid=(case_path/"initial-offline/valid_mask.u8").read_bytes()[index]
            hit=metadata["instance_labels"].get(str(geom))=="object_geom" and bool(valid) and depth>0
            if valid and depth>0:
                fx,fy,cx,cy=metadata["intrinsics"]
                camera=[(pixel[0]-cx)*depth/fx,(pixel[1]-cy)*depth/fy,depth]
                matrix=metadata["camera_to_world"]
                world=[sum(matrix[r+a]*camera[a] for a in range(3))+matrix[r+3] for r in(0,4,8)]
        if hit!=row["attempt"]["target_hit"]:
            errors.append(case["case_id"]+": independently replayed hit differs")
        geometric_hits[case["kind"]]+=hit
        truth=read(case_path/"initial-truth.json")
        target=next(t for t in truth["instances"] if t["role"]=="target")
        top=[*target["position"][:2],target["position"][2]+target["half_size"][2]]
        metric=1000*math.dist(world,top) if world is not None else None
        logged=row["target_top_center_error_mm"]
        if (metric is None)!=(logged is None) or (metric is not None and not math.isclose(metric,logged,abs_tol=1e-9)):
            errors.append(case["case_id"]+": independently replayed world localization differs")
        if world is not None and isinstance(check.get("world_surface_point_m"),dict):
            if math.dist(world,[check["world_surface_point_m"][a] for a in("x","y","z")])>1e-12:
                errors.append(case["case_id"]+": deprojected world point differs")
        if case["kind"]=="positive" and metric is not None:
            all_valid_errors.append(metric)
            if hit:
                conditional_errors.append(metric)
    summary=read(args.screen/"summary.json")
    if summary["target_error_p90_mm"]!=percentile(all_valid_errors,.9):
        errors.append("all-valid-point P90 differs")
    payload={"valid":not errors,"errors":errors,"retained_cases":len(rows),
             "verified_same_message_dual_image_calls":bindings,"physical_actions":0,
             "independent_target_hits":geometric_hits,
             "target_hit_conditional_P90_mm":percentile(conditional_errors,.9),
             "target_hit_conditional_coverage":f"{len(conditional_errors)}/12",
             "all_valid_point_P90_mm":percentile(all_valid_errors,.9),
             "all_valid_point_coverage":f"{len(all_valid_errors)}/12",
             "screen_results_sha256":sha(args.screen/"results.json")}
    with args.output.open("x") as f:
        json.dump(payload,f,indent=2,allow_nan=False)
    print(json.dumps(payload,indent=2))
    if errors:
        raise SystemExit(1)


if __name__=="__main__":
    main()
