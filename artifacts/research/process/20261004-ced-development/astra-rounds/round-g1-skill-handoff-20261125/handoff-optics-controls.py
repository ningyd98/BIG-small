"""Real foreign-marker and occlusion records, plus missing-depth/identity transport controls."""
import argparse
import base64
import gzip
import importlib.util
import json
from pathlib import Path

import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from scripts.graduation.g1_complete_cv_calibrate import digest,write
from scripts.graduation.g1_complete_cv_handoff_optics import rigid_pose


def run(rd,base,out):
    module=importlib.util.spec_from_file_location("raw_optics",rd/"handoff-optics-readback.py")
    scorer=importlib.util.module_from_spec(module);module.loader.exec_module(scorer)
    decode=scorer.detector()
    geometry=json.loads(gzip.decompress((base/"mount-optics-02/capture-gpu/compiled.json.gz").read_bytes()))["geometry"]
    report=[]
    def test(name,frame,expected_file,marker=None):
        mark=decode(frame,geometry) if marker is None else marker
        data=rigid_pose(frame,mark,geometry)
        report.append(dict(case=name,source_sha256=expected_file,observed=mark.get("observed_ids"),
          reason=mark.get("reason"),supplies_pose=data is not None))
    def read(p):return RGBDObservation.model_validate_json(gzip.decompress(p.read_bytes()))
    for k in ("foreign-in-seven","foreign-in-eight"):
        file=base/"target-visibility/qualification-gpu-02"/k/"reset.rgbd.json.gz"
        test(k,read(file),digest(file))
    for k in ("shifted-small-foreign","shifted-large-foreign"):
        file=base/"target-visibility/scale-gpu-01"/k/"reset.rgbd.json.gz"
        test(k,read(file),digest(file))
    capture=base/"handoff-rigid-verify-01"
    cases=json.loads((base/"handoff-rigid-verify-score-01.json").read_bytes())
    row=next(d for d in cases if d.get("method")=="id8")
    file=capture/(row["curve"]+"-"+str(row["step"]).zfill(5)+".rgbd.json.gz")
    test("real_single_code_without_opposite",read(file),digest(file))
    row=next(d for d in cases if d.get("method")=="both")
    file=capture/(row["curve"]+"-"+str(row["step"]).zfill(5)+".rgbd.json.gz")
    good=read(file);mark=decode(good,geometry)
    assert rigid_pose(good,mark,geometry) is not None
    for name,changed in (("cross_frame_id",dict(frame_id="unmatched")),("cross_checksum",dict(checksum="0"*64)),("wrong_asset",dict(asset_sha256="0"*64)),("foreign_rig",dict(registration_id="wrong"))):
        test(name,good,digest(file),dict(mark,**changed))
    uv=np.asarray(mark["by_id"]["8"]["ordered_corners_px"]).mean(axis=0).round().astype(int)
    pixels=np.frombuffer(base64.b64decode(good.depth_float32_base64),"<f4").copy().reshape(good.height,good.width)
    pixels[uv[1],uv[0]]=0.
    modified=dict(good.model_dump(),depth_float32_base64=base64.b64encode(pixels.tobytes()).decode(),valid_mask_base64=None,checksum_sha256="")
    frame=RGBDObservation.model_validate(modified)
    test("missing_current_depth_at_mark_center",frame,digest(file))
    if any(r["supplies_pose"] for r in report):raise ValueError("negative released")
    write(out,dict(controls=report,all_rejected=len(report),reader_sha256=digest(Path("scripts/graduation/g1_complete_cv_handoff_optics.py"))))


if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__)
    for k in ("rd","base","out"):a.add_argument(k,type=Path)
    v=a.parse_args();run(v.rd,v.base,v.out)

