"""Read the four original actuator calibrations from each dense physical trace."""

import gzip
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


def physical(base):
    dirs = ("mount-qualification-01/angles-centers-grid", "angle-physical-extension-01",
            "angle-physical-tangent-01", "angle-physical-height-01")
    summary = {}
    centers=[defaultdict(list),defaultdict(list)]
    for i,name in enumerate(dirs):
        p=base/name
        data=json.loads((p/"summary.json").read_bytes())
        h=lambda f: hashlib.sha256(f.read_bytes()).hexdigest()
        counts=defaultdict(lambda:[0,0])
        lifted=[]
        positions=[]
        negatives=[]
        raw=[]
        for x in data["cases"]:
            path=p/(x["case"]+".json.gz");sha=h(path)
            if "raw_sha256" in x and x["raw_sha256"]!=sha:raise ValueError(str(path))
            trace=json.loads(gzip.decompress(path.read_bytes()))
            orig=next(r for r in reversed(trace) if r["phase"].lower() in ("open_settle","open"))
            hold=[r for r in trace if r["phase"].lower()=="lift"][-120:]
            bilateral=len(hold)==120 and all(min(r["normal_force_N"])>0 for r in hold)
            lift=min((r["cube_bottom_m"]-orig["cube_bottom_m"] for r in hold),default=0)
            passed=bool(bilateral and lift>=.05 and not any(r["forbidden_pairs"] for r in trace))
            if passed!=x["eligible"]:raise ValueError("raw outcome drift "+str(path))
            yaw=x["nominal_cube_yaw_deg"]; counts[yaw][0]+=passed; counts[yaw][1]+=1
            raw.append([x["case"],sha])
            if passed:
                lifted.append(lift);positions.append(orig["xyz_error_object_m"])
                if i<2 and abs(yaw)<=3:centers[0][yaw].append(orig["xyz_error_object_m"][:2])
                if i==2:centers[1][yaw].append(orig["xyz_error_object_m"][:2])
            else:
                if not any(k>0 for k in orig["normal_force_N"]):raise ValueError("unexpected negative")
                negatives.append(dict(case=x["case"],yaw_deg=yaw,xy_mm=x["target_offset_xy_mm"],open_force_N=orig["normal_force_N"]))
        summary[name]=dict(index_sha256=h(p/"summary.json"),raw_digest=hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),passed=len(lifted),total=len(data["cases"]),per_yaw=counts,
                 minimum_qualified_lift_m=min(lifted),maximum_qualified_z_m=max(v[2] for v in positions),
                 minimum_qualified_z_m=min(v[2] for v in positions),negative_open_touch=negatives)
    bounds=[[-.00379,.00129,.00274],[-.00479,.00319,.00169]]
    hulls=[]
    for tab,box in zip(centers,bounds,strict=True):
        corners=list(itertools.product(box[:2],[-box[2],box[2]]))
        distances=[]
        for yaw,points in tab.items():
            poly=cv2.convexHull(np.asarray(points,np.float32))
            distances.extend(cv2.pointPolygonTest(poly,c,True) for c in corners)
        if min(distances)<0:raise ValueError("unmeasured rectangle")
        hulls.append(dict(registered_box_m=box,angles=sorted(tab),minimum_corner_hull_distance_m=min(distances)))
    return dict(groups=summary,rectangles=hulls,formal_runs=0)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("base",type=Path);p.add_argument("out",type=Path)
    a=p.parse_args()
    payload=json.dumps(physical(a.base),ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    with a.out.open("x") as f:f.write(payload)

