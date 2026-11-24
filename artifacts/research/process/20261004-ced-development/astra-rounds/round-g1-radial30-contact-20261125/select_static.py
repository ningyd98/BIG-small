"""Publish the independent zero-step decision with exact per-anchor and per-step inputs."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import static_screen as sc

ROOT, ROUND, check = sc.ROOT, sc.ROUND, sc.require
read,write,sha=sc.read,sc.write,sc.sha


def geometry_for_release(g):
    m=sc.old.checked_model(ROOT/g["asset_path"],g)
    original=sc.mujoco.MjModel.from_xml_path(str(ROOT/sc.radial.V2_PATH))
    faces=sc.radial.compiled_faces(m,30)
    spec=sc.radial.details(30)
    check(len(faces)==6 and min(faces.values())>0,"loose support faces")
    parts={}
    for code,axis in ((7,1),(8,0)):
        expected=sc.np.zeros(3);expected[axis]=.030
        for name in [f"g1_dual_id{code}_plate",f"g1_dual_id{code}_quiet",*(f"g1_dual_id{code}_r{a}c{b}" for a in range(6) for b in range(6))]:
            new=m.geom(name);old=original.geom(name)
            shift=new.pos-old.pos
            check(sc.np.allclose(shift,expected,rtol=0,atol=1e-12) and sc.np.array_equal(new.quat,old.quat) and
                  sc.np.array_equal(new.size,old.size) and sc.np.array_equal(new.rgba,old.rgba) and
                  sc.np.array_equal(new.conaffinity,old.conaffinity) and sc.np.array_equal(new.contype,old.contype),
                  "print, quiet region or plate changed beyond the radial translation")
            parts[name]={"local_translation_m":shift.tolist(),"size_m":new.size.tolist(),"quat_wxyz":new.quat.tolist(),
                         "contype":int(new.contype[0]),"conaffinity":int(new.conaffinity[0])}
    b=m.body("object")
    check(abs(float(b.mass[0])-spec["body_mass_kg"])<=1e-12,"runtime body mass mismatch")
    return {"registration_id":g["registration_id"],"asset_sha256":spec["asset_sha256"],"registered_marker_centers":spec["centers"],
            "compiled_mass_kg":float(b.mass[0]),"compiled_inertial_position_m":b.ipos.tolist(),
            "compiled_principal_inertia_kg_m2":b.inertia.tolist(),"compiled_inertial_quat":b.iquat.tolist(),
            "attached_faces_area_m2":faces,"registered_marker_transforms":g["development_dual"]["markers"],
            "translated_geometries":parts}


def run(work):
    plan=sc.pins()
    optical=read(work/"screen-optical-summary.json")
    dense=read(work/"screen-clearance-summary.json")
    check(optical["plan_sha256"]==dense["plan_sha256"]==sc.PLAN and optical["parent_generation"]==dense["parent_generation"]==sc.PARENT and
          optical["candidate_asset_sha256"]==dense["candidate_asset_sha256"]==plan["new_asset_sha256"] and
          optical["optical_anchors"]==optical["matched_depth_inputs"]==31 and dense["native_states"]==dense["dense_states"]==3432 and
          dense["all_sources_contact_multiplicity_exact"], "incomplete static screening")
    frames=read(work/"screen-optical-frames.json.gz",optical["details_sha256"])
    hw=geometry_for_release(sc.registrations()[30])
    source={};local={}
    def pin(path,digest=None):
        actual=sha(path)
        check(digest is None or digest==actual,"source changed: "+str(path))
        source[path.resolve().relative_to(ROOT).as_posix()]=actual
    def copy(old,new):
        with old.open("rb") as si,new.open("xb") as so:shutil.copyfileobj(si,so)
        pin(new,sha(old))
    for k,h in plan["inputs_sha256"].items():
        path=ROOT/k
        if k.startswith("scripts/graduation/") and (sc.PHYSICAL/k).is_file():path=sc.PHYSICAL/k
        if not path.resolve().is_relative_to(ROOT):
            check(sha(path)==h,"private source changed");local[str(path.resolve())]=h
        else:pin(path,h)
    for f in ("plan.md","plan.json","static_screen.py","optical_screen.py","select_static.py","test_static_screen.py"):
        pin(ROUND/f)
    for tag in ("native","candidate"):
        for name in sc.NAMES:
            filename="dense-"+tag+"-"+name+".json.gz";s=dense["trajectories"][tag][name]
            check(s["detail_sha256"]==sha(work/filename) and s["states"]==sc.NAMES[name],"dense details changed")
            copy(work/filename,ROUND/("screen-"+tag+"-"+name+".public.json.gz"))
    copy(work/"screen-optical-frames.json.gz",ROUND/"screen-optical-frames.public.json.gz")
    copy(work/"screen-optical-summary.json",ROUND/"screen-optical-summary.public.json")
    copy(work/"screen-clearance-summary.json",ROUND/"screen-clearance-summary.public.json")
    prevpath=sc.old.ROUND/"screen-optical-15.public.json.gz"
    prev=read(prevpath,plan["inputs_sha256"][prevpath.relative_to(ROOT).as_posix()])["frames"]
    current=frames["anchors"]
    full=[]
    for actual,expected in zip(current[:22],prev,strict=True):
        check(actual["frame_id"]==expected["frame_id"] and actual["source_file_sha256"]==expected["original_file_sha256"],
              "wrong original optical anchor")
        for mode,key in (("clean","candidate_clean"),("matched","candidate_matched_noise")):
            source_measure=expected[key]["measurement"]
            measured=actual["15"][mode]["measurement"]
            check(all(measured[n]==v for n,v in source_measure.items()),"115 mm optical reference no longer reproduced")
            full.append(actual["frame_id"]+" "+mode)
    history=read(sc.NEW/"instance/online-vision.json")["frames"]
    measured_feedback=[]
    for row in current[-9:]:
        if row["role"]!="contact_terminal":
            frame_id=row["frame_id"]
            check(row["source_native"]["measurement"]==history[frame_id]["measurement"],"native observation differs from archived consumer")
            measured_feedback.append(frame_id)
        else:
            check(row["step"]==1221 and row["frame_id"] not in history,"unexpected terminal consumer")
    originals={}
    locations={f.name:f for f in sc.old.ARCHIVE.joinpath("trials").iterdir()}
    locations.update(d01=sc.old.D01,d02=sc.old.D02,d02_radial15=sc.NEW)
    packets={}
    for row in current:
        origin=locations[row["case"]]/"instance"/row["source_file"]
        check(sha(origin)==row["source_file_sha256"],"changed unaltered RGB-D")
        if origin.resolve().is_relative_to(ROOT):pin(origin)
        else:local[str(origin.resolve())]=sha(origin)
        originals[row["frame_id"]]={"path":str(origin.resolve()),"sha256":sha(origin)}
        for readback in (row["source_native"],*(row[s][m] for s in ("15","30") for m in ("clean","matched"))):
            p=work/"optical-packets"/readback["packet_file"]
            check(sha(p)==readback["packet_sha256"],"changed static RGB-D bytes")
            packets[p.name]=sha(p)
    for control in frames["controls"].values():
        if "packet_file" in control:
            p=work/"optical-packets"/control["packet_file"];check(sha(p)==control["packet_sha256"],"control packet changed");packets[p.name]=sha(p)
    check(len(packets)==159 and len(originals)==31,"missing static packet")
    evidence=ROUND/"screen-local-raw-bindings.public.json"
    write(evidence,{"source_originals":originals,"additional_private_source_sha256":local,"counterfactual_packet_root":str((work/"optical-packets").resolve()),
                    "packet_files_sha256":packets,"frozen_115_published_measurements_reproduced":full,
                    "native_115_full_online_evidence_reproduced":measured_feedback,
                    "note":"Counterfactual rerendering uses identical archived joint/object pose. Original and modeled RGB-D stores remain distinct."})
    pin(evidence)
    geometry=ROUND/"screen-compiled-assembly.public.json"
    write(geometry,hw);pin(geometry)
    for k,v in optical["detector_files_sha256"].items():pin(ROOT/k,v)
    check(all(sha(ROOT/k)==v for k,v in source.items()),"underlying qualification artifact changed")
    ok=bool(optical["eligible"] and dense["eligible"] and optical["negative_controls_pass"])
    selected={"schema":"g1.visibility.radial30-screen-selection.v1","plan_sha256":sc.PLAN,"parent_generation":sc.PARENT,
              "candidate_offset_mm":30,"selected_offset_mm":30 if ok else None,"asset_sha256":plan["new_asset_sha256"],
              "registration_id":hw["registration_id"],"eligible":ok,"optical_anchors":31,"matched_depth_inputs":31,"dense_states":3432,
              "optical_pass":optical["eligible"],"clearance_pass":dense["eligible"],"negative_controls_pass":optical["negative_controls_pass"],
              "unauthorized_contact_steps":dense["unauthorized_contact_steps"],"unproved_separation_steps":dense["unproved_separation_steps"],
              "zero_integrations":True,"optical_summary_sha256":sha(ROUND/"screen-optical-summary.public.json"),
              "clearance_summary_sha256":sha(ROUND/"screen-clearance-summary.public.json"),
              "input_artifacts_sha256":source,"original_15_optical_matches":len(full),"new_native_online_matches":len(measured_feedback),
              "source_failures_reproduced":{"d01_native_1120":True,"new_d02_native_1221":True},
              "closest_mount_pair_by_trajectory":{name:s["closest_hand_or_finger_to_mount"] for name,s in dense["trajectories"]["candidate"].items()},
              "historical_job_runs":0,"new_formal_trials":0,"real_hardware_trials":0}
    path=ROUND/"screen-selection.public.json"
    write(path,selected)
    check(read(path)==selected,"published static selection differs")
    print(ok,sha(path),len(source),path,flush=True)


if __name__=="__main__":run(Path(sys.argv[1]))

