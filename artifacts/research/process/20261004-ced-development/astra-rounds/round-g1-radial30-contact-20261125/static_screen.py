"""Zero-integration optical and full dense contact screen for the registered 130 mm mount."""

from __future__ import annotations

import fcntl
import json
import math
import os
import sys
from collections import Counter
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

import cv2
import mujoco
import numpy as np

from scripts.graduation import g1_visibility_radial_screen as old
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration

ROOT, BASE = old.ROOT, old.BASE
ROUND = Path(__file__).resolve().parent
PLAN = "6a8eb89a5609a01dbbd5560c28a5379b95b72c7061522299185c7ced94fc3d9c"
PARENT = "f33d25e2ebac4342e32e3878263ab6f92838ed51c715a3b0c28a9777a4dad892"
PHYSICAL = BASE/"builds"/PARENT/"runtime-source"
NEW = BASE/"batches/train-radial15-timing-01/d02"
radial = old.radial
read, write, sha, require = old.read, old.write, old.sha, old.require
NAMES = {"d01":1121,"d02":1089,"d02_radial15":1222}


def pins():
    plan=read(ROUND/"plan.json",PLAN)
    require(sha(ROUND/"plan.md")==plan["plan_md_sha256"] and plan["parent_generation"]==PARENT,"wrong plan")
    for k,v in plan["inputs_sha256"].items():
        p=ROOT/k
        if k.startswith("scripts/graduation/") and (PHYSICAL/k).is_file():
            p=PHYSICAL/k
        require(sha(p)==v,"unexpected registered input "+k)
    for path in ("scripts/graduation/g1_visibility_grid.py","scripts/graduation/g1_visibility_vision.py",
                 "scripts/graduation/g1_visibility_radial.py"):
        require(sha(ROOT/path)==sha(PHYSICAL/path),"working sensor or assembly differs from actual parent")
    require(sha(Path(old.__file__))==plan["inputs_sha256"]["scripts/graduation/g1_visibility_radial_screen.py"],
            "frozen restoration code changed")
    return plan


def registrations():
    parent=read(old.D02/"allocation.json")["geometry"]
    return {n:radial.geometry_for_screen(parent,n) for n in (15,30)}


def check_registration(geometry, offset):
    spec=radial.details(offset)
    identity=geometry["pose_marker"]
    require(geometry["registration_id"]==spec["registration_id"] and geometry["marker_family"]==spec["family"] and
            geometry["asset_path"]==spec["asset_path"] and identity["marked_asset_sha256"]==spec["asset_sha256"] and
            sha(ROOT/spec["asset_path"])==spec["asset_sha256"] and geometry["camera"]["calibration_version"]=="f33940579c533afe"
            and identity["marker_id"]==7 and identity["dictionary"]=="DICT_4X4_50" and identity["marker_size_m"]==.075,
            "wrong registered mount identity")
    dual=geometry["development_dual"]
    require(set(dual["markers"])=={"7","8"} and dual["scene_asset_sha256"]==spec["asset_sha256"] and dual["agreement_m"]==.010,
            "wrong asset or arbitration")
    for code in (7,8):
        m=dual["markers"][str(code)]
        expected=np.eye(4)
        expected[:3,3]=spec["centers"][code]
        require(m["marker_id"]==code and m["dictionary"]==identity["dictionary"] and m["marker_size_m"]==.075 and
                m["marker_registration_hash"]==PoseMarkerRegistration(code,.075,spec["asset_sha256"]).digest()
                and np.array_equal(np.reshape(m["object_T_marker"],(4,4)),expected),"wrong registered code or rigid transform")
    require(np.array_equal(dual["markers"]["7"]["object_T_marker"],geometry["marker_to_object"]),
            "wrong primary rigid transform")


def collect(dense_only=False):
    pinned=pins()
    cases={name:old.checked_case(d) for name,d in (("d01",old.D01),("d02",old.D02),("d02_radial15",NEW))}
    for name,n in NAMES.items():
        require(len(cases[name]["states"])==n,"incomplete trajectory "+name)
    require(cases["d01"]["asset_sha256"]==cases["d02"]["asset_sha256"]==old.ASSET_SHA and
            cases["d02_radial15"]["asset_sha256"]==radial.details(15)["asset_sha256"],"source asset mismatch")
    if dense_only: return cases,[]
    opt=old.ROUND/"screen-optical-15.public.json.gz"
    source=read(opt,pinned["inputs_sha256"][opt.relative_to(ROOT).as_posix()])["frames"]
    anchors=[]
    for a in source:
        name=a["case"]
        if name not in cases: cases[name]=old.checked_case(old.ARCHIVE/"trials"/name)
        case=cases[name]
        require(case["truth_sha256"]==a["original_truth_sha256"],"wrong archived truth")
        ref,=[row for row in case["index"]["frames"] if row["frame_id"]==a["frame_id"]]
        require(ref["physics_step"]==a["step"] and ref["file_sha256"]==a["original_file_sha256"],"archived anchor changed")
        anchors.append((name,a["role"],ref,a["candidate_clean"]["requires_both_codes"]))
    long=cases["d02_radial15"]["index"]["frames"][-9:]
    require([x["physics_step"] for x in long]==[*range(1160,1217,8),1221] and
            [x["label"] for x in long]==["APPROACH/feedback"]*8+["terminal"],"new collision-phase sample set differs")
    anchors.extend(("d02_radial15","contact_terminal" if r["label"]=="terminal" else "approach_feedback",r,False) for r in long)
    require(len(anchors)==31 and len({r["frame_id"] for _,_,r,_ in anchors})==31,"duplicate or absent anchor")
    return cases,anchors


def pairs(model):
    robot=list(old.cam.arm_geometries(model).values())
    rows=[(a,b,True) for a in old.PARTS for b in [*robot,"table","target_region_geom"]]
    for arm in robot:
        rows.extend((other,arm,not (other=="object_geom" and arm in old.FINGERS)) for other in ("object_geom","table","target_region_geom"))
    rows.extend((("object_geom","table",False),("object_geom","target_region_geom",True)))
    require(len(rows)==len({frozenset((a,b)) for a,b,_ in rows}),"duplicate measured pair")
    return [(a,b,model.geom(a).id,model.geom(b).id,g) for a,b,g in rows]


def contact_summary(model, data):
    contacts=[]; ids=set()
    for v in data.contact:
        i,j=int(v.geom1),int(v.geom2)
        a,b=model.geom(i).name,model.geom(j).name
        ids.add(tuple(sorted((i,j))))
        contacts.append({"pair":[a,b],"distance_mm":float(v.dist)*1000,"category":old.contact_category(a,b)})
    return contacts,ids


def distance_profile(case, registration, model, data, all_pairs, baseline):
    rows=[]; minimum={}; unproved=[]; hazards=[]; mismatch=[]; residuals=Counter(); contact_steps=Counter()
    for entry in case["states"]:
        step=entry["physics_step"]
        residual=old.restore(model,data,entry)
        for k,v in residual.items(): residuals[k]=max(residuals[k],v)
        actual,ids=contact_summary(model,data)
        for k in {r["category"] for r in actual}:contact_steps[k]+=1
        geometric=any(c["category"]=="unauthorized" for c in actual)
        native=Counter(tuple(sorted(x)) for x in entry["contact_pairs"])
        match=native==Counter(tuple(sorted(c["pair"])) for c in actual)
        if not match:mismatch.append(step)
        raw=[];adjustments=[];wrong=[]
        for n,(a,b,i,j,gate) in enumerate(all_pairs):
            d=float(mujoco.mj_geomDistance(model,data,i,j,3,None))
            require(math.isfinite(d) and d<3,"unmeasured pair")
            cert,method=old.geometric_witness(model,data,i,j,d,ids)
            mm=1000*cert
            raw.append(1000*d)
            if method!="mj_geomDistance":adjustments.append([n,mm,method])
            if gate and cert<=0:
                wrong.append([n,mm,method])
                if method=="separation_unproved":unproved.append(step)
            if n not in minimum or mm<minimum[n]["minimum_mm"]:
                minimum[n]={"pair":[a,b],"step":step,"minimum_mm":mm,"raw_mj_geomDistance_mm":1000*d,"method":method,"strict":gate}
        if wrong or geometric:hazards.append({"step":step,"nonpositive_or_unproved":wrong,
                    "unauthorized_contacts":[c for c in actual if c["category"]=="unauthorized"]})
        rows.append({"step":step,"raw_signed_mm":raw,"separation_witness":adjustments,"restoration":residual,
                     "reconstructed_contacts":actual,"original_contact_pairs":entry["contact_pairs"],"multiplicity_matches_native":match})
    require(len(rows)==len(case["states"]),"missing restored state")
    if baseline: require(not mismatch,"original contact manifold differs at "+str(mismatch[:10]))
    protected=[r for r in minimum.values() if r["strict"]]
    hand=[r for r in protected if r["pair"][0] in old.PARTS and r["pair"][1] in (*old.FINGERS,"hand")]
    source={"truth_sha256":case["truth_sha256"],"pixel_index_sha256":case["index_sha256"],
            "episode":case["index"]["episode"],"original_asset_sha256":case["asset_sha256"],"rendered_asset_sha256":registration["pose_marker"]["marked_asset_sha256"]}
    summary={"states":len(rows),"start":0,"end":rows[-1]["step"],"pairs_per_state":len(all_pairs),"source":source,
         "minimum_each_pair":list(minimum.values()),"closest_restricted_pair":min(protected,key=lambda r:r["minimum_mm"]),
         "closest_hand_or_finger_to_mount":min(hand,key=lambda r:r["minimum_mm"]),"contact_steps":dict(contact_steps),
         "unauthorized_contact_steps":contact_steps.get("unauthorized",0),"unproved_separation_steps":len(set(unproved)),
         "nonpositive_or_unauthorized_steps":len(hazards),"first_hazard":hazards[0] if hazards else None,
         "maximum_restoration_residual":dict(residuals),"source_contact_multiplicity_differences":mismatch,
         "reset_qualified":not any(x["step"]==0 for x in hazards),"eligible":not hazards}
    return summary,{"pair_order":[[a,b] for a,b,*_ in all_pairs],"states":rows,"violations":hazards}


def dense(work):
    cases,_=collect(True)
    geom=registrations()[30]
    check_registration(geom,30)
    summaries={"native":{},"candidate":{}}
    for name,case in cases.items():
        for tag,g in (("native",case["geometry"]),("candidate",geom)):
            m=old.checked_model(ROOT/g["asset_path"],g); d=mujoco.MjData(m)
            summary,detail=distance_profile(case,g,m,d,pairs(m),tag=="native")
            target=work/("dense-"+tag+"-"+name+".json.gz")
            write(target,detail)
            summaries[tag][name]={**summary,"detail_sha256":sha(target)}
            print(name,tag,summary["closest_hand_or_finger_to_mount"],summary["first_hazard"],flush=True)
    source=summaries["native"];new=summaries["candidate"]
    require(source["d01"]["first_hazard"]["step"]==1120 and source["d02"]["eligible"] and
            source["d02_radial15"]["first_hazard"]["step"]==1221,"known original physical failures not reproduced")
    out={"schema":"g1.visibility.radial30-dense-screen.v1","plan_sha256":PLAN,"parent_generation":PARENT,
         "candidate_asset_sha256":geom["pose_marker"]["marked_asset_sha256"],"dense_states":sum(r["states"] for r in new.values()),
         "native_states":sum(r["states"] for r in source.values()),"trajectories":summaries,"zero_integrations":True,
         "eligible":all(r["eligible"] and r["reset_qualified"] for r in new.values()),
         "unauthorized_contact_steps":sum(r["unauthorized_contact_steps"] for r in new.values()),
         "unproved_separation_steps":sum(r["unproved_separation_steps"] for r in new.values()),
         "all_sources_contact_multiplicity_exact":all(not r["source_contact_multiplicity_differences"] for r in source.values())}
    write(work/"screen-clearance-summary.json",out)
    print("DENSE",out["dense_states"],out["eligible"],flush=True)


if __name__=="__main__":
    cmd,*argv=sys.argv[1:]
    if cmd=="dense": dense(Path(argv[0]))

