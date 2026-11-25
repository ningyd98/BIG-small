"""Offline oracle comparison for the five archived brake branches that really struck a bracket."""

import gzip
import json
from pathlib import Path

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_complete_cv_clearance import LocalClearance
from scripts.graduation.g1_complete_cv_geometry import Model, box_gap
from scripts.graduation.g1_complete_cv_motion import MotionGeometry, upper_support
from scripts.graduation.g1_complete_cv_support_domain import descending, state_rows


def run(private):
    geometry=json.loads(gzip.decompress((private/"mount-optics-02/capture-gpu/compiled.json.gz").read_bytes()))["geometry"]
    cal=private/"calibration-gpu-01"
    ref=LocalClearance(geometry,geometry["asset_path"],cal,calibration_sha256=digest(cal/"manifest.json"),isolated_scene=True)
    base=private/"mount-historic-brake-01/braking";result=[]
    for mm,label in ((115,"train-radial15-timing-01"),(130,"train-radial30-contact-d02-02")):
        asset=Path("assets/robots/franka_panda")/f"scene_g1_development_dual_id7_y{mm}_id8_x{mm}_low_bracket_v3.xml"
        source=base/(label+"-original-stop.json.gz");archive=base/(label+"-original-continuous.npz")
        stored=json.loads(gzip.decompress(source.read_bytes()))
        motion=MotionGeometry(Model(asset))
        with np.load(archive) as z:
            for row in stored:
                if not row["forbidden_contacts"]:continue
                step=row["step"];idx=z["step"].tolist().index(step)
                q=z["qpos"][idx,0];dq=z["qvel"][idx,0];c=z["cube_m"][idx,0];rot=z["cube_matrix"][idx,0]
                first,pairs=row["forbidden_contacts"][0]
                carrier,finger=pairs[0];i,j=motion.names.index(finger),motion.names.index(carrier)
                tcp,wrist,_=motion.model.forward(q[:7])
                hand=motion.model.hand_at(tcp,wrist,q[7:9])[i-motion.hand_start]
                target=motion.model.object[j-motion.load_start].placed(c,rot)
                # Inspect the generous ideal observation with no optical error.
                v=state_rows(motion,q[None,:7],q[None,7:9],dq[None,:7],dq[None,7:9],c[None])[0,-3:]
                pad=ref.descent_support if descending(v,ref.descent_vrange) else ref.support_phases["APPROACH"]
                zeros=np.zeros((len(motion.names),3));_,points=motion.envelopes(q[:7],q[7:9],dq[:7],dq[7:9],c,rot,
                    "APPROACH",dict(normal=zeros,stop=zeros),with_vertices=True)
                live=np.vstack((hand.r.T,rot.T,np.cross(hand.r.T[:,None,:],rot.T).reshape(-1,3)))
                length=np.linalg.norm(live,axis=1);live=live[length>1e-8]/length[length>1e-8,None]
                axes=np.vstack((ref.axes,live,-live));faces,weight=ref.directions.mix(axes);opp=ref.opposite[faces]
                def limit(part,dirs,ids):
                    return upper_support(points[:,part],dirs,(pad[part,ids]*weight).sum(1),
                                         (ref.half_tick["APPROACH"][part,ids]*weight).sum(1))
                gap=(-limit(j,-axes,opp)-limit(i,axes,faces)).max()
                result.append(dict(mount_mm=mm,source_step=step,actual_first_forbidden_stop_tick=first,
                    actual_pair=pairs[0],current_gap_m=box_gap(hand,target),swept_gap_m=float(gap),
                    telemetry_sha256=digest(archive),contacts_sha256=digest(source),model_sha256=digest(asset)))
    return result


if __name__=="__main__":
    import sys
    write(Path(sys.argv[1]),run(Path("experiments/results/g1-complete-cv-repair-20261125")))
