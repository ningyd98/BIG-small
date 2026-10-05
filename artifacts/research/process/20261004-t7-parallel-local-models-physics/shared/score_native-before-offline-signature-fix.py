"""Offline scoring of retained Molmo native points on the immutable common bank."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
SOURCE=BASE/"source-snapshot"
sys.path[:0]=[str(SOURCE),str(SOURCE/"src")]
os.chdir(SOURCE)
from cloud_edge_robot_arm.cloud.planning.models import InitialPlanningRequest,SceneSummary
from cloud_edge_robot_arm.vision.model_resolver import ModelConfigSnapshot
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
from scripts import evaluate_rgbd_model_scenes as scene_eval


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


def metric_point(path,norm):
    meta=read(path/"initial-offline/observation.json")
    if not (isinstance(norm,list) and len(norm)==2 and all(type(v)is int and 0<=v<=1000 for v in norm)):
        return {"pixel":None,"world":None,"geom_label":None}
    width,height=meta["width"],meta["height"]
    pixel=[min(width-1,norm[0]*width//1000),min(height-1,norm[1]*height//1000)]
    index=pixel[1]*width+pixel[0]
    depth=struct.unpack_from("<f",(path/"initial-offline/depth.f32").read_bytes(),index*4)[0]
    valid=(path/"initial-offline/valid_mask.u8").read_bytes()[index]
    geom=struct.unpack_from("<i",(path/"initial-offline/instance_geom_ids.i32").read_bytes(),index*4)[0]
    if not valid or not math.isfinite(depth) or depth<=0:
        return {"pixel":pixel,"world":None,"geom_label":meta["instance_labels"].get(str(geom))}
    fx,fy,cx,cy=meta["intrinsics"]
    camera=[(pixel[0]-cx)*depth/fx,(pixel[1]-cy)*depth/fy,depth]
    matrix=meta["camera_to_world"]
    world=[sum(matrix[r+a]*camera[a] for a in range(3))+matrix[r+3] for r in(0,4,8)]
    return {"pixel":pixel,"world":world,"geom_label":meta["instance_labels"].get(str(geom))}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--native-output",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    bank=BASE/"shared/scene-bank"
    assignments=read(bank/"bank-manifest.json")["cases"]
    if args.output.exists():
        raise FileExistsError("refusing to overwrite offline scores")
    args.output.mkdir(parents=True)
    results=[]
    for case in assignments:
        path=bank/"cases"/case["case_id"]
        nativefile=args.native_output/(case["case_id"]+".json")
        row={"case_id":case["case_id"],"kind":case["kind"],"recorded":False,
             "target_hit":False,"destination_hit":False,"full_contract_geometry_pass":False,
             "native_explicit_absence":False,"absent_target_point_proposal":False,
             "target_top_center_error_mm":None,"physical_actions":0}
        if not nativefile.exists():
            row["error"]="missing native result"
            results.append(row)
            continue
        native=read(nativefile)
        row.update(recorded=True,native_result_sha256=sha(nativefile),model=native["model"],
                   precision=native["precision"],method=native["method"],
                   task_metrics=native["task_metrics"],contract_error=native.get("contract_error"))
        if native["case_id"]!=case["case_id"] or native["observation"]["rgb_sha256"]!=case["rgb_sha256"]:
            raise ValueError("native result is bound to a different assignment or image")
        if native["observation"]["depth_sha256"]!=case["depth_sha256"]:
            raise ValueError("native depth binding differs")
        if native["ground_truth_used_online"] is not False or native["call_count"]!=len(native["calls"]):
            raise ValueError("online boundary or call count differs")
        roles=[call["role"] for call in native["calls"]]
        if roles not in [["target","destination"],["target","destination","evidence"]]:
            raise ValueError("native method changed or calls missing")
        target,destination=[native["calls"][i]["localization"] for i in(0,1)]
        row.update(target_status=target["status"],destination_status=destination["status"],
                   native_explicit_absence=target["status"]=="absent",
                   absent_target_point_proposal=case["kind"]=="negative_absent" and target["status"]=="localized")
        for role,result,label in (("target",target,"object_geom"),("destination",destination,"target_region_geom")):
            check=metric_point(path,result.get("point"))
            row[role+"_offline_check"]=check
            row[role+"_hit"]=bool(check["world"] is not None and check["geom_label"]==label)
        truth=read(path/"initial-truth.json")
        expected=next(t for t in truth["instances"] if t["role"]=="target")
        top=[*expected["position"][:2],expected["position"][2]+expected["half_size"][2]]
        world=row["target_offline_check"]["world"]
        row["target_top_center_error_mm"]=1000*math.dist(world,top) if world else None
        decision=native.get("visual_decision")
        if decision is not None:
            observation=RGBDObservation.model_validate(read(path/"observation-transport.json"))
            # Offline adapter validation makes no endpoint requests or physical actions.
            snapshot=ModelConfigSnapshot(provider="openai_compatible",model=native["model"],
                endpoint="http://127.0.0.1:11439",weight_digest="",quantization="NATIVE_RESEARCH",
                image_size=(320,240),generation_parameters={"temperature":0,"num_predict":256},
                timeout_s=180,coordinate_system="normalized_1000",grasp_profile="mujoco_upright_box_v1")
            planner=RGBDPlannerAdapter(model=native["model"],provider="openai_compatible",model_snapshot=snapshot)
            draft=planner._ground_response(InitialPlanningRequest(
                request_id="native-offline-contract-replay",user_instruction=case["instruction"],
                observation=observation,scene=SceneSummary(scene_version=1,updated_at=datetime.now(UTC))),
                json.dumps(decision))
            attempt={"observation_evidence":draft.observation_evidence}
            row["contract_adapter_parse_error"]=draft.parse_error
            row["contract_observed_scene_present"]=draft.observed_scene is not None
            row["full_contract_geometry_pass"]=bool(draft.parse_error is None
                and draft.observed_scene is not None and draft.parsed_json is not None
                and row["target_hit"] and row["destination_hit"] and scene_eval._calibrated_offset(attempt))
        results.append(row)
    positives=[r for r in results if r["kind"]=="positive"]
    negatives=[r for r in results if r["kind"]=="negative_absent"]
    fixed=[r for r in results if r["kind"]=="FIXED_S01"]
    conditional=[r["target_top_center_error_mm"] for r in positives if r["target_hit"]]
    allvalid=[r["target_top_center_error_mm"] for r in positives if r["target_top_center_error_mm"] is not None]
    measured=[r for r in results if r["recorded"]]
    summary={"scope":"native pointing development screen, not physical closed-loop test",
        "assigned_cases":20,"recorded_cases":len(measured),"error_cases":sum(bool(r.get("error")) for r in results),
        "positive_target_hit":sum(r["target_hit"] for r in positives),
        "positive_both_hit":sum(r["target_hit"] and r["destination_hit"] for r in positives),
        "fixed_both_hit":sum(r["target_hit"] and r["destination_hit"] for r in fixed),
        "fixed_full_contract_geometry_pass":sum(r["full_contract_geometry_pass"] for r in fixed),
        "positive_full_contract_geometry_pass":sum(r["full_contract_geometry_pass"] for r in positives),
        "negative_native_explicit_absence":sum(r["native_explicit_absence"] for r in negatives),
        "negative_native_point_proposals":sum(r["absent_target_point_proposal"] for r in negatives),
        "target_hit_conditional_P90_mm":percentile(conditional,.9),
        "target_hit_conditional_coverage":f"{len(conditional)}/12",
        "all_valid_point_P90_mm":percentile(allvalid,.9),"all_valid_point_coverage":f"{len(allvalid)}/12",
        "warm_task_latency_P95_s":percentile([r["task_metrics"]["task_latency_s"] for r in measured[1:]],.95),
        "all_actual_model_calls":sum(r["task_metrics"]["model_call_count"] for r in measured),
        "physical_task_success_rate":None,"physical_misoperation_rate":None,
        "physical_actions":0,"local_API_cost_CNY_per_task":0,"total_cost_CNY_per_task":None,
        "held_out_test":False,"formal_G1":False}
    for name,payload in (("results",results),("summary",summary)):
        with (args.output/(name+".json")).open("x") as f:
            json.dump(payload,f,indent=2,allow_nan=False)
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    main()
