"""Read real registered pixels and encoder geometry at each candidate's physical GRASP PRE."""
from __future__ import annotations
import argparse,fcntl,gzip,hashlib,json
from pathlib import Path
import cv2,mujoco,numpy as np
from OpenGL import GL
from cloud_edge_robot_arm.simulation.mujoco.camera import MuJoCoRGBDCamera
from cloud_edge_robot_arm.vision.observations import observation_from_sensor_frame
from scripts.graduation.g1_complete_cv_angle import grasp_readiness
from scripts.graduation.g1_formal_runtime import bind_scene
from scripts.graduation.g1_visibility_vision import measure_frame


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_bytes())

def run(root,out,groups):
    course=root/'experiments/results/g1-lift-corridor-20261125/candidate-calibration-01';prior=root/'experiments/results/g1-complete-cv-repair-20261125/batches/train-full-02/cvfix-t01/allocation.json';geom=read(prior)['geometry'];model=mujoco.MjModel.from_xml_path(str(root/geom['asset_path']));model.opt.timestep=1/240;data=mujoco.MjData(model);cam=MuJoCoRGBDCamera(mujoco,model,width=320,height=240);out.mkdir(parents=True,exist_ok=False);raw=[]
    try:
        for g in groups:
            for p in sorted((course/'courses').glob(g+'/*/result.json')):
                n=p.parents[1].name;a=read(p);k=a['candidate']['id'];
                if not n.startswith('fresh') and k not in ['r+0_t+0_h22','r+0_t-2_h20','r+0_t+2_h16','r+0_t+0_h20','r+4_t+0_h16','rad+0_h10']:continue
                if not any(v['stage']=='GRASP' for v in a['actions']):continue
                b=read(p.with_name('handoffs.json'));edge=next(x for x in b if x['stage']=='GRASP');st=edge['step'];d=p.parent;series=np.load(d/'series.npz');ii=st-int(series['step'][0]);qq=series['q'][ii];vv=series['qvel'][ii];data.qpos[:]=qq;data.qvel[:]=vv;data.ctrl[:]=series['ctrl'][ii];data.time=st/240;mujoco.mj_forward(model,data)
                scene='candidate-closure-'+n;tuples=[];rng=np.random.default_rng(9992+int.from_bytes(hashlib.sha256((n+k).encode()).digest()[:3],'big'))
                for noise in (0,1,2):
                    with bind_scene(scene):
                        f=observation_from_sensor_frame(cam.capture(data,rng=rng,noise_std_m=.001,scene_id=scene,episode_id=scene),source='mujoco_camera',png_compress_level=1);marker=measure_frame(f,geom)
                        if marker['usable']:
                            center=marker['object_center_world_m'];rot=np.array(marker['rotation_object_to_world']).reshape(3,3);tcp=data.site('tcp');angle,patch,ref=grasp_readiness(f,marker,geom,center,rot,tcp.xpos,tcp.xmat.reshape(3,3),qq[7:9],closure=True)
                        else:angle,patch,ref=None,None,marker['reason']
                    fname=out/(n+'-'+k+'-'+str(noise)+'.json.gz');fname.write_bytes(gzip.compress(f.model_dump_json().encode(),3,mtime=0));tuples.append(dict(frame=fname.name,sha256=sha(fname),ids=marker.get('usable_ids'),allowed=ref is None,reason=ref,angle=angle,patch=patch))
                raw.append(dict(case=n,candidate=k,source_result_sha256=sha(p),measured_closure_height_m=float(((data.site('tcp').xpos-data.geom('object_geom').xpos)@data.geom('object_geom').xmat.reshape(3,3))[2]),
                               nominal_mechanical_pass=a['eligible'],frozen_sources={f:sha(root/'scripts/graduation'/f) for f in ('g1_complete_cv_angle.py','g1_complete_cv_angle_domain.py')},captures=tuples))
        result=dict(renderer=GL.glGetString(GL.GL_RENDERER).decode(),geometry_sha256=sha(root/geom['asset_path']),method='Three independently noisy registered NVIDIA RGB-D captures at each untouched actual GRASP return; encoder-only TCP and fingers enter the existing optical angle / bilateral geometry gate, without changing its limits. Separate mechanical truth, screw contact torque and full action outcomes are used offline only.',courses=raw)
        (out/'index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n');print(len(raw),sum(all(q['allowed'] for q in r['captures']) for r in raw),flush=True)
    finally:cam.close()

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--group',action='append',required=True);p=a.parse_args();root=p.root.resolve();cv2.setNumThreads(1)
    with (root/'experiments/results/g1-visibility-pose-repair-20261124/egl.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);run(root,p.out.resolve(),p.group)
