"""Fit the printed ID8 and observed red block on their measured common plane in the current image."""
import argparse
import base64
import ctypes
import gzip
import hashlib
import itertools
import json
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
BASE=Path('experiments/results/g1-continuous-payload-observation-20261125')
ASSET=Path('assets/robots/franka_panda/scene_g1_development_dual_id7_minusx130_id8_plusx130_end_wings_v1.xml')
OUT=BASE/'red-ink-fit-01'
SAMPLES=np.array([[.375,.875],[.875,.625],[.125,.375],[.625,.125]])-.5
GRID=np.array([(np.deg2rad(a),x/1000,y/1000) for a,x,y in itertools.product(np.arange(-3,3.001,.2),np.arange(-1.5,1.501,.5),np.arange(-1.5,1.501,.5))])
DLL=ctypes.CDLL(str((OUT/'grid.so').resolve()))
arr=np.ctypeslib.ndpointer(flags='C_CONTIGUOUS')
DLL.grid.argtypes=[ctypes.c_int,arr,arr,arr,ctypes.c_int,arr,ctypes.c_int,arr,arr]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
xml=ET.parse(ASSET)
BITS=np.array([float(xml.find(f'.//geom[@name="g1_dual_id8_r{r}c{c}"]').get('rgba').split()[0])>.5 for r in range(6) for c in range(6)],dtype=np.int32)

def metric(frame,pose):
    a=np.asarray(pose['anchor_world_m']); r=np.asarray(pose['rotation'])
    c=np.asarray(pose['center_m']); normal=r[:,2]
    t=np.array(frame['camera_to_world']).reshape(4,4);eye=t[:3,3]; rot=t[:3,:3]
    fx,fy,cx,cy=frame['intrinsics']
    h,w=frame['height'],frame['width']
    z=np.frombuffer(base64.b64decode(frame['depth_float32_base64']),'<f4').reshape(h,w)
    rgb=cv2.imdecode(np.frombuffer(base64.b64decode(frame['rgb_png_base64']),np.uint8),1)[:,:,::-1].astype(float)
    def image(p):
        q=(p-eye)@rot
        return np.array([cx+fx*q[0]/q[2],cy+fy*q[1]/q[2]])
    def rays(uv):
        return (np.concatenate(((uv-[cx,cy])/[fx,fy],np.ones((*uv.shape[:-1],1))),axis=-1)@rot.T)
    def region(center):
        u,v=np.rint(image(center)).astype(int)
        yy,xx=np.mgrid[max(0,v-17):min(h,v+18),max(0,u-17):min(w,u+18)]
        return np.stack((xx,yy),-1).reshape(-1,2)
    def project(uv):
        ray=rays(uv);s=((a-eye)@normal)/(ray@normal)
        return ((eye+s[...,None]*ray-a)@r)[...,:2],s
    uv=region(a)
    xy,expected=project(uv)
    px,py=uv.T
    rgbp=rgb[py,px]
    ok=(np.abs(xy).max(axis=1)<.043)&(np.abs(z[py,px]-expected)<.004)&(np.ptp(rgbp,axis=1)<40)
    if ok.sum()<110:return None
    vals=rgbp[ok].mean(axis=1);black,white=np.percentile(vals,[12,85])
    if white-black<60:return None
    intensity=np.ascontiguousarray(np.clip((vals-black)/(white-black),0,1))
    optical,_=project(uv[ok,None,:]+SAMPLES[None,:,:]); optical=np.ascontiguousarray(optical)
    red_uv=region(c+r[:,2]*.035)
    red_xy,red_z=project(red_uv);px,py=red_uv.T
    rr,gg,bb=rgb[py,px].T
    use=(rr>1.25*gg+7)&(rr>1.25*bb+7)&(np.abs(z[py,px]-red_z)<.004)&(np.abs(red_xy+[.13,0]).max(axis=1)<.043)
    red=np.ascontiguousarray(red_xy[use]);n=len(red)
    if n<12 or np.ptp(red,axis=0).max()<.053:return None
    scores=np.empty((len(GRID),3));DLL.grid(len(intensity),optical,intensity,BITS,n,red,len(GRID),GRID,scores)
    # Permit a finite half-pixel footprint (a square, conservatively projected to the plane).
    red_allow=0.5*np.hypot(1/fx,1/fy)*np.max(red_z)/abs(normal@rot[:,2])+.00005
    supported=(scores[:,1]<=red_allow)&(scores[:,0]<=.16)
    if not supported.any():return None
    best=np.min(scores[supported,0]);ids=np.where(supported&(scores[:,0]<=best+.001))[0]
    choice=ids[np.argmin(np.linalg.norm((GRID[ids]-np.median(GRID[ids],axis=0))/[np.deg2rad(.2),.0005,.0005],axis=1))]
    def make(k):
        theta,dx,dy=GRID[k];co,si=np.cos(theta),np.sin(theta)
        rn=r@np.array([[co,-si,0],[si,co,0],[0,0,1]])
        an=a+r[:,:2]@[dx,dy]
        return an-rn@pose['anchor_object_m'],rn,an
    centers=np.stack([make(i)[0] for i in ids]);center,orient,anchor=make(choice)
    return dict(center=center.tolist(),rotation=orient.tolist(),anchor=anchor.tolist(),eligible=len(ids),
        red_pixels=n,gray_pixels=len(intensity),best_mae=best,nominal_mae=scores[len(GRID)//2,0],
        delta_deg=np.rad2deg(GRID[choice,0]),delta_xy_mm=(1000*GRID[choice,1:]).tolist(),
        competing_angle_range_deg=np.rad2deg(np.ptp(GRID[ids,0])),
        competing_center_span_m=np.ptp(centers,axis=0).tolist(),hit_search_boundary=bool(np.any(abs(GRID[ids,0])>np.deg2rad(2.99)) or np.any(abs(GRID[ids,1:])>.00149)))
    
def main(name):
    assert name in ('dense-fit-01','dense-fit-02','dense-fit-03')
    folder=BASE/'physical-03'/name; native=BASE/(name+'-prediction-01.json')
    dr=json.loads(native.read_bytes());index=json.loads((folder/'rgbd-index.json').read_bytes())
    rec=json.loads((folder/'sensor-receipt.json').read_bytes())
    assert rec['index_sha256']==sha(folder/'rgbd-index.json') and rec['asset_sha256']==sha(ASSET) and rec['role']=='fit'
    rows=[]
    for source,old in zip(index['rows'],dr['records'],strict=True):
        pose=old['result']['pose']
        if not pose or pose['method']!='id8_and_red_top':continue
        path=folder/source['file'];assert sha(path)==source['file_sha256']
        fr=json.loads(gzip.decompress(path.read_bytes()))
        assert fr['checksum_sha256']==old['checksum_sha256']==pose['checksum_sha256'] and fr['frame_id']==old['frame_id']==pose['frame_id']
        start=time.perf_counter(); pred=metric(fr,pose)
        rows.append(dict(frame_id=fr['frame_id'],checksum=fr['checksum_sha256'],step=old['step'],skill=old['skill'],pred=pred,
                         elapsed_ms=(time.perf_counter()-start)*1000))
    out=OUT/(name+'.json')
    out.open('x').write(json.dumps(dict(id=name,native_source_sha256=sha(native),index_sha256=rec['index_sha256'],rows=rows,
        source_sha256=sha(Path(__file__)),cpp_sha256=sha(HERE/'red-ink-grid.cpp'),library_sha256=sha(OUT/'grid.so'),asset_sha256=sha(ASSET),
        declared_interval=None,control_admission=False,physics_labels_read=False),sort_keys=True,allow_nan=False)+'\n')
    print(name,len(rows),sha(out))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');main(ap.parse_args().case)
