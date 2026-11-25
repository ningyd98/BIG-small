"""Run the registered GuardedClockEpisode PRE against freshly acquired, zero-step RGB-D."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import shutil
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
PLAN="f6d83d5d1ba5fa88cbde31ac46a3e89e6c7c2edfa7b39013d403d3c2ce377fd2"
PRIVATE=Path("experiments/results/g1-cv-grasp-validation-20261125/binding-qualification")
OLD=PRIVATE/"run-01"
PLAN_REL=Path("artifacts/research/process/20261004-ced-development/astra-rounds/round-g1-cv-qualification-entry-20261125")
PARENT="e70951ea7032fbaa222dffd5e79830680973755856b217ab64d365159f33213f"
STIMULUS="synthetic candidate CLEAR for guarded zero-motion interface qualification"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False)+"\n")


def checked(path, digest):
    if sha(path)!=digest:
        raise ValueError("sealed input SHA mismatch: "+str(path))
    return json.loads(path.read_bytes())


def frozen_inputs(repo):
    plan=checked(repo/PLAN_REL/"plan.json",PLAN)
    for n,h in plan["input_sha256"].items():
        if sha(repo/n)!=h:
            raise ValueError("frozen plan input changed: "+n)
    old=repo/OLD
    source=checked(old/"runtime-source/binding-generation.json",PARENT)
    for n,h in source["files"].items():
        if sha(old/"runtime-source"/n)!=h:
            raise ValueError("frozen source changed: "+n)
    packages=json.loads((old/"read-input.json").read_text())
    count=0
    refusals=[]
    old_stamps=[]
    for mm,spec in zip((0,7),packages,strict=True):
        folder=old/("offset-"+str(mm))
        for n,h in spec.items():
            if sha(folder/n)!=h:
                raise ValueError("run-01 package changed: "+n)
        frames=json.loads((folder/"frame-index.json").read_text())
        for fid,key in frames.items():
            packet=checked(folder/key["file"],key["sha256"])
            if packet["frame_id"]!=fid:
                raise ValueError("run-01 source frame mismatch")
            count+=1
        audit=checked(folder/"audit.json",spec["audit.json"])
        reasons=[a for a in audit if a.get("phase")=="PRE" and "shield" in a
                  and any(r["reason_code"]=="PHYSICS_STEP_INVALID" for r in a["shield"]["evaluated_rules"])]
        refusals.append(len(reasons))
        exact=[a for a in audit if a.get("schema_version")=="native.registered.grounding.v2" and a.get("tracker_evaluated_at") and a.get("binding_now")]
        old_stamps.append(dict(native_issue_and_preview=len(exact), original_color_reference_read_utc=None,
                          reason="bootstrap color_reference has no exact evaluated-at event tied to its original frame"))
    failures=sum((old/f"read-{name}.failure.log").read_text().endswith("ValueError: initial acquisition unavailable: capture_time_not_fresh\n") for name in ("one","two"))
    if refusals!=[8,8] or failures!=2:
        raise ValueError("original failed-entry witness changed")
    return dict(plan_inputs=len(plan["input_sha256"]), parent_sources=len(source["files"]), old_raw_frames=count,
                pre_clock_refusals=refusals, cold_read_failures=failures, old_source_times=old_stamps)


def prepare(repo,folder):
    witness=frozen_inputs(repo)
    folder.mkdir(parents=True,exist_ok=False)
    dump(folder/"old-failures.json",witness)
    root=repo/OLD/"runtime-source"
    tree=folder/"runtime-source"
    parent=checked(root/"binding-generation.json",PARENT)
    files=dict(parent["files"])
    for name in sorted(files):
        path=tree/name
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,path)
    # In production the guarded colour reference is initialised from the actual handoff.
    # Add only the event record consumed by the cold reader; native checks run unchanged.
    owner="scripts/graduation/guarded_clock.py"
    scorer="scripts/graduation/g1_dual_batch_score.py"
    src=(tree/owner).read_text()
    before="        self.color, self.evidence = bootstrap_collection_tracker(handoff, self.geometry)"
    if src.count(before)!=1:
        raise ValueError("native color-reference event location changed")
    src=src.replace(before,"        color_call_start = datetime.now(UTC)\n"+before+"\n"
                    '        self.report["color_init_event"] = {\n'
                    '            "frame_id": handoff.frame_id, "checksum_sha256": handoff.checksum_sha256,\n'
                    '            "role":"color.initial", "lease_id":self.original.identity.lease_id,\n'
                    '            "captured_at":handoff.captured_at.isoformat(), "evaluated_at":self.color.last_binding_evaluated_at.isoformat(),\n'
                    '            "call_start_utc":color_call_start.isoformat(), "call_end_utc":datetime.now(UTC).isoformat(),\n'
                    '        }')
    (tree/owner).write_text(src)
    src=(tree/scorer).read_text()
    before='tracker, _ = bootstrap_collection_tracker(fetch(roles["color_reference"]), geometry)'
    if src.count(before)!=1:
        raise ValueError("cold region-reference branch changed")
    src=src.replace(before,'from scripts.graduation.qualify_archive import archived_color\n'
            '                first = next(r for r in audit if r.get("schema_version") == "native.registered.grounding.v2")\n'
            '                tracker = archived_color(fetch(roles["color_reference"]), geometry, run["color_init_event"],\n'
            '                                         first["identity"]["lease_id"], first["lease_source"]["expires_at"])')
    (tree/scorer).write_text(src)
    for name in ("qualify_native.py","qualify_archive.py"):
        target="scripts/graduation/"+name
        shutil.copyfile(HERE/name,tree/target)
        files[target]=sha(tree/target)
    for name in (owner,scorer):
        files[name]=sha(tree/name)
    dump(tree/"qualification-generation.json",dict(parent_sha256=PARENT,plan_sha256=PLAN,files=files))


def qualify(repo,folder):
    import numpy as np
    from scripts.graduation import binding as b, dynamic_vision as rt, guarded_clock, g1_dual_asset as asset
    from scripts.graduation import g1_dual_observer as observer, g1_dual_probe as probe, g1_dual_trials as dual
    from scripts.graduation import g1_visibility_trials as trials
    from scripts.graduation.g1_formal_runtime import bind_scene
    from scripts.graduation.g1_formal_trials import identities
    from scripts.graduation.perception_io import ROOT
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import _DOWNWARD
    from cloud_edge_robot_arm.simulation.mujoco.visual_servo import MuJoCoVisualServoController
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.owner_registration import _resolved_parameters, RegisteredGroundingFrameInputsV2, RegisteredGroundingPolicyV2
    from cloud_edge_robot_arm.vision.servo_region import measure_servo_region

    frozen_inputs(repo)
    gen=sha(ROOT/"qualification-generation.json")
    files=checked(ROOT/"qualification-generation.json",gen)["files"]
    if any(sha(ROOT/n)!=h for n,h in files.items()):
        raise ValueError("foreign qualification generation")
    historical=repo/"experiments/results/g1-visibility-pose-repair-20261124"
    keys=checked(historical/"batches/train-radial30-contact-d02-02/source-inventory.json","643272775723504533b27a6a6443c8624bca8f609d6c60c87af09bd90ec0868d")
    names=set(keys)|{"scripts/graduation/"+n for n in ("binding.py","binding_score.py","g1_dual_batch_score.py","g1_dual_pixel_readback.py","dynamic_vision.py","guarded_clock.py","qualify_native.py","qualify_archive.py")}
    catalog={n:files[n] for n in names}
    fixture=trials.qualified_preflight_pose(repo)
    manifests={}
    with trials.device(historical):
        for mm in (0,7):
            path=folder/f"offset-{mm}"
            path.mkdir()
            (path/"frames").mkdir()
            scene="G1_CV_QUALIFICATION_20261125"
            visual=scene+"/primary-"+str(mm)
            case=dict(**identities(visual),visual_id=visual,visual_seed=fixture["seed"],release="g1-offset-qual2-"+str(mm))
            case.update(scene_id=scene,visual_stages_in_order=["MOVE_ABOVE","APPROACH","GRASP","LIFT","MOVE_TO_REGION","PLACE","RELEASE","RETREAT"])
            geom=asset.geometry_descriptor()
            alloc=dict(case=case,geometry=geom,baseline="40f9cf2da56e7c8e4f4c5ea33dc28c8a3ae4c5d6",runtime_build_sha256=gen,
                       component_catalog_sha256=rt.digest(catalog),intent_descriptor=dict(purpose=STIMULUS,dispatch=False))
            dump(path/"allocation.json",alloc)
            ep=guarded_clock.GuardedClockEpisode(path,alloc,sha(path/"allocation.json"),catalog)
            backend=ep.backend
            frames=[]
            operations=[]
            controls={}
            times={}
            component=None
            succeeded=False
            def op(event):
                data=dict(kind=event.kind,phase=event.phase,id=event.operation_id,step=event.physics_step,episode=event.episode_id,error=event.error)
                if event.kind=="CAPTURE" and event.phase=="END" and not event.error:
                    sf=event.result["sensor_frame"]
                    data.update(frame_id=sf["frame_id"],captured_at=rt.plain(sf["captured_at"]))
                operations.append(data)
            def capture(label):
                packet=rt.Episode.capture(ep,label)
                frames.append((label,packet))
                return packet
            def timing(role,frame,lease,start,end,actual):
                return dict(**b.frame_identity(frame),role=role,lease_id=lease.lease_id,captured_at=frame.captured_at.isoformat(),
                            call_start_utc=start.isoformat(),call_end_utc=end.isoformat(),evaluated_at=actual.isoformat())
            def refuse(name,call):
                before=(backend.total_physics_steps,len(backend.command_records))
                try:
                    call()
                except ValueError as err:
                    controls[name]=dict(reason=str(err),physical_step_delta=backend.total_physics_steps-before[0],command_delta=len(backend.command_records)-before[1])
                else:
                    raise AssertionError("control unexpectedly accepted: "+name)
            try:
                backend.initialize(probe.config({"geometry":geom},fixture["seed"]))
                with bind_scene(scene), backend.observe_operation_boundaries(op):
                    mass=dual.mass_properties(backend._model)
                    x,y,z,yaw=fixture["pose_xyzyaw"]
                    scenario=rt.PhysicalScenarioConfig(scenario_id=scene,seed=fixture["seed"],object_pose=rt.Pose(x=x,y=y,z=z),object_yaw_rad=yaw)
                    backend.reset(dual.bind_scenario_mass(scenario,asset.BODY_MASS_KG,mass["mass_kg"]))
                    state=ep.robot.get_state()
                    boot=capture("original-source")
                    lease=ep.active()
                    original=ep.original=rt.build_collection_contract_v2(assignment=case,
                    current_owner=dict(task_id=case["task_id"],plan_id=case["plan_id"],issued_at=lease.acquired_at,
                    deadline_at=lease.acquired_at+timedelta(hours=1),role_sha256=rt.digest(alloc["intent_descriptor"]),lease=lease),
                    geometry=geom,source_hashes=catalog,observation=boot,protocol_settings={"timeout_basis":"physics_steps"})
                    handoff=capture("color_reference")
                    start=datetime.now(UTC)
                    ep.color,ep.evidence=rt.bootstrap_collection_tracker(handoff,geom)
                    end=datetime.now(UTC)
                    color_event=timing("color.initial",handoff,lease,start,end,ep.color.last_binding_evaluated_at)
                    ep.current=(backend.total_physics_steps,handoff)
                    current=ep.capture("MOVE_ABOVE/PRE")
                    if current is not handoff or boot.frame_id==current.frame_id or boot.sim_time_s!=current.sim_time_s:
                        raise ValueError("retained handoff mismatch")
                    ep.registered=probe.registered_tracker(current,ep.registration,catalog)
                    marker=observer.measure_frame(current,geom)
                    rot=np.array(marker["rotation_object_to_world"]).reshape(3,3)
                    angle=np.arctan2(rot[1,0],rot[0,0])
                    cid=f"existing_tool_closure_axis:{mm:+.6f}"
                    row=dict(candidate_id=cid,direction="existing_tool_closure_axis",tangent_mm=mm,offset_object_m=(np.array([np.cos(angle),-np.sin(angle),0])*mm/1000).tolist(),
                             orientation_wxyz=list(_DOWNWARD),clearance="CLEAR",proof_sha256=b.digest([STIMULUS,b.frame_identity(current),mm]))
                    table={**b.frame_identity(current),"scope":STIMULUS,"rows":[row]}
                    led=path/"grasp-binding.sqlite"
                    att=b.BoundAttempt.select(original,ep.active(),current,table,cid,ledger=led)
                    start=datetime.now(UTC)
                    ct,step,issued,online,_=att.issue_step(original,index=0,observation=current,state=state,tracker=ep.registered,
                                lease_source=ep.active(),table=table,evidence_sink=ep.audit.append)
                    end=datetime.now(UTC)
                    issue=ep.audit[-1]
                    for name,field in (("registered.preview","tracker_evaluated_at"),("registered.issue","binding_now")):
                        times[name]=timing(name,current,lease,start,end,datetime.fromisoformat(issue[field]))
                    central=_resolved_parameters(original.contract.steps[0],original,online,RegisteredGroundingFrameInputsV2.from_payload(issue["inputs"]),
                                                 RegisteredGroundingPolicyV2.from_payload(issue["policy"]))["target_pose"]
                    ep.action=ep.report["actions"][0]
                    ep.action.update(status="PREPARATION_ONLY",dispatched=False,entered_step=backend.total_physics_steps)
                    before=time.monotonic()
                    start=datetime.now(UTC)
                    try:
                        ep.admission(current,"PRE",ct,step,issued,before,None)
                        pre_reason=None
                    except rt.ComponentStopped as exc:
                        pre_reason=str(exc)
                    end=datetime.now(UTC)
                    times["color.pre"]=timing("color.pre",current,lease,start,end,ep.color.last_binding_evaluated_at)
                    pre=ep.action["pre"]
                    pre_ok=pre_reason is None and pre["shield"]["allowed"] and pre["shield"]["unmodified"]
                    start=datetime.now(UTC)
                    facts=ep.color.facts(current,state)
                    end=datetime.now(UTC)
                    times["color.facts"]=timing("color.facts",current,lease,start,end,ep.color.last_binding_evaluated_at)
                    region,reason=measure_servo_region(current,ep.color)
                    if region is None:
                        raise ValueError("reference region: "+str(reason))
                    refuse("feedback_before_dispatch",lambda:ep.check_shield(current,"FEEDBACK",ct,step,before,None))
                    refuse("post_before_return",lambda:ep.check_shield(current,"POST",ct,step,before,None))
                    refuse("unregistered",lambda:b.BoundAttempt.select(original,ep.owner.current(),current,table,"unknown",ledger=led))
                    refuse("cross_frame",lambda:b.BoundAttempt.select(original,ep.owner.current(),current,{**table,**b.frame_identity(boot)},cid,ledger=led))
                    alt=dict(row,tangent_mm=14,offset_object_m=(np.array([np.cos(angle),-np.sin(angle),0])*0.014).tolist(),candidate_id="existing_tool_closure_axis:+14.000000")
                    refuse("attempt_reselection",lambda:b.BoundAttempt.select(original,ep.owner.current(),current,dict(table,rows=[alt]),alt["candidate_id"],ledger=led))
                    altered=dict(catalog)
                    altered["scripts/graduation/binding.py"]="0"*64
                    refuse("wrong_generation",lambda:probe.registered_tracker(current,ep.registration,altered))
                    otherdir=path/"foreign-owner"
                    otherdir.mkdir()
                    othercase={**case,**identities(scene+"/foreign-"+str(mm)),"scene_id":scene,"visual_id":scene+"/foreign-"+str(mm),"release":"g1-foreign-qual-"+str(mm)}
                    other=rt.Owner(otherdir,{**alloc,"case":othercase},sha(path/"allocation.json"))
                    try:
                        refuse("foreign_lease",lambda:b.BoundAttempt.select(original,other.current(),current,table,cid,ledger=led))
                    finally:
                        other.close(False)
                    old_packet=repo/OLD/"offset-0/frames/0000.json"
                    old_frame=RGBDObservation.model_validate_json(old_packet.read_bytes())
                    refuse("stale_original",lambda:probe.registered_tracker(old_frame,ep.registration,catalog))
                    if pre_ok:
                        ref=capture("MOVE_ABOVE/servo_reference")
                        ref_start=datetime.now(UTC)
                        provider=b.BoundServoFeedback(att,issued,ref,ep.color,ep.evidence,marker_family_id=ep.registration.marker_family_id)
                        ref_end=datetime.now(UTC)
                        previous=rt.MotionTarget(rt.Pose.model_validate(step.parameters["target_pose"]),_DOWNWARD)
                        ctrl=MuJoCoVisualServoController(backend)
                        utc_begin=datetime.now(UTC)
                        n0=time.perf_counter_ns()
                        measured_frame=capture("MOVE_ABOVE/component-sample")
                        n1=time.perf_counter_ns()
                        measured=provider.update(measured_frame)
                        motion=provider.motion_target(previous,measured)
                        n2=time.perf_counter_ns()
                        q=ctrl.kinematics._inverse_kinematics(np.array([getattr(motion.position,k) for k in "xyz"]),
                                                               np.asarray(motion.orientation_wxyz),backend._model.site("tcp").id)
                        n3=time.perf_counter_ns()
                        utc_end=datetime.now(UTC)
                        component=dict(reference=ref.frame_id,reference_init_utc=[ref_start.isoformat(),ref_end.isoformat()],
                                    sample=rt.plain(provider.records[-1]),sample_utc=[utc_begin.isoformat(),utc_end.isoformat()],
                                    perf_counter_ns=[n0,n1,n2,n3],capture_ms=(n1-n0)/1e6,provider_ms=(n2-n1)/1e6,
                                    read_only_ik_ms=(n3-n2)/1e6,capture_sample_ik_ms=(n3-n0)/1e6,in_100ms=(n3-n0)<=100_000_000,
                                    native_ik_solution=None if q is None else q.tolist(),physical_step=backend.total_physics_steps,
                                    callback_executed=False,full_controller_sample_shield_ik_deadline=None)
                        refuse("in_flight_orientation",lambda:provider.motion_target(rt.MotionTarget(previous.position,(1,0,0,0)),measured))
                        refuse("substituted_endpoint",lambda:provider.motion_target(previous,rt.Pose(x=0.1,y=0.1,z=0.1)))
                    elif pre_reason is None:
                        raise ValueError("Shield result disagrees with PRE")
                    if backend.total_physics_steps!=0 or backend.command_records:
                        raise ValueError("zero-motion qualification advanced")
                    proc=dict(offset_mm=mm,generation=gen,qualification_scope=STIMULUS,actions=ep.report["actions"],
                             frame_roles=ep.roles+[{"label":n,"frame_id":f.frame_id} for n,f in frames],
                             measured_state=state.model_dump(mode="json"),physical_sample=rt.plain(backend.current_physics_observation()),
                             physics_steps=backend.total_physics_steps,commands=rt.plain(backend.command_records),operations=operations,
                             controls=controls,component_sample=component,read_times=times,color_init_event=color_event,
                             facts_readback=rt.plain(facts),region_reference=rt.plain(region),central_recipe=central,
                             admission=dict(allowed=pre_ok,reason=pre_reason,shield=pre["shield"]["allowed"],
                                            unmodified=pre["shield"]["unmodified"],conditions=pre["conditions"]),
                             action_clock=rt.plain(ep.action_clock),clock_contexts=ep.context_rows,kinematic_process="fresh process, shared imports & native owner pre before sample")
                    dump(path/"run.json",proc)
                    succeeded=True
            finally:
                backend.shutdown()
                closed=ep.owner.close(succeeded)
                dump(path/"owner.json",rt.plain(closed))
                dump(path/"audit.json",rt.plain(ep.audit))
                dump(path/"operation-boundaries.json",operations)
                index=[]
                for i,(label,f) in enumerate(frames):
                    out=path/"frames"/f"{i:04d}.json"
                    dump(out,f.model_dump(mode="json"))
                    index.append(dict(role=label,file=str(out.relative_to(path)),file_sha256=sha(out),**b.frame_identity(f)))
                dump(path/"frames.json",index)
            manifests[str(mm)]={n:sha(path/n) for n in ("run.json","owner.json","audit.json","operation-boundaries.json","frames.json","allocation.json","development-worker.db","grasp-binding.sqlite")}
    dump(folder/"sealed-inputs.json",dict(generation=gen,old_source_sha256=PARENT,plan_sha256=PLAN,cases=manifests))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("op",choices=["prepare","acquire","read"])
    ap.add_argument("repo",type=Path)
    ap.add_argument("folder",type=Path)
    ap.add_argument("out",type=Path,nargs="?")
    ap.add_argument("--seal")
    a=ap.parse_args()
    if a.op=="prepare":
        prepare(a.repo,a.folder)
    elif a.op=="acquire":
        qualify(a.repo,a.folder)
    else:
        if not a.seal:
            raise ValueError("expected sealed input digest required")
        from scripts.graduation.qualify_archive import read_case
        seals=checked(a.folder/"sealed-inputs.json",a.seal)
        tree=a.folder/"runtime-source"
        generation=checked(tree/"qualification-generation.json",seals["generation"])
        if generation["plan_sha256"]!=PLAN or any(sha(tree/n)!=h for n,h in generation["files"].items()):
            raise ValueError("changed current readback generation")
        dump(a.out,dict(sealed_input_sha256=a.seal,cases=[read_case(a.folder/f"offset-{k}",m) for k,m in seals["cases"].items()]))


if __name__=="__main__":
    main()
