"""Counterfactual same-ray tip against an independently obtained noise-free ordinary exposure."""
import argparse
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
from scripts.graduation.g1_complete_cv_calibrate import digest, write
from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
from scripts.graduation.g1_visibility_trials import device

def main(out):
    here=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location("before_control",here/"surface-failure.py")
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    frame,pose,rr,allocation,entry=source.load()
    out.mkdir(parents=True,exist_ok=False)
    root=ET.parse(source.BASE/"carried-surface-materials-01/pin-3.xml")
    data=json.loads((source.BASE/"batches/train-full-04/cvfix-t02/instance/offline-truth.json").read_bytes())["samples"][2112]
    centre=data["object_geom_position_m"];r=np.asarray(data["object_geom_rotation_row_major"]).reshape(3,3)
    args=(centre,r,rr["robot"]["camera_joint_positions_rad"],rr["robot"]["camera_finger_positions_m"])
    clean=np.load(source.BASE/"carried-surface-paired-01/no-pin-2112.npz")
    pin=root.find("./worldbody/geom[@name='diagnostic_pin']")
    tf=np.asarray(frame.camera_to_world).reshape(4,4);fx,fy,cx,cy=frame.intrinsics
    ray=np.asarray([(171-cx)/fx,(122-cy)/fy,1.])@tf[:3,:3].T
    true_z=float(clean["depth"][122,171])
    point=tf[:3,3]+ray*(true_z-.000005)
    pin.set("pos"," ".join(str(t) for t in (point-np.array([0,0,.008]))))
    xml=out/"physical-alias.xml";root.write(xml)
    rows=[]
    with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
        ref=CarriedSurface(xml)
        try:
            mat=ref.model.material("diagnostic_reflective_tip").id
            for emission in (.34,.35,.36,.37,.38,.39,.4):
                for green in (.9,.92,.94,.96, .98,1.):
                    ref.model.mat_emission[mat]=emission
                    ref.model.mat_rgba[mat]=[1.,green,green,1.]
                    rgb,z=ref.project(*args)
                    err=abs(clean["rgb"].astype(int)-rgb.astype(int))
                    rows.append(dict(emission=emission,green=green,color=rgb[122,171].tolist(),peak=int(err.max()),
                                    changed_pixels=int(np.any(err>0,axis=2).sum()),z=float(z[122,171])))
            best=min(rows,key=lambda x:(x["peak"],x["changed_pixels"]))
            ref.model.mat_emission[mat]=best["emission"];ref.model.mat_rgba[mat]=[1.,best["green"],best["green"],1.]
            rgb,z=ref.project(*args);datafile=out/"physical-alias.npz";np.savez_compressed(datafile,rgb=rgb,depth=z)
        finally:ref.close()
    write(here/"single-ray-alias.public.json",dict(best=best,measured_native_clean_z_m=true_z,
        registered_sensor_noise_std_m=.001,sensor_rgb_max_abs_difference=best["peak"],
        measurable_depth_change_pixels=int(np.sum(z!=clean["depth"])),z_most_changed_m=float(abs(z-clean["depth"]).max()),
        genuine_physical_obstacle_sha256=digest(xml),outputs_sha256=digest(datafile),radiometric_grid=rows))

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("out",type=Path);main(a.parse_args().out)
