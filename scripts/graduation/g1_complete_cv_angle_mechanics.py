"""Exercise the original fixed-wrist closure/lift on prospectively expanded development poses."""

import argparse
import itertools
import traceback
from pathlib import Path

import numpy as np
from scripts.graduation import g1_clearance_mount_physics as physics


ANGLES=(-4.,4.,-3.5,3.5,-3.,3.)
OFFSETS=((0,0),*[(x,y) for x,y in itertools.product((-3,0,3),repeat=2) if (x,y)!=(0,0)])


def run(out, extra_centers=False):
    out.mkdir(parents=True,exist_ok=False)
    design=[(a,xy) for a in ANGLES for xy in OFFSETS] if not extra_centers else [
        (a,(x,y)) for a,x,y in itertools.product((-3.5,0,3.5),(-4,5),(-2,0,2))]
    plan=dict(standalone_actuator_fixture=True,
              driver_sha256=physics.digest(Path(physics.__file__)),
              assembly_sha256=physics.digest(physics.ROOT/physics.mount.ASSET_PATH),
              design=design,protocol="same original actuator, three-axis state, bilateral final 120-step lift/hold, no structure contact",
              angles_extra_centers=extra_centers)
    physics.write(out/"prospective.json",plan)
    cases=[]
    for i,(angle,xy) in enumerate(design,1):
        case=f"width-{i:03d}"
        try:
            result=physics.run_case(out,case,angle,xy)
        except Exception as exc:
            result=dict(case=case,nominal_cube_yaw_deg=angle,target_offset_xy_mm=xy,eligible=False,
                        reason=str(exc),traceback=traceback.format_exc())
        physics.write(out/(case+"-summary.json"),result)
        cases.append(result)
        print(case,angle,xy,result["eligible"],result.get("reason",""),flush=True)
    physics.write(out/"summary.json",dict(prospective_sha256=physics.digest(out/"prospective.json"),
                  passed=sum(r["eligible"] for r in cases),total=len(cases),cases=cases))


def vertical(out):
    out.mkdir(parents=True,exist_ok=False)
    design=list(itertools.product((-3.,3.),(-3,3),(-2,2),(-4,4)))
    physics.write(out/"prospective.json",dict(design_xyz_mm_and_yaw=design,commands="original 60 open settle, grasp 1000ms, lift 100mm, check last 120 steps",
        assembly_sha256=physics.digest(physics.ROOT/physics.mount.ASSET_PATH)))
    cases=[]
    for i,(yaw,x,y,z) in enumerate(design,1):
        case=f"height-{i:03d}"
        backend=physics.MuJoCoPhysicsBackend()
        trace=[]
        phase="open"
        try:
            robot=physics.initialize(backend,physics.CENTER,yaw,1083,False)
            physics.set_diagnostic_arm(backend,robot,np.array(physics.CENTER)+np.array([x,y,10+z])*.001)
            def sample(state):
                trace.append(dict(phase=phase,**physics.snapshot(backend,state)))
                if trace[-1]["forbidden_pairs"]:
                    raise ValueError("physical forbidden contact")
            with backend.observe_physics_steps(sample):
                backend.step(60)
                initial=trace[-1]
                if max(initial["normal_force_N"])>0:
                    raise ValueError("physical open hand already touching")
                phase="grasp"
                closed=robot.grasp("object",timeout_ms=1000)
                phase="lift"
                lifted=robot.lift(height_m=.10,tcp_velocity=.15,acceleration=.5,timeout_ms=8000) if closed.success else None
            lift=[v for v in trace if v["phase"]=="lift"]
            held=lift[-120:]
            minimum=min((v["cube_bottom_m"]-initial["cube_bottom_m"] for v in held),default=0)
            result=dict(eligible=bool(closed.success and lifted and lifted.success and len(held)==120
                                    and all(min(v["normal_force_N"])>0 for v in held) and minimum>=.05),
                        measured_open_xyz_error_object_m=initial["xyz_error_object_m"],last_half_second_min_lift_m=minimum,
                        forbidden_contact_steps=sum(bool(v["forbidden_pairs"]) for v in trace))
            physics.write(out/(case+"-commands.json.gz"),backend.command_records)
        except Exception as exc:
            result=dict(eligible=False,reason=str(exc))
        finally:
            backend.shutdown()
        physics.write(out/(case+".json.gz"),trace)
        result.update(case=case,nominal_cube_yaw_deg=yaw,target_offset_xyz_mm=[x,y,z],
                      raw_sha256=physics.digest(out/(case+".json.gz")))
        cases.append(result)
        print(case,yaw,[x,y,z],result["eligible"],flush=True)
    physics.write(out/"summary.json",dict(total=len(cases),passed=sum(r["eligible"] for r in cases),
                                          prospective_sha256=physics.digest(out/"prospective.json"),cases=cases))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out",type=Path)
    parser.add_argument("--extra-centers",action="store_true")
    parser.add_argument("--vertical",action="store_true")
    args=parser.parse_args()
    if args.vertical:
        vertical(args.out)
    else:
        run(args.out,args.extra_centers)
