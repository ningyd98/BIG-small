"""Render the 31 registered anchors once under one EGL lease, preserving every RGB-D input."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import static_screen as sc

old, np, cv2, mujoco = sc.old, sc.np, sc.cv2, sc.mujoco
write, read, sha, require = sc.write,sc.read,sc.sha,sc.require


def frozen_detector():
    modules={}
    for name in ("g1_visibility_grid","g1_visibility_vision"):
        path=sc.PHYSICAL/"scripts/graduation"/(name+".py")
        import_name="scripts.graduation."+name
        spec=importlib.util.spec_from_file_location(import_name,path)
        mod=importlib.util.module_from_spec(spec)
        sys.modules[import_name]=mod
        spec.loader.exec_module(mod)
        modules[name]=mod
    require(modules["g1_visibility_vision"].find_grids is modules["g1_visibility_grid"].find_grids,
            "sensor imported a grid outside frozen runtime")
    return modules["g1_visibility_vision"].measure_frame,{str(Path(m.__file__).relative_to(sc.ROOT)):sha(Path(m.__file__)) for m in modules.values()}


def sensor(reader,private,key,f,g,state,both):
    m=reader(f,g)
    require(m["registration_id"]==g["registration_id"] and m["asset_sha256"]==g["pose_marker"]["marked_asset_sha256"] and
            m["frame_id"]==f.frame_id and m["checksum"]==f.checksum_sha256,"wrong mount or acquisition")
    points={str(i):old.reference.independent_pose(g,i,m["by_id"][str(i)]) for i in m["usable_ids"]}
    t=old.reference.truth_errors(g,state,{**m,"per_id":points})
    if len(points)==2:
        distance=sc.math.dist(points["7"]["tcp_m"],points["8"]["tcp_m"])
        require(abs(distance-m["target_disagreement_m"])<=1e-10 and (distance<=.010 or not m["usable"]),"invalid dual conflict result")
    p=private/(key+".json")
    write(p,f.model_dump(mode="json"))
    return {"packet_file":p.name,"packet_sha256":sha(p),"frame_checksum":f.checksum_sha256,"calibration":f.calibration_version,
            "registered_geometry":g["registration_id"],"asset_sha256":m["asset_sha256"],"measurement":m,"independent_pose":points,
            "truth":t,"requires_both_codes":both,"qualified":old.visual_qualified(m,t,both)}


def physical_context(camera,model,data,ref,state,geometry):
    residual=old.restore(model,data,state)
    h=camera._physics_state_hash(data)
    rendered=old.optical.render(camera,model,data,ref,(),h)
    require(data.time==ref.sim_time_s and h==camera._physics_state_hash(data),"render affected physical pose")
    return rendered,h,residual


def checks(reader,private,frame,g,clean):
    rgb,depth,mask=old.reference.unpack(frame)
    sides={c["id"]:np.array(c["ordered_corners_px"]) for c in clean["measurement"]["candidates"]}
    require(set(sides)=={7,8},"positive control requires two actual prints")
    boxes={}
    for code,coords in sides.items():
        x,y=np.floor(coords.min(axis=0)).astype(int)-3
        xx,yy=np.ceil(coords.max(axis=0)).astype(int)+4
        boxes[code]=(slice(y,yy),slice(x,xx))
    seeds={}
    for keep,hide in ((7,8),(8,7)):
        c,z,k=(a.copy() for a in (rgb,depth,mask))
        chip=boxes[hide];c[chip]=95;z[chip]=0;k[chip]=0
        seeds["only-"+str(keep)]=(old.reference.intervention(frame,12000+keep,c,z,k),[keep],"")
    seeds["fully-occluded"]=(old.reference.intervention(frame,12020,np.full_like(rgb,95),np.zeros_like(depth),np.zeros_like(mask)),[],None)
    chip=boxes[8];dx=39
    dest=(chip[0],slice(chip[1].start+dx,chip[1].stop+dx));require(dest[1].stop<=frame.width and chip[1].stop<=dest[1].start,
                                                                       "registered movement exceeds image")
    switched=[a.copy() for a in (rgb,depth,mask)]
    for before,after in zip((rgb,depth,mask),switched,strict=True):
        after[chip],after[dest]=before[dest],before[chip]
        require(np.array_equal(after[dest],before[chip]) and np.array_equal(after[chip],before[dest]),"chip movement distorted")
    seeds["two-valid-targets-over-10mm"]=(old.reference.intervention(frame,12030,*switched),[7,8],"dual_marker_grasp_conflict")
    result={}
    for name,(f,ids,reason) in seeds.items():
        m=reader(f,g)
        if name.startswith("only"):
            ok=m["observed_ids"]==m["usable_ids"]==ids and m["usable"] and m["selected_id"]==ids[0]
        elif name=="fully-occluded":
            ok=(m["usable_ids"]==[] and not m["usable"] and m["grasp_world_m"] is None)
        else:
            ok=(m["observed_ids"]==m["usable_ids"]==[7,8] and m["reason"]==reason and m["target_disagreement_m"]>.01
                and not m["usable"] and m["selected_id"] is None and m["grasp_world_m"] is None)
        p=private/(name+".json")
        write(p,f.model_dump(mode="json"))
        result[name]={"pass":ok,"packet_file":p.name,"packet_sha256":sha(p),"measurement":m}
    for name in ("old-115-registration","old-100-transform","swapped-ID7-ID8"):
        bad=sc.deepcopy(g)
        if name=="old-115-registration":bad["registration_id"]=sc.radial.details(15)["registration_id"]
        if name=="old-100-transform":bad["development_dual"]["markers"]["8"]["object_T_marker"][3]=.100
        if name=="swapped-ID7-ID8":bad["development_dual"]["markers"]["7"]["marker_id"]=8
        try:
            sc.check_registration(bad,30)
        except ValueError as e:
            result[name]={"pass":True,"registered_error":str(e)}
        else:
            result[name]={"pass":False,"registered_error":None}
    return result


def run(work):
    cases,anchors=sc.collect()
    regs=sc.registrations()
    for offset,g in regs.items():sc.check_registration(g,offset)
    read_frame,detector=frozen_detector()
    require(sc.os.environ.get("MUJOCO_GL")=="egl","EGL required")
    private=work/"optical-packets"
    private.mkdir()
    rows=[];controls=None
    with sc.ExitStack() as stack:
        lock=stack.enter_context((sc.BASE/"egl.lock").open("rb"));sc.fcntl.flock(lock,sc.fcntl.LOCK_EX)
        pool={}
        for name,role,record,both in anchors:
            case=cases[name]
            g=case["geometry"]
            frame=old.frame_from_row(case["folder"]/"instance",record,case["index"]["episode"],case["index"]["scene"],g)
            raw=old.cam.depth(frame);step=record["physics_step"];state=case["states"][step];base=f"{name}-{role}-{step}"
            m,d,c=old.cameras_for(stack,pool,g)
            src,old_state,residual=physical_context(c,m,d,frame,state,g)
            output={"case":name,"role":role,"step":step,"source_file":record["file"],"source_file_sha256":record["file_sha256"],
                    "frame_id":frame.frame_id,"source_truth_sha256":case["truth_sha256"],"source_asset":case["asset_sha256"],
                    "source_state_sha256":old_state,"source_restore":residual,
                    "original_camera":frame.model_dump(mode="json",include=set(g["camera"])),
                    "original_rgb_pixel_mismatches_vs_rerender":int(np.any(old.cam.rgb(frame)!=src["rgb"],axis=2).sum()),
                    "source_native":sensor(read_frame,private,base+"-original",frame,g,state,both)}
            for off in (15,30):
                geometry=regs[off];sc.check_registration(geometry,off)
                if geometry["asset_path"]==g["asset_path"]:
                    rendered,render_state,render_residual=src,old_state,residual
                else:
                    m,d,c=old.cameras_for(stack,pool,geometry)
                    rendered,render_state,render_residual=physical_context(c,m,d,frame,state,geometry)
                pair=old.optical.paired_depth(raw,src["depth"],rendered["depth"])
                output[str(off)]={"state_sha256":render_state,"restoration":render_residual}
                for mode,dp in (("clean",rendered["depth"]),("matched",pair)):
                    f=old.optical.packet(frame,rendered["rgb"],dp,base+"-"+str(off)+"-"+mode)
                    outcome=sensor(read_frame,private,base+"-"+str(off)+"-"+mode,f,geometry,state,both)
                    output[str(off)][mode]=outcome
                    if off==30 and mode=="clean" and controls is None and outcome["measurement"]["usable_ids"]==[7,8]:
                        controls=checks(read_frame,private,f,geometry,outcome)
            rows.append(output)
    require(controls is not None and len(rows)==31,"missing independent optical controls/anchors")
    bad=[{"case":v["case"],"role":v["role"],"step":v["step"],"clean":v["30"]["clean"]["measurement"]["reason"],
          "matched":v["30"]["matched"]["measurement"]["reason"]} for v in rows
          if not all(v["30"][k]["qualified"] for k in ("clean","matched"))]
    metrics={}
    for off in ("15","30"):
        metrics[off]={}
        for mode in ("clean","matched"):
            observations=[v[off][mode] for v in rows]
            err=[p["top_error_mm"] for v in observations for p in v["truth"]["per_id"].values()]
            tcp=[p["tcp_error_mm"] for v in observations for p in v["truth"]["per_id"].values()]
            ds=[r["measurement"]["target_disagreement_m"]*1000 for r in observations if r["measurement"]["target_disagreement_m"] is not None]
            metrics[off][mode]={"qualified":sum(r["qualified"] for r in observations),"registered_top_max_mm":max(err),
                               "registered_tcp_max_mm":max(tcp),"max_dual_target_disagreement_mm":max(ds)}
    data=work/"screen-optical-frames.json.gz"
    write(data,{"schema":"g1.visibility.radial30-optical-details.v1","plan_sha256":sc.PLAN,"anchors":rows,"controls":controls})
    result={"schema":"g1.visibility.radial30-optical-screen.v1","plan_sha256":sc.PLAN,"parent_generation":sc.PARENT,
            "candidate_asset_sha256":regs[30]["pose_marker"]["marked_asset_sha256"],"optical_anchors":31,"matched_depth_inputs":31,
            "zero_integrations":True,"camera":"f33940579c533afe","detector_files_sha256":detector,"details_sha256":sha(data),
            "measurements":metrics,"failures":bad,"control_results":{k:v["pass"] for k,v in controls.items()},
            "negative_controls_pass":all(v["pass"] for v in controls.values()),"eligible":not bad and all(v["pass"] for v in controls.values())}
    write(work/"screen-optical-summary.json",result)
    print(result["eligible"],result["failures"],result["control_results"],result["measurements"],flush=True)


if __name__=="__main__":run(Path(sys.argv[1]))

