"""Isolated retained-pose and paired physical pin exposures after the optical prediction was sealed."""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path

import mujoco
import numpy as np
from OpenGL import GL

from scripts.graduation.g1_complete_cv_calibrate import digest,write
from scripts.graduation.g1_complete_cv_carried_surface import CarriedSurface
from scripts.graduation.g1_visibility_trials import device


def main(out):
    rd=Path(__file__).resolve().parent
    prior=rd/"independent-projection-before-label.public.json"
    spec=importlib.util.spec_from_file_location("surface_source",rd/"surface-failure.py")
    source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
    frame,pose,r,a,it=source.load()
    data=source.BASE/"batches/train-full-04/cvfix-t02/instance/offline-truth.json"
    true=json.loads(data.read_bytes())["samples"]
    tf=np.asarray(frame.camera_to_world).reshape(4,4);fx,fy,cx,cy=frame.intrinsics
    ray=np.asarray([(171-cx)/fx,(122-cy)/fy,1.])@tf[:3,:3].T
    # These fixture poses and neutral/painted pins are for the diagnostic source alone.
    # The deployed projector reads no physical-state labels or fixture pose.
    obs=1.333837866783142;rows=[]
    out.mkdir(parents=True,exist_ok=False)
    for label,advance,radius,color in (
        ("no-pin",0.,0.,None),("pin-black-80",.080,.0018,"0.01 0.01 0.01 1"),
        ("pin-red-40",.040,.0018,"0.75 0.22 0.16 1"),
        ("pin-black-20",.020,.0018,"0.01 0.01 0.01 1"),
        ("pin-coplanar-ambiguous",.002,.0018,"0.1 0.04 0.04 1"),
        ("broader-object",.050,.007,"0.1 0.7 0.8 1")):
        centre=tf[:3,3]+ray*(obs-advance);bottom=centre[2]-.008
        extra=None if color is None else (f'<geom name="paired_intrusion" type="box" pos="{centre[0]:.10f} {centre[1]:.10f} {bottom:.10f}" '
            f'size="{radius} {radius} .008" rgba="{color}" contype="1" conaffinity="3" mass=".006" />')
        with device(Path("experiments/results/g1-visibility-pose-repair-20261124")):
            ref=CarriedSurface(a["geometry"]["asset_path"],additional_physical_fixture=extra)
            try:
                for t in ((2111,2112) if color is None else (2112,)):
                    live=true[t]
                    rgb,depth=ref.project(live["object_geom_position_m"],np.asarray(live["object_geom_rotation_row_major"]).reshape(3,3),
                          r["robot"]["camera_joint_positions_rad"],r["robot"]["camera_finger_positions_m"])
                    ref.renderer.disable_depth_rendering();ref.renderer.enable_segmentation_rendering()
                    labels=ref.renderer.render().copy();ref.renderer.disable_segmentation_rendering()
                    ident=int(labels[122,171,0]);kind=ref.model.geom(ident).name if ident>=0 else "background"
                    outfile=out/f"{label}-{t:04}.npz";np.savez_compressed(outfile,rgb=rgb,depth=depth)
                    rows.append(dict(case=label,archived_object_physics_step=t,paired_npz_sha256=digest(outfile),
                         original_single_uv_rgb=rgb[122,171].tolist(),original_single_uv_depth=float(depth[122,171]),
                         offline_only_segmentation_front_geom=kind,radius_m=radius,advance_m=advance,
                         noise_free_depth_neighborhood=depth[120:125,169:174].tolist(),
                         registered_camera=GL.glGetString(GL.GL_RENDERER).decode()))
            finally:ref.close()
    write(rd/"paired-original-pins.public.json",dict(original_truth_sha256=digest(data),optical_prediction_before_labels_sha256=digest(prior),cases=rows))


if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("out",type=Path);main(a.parse_args().out)

