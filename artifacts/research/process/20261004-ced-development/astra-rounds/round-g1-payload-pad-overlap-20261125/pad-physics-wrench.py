"""Read each real transport manifold and resolve its loaded pad patch and six-axis wrench."""

import argparse
import gzip
import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
from scipy.optimize import OptimizeWarning, linprog


HERE = Path(__file__).resolve().parent
RAW = Path("experiments/results/g1-payload-pad-overlap-20261125/fit-pad-physics-01")
FITS = ("dense-fit-01", "dense-fit-02", "dense-fit-03")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def polygon(points):
    xy = sorted({tuple(p) for p in points})
    if len(xy) <= 2:
        return xy, 0.
    def side(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def edge(rows):
        out = []
        for p in rows:
            while len(out) >= 2 and side(out[-2], out[-1], p) <= 0:
                out.pop()
            out.append(p)
        return out
    hull = edge(xy)[:-1] + edge(list(reversed(xy)))[:-1]
    q = np.asarray(hull)
    area = .5*abs(np.sum(q[:,0]*np.roll(q[:,1],-1)-q[:,1]*np.roll(q[:,0],-1)))
    return [list(p) for p in hull], float(area)


def photograph(contacts, side, half):
    rows = [a for a in contacts if a[0] == side]
    if not rows:
        return {"positive_points": 0, "normal_N": 0, "force_world_N": [0,0,0],
                "moment_about_object_com_Nm": [0,0,0], "actual_loaded_patch_area_m2": 0}
    local = np.asarray([r[3] for r in rows])
    object_local = np.asarray([r[4] for r in rows])
    loads = np.asarray([r[5][0] for r in rows])
    weights = loads/loads.sum()
    hull, area = polygon(local[:,[0,2]])
    force = np.sum([r[8] for r in rows], axis=0)
    moment = np.sum([r[9] for r in rows],axis=0)
    return {
        "positive_points": len(rows), "normal_N": float(sum(loads)),
        "maximum_individual_normal_N": float(max(loads)),
        "force_world_N": force.tolist(), "force_magnitude_N": float(np.linalg.norm(force)),
        "moment_about_object_com_Nm": moment.tolist(), "moment_magnitude_Nm": float(np.linalg.norm(moment)),
        "loaded_normal_centroid_pad_m": (weights @ local).tolist(),
        "loaded_normal_centroid_object_m": (weights @ object_local).tolist(),
        "support_pad_polygon_xz_m": hull, "actual_loaded_patch_area_m2": area,
        "cloud_span_pad_xz_m": np.ptp(local[:,[0,2]], axis=0).tolist(),
        "per_point_edge_distance_pad_m": np.min(np.asarray(half)[[0,2]]-abs(local[:,[0,2]]),axis=1).tolist(),
        "per_point_normal_N": loads.tolist(), "points_on_object_m": object_local.tolist(),
        "points_on_pad_m": local.tolist(), "points_in_world_m": [r[2] for r in rows],
    }


def equilibrium(rows, com, mass, gravity):
    if len({r[0] for r in rows}) != 2:
        return 0.
    columns, budget = [], []
    for c in rows:
        basis = np.array(c[6])
        mu = np.minimum(c[7][:2], .8)
        forces = basis[0] + np.array([mu[0]*basis[1],-mu[0]*basis[1],mu[1]*basis[2],-mu[1]*basis[2]])
        lever = np.array(c[2])-com
        columns.extend(np.column_stack([forces, np.cross(lever, forces)]))
        budget.append(c[5][0])
    wrench = np.array(columns).T
    wrench[3:]*=30
    A = np.column_stack((wrench,np.r_[mass*np.array(gravity),0,0,0]))
    U = np.zeros((len(budget), 4*len(budget)+1))
    for j in range(len(budget)):
        U[j,4*j:4*j+4]=1
    c = np.zeros(U.shape[1])
    c[-1]=-1
    res = linprog(c,A_ub=U,b_ub=budget,A_eq=A,b_eq=np.zeros(6),bounds=(0,None),
                  method="highs",options={"threads":1})
    if not res.success or max(np.max(abs(A@res.x)),np.max(U@res.x-budget))>2e-6:
        raise ValueError("wrench solution failed physical equality")
    return float(res.x[-1])


def extremes(rows, target):
    if not rows:
        return None
    out = {}
    for side, name in enumerate(("left","right")):
        metrics = {}
        for key in ("normal_N","force_magnitude_N","moment_magnitude_Nm","actual_loaded_patch_area_m2"):
            values = np.array([x["pads"][side][key] for x in rows])
            high = np.flatnonzero(np.isclose(values, values.max(), atol=1e-13, rtol=0))
            low = int(np.argmin(values))
            first = rows[int(high[0])]["step"]
            last = rows[int(high[-1])]["step"]
            metrics[key]={"maximum":float(values.max()),"peak_first_step":first,"peak_last_step":last,
                          "peak_first_relative_to_rejection_s":(first-target)/240,
                          "minimum":float(values[low]),"minimum_step":rows[low]["step"]}
        out[name]=metrics
    out["minimum_static_gravity_wrench_in_weights"]=min(r["static_6d_weights"] for r in rows)
    out["bilateral_positive_steps"]=sum(all(p["positive_points"]>0 for p in r["pads"]) for r in rows)
    out["step_count"]=len(rows)
    return out


def run(root, case):
    d=root/RAW/case
    replay=json.loads((d/"replay.json").read_bytes())
    path=d/"transport-contact-manifolds.json.gz"
    if sha(path)!=replay["archive_sha256"]:
        raise ValueError("changed original contact readback")
    samples=json.loads(gzip.decompress(path.read_bytes()))["rows"]
    rows=[]
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore",category=OptimizeWarning,message="Unrecognized options detected.*")
        for step,com,_,_,_,_,ids,contacts in samples:
            pads=[photograph(contacts,j,replay["pad_half_extents_m"][j]) for j in (0,1)]
            rows.append({"step":step,"exposures":ids,"pads":pads,
                         "net_force_world_N":np.sum([p["force_world_N"] for p in pads],axis=0).tolist(),
                         "net_moment_about_object_com_Nm":np.sum([p["moment_about_object_com_Nm"] for p in pads],axis=0).tolist(),
                         "static_6d_weights":equilibrium(contacts,np.array(com),replay["body_mass_kg"],replay["gravity_m_s2"])})
    at=replay["trigger_step"]
    trigger=next(r for r in rows if r["step"]==at)
    file=d/"transport-contact-wrenches.json.gz"
    with file.open("xb") as f:
        f.write(gzip.compress(json.dumps(rows,allow_nan=False).encode(),3,mtime=0))
    results={
        "case":case,"replay_sha256":sha(d/"replay.json"),"wrenches_sha256":sha(file),
        "source_sha256":sha(Path(__file__)),"trigger":trigger,"transport":extremes(rows,at),
        "before_trigger":extremes([r for r in rows if r["step"]<at],at),
        "after_trigger":extremes([r for r in rows if r["step"]>at],at),
        "adjacent_eight_physics_ticks":[r for r in rows if at-8<=r["step"]<=at+8],
        "scope":"Mechanical truth only. Native force and moment are measured from MuJoCo impulses with sign on the object and all contact torques. Static support LP uses two opposed physical patches, current native per-point normal force ceilings, sliding friction capped at 0.8, four inner cone generators, zero torsion credit and equilibrium about actual mass center. A static weight factor does not bound camera-time preload, dynamic stopping or unseen placements. Polygon area is the convex hull of actual positive contact support points in each pad X-Z plane.",
    }
    with (d/"wrench-summary.json").open("x") as f:
        json.dump(results,f,indent=2,sort_keys=True,allow_nan=False)
        f.write("\n")
    print(case,at,[(p["positive_points"],p["normal_N"],p["actual_loaded_patch_area_m2"]) for p in trigger["pads"]],trigger["static_6d_weights"],flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",required=True,type=Path)
    ap.add_argument("--case",required=True,choices=FITS)
    x=ap.parse_args()
    run(x.root.resolve(), x.case)
