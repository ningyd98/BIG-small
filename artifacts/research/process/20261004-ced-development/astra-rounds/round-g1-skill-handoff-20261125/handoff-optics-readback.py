"""Fit independent current-camera rigidity residuals and verify all mechanical corners on unseen trajectories."""
import argparse
import gzip
import importlib.util
import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path
import time

import numpy as np
from scripts.graduation import g1_complete_cv_handoff_optics as optical
from scripts.graduation.g1_complete_cv_calibrate import digest,write

from cloud_edge_robot_arm.vision.observations import RGBDObservation


BASE=Path("experiments/results/g1-complete-cv-repair-20261125")
NORMAL=Path("experiments/results/g1-skill-handoff-20261125/physical-capture-01")
FROZEN=BASE/"builds/9ed09852049be122ae5ff684af8d89e20012dcae7486db44e93421e075d57caf/runtime-source/scripts/graduation/g1_visibility_vision.py"
SIGN=np.asarray(list(itertools.product((-1.,1.),repeat=3)))


def detector():
    module=importlib.util.spec_from_file_location("g1_qualified_native_detector",FROZEN)
    instrument=importlib.util.module_from_spec(module);module.loader.exec_module(instrument)
    return instrument.measure_frame


def one(frame,folder,compiled,read,normals,truths,fit):
    src=folder/frame["file"]
    if digest(src)!=frame["sha256"]:raise ValueError("raw frame hash mismatch")
    img=RGBDObservation.model_validate_json(gzip.decompress(src.read_bytes()))
    marker=read(img,compiled["geometry"])
    start=time.perf_counter_ns()
    pose=optical.measured_pose(img,marker,compiled["geometry"]) if fit else optical.rigid_pose(img,marker,compiled["geometry"])
    elapsed=(time.perf_counter_ns()-start)/1e6
    result=dict(curve=frame["curve"],stage=frame["stage"],step=frame["step"],raw=frame["sha256"],
                ids=marker["usable_ids"],marker_reason=marker["reason"],available=bool(pose),local_ms=elapsed)
    if not pose:return result
    values=normals[frame["curve"]];i=frame["i"]
    gi=next(j for j,name in enumerate(truths[frame["curve"]]['names']) if name=="object_geom")
    world=values['centers'][i,gi]
    actual=values['rotation'][i,gi]
    estimate=np.asarray(pose["rotation_object_to_world"])
    result["method"]=pose["method"]
    result["anchor"]=abs((world+actual@pose["anchor_object_m"]-pose["anchor_world_m"])@estimate).tolist()
    result["basis"]=abs(estimate.T@actual-np.eye(3)).tolist()
    result["center_error_m"]=float(np.linalg.norm(np.asarray(pose["center_world_m"])-world))
    result["orientation_error_deg"]=float(np.degrees(np.arccos(np.clip((np.trace(estimate.T@actual)-1)/2,-1,1))))
    if not fit:
        b=optical.CALIBRATION[pose["method"]]
        result["componentwise_valid"]=bool(np.all(np.asarray(result["anchor"])<=b["anchor"]) and np.all(np.asarray(result["basis"])<=b["basis"]))
        ratios=[];maximum=[]
        for name,solid in compiled["structure"].items():
            j=list(truths[frame["curve"]]["names"]).index(name)
            pts=np.asarray(solid["center_object_m"])+SIGN*solid["half_extent_m"]
            ground=values["centers"][i,j]+(SIGN*solid["half_extent_m"])@values["rotation"][i,j].T
            observed=pose["center_world_m"]+pts@estimate.T
            diff=(observed-ground)@estimate
            limit=np.asarray(pose["anchor_error_object_m"])+abs(pts-pose["anchor_object_m"])@np.asarray(pose["basis_error_object"]).T
            ratios.append(float(np.max(abs(diff)/limit)))
            maximum.append(float(np.max(np.linalg.norm(diff,axis=1))))
        result.update(all_entity_corner_max_ratio=max(ratios),max_entity_corner_error_m=max(maximum),
            center_cert_m=pose["center_error_m"],angular_cert_deg=float(np.degrees(pose["rotation_error_rad"])))
    return result


def report(inputs,out,private,fit):
    compiled=json.loads(gzip.decompress((BASE/"mount-optics-02/capture-gpu/compiled.json.gz").read_bytes()))
    reader=detector()
    idx=json.loads((inputs/"index.json").read_bytes())
    normal={};geo={}
    results=[]
    for raw in idx["records"]:
        if raw["curve"] not in normal:
            data=np.load(NORMAL/raw["curve"]/"normal.npz")
            normal[raw["curve"]]={k:data[k] for k in ("centers","rotation")}
            geo[raw["curve"]]=dict(np.load(NORMAL/raw["curve"]/"physical-geometries.npz"))
        results.append(one(raw,inputs,compiled,reader,normal,geo,fit))
    active=[r for r in results if r['available']]
    outdata=dict(capture_index_sha256=digest(inputs/"index.json"),renderer=idx['renderer'],
              n=len(results),measurable=len(active),native_marker_sha256=digest(FROZEN),by_stage={},
              marker_reject=dict(Counter(r["marker_reason"] for r in results if not r["available"])))
    if fit:
        profiles={}
        for k in sorted(set(r['method'] for r in active)):
            rows=[r for r in active if r["method"]==k]
            if len(rows)<5:continue
            profiles[k]={field:(np.ceil((1.35*np.max([r[field] for r in rows],axis=0)+floor)*1e6)/1e6).tolist()
                         for field,floor in (("anchor",.0002),("basis",.0015))}
        outdata['bounds']=profiles
    for stage in sorted(set(r["stage"] for r in results)):
        rs=[r for r in results if r["stage"]==stage]
        certain=[r for r in rs if r['available']]
        outdata['by_stage'][stage]=dict(n=len(rs),usable=len(certain),methods=dict(Counter(r['method'] for r in certain)))
    if not fit:
        outdata['failures']=[{k:r[k] for k in ('curve','step','method','componentwise_valid','all_entity_corner_max_ratio')}
              for r in active if not(r['componentwise_valid'] and r['all_entity_corner_max_ratio']<=1)]
        outdata['methods']={}
        for method in sorted({r['method'] for r in active}):
            rows=[r for r in active if r['method']==method]
            outdata['methods'][method]={k:max(r[k] for r in rows) for k in [
                'center_error_m','center_cert_m','orientation_error_deg','angular_cert_deg','max_entity_corner_error_m','all_entity_corner_max_ratio']}
            outdata['methods'][method]['n']=len(rows)
    outdata['max_estimation_ms']=max(r["local_ms"] for r in results)
    write(private,results)
    outdata['details_sha256']=digest(private)
    write(out,outdata)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ("input","out","details"):parser.add_argument(k,type=Path)
    parser.add_argument("--fit",action="store_true")
    a=parser.parse_args();report(a.input,a.out,a.details,a.fit)

