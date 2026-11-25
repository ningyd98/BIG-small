"""Reconstruct signed joint contributions, force transfer and target/physical lag at the peak."""
import argparse,gzip,hashlib,json
from pathlib import Path
import mujoco
import numpy as np


def run(root):
    base=root/'experiments/results/g1-skill-handoff-20261125/physical-capture-01';modelpath=root/'assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml';m=mujoco.MjModel.from_xml_path(str(modelpath));d=mujoco.MjData(m);site=m.site('tcp').id;nodes,weights=np.polynomial.legendre.leggauss(8);out={}
    def fk(q):
        d.qpos[:7]=q;mujoco.mj_kinematics(m,d);return d.site('tcp').xpos.copy()
    for p in sorted(base.iterdir()):
        hs=json.loads((p/'handoffs.json').read_bytes());h=next(x for x in hs if x['incoming']=='LIFT');start=h['start_step'];a=np.load(p/'normal.npz');steps=a['step'];mask=np.flatnonzero(a['stage']=='LIFT');force=a['force_N'];tcp=a['tcp'];q=a['q'];cmd=a['command_q'];counts=a['contacts'];cb=a['cube_bottom_m'];T0=fk(q[start,:7]);lateral=np.linalg.norm(tcp[mask,:2]-T0[:2],axis=1);t=int(mask[np.argmax(lateral)]);dv=q[t,:7]-q[start,:7];contrib=np.zeros((3,7));
        for v,w in zip(nodes,weights,strict=True):
            d.qpos[:7]=q[start,:7]+(.5+.5*v)*dv;mujoco.mj_kinematics(m,d);mujoco.mj_comPos(m,d);j=np.zeros((3,m.nv));mujoco.mj_jacSite(m,d,j,None,site);contrib+=w*.5*j[:,:7]*dv[None]
        x=fk(q[t,:7]);xc=fk(cmd[t]);total=x-T0;assert abs(contrib.sum(axis=1)-total).max()<1e-10
        mf=json.loads(gzip.decompress((p/'contact-manifolds.json.gz').read_bytes()));geoms=json.loads((p/'summary.json').read_bytes())['model_contact_geom_names'];oid=geoms.index('object_geom');tid=geoms.index('table');fs={geoms.index(n) for n in ('left_finger_geom','right_finger_geom')}
        def wrench_row(ii):
            result={'table':np.zeros(3),'fingers':np.zeros(3)}
            for ga,gb,dist,pos,frame,mu,f in mf[ii][1]:
                pair={ga,gb}
                if oid not in pair:continue
                key='table' if tid in pair else 'fingers' if pair.intersection(fs) else None
                if key:result[key]+=(1 if gb==oid else -1)*np.array(f[:3])@np.array(frame).reshape(3,3)
            return {k:v.tolist() for k,v in result.items()}
        first_free=next((int(j) for j in mask if counts[j,2]==0),None);first_gain=next((int(j) for j in mask if cb[j]-cb[start]>.00025),None)
        out[p.name]=dict(start=start,peak_step=t,ticks_into_lift=t-start,real_peak_lateral_m=lateral.max(),
             real_xyz_change_m=total.tolist(),world_moving_arm_target_equivalent_FK_xyz_change_m=(xc-T0).tolist(),
             actual_minus_target_equivalent_FK_xyz_m=(x-xc).tolist(),
             signed_world_XY_contribution_by_measured_joint_m=contrib[:2].T.tolist(),sum_of_joint_decomposition_error_m=float(abs(contrib.sum(axis=1)-total).max()),
             peak_sample_z_gain_m=float(cb[t]-cb[start]),first_zero_workpiece_table_contact=first_free,first_cube_gain_over_quarter_mm=first_gain,
             start_world_forces_N=wrench_row(start),peak_world_forces_N=wrench_row(t),current_arm_q_minus_target_rad=(q[t,:7]-cmd[t]).tolist(),
             gravity_feedforward_compensated_effective_ctrl_minus_target_rad=(a['ctrl'][t,:7]-cmd[t]).tolist(),prelift_max_measured_joint_speed_rad_s=float(abs(a['qvel'][start,:7]).max()),
             input_sha256=hashlib.sha256((p/'normal.npz').read_bytes()).hexdigest());
    return dict(cases=out,method='Forward-kinematic line integral of the native TCP Jacobian along measured joint displacement to its actual lateral peak. The joint-target FK is an equivalent diagnostic pose: the original actuator target includes rate-limited damping, gravity and disturbance compensation. Its difference from actual FK is reported separately; the true Cartesian reference keeps the entry XY fixed. Force vectors are expressed on the workpiece, measured by the native solver, including table contact. Failed traces end at the first overlimit sample.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args();rep=run(args.root.resolve());args.out.write_text(json.dumps(rep,indent=2,sort_keys=True)+'\n')
